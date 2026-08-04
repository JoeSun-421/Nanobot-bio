# -*- coding: utf-8 -*-
"""Agent-side eval harness aligned with delivery agent/eval protocol.

Given a policy (selection top_k + integrate/abstain knobs) and LOO transfer
matrix: per held RBP → recovered AUPRC, gap-to-ceiling, abstain rate; aggregate
report + end-to-end modality/prior ablations.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Iterable, Optional

from app.core.paths import REPORTS, ensure_artifact_dirs, find_report, report_path
from rbp_eval.scoring.fuse_hits import DEFAULT_WEIGHTS, fuse_rbp_hits
from rbp_eval.loo.loo_eval import load_loo_summary, resolve_loo_csvs
from rbp_eval.loo.heavy_loo import MEDOIDS

# Axis → fusion metric keys zeroed for ablation.
MODALITY_AXES: dict[str, frozenset[str]] = {
    "embedding": frozenset({"esmc_cosine", "esm2_cosine", "saprot_cosine"}),
    "structure": frozenset({"tm_score", "lddt", "fident"}),
    "sequence": frozenset({"seq_identity", "pident", "phmmer_evalue"}),
    "domain": frozenset({"domain_jaccard", "domain_overlap", "function_similarity"}),
    "rna": frozenset({"rna_embed", "rna_fm"}),
    "transfer_prior": frozenset({"transfer_prior"}),
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
    names = (
        "eval_loo_report.json",
        "heavy_loo_report.json",
        "loo_eval_report.json",
    )
    for name in names:
        found = find_report(name, root=root)
        if found is not None:
            return found
    raise FileNotFoundError(
        "LOO or heavy-LOO report required for self-evolution. "
        f"Expected one of: {', '.join(names)} under {root} (json/ or flat). "
        "Run: rbp-agent gate  or  rbp-agent heavy-loo / evolve (scored)"
    )


def _load_policy(policy_path: Optional[Path]) -> dict[str, Any]:
    if policy_path is None:
        try:
            from app.core.runtime_config import load_runtime_config

            return load_runtime_config()
        except Exception:
            return {}
    import yaml

    p = Path(policy_path).expanduser()
    if not p.is_file():
        return {}
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    return data if isinstance(data, dict) else {}


def run_policy_loo_eval(
    *,
    helds: Optional[list[str]] = None,
    cohort: str = "K562",
    top_k: int = 5,
    max_seqs: int = 64,
    device: str = "cuda",
    policy_path: Optional[Path] = None,
    transfer_dir: Optional[Path] = None,
) -> dict[str, Any]:
    """Per-RBP recovered AUPRC / gap-to-ceiling / abstain under a policy."""
    prev = os.environ.get("RBP_LOO_TRANSFER_DIR")
    if transfer_dir:
        os.environ["RBP_LOO_TRANSFER_DIR"] = str(Path(transfer_dir).expanduser().resolve())
    try:
        from rbp_eval.evolve.runner import run_scored_loo_val_batch

        policy = _load_policy(policy_path)
        tk = int(policy.get("top_k") or top_k)
        held_list = list(helds) if helds else list(MEDOIDS)
        results, held_hits, scored_labels = run_scored_loo_val_batch(
            rbps=held_list,
            top_k=tk,
            cohort=cohort,
            max_seqs=max_seqs,
            device=device,
            with_retrieval_hits=False,
        )
        per_rbp: list[dict[str, Any]] = []
        for r in results:
            alias = (r.get("query") or {}).get("alias") or r.get("alias")
            lm = r.get("loo_metrics") or {}
            verdict = r.get("verdict") or {}
            per_rbp.append(
                {
                    "held_rbp": alias,
                    "ok": bool(lm.get("recovered_auprc") is not None),
                    "recovered_auprc": lm.get("recovered_auprc"),
                    "gap_to_ceiling": lm.get("gap_to_ceiling"),
                    "own_full_auprc": lm.get("own_full_auprc"),
                    "abstain_rate": lm.get("abstain_rate"),
                    "n_scored": lm.get("n_scored"),
                    "p_hat_mean": verdict.get("p_hat"),
                    "donors": [d.get("alias") for d in (r.get("donors") or []) if isinstance(d, dict)],
                }
            )
        ok_rows = [x for x in per_rbp if x.get("ok")]
        mean_rec = (
            sum(float(x["recovered_auprc"]) for x in ok_rows) / len(ok_rows)
            if ok_rows
            else None
        )
        mean_gap = (
            sum(float(x["gap_to_ceiling"]) for x in ok_rows if x.get("gap_to_ceiling") is not None)
            / max(1, sum(1 for x in ok_rows if x.get("gap_to_ceiling") is not None))
            if ok_rows
            else None
        )
        mean_abs = (
            sum(float(x["abstain_rate"] or 0) for x in ok_rows) / len(ok_rows)
            if ok_rows
            else None
        )
        # End-to-end ablation: drop transfer_prior / domain axes on hit lists
        e2e_ablation: list[dict[str, Any]] = []
        if held_hits and mean_rec is not None:
            base_w = {**DEFAULT_WEIGHTS, **(policy.get("fusion_weights") or {})}
            # Proxy: re-fuse donors; delta on mean recovered when axis zeroed is
            # approximate (selection only). Report selection-score delta + note.
            abl = run_modality_ablation(held_hits, base_weights=base_w, top_k=tk)
            for row in abl.get("ablations") or []:
                e2e_ablation.append(
                    {
                        **row,
                        "metric": "mean_top_score_proxy",
                        "note": "selection-score delta; recovered AUPRC uses matrix donors",
                    }
                )
            # Equal-weight donors vs matrix top-k: compare mean recovered if we
            # already have per-RBP recovered (matrix path is the full policy).
            e2e_ablation.append(
                {
                    "axis": "matrix_top_k_policy",
                    "mean_recovered_auprc": mean_rec,
                    "delta_vs_full": 0.0,
                    "metric": "recovered_auprc",
                }
            )

        return {
            "schema": "run_eval/v2",
            "ok": len(ok_rows) >= 1,
            "protocol": "hide_own_head_policy_loo",
            "cohort": cohort,
            "top_k": tk,
            "max_seqs": max_seqs,
            "policy_path": str(policy_path) if policy_path else None,
            "per_rbp": per_rbp,
            "summary": {
                "n_ok": len(ok_rows),
                "n_fail": len(per_rbp) - len(ok_rows),
                "mean_recovered_auprc": mean_rec,
                "mean_gap_to_ceiling": mean_gap,
                "mean_abstain_rate": mean_abs,
                "n_scored_labels": len(scored_labels),
            },
            "modality_ablation_e2e": e2e_ablation,
            "scored_labels": scored_labels,
            "held_to_hit_lists": held_hits,
        }
    finally:
        if transfer_dir:
            if prev is None:
                os.environ.pop("RBP_LOO_TRANSFER_DIR", None)
            else:
                os.environ["RBP_LOO_TRANSFER_DIR"] = prev


def run_eval(
    *,
    held_to_hit_lists: Optional[dict[str, list[list[dict[str, Any]]]]] = None,
    scored_labels: Optional[list[dict[str, Any]]] = None,
    base_weights: Optional[dict[str, float]] = None,
    top_k: int = 5,
    out_dir: Path | None = None,
    write: bool = True,
    # Policy LOO path (spec-aligned)
    medoids: bool = False,
    helds: Optional[list[str]] = None,
    cohort: str = "K562",
    max_seqs: int = 64,
    device: str = "cuda",
    policy_path: Optional[Path] = None,
    transfer_dir: Optional[Path] = None,
) -> dict[str, Any]:
    """LOO ceiling + optional modality ablation + abstain; or full policy LOO."""
    ensure_artifact_dirs()
    out = out_dir or REPORTS
    out.mkdir(parents=True, exist_ok=True)
    (out / "json").mkdir(parents=True, exist_ok=True)

    if medoids or helds or policy_path or transfer_dir:
        policy_report = run_policy_loo_eval(
            helds=helds or (list(MEDOIDS) if medoids else None),
            cohort=cohort,
            top_k=top_k,
            max_seqs=max_seqs,
            device=device,
            policy_path=Path(policy_path) if policy_path else None,
            transfer_dir=Path(transfer_dir) if transfer_dir else None,
        )
        report = {
            **policy_report,
            "gap_to_ceiling": {
                "loo_mean_ceiling": None,
                "agent_mean": policy_report.get("summary", {}).get("mean_recovered_auprc"),
                "gap_to_ceiling": policy_report.get("summary", {}).get("mean_gap_to_ceiling"),
            },
            "abstain_rate": policy_report.get("summary", {}).get("mean_abstain_rate"),
            "status": "ok" if policy_report.get("ok") else "blocked",
        }
        # Attach classic LOO ceiling for reference
        summary_path, _ = resolve_loo_csvs()
        summary = load_loo_summary(summary_path) if summary_path and summary_path.is_file() else {}
        ceil = gap_to_ceiling_from_loo(summary)
        if report["gap_to_ceiling"].get("agent_mean") is not None and ceil.get("loo_mean_ceiling"):
            report["gap_to_ceiling"]["loo_mean_ceiling"] = ceil["loo_mean_ceiling"]
        held_to_hit_lists = policy_report.get("held_to_hit_lists") or held_to_hit_lists
        scored_labels = policy_report.get("scored_labels") or scored_labels
    else:
        summary_path, _matrix_path = resolve_loo_csvs()
        summary = load_loo_summary(summary_path) if summary_path and summary_path.is_file() else {}
        gap = gap_to_ceiling_from_loo(summary)
        abstain_rate = None
        if scored_labels:
            n = len(scored_labels)
            n_null = sum(1 for r in scored_labels if r.get("p_hat") is None)
            abstain_rate = round(n_null / n, 6) if n else None
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
        report = {
            "schema": "run_eval/v1",
            "ok": bool(summary),
            "loo_summary_path": str(summary_path) if summary_path else None,
            "gap_to_ceiling": gap,
            "abstain_rate": abstain_rate,
            "status": "ok" if summary else "blocked",
            "reason": None if summary else "missing_loo_summary",
        }

    ablation: dict[str, Any] | None = None
    if held_to_hit_lists:
        ablation = run_modality_ablation(
            held_to_hit_lists,
            base_weights=base_weights,
            top_k=top_k,
        )
        report["modality_ablation"] = ablation

    if write:
        abl_path = report_path(ABLATION_REPORT_NAME, root=out)
        if ablation is not None:
            abl_path.parent.mkdir(parents=True, exist_ok=True)
            abl_path.write_text(
                json.dumps(ablation, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            report.setdefault("paths", {})["ablation"] = str(abl_path)
        re_path = report_path(RUN_EVAL_REPORT_NAME, root=out)
        re_path.parent.mkdir(parents=True, exist_ok=True)
        # Drop bulky scored_labels from disk report (keep counts)
        disk = {k: v for k, v in report.items() if k not in ("scored_labels", "held_to_hit_lists")}
        re_path.write_text(
            json.dumps(disk, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        report.setdefault("paths", {})["run_eval"] = str(re_path)
        # Markdown summary
        md_path = re_path.with_suffix(".md")
        if re_path.name.endswith(".json"):
            from app.core.paths import paired_md_path

            md_path = paired_md_path(re_path)
        lines = [
            "# run_eval report",
            "",
            f"- schema: {report.get('schema')}",
            f"- status: {report.get('status')}",
            f"- summary: {json.dumps(report.get('summary') or report.get('gap_to_ceiling'), ensure_ascii=False)}",
            "",
        ]
        if report.get("per_rbp"):
            lines += [
                "| held | recovered | gap | abstain | n |",
                "|------|-----------|-----|---------|---|",
            ]
            for row in report["per_rbp"]:
                lines.append(
                    f"| {row.get('held_rbp')} | {row.get('recovered_auprc')} | "
                    f"{row.get('gap_to_ceiling')} | {row.get('abstain_rate')} | "
                    f"{row.get('n_scored')} |"
                )
        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        report.setdefault("paths", {})["md"] = str(md_path)

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
    ap.add_argument("--medoids", action="store_true")
    ap.add_argument("--held", action="append", default=None)
    ap.add_argument("--cohort", default="K562")
    ap.add_argument("--max-seqs", type=int, default=64)
    ap.add_argument("--policy", default=None)
    ap.add_argument("--transfer-dir", default=None)
    ap.add_argument("--device", default=None)
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
    device = args.device or os.environ.get("RHOBIND_DEVICE") or "cuda"
    report = run_eval(
        held_to_hit_lists=held,
        top_k=args.top_k,
        out_dir=out_dir,
        medoids=bool(args.medoids),
        helds=list(args.held) if args.held else None,
        cohort=str(args.cohort),
        max_seqs=int(args.max_seqs),
        device=str(device),
        policy_path=Path(args.policy) if args.policy else None,
        transfer_dir=Path(args.transfer_dir) if args.transfer_dir else None,
    )
    print(json.dumps({k: v for k, v in report.items() if k not in ("scored_labels", "held_to_hit_lists")}, indent=2, ensure_ascii=False)[:6000])
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
