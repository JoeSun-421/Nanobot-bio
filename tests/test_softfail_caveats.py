# -*- coding: utf-8 -*-
"""F1/F2: delivery-backed soft-fail evidence flags + head-coverage caveat.

Covers the RBM20-style gaps surfaced in the v0.5.0 review:
* structure_fetch error → structure_axis_unavailable caveat (F1/B3)
* domain_architecture domain_source:none → domain_empty caveat (F1/B3)
* predict_interaction multi-head with null-prob donors → low_head_coverage caveat (F2)
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from nanobot.agent.tools.rbp import turn_guards  # noqa: E402
from app.core.verdict_schema import normalize_verdict_with_turn_state  # noqa: E402


def _reset():
    turn_guards.reset_stage_guards()


def _build_delivery_tool(name: str):
    """Construct a DeliveryBackedTool shell (no live client) for softfail mapping."""
    from app.backends.delivery.registry import DeliveryBackedTool

    tool = DeliveryBackedTool.__new__(DeliveryBackedTool)
    tool._delivery_name = name
    return tool


def test_structure_fetch_error_surfaces_axis_unavailable():
    _reset()
    tool = _build_delivery_tool("structure_fetch")
    # Simulate the error-envelope branch by calling the softfail mapper directly.
    tool._surface_axis_softfail({"error": "no structure available"})
    flags = turn_guards.evidence_flags()
    assert flags.get("structure_axis_unavailable") is True
    _reset()


def test_domain_architecture_none_surfaces_domain_empty():
    _reset()
    tool = _build_delivery_tool("domain_architecture")
    tool._surface_axis_softfail({"error": "no domains"})
    flags = turn_guards.evidence_flags()
    assert flags.get("domain_empty") is True
    _reset()


def test_literature_error_surfaces_literature_unavailable():
    _reset()
    tool = _build_delivery_tool("literature_retrieval")
    tool._surface_axis_softfail({"error": "offline"})
    flags = turn_guards.evidence_flags()
    assert flags.get("literature_unavailable") is True
    _reset()


def test_mmseqs_segfault_surfaces():
    _reset()
    tool = _build_delivery_tool("seq_similarity")
    tool._surface_axis_softfail({"error": "mmseqs segfault exit -11"})
    flags = turn_guards.evidence_flags()
    assert flags.get("mmseqs_segfall") is True
    _reset()


def test_normalize_merges_structure_axis_unavailable_into_caveats():
    _reset()
    turn_guards.add_evidence_flag("structure_axis_unavailable", True)
    raw = {
        "label": "Likely",
        "p_hat": 0.73,
        "confidence": "medium",
        "explanation": "transfer prediction",
    }
    out = normalize_verdict_with_turn_state(raw)
    caveats = out.get("caveats") or []
    assert "structure_axis_unavailable" in caveats
    assert out["confidence"] == "low"
    _reset()


def test_normalize_merges_domain_empty_into_caveats():
    _reset()
    turn_guards.add_evidence_flag("domain_empty", True)
    raw = {
        "label": "Likely",
        "p_hat": 0.6,
        "confidence": "medium",
        "explanation": "transfer",
    }
    out = normalize_verdict_with_turn_state(raw)
    assert "domain_empty" in (out.get("caveats") or [])
    _reset()


def test_low_head_coverage_forces_low_confidence():
    _reset()
    # Simulate predict_interaction surfacing low head coverage (2 of 5 donors no head).
    turn_guards.add_evidence_flag("low_head_coverage", 0.6)
    raw = {
        "label": "Likely",
        "p_hat": 0.7325,
        "confidence": "medium",
        "explanation": "multi-head transfer",
    }
    out = normalize_verdict_with_turn_state(raw)
    assert out["confidence"] == "low"
    assert "low_head_coverage" in (out.get("caveats") or [])
    _reset()


def test_two_axis_failures_force_low_via_checklist():
    """structure_axis_unavailable + domain_empty → ≥2 checklist fails → low."""
    _reset()
    turn_guards.add_evidence_flag("structure_axis_unavailable", True)
    turn_guards.add_evidence_flag("domain_empty", True)
    raw = {
        "label": "Likely",
        "p_hat": 0.7,
        "confidence": "high",
        "explanation": "transfer",
    }
    out = normalize_verdict_with_turn_state(raw)
    assert out["confidence"] == "low"
    _reset()
