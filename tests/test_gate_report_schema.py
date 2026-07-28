# -*- coding: utf-8 -*-
"""Offline schema asserts for LOO / eval-plan gate reports."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.dev.gate import assert_eval_plan_report, assert_loo_report


def test_assert_loo_report_schema(tmp_path: Path):
    p = tmp_path / "eval_loo_report.json"
    p.write_text(
        json.dumps(
            {
                "n": 10,
                "summary": {"n_ok": 10, "mean_policy_best": 0.5},
                "rows": [{"held_rbp": f"R{i}"} for i in range(10)],
                "failures": [],
            }
        ),
        encoding="utf-8",
    )
    assert_loo_report(p)


def test_assert_loo_report_rejects_small_n(tmp_path: Path):
    p = tmp_path / "eval_loo_report.json"
    p.write_text(
        json.dumps({"n": 3, "summary": {}, "rows": []}),
        encoding="utf-8",
    )
    with pytest.raises(AssertionError, match="n<10"):
        assert_loo_report(p)


def test_assert_eval_plan_report_schema(tmp_path: Path):
    p = tmp_path / "evaluation_plan_report.json"
    p.write_text(
        json.dumps(
            {
                "held_out_split": {
                    "n_held": 10,
                    "held_out_rbps": [f"R{i}" for i in range(10)],
                    "seen": 100,
                    "note": "fixture",
                },
                "primary_metrics": {
                    "transfer_level": {"auprc": 0.7, "auroc": 0.8},
                    "instance_level": {},
                },
            }
        ),
        encoding="utf-8",
    )
    assert_eval_plan_report(p)


def test_assert_eval_plan_report_requires_transfer_metrics(tmp_path: Path):
    p = tmp_path / "evaluation_plan_report.json"
    p.write_text(
        json.dumps(
            {
                "held_out_split": {"n_held": 10, "held_out_rbps": ["A"]},
                "primary_metrics": {},
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(AssertionError, match="transfer_level"):
        assert_eval_plan_report(p)
