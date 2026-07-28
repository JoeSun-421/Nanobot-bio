# -*- coding: utf-8 -*-
"""Runtime + product contracts: vote aligns with predict p_hat; RNA fusion honesty."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_vote_not_tagged_explain_only(monkeypatch):
    from app.backends.delivery.client import DeliveryToolClient

    cli = DeliveryToolClient(offline=True, device="cpu", use_conda=False)

    def _fake_import(name, payload):
        return {"ok": True, "score": 0.77, "predictions": []}

    monkeypatch.setattr(cli, "_call_import", _fake_import)
    monkeypatch.setattr(cli, "prefer_import", True)
    import app.backends.delivery.client as client_mod

    monkeypatch.setattr(
        client_mod,
        "PURE_PYTHON_TOOLS",
        set(getattr(client_mod, "PURE_PYTHON_TOOLS", set())) | {"similarity_weighted_vote"},
    )
    out = cli.call(
        "similarity_weighted_vote",
        {
            "predictions": [{"donor": "FMR1", "prob": 0.8}],
            "hits": [{"alias": "FMR1", "score": 0.9}],
        },
    )
    assert out.get("drives_p_hat") is None
    assert out.get("role") is None


def test_fuse_zeros_rna_peak_without_peaks_db(monkeypatch):
    from app.core import capability_matrix as cm
    from rbp_eval.scoring.fuse_hits import fuse_rbp_hits

    monkeypatch.setattr(
        cm,
        "rna_blastn_status",
        lambda: {"status": "degraded", "tool": "rna_blastn"},
    )
    hits = [
        [
            {
                "alias": "A",
                "score": 0.9,
                "metric": "rna_peak_homology",
            },
            {
                "alias": "B",
                "score": 0.8,
                "metric": "domain_overlap",
            },
        ]
    ]
    donors = fuse_rbp_hits(
        hits,
        weights={"rna_peak_homology": 10.0, "domain_overlap": 1.0},
        top_k=2,
        use_rank_normalize=False,
        cross_metric_normalize=False,
    )
    assert donors


def test_skill_documents_delivery_p_hat_formula():
    skill = (ROOT / "nanobot" / "skills" / "rbp-agent" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    assert "similarity_weighted_vote" in skill
    assert "transfer_prior" in skill or "donor_quality" in skill


def test_aggregate_p_hat_matches_similarity_only_vote():
    from rbp_eval.scoring.fuse_hits import aggregate_p_hat

    out = aggregate_p_hat(
        [{"rbp_id": "X", "similarity_score": 0.5}],
        [{"alias": "X", "prob": 0.8}],
    )
    assert out["p_hat"] == 0.8


def test_product_verdict_rejects_llm_supplied_p_hat():
    from app.core.verdict_schema import normalize_verdict_with_turn_state
    from nanobot.agent.tools.rbp.turn_guards import reset_stage_guards

    reset_stage_guards()
    out = normalize_verdict_with_turn_state(
        {
            "label": "Strong",
            "p_hat": 0.999,
            "confidence": "high",
            "explanation": "LLM guess",
            "supporting_rbps": [],
        }
    )
    assert out["p_hat"] is None
    assert out["label"] == "No"
    assert out["confidence"] == "low"
    assert out["score_source"] == "unavailable"


def test_product_verdict_uses_tool_authority_and_evidence_confidence():
    from app.core.verdict_schema import normalize_verdict_with_turn_state
    from nanobot.agent.tools.rbp.turn_guards import (
        reset_stage_guards,
        set_authoritative_score,
    )

    reset_stage_guards()
    set_authoritative_score(
        0.42,
        source="delivery_similarity_weighted_vote",
        mode="multi_head",
        provenance={
            "predictions": [
                {"alias": "A", "prob": 0.9},
                {"alias": "B", "prob": 0.2},
                {"alias": "C", "prob": 0.4},
            ],
            "aggregation": {
                "terms": [{"donor": x} for x in ("A", "B", "C")],
                "n_transfer_priors": 3,
                "n_donor_quality": 3,
            },
        },
    )
    out = normalize_verdict_with_turn_state(
        {
            "p_hat": 0.99,
            "confidence": "low",
            "explanation": "Tool-grounded explanation.",
            "supporting_rbps": [],
        }
    )
    assert out["p_hat"] == 0.42
    assert out["score_source"] == "delivery_similarity_weighted_vote"
    assert out["confidence"] == "medium"


def test_product_verdict_forces_low_on_deterministic_ood_flag():
    from app.core.verdict_schema import normalize_verdict_with_turn_state
    from nanobot.agent.tools.rbp.turn_guards import (
        add_evidence_flag,
        reset_stage_guards,
        set_authoritative_score,
    )

    reset_stage_guards()
    set_authoritative_score(
        0.91,
        source="delivery_similarity_weighted_vote",
        mode="multi_head",
        provenance={
            "predictions": [{"alias": "A", "prob": 0.91}],
            "aggregation": {
                "terms": [{"donor": "A"}],
                "n_transfer_priors": 1,
                "n_donor_quality": 1,
            },
        },
    )
    add_evidence_flag("ood", True)
    add_evidence_flag("selective_abstain", True)
    out = normalize_verdict_with_turn_state(
        {
            "confidence": "high",
            "explanation": "The deterministic scorer ran outside support.",
            "supporting_rbps": [],
        }
    )
    assert out["p_hat"] == 0.91
    assert out["confidence"] == "low"
    assert out["abstain"]["confident"] is False
    assert {"ood", "selective_abstain"} <= set(out["caveats"])


def test_confidence_abstain_output_sets_ood_turn_evidence():
    from app.backends.delivery.registry import DeliveryBackedTool
    from nanobot.agent.tools.rbp.turn_guards import (
        evidence_flags,
        reset_stage_guards,
        set_committed_proxies,
    )

    class Client:
        def call(self, name, payload):
            assert name == "confidence_abstain"
            return {
                "ok": True,
                "confident": False,
                "max_similarity": 0.12,
                "_script": "/missing/test.py",
                "_invocation": "test",
                "_args_hash": "abc",
            }

    reset_stage_guards()
    set_committed_proxies([{"alias": "A", "similarity_score": 0.12}])
    tool = DeliveryBackedTool(
        tool_name="confidence_abstain",
        description="test",
        parameters={"type": "object", "properties": {}},
        client=Client(),
    )
    result = json.loads(asyncio.run(tool.execute(hits=[{"alias": "A", "score": 0.12}])))
    assert result["status"] == "ok"
    flags = evidence_flags()
    assert flags["ood_assessed"] is True
    assert flags["ood"] is True
    assert flags["selective_abstain"] is True
