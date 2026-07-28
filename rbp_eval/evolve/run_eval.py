# -*- coding: utf-8 -*-
"""Agent-side eval harness: LOO ceiling gap + modality ablation (DESIGN Phase 2)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Optional

from app.core.paths import REPORTS, ensure_artifact_dirs
from rbp_eval.scoring.fuse_hits import DEFAULT_WEIGHTS, fuse_rbp_hits
from rbp_eval.loo.loo_eval import load_loo_summary, resolve_loo_csvs

# Axis → fusion metric keys zeroed for ablation.
MODALITY_AXES: dict[str, frozenset[str]] = {
    "embedding": frozenset({"esmc_cosine", "esm2_cosine", "saprot_cosine"}),
    "structure": frozenset({"tm_score", "lddt", "fident"}),
    "sequence": frozenset({"seq_identity", "pident", "phmmer_evalue"}),
    "domain": frozenset({"domain_jaccard", "domain_overlap", "function_similarity"}),
    "rna": frozenset({"rna_embed", "rna_fm"}),
}

ABLATION_REPORT_NAME = "modality_ablation_report.json"
RUN_EVAL_REPORT_NAME = "run_eval_report.json"


def _weights_with_axis_off(
    base: dict[str, float],
    axis: str,
) -> dict[str, float]:
    keys = MODALITY_AXES.get(axis) or frozenset()
    out = dict(base)
    for k in keys:
        out[k] = 0.0
    return out


def _mean_top_score(
    held_to_hit_lists: dict[str, list[list[dict[str, Any]]]],
    weights: dict[str, float],
    *,
    top_k: int = 5,
) -> float:
    """Mean fused top-1 donor score across held RBPs (proxy when no labels)."""
    scores: list[float] = []
    for held, lists in held_to_hit_lists.items():
        if not lists or not any(lists):
            continue
        donors = fuse_rbp_hits(
            lists,
            top_k=top_k,
            exclude_aliases={held},
            weights=weights,
            use_rank_normalize=True,
            tau_drop=0.30,
        )
        if donors:
            try:
                scores.append(float(donors[0].get("score") or 0.0))
            except (TypeError, ValueError):
                continue
    if not scores:
        return 0.0
    return sum(scores) / len(scores)


def run_modality_ablation(
    held_to_hit_lists: dict[str, list[list[dict[str, Any]]]],
    *,
    base_weights: Optional[dict[str, float]] = None,
    top_k: int = 5,
    axes: Optional[Iterable[str]] = None,
) -> dict[str, Any]:
    """Typed modality ablation: zero each axis and report delta vs full fusion."""
    w0 = {**DEFAULT_WEIGHTS, **(base_weights or {})}
    # Mock RNA must not contribute to baseline.
    w0["rna_embed"] = 0.0
    w0["rna_fm"] = 0.0
    full = _mean_top_score(held_to_hit_lists, w0, top_k=top_k)
    axis_list = list(axes) if axes is not None else list(MODALITY_AXES.keys())
    rows: list[dict[str, Any]] = []
    for axis in axis_list:
        if axis not in MODALITY_AXES:
            continue
        w = _weights_with_axis_off(w0, axis)
        scored = _mean_top_score(held_to_hit_lists, w, top_k=top_k)
        rows.append(
            {
                "axis": axis,
                "mean_top_score": round(scored, 6),
                "delta_vs_full": round(scored - full, 6),
                "zeroed_keys": sorted(MODALITY_AXES[axis]),
            }
        )
    return {
        "schema": "modality_ablation/v1",
        "full_mean_top_score": round(full, 6),
        "n_held": len(held_to_hit_lists),
        "ablations": rows,
    }


def gap_to_ceiling_from_loo(
    summary: dict[str, dict[str, Any]],
    *,
    metric: str = "auprc",
) -> dict[str, Any]:
    """Aggregate LOO summary into mean ceiling + placeholder agent gap fields."""
    vals: list[float] = []
    for _alias, row in summary.items():
        try:
            v = float(row.get(metric) or row.get(metric.upper()) or 0.0)
        except (TypeError, ValueError):
            continue
        if v > 0:
            vals.append(v)
    mean_ceiling = sum(vals) / len(vals) if vals else 0.0
    return {
        "metric": metric,
        "n_rbps": len(vals),
        "loo_mean_ceiling": round(mean_ceiling, 6),
        "agent_mean": None,
        "gap_to_ceiling": None,
        "note": (
            "agent_mean filled when scored (p_hat,y) pairs are supplied; "
            "ceiling from delivery loo_summary"
        ),
    }


def results_are_retrieval_only_synthetic(results: list[dict[str, Any]]) -> bool:
    """True when every row is retrieval_only with null p_hat (not promotable scores)."""
    if not results:
        return False
    for r in results:
        if r.get("mode") != "retrieval_only":
            return False
        v = r.get("verdict") or {}
        if v.get("p_hat") is not None:
            return False
    return True


def assert_not_synthetic_promote_input(results: list[dict[str, Any]]) -> None:
    if results_are_retrieval_only_synthetic(results):
        raise ValueError(
            "Refuse promote/evolve scoring on retrieval-only synthetic No/p_hat=null "
            "batches. Use heavy-loo / agent scored labels / evolve-eval real scores."
        )


def require_loo_or_heavy_report(
    *,
    reports_dir: Path | None = None,
) -> Path:
    """Return path to an existing LOO or heavy-LOO report; raise if neither exists."""
    root = reports_dir or REPORTS
    candidates = [
        root / "eval_loo_report.json",
        root / "heavy_loo_report.json",
        root / "loo_eval_report.json",
    ]
    for p in candidates:
        if p.is_file():
            return p
    raise FileNotFoundError(
        "LOO or heavy-LOO report required for self-evolution. "
        f"Expected one of: {', '.join(c.name for c in candidates)} under {root}. "
        "Run: rbp-agent gate  or  rbp-agent heavy-loo"
    )


def run_eval(
    *,
    held_to_hit_lists: Optional[dict[str, list[list[dict[str, Any]]]]] = None,
    scored_labels: Optional[list[dict[str, Any]]] = None,
    base_weights: Optional[dict[str, float]] = None,
    top_k: int = 5,
    out_dir: Path | None = None,
    write: bool = True,
) -> dict[str, Any]:
    """
    DESIGN-aligned run_eval: LOO ceiling + optional modality ablation + abstain rate.

    Does not invent RhoBind scores; ablation uses retrieval hit lists when provided.
    """
    ensure_artifact_dirs()
    out = out_dir or REPORTS
    out.mkdir(parents=True, exist_ok=True)

    summary_path, _matrix_path = resolve_loo_csvs()
    summary = load_loo_summary(summary_path) if summary_path and summary_path.is_file() else {}
    gap = gap_to_ceiling_from_loo(summary)

    abstain_rate = None
    if scored_labels:
        n = len(scored_labels)
        n_null = sum(1 for r in scored_labels if r.get("p_hat") is None)
        abstain_rate = round(n_null / n, 6) if n else None
        # Fill agent mean when labels present
        ys = []
        for r in scored_labels:
            try:
                if r.get("p_hat") is not None:
                    ys.append(float(r["p_hat"]))
            except (TypeError, ValueError):
                continue
        if ys:
            agent_mean = sum(ys) / len(ys)
            gap["agent_mean"] = round(agent_mean, 6)
            gap["gap_to_ceiling"] = round(gap["loo_mean_ceiling"] - agent_mean, 6)

    ablation: dict[str, Any] | None = None
    if held_to_hit_lists:
        ablation = run_modality_ablation(
            held_to_hit_lists,
            base_weights=base_weights,
            top_k=top_k,
        )

    report: dict[str, Any] = {
        "schema": "run_eval/v1",
        "ok": bool(summary),
        "loo_summary_path": str(summary_path) if summary_path else None,
        "gap_to_ceiling": gap,
        "abstain_rate": abstain_rate,
        "modality_ablation": ablation,
        "status": "ok" if summary else "blocked",
        "reason": None if summary else "missing_loo_summary",
    }

    if write:
        abl_path = out / ABLATION_REPORT_NAME
        if ablation is not None:
            abl_path.write_text(
                json.dumps(ablation, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            report["paths"] = {"ablation": str(abl_path)}
        re_path = out / RUN_EVAL_REPORT_NAME
        re_path.write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        report.setdefault("paths", {})["run_eval"] = str(re_path)

    return report


def main(argv: Optional[list[str]] = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="Agent run_eval + modality ablation")
    ap.add_argument(
        "--hits-json",
        default=None,
        help="JSON {held: [[hits...], ...]} for ablation (optional)",
    )
    ap.add_argument("--top-k", type=int, default=5)
    ap.add_argument("--out-dir", default=None)
    args = ap.parse_args(argv)

    held = None
    if args.hits_json:
        p = Path(args.hits_json)
        raw = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(raw, dict) and "held_to_hit_lists" in raw:
            held = raw["held_to_hit_lists"]
        elif isinstance(raw, dict):
            held = raw
    out_dir = Path(args.out_dir) if args.out_dir else None
    report = run_eval(held_to_hit_lists=held, top_k=args.top_k, out_dir=out_dir)
    print(json.dumps(report, indent=2, ensure_ascii=False)[:4000])
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
