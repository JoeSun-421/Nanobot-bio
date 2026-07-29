# -*- coding: utf-8 -*-
"""Heavy LOO: hide own head → donor predict on test RNAs → AUPRC.

Implements Delivery agent/eval protocol (subset). Pilot-friendly ``--max-seqs``.
Does not edit delivery weights or registry.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rbp_eval.loo.loo_eval import DEFAULT_VAL, load_loo_summary, load_transfer_matrix, _paths
from rbp_eval.scoring.metrics import metrics_from_pairs

MEDOIDS = list(DEFAULT_VAL)


def _average_precision(y_true: list[int], y_score: list[float]) -> float:
    try:
        from sklearn.metrics import average_precision_score

        return float(average_precision_score(y_true, y_score))
    except Exception:
        # Rank-based AP without sklearn
        pairs = sorted(zip(y_score, y_true), key=lambda t: t[0], reverse=True)
        hits = 0
        ap_sum = 0.0
        pos = sum(y_true)
        if pos == 0:
            return 0.0
        for i, (_s, y) in enumerate(pairs, start=1):
            if y:
                hits += 1
                ap_sum += hits / i
        return ap_sum / pos


def parse_test_fasta(path: Path) -> list[tuple[str, int]]:
    """Return list of (rna_seq, label) where label 1=POS, 0=NEG."""
    text = path.read_text(encoding="utf-8", errors="replace")
    entries: list[tuple[str, int]] = []
    header = ""
    seq_parts: list[str] = []
    for line in text.splitlines():
        if line.startswith(">"):
            if header and seq_parts:
                seq = "".join(seq_parts).upper().replace("T", "U")
                lab = 0 if header.upper().startswith(">NEG") else 1
                entries.append((seq, lab))
            header = line
            seq_parts = []
        else:
            seq_parts.append(line.strip())
    if header and seq_parts:
        seq = "".join(seq_parts).upper().replace("T", "U")
        lab = 0 if header.upper().startswith(">NEG") else 1
        entries.append((seq, lab))
    return entries


def subsample(
    entries: list[tuple[str, int]],
    max_seqs: int,
    *,
    seed: int = 42,
) -> list[tuple[str, int]]:
    if max_seqs <= 0 or len(entries) <= max_seqs:
        return entries
    pos = [e for e in entries if e[1] == 1]
    neg = [e for e in entries if e[1] == 0]
    rng = random.Random(seed)
    half = max(1, max_seqs // 2)
    take_pos = pos if len(pos) <= half else rng.sample(pos, half)
    rem = max_seqs - len(take_pos)
    take_neg = neg if len(neg) <= rem else rng.sample(neg, rem)
    out = take_pos + take_neg
    rng.shuffle(out)
    return out


def test_fasta_for(alias: str, cohort: str, delivery_root: Path) -> Optional[Path]:
    c = cohort.lower()
    rel = delivery_root / "release" / "rhobind_release_v1" / "test_data" / c / alias / "test.fasta"
    if rel.is_file():
        return rel
    # Alternate layouts
    for cand in delivery_root.rglob(f"test_data/{c}/{alias}/test.fasta"):
        return cand
    return None


def pick_donors(
    held: str,
    matrix: dict[tuple[str, str], float],
    top_k: int,
) -> list[str]:
    """Use precomputed transfer matrix ranking (hide held; best foreign donors)."""
    scored = [
        (foreign, auprc)
        for (h, foreign), auprc in matrix.items()
        if h == held and foreign != held
    ]
    scored.sort(key=lambda t: t[1], reverse=True)
    return [a for a, _ in scored[: max(1, top_k)]]


def run_one_held(
    held: str,
    *,
    cohort: str = "K562",
    top_k: int = 5,
    max_seqs: int = 64,
    device: str = "cuda",
) -> dict[str, Any]:
    from app.backends.delivery.client import DeliveryToolClient
    from app.backends.delivery.env import apply_delivery_env, resolve_delivery_paths

    apply_delivery_env()
    paths = resolve_delivery_paths()
    delivery = Path(paths["delivery_root"])
    summary_path, metrics_path = _paths()
    summary = load_loo_summary(summary_path)
    matrix = load_transfer_matrix(metrics_path)

    sm = summary.get(held) or {}
    own_ceil = float(sm["own_full_auprc"]) if sm.get("own_full_auprc") else None
    best_f = float(sm["best_foreign_auprc"]) if sm.get("best_foreign_auprc") else None

    fasta = test_fasta_for(held, cohort, delivery)
    if fasta is None:
        return {
            "held_rbp": held,
            "ok": False,
            "reason": f"test.fasta missing for {held} cohort={cohort}",
        }

    entries = parse_test_fasta(fasta)
    used = subsample(entries, max_seqs)
    donors = pick_donors(held, matrix, top_k)
    if not donors:
        return {"held_rbp": held, "ok": False, "reason": "no foreign donors in transfer matrix"}

    cli = DeliveryToolClient(offline=False, device=device, use_conda=True)
    y_true: list[int] = []
    y_score: list[float] = []
    errors = 0
    for rna, lab in used:
        pred = cli.call(
            "rhobind_predict",
            {
                "rna": rna,
                "rbps": donors,
                "cohort": cohort.upper() if cohort.upper() in ("K562", "HEPG2") else "K562",
                "device": device,
                "aggregate": "max",
                "timeout_s": 180,
            },
        )
        preds = pred.get("predictions") or []
        # Hide-own-head: never use held alias even if returned
        probs = [
            float(p["prob"])
            for p in preds
            if p.get("prob") is not None and str(p.get("alias") or "") != held
        ]
        if not probs or pred.get("error"):
            errors += 1
            continue
        y_true.append(int(lab))
        y_score.append(max(probs))

    if len(y_true) < 4 or sum(y_true) == 0:
        return {
            "held_rbp": held,
            "ok": False,
            "reason": f"insufficient scored examples n={len(y_true)} pos={sum(y_true)} err={errors}",
            "donors": donors,
            "n_fasta": len(entries),
            "n_used": len(used),
        }

    auprc = _average_precision(y_true, y_score)
    pairs = [{"score": s, "y": y} for s, y in zip(y_score, y_true)]
    instance = metrics_from_pairs(pairs)
    return {
        "held_rbp": held,
        "ok": True,
        "donors": donors,
        "n_fasta": len(entries),
        "n_used": len(used),
        "n_scored": len(y_true),
        "n_pos": int(sum(y_true)),
        "n_neg": int(len(y_true) - sum(y_true)),
        "predict_errors": errors,
        "recovered_auprc": round(auprc, 5),
        "own_full_auprc": own_ceil,
        "best_foreign_auprc": best_f,
        "gap_to_own": None if own_ceil is None else round(own_ceil - auprc, 5),
        "gap_to_best_foreign": None if best_f is None else round(best_f - auprc, 5),
        "instance_metrics": instance,
        # Raw (score,y) so run_heavy_loo can pool a global instance-metrics block.
        "pairs": pairs,
        "test_fasta": str(fasta),
        "cohort": cohort,
        "max_seqs": max_seqs,
    }


def run_heavy_loo(
    *,
    rbps: list[str],
    cohort: str = "K562",
    top_k: int = 5,
    max_seqs: int = 64,
    out: Optional[Path] = None,
) -> dict[str, Any]:
    from app.core.paths import ensure_artifact_dirs, paired_md_path, report_path

    ensure_artifact_dirs()
    rows = [
        run_one_held(h, cohort=cohort, top_k=top_k, max_seqs=max_seqs) for h in rbps
    ]
    ok_rows = [r for r in rows if r.get("ok")]
    mean_rec = None
    if ok_rows:
        mean_rec = sum(float(r["recovered_auprc"]) for r in ok_rows) / len(ok_rows)
    # Pool per-instance (score,y) across all held RBPs for a global AUROC/AUPRC/ECE.
    pooled: list[dict[str, Any]] = []
    for r in ok_rows:
        pooled.extend(r.get("pairs") or [])
    pooled_metrics = metrics_from_pairs(pooled) if pooled else {
        "status": "skipped",
        "reason": "no scored instances",
        "n": 0,
    }
    # Drop the bulky raw pairs from persisted rows (kept only for pooling above).
    for r in rows:
        r.pop("pairs", None)
    report = {
        "schema": "loo_heavy.v2",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "protocol": "hide_own_head_donor_predict_test_fasta",
        "cohort": cohort,
        "top_k": top_k,
        "max_seqs": max_seqs,
        "rbps": rbps,
        "rows": rows,
        "summary": {
            "n_ok": len(ok_rows),
            "n_fail": len(rows) - len(ok_rows),
            "mean_recovered_auprc": None if mean_rec is None else round(mean_rec, 5),
            "instance_metrics_pooled": pooled_metrics,
        },
        "ok": len(ok_rows) >= 1,
    }
    out_path = out or report_path(
        f"loo_heavy_{rbps[0] if len(rbps) == 1 else 'batch'}.json"
    )
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    md = paired_md_path(out_path)
    md.parent.mkdir(parents=True, exist_ok=True)
    pm = report["summary"]["instance_metrics_pooled"]

    def _fmt(x: Any) -> str:
        return f"{x:.4f}" if isinstance(x, (int, float)) else str(x)

    lines = [
        "# Heavy LOO report",
        "",
        f"- generated: {report['generated_at']}",
        f"- cohort: {cohort} top_k={top_k} max_seqs={max_seqs}",
        f"- ok: {report['ok']} mean_recovered_auprc={report['summary']['mean_recovered_auprc']}",
        f"- pooled instance metrics: status={pm.get('status')} n={pm.get('n')} "
        f"AUROC={_fmt(pm.get('auroc'))} AUPRC={_fmt(pm.get('auprc'))} ECE={_fmt(pm.get('ece'))}",
        "",
        "| held | recovered | own_full | best_foreign | AUROC | AUPRC | ECE | donors | n_scored |",
        "|------|-----------|----------|--------------|-------|-------|-----|--------|----------|",
    ]
    for r in rows:
        im = r.get("instance_metrics") or {}
        lines.append(
            f"| {r.get('held_rbp')} | {r.get('recovered_auprc')} | {r.get('own_full_auprc')} | "
            f"{r.get('best_foreign_auprc')} | {_fmt(im.get('auroc'))} | {_fmt(im.get('auprc'))} | "
            f"{_fmt(im.get('ece'))} | {','.join(r.get('donors') or [])} | "
            f"{r.get('n_scored') or r.get('reason')} |"
        )
    md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    report["paths"] = {"json": str(out_path), "md": str(md)}
    return report


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Heavy hide-head LOO AUPRC")
    ap.add_argument("--rbp", default=None)
    ap.add_argument("--medoids", action="store_true")
    ap.add_argument("--cohort", default="K562")
    ap.add_argument("--max-seqs", type=int, default=64)
    ap.add_argument("--top-k", type=int, default=5)
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)
    if args.medoids:
        rbps = list(MEDOIDS)
    elif args.rbp:
        rbps = [str(args.rbp).strip()]
    else:
        rbps = ["PTBP1"]
    report = run_heavy_loo(
        rbps=rbps,
        cohort=str(args.cohort),
        top_k=int(args.top_k),
        max_seqs=int(args.max_seqs),
        out=Path(args.out) if args.out else None,
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
