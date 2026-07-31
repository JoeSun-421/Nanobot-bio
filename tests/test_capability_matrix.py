# -*- coding: utf-8 -*-
"""Capability matrix SoT + promote RNA fusion honesty."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_probe_capabilities_has_feature_contracts():
    from app.core.capability_matrix import (
        SIMILARITY_WEIGHTED_VOTE_DRIVES_P_HAT,
        probe_capabilities,
    )

    data = probe_capabilities()
    feats = data["features"]
    assert feats["similarity_weighted_vote_drives_p_hat"] is True
    assert SIMILARITY_WEIGHTED_VOTE_DRIVES_P_HAT is True
    assert feats["feature_attribution"]["status"] == "unavailable"
    assert feats["p_hat_formula"]["source"] == "delivery_similarity_weighted_vote"
    assert feats["rna_blastn"]["tool"] == "rna_blastn"
    assert "rna_similarity" not in feats
    assert "af3" in feats


def test_write_capability_matrix_includes_features(tmp_path):
    from app.core.capability_matrix import write_capability_matrix

    path = write_capability_matrix(tmp_path / "matrix.json")
    text = path.read_text(encoding="utf-8")
    assert "feature_attribution" in text
    assert "similarity_weighted_vote_drives_p_hat" in text
    assert "p_hat_formula" in text


def test_assert_rna_fusion_promotable_blocks_nonzero_without_peaks(monkeypatch):
    from app.core import capability_matrix as cm

    monkeypatch.setattr(
        cm,
        "rna_blastn_status",
        lambda: {"status": "degraded", "tool": "rna_blastn"},
    )
    with pytest.raises(ValueError, match="rna_peak_homology"):
        cm.assert_rna_fusion_promotable(
            {"fusion_weights": {"rna_peak_homology": 0.3}}
        )


def test_assert_rna_fusion_promotable_ok_when_zero(monkeypatch):
    from app.core import capability_matrix as cm

    monkeypatch.setattr(
        cm,
        "rna_blastn_status",
        lambda: {"status": "degraded", "tool": "rna_blastn"},
    )
    cm.assert_rna_fusion_promotable(
        {"fusion_weights": {"rna_peak_homology": 0.0}}
    )


def test_promote_blocks_nonzero_rna_weights(tmp_path, monkeypatch):
    import yaml
    from app.core import capability_matrix as cm
    from rbp_eval.evolve.promote import promote_evolved_config

    monkeypatch.setattr(
        cm,
        "rna_blastn_status",
        lambda: {"status": "degraded", "tool": "rna_blastn"},
    )
    cand = tmp_path / "evolved.candidate.yaml"
    live = tmp_path / "evolved.yaml"
    cand.write_text(
        yaml.safe_dump(
            {
                "candidate": True,
                "evolved": False,
                "fusion_weights": {"rna_peak_homology": 0.3},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="rna_peak_homology"):
        promote_evolved_config(
            candidate=cand, live=live, require_reports=False, seed=False
        )


def test_candidate_seed_rna_weights_zero():
    import yaml

    seed = ROOT / "config" / "evolved.candidate.yaml.example"
    cfg = yaml.safe_load(seed.read_text(encoding="utf-8"))
    assert float(cfg["fusion_weights"]["rna_peak_homology"]) == 0.0


def test_af3_status_points_at_blackwell():
    from app.core.capability_matrix import read_af3_status

    st = read_af3_status()
    if not st:
        pytest.skip("AF3 status file not present (public CI / no local AF3 setup)")
    assert st.get("state")
    py = st.get("af3_python") or ""
    assert "af3_blackwell" in py or "af3" in py
