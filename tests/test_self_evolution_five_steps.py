# -*- coding: utf-8 -*-
"""Unit coverage for proposal §7 five-step self-evolution closure."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_trace_schema_make_event_and_stage1_type():
    from rbp_eval.runtime.trace_schema import EVENT_TYPES, make_event, validate_event

    assert "stage1_bypassed" in EVENT_TYPES
    ev = make_event(
        "query_end",
        session_key="t",
        donors=[{"alias": "U2AF2", "sim_by_modality": {"transfer_prior": 0.9}}],
        fused_similarities=[{"alias": "U2AF2", "score": 0.9}],
        verdict={"label": "Likely", "p_hat": 0.7},
    )
    assert ev["schema"] == "rbp_trace/v1"
    assert validate_event(ev) == []


def test_soft_disabled_skips_registration(monkeypatch):
    from app.core import runtime_config as rc

    rc.clear_runtime_config_cache()
    monkeypatch.setattr(rc, "soft_disabled_tools", lambda: ["lookup_proxy_cache"])

    class _Reg:
        def __init__(self):
            self.names = []

        def register(self, tool):
            self.names.append(tool.name)

    from nanobot.agent.tools.rbp import register_all

    reg = _Reg()
    names = register_all(reg)
    assert "lookup_proxy_cache" not in names
    assert "lookup_proxy_cache" not in reg.names
    assert "fuse_similarity_views" in names


def test_soft_disabled_blocked_envelope(monkeypatch):
    from app.core import runtime_config as rc
    from nanobot.agent.tools.rbp.turn_guards import blocked_envelope_json, reset_stage_guards

    reset_stage_guards()
    rc.clear_runtime_config_cache()
    monkeypatch.setattr(rc, "soft_disabled_tools", lambda: ["seq_similarity"])
    env = blocked_envelope_json("seq_similarity")
    assert env is not None
    assert "disabled_by_evolution" in env


def test_ce_retune_writes_logit_scale_and_tuned_weights():
    from rbp_eval.evolve.retune import retune_fusion_on_dval_ce

    labels = [{"p_hat": 0.9, "y": 1, "held_rbp": "PTBP1"}, {"p_hat": 0.1, "y": 0, "held_rbp": "PTBP1"}] * 5
    labels += [{"p_hat": 0.8, "y": 1, "held_rbp": "FXR2"}, {"p_hat": 0.2, "y": 0, "held_rbp": "FXR2"}] * 3
    hmap = {
        "PTBP1": [[{"alias": "U2AF2", "score": 0.9, "metric": "domain_jaccard"}]],
        "FXR2": [[{"alias": "FMR1", "score": 0.8, "metric": "esmc_cosine"}]],
    }
    out = retune_fusion_on_dval_ce(labels, held_to_hit_lists=hmap, base_weights={"esmc_cosine": 1.0})
    assert out["status"] == "ok"
    assert out["logit_scale"] > 0
    assert "tuned_weights" in out
    assert out["tuned_weights"]


def test_write_evolved_config_logit_scale(tmp_path):
    from rbp_eval.evolve.promote import write_evolved_config

    path = tmp_path / "evolved.candidate.yaml"
    write_evolved_config(
        tuned_weights={"esmc_cosine": 1.1},
        thresholds={"strong": 0.8, "likely": 0.5, "unlikely": 0.25},
        soft_disabled=["rna_blastn"],
        logit_scale=8.0,
        path=path,
        promoted=False,
    )
    text = path.read_text(encoding="utf-8")
    assert "logit_scale" in text
    assert "8" in text
    assert "soft_disabled" in text


def test_apply_logit_scale_identity_and_tempered():
    from app.core.runtime_config import apply_logit_scale

    assert abs(apply_logit_scale(0.7, scale=1.0) - 0.7) < 1e-9
    hot = apply_logit_scale(0.7, scale=12.0)
    assert hot > 0.7


def test_stage1_bypass_blocks_retrieve_allows_fuse():
    from nanobot.agent.tools.rbp.turn_guards import (
        fuse_blocked_reason,
        mark_stage1_bypassed,
        reset_stage_guards,
        retrieve_blocked_reason,
        stage1_bypassed,
    )

    reset_stage_guards()
    mark_stage1_bypassed([{"alias": "U2AF2", "score": 0.9}])
    assert stage1_bypassed()
    assert retrieve_blocked_reason("domain_architecture") is not None
    assert retrieve_blocked_reason("seq_similarity") is not None
    assert fuse_blocked_reason() is None
    reset_stage_guards()
    assert not stage1_bypassed()


def test_review_toolkit_proposals_writes_decisions(tmp_path):
    from rbp_eval.evolve.toolkit_review import list_proposals, review_proposal

    props = tmp_path / "toolkit_proposals.json"
    props.write_text(
        json.dumps(
            {
                "schema": "toolkit_proposals/v1",
                "human_review": True,
                "proposals": [{"id": "add_motif_scan", "priority": "high"}],
            }
        ),
        encoding="utf-8",
    )
    dec = tmp_path / "decisions.json"
    entry = review_proposal(
        "add_motif_scan",
        decision="accept",
        note="ok for PR",
        proposals_path=props,
        decisions_path=dec,
    )
    assert entry["decision"] == "accept"
    assert entry["auto_install"] is False
    data = json.loads(dec.read_text(encoding="utf-8"))
    assert data["decisions"][-1]["id"] == "add_motif_scan"
    assert list_proposals(proposals_path=props)[0]["id"] == "add_motif_scan"


def test_collect_agent_traces_writes_schema(tmp_path):
    from rbp_eval.evolve.runner import collect_agent_traces, load_traces

    results = [
        {
            "query": {"alias": "PTBP1"},
            "mode": "transfer",
            "donors": [
                {
                    "alias": "U2AF2",
                    "score": 0.9,
                    "sim_by_modality": {"transfer_prior": 0.9},
                }
            ],
            "evidence_table": [
                {"alias": "U2AF2", "score": 0.9, "sim_by_modality": {"transfer_prior": 0.9}}
            ],
            "verdict": {"label": "Likely", "p_hat": 0.6},
        }
    ]
    path = collect_agent_traces(results, out_path=tmp_path / "t.jsonl")
    rows = load_traces(path)
    assert rows
    assert rows[0]["schema"] == "rbp_trace/v1"
    assert rows[0]["type"] == "query_end"
    assert rows[0]["donors"][0]["sim_by_modality"]["transfer_prior"] == 0.9
