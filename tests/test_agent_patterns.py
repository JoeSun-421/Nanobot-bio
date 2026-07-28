# -*- coding: utf-8 -*-
"""Tests for agent-pattern iteration: traces, axes gate, dedupe, promote."""

from __future__ import annotations

from pathlib import Path

import yaml


def test_trace_schema_make_event():
    from rbp_eval.runtime.trace_schema import make_event, validate_event

    row = make_event(
        "tool_result",
        session_key="t",
        tool="resolve_rbp",
        args_hash="abcd",
        status="ok",
        latency_ms=1.2,
    )
    assert row["schema"] == "rbp_trace/v1"
    assert row["type"] == "tool_result"
    assert validate_event(row) == []


def test_axis_gate_blocks_structure_when_disabled():
    from app.backends.delivery.stage_tools import STAGE_TOOL_SETS, axis_enabled

    assert "predict_interaction" in STAGE_TOOL_SETS["stage0"]
    ok, axis = axis_enabled("predict_structure", axes={"use_af3": False, "structure": False})
    assert ok is False and axis == "use_af3"
    ok2, _ = axis_enabled("resolve_rbp", axes={"structure": False})
    assert ok2 is True


def test_promote_evolved_without_reports_force(tmp_path):
    from rbp_eval.evolve.promote import promote_evolved_config

    cand = tmp_path / "evolved.candidate.yaml"
    live = tmp_path / "evolved.yaml"
    cand.write_text(
        yaml.safe_dump(
            {
                "schema_version": "2.0+evolved",
                "evolved": False,
                "candidate": True,
                "fusion_weights": {"esmc_cosine": 0.9},
            }
        ),
        encoding="utf-8",
    )
    out = promote_evolved_config(
        candidate=cand, live=live, require_reports=False
    )
    assert out == live
    data = yaml.safe_load(live.read_text(encoding="utf-8"))
    assert data["evolved"] is True
    assert data["candidate"] is False


def test_jsonl_hook_writes_schema(tmp_path):
    from rbp_eval.runtime.hooks import JsonlTraceHook

    p = tmp_path / "t.jsonl"
    h = JsonlTraceHook(p, session_key="s1")
    h.push_event({"type": "query_end", "query": "x"})
    line = p.read_text(encoding="utf-8").strip().splitlines()[0]
    assert "rbp_trace/v1" in line
    assert "query_end" in line
