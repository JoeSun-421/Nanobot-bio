# -*- coding: utf-8 -*-
"""Unit tests for Stage 0–3 turn guards (BUILD_SPEC fuse → abstain → predict)."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_transfer_predict_requires_fuse_commit_then_abstain(monkeypatch):
    # Load SoT module directly (overlay may not be synced yet).
    import importlib.util

    path = ROOT / "nanobot" / "agent" / "tools" / "rbp" / "turn_guards.py"
    spec = importlib.util.spec_from_file_location("turn_guards_sot", path)
    assert spec and spec.loader
    tg = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tg)

    tg.reset_stage_guards()
    monkeypatch.setattr(tg, "alias_has_panel_head", lambda *a, **k: False)

    reason = tg.transfer_predict_blocked_reason(
        force_transfer=True, rbps=["FUS"], cohort="K562"
    )
    assert reason and "fuse_similarity_views" in reason

    tg.mark_fuse_done()
    reason = tg.transfer_predict_blocked_reason(
        force_transfer=True, rbps=["FUS"], cohort="K562"
    )
    assert reason and "commit_proxy_candidates" in reason

    tg.set_committed_proxies(
        [
            {
                "rbp_id": "FUS",
                "alias": "FUS",
                "similarity_score": 0.8,
                "similarity_breakdown": {"seq": 0.8},
                "rationale": "test",
            }
        ]
    )
    reason = tg.transfer_predict_blocked_reason(
        force_transfer=True, rbps=["FUS"], cohort="K562"
    )
    assert reason and "confidence_abstain" in reason

    tg.mark_abstain_done()
    assert (
        tg.transfer_predict_blocked_reason(
            force_transfer=True, rbps=["FUS"], cohort="K562"
        )
        is None
    )


def test_abstain_requires_commit_after_fuse():
    import importlib.util

    path = ROOT / "nanobot" / "agent" / "tools" / "rbp" / "turn_guards.py"
    spec = importlib.util.spec_from_file_location("turn_guards_sot2", path)
    assert spec and spec.loader
    tg = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tg)

    tg.reset_stage_guards()
    reason = tg.abstain_blocked_reason()
    assert reason and "commit_proxy_candidates" in reason
    tg.mark_fuse_done()
    reason = tg.abstain_blocked_reason()
    assert reason and "commit_proxy_candidates" in reason
    tg.set_committed_proxies(
        [
            {
                "rbp_id": "X",
                "alias": "X",
                "similarity_score": 0.5,
                "similarity_breakdown": {},
                "rationale": "t",
            }
        ]
    )
    assert tg.abstain_blocked_reason() is None


def test_own_head_single_alias_skips_abstain_gate(monkeypatch):
    import importlib.util

    path = ROOT / "nanobot" / "agent" / "tools" / "rbp" / "turn_guards.py"
    spec = importlib.util.spec_from_file_location("turn_guards_sot3", path)
    assert spec and spec.loader
    tg = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tg)

    tg.reset_stage_guards()
    monkeypatch.setattr(tg, "alias_has_panel_head", lambda *a, **k: True)
    assert (
        tg.transfer_predict_blocked_reason(
            force_transfer=False, rbps=["PTBP1"], cohort="K562"
        )
        is None
    )


def test_user_message_loo_seeds_sticky_flag():
    from nanobot.agent.tools.rbp.turn_guards import (
        reset_stage_guards,
        seed_loo_force_transfer_from_user_message,
        force_transfer_active,
        evidence_flags,
    )

    reset_stage_guards()
    assert seed_loo_force_transfer_from_user_message(
        "Please run leave-one-out on DROSHA; force transfer, no own-head"
    )
    assert force_transfer_active() is True
    assert evidence_flags().get("loo_force_transfer") is True
    assert evidence_flags().get("loo_force_transfer_source") == "user_message"


def test_fuse_tool_hard_blocks_without_retrieve():
    from nanobot.agent.tools.rbp.evolve_tools import FuseSimilarityViewsTool
    from nanobot.agent.tools.rbp.turn_guards import reset_stage_guards

    reset_stage_guards()
    result = json.loads(
        asyncio.run(
            FuseSimilarityViewsTool().execute(
                hits=[[{"alias": "PTBP1", "score": 0.8}]]
            )
        )
    )
    assert result["status"] == "error"
    assert "retrieve tool" in result["reason"]


def test_commit_loo_emits_near_match_loo_disclosed_not_no_head():
    """LOO / force_transfer must not emit misleading near_match_donor_no_head."""
    from nanobot.agent.tools.rbp.commit_proxies import CommitProxyCandidatesTool
    from nanobot.agent.tools.rbp.turn_guards import (
        add_evidence_flag,
        evidence_flags,
        reset_stage_guards,
        set_fused_proxies,
    )

    reset_stage_guards()
    set_fused_proxies(
        [
            {
                "alias": "DROSHA",
                "score": 1.0,
                "vote_similarity": 1.0,
                "sim_by_modality": {"esmc_cosine": 1.0},
            },
            {
                "alias": "DGCR8",
                "score": 0.88,
                "vote_similarity": 0.92,
                "sim_by_modality": {"esmc_cosine": 0.92},
            },
        ]
    )
    add_evidence_flag("near_match", True)
    add_evidence_flag("near_match_donor", "DROSHA")
    raw = json.loads(
        asyncio.run(
            CommitProxyCandidatesTool().execute(
                candidates=[{"alias": "DGCR8"}],
                tau_drop=0.30,
                n_cand=5,
                force_transfer=True,
            )
        )
    )
    assert raw["status"] == "ok"
    flags = evidence_flags() or {}
    assert flags.get("near_match_loo_disclosed") is True
    assert "near_match_donor_no_head" not in flags


def test_loo_path_contract_assertions_documented():
    """Contract checklist for future accept-llm LOO (no GPU/API)."""
    from nanobot.agent.tools.rbp.turn_guards import (
        force_transfer_active,
        reset_stage_guards,
        seed_loo_force_transfer_from_user_message,
        transfer_predict_blocked_reason,
    )

    reset_stage_guards()
    assert seed_loo_force_transfer_from_user_message(
        "LOO leave-one-out force_transfer=true treat as unseen"
    )
    assert force_transfer_active() is True
    # Own-head on the query alone must stay refused under sticky LOO.
    reason = transfer_predict_blocked_reason(
        force_transfer=False, rbps=["DROSHA"], cohort="K562"
    )
    # Either own-head refuse or stage-order block — never a silent own-head pass.
    assert reason is not None
