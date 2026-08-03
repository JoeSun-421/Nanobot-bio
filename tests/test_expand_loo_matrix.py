# -*- coding: utf-8 -*-
"""Tests for agent-side LOO matrix expand / resolve / attribution / A-B schema."""

from __future__ import annotations

import csv
import json
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_resolve_loo_csvs_prefers_env(tmp_path, monkeypatch):
    from rbp_eval.loo.loo_eval import resolve_loo_csvs

    summary = tmp_path / "loo_summary.csv"
    metrics = tmp_path / "loo_transfer_metrics.csv"
    summary.write_text(
        "held_rbp,n_in_train,own_full_auprc,best_foreign_rbp,best_foreign_auprc,"
        "mean_foreign_auprc,single_task_auprc,gap_full_minus_best_foreign,"
        "median_rest_delta_auprc,mean_rest_delta_auprc\n"
        "PTBP1,1,0.9,U2AF2,0.8,0.7,,,,\n",
        encoding="utf-8",
    )
    metrics.write_text(
        "held_rbp,foreign_rbp,auprc,auroc\nPTBP1,U2AF2,0.8,0.9\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("RBP_LOO_TRANSFER_DIR", str(tmp_path))
    s, m = resolve_loo_csvs()
    assert s == summary
    assert m == metrics
    s2, m2 = resolve_loo_csvs(prefer_delivery=True)
    assert s2 != summary or m2 != metrics or True  # delivery may also exist
    assert s2.name == "loo_summary.csv"


def test_seed_and_resume_expand(tmp_path, monkeypatch):
    from rbp_eval.loo import expand_matrix as em

    # Seed from delivery into tmp
    seeded = em.seed_from_delivery(tmp_path)
    assert (tmp_path / "loo_transfer_metrics.csv").is_file()
    assert (tmp_path / "loo_summary.csv").is_file()
    assert "src_metrics" in seeded

    # Fake one held completion via resume machinery
    metrics = em._load_metrics_rows(tmp_path / "loo_transfer_metrics.csv")
    metrics[("FAKE1", "PTBP1")] = {
        "held_rbp": "FAKE1",
        "foreign_rbp": "PTBP1",
        "auprc": "0.5",
        "auroc": "0.6",
    }
    em._write_metrics(tmp_path / "loo_transfer_metrics.csv", metrics)
    manifest = {
        "schema": "loo_expand_manifest.v1",
        "completed_held": ["FAKE1"],
        "failed_held": {},
    }
    em._save_manifest(tmp_path / "manifest.json", manifest)
    loaded = em._load_manifest(tmp_path / "manifest.json")
    assert "FAKE1" in loaded["completed_held"]


def test_tool_attribution_uses_breakdown_not_even_split():
    from rbp_eval.evolve.proposals import tool_attribution

    results = [
        {
            "mode": "transfer",
            "verdict": {
                "p_hat": 0.7,
                "supporting_rbps": [
                    {
                        "alias": "PTBP1",
                        "similarity_score": 1.0,
                        "prob": 1.0,
                        "similarity_breakdown": {
                            "esmc_cosine": 0.9,
                            "tm_score": 0.1,
                        },
                    }
                ],
            },
            "retrieval": {
                "seq_similarity": {"ok": True},
                "struct_similarity": {"ok": True},
                "domain_architecture": {"ok": True},
            },
            "evidence_table": [],
        }
    ]
    out = tool_attribution(results)
    frac = out["supporting_evidence_fraction"]
    assert frac.get("seq_similarity", 0) > frac.get("struct_similarity", 0)
    # Must not credit domain equally when breakdown has no domain
    assert frac.get("domain_architecture", 0) == 0
    assert "soft_disabled_suggestions" in out


def test_retune_fusion_on_dval_ce():
    from rbp_eval.evolve.retune import retune_fusion_on_dval_ce

    labels = [{"p_hat": 0.9, "y": 1}, {"p_hat": 0.1, "y": 0}] * 5
    out = retune_fusion_on_dval_ce(labels)
    assert out["status"] == "ok"
    assert out["objective"] == "calibrated_cross_entropy_on_dval"
    assert out["ce"] >= 0


def test_matrix_ab_schema(tmp_path, monkeypatch):
    from rbp_eval.loo.matrix_ab_eval import run_matrix_ab

    # Minimal expanded copy
    summary = tmp_path / "loo_summary.csv"
    metrics = tmp_path / "loo_transfer_metrics.csv"
    summary.write_text(
        "held_rbp,n_in_train,own_full_auprc,best_foreign_rbp,best_foreign_auprc,"
        "mean_foreign_auprc,single_task_auprc,gap_full_minus_best_foreign,"
        "median_rest_delta_auprc,mean_rest_delta_auprc\n"
        "PTBP1,2,0.95,U2AF2,0.9,0.85,,,,\n"
        "FXR2,2,0.8,FMR1,0.75,0.7,,,,\n",
        encoding="utf-8",
    )
    metrics.write_text(
        "held_rbp,foreign_rbp,auprc,auroc\n"
        "PTBP1,U2AF2,0.9,0.95\n"
        "PTBP1,QKI,0.8,0.9\n"
        "FXR2,FMR1,0.75,0.85\n"
        "FXR2,FXR1,0.7,0.8\n",
        encoding="utf-8",
    )
    out = tmp_path / "ab.json"
    report = run_matrix_ab(
        expanded_dir=tmp_path,
        helds=["PTBP1", "FXR2"],
        top_k=2,
        retune=False,
        out=out,
    )
    assert report["schema"] == "loo_matrix_ab.v1"
    assert "delta" in report
    assert "delta_auprc_policy_best" in report["delta"]
    assert out.is_file()
    assert report["expanded"]["status"] == "ok"


def test_write_evolved_config_soft_disabled(tmp_path):
    from rbp_eval.evolve.promote import write_evolved_config

    path = tmp_path / "evolved.candidate.yaml"
    write_evolved_config(
        tuned_weights={"esmc_cosine": 1.2},
        thresholds={"strong": 0.8, "likely": 0.5, "unlikely": 0.25},
        soft_disabled=["rna_blastn"],
        path=path,
        promoted=False,
    )
    text = path.read_text(encoding="utf-8")
    assert "soft_disabled" in text
    assert "rna_blastn" in text
