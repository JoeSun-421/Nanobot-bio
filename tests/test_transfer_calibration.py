# -*- coding: utf-8 -*-
"""Lightweight tests for Phase-2 transfer calibration (no torch/GPU)."""

from __future__ import annotations

import json

import pytest

from rbp_eval.accept.transfer_calibration import (
    ASSISTED_LOO,
    TRUE_UNSEEN,
    HeldTargetLeakage,
    aggregate_calibration_record,
    build_calibration_report,
    validate_coverage_risk_calibration,
    main,
    validate_strict_target_exclusion,
)


def _records(regime: str) -> list[dict]:
    rows = []
    labels = [1, 0, 1, 0, 1, 0]
    for index, y in enumerate(labels):
        predictions = (
            [{"alias": "DONOR_A", "prob": 0.95}, {"alias": "DONOR_B", "prob": 0.85}]
            if y
            else [{"alias": "DONOR_A", "prob": 0.05}, {"alias": "DONOR_B", "prob": 0.15}]
        )
        rows.append(
            {
                "case_id": f"{regime}:{index}",
                "regime": regime,
                "held_target": "HELD",
                "y": y,
                "own_head_prob": 0.90 if y else 0.10,
                "proxies": [
                    {"rbp_id": "DONOR_A", "similarity_score": 0.9},
                    {"rbp_id": "DONOR_B", "similarity_score": 0.8},
                ],
                "predictions": predictions,
                "transfer_priors": (
                    {"DONOR_A": 0.8, "DONOR_B": 0.7}
                    if regime == ASSISTED_LOO
                    else {}
                ),
                "donor_quality": {"DONOR_A": 0.9, "DONOR_B": 0.8},
            }
        )
    return rows


def test_report_separates_regimes_and_emits_required_outputs():
    report = build_calibration_report(
        _records(ASSISTED_LOO) + _records(TRUE_UNSEEN)
    )

    assert report["ok"] is True
    assert set(report["regimes"]) == {ASSISTED_LOO, TRUE_UNSEEN}
    for regime, block in report["regimes"].items():
        assert block["metrics"]["all_scored"]["auprc"] == 1.0
        assert block["metrics"]["all_scored"]["auroc"] == 1.0
        assert block["metrics"]["all_scored"]["ece"] is not None
        assert block["positive_fidelity"]["passed_all"] is True
        assert block["negative_fidelity"]["passed_all"] is True
        assert block["failures"]["n"] == 0
        assert len(block["coverage_risk"]) == 3
        assert block["coverage_risk"][0]["minimum_evidence_confidence"] == "high"
        assert block["selective_risk_validation"]["status"] == "not_validated"
        assert block["selective_risk_validation"]["high_confidence_policy"] == (
            "disabled_for_transfer"
        )
        if regime == TRUE_UNSEEN:
            assert all(
                not row["evidence"]["target_specific_prior_used"]
                for row in block["rows"]
            )


def test_strict_exclusion_rejects_held_target_everywhere():
    record = _records(ASSISTED_LOO)[0]
    record["predictions"].append({"alias": "HELD", "prob": 0.99})
    with pytest.raises(HeldTargetLeakage):
        validate_strict_target_exclusion(record)
    with pytest.raises(HeldTargetLeakage):
        aggregate_calibration_record(record)


def test_true_unseen_forbids_target_specific_prior_even_for_foreign_key():
    record = _records(TRUE_UNSEEN)[0]
    record["transfer_priors"] = {"DONOR_A": 0.8}
    with pytest.raises(HeldTargetLeakage, match="true_unseen forbids"):
        aggregate_calibration_record(record)


def test_positive_fidelity_needs_score_and_evidence_confidence():
    records = _records(TRUE_UNSEEN)
    # Score remains positive, but missing quality evidence forces low confidence.
    records[0]["donor_quality"] = {}
    block = build_calibration_report(
        records,
        requested_regimes=[TRUE_UNSEEN],
    )["regimes"][TRUE_UNSEEN]

    assert block["positive_fidelity"]["n_total"] == 3
    assert block["positive_fidelity"]["n_pass"] == 2
    assert block["positive_fidelity"]["passed_all"] is False
    assert block["coverage"]["medium_high_coverage"] == pytest.approx(5 / 6)


def test_fidelity_uses_per_rna_own_head_not_binary_label():
    records = _records(ASSISTED_LOO)
    records[0]["own_head_prob"] = 0.40
    block = build_calibration_report(
        records,
        requested_regimes=[ASSISTED_LOO],
    )["regimes"][ASSISTED_LOO]
    first = block["rows"][0]
    assert first["label_absolute_error"] < 0.2
    assert first["absolute_error_to_own_head"] > 0.2
    assert block["positive_fidelity"]["n_pass"] == 2


def test_report_publishes_fixed_cohort_metric_ablations():
    records = _records(TRUE_UNSEEN)
    for row in records:
        row["metric_ablation_p_hat"] = {
            "esmc_cosine": 0.88 if row["y"] else 0.12
        }
    block = build_calibration_report(
        records,
        requested_regimes=[TRUE_UNSEEN],
    )["regimes"][TRUE_UNSEEN]
    ablation = block["metric_ablations"]["esmc_cosine"]
    assert ablation["n"] == 6
    assert ablation["coverage"] == 1.0
    assert ablation["metrics"]["auprc"] == 1.0


def test_failed_aggregation_is_visible_in_failure_and_coverage_risk():
    records = _records(ASSISTED_LOO)
    records[0]["predictions"] = []
    block = build_calibration_report(
        records,
        requested_regimes=[ASSISTED_LOO],
    )["regimes"][ASSISTED_LOO]

    assert block["failures"]["n"] == 1
    assert block["coverage"]["score_coverage"] == pytest.approx(5 / 6)
    assert block["coverage_risk"][-1]["coverage"] == pytest.approx(5 / 6)


def test_selective_risk_validation_detects_nonmonotonic_risk():
    curve = [
        {
            "minimum_evidence_confidence": "high",
            "n_covered": 0,
            "coverage": 0.0,
            "classification_risk": None,
            "mean_absolute_error": None,
        },
        {
            "minimum_evidence_confidence": "medium",
            "n_covered": 60,
            "coverage": 0.6,
            "classification_risk": 0.30,
            "mean_absolute_error": 0.20,
        },
        {
            "minimum_evidence_confidence": "low",
            "n_covered": 100,
            "coverage": 1.0,
            "classification_risk": 0.20,
            "mean_absolute_error": 0.25,
        },
    ]
    validation = validate_coverage_risk_calibration(curve)
    assert validation["validated"] is False
    assert validation["sample_sufficient"] is True
    assert validation["classification_risk_monotonic"] is False


def test_cli_aggregates_records_without_gpu(tmp_path):
    records_path = tmp_path / "records.json"
    out = tmp_path / "report.json"
    records_path.write_text(json.dumps(_records(TRUE_UNSEEN)), encoding="utf-8")

    rc = main(
        [
            "--records-json",
            str(records_path),
            "--regime",
            "true-unseen",
            "--out",
            str(out),
        ]
    )

    assert rc == 0
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["regimes"][TRUE_UNSEEN]["metrics"]["all_scored"]["status"] == "ok"


def test_cli_fails_honestly_for_missing_records(tmp_path, capsys):
    rc = main(
        [
            "--records-json",
            str(tmp_path / "missing.json"),
            "--regime",
            "assisted-loo",
        ]
    )
    captured = capsys.readouterr()

    assert rc == 2
    assert '"status": "blocked"' in captured.err
    assert "records JSON unavailable" in captured.err
