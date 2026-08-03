# -*- coding: utf-8 -*-
"""Expand LOO transfer matrix into an agent-side copy (never edits delivery).

For each held catalogue RBP with test.fasta: hide own head, batch-predict all
foreign heads on (optionally subsampled) test RNAs, write AUPRC/AUROC rows.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT.parent
if str(PKG) not in sys.path:
    sys.path.insert(0, str(PKG))

from rbp_eval.loo.heavy_loo import (  # noqa: E402
    _average_precision,
    parse_test_fasta,
    subsample,
    test_fasta_for,
)
from rbp_eval.loo.loo_eval import (  # noqa: E402
    default_expanded_transfer_dir,
    resolve_loo_csvs,
)

METRICS_NAME = "loo_transfer_metrics.csv"
SUMMARY_NAME = "loo_summary.csv"
MANIFEST_NAME = "manifest.json"
SUMMARY_FIELDS = [
    "held_rbp",
    "n_in_train",
    "own_full_auprc",
    "best_foreign_rbp",
    "best_foreign_auprc",
    "mean_foreign_auprc",
    "single_task_auprc",
    "gap_full_minus_best_foreign",
    "median_rest_delta_auprc",
    "mean_rest_delta_auprc",
]


def _auroc(y_true: list[int], y_score: list[float]) -> float:
    try:
        from sklearn.metrics import roc_auc_score

        if len(set(y_true)) < 2:
            return float("nan")
        return float(roc_auc_score(y_true, y_score))
    except Exception:
        # Mann–Whitney U / rank AUROC
        pos = [s for s, y in zip(y_score, y_true) if y == 1]
        neg = [s for s, y in zip(y_score, y_true) if y == 0]
        if not pos or not neg:
            return float("nan")
        wins = 0.0
        for p in pos:
            for n in neg:
                if p > n:
                    wins += 1.0
                elif p == n:
                    wins += 0.5
        return wins / (len(pos) * len(neg))


def _chunk(xs: list[str], size: int) -> list[list[str]]:
    if size <= 0:
        return [xs]
    return [xs[i : i + size] for i in range(0, len(xs), size)]


def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def catalogue_aliases(cohort: str = "K562") -> list[str]:
    """Aliases with a RhoBind head for ``cohort`` (registry keyed by UniProt)."""
    from app.backends.delivery.env import apply_delivery_env, load_rbp_registry

    apply_delivery_env()
    reg = load_rbp_registry()
    out: list[str] = []
    want = cohort.upper()
    if not isinstance(reg, dict):
        return []
    for _key, meta in reg.items():
        if not isinstance(meta, dict):
            continue
        alias = meta.get("alias") or meta.get("symbol") or _key
        hi = meta.get("head_index") or {}
        cohorts = meta.get("cohorts") or []
        on_cohort = False
        if isinstance(hi, dict) and any(str(k).upper() == want for k in hi):
            on_cohort = True
        elif isinstance(cohorts, (list, tuple, set)) and any(
            str(c).upper() == want for c in cohorts
        ):
            on_cohort = True
        if on_cohort and alias:
            out.append(str(alias))
    return sorted(set(out))


def seed_from_delivery(out_dir: Path) -> dict[str, Any]:
    """Copy delivery CSVs into out_dir when local files are missing/empty."""
    out_dir.mkdir(parents=True, exist_ok=True)
    metrics_out = out_dir / METRICS_NAME
    summary_out = out_dir / SUMMARY_NAME
    src_summary, src_metrics = resolve_loo_csvs(prefer_delivery=True)
    seeded = {"metrics": False, "summary": False, "src_metrics": str(src_metrics), "src_summary": str(src_summary)}
    if src_metrics.is_file() and (not metrics_out.is_file() or metrics_out.stat().st_size < 32):
        shutil.copy2(src_metrics, metrics_out)
        seeded["metrics"] = True
    if src_summary.is_file() and (not summary_out.is_file() or summary_out.stat().st_size < 32):
        shutil.copy2(src_summary, summary_out)
        seeded["summary"] = True
    # Ensure headers exist even without delivery seed
    if not metrics_out.is_file():
        metrics_out.write_text("held_rbp,foreign_rbp,auprc,auroc\n", encoding="utf-8")
    if not summary_out.is_file():
        summary_out.write_text(",".join(SUMMARY_FIELDS) + "\n", encoding="utf-8")
    return seeded


def _load_metrics_rows(path: Path) -> dict[tuple[str, str], dict[str, str]]:
    rows: dict[tuple[str, str], dict[str, str]] = {}
    if not path.is_file():
        return rows
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            key = (r["held_rbp"], r["foreign_rbp"])
            rows[key] = r
    return rows


def _load_summary_rows(path: Path) -> dict[str, dict[str, str]]:
    rows: dict[str, dict[str, str]] = {}
    if not path.is_file():
        return rows
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows[r["held_rbp"]] = r
    return rows


def _write_metrics(path: Path, rows: dict[tuple[str, str], dict[str, str]]) -> None:
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["held_rbp", "foreign_rbp", "auprc", "auroc"])
        w.writeheader()
        for key in sorted(rows.keys()):
            w.writerow(rows[key])
    tmp.replace(path)


def _write_summary(path: Path, rows: dict[str, dict[str, str]]) -> None:
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=SUMMARY_FIELDS, extrasaction="ignore")
        w.writeheader()
        for held in sorted(rows.keys()):
            row = {k: rows[held].get(k, "") for k in SUMMARY_FIELDS}
            w.writerow(row)
    tmp.replace(path)


def _load_manifest(path: Path) -> dict[str, Any]:
    if path.is_file():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {
        "schema": "loo_expand_manifest.v1",
        "completed_held": [],
        "failed_held": {},
    }


def _save_manifest(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def score_held_against_foreigns(
    held: str,
    *,
    cohort: str,
    foreigns: list[str],
    max_seqs: int,
    device: str,
    rbp_chunk: int,
    seed: int,
) -> dict[str, Any]:
    """Return metrics rows + summary stats for one held RBP."""
    from app.backends.delivery.client import DeliveryToolClient
    from app.backends.delivery.env import apply_delivery_env, resolve_delivery_paths

    apply_delivery_env()
    delivery = Path(resolve_delivery_paths()["delivery_root"])
    fasta = test_fasta_for(held, cohort, delivery)
    if fasta is None:
        return {"ok": False, "reason": f"test.fasta missing for {held}"}

    entries = parse_test_fasta(fasta)
    used = subsample(entries, max_seqs, seed=seed)
    if len(used) < 4 or sum(y for _, y in used) == 0:
        return {"ok": False, "reason": f"insufficient labeled seqs for {held}"}

    cli = DeliveryToolClient(offline=False, device=device, use_conda=True)
    cohort_u = cohort.upper() if cohort.upper() in ("K562", "HEPG2") else "K562"
    # foreign -> list of (y, prob)
    by_f: dict[str, list[tuple[int, float]]] = {f: [] for f in foreigns}
    own_pairs: list[tuple[int, float]] = []
    errors = 0

    for rna, lab in used:
        # own-head once
        own = cli.call(
            "rhobind_predict",
            {
                "rna": rna,
                "rbps": [held],
                "cohort": cohort_u,
                "device": device,
                "aggregate": "max",
                "timeout_s": 300,
            },
        )
        op = None
        for p in own.get("predictions") or []:
            if str(p.get("alias") or "") == held and p.get("prob") is not None:
                op = float(p["prob"])
                break
        if op is not None:
            own_pairs.append((lab, op))
        else:
            errors += 1

        for chunk in _chunk(foreigns, rbp_chunk):
            pred = cli.call(
                "rhobind_predict",
                {
                    "rna": rna,
                    "rbps": chunk,
                    "cohort": cohort_u,
                    "device": device,
                    "aggregate": "max",
                    "timeout_s": 600,
                },
            )
            if pred.get("error") and not pred.get("predictions"):
                errors += 1
                continue
            for p in pred.get("predictions") or []:
                alias = str(p.get("alias") or "")
                if alias == held or alias not in by_f or p.get("prob") is None:
                    continue
                by_f[alias].append((lab, float(p["prob"])))

    metrics_rows: list[dict[str, str]] = []
    foreign_auprcs: list[tuple[str, float]] = []
    for foreign, pairs in by_f.items():
        if len(pairs) < 4 or sum(y for y, _ in pairs) == 0:
            continue
        ys = [y for y, _ in pairs]
        ss = [s for _, s in pairs]
        ap = _average_precision(ys, ss)
        ar = _auroc(ys, ss)
        foreign_auprcs.append((foreign, ap))
        metrics_rows.append(
            {
                "held_rbp": held,
                "foreign_rbp": foreign,
                "auprc": f"{ap:.5f}",
                "auroc": f"{ar:.5f}" if math.isfinite(ar) else "",
            }
        )

    if not metrics_rows:
        return {"ok": False, "reason": f"no foreign AUPRC for {held}", "errors": errors}

    foreign_auprcs.sort(key=lambda t: t[1], reverse=True)
    best_f, best_a = foreign_auprcs[0]
    mean_a = sum(a for _, a in foreign_auprcs) / len(foreign_auprcs)
    own_a = None
    if len(own_pairs) >= 4 and sum(y for y, _ in own_pairs) > 0:
        own_a = _average_precision([y for y, _ in own_pairs], [s for _, s in own_pairs])

    gap = "" if own_a is None else f"{own_a - best_a:.5f}"
    summary = {
        "held_rbp": held,
        "n_in_train": str(len(foreigns)),
        "own_full_auprc": "" if own_a is None else f"{own_a:.5f}",
        "best_foreign_rbp": best_f,
        "best_foreign_auprc": f"{best_a:.5f}",
        "mean_foreign_auprc": f"{mean_a:.5f}",
        "single_task_auprc": "",
        "gap_full_minus_best_foreign": gap,
        "median_rest_delta_auprc": "",
        "mean_rest_delta_auprc": "",
    }
    return {
        "ok": True,
        "metrics_rows": metrics_rows,
        "summary": summary,
        "n_used": len(used),
        "n_foreign_scored": len(metrics_rows),
        "errors": errors,
        "test_fasta": str(fasta),
    }


def plan_helds(
    *,
    cohort: str = "K562",
    held_filter: Optional[list[str]] = None,
    skip_existing: bool = False,
    existing_held: Optional[set[str]] = None,
) -> dict[str, Any]:
    """Resolve catalogue / test.fasta / planned helds (no scoring).

    Held selection is **not** limited to the seed LOO summary (~10 rows).
    A held is planned iff it is in the cohort catalogue **and**
    ``release/.../test_data/{cohort}/{alias}/test.fasta`` exists.
    """
    from app.backends.delivery.env import apply_delivery_env, resolve_delivery_paths

    apply_delivery_env()
    delivery = Path(resolve_delivery_paths()["delivery_root"])
    aliases = catalogue_aliases(cohort)
    with_fasta = [a for a in aliases if test_fasta_for(a, cohort, delivery) is not None]
    helds = list(with_fasta)
    if held_filter:
        want = {h.upper() for h in held_filter}
        helds = [h for h in helds if h.upper() in want]
    existing = {str(x) for x in (existing_held or set())}
    # Prefer helds not already in summary (expand beyond seed first).
    new_first = [h for h in helds if h not in existing]
    old = [h for h in helds if h in existing]
    helds_ordered = new_first + old
    if skip_existing:
        helds_ordered = new_first
    fasta_paths = {
        a: str(test_fasta_for(a, cohort, delivery))
        for a in with_fasta
    }
    return {
        "cohort": cohort,
        "delivery_root": str(delivery),
        "n_catalogue": len(aliases),
        "catalogue": aliases,
        "n_with_test_fasta": len(with_fasta),
        "with_test_fasta": with_fasta,
        "test_fasta_paths": fasta_paths,
        "n_existing_summary": len(existing),
        "existing_summary_held": sorted(existing),
        "n_held_planned": len(helds_ordered),
        "held_planned": helds_ordered,
        "n_new_beyond_summary": len(new_first),
        "new_beyond_summary": new_first,
        "skip_existing": skip_existing,
        "note": (
            "Held gate = catalogue ∩ test.fasta. Seed summary (~10) is only a "
            "starting CSV copy; expand does not restrict to those aliases. "
            "If n_held_planned << n_catalogue, install more "
            "release/.../test_data/{cohort}/<ALIAS>/test.fasta (labeled POS/NEG)."
        ),
    }


def expand_loo_matrix(
    *,
    out_dir: Optional[Path] = None,
    cohort: str = "K562",
    max_seqs: int = 64,
    device: str = "cuda",
    rbp_chunk: int = 40,
    seed: int = 42,
    resume: bool = True,
    held_filter: Optional[list[str]] = None,
    skip_existing_helds: bool = False,
    list_helds_only: bool = False,
) -> dict[str, Any]:
    out_dir = Path(out_dir or default_expanded_transfer_dir()).expanduser().resolve()
    seeded = seed_from_delivery(out_dir)
    metrics_path = out_dir / METRICS_NAME
    summary_path = out_dir / SUMMARY_NAME
    manifest_path = out_dir / MANIFEST_NAME

    metrics = _load_metrics_rows(metrics_path)
    summary = _load_summary_rows(summary_path)
    manifest = _load_manifest(manifest_path)
    completed = set(manifest.get("completed_held") or [])
    if not resume:
        completed = set()
        manifest["failed_held"] = {}

    plan = plan_helds(
        cohort=cohort,
        held_filter=held_filter,
        skip_existing=skip_existing_helds,
        existing_held=set(summary.keys()),
    )
    aliases = plan["catalogue"]
    helds = list(plan["held_planned"])

    if list_helds_only:
        report = {
            "ok": True,
            "list_helds_only": True,
            "out_dir": str(out_dir),
            **{k: plan[k] for k in plan if k != "catalogue"},
            "n_catalogue": plan["n_catalogue"],
            "export_hint": f"export RBP_LOO_TRANSFER_DIR={out_dir}",
        }
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return report

    print(
        f"[expand-loo] catalogue={plan['n_catalogue']} "
        f"with_test_fasta={plan['n_with_test_fasta']} "
        f"planned={len(helds)} "
        f"new_beyond_summary={plan['n_new_beyond_summary']} "
        f"skip_existing={skip_existing_helds}",
        flush=True,
    )
    print(f"[expand-loo] planned_helds={helds}", flush=True)
    if plan["n_with_test_fasta"] == 0:
        print(
            "[expand-loo] WARN: no test.fasta under "
            f"release/.../test_data/{cohort.lower()}/<ALIAS>/ — nothing to expand.",
            flush=True,
        )
    elif plan["n_new_beyond_summary"] == 0 and not skip_existing_helds:
        print(
            "[expand-loo] NOTE: all planned helds already appear in summary "
            f"({plan['existing_summary_held']}). To grow beyond seed ~10 you need "
            "more labeled test.fasta on disk (peaks.fasta alone is POS-only).",
            flush=True,
        )

    started = datetime.now(timezone.utc).isoformat()
    manifest.update(
        {
            "schema": "loo_expand_manifest.v1",
            "cohort": cohort,
            "max_seqs": max_seqs,
            "device": device,
            "rbp_chunk": rbp_chunk,
            "seed": seed,
            "out_dir": str(out_dir),
            "seeded_from_delivery": seeded,
            "n_catalogue": len(aliases),
            "n_with_test_fasta": plan["n_with_test_fasta"],
            "n_held_planned": len(helds),
            "held_planned": helds,
            "skip_existing_helds": skip_existing_helds,
            "started_at": manifest.get("started_at") or started,
            "updated_at": started,
        }
    )
    _save_manifest(manifest_path, manifest)

    ran: list[str] = []
    for held in helds:
        if resume and held in completed:
            continue
        foreigns = [a for a in aliases if a != held]
        print(f"[expand-loo] held={held} foreigns={len(foreigns)} max_seqs={max_seqs}", flush=True)
        try:
            result = score_held_against_foreigns(
                held,
                cohort=cohort,
                foreigns=foreigns,
                max_seqs=max_seqs,
                device=device,
                rbp_chunk=rbp_chunk,
                seed=seed,
            )
        except Exception as e:  # noqa: BLE001
            result = {"ok": False, "reason": str(e)}

        if not result.get("ok"):
            manifest.setdefault("failed_held", {})[held] = result.get("reason") or "failed"
            _save_manifest(manifest_path, manifest)
            print(f"[expand-loo] FAIL {held}: {result.get('reason')}", flush=True)
            continue

        for row in result["metrics_rows"]:
            metrics[(row["held_rbp"], row["foreign_rbp"])] = row
        summary[held] = result["summary"]
        _write_metrics(metrics_path, metrics)
        _write_summary(summary_path, summary)
        completed.add(held)
        ran.append(held)
        manifest["completed_held"] = sorted(completed)
        manifest["failed_held"].pop(held, None)
        manifest["updated_at"] = datetime.now(timezone.utc).isoformat()
        manifest["metrics_sha256"] = _file_sha256(metrics_path)
        manifest["summary_sha256"] = _file_sha256(summary_path)
        _save_manifest(manifest_path, manifest)
        print(
            f"[expand-loo] OK {held} foreign_scored={result.get('n_foreign_scored')} "
            f"best={result['summary'].get('best_foreign_rbp')}",
            flush=True,
        )

    manifest["finished_at"] = datetime.now(timezone.utc).isoformat()
    manifest["n_completed"] = len(completed)
    manifest["n_ran_this_session"] = len(ran)
    _save_manifest(manifest_path, manifest)

    return {
        "ok": True,
        "out_dir": str(out_dir),
        "cohort": cohort,
        "n_catalogue": plan["n_catalogue"],
        "n_with_test_fasta": plan["n_with_test_fasta"],
        "n_held_planned": len(helds),
        "held_planned": helds,
        "n_new_beyond_summary": plan["n_new_beyond_summary"],
        "n_completed": len(completed),
        "n_ran_this_session": len(ran),
        "ran": ran,
        "metrics": str(metrics_path),
        "summary": str(summary_path),
        "manifest": str(manifest_path),
        "export_hint": f"export RBP_LOO_TRANSFER_DIR={out_dir}",
    }


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Expand LOO transfer matrix into rbp_eval copy")
    ap.add_argument("--out-dir", default=str(default_expanded_transfer_dir()))
    ap.add_argument("--cohort", default="K562")
    ap.add_argument("--max-seqs", type=int, default=64)
    ap.add_argument("--device", default=os.environ.get("RHOBIND_DEVICE", "cuda") or "cuda")
    ap.add_argument("--rbp-chunk", type=int, default=40)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--no-resume", action="store_true")
    ap.add_argument("--held", action="append", default=None, help="Limit to alias (repeatable)")
    ap.add_argument(
        "--skip-existing-helds",
        action="store_true",
        help="Skip helds already present in loo_summary.csv (focus on new test.fasta)",
    )
    ap.add_argument(
        "--list-helds",
        action="store_true",
        help="Dry-run: print catalogue / test.fasta / planned helds and exit",
    )
    args = ap.parse_args(argv)
    report = expand_loo_matrix(
        out_dir=Path(args.out_dir),
        cohort=args.cohort,
        max_seqs=int(args.max_seqs),
        device=str(args.device),
        rbp_chunk=int(args.rbp_chunk),
        seed=int(args.seed),
        resume=not bool(args.no_resume),
        held_filter=list(args.held) if args.held else None,
        skip_existing_helds=bool(args.skip_existing_helds),
        list_helds_only=bool(args.list_helds),
    )
    if not args.list_helds:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
