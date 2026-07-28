# -*- coding: utf-8 -*-
"""Unit tests for Evaluation Plan metrics helpers."""

from __future__ import annotations

from rbp_eval.plans.evaluation_plan import (
    binary_from_four_level,
    expected_calibration_error,
    metrics_from_pairs,
)


def test_binary_collapse():
    assert binary_from_four_level("Strong") == 1
    assert binary_from_four_level("Likely") == 1
    assert binary_from_four_level("Unlikely") == 0
    assert binary_from_four_level("No") == 0


def test_metrics_perfect_separation():
    pairs = [{"p_hat": 0.9, "y": 1} for _ in range(5)] + [
        {"p_hat": 0.1, "y": 0} for _ in range(5)
    ]
    m = metrics_from_pairs(pairs)
    assert m["status"] == "ok"
    assert m["auroc"] == 1.0
    assert m["auprc"] == 1.0
    assert m["ece"] is not None
    assert m["ece"] < 0.2


def test_ece_calibrated():
    # perfectly calibrated mid scores
    pairs = [{"p_hat": 0.7, "y": 1} for _ in range(7)] + [
        {"p_hat": 0.7, "y": 0} for _ in range(3)
    ]
    m = metrics_from_pairs(pairs)
    assert m["status"] == "ok"
    assert expected_calibration_error(
        [0.7] * 10, [1] * 7 + [0] * 3
    ) is not None
