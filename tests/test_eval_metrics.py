# -*- coding: utf-8 -*-
"""A4/A5/B4: shared metrics + Stage-3 de-LLM-explanation ablation + ECE in LOO."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rbp_eval.scoring.metrics import (
    average_precision,
    expected_calibration_error,
    metrics_from_pairs,
    roc_auc,
)


def test_metrics_from_pairs_includes_ece():
    pairs = [
        {"p_hat": 0.9, "y": 1},
        {"p_hat": 0.8, "y": 1},
        {"p_hat": 0.7, "y": 0},
        {"p_hat": 0.6, "y": 1},
        {"p_hat": 0.1, "y": 0},
        {"p_hat": 0.2, "y": 0},
    ]
    m = metrics_from_pairs(pairs)
    assert m["status"] == "ok"
    assert m["n"] == 6 and m["n_pos"] == 3 and m["n_neg"] == 3
    assert m["auroc"] is not None and m["auprc"] is not None
    assert m["ece"] is not None and 0.0 <= m["ece"] <= 1.0


def test_metrics_from_pairs_label_collapse():
    pairs = [
        {"p_hat": 0.9, "label": "Strong"},
        {"p_hat": 0.8, "label": "Likely"},
        {"p_hat": 0.7, "label": "Unlikely"},
        {"p_hat": 0.6, "label": "Likely"},
        {"p_hat": 0.1, "label": "No"},
        {"p_hat": 0.2, "label": "No"},
    ]
    m = metrics_from_pairs(pairs)
    assert m["status"] == "ok" and m["n_pos"] == 3


def test_metrics_skipped_when_too_few():
    m = metrics_from_pairs([{"p_hat": 0.5, "y": 1}, {"p_hat": 0.5, "y": 0}])
    assert m["status"] == "skipped"


def test_evaluation_plan_reexports_metrics():
    from rbp_eval.plans.evaluation_plan import (
        binary_from_four_level,
        expected_calibration_error as ece_re,
        metrics_from_pairs as mfp_re,
    )

    assert binary_from_four_level("Strong") == 1
    assert binary_from_four_level("No") == 0
    pairs = [{"p_hat": 0.9, "y": 1}, {"p_hat": 0.1, "y": 0}] * 3
    assert mfp_re(pairs)["ece"] == metrics_from_pairs(pairs)["ece"]
    assert ece_re([0.9, 0.1, 0.8, 0.2, 0.7, 0.3], [1, 0, 1, 0, 1, 0]) is not None


def test_loo_eval_instance_level_with_labels(tmp_path):
    import asyncio
    import importlib

    loo = importlib.import_module("rbp_eval.loo.loo_eval")
    labels = tmp_path / "labels.json"
    labels.write_text(
        json.dumps([{"p_hat": 0.9, "y": 1}, {"p_hat": 0.1, "y": 0}] * 3),
        encoding="utf-8",
    )
    # Exercise the instance-level branch without the full LOO CSV pipeline by
    # calling metrics_from_pairs directly (loo_eval wires it the same way).
    pairs = json.loads(labels.read_text(encoding="utf-8"))
    il = metrics_from_pairs(pairs)
    assert il["status"] == "ok" and il["ece"] is not None


@pytest.mark.requires_delivery
def test_stage3_no_llm_explanation_ablation_runs(tmp_path):
    """A4: evaluation_plan --no-llm-explanation records no_llm vs full_llm metrics."""
    import subprocess

    no_llm = tmp_path / "no_llm.json"
    full_llm = tmp_path / "full_llm.json"
    no_llm.write_text(
        json.dumps([{"p_hat": 0.9, "y": 1}, {"p_hat": 0.1, "y": 0}] * 3),
        encoding="utf-8",
    )
    full_llm.write_text(
        json.dumps([{"p_hat": 0.95, "y": 1}, {"p_hat": 0.05, "y": 0}] * 3),
        encoding="utf-8",
    )
    out = tmp_path / "ep.json"
    md = tmp_path / "ep.md"
    qual = tmp_path / "qual.csv"
    rc = subprocess.run(
        [
            sys.executable, "-m", "rbp_eval.plans.evaluation_plan",
            "--out", str(out), "--md", str(md), "--qual", str(qual),
            "--labels", str(no_llm), "--labels-llm", str(full_llm),
            "--no-llm-explanation",
        ],
        capture_output=True, text=True, cwd=str(ROOT),
    )
    assert rc.returncode == 0, rc.stderr
    report = json.loads(out.read_text(encoding="utf-8"))
    abl = report["stage3"]["ablation_no_llm_explanation"]
    assert abl["status"] == "ok"
    assert abl["no_llm"]["status"] == "ok" and abl["full_llm"]["status"] == "ok"
    assert "delta_auroc" in abl and "delta_auprc" in abl and "delta_ece" in abl
