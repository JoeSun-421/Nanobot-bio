# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

from app.core.paths import (
    DEFAULT_EVOLVE_REPORT,
    PACKAGE_ROOT,
    PROXY_CACHE,
    ensure_artifact_dirs,
)
from rbp_eval.evolve.promote import (
    CANDIDATE_CONFIG,
    EVOLVED_CONFIG,
    EVOLVED_REPORT,
    write_evolved_config,
)
from rbp_eval.evolve.proposals import propose_toolkit_expansions, tool_attribution
from rbp_eval.evolve.proxy_cache import promote_from_traces
from rbp_eval.evolve.retune import (
    _hit_lists_from_results,
    retune_abstain_thresholds,
    retune_fusion_on_dval_ce,
    retune_label_thresholds,
    retune_tau_drop,
    retune_weights,
)

ensure_artifact_dirs()

@dataclass
class EvolutionReport:
    n_traces: int = 0
    n_val: int = 0
    tool_attribution: dict[str, Any] = field(default_factory=dict)
    weight_retune: dict[str, Any] = field(default_factory=dict)
    dval_ce_retune: dict[str, Any] = field(default_factory=dict)
    threshold_retune: dict[str, Any] = field(default_factory=dict)
    abstain_retune: dict[str, Any] = field(default_factory=dict)
    tau_drop_retune: dict[str, Any] = field(default_factory=dict)
    toolkit_proposals: list[dict[str, Any]] = field(default_factory=list)
    cache_promotion: dict[str, Any] = field(default_factory=dict)
    promotion_evidence: dict[str, Any] = field(default_factory=dict)
    transfer_dir: Optional[str] = None
    evolved_config_path: Optional[str] = None
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def run_self_evolution(
    results: list[dict[str, Any]],
    *,
    held_to_hit_lists: Optional[dict[str, list[list[dict[str, Any]]]]] = None,
    scored_labels: Optional[list[dict[str, Any]]] = None,
    traces: Optional[list[dict[str, Any]]] = None,
    base_weights: Optional[dict[str, float]] = None,
    top_k: int = 5,
    write_config: bool = True,
    require_loo_report: bool = True,
    allow_retrieval_only: bool = False,
    transfer_dir: Optional[str | Path] = None,
) -> EvolutionReport:
    """
    Full offline self-evolution loop.

    Parameters
    ----------
    results
        Per-query agent/pipeline outputs (with retrieval, evidence_table, verdict).
    held_to_hit_lists
        For weight retune: held_rbp → list of hit lists (modalities).
        If None, built from results' retrieval when possible.
    scored_labels
        Optional [{p_hat, y}] for threshold calibration.
    traces
        Optional raw JSONL events for cache promotion.
    require_loo_report
        When True (default), block without LOO/heavy-LOO report on disk.
    allow_retrieval_only
        When False (default), retrieval-only synthetic batches cannot write a
        promotable candidate (weight retune from hits may still run for research).
    """
    from rbp_eval.evolve.run_eval import (
        require_loo_or_heavy_report,
        results_are_retrieval_only_synthetic,
        run_eval,
    )

    prev_transfer = os.environ.get("RBP_LOO_TRANSFER_DIR")

    def _restore_transfer_env() -> None:
        if transfer_dir:
            if prev_transfer is None:
                os.environ.pop("RBP_LOO_TRANSFER_DIR", None)
            else:
                os.environ["RBP_LOO_TRANSFER_DIR"] = prev_transfer

    if transfer_dir:
        os.environ["RBP_LOO_TRANSFER_DIR"] = str(Path(transfer_dir).expanduser().resolve())

    report = EvolutionReport(n_val=len(results), n_traces=len(traces or []))
    report.transfer_dir = os.environ.get("RBP_LOO_TRANSFER_DIR")
    report.promotion_evidence = {
        "status": "required_at_promote",
        "metric": "real_transfer_calibration.delta_auprc",
        "minimum_n": 10,
        "required_manifests": [
            "source_manifest",
            "split_manifest",
            "policy_manifest",
            "objective",
            "before_after_metrics",
            "rollback",
        ],
        "note": (
            "Retrieval-only and delivery-CSV proxy scores are not promotion metrics; "
            "promote-evolved validates the real RhoBind transfer-calibration report."
        ),
    }
    report_dict_extra: dict[str, Any] = {}

    if require_loo_report:
        try:
            loo_path = require_loo_or_heavy_report()
            report.notes.append(f"loo_report={loo_path}")
        except FileNotFoundError as e:
            report.notes.append(str(e))
            report_dict_extra["status"] = "blocked"
            report_dict_extra["reason"] = "missing_loo_or_heavy_report"
            report_dict_extra["promote_blocked"] = True
            EVOLVED_REPORT.parent.mkdir(parents=True, exist_ok=True)
            payload = {**report.to_dict(), **report_dict_extra}
            EVOLVED_REPORT.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            report.notes.append(f"Report → {EVOLVED_REPORT}")
            report.evolved_config_path = None
            _restore_transfer_env()
            return report

    synthetic = results_are_retrieval_only_synthetic(results)
    if synthetic:
        report_dict_extra["scores_source"] = "retrieval_only_synthetic"
        report.notes.append(
            "Input is retrieval-only synthetic (p_hat=null); "
            "candidate promote path blocked unless allow_retrieval_only."
        )
        if not allow_retrieval_only:
            write_config = False
            report_dict_extra["promote_blocked"] = True
            report_dict_extra["status"] = "blocked"
            report_dict_extra["reason"] = "retrieval_only_synthetic"
            report.notes.append(
                "Refuse promotable candidate from retrieval-only synthetic "
                "No/p_hat=null batches (use heavy-loo / scored labels)."
            )

    # base weights from runtime config when not supplied
    if base_weights is None:
        try:
            from app.core.runtime_config import fusion_weights

            base_weights = fusion_weights()
        except Exception:
            base_weights = None

    # 1–2 attribution
    report.tool_attribution = tool_attribution(results)

    # 3 weights
    hmap = held_to_hit_lists
    if hmap is None:
        hmap = _hit_lists_from_results(results)
    if hmap:
        report.weight_retune = retune_weights(
            hmap, base_weights=base_weights, top_k=top_k
        )
    else:
        report.weight_retune = {
            "status": "skipped",
            "reason": "no held_to_hit_lists / retrieval hits",
        }
        report.notes.append("Weight retune skipped — provide LOO hit lists.")

    # 3 thresholds + D_val CE (proposal §7.3 dual objective)
    if scored_labels:
        report.threshold_retune = retune_label_thresholds(scored_labels)
        tuned_w_for_ce = None
        if report.weight_retune.get("status") == "ok":
            tuned_w_for_ce = report.weight_retune.get("tuned_weights")
        report.dval_ce_retune = retune_fusion_on_dval_ce(
            scored_labels, base_weights=tuned_w_for_ce or base_weights
        )
    else:
        report.threshold_retune = retune_label_thresholds([])
        report.dval_ce_retune = {
            "status": "skipped",
            "reason": "need scored_labels / --with-labels",
            "objective": "calibrated_cross_entropy_on_dval",
        }
        report.notes.append(
            "Threshold/D_val CE skipped — pass scored_labels / --with-labels for (p_hat,y) pairs."
        )

    # 3b abstain thresholds
    if hmap:
        tuned_w = None
        if report.weight_retune.get("status") == "ok":
            tuned_w = report.weight_retune.get("tuned_weights")
        report.abstain_retune = retune_abstain_thresholds(
            hmap, weights=tuned_w or base_weights, top_k=top_k
        )
        report.tau_drop_retune = retune_tau_drop(
            hmap, weights=tuned_w or base_weights, top_k=top_k
        )
    else:
        report.abstain_retune = {
            "status": "skipped",
            "reason": "no held_to_hit_lists / retrieval hits",
        }
        report.tau_drop_retune = {
            "status": "skipped",
            "reason": "no held_to_hit_lists / retrieval hits",
        }

    # 4 toolkit expansion proposals (human review only — not auto-installed tools)
    report.toolkit_proposals = propose_toolkit_expansions(
        results, attribution=report.tool_attribution
    )
    report.notes.append(
        "Toolkit expansion proposals require human review "
        "(do not claim toolkit self-evolved)."
    )

    # 4b run_eval harness (ceiling + ablation when hit lists exist)
    hmap_for_eval = held_to_hit_lists
    if hmap_for_eval is None:
        hmap_for_eval = _hit_lists_from_results(results)
    try:
        eval_report = run_eval(
            held_to_hit_lists=hmap_for_eval or None,
            scored_labels=scored_labels,
            base_weights=base_weights,
            top_k=top_k,
            write=True,
        )
        report.notes.append(
            f"run_eval status={eval_report.get('status')} "
            f"paths={eval_report.get('paths')}"
        )
    except Exception as e:
        report.notes.append(f"run_eval skipped: {type(e).__name__}: {e}")

    # 5 cache promotion
    trace_rows = list(traces or [])
    # also synthesise from results
    for r in results:
        q = r.get("query") or {}
        if isinstance(q, str):
            q = {"alias": q}
        alias = q.get("alias") or r.get("alias")
        uniprot = q.get("uniprot") or r.get("uniprot")
        trace_rows.append(
            {
                "type": "query_end",
                "query": q,
                "uniprot": uniprot,
                "alias": alias,
                "donors": r.get("donors") or [],
                "verdict": r.get("verdict"),
            }
        )
    cache_data = promote_from_traces(trace_rows, promote_after=2)
    report.cache_promotion = {
        "stats": cache_data.get("stats"),
        "n_entries": len(cache_data.get("entries") or {}),
        "path": str(PROXY_CACHE),
        "role": cache_data.get("role"),
        "promotion": cache_data.get("promotion"),
    }
    if results and results[0].get("axes_used_global") is not None:
        report.notes.append(f"axes_used={results[0].get('axes_used_global')}")

    # write evolved *candidate* config (promote separately after eval gate)
    can_write = (
        report.weight_retune.get("status") == "ok"
        or report.abstain_retune.get("status") == "ok"
        or report.tau_drop_retune.get("status") == "ok"
    )
    if write_config and can_write:
        thr = (report.threshold_retune or {}).get("thresholds") or {
            "strong": 0.75,
            "likely": 0.50,
            "unlikely": 0.25,
        }
        tuned_w = (report.weight_retune or {}).get("tuned_weights") or (base_weights or {})
        abstain = (report.abstain_retune or {}).get("tuned_thresholds")
        tuned_tau = None
        if (report.tau_drop_retune or {}).get("status") == "ok":
            tuned_tau = report.tau_drop_retune.get("tuned_tau_drop")
        soft = list(
            (report.tool_attribution or {}).get("soft_disabled_suggestions")
            or (report.tool_attribution or {}).get("retirement_candidates")
            or []
        )
        path = write_evolved_config(
            tuned_weights=tuned_w,
            thresholds=thr,
            abstain_thresholds=abstain,
            tau_drop=tuned_tau,
            soft_disabled=soft,
            path=CANDIDATE_CONFIG,
            promoted=False,
        )
        report.evolved_config_path = str(path)
        report.notes.append(
            f"Wrote candidate config → {path} (run: rbp-agent promote-evolved after gate)"
        )
        try:
            from app.core.runtime_config import clear_runtime_config_cache

            clear_runtime_config_cache()
        except Exception:
            pass

    # persist report (include promote honesty fields)
    EVOLVED_REPORT.parent.mkdir(parents=True, exist_ok=True)
    payload = {**report.to_dict(), **report_dict_extra}
    if "status" not in payload:
        payload["status"] = "ok"
    EVOLVED_REPORT.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    report.notes.append(f"Report → {EVOLVED_REPORT}")
    _restore_transfer_env()
    return report


def summarize_verdicts(results: list[dict[str, Any]]) -> dict[str, Any]:
    labels: dict[str, int] = {}
    for r in results:
        lab = (r.get("verdict") or {}).get("label") or "Unknown"
        labels[lab] = labels.get(lab, 0) + 1
    return {"n": len(results), "label_counts": labels}

