# -*- coding: utf-8 -*-
"""B1/B3: AF3 confidence on-demand + verdict caveats evidence-completeness audit."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.verdict_schema import normalize_verdict_with_turn_state
from nanobot.agent.tools.rbp import turn_guards


def test_caveats_surface_structure_soft_failures():
    """B1/B3: structure low_plddt / AF3 unavailable / literature offline must
    all surface into verdict caveats via the turn-state merge."""
    turn_guards.reset_stage_guards()
    turn_guards.add_evidence_flag("structure_low_plddt", True)
    turn_guards.add_evidence_flag("af3_unavailable", True)
    turn_guards.add_evidence_flag("literature_unavailable", True)

    raw = {
        "label": "Likely",
        "p_hat": 0.6,
        "confidence": "medium",
        "explanation": "grounded in tool outputs",
        "supporting_rbps": [],
    }
    v = normalize_verdict_with_turn_state(raw)
    caveats = v.get("caveats") or []
    assert "structure_low_plddt" in caveats
    assert "af3_unavailable" in caveats
    assert "literature_unavailable" in caveats


def test_caveats_surface_region_plddt_low_and_axis_skipped():
    turn_guards.reset_stage_guards()
    turn_guards.add_evidence_flag("region_plddt_low", True)
    turn_guards.add_evidence_flag("structure_axis_unavailable", True)
    v = normalize_verdict_with_turn_state(
        {
            "label": "Unlikely",
            "p_hat": 0.3,
            "confidence": "medium",
            "explanation": "x",
            "supporting_rbps": [],
        }
    )
    caveats = v.get("caveats") or []
    assert "region_plddt_low" in caveats
    assert "structure_axis_unavailable" in caveats


def test_no_caveats_when_no_soft_failures():
    turn_guards.reset_stage_guards()
    v = normalize_verdict_with_turn_state(
        {
            "label": "Strong",
            "p_hat": 0.9,
            "confidence": "high",
            "explanation": "all axes ok",
            "supporting_rbps": [],
        }
    )
    assert not v.get("caveats")


def test_explicit_evidence_flags_not_overridden_by_turn_state():
    """Caller-supplied evidence_flags win over turn-state flags (no clobber)."""
    turn_guards.reset_stage_guards()
    turn_guards.add_evidence_flag("literature_unavailable", True)
    v = normalize_verdict_with_turn_state(
        {
            "label": "Likely",
            "p_hat": 0.6,
            "confidence": "medium",
            "explanation": "x",
            "supporting_rbps": [],
            "evidence_flags": {"prior_missing": True},
        }
    )
    flags = v.get("evidence_flags") or {}
    assert flags.get("prior_missing") is True
    assert flags.get("literature_unavailable") is True
    caveats = v.get("caveats") or []
    assert "prior_missing" in caveats
    assert "literature_unavailable" in caveats


def test_af3_confidence_fields_filter_heavy_payload():
    """B1: _af3_confidence_fields surfaces region_plddt but drops chain_ptm /
    per_residue_plddt / confidences_json / regions[] (binding-relevant only)."""
    from nanobot.agent.tools.rbp.structure import _af3_confidence_fields

    out = {
        "mean_plddt": 62.0,
        "ptm": 0.7,
        "iptm": 0.65,
        "region_plddt": [{"region": [10, 80], "plddt": 55}],
        "chain_ptm": 0.8,  # should be dropped
        "per_residue_plddt": [0.1] * 100,  # should be dropped
        "confidences_json": "{}",  # should be dropped
        "regions": [[10, 80]],  # should be dropped
    }
    fields = _af3_confidence_fields(out)
    assert "mean_plddt" in fields and "region_plddt" in fields
    assert "chain_ptm" not in fields
    assert "per_residue_plddt" not in fields
    assert "confidences_json" not in fields
    assert "regions" not in fields
