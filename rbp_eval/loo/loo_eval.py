#!/usr/bin/env python3
"""LOO light eval: hide-own-head donor policy vs precomputed transfer AUPRC.

Protocol (NOT a RhoBind re-run on test FASTA):
  1. For each held-out catalogue RBP, select donors via domain (+ optional ESM).
  2. Look up measured transfer AUPRC in delivery-only CSV
     (agent_db/transfer/loo_transfer_metrics.csv + loo_summary.csv).
  3. Compare policy_best / policy_mean to own_full_auprc and best_foreign.

Heavy force_transfer (re-predict on test_data) is deferred — see docs/工程指南.zh.md §6.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parents[1]  # nanobot-bio
sys.path.insert(0, str(ROOT))

from app.core.paths import DEFAULT_LOO_REPORT, ensure_artifact_dirs
from rbp_eval.scoring.metrics import metrics_from_pairs

DEFAULT_VAL = [
    "NSUN2",
    "FXR2",
    "HNRNPUL1",
    "EEF2",
    "PTBP1",
    "CPSF6",
    "DHX30",
    "DDX51",
    "DROSHA",
    "RPS6",
]


def load_loo_summary(path: Path) -> dict[str, dict[str, Any]]:
    rows = {}
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows[r["held_rbp"]] = r
    return rows


def load_transfer_matrix(path: Path) -> dict[tuple[str, str], float]:
    m: dict[tuple[str, str], float] = {}
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            m[(r["held_rbp"], r["foreign_rbp"])] = float(r["auprc"])
    return m


#: Delivery layouts where the LOO transfer CSVs may live, relative to a base dir.
#: ``agent_db`` first (installed bundle), then the in-source ``agent/database``.
_LOO_CSV_SUBDIRS = (
    ("agent_db", "transfer"),
    ("agent", "database", "transfer"),
)


def default_expanded_transfer_dir() -> Path:
    """Agent-side LOO matrix copy (not delivery SoT)."""
    return Path(__file__).resolve().parents[1] / "data" / "transfer"


def resolve_loo_csvs(
    transfer_dir: Optional[Path | str] = None,
    *,
    prefer_delivery: bool = False,
) -> tuple[Path, Path]:
    """Locate loo_summary.csv + loo_transfer_metrics.csv.

    Priority (unless ``prefer_delivery``):
      1. Explicit ``transfer_dir`` argument
      2. ``RBP_LOO_TRANSFER_DIR`` env (agent-side expanded copy)
      3. Delivery layouts under ``agent_db`` / delivery root

    Shared by loo_eval, retune, heavy_loo, transfer_calibration, expand_matrix.
    """
    import os

    from app.backends.delivery.env import apply_delivery_env, resolve_delivery_paths

    apply_delivery_env()

    explicit = transfer_dir or os.environ.get("RBP_LOO_TRANSFER_DIR")
    if not prefer_delivery and explicit:
        base = Path(str(explicit)).expanduser().resolve()
        summary = base / "loo_summary.csv"
        metrics = base / "loo_transfer_metrics.csv"
        if summary.is_file() and metrics.is_file():
            return summary, metrics
        # Prefer explicit dir even if incomplete so callers report clear missing paths
        if base.is_dir() or explicit:
            return summary, metrics

    paths = resolve_delivery_paths()
    agent_db = Path(paths["agent_db"])
    root = Path(paths["delivery_root"])

    def _candidates(name: str) -> list[Path]:
        cands = [agent_db / "transfer" / name]
        for sub in _LOO_CSV_SUBDIRS:
            cands.append(root.joinpath(*sub, name))
        seen: set[str] = set()
        out: list[Path] = []
        for c in cands:
            k = str(c)
            if k not in seen:
                seen.add(k)
                out.append(c)
        return out

    def _pick(name: str) -> Path:
        cands = _candidates(name)
        for c in cands:
            if c.is_file():
                return c
        return cands[0]

    return _pick("loo_summary.csv"), _pick("loo_transfer_metrics.csv")


def _paths(transfer_dir: Optional[Path | str] = None):
    return resolve_loo_csvs(transfer_dir=transfer_dir)


def policy_from_hits(
    held: str,
    hits: list[dict[str, Any]],
    matrix: dict[tuple[str, str], float],
    top_k: int,
) -> dict[str, Any]:
    from rbp_eval.scoring.fuse_hits import fuse_rbp_hits

    hits = [h for h in hits if h.get("alias") and h.get("alias") != held]
    donors = fuse_rbp_hits([hits], top_k=top_k, exclude_aliases={held})
    vals = []
    for d in donors:
        a = matrix.get((held, d["alias"]))
        if a is not None:
            vals.append(a)
    return {
        "donors": [d["alias"] for d in donors],
        "policy_best": max(vals) if vals else None,
        "policy_mean": (sum(vals) / len(vals)) if vals else None,
        "n_measured": len(vals),
    }


def _fetch_domain_hits(cli: Any, held: str, top_k: int) -> tuple[list[dict], Optional[str]]:
    try:
        out = cli.call("domain_architecture", {"alias": held, "top_k": top_k * 2})
        if out.get("error"):
            return [], str(out["error"])
        return list(out.get("hits") or []), None
    except Exception as e:
        return [], str(e)


def _fetch_seq_hits(cli: Any, held: str, top_k: int) -> tuple[list[dict], Optional[str]]:
    """Best-effort ESM axis; failures are recorded without synthetic scores."""
    try:
        import os

        from nanobot.agent.tools.rbp.common import load_catalogue_sequence

        seq = load_catalogue_sequence(held) or ""
        if not seq:
            return [], f"no AA sequence for {held}"
        dev = os.environ.get("RHOBIND_DEVICE", "cpu")
        if dev == "auto":
            dev = "cuda"
        if dev not in ("cuda", "cpu"):
            dev = "cpu"
        out = cli.call(
            "esm_similarity",
            {
                "sequence": seq,
                "encoder": "esmc",
                "device": dev,
                "top_k": top_k * 2,
            },
        )
        if out.get("error") and not out.get("hits"):
            return [], str(out["error"])
        return list(out.get("hits") or []), (str(out["error"]) if out.get("error") else None)
    except Exception as e:
        return [], str(e)


def _mean(xs: list[Any]) -> Optional[float]:
    vals = [float(x) for x in xs if x is not None]
    return sum(vals) / len(vals) if vals else None


def _write_markdown_summary(path: Path, payload: dict[str, Any]) -> None:
    rows = payload.get("rows") or []
    lines = [
        "# LOO light report",
        "",
        f"- protocol: `{payload.get('protocol')}`",
        f"- n: **{payload.get('n')}**",
        f"- mean policy_best AUPRC: **{payload.get('summary', {}).get('mean_policy_best')}**",
        f"- mean own_full AUPRC: **{payload.get('summary', {}).get('mean_own_full_auprc')}**",
        f"- mean gap (own − policy_best): **{payload.get('summary', {}).get('mean_gap_to_own')}**",
        "",
        "| held_rbp | own_full | policy_best | best_foreign | donors | status |",
        "|---|---:|---:|---:|---|---|",
    ]
    for r in rows:
        status = "ok" if r.get("policy_best") is not None else "fail_no_measured_donors"
        donors = ",".join((r.get("donors") or [])[:3]) or "-"
        lines.append(
            f"| {r.get('held_rbp')} | {r.get('own_full_auprc')} | {r.get('policy_best')} | "
            f"{r.get('best_foreign_auprc')} | {donors} | {status} |"
        )
    fails = payload.get("failures") or []
    if fails:
        lines.extend(["", "## Failures", ""])
        for f in fails:
            lines.append(f"- **{f.get('held_rbp')}**: {f.get('reason')}")
    defs = payload.get("deficiencies") or []
    if defs:
        lines.extend(["", "## Deficiencies", ""])
        for d in defs:
            lines.append(f"- {d}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    from app.backends.delivery.client import DeliveryToolClient

    ensure_artifact_dirs()
    ap = argparse.ArgumentParser(description="LOO light: donor policy vs CSV transfer AUPRC")
    ap.add_argument("--top-k", type=int, default=5)
    ap.add_argument("--out", default=str(DEFAULT_LOO_REPORT))
    ap.add_argument("--with-seq", action="store_true", help="Also try ESM donor axis (needs conda)")
    ap.add_argument("--ablation", action="store_true", help="Record modality ablation notes")
    ap.add_argument(
        "--labels",
        type=str,
        default=None,
        help="JSON list of {p_hat|score, y, label?} for instance AUROC/AUPRC/ECE (A5)",
    )
    args = ap.parse_args()

    summary_path, metrics_path = _paths()
    if not summary_path.is_file() or not metrics_path.is_file():
        print(f"ERROR: missing LOO CSV (summary={summary_path} metrics={metrics_path})", file=sys.stderr)
        return 2

    summary = load_loo_summary(summary_path)
    matrix = load_transfer_matrix(metrics_path)
    # Offline domain is enough for light; seq needs protein_embed when --with-seq
    cli = DeliveryToolClient(offline=True, use_conda=bool(args.with_seq), device="cpu")

    report_rows: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    deficiencies: list[str] = [
        "Light protocol: does not re-run RhoBind on test FASTA (needs rhobind env + panels).",
        "LOO priors calibrate transfer-as-a-method on held-out catalogue RBPs; "
        "dark/novel UniProt IDs correctly have no per-target LOO prior.",
    ]
    seq_errors: list[str] = []

    for held in DEFAULT_VAL:
        domain_hits, domain_err = _fetch_domain_hits(cli, held, args.top_k)
        combined: list[dict] = list(domain_hits)
        modality = "domain" if domain_hits else "none"
        if args.with_seq:
            seq_hits, seq_err = _fetch_seq_hits(cli, held, args.top_k)
            if seq_err:
                seq_errors.append(f"{held}: {seq_err[:120]}")
            if seq_hits:
                combined.extend(seq_hits)
                modality = "domain+seq" if domain_hits else "seq"

        if not combined:
            pol = {
                "donors": [],
                "policy_best": None,
                "policy_mean": None,
                "n_measured": 0,
            }
            reason = domain_err or "no domain/seq hits"
            failures.append({"held_rbp": held, "reason": reason})
        else:
            pol = policy_from_hits(held, combined, matrix, args.top_k)
            if pol["policy_best"] is None:
                failures.append(
                    {
                        "held_rbp": held,
                        "reason": f"donors={pol['donors']} but none in loo_transfer_metrics",
                    }
                )

        sm = summary.get(held, {})
        own = float(sm["own_full_auprc"]) if sm.get("own_full_auprc") else None
        best_f = float(sm["best_foreign_auprc"]) if sm.get("best_foreign_auprc") else None
        mean_f = float(sm["mean_foreign_auprc"]) if sm.get("mean_foreign_auprc") else None
        report_rows.append(
            {
                "held_rbp": held,
                "modality": modality,
                **pol,
                "own_full_auprc": own,
                "best_foreign_auprc": best_f,
                "mean_foreign_auprc": mean_f,
                "gap_to_own": None
                if pol["policy_best"] is None or own is None
                else own - pol["policy_best"],
                "gap_to_best_foreign": (
                    None
                    if pol["policy_best"] is None or best_f is None
                    else best_f - pol["policy_best"]
                ),
            }
        )

    if seq_errors:
        deficiencies.append(
            "ESM axis unavailable or partial: " + "; ".join(seq_errors[:5])
        )
    else:
        deficiencies.append(
            "Donor selection default=domain-only; pass --with-seq for ESM-C axis."
        )

    ablation: dict[str, Any] = {}
    if args.ablation:
        ablation["domain_only"] = {
            "mean_policy_best": _mean([r["policy_best"] for r in report_rows]),
            "mean_gap_to_best_foreign": _mean([r["gap_to_best_foreign"] for r in report_rows]),
            "note": "emb/seq/struct full ablation needs protein_embed + foldseek envs",
        }

    summary_block = {
        "mean_policy_best": _mean([r["policy_best"] for r in report_rows]),
        "mean_policy_mean": _mean([r["policy_mean"] for r in report_rows]),
        "mean_own_full_auprc": _mean([r["own_full_auprc"] for r in report_rows]),
        "mean_best_foreign_auprc": _mean([r["best_foreign_auprc"] for r in report_rows]),
        "mean_gap_to_own": _mean([r["gap_to_own"] for r in report_rows]),
        "n_ok": sum(1 for r in report_rows if r.get("policy_best") is not None),
        "n_fail": len(failures),
    }

    out = Path(args.out)
    if not out.is_absolute():
        out = ROOT / out
    out.parent.mkdir(parents=True, exist_ok=True)

    # A5: instance-level metrics (AUROC/AUPRC/ECE) shared with evaluation_plan.
    instance_level: dict[str, Any] = {
        "status": "skipped",
        "reason": "no --labels JSON provided (light protocol is transfer-CSV only)",
        "auroc": None,
        "auprc": None,
        "ece": None,
    }
    if args.labels:
        labels_path = Path(args.labels)
        if labels_path.is_file():
            try:
                raw = json.loads(labels_path.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    pairs = raw.get("scored_labels") or raw.get("pairs") or []
                else:
                    pairs = raw
                instance_level = metrics_from_pairs(list(pairs))
                instance_level["source"] = str(labels_path)
            except Exception as e:  # noqa: BLE001
                instance_level = {
                    "status": "error",
                    "reason": f"{type(e).__name__}: {e}",
                    "auroc": None,
                    "auprc": None,
                    "ece": None,
                }
        else:
            instance_level = {
                "status": "error",
                "reason": f"labels file not found: {labels_path}",
                "auroc": None,
                "auprc": None,
                "ece": None,
            }

    payload = {
        "protocol": "LOO light: hide head, select donors, lookup loo_transfer_metrics (no RhoBind re-run)",
        "val_set": DEFAULT_VAL,
        "n": len(report_rows),
        "summary": summary_block,
        "instance_level": instance_level,
        "rows": report_rows,
        "failures": failures,
        "ablation": ablation,
        "deficiencies": deficiencies,
        "sources": {
            "loo_summary": str(summary_path),
            "loo_transfer_metrics": str(metrics_path),
        },
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    from app.core.paths import paired_md_path

    md = paired_md_path(out)
    md.parent.mkdir(parents=True, exist_ok=True)
    _write_markdown_summary(md, payload)

    print(f"wrote {out}")
    print(f"wrote {md}")
    print(
        f"summary mean_policy_best={summary_block['mean_policy_best']} "
        f"mean_own={summary_block['mean_own_full_auprc']} "
        f"ok={summary_block['n_ok']}/{payload['n']}"
    )
    for row in report_rows:
        print(
            f"{row['held_rbp']:12} policy_best={row['policy_best']} "
            f"own={row['own_full_auprc']} donors={row['donors'][:3]}"
        )
    if len(report_rows) < 10:
        print("WARN: n<10 held-out RBPs", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
