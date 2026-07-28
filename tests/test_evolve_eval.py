# -*- coding: utf-8 -*-
"""Unit tests for light nested-split self-evolution eval harness."""

from __future__ import annotations

from pathlib import Path

from rbp_eval.evolve.evolve_eval import (
    assemble_report,
    report_to_markdown,
    run_evolve_eval,
    score_policy_on_held,
    split_val_rbps,
)


def test_split_val_rbps_deterministic():
    a1, b1 = split_val_rbps(seed=42, n_test=5)
    a2, b2 = split_val_rbps(seed=42, n_test=5)
    assert a1 == a2 and b1 == b2
    assert len(a1) == 5 and len(b1) == 5
    assert set(a1).isdisjoint(set(b1))
    assert len(set(a1) | set(b1)) == 10


def test_score_policy_and_assemble_schema():
    hits = {
        "PTBP1": [
            [
                {"alias": "U2AF2", "score": 0.9, "metric": "domain_overlap"},
                {"alias": "ELAVL1", "score": 0.7, "metric": "domain_overlap"},
            ]
        ],
        "QKI": [
            [
                {"alias": "HNRNPC", "score": 0.85, "metric": "esmc_cosine"},
            ]
        ],
    }
    matrix = {
        ("PTBP1", "U2AF2"): 0.8,
        ("PTBP1", "ELAVL1"): 0.6,
        ("QKI", "HNRNPC"): 0.5,
    }
    scored = score_policy_on_held(
        hits,
        matrix,
        weights={"domain_overlap": 1.0, "esmc_cosine": 1.0, "fused": 1.0},
        abstain_thresholds={"fused": 0.1, "domain_overlap": 0.1, "esmc_cosine": 0.1},
        top_k=3,
    )
    assert scored["n_held"] == 2
    assert scored["n_scored"] >= 1
    assert "mean_policy_best_auprc" in scored

    report = assemble_report(
        train=["PTBP1"],
        test=["QKI"],
        defaults_score=scored,
        retuned_score={**scored, "mean_policy_best_auprc": (scored["mean_policy_best_auprc"] or 0) + 0.05},
        live_score=None,
        weight_retune={"status": "ok", "tuned_weights": {"domain_overlap": 1.0}},
        abstain_retune={"status": "ok", "tuned_thresholds": {"fused": 0.4}},
        seed=42,
        top_k=5,
        tier_a_ok=True,
    )
    assert report["schema"] == "evolve_eval.v1"
    assert "delta_auprc" in report
    assert report["promote"]["recommend"] in (
        "promote",
        "promote_if_tier_a_green",
        "hold",
    )
    md = report_to_markdown(report)
    assert "delta_auprc" in md
    assert "Promote recommendation" in md


def test_run_evolve_eval_synthetic(tmp_path, monkeypatch):
    from rbp_eval.evolve import retune as ev

    held = {
        "NSUN2": [[{"alias": "NOP2", "score": 0.9, "metric": "domain_overlap"}]],
        "FXR2": [[{"alias": "FMR1", "score": 0.85, "metric": "domain_overlap"}]],
        "HNRNPUL1": [[{"alias": "HNRNPC", "score": 0.8, "metric": "domain_overlap"}]],
        "EEF2": [[{"alias": "EEF1A1", "score": 0.75, "metric": "domain_overlap"}]],
        "PTBP1": [[{"alias": "U2AF2", "score": 0.95, "metric": "domain_overlap"}]],
        "CPSF6": [[{"alias": "CPSF7", "score": 0.7, "metric": "domain_overlap"}]],
        "DHX30": [[{"alias": "DHX9", "score": 0.65, "metric": "domain_overlap"}]],
        "DDX51": [[{"alias": "DDX5", "score": 0.6, "metric": "domain_overlap"}]],
        "DROSHA": [[{"alias": "DGCR8", "score": 0.55, "metric": "domain_overlap"}]],
        "RPS6": [[{"alias": "RPS3", "score": 0.5, "metric": "domain_overlap"}]],
    }
    matrix = {}
    for held_rbp, lists in held.items():
        for h in lists[0]:
            matrix[(held_rbp, h["alias"])] = 0.4 + 0.05 * (hash(held_rbp) % 5)

    def fake_weights(hmap, **kwargs):
        return {
            "status": "ok",
            "baseline_score": 0.5,
            "tuned_score": 0.55,
            "tuned_weights": {"domain_overlap": 1.5, "esmc_cosine": 0.3},
        }

    def fake_abstain(hmap, **kwargs):
        return {
            "status": "ok",
            "tuned_thresholds": {"fused": 0.35, "domain_overlap": 0.4},
            "tuned": {"mean_transfer": 0.55, "abstain_rate": 0.1},
        }

    monkeypatch.setattr(ev, "retune_weights", fake_weights)
    monkeypatch.setattr(ev, "retune_abstain_thresholds", fake_abstain)

    out_j = tmp_path / "evolve_eval_report.json"
    out_m = tmp_path / "evolve_eval_report.md"
    report = run_evolve_eval(
        held_to_hit_lists=held,
        matrix=matrix,
        seed=42,
        n_test=5,
        top_k=3,
        include_live=False,
        tier_a_ok=True,
        out_json=out_j,
        out_md=out_m,
        write=True,
    )
    assert report["schema"] == "evolve_eval.v1"
    assert "delta_auprc" in report
    assert out_j.is_file() and out_m.is_file()
    assert report["split"]["n_train"] == 5
    assert report["split"]["n_test"] == 5
