# -*- coding: utf-8 -*-
"""run_eval harness + synthetic promote refusal."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _held():
    return {
        "PTBP1": [
            [
                {
                    "alias": "U2AF2",
                    "score": 0.9,
                    "metric": "domain_overlap",
                    "sim_by_modality": {
                        "domain_overlap": 0.9,
                        "esmc_cosine": 0.85,
                        "tm_score": 0.5,
                    },
                },
                {
                    "alias": "ELAVL1",
                    "score": 0.6,
                    "metric": "domain_overlap",
                    "sim_by_modality": {
                        "domain_overlap": 0.6,
                        "esmc_cosine": 0.55,
                        "tm_score": 0.4,
                    },
                },
            ]
        ]
    }


def test_modality_ablation_schema():
    from rbp_eval.evolve.run_eval import run_modality_ablation

    out = run_modality_ablation(_held(), top_k=3)
    assert out["schema"] == "modality_ablation/v1"
    axes = {r["axis"] for r in out["ablations"]}
    assert "embedding" in axes
    assert "structure" in axes
    assert "sequence" in axes


def test_run_eval_writes_reports(tmp_path):
    from rbp_eval.evolve.run_eval import run_eval

    report = run_eval(held_to_hit_lists=_held(), top_k=3, out_dir=tmp_path, write=True)
    # report_path writes JSON under out_dir/json/ (format subdir layout)
    assert (tmp_path / "json" / "modality_ablation_report.json").is_file()
    assert (tmp_path / "json" / "run_eval_report.json").is_file()
    assert report.get("modality_ablation")


def test_synthetic_retrieval_only_detected():
    from rbp_eval.evolve.run_eval import (
        assert_not_synthetic_promote_input,
        results_are_retrieval_only_synthetic,
    )

    results = [
        {
            "mode": "retrieval_only",
            "verdict": {"p_hat": None},
        }
    ]
    assert results_are_retrieval_only_synthetic(results)
    with pytest.raises(ValueError, match="retrieval-only"):
        assert_not_synthetic_promote_input(results)


def test_evolve_blocks_synthetic_candidate(tmp_path, monkeypatch):
    from rbp_eval.evolve import orchestrator as orch
    from rbp_eval.evolve import promote as promo
    from rbp_eval.evolve.orchestrator import run_self_evolution

    monkeypatch.setattr(orch, "EVOLVED_REPORT", tmp_path / "r.json")
    monkeypatch.setattr(orch, "CANDIDATE_CONFIG", tmp_path / "c.yaml")
    monkeypatch.setattr(promo, "EVOLVED_REPORT", tmp_path / "r.json")
    monkeypatch.setattr(promo, "CANDIDATE_CONFIG", tmp_path / "c.yaml")
    monkeypatch.setattr(promo, "EVOLVED_CONFIG", tmp_path / "e.yaml")

    results = [
        {
            "query": {"alias": "PTBP1"},
            "mode": "retrieval_only",
            "donors": [{"alias": "U2AF2", "score": 0.9}],
            "verdict": {"p_hat": None, "label": "No", "confidence": "low", "explanation": "x"},
        }
    ]
    report = run_self_evolution(
        results,
        held_to_hit_lists=_held(),
        write_config=True,
        require_loo_report=False,
        allow_retrieval_only=False,
    )
    payload = json.loads((tmp_path / "r.json").read_text(encoding="utf-8"))
    assert payload.get("promote_blocked") is True
    assert payload.get("scores_source") == "retrieval_only_synthetic"
    assert report.evolved_config_path is None
    assert not (tmp_path / "c.yaml").is_file()
