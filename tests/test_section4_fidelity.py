# -*- coding: utf-8 -*-
"""Proposal §4 fidelity: commit_proxy_candidates + weighted aggregation."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_proposal_breakdown_maps_metrics():
    from rbp_eval.scoring.fuse_hits import proposal_breakdown

    br = proposal_breakdown(
        {"esmc_cosine": 0.9, "tm_score": 0.7, "domain_jaccard": 0.5, "noise": 0.1}
    )
    assert br["seq"] == 0.9
    assert br["struct"] == 0.7
    assert br["func"] == 0.5


def test_aggregate_probability_weighted_mean():
    from rbp_eval.scoring.fuse_hits import aggregate_probability

    out = aggregate_probability(
        [
            {"rbp_id": "A", "similarity_score": 1.0},
            {"rbp_id": "B", "similarity_score": 0.5},
        ],
        [
            {"alias": "A", "prob": 0.8},
            {"alias": "B", "prob": 0.2},
        ],
    )
    # (1.0*0.8 + 0.5*0.2) / (1.0+0.5) = 0.9/1.5 = 0.6
    assert abs(out["p_hat"] - 0.6) < 1e-6
    assert len(out["terms"]) == 2
    assert out["formula"] == "delivery_similarity_weighted_vote"


def test_aggregate_p_hat_with_transfer_and_quality():
    from rbp_eval.scoring.fuse_hits import aggregate_p_hat

    out = aggregate_p_hat(
        [
            {"rbp_id": "A", "similarity_score": 0.9},
            {"rbp_id": "B", "similarity_score": 0.5},
        ],
        [
            {"alias": "A", "prob": 0.8},
            {"alias": "B", "prob": 0.2},
        ],
        transfer_priors={"A": 0.5},
        donor_quality={"B": 0.5},
    )
    # A: w=0.9*0.5=0.45, B: w=0.5*0.5=0.25 -> p_hat=(0.36+0.05)/0.7
    assert out["p_hat"] == 0.5857


def test_aggregate_p_hat_contract_matches_delivery_vote():
    """Agent compatibility helper must numerically match immutable delivery."""
    import importlib.util

    from rbp_eval.scoring.fuse_hits import aggregate_p_hat

    delivery_script = (
        ROOT.parent
        / "rhobind_agent_delivery"
        / "agent"
        / "tools"
        / "integrate"
        / "similarity_weighted_vote.py"
    )
    spec = importlib.util.spec_from_file_location("delivery_similarity_weighted_vote", delivery_script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    proxies = [
        {"rbp_id": "A", "alias": "A", "similarity_score": 0.91321},
        {"rbp_id": "B", "alias": "B", "similarity_score": 0.51234},
    ]
    predictions = [{"alias": "A", "prob": 0.812345}, {"alias": "B", "prob": 0.234567}]
    transfer = {"A": 0.61}
    quality = {"A": 0.73, "B": 0.57}
    agent = aggregate_p_hat(
        proxies,
        predictions,
        transfer_priors=transfer,
        donor_quality=quality,
    )
    delivery = module.run(
        {
            "predictions": [
                {"donor": row["alias"], "prob": row["prob"]} for row in predictions
            ],
            "hits": [
                {"alias": row["alias"], "score": row["similarity_score"]}
                for row in proxies
            ],
            "transfer_priors": transfer,
            "donor_quality": quality,
        }
    )
    assert agent["p_hat"] == delivery["score"]


def test_commit_proxy_candidates_and_gate():
    import importlib.util

    path = ROOT / "nanobot" / "agent" / "tools" / "rbp" / "turn_guards.py"
    spec = importlib.util.spec_from_file_location("tg_commit", path)
    assert spec and spec.loader
    tg = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tg)

    tg.reset_stage_guards()
    assert tg.commit_blocked_reason() and "fuse" in tg.commit_blocked_reason().lower()
    tg.mark_fuse_done()
    assert tg.commit_blocked_reason() is None

    tg.set_committed_proxies(
        [
            {
                "rbp_id": "PTBP1",
                "alias": "PTBP1",
                "similarity_score": 0.8,
                "similarity_breakdown": {"seq": 0.9},
                "rationale": "test",
            }
        ]
    )
    assert tg.commit_done()
    assert tg.committed_proxies()[0]["similarity_score"] == 0.8


def test_commit_tool_filters_tau_and_persists():
    from nanobot.agent.tools.rbp.commit_proxies import CommitProxyCandidatesTool
    from nanobot.agent.tools.rbp.turn_guards import (
        committed_proxies,
        reset_stage_guards,
        set_fused_proxies,
    )

    reset_stage_guards()
    candidates = [
        {
            "rbp_id": "U2AF2",
            "similarity_score": 0.9,
            "similarity_breakdown": {"seq": 0.9, "struct": 0.5, "func": 0.7},
            "rationale": "high",
        },
        {
            "rbp_id": "MATR3",
            "similarity_score": 0.1,
            "similarity_breakdown": {"seq": 0.1},
            "rationale": "low",
        },
    ]
    set_fused_proxies(candidates)
    tool = CommitProxyCandidatesTool()
    raw = asyncio.run(
        tool.execute(
            candidates=[
                {"rbp_id": "U2AF2"},
                {"rbp_id": "MATR3", "similarity_score": 1.0},
            ],
            tau_drop=0.30,
            n_cand=5,
        )
    )
    obj = json.loads(raw)
    assert obj["status"] == "ok"
    assert obj["value"]["n"] == 1
    assert committed_proxies()[0]["rbp_id"] == "U2AF2"


def test_commit_accepts_fuse_score_shaped_donors():
    """Live bug: fuse_rbp_hits emits ``score``, commit required similarity_score."""
    from nanobot.agent.tools.rbp.commit_proxies import CommitProxyCandidatesTool
    from nanobot.agent.tools.rbp.turn_guards import (
        committed_proxies,
        fused_proxies,
        reset_stage_guards,
        set_fused_proxies,
    )

    reset_stage_guards()
    # Exact shape returned by fuse_rbp_hits / fuse_similarity_views tool.
    fuse_donors = [
        {
            "alias": "U2AF2",
            "uniprot": "P26368",
            "score": 1.0,
            "metric": "fused",
            "rank": 1,
            "sim_by_modality": {"esmc_cosine": 0.9635},
            "similarity_breakdown": {"seq": 0.9635},
        },
        {
            "alias": "MATR3",
            "uniprot": "P43243",
            "score": 0.85,
            "metric": "fused",
            "rank": 2,
            "similarity_breakdown": {"seq": 0.85},
        },
        {
            "alias": "TAF15",
            "uniprot": "Q92804",
            "score": 0.7,
            "metric": "fused",
            "rank": 3,
            "similarity_breakdown": {"seq": 0.7},
        },
    ]
    set_fused_proxies(fuse_donors)
    stored = fused_proxies()
    assert stored[0]["fused_score"] == 1.0
    assert stored[0]["similarity_score"] == 0.9635
    assert stored[0]["rbp_id"] == "U2AF2"

    tool = CommitProxyCandidatesTool()
    # Selection-only payload (as the LLM should send after the refactor).
    raw = asyncio.run(
        tool.execute(
            candidates=[
                {"rbp_id": "MATR3", "uniprot": "P43243"},
                {"alias": "TAF15", "similarity_score": 1.0},  # LLM score ignored
            ],
            tau_drop=0.30,
            n_cand=5,
        )
    )
    obj = json.loads(raw)
    assert obj["status"] == "ok", obj
    assert obj["value"]["n"] == 3
    kept = committed_proxies()
    assert {c["alias"] for c in kept} == {"U2AF2", "MATR3", "TAF15"}
    # ESM top neighbour is automatically retained even when the LLM omits it.
    u2af2 = next(c for c in kept if c["alias"] == "U2AF2")
    assert u2af2["similarity_score"] == 0.9635
    assert u2af2["fused_score"] == 1.0
    # LLM-supplied 1.0 for TAF15 must not override fused 0.7
    taf15 = next(c for c in kept if c["alias"] == "TAF15")
    assert taf15["similarity_score"] == 0.7


def test_commit_reports_unknown_ids_not_tau_drop():
    from nanobot.agent.tools.rbp.commit_proxies import CommitProxyCandidatesTool
    from nanobot.agent.tools.rbp.turn_guards import reset_stage_guards, set_fused_proxies

    reset_stage_guards()
    set_fused_proxies(
        [{"alias": "U2AF2", "score": 1.0, "similarity_breakdown": {"seq": 1.0}}]
    )
    tool = CommitProxyCandidatesTool()
    raw = asyncio.run(
        tool.execute(candidates=[{"alias": "NOPE"}], tau_drop=0.0)
    )
    obj = json.loads(raw)
    assert obj["status"] == "error"
    reason = obj.get("reason") or obj.get("error") or ""
    assert "not found in fused store" in reason
    assert "τ_drop" not in reason


def test_defaults_section4_weighted_and_af3():
    import yaml

    cfg = yaml.safe_load((ROOT / "config" / "defaults.yaml").read_text(encoding="utf-8"))
    assert cfg["predict"]["aggregate"] == "weighted"
    assert cfg["axes"]["use_af3"] is True
    assert cfg["structure_policy"]["use_af3_fallback"] is True


def test_commit_proxy_tool_registered():
    from app.backends.delivery.registry import build_proposal_tools

    names = {t.name for t in build_proposal_tools()}
    assert "commit_proxy_candidates" in names
