#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Phase-2 transfer calibration acceptance harness.

The harness has two deliberately separate regimes:

``assisted_loo``
    The target head is excluded from transfer and scored separately as the
    per-RNA reference; measured target->donor LOO priors may assist transfer.

``true_unseen``
    The target head is excluded from transfer and target-specific LOO
    rows/priors are forbidden. It is used only as the acceptance reference.

Live runs use delivery release FASTA labels and delivery tools for prediction,
priors, quality and fusion.  The aggregation/evaluation functions are pure
Python so unit tests can exercise the protocol without importing torch or using
a GPU.  Missing model/data assets are reported as blockers; no scores are
fabricated.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rbp_eval.loo.heavy_loo import (  # noqa: E402
    parse_test_fasta,
    pick_donors,
    subsample,
    test_fasta_for,
)
from rbp_eval.loo.loo_eval import (  # noqa: E402
    _fetch_domain_hits,
    _fetch_seq_hits,
    load_transfer_matrix,
    resolve_loo_csvs,
)
from rbp_eval.scoring.fuse_hits import (  # noqa: E402
    DEFAULT_WEIGHTS,
    aggregate_p_hat,
    fuse_rbp_hits,
    map_donor_quality,
    map_transfer_priors,
)
from rbp_eval.scoring.metrics import metrics_from_pairs  # noqa: E402

ASSISTED_LOO = "assisted_loo"
TRUE_UNSEEN = "true_unseen"
REGIMES = (ASSISTED_LOO, TRUE_UNSEEN)
CONFIDENCE_RANK = {"low": 0, "medium": 1, "high": 2}
POSITIVE_FIDELITY_TOLERANCE = 0.20


class HeldTargetLeakage(ValueError):
    """Raised when a hidden target appears in donor-side evidence."""


class CalibrationDataUnavailable(RuntimeError):
    """Raised when a live run cannot access required real data/model assets."""


def normalize_regime(value: Any) -> str:
    """Normalize CLI/fixture regime spellings."""
    raw = str(value or "").strip().lower().replace("-", "_")
    aliases = {
        "assisted": ASSISTED_LOO,
        "loo": ASSISTED_LOO,
        "assisted_loo": ASSISTED_LOO,
        "unseen": TRUE_UNSEEN,
        "true_unseen": TRUE_UNSEEN,
    }
    if raw not in aliases:
        raise ValueError(f"unknown regime {value!r}; expected assisted-loo or true-unseen")
    return aliases[raw]


def _canonical_alias(value: Any) -> str:
    alias = str(value or "").strip().upper()
    for suffix in ("_K562", "_HEPG2"):
        if alias.endswith(suffix):
            alias = alias[: -len(suffix)]
    return alias


def _donor_alias(row: dict[str, Any]) -> str:
    return _canonical_alias(
        row.get("alias") or row.get("donor") or row.get("rbp_id") or row.get("uniprot")
    )


def validate_strict_target_exclusion(record: dict[str, Any]) -> None:
    """Reject a case if the held target occurs in any donor-side input.

    Live collection filters delivery outputs before constructing records.  This
    validator is the final fail-closed boundary for fixtures and persisted data.
    """
    held = _canonical_alias(record.get("held_target") or record.get("target"))
    if not held:
        raise ValueError("record needs held_target")

    leaks: list[str] = []
    list_fields = ("proxies", "predictions", "donors")
    for field in list_fields:
        for row in record.get(field) or []:
            if isinstance(row, str):
                alias = _canonical_alias(row)
            elif isinstance(row, dict):
                alias = _donor_alias(row)
            else:
                continue
            if alias == held:
                leaks.append(field)

    for field in ("transfer_priors", "donor_quality"):
        raw = record.get(field) or {}
        if isinstance(raw, dict):
            for alias in raw:
                if _canonical_alias(alias) == held:
                    leaks.append(field)

    fusion = record.get("delivery_fusion") or {}
    for row in fusion.get("contributions") or []:
        if isinstance(row, dict) and _donor_alias(row) == held:
            leaks.append("delivery_fusion")

    if leaks:
        raise HeldTargetLeakage(
            f"held target {held} present in donor evidence: {sorted(set(leaks))}"
        )

    if normalize_regime(record.get("regime")) == TRUE_UNSEEN:
        priors = record.get("transfer_priors") or {}
        if priors:
            raise HeldTargetLeakage(
                "true_unseen forbids target-specific transfer priors; use quality only"
            )


def _numeric_map(raw: Any) -> dict[str, float]:
    out: dict[str, float] = {}
    if not isinstance(raw, dict):
        return out
    for key, value in raw.items():
        try:
            if value is not None:
                out[str(key)] = float(value)
        except (TypeError, ValueError):
            continue
    return out


def assess_evidence_confidence(
    *,
    regime: str,
    proxies: list[dict[str, Any]],
    predictions: list[dict[str, Any]],
    transfer_priors: Optional[dict[str, float]] = None,
    donor_quality: Optional[dict[str, float]] = None,
    p_hat: Optional[float],
) -> dict[str, Any]:
    """Assess confidence from observable donor evidence, independently of labels."""
    regime = normalize_regime(regime)
    transfer_priors = transfer_priors or {}
    donor_quality = donor_quality or {}
    proxy_aliases = [_donor_alias(p) for p in proxies if _donor_alias(p)]
    predicted = {_donor_alias(p) for p in predictions if _donor_alias(p) and p.get("prob") is not None}
    n_proxy = len(set(proxy_aliases))
    n_predicted = len(set(proxy_aliases).intersection(predicted))
    pred_coverage = (n_predicted / n_proxy) if n_proxy else 0.0

    def _has(mapping: dict[str, float], alias: str) -> bool:
        return any(_canonical_alias(k) == alias for k in mapping)

    prior_coverage = (
        sum(1 for alias in set(proxy_aliases) if _has(transfer_priors, alias)) / n_proxy
        if n_proxy
        else 0.0
    )
    quality_coverage = (
        sum(1 for alias in set(proxy_aliases) if _has(donor_quality, alias)) / n_proxy
        if n_proxy
        else 0.0
    )
    similarities: list[float] = []
    modalities: set[str] = set()
    for proxy in proxies:
        try:
            similarities.append(float(proxy.get("similarity_score") or proxy.get("score") or 0.0))
        except (TypeError, ValueError):
            continue
        breakdown = proxy.get("similarity_breakdown")
        if isinstance(breakdown, dict):
            modalities.update(
                str(key)
                for key, value in breakdown.items()
                if value is not None and str(key) != "assisted_loo_rank"
            )
    best_similarity = max(similarities) if similarities else 0.0
    probs = [
        float(row["prob"])
        for row in predictions
        if row.get("prob") is not None
    ]
    prediction_spread = max(probs) - min(probs) if probs else 1.0

    prior_ready = regime == TRUE_UNSEEN or prior_coverage >= 0.80
    prior_partial = regime == TRUE_UNSEEN or prior_coverage >= 0.50
    if (
        p_hat is not None
        and n_predicted >= 2
        and best_similarity >= 0.75
        and pred_coverage >= 0.80
        and quality_coverage >= 0.80
        and prior_ready
        and prediction_spread <= 0.35
        and (regime == ASSISTED_LOO or len(modalities) >= 2)
    ):
        # Until a larger held-out coverage-risk fit exists, transfer confidence
        # is conservatively capped at medium. Own-head remains high elsewhere.
        level = "medium"
    elif (
        p_hat is not None
        and n_predicted >= 1
        and best_similarity >= 0.50
        and pred_coverage >= 0.50
        and quality_coverage >= 0.50
        and prior_partial
        and prediction_spread <= 0.65
    ):
        level = "medium"
    else:
        level = "low"

    return {
        "level": level,
        "n_proxies": n_proxy,
        "n_predicted": n_predicted,
        "prediction_coverage": round(pred_coverage, 6),
        "transfer_prior_coverage": round(prior_coverage, 6),
        "donor_quality_coverage": round(quality_coverage, 6),
        "best_similarity": round(best_similarity, 6),
        "prediction_spread": round(prediction_spread, 6),
        "n_modalities": len(modalities),
        "target_specific_prior_used": bool(transfer_priors),
        "policy_status": "conservative_unvalidated_transfer_v1",
        "basis": (
            "similarity+prediction+quality+target_loo_prior"
            if regime == ASSISTED_LOO
            else "similarity+prediction+quality_no_target_prior"
        ),
    }


def aggregate_calibration_record(record: dict[str, Any]) -> dict[str, Any]:
    """Pure aggregation for one labeled case, with fail-closed leakage checks."""
    validate_strict_target_exclusion(record)
    regime = normalize_regime(record.get("regime"))
    proxies = [dict(p) for p in (record.get("proxies") or []) if isinstance(p, dict)]
    predictions = [
        dict(p) for p in (record.get("predictions") or []) if isinstance(p, dict)
    ]
    transfer_priors = _numeric_map(record.get("transfer_priors"))
    donor_quality = _numeric_map(record.get("donor_quality"))
    pure = aggregate_p_hat(
        proxies,
        predictions,
        transfer_priors=transfer_priors,
        donor_quality=donor_quality,
    )

    delivery = record.get("delivery_fusion") or {}
    delivery_score = delivery.get("score")
    if delivery_score is not None:
        p_hat = float(delivery_score)
        source = "delivery_similarity_weighted_vote"
        parity = (
            None
            if pure.get("p_hat") is None
            else abs(float(pure["p_hat"]) - p_hat)
        )
    else:
        p_hat = pure.get("p_hat")
        source = "pure_delivery_formula"
        parity = None

    evidence = assess_evidence_confidence(
        regime=regime,
        proxies=proxies,
        predictions=predictions,
        transfer_priors=transfer_priors,
        donor_quality=donor_quality,
        p_hat=p_hat,
    )
    try:
        y = int(record["y"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("record needs binary y") from exc
    if y not in (0, 1):
        raise ValueError(f"record y must be 0 or 1, got {y!r}")
    own_head_prob = record.get("own_head_prob")
    try:
        own_head_prob = None if own_head_prob is None else float(own_head_prob)
    except (TypeError, ValueError):
        own_head_prob = None

    result = {
        "case_id": str(record.get("case_id") or record.get("rna_id") or ""),
        "held_target": str(record.get("held_target") or record.get("target")),
        "regime": regime,
        "y": y,
        "p_hat": p_hat,
        "own_head_prob": own_head_prob,
        "evidence_confidence": evidence["level"],
        "evidence": evidence,
        "aggregation_source": source,
        "aggregation": pure,
        "metric_ablation_p_hat": dict(record.get("metric_ablation_p_hat") or {}),
        "delivery_parity_abs": None if parity is None else round(parity, 6),
        "held_target_exclusions": int(record.get("held_target_exclusions") or 0),
    }
    prediction_error = record.get("prediction_error")
    if prediction_error:
        result["status"] = "failed"
        result["failure_reason"] = f"prediction_error: {prediction_error}"
    elif p_hat is None:
        result["status"] = "failed"
        result["failure_reason"] = "no_positive_aggregation_weight"
    else:
        result["status"] = "scored"
        result["label_absolute_error"] = round(abs(float(p_hat) - y), 6)
        result["absolute_error_to_own_head"] = (
            None
            if own_head_prob is None
            else round(abs(float(p_hat) - own_head_prob), 6)
        )
        result["reference_status"] = (
            "available" if own_head_prob is not None else "missing"
        )
        result["predicted_label"] = int(float(p_hat) >= 0.5)
    return result


def coverage_risk_curve(rows: list[dict[str, Any]], *, n_total: Optional[int] = None) -> list[dict[str, Any]]:
    """Selective classification risk at high, medium+, and all-score coverage."""
    total = int(n_total if n_total is not None else len(rows))
    scored = [row for row in rows if row.get("status") == "scored"]
    curve: list[dict[str, Any]] = []
    for minimum in ("high", "medium", "low"):
        floor = CONFIDENCE_RANK[minimum]
        covered = [
            row
            for row in scored
            if CONFIDENCE_RANK.get(str(row.get("evidence_confidence")), -1) >= floor
        ]
        errors = sum(int(row["predicted_label"]) != int(row["y"]) for row in covered)
        mae = (
            sum(abs(float(row["p_hat"]) - int(row["y"])) for row in covered) / len(covered)
            if covered
            else None
        )
        curve.append(
            {
                "minimum_evidence_confidence": minimum,
                "n_covered": len(covered),
                "coverage": round(len(covered) / total, 6) if total else 0.0,
                "classification_risk": round(errors / len(covered), 6) if covered else None,
                "mean_absolute_error": None if mae is None else round(mae, 6),
            }
        )
    return curve


def validate_coverage_risk_calibration(
    curve: list[dict[str, Any]],
    *,
    min_selective_cases: int = 50,
    tolerance: float = 0.0,
) -> dict[str, Any]:
    """Validate that stricter evidence selection does not increase observed risk.

    This is a descriptive held-out check, not a statistical proof.  Empty
    high-confidence coverage is expected while transfer confidence is capped at
    medium and is reported as unavailable rather than silently treated as zero
    risk.
    """
    by_level = {
        str(row.get("minimum_evidence_confidence")): row
        for row in curve
        if isinstance(row, dict)
    }
    ordered = [by_level[level] for level in ("high", "medium", "low") if level in by_level]
    coverage_monotonic = all(
        float(left.get("coverage") or 0.0) <= float(right.get("coverage") or 0.0)
        for left, right in zip(ordered, ordered[1:])
    )
    comparable = [
        row
        for row in ordered
        if row.get("classification_risk") is not None and int(row.get("n_covered") or 0) > 0
    ]
    comparisons: list[dict[str, Any]] = []
    risk_monotonic = True
    mae_monotonic = True
    for stricter, looser in zip(comparable, comparable[1:]):
        risk_ok = float(stricter["classification_risk"]) <= (
            float(looser["classification_risk"]) + float(tolerance)
        )
        strict_mae = stricter.get("mean_absolute_error")
        loose_mae = looser.get("mean_absolute_error")
        mae_ok = (
            True
            if strict_mae is None or loose_mae is None
            else float(strict_mae) <= float(loose_mae) + float(tolerance)
        )
        risk_monotonic = risk_monotonic and risk_ok
        mae_monotonic = mae_monotonic and mae_ok
        comparisons.append(
            {
                "stricter": stricter["minimum_evidence_confidence"],
                "looser": looser["minimum_evidence_confidence"],
                "classification_risk_nonincreasing": risk_ok,
                "mean_absolute_error_nonincreasing": mae_ok,
            }
        )
    selective_rows = [
        row for row in comparable
        if row.get("minimum_evidence_confidence") in ("high", "medium")
    ]
    n_selective = max((int(row.get("n_covered") or 0) for row in selective_rows), default=0)
    sample_sufficient = n_selective >= int(min_selective_cases)
    validated = bool(
        coverage_monotonic
        and risk_monotonic
        and mae_monotonic
        and comparisons
        and sample_sufficient
    )
    limitations: list[str] = []
    if not sample_sufficient:
        limitations.append(
            f"selective cohort n={n_selective} < required {int(min_selective_cases)}"
        )
    if not risk_monotonic:
        limitations.append("observed classification risk increased at a stricter threshold")
    if not mae_monotonic:
        limitations.append("observed mean absolute error increased at a stricter threshold")
    if not comparisons:
        limitations.append("fewer than two non-empty confidence tiers")
    return {
        "status": "validated" if validated else "not_validated",
        "validated": validated,
        "coverage_monotonic": coverage_monotonic,
        "classification_risk_monotonic": risk_monotonic,
        "mean_absolute_error_monotonic": mae_monotonic,
        "sample_sufficient": sample_sufficient,
        "n_selective": n_selective,
        "min_selective_cases": int(min_selective_cases),
        "comparisons": comparisons,
        "limitations": limitations,
        "high_confidence_policy": "disabled_for_transfer",
    }


def _fidelity_block(rows: list[dict[str, Any]], y: int) -> dict[str, Any]:
    selected = [row for row in rows if row.get("y") == y]
    passing = [
        row
        for row in selected
        if row.get("status") == "scored"
        and row.get("own_head_prob") is not None
        and abs(float(row["p_hat"]) - float(row["own_head_prob"]))
        <= POSITIVE_FIDELITY_TOLERANCE + 1e-12
        and CONFIDENCE_RANK.get(str(row.get("evidence_confidence")), -1)
        >= CONFIDENCE_RANK["medium"]
    ]
    return {
        "n_total": len(selected),
        "n_pass": len(passing),
        "pass_rate": round(len(passing) / len(selected), 6) if selected else None,
        "passed_all": bool(selected) and len(passing) == len(selected),
        "n_reference_missing": sum(
            row.get("own_head_prob") is None for row in selected
        ),
        "criterion": (
            f"abs(p_hat_transfer-p_hat_own_head) <= {POSITIVE_FIDELITY_TOLERANCE:.2f} "
            "and evidence_confidence in {medium,high}"
        ),
    }


def summarize_metric_ablations(
    scored: list[dict[str, Any]],
    full_metrics: dict[str, Any],
) -> dict[str, Any]:
    """Summarize stored one-metric removals without rerunning RhoBind."""
    axes = sorted(
        {
            str(axis)
            for row in scored
            for axis in (row.get("metric_ablation_p_hat") or {})
        }
    )
    ablations: dict[str, Any] = {}
    for axis in axes:
        axis_rows: list[dict[str, Any]] = []
        for row in scored:
            axis_score = (row.get("metric_ablation_p_hat") or {}).get(axis)
            if axis_score is None:
                continue
            axis_row = dict(row)
            axis_row["p_hat"] = float(axis_score)
            axis_row["predicted_label"] = int(float(axis_score) >= 0.5)
            axis_row["absolute_error_to_own_head"] = (
                None
                if row.get("own_head_prob") is None
                else round(abs(float(axis_score) - float(row["own_head_prob"])), 6)
            )
            axis_rows.append(axis_row)
        axis_pairs = [
            {"p_hat": row["p_hat"], "y": row["y"]}
            for row in axis_rows
        ]
        axis_metrics = metrics_from_pairs(axis_pairs)
        full_auprc = full_metrics.get("auprc")
        axis_auprc = axis_metrics.get("auprc")
        full_ece = full_metrics.get("ece")
        axis_ece = axis_metrics.get("ece")
        ablations[axis] = {
            "operation": f"remove_{axis}_on_fixed_donor_cohort",
            "n": len(axis_rows),
            "coverage": round(len(axis_rows) / len(scored), 6) if scored else 0.0,
            "metrics": axis_metrics,
            "positive_fidelity": _fidelity_block(axis_rows, 1),
            "negative_fidelity": _fidelity_block(axis_rows, 0),
            "coverage_risk": coverage_risk_curve(axis_rows, n_total=len(scored)),
            "delta_auprc_removed_minus_full": (
                None
                if full_auprc is None or axis_auprc is None
                else round(float(axis_auprc) - float(full_auprc), 6)
            ),
            "delta_ece_removed_minus_full": (
                None
                if full_ece is None or axis_ece is None
                else round(float(axis_ece) - float(full_ece), 6)
            ),
        }
    return ablations


def evaluate_regime_records(
    records: Iterable[dict[str, Any]],
    *,
    regime: str,
    setup_failures: Optional[list[dict[str, Any]]] = None,
) -> dict[str, Any]:
    """Evaluate one regime and expose metrics, fidelity, failures and coverage-risk."""
    regime = normalize_regime(regime)
    rows: list[dict[str, Any]] = []
    failures = list(setup_failures or [])
    for index, record in enumerate(records):
        case = dict(record)
        case["regime"] = regime
        try:
            row = aggregate_calibration_record(case)
        except HeldTargetLeakage as exc:
            row = {
                "case_id": str(case.get("case_id") or case.get("rna_id") or index),
                "held_target": str(case.get("held_target") or case.get("target") or ""),
                "regime": regime,
                "y": case.get("y"),
                "p_hat": None,
                "status": "failed",
                "failure_reason": f"held_target_leakage: {exc}",
                "evidence_confidence": "low",
            }
        except (TypeError, ValueError) as exc:
            row = {
                "case_id": str(case.get("case_id") or case.get("rna_id") or index),
                "held_target": str(case.get("held_target") or case.get("target") or ""),
                "regime": regime,
                "y": case.get("y"),
                "p_hat": None,
                "status": "failed",
                "failure_reason": f"invalid_record: {exc}",
                "evidence_confidence": "low",
            }
        rows.append(row)
        if row.get("status") != "scored":
            failures.append(
                {
                    "case_id": row.get("case_id"),
                    "held_target": row.get("held_target"),
                    "reason": row.get("failure_reason") or "unscored",
                }
            )

    scored = [row for row in rows if row.get("status") == "scored"]
    medium_high = [
        row
        for row in scored
        if CONFIDENCE_RANK.get(str(row.get("evidence_confidence")), -1) >= 1
    ]
    pairs = [{"p_hat": row["p_hat"], "y": row["y"]} for row in scored]
    accepted_pairs = [{"p_hat": row["p_hat"], "y": row["y"]} for row in medium_high]
    metrics = metrics_from_pairs(pairs)
    accepted_metrics = metrics_from_pairs(accepted_pairs)
    ablations = summarize_metric_ablations(scored, metrics)
    reasons = Counter(str(f.get("reason") or "unknown") for f in failures)
    positive = _fidelity_block(rows, 1)
    negative = _fidelity_block(rows, 0)
    n_setup_failures = len(setup_failures or [])
    n_attempted_units = len(rows) + n_setup_failures
    status = (
        "ok"
        if metrics.get("status") == "ok"
        and positive["n_total"] > 0
        and negative["n_total"] > 0
        else "blocked"
    )
    coverage_risk = coverage_risk_curve(rows)
    return {
        "regime": regime,
        "status": status,
        "n_total": len(rows),
        "n_scored": len(scored),
        "n_positive": sum(row.get("y") == 1 for row in rows),
        "n_negative": sum(row.get("y") == 0 for row in rows),
        "metrics": {
            "all_scored": metrics,
            "evidence_medium_high": accepted_metrics,
        },
        "positive_fidelity": positive,
        "negative_fidelity": negative,
        "coverage": {
            "score_coverage": round(len(scored) / len(rows), 6) if rows else 0.0,
            "medium_high_coverage": (
                round(len(medium_high) / len(rows), 6) if rows else 0.0
            ),
            "failure_rate": (
                round(len(failures) / n_attempted_units, 6)
                if n_attempted_units
                else None
            ),
        },
        "coverage_risk": coverage_risk,
        "selective_risk_validation": validate_coverage_risk_calibration(coverage_risk),
        "metric_ablations": ablations,
        "failures": {
            "n": len(failures),
            "by_reason": dict(sorted(reasons.items())),
            "rows": failures,
        },
        "rows": rows,
    }


def build_calibration_report(
    records: Iterable[dict[str, Any]],
    *,
    requested_regimes: Iterable[str] = REGIMES,
    setup_failures: Optional[dict[str, list[dict[str, Any]]]] = None,
    sources: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Group records into scientifically distinct regime reports."""
    requested = tuple(dict.fromkeys(normalize_regime(r) for r in requested_regimes))
    grouped: dict[str, list[dict[str, Any]]] = {regime: [] for regime in requested}
    for raw in records:
        record = dict(raw)
        regime = normalize_regime(record.get("regime"))
        if regime in grouped:
            grouped[regime].append(record)

    regimes = {
        regime: evaluate_regime_records(
            grouped[regime],
            regime=regime,
            setup_failures=(setup_failures or {}).get(regime),
        )
        for regime in requested
    }
    ok = bool(regimes) and all(block.get("status") == "ok" for block in regimes.values())
    return {
        "schema": "transfer_calibration.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "ok" if ok else "blocked",
        "ok": ok,
        "protocol": {
            "held_target_exclusion": "fail_closed_across_proxies_predictions_priors_quality",
            "assisted_loo": (
                "exclude target head from transfer; score it only as the per-RNA "
                "reference; measured LOO prior may assist donor weighting"
            ),
            "true_unseen": (
                "exclude target head from transfer and target-specific priors; "
                "target head is evaluated separately only as per-RNA reference"
            ),
            "positive_fidelity": (
                "abs(p_hat_transfer-p_hat_own_head) <= 0.20 and evidence confidence "
                "is medium/high on positive release RNAs"
            ),
            "negative_fidelity": (
                "diagnostic: same transfer-vs-own-head criterion on negative RNAs"
            ),
            "limitations": [
                (
                    "true_unseen exercises the no-target-head/no-target-prior path "
                    "on labeled release RBPs; the release has no labeled novel-RBP "
                    "set, so it cannot prove protein-level generalization beyond "
                    "the shared encoder's training panel"
                ),
                (
                    "assisted_loo is intentionally optimistic because measured "
                    "target-to-donor transfer priors may guide selection and weighting"
                ),
            ],
        },
        "requested_regimes": list(requested),
        "regimes": regimes,
        "sources": sources or {},
    }


def _load_head_aliases(release: Path, cohort: str) -> set[str]:
    from rbp_eval.scoring.head_index import cohort_head_aliases

    return cohort_head_aliases(cohort, release=release)


def _release_reference(release: Path, cohort: str, targets: Iterable[str]) -> list[dict[str, Any]]:
    path = release / "expected_metrics.csv"
    wanted = {_canonical_alias(target) for target in targets}
    rows: list[dict[str, Any]] = []
    if not path.is_file():
        return rows
    with path.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if str(row.get("cohort") or "").upper() != cohort.upper():
                continue
            if _canonical_alias(row.get("rbp")) not in wanted:
                continue
            rows.append(
                {
                    "cohort": row["cohort"],
                    "rbp": row["rbp"],
                    "n_test": int(row["n_test"]),
                    "own_head_auprc": float(row["auprc"]),
                    "own_head_auroc": float(row["auroc"]),
                }
            )
    return rows


def _live_preflight(release: Path, cohort: str) -> None:
    cohort_key = "k562" if cohort.upper() == "K562" else "hepg2"
    required = [
        release / "checkpoints" / f"head_index_{cohort_key}.json",
        release / "checkpoints" / f"rhobind_{cohort_key}_mt_all118_cutoff08.ckpt",
        release / "test_data" / cohort_key,
    ]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise CalibrationDataUnavailable(
            "live calibration requires real release assets; missing: " + ", ".join(missing)
        )


def _fetch_static_live_hits(
    *,
    client: Any,
    held: str,
    top_k: int,
    with_seq: bool,
) -> tuple[list[list[dict[str, Any]]], list[str]]:
    """Fetch protein/domain/structure views once per held target."""
    hit_lists: list[list[dict[str, Any]]] = []
    errors: list[str] = []
    domain_hits, domain_error = _fetch_domain_hits(client, held, top_k * 4)
    if domain_hits:
        hit_lists.append(domain_hits)
    if domain_error:
        errors.append(domain_error)
    if with_seq:
        seq_hits, seq_error = _fetch_seq_hits(client, held, top_k * 4)
        if seq_hits:
            hit_lists.append(seq_hits)
        if seq_error:
            errors.append(seq_error)
    structure = client.call("structure_fetch", {"alias": held, "allow_download": False})
    pdb_path = structure.get("pdb_path")
    if pdb_path:
        structural = client.call(
            "struct_similarity_foldseek",
            {"pdb_path": pdb_path, "top_k": top_k * 4},
        )
        if structural.get("hits"):
            hit_lists.append(list(structural["hits"]))
        elif structural.get("error"):
            errors.append(f"struct_similarity_foldseek: {structural['error']}")
    elif structure.get("error"):
        errors.append(f"structure_fetch: {structure['error']}")
    return hit_lists, errors


def _select_live_proxies(
    *,
    regime: str,
    held: str,
    top_k: int,
    allowed_heads: set[str],
    matrix: dict[tuple[str, str], float],
    client: Any,
    with_seq: bool,
    with_rna: bool = True,
    rna: Optional[str] = None,
    static_hit_lists: Optional[list[list[dict[str, Any]]]] = None,
    static_errors: Optional[list[str]] = None,
) -> tuple[list[dict[str, Any]], Optional[str]]:
    held_c = _canonical_alias(held)
    if regime == ASSISTED_LOO:
        donors = [
            donor
            for donor in pick_donors(held, matrix, top_k * 2)
            if _canonical_alias(donor) != held_c
            and _canonical_alias(donor) in allowed_heads
        ][:top_k]
        proxies = [
            {
                "rbp_id": donor,
                "alias": donor,
                # Assisted-LOO selection is already ranked by measured transfer;
                # use a neutral similarity factor so the prior is applied once.
                "similarity_score": 1.0,
                "similarity_breakdown": {"assisted_loo_rank": 1.0},
            }
            for donor in donors
        ]
        return proxies, None if proxies else "no eligible foreign donors in LOO matrix"

    if static_hit_lists is None:
        hit_lists, errors = _fetch_static_live_hits(
            client=client,
            held=held,
            top_k=top_k,
            with_seq=with_seq,
        )
    else:
        hit_lists = [list(hits) for hits in static_hit_lists]
        errors = list(static_errors or [])
    if rna and with_rna:
        rna_hits = client.call("rna_blastn", {"rna": rna, "top_k": top_k * 4})
        if rna_hits.get("hits"):
            hit_lists.append(list(rna_hits["hits"]))
        elif rna_hits.get("error"):
            errors.append(f"rna_blastn: {rna_hits['error']}")
    if not hit_lists:
        return [], "; ".join(errors) or "no delivery retrieval hits"
    from app.core.runtime_config import fusion_weights, tau_drop

    active_weights = fusion_weights()
    fused = fuse_rbp_hits(
        hit_lists,
        weights=active_weights,
        top_k=top_k,
        exclude_aliases={held},
        allowed_aliases=allowed_heads,
        use_rank_normalize=True,
        tau_drop=tau_drop(),
    )
    proxies = [
        {
            "rbp_id": row["alias"],
            "alias": row["alias"],
            "similarity_score": row.get("vote_similarity", row["score"]),
            "fused_score": row["score"],
            "similarity_breakdown": row.get("similarity_breakdown") or {},
            "similarity_metrics_normalized": row.get("sim_normalized") or {},
            "similarity_metric_weights": active_weights,
        }
        for row in fused
        if _canonical_alias(row.get("alias")) != held_c
    ]
    return proxies, None if proxies else "retrieval found no eligible foreign donor heads"


def _filter_predictions(
    predictions: Iterable[dict[str, Any]],
    *,
    held: str,
    allowed_donors: set[str],
) -> tuple[list[dict[str, Any]], int]:
    clean: list[dict[str, Any]] = []
    excluded = 0
    held_c = _canonical_alias(held)
    for raw in predictions:
        if not isinstance(raw, dict):
            continue
        alias = _donor_alias(raw)
        if alias == held_c:
            excluded += 1
            continue
        if alias not in allowed_donors:
            excluded += 1
            continue
        clean.append(dict(raw))
    return clean, excluded


def _metric_ablation_votes(
    client: Any,
    *,
    proxies: list[dict[str, Any]],
    predictions: list[dict[str, Any]],
    transfer_priors: dict[str, float],
    donor_quality: dict[str, float],
) -> dict[str, Optional[float]]:
    """Remove one retrieval metric at a time on the fixed donor cohort."""
    axes = sorted(
        {
            str(metric)
            for proxy in proxies
            for metric in (proxy.get("similarity_metrics_normalized") or {})
        }
    )
    out: dict[str, Optional[float]] = {}
    for removed in axes:
        hits: list[dict[str, Any]] = []
        for proxy in proxies:
            metrics = dict(proxy.get("similarity_metrics_normalized") or {})
            numerator = denominator = 0.0
            for metric, raw_score in metrics.items():
                if str(metric) == removed:
                    continue
                configured = proxy.get("similarity_metric_weights") or {}
                weight = float(
                    configured.get(
                        str(metric),
                        DEFAULT_WEIGHTS.get(str(metric), 0.2),
                    )
                )
                if weight <= 0:
                    continue
                numerator += weight * float(raw_score)
                denominator += weight
            if denominator > 0:
                hits.append(
                    {
                        "alias": proxy["rbp_id"],
                        "score": numerator / denominator,
                    }
                )
        if not hits:
            out[removed] = None
            continue
        vote = client.call(
            "similarity_weighted_vote",
            {
                "predictions": predictions,
                "hits": hits,
                "transfer_priors": transfer_priors,
                "donor_quality": donor_quality,
            },
        )
        score = vote.get("score") if not vote.get("error") else None
        out[removed] = None if score is None else float(score)
    return out


def collect_live_records(
    *,
    regimes: Iterable[str],
    targets: Iterable[str],
    cohort: str,
    top_k: int,
    max_seqs: int,
    device: str,
    with_seq: bool = False,
    with_rna: bool = True,
) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]], dict[str, Any]]:
    """Collect real delivery-backed records; never substitute synthetic scores."""
    from app.backends.delivery.client import DeliveryToolClient
    from app.backends.delivery.env import apply_delivery_env, resolve_delivery_paths
    from app.core.runtime_config import load_runtime_config

    apply_delivery_env()
    paths = resolve_delivery_paths()
    delivery_root = Path(paths["delivery_root"])
    release = Path(paths["rhobind_release"])
    _live_preflight(release, cohort)
    _, metrics_path = resolve_loo_csvs()
    normalized_regimes = tuple(normalize_regime(r) for r in regimes)
    if ASSISTED_LOO in normalized_regimes and not metrics_path.is_file():
        raise CalibrationDataUnavailable(f"assisted-LOO matrix missing: {metrics_path}")
    matrix = load_transfer_matrix(metrics_path) if metrics_path.is_file() else {}
    allowed_heads = _load_head_aliases(release, cohort)
    integrate = load_runtime_config().get("integrate") or {}
    max_vote_donors = int(integrate.get("max_vote_donors", 2))
    client = DeliveryToolClient(offline=False, device=device, use_conda=True)

    records: list[dict[str, Any]] = []
    failures: dict[str, list[dict[str, Any]]] = {regime: [] for regime in normalized_regimes}
    target_list = [str(target).strip() for target in targets if str(target).strip()]
    for regime in normalized_regimes:
        for held in target_list:
            held_c = _canonical_alias(held)
            fasta = test_fasta_for(held, cohort, delivery_root)
            if fasta is None:
                failures[regime].append(
                    {"held_target": held, "reason": f"release test FASTA unavailable ({cohort})"}
                )
                continue
            proxies: list[dict[str, Any]] = []
            selection_error: Optional[str] = None
            if regime == ASSISTED_LOO:
                proxies, selection_error = _select_live_proxies(
                    regime=regime,
                    held=held,
                    top_k=top_k,
                    allowed_heads=allowed_heads,
                    matrix=matrix,
                    client=client,
                    with_seq=with_seq,
                )
            if selection_error:
                failures[regime].append(
                    {"held_target": held, "reason": f"donor_selection: {selection_error}"}
                )
                continue
            donors = [str(proxy["rbp_id"]) for proxy in proxies]
            if held_c in {_canonical_alias(donor) for donor in donors}:
                failures[regime].append(
                    {"held_target": held, "reason": "held_target_leakage in selected donors"}
                )
                continue

            transfer_priors: dict[str, float] = {}
            if regime == ASSISTED_LOO:
                raw_prior = client.call(
                    "transfer_prior_lookup", {"target": held, "donors": donors}
                )
                if raw_prior.get("error"):
                    failures[regime].append(
                        {
                            "held_target": held,
                            "reason": f"transfer_prior_lookup: {raw_prior['error']}",
                        }
                    )
                    continue
                transfer_priors = map_transfer_priors(raw_prior)
                if not transfer_priors:
                    failures[regime].append(
                        {"held_target": held, "reason": "no measured assisted-LOO priors"}
                    )
                    continue

            static_hit_lists: Optional[list[list[dict[str, Any]]]] = None
            static_errors: list[str] = []
            if regime == TRUE_UNSEEN:
                static_hit_lists, static_errors = _fetch_static_live_hits(
                    client=client,
                    held=held,
                    top_k=top_k,
                    with_seq=with_seq,
                )
            entries = subsample(parse_test_fasta(fasta), max_seqs)
            for index, (rna, label) in enumerate(entries):
                case_proxies = proxies
                case_transfer_priors = transfer_priors
                if regime == TRUE_UNSEEN:
                    case_proxies, case_error = _select_live_proxies(
                        regime=regime,
                        held=held,
                        top_k=top_k,
                        allowed_heads=allowed_heads,
                        matrix=matrix,
                        client=client,
                        with_seq=with_seq,
                        with_rna=with_rna,
                        rna=rna,
                        static_hit_lists=static_hit_lists,
                        static_errors=static_errors,
                    )
                    if case_error:
                        failures[regime].append(
                            {
                                "case_id": f"{regime}:{held}:{index}",
                                "held_target": held,
                                "reason": f"donor_selection: {case_error}",
                            }
                        )
                        continue
                if max_vote_donors > 0 and len(case_proxies) > max_vote_donors:
                    case_proxies = sorted(
                        case_proxies,
                        key=lambda proxy: float(
                            proxy.get("similarity_score")
                            or proxy.get("score")
                            or 0.0
                        ),
                        reverse=True,
                    )[:max_vote_donors]
                case_donors = [str(proxy["rbp_id"]) for proxy in case_proxies]
                if held_c in {_canonical_alias(donor) for donor in case_donors}:
                    failures[regime].append(
                        {
                            "case_id": f"{regime}:{held}:{index}",
                            "held_target": held,
                            "reason": "held_target_leakage in selected donors",
                        }
                    )
                    continue
                raw_quality = client.call(
                    "donor_quality_prior",
                    {"donors": case_donors, "cohort": cohort},
                )
                case_donor_quality = (
                    {} if raw_quality.get("error") else map_donor_quality(raw_quality)
                )
                allowed_donors = {
                    _canonical_alias(donor) for donor in case_donors
                }
                pred = client.call(
                    "rhobind_predict",
                    {
                        "rna": rna,
                        # Evaluation-only joint call: split the held row out as the
                        # own-head reference before donor aggregation. The held row
                        # never enters proxies, priors, vote inputs or transfer p_hat.
                        "rbps": [held, *case_donors],
                        "cohort": cohort,
                        "device": device,
                        "aggregate": "max",
                        "timeout_s": 180,
                    },
                )
                all_predictions = [
                    dict(row)
                    for row in (pred.get("predictions") or [])
                    if isinstance(row, dict)
                ]
                own_head_rows = [
                    row
                    for row in all_predictions
                    if _donor_alias(row) == held_c and row.get("prob") is not None
                ]
                own_head_prob = (
                    float(own_head_rows[0]["prob"]) if own_head_rows else None
                )
                predictions, excluded = _filter_predictions(
                    all_predictions,
                    held=held,
                    allowed_donors=allowed_donors,
                )
                prediction_error = pred.get("error")
                delivery_fusion: dict[str, Any] = {}
                metric_ablations: dict[str, Optional[float]] = {}
                if predictions and not prediction_error:
                    delivery_fusion = client.call(
                        "similarity_weighted_vote",
                        {
                            "predictions": predictions,
                            "hits": [
                                {
                                    "alias": proxy["rbp_id"],
                                    "score": proxy["similarity_score"],
                                }
                                for proxy in case_proxies
                            ],
                            "transfer_priors": case_transfer_priors,
                            "donor_quality": case_donor_quality,
                        },
                    )
                    if delivery_fusion.get("error"):
                        prediction_error = (
                            f"similarity_weighted_vote: {delivery_fusion['error']}"
                        )
                    elif regime == TRUE_UNSEEN:
                        metric_ablations = _metric_ablation_votes(
                            client,
                            proxies=case_proxies,
                            predictions=predictions,
                            transfer_priors=case_transfer_priors,
                            donor_quality=case_donor_quality,
                        )
                records.append(
                    {
                        "case_id": f"{regime}:{held}:{index}",
                        "regime": regime,
                        "held_target": held,
                        "y": int(label),
                        "proxies": case_proxies,
                        "predictions": predictions,
                        "own_head_prob": own_head_prob,
                        "own_head_prediction": (
                            own_head_rows[0] if own_head_rows else None
                        ),
                        "transfer_priors": case_transfer_priors,
                        "donor_quality": case_donor_quality,
                        "delivery_fusion": delivery_fusion,
                        "metric_ablation_p_hat": metric_ablations,
                        "prediction_error": prediction_error,
                        "reference_error": (
                            None
                            if own_head_prob is not None
                            else "held own-head prediction unavailable"
                        ),
                        "held_target_exclusions": excluded,
                    }
                )

    sources = {
        "delivery_root": str(delivery_root),
        "release": str(release),
        "loo_transfer_metrics": (
            str(metrics_path) if ASSISTED_LOO in normalized_regimes else None
        ),
        "test_fastas": "release/rhobind_release_v1/test_data",
        "release_own_head_reference": _release_reference(release, cohort, target_list),
        "cohort": cohort,
        "device": device,
        "max_seqs_per_target": max_seqs,
        "top_k": top_k,
        "with_seq": with_seq,
        "with_rna": with_rna,
    }
    return records, failures, sources


def run_live_calibration(
    *,
    regimes: Iterable[str],
    targets: Optional[Iterable[str]] = None,
    cohort: str = "K562",
    top_k: int = 5,
    max_seqs: int = 64,
    device: str = "cuda",
    with_seq: bool = False,
    with_rna: bool = True,
) -> dict[str, Any]:
    """Run the live delivery protocol and return a complete report."""
    from app.backends.delivery.env import apply_delivery_env, resolve_delivery_paths

    apply_delivery_env()
    paths = resolve_delivery_paths()
    release = Path(paths["rhobind_release"])
    cohort_dir = release / "test_data" / cohort.lower()
    if targets is None:
        if not cohort_dir.is_dir():
            raise CalibrationDataUnavailable(f"release test-data directory missing: {cohort_dir}")
        target_list = sorted(path.name for path in cohort_dir.iterdir() if path.is_dir())
    else:
        target_list = [str(target) for target in targets]
    if not target_list:
        raise CalibrationDataUnavailable("no release targets selected")
    records, failures, sources = collect_live_records(
        regimes=regimes,
        targets=target_list,
        cohort=cohort,
        top_k=top_k,
        max_seqs=max_seqs,
        device=device,
        with_seq=with_seq,
        with_rna=with_rna,
    )
    return build_calibration_report(
        records,
        requested_regimes=regimes,
        setup_failures=failures,
        sources=sources,
    )


def _load_records(path: Path) -> list[dict[str, Any]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, dict):
        raw = raw.get("records")
    if not isinstance(raw, list):
        raise ValueError("records JSON must be a list or {'records': [...]}")
    if not all(isinstance(row, dict) for row in raw):
        raise ValueError("every calibration record must be an object")
    return [dict(row) for row in raw]


def _write_report(report: dict[str, Any], out: Path) -> Path:
    out = Path(out)
    if not out.is_absolute():
        out = ROOT / out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return out


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Phase-2 transfer calibration acceptance")
    parser.add_argument(
        "--regime",
        choices=("both", "assisted-loo", "true-unseen"),
        default="both",
    )
    parser.add_argument("--records-json", type=Path, default=None)
    parser.add_argument(
        "--reanalyze-report",
        type=Path,
        default=None,
        help="Refresh ablation summaries from stored rows without rerunning models",
    )
    parser.add_argument("--rbp", action="append", default=None, help="Target alias; repeatable")
    parser.add_argument("--cohort", choices=("K562", "HepG2"), default="K562")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--max-seqs", type=int, default=64)
    parser.add_argument("--device", choices=("cuda", "cpu"), default="cuda")
    parser.add_argument("--with-seq", action="store_true")
    parser.add_argument(
        "--no-rna",
        action="store_true",
        help="Skip RNA BLAST for a zero-weight policy iteration",
    )
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)

    regimes = (
        REGIMES
        if args.regime == "both"
        else (normalize_regime(args.regime),)
    )
    if args.top_k < 1 or args.max_seqs < 1:
        parser.error("--top-k and --max-seqs must be positive")

    try:
        if args.reanalyze_report is not None:
            report = json.loads(args.reanalyze_report.read_text(encoding="utf-8"))
            if report.get("schema") != "transfer_calibration.v1":
                raise ValueError("--reanalyze-report needs transfer_calibration.v1")
            for block in (report.get("regimes") or {}).values():
                all_rows = [
                    row
                    for row in (block.get("rows") or [])
                    if isinstance(row, dict)
                ]
                rows = [
                    row
                    for row in all_rows
                    if row.get("status") == "scored"
                ]
                full_metrics = (
                    (block.get("metrics") or {}).get("all_scored") or {}
                )
                block["metric_ablations"] = summarize_metric_ablations(
                    rows,
                    full_metrics,
                )
                curve = coverage_risk_curve(all_rows)
                block["coverage_risk"] = curve
                block["selective_risk_validation"] = (
                    validate_coverage_risk_calibration(curve)
                )
            report["reanalyzed_at"] = datetime.now(timezone.utc).isoformat()
        elif args.records_json is not None:
            if not args.records_json.is_file():
                raise CalibrationDataUnavailable(
                    f"records JSON unavailable: {args.records_json}"
                )
            records = _load_records(args.records_json)
            report = build_calibration_report(records, requested_regimes=regimes)
        else:
            report = run_live_calibration(
                regimes=regimes,
                targets=args.rbp,
                cohort=args.cohort,
                top_k=args.top_k,
                max_seqs=args.max_seqs,
                device=args.device,
                with_seq=bool(args.with_seq),
                with_rna=not bool(args.no_rna),
            )
    except (CalibrationDataUnavailable, ImportError) as exc:
        blocked = {
            "schema": "transfer_calibration.v1",
            "status": "blocked",
            "ok": False,
            "reason": (
                str(exc)
                if isinstance(exc, CalibrationDataUnavailable)
                else f"live calibration dependency unavailable: {exc}"
            ),
            "requested_regimes": list(regimes),
        }
        if args.out is not None:
            _write_report(blocked, args.out)
        print(json.dumps(blocked, indent=2, ensure_ascii=False), file=sys.stderr)
        return 2
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    if args.out is None and args.reanalyze_report is not None:
        out = args.reanalyze_report
    elif args.out is None:
        from app.core.paths import ensure_artifact_dirs, report_path

        ensure_artifact_dirs()
        out = report_path("transfer_calibration.json")
    else:
        out = args.out
    written = _write_report(report, out)
    summary = {
        "status": report["status"],
        "ok": report["ok"],
        "out": str(written),
        "regimes": {
            key: {
                "status": value["status"],
                "n_total": value["n_total"],
                "n_scored": value["n_scored"],
                "auprc": value["metrics"]["all_scored"].get("auprc"),
                "auroc": value["metrics"]["all_scored"].get("auroc"),
                "ece": value["metrics"]["all_scored"].get("ece"),
                "positive_fidelity": value["positive_fidelity"]["pass_rate"],
            }
            for key, value in report["regimes"].items()
        },
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if report.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
