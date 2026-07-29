# -*- coding: utf-8 -*-
"""Path / SDK-boundary / accuracy-gate regression tests."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_no_proposal_sot_or_fusion_shim():
    assert not (ROOT / "app" / "_proposal_sot").exists()
    assert not (ROOT / "rbp_eval" / "fusion.py").exists()


def test_sot_root_is_repo_nanobot():
    from app.sot import skill_md, sot_root, tools_rbp

    assert sot_root() == (ROOT / "nanobot").resolve()
    assert skill_md().is_file()
    assert (tools_rbp() / "predict.py").is_file()


def test_defaults_rna_weights_zero_and_models_section():
    import yaml

    cfg = yaml.safe_load((ROOT / "config" / "defaults.yaml").read_text(encoding="utf-8"))
    assert float(cfg["fusion_weights"]["rna_peak_homology"]) == 0.0
    assert "rhobind" in cfg["models"]
    assert "rna_blastn" in cfg["models"]
    assert "rna_fm" not in cfg["models"]


def test_checklist_two_fails_forces_low_confidence():
    from app.core.verdict_schema import normalize_verdict

    v = normalize_verdict(
        {
            "label": "Strong",
            "p_hat": 0.9,
            "confidence": "high",
            "explanation": "High score but weak evidence.",
            "supporting_rbps": [],
            "evidence_flags": {
                "structure_unavailable": True,
                "prior_missing": True,
            },
        }
    )
    assert v["confidence"] == "low"


def test_model_capability_matrix_writes():
    from app.core.model_registry import write_capability_matrix
    from app.core.paths import report_path

    path = write_capability_matrix(report_path("model_capability_matrix_test.json"))
    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    assert "rhobind" in text
    assert "rna_blastn" in text
