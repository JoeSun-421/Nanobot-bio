# -*- coding: utf-8 -*-
"""Proposal / delivery-contract compliance tests (agent-side only)."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_tau_drop_filters_low_similarity():
    from rbp_eval.scoring.fuse_hits import fuse_rbp_hits

    hits = [
        [
            {"alias": "A", "score": 0.9, "metric": "esmc_cosine", "rank": 1},
            {"alias": "B", "score": 0.2, "metric": "esmc_cosine", "rank": 2},
            {"alias": "C", "score": 0.35, "metric": "esmc_cosine", "rank": 3},
        ]
    ]
    donors = fuse_rbp_hits(hits, top_k=5, tau_drop=0.30, use_rank_normalize=False)
    aliases = {d["alias"] for d in donors}
    assert "A" in aliases
    assert "B" not in aliases
    assert "C" in aliases
    assert len(donors) <= 5


def test_percent_identity_normalized_before_clamp():
    from rbp_eval.scoring.fuse_hits import fuse_rbp_hits

    donors = fuse_rbp_hits(
        [
            [
                {
                    "alias": "PTBP1",
                    "score": 97.0,
                    "metric": "seq_identity",
                    "rank": 1,
                }
            ]
        ],
        top_k=1,
        use_rank_normalize=False,
    )
    assert donors
    # 97% → 0.97, not clamped to 1.0 via raw>1 then min(1,97)
    assert abs(donors[0]["sim_by_modality"]["seq_identity"] - 0.97) < 1e-6


def test_cross_metric_normalization_equalizes_scales():
    """Delivery §9: different metrics live on different scales, so raw fusion is
    skewed toward the metric with the larger raw spread. Min–max cross-metric
    scaling equalizes each metric's contribution before the weighted combine.

    Here A barely leads on the narrow esmc_cosine metric while B leads by a wide
    margin on tm_score. Raw fusion lets tm_score's large spread dominate (B wins
    decisively); equalized fusion puts both metrics on a common [0,1] spread so
    the two candidates end up ~tied."""
    from rbp_eval.scoring.fuse_hits import fuse_rbp_hits

    hits = [
        [
            {"alias": "A", "score": 0.92, "metric": "esmc_cosine"},
            {"alias": "B", "score": 0.90, "metric": "esmc_cosine"},
        ],
        [
            {"alias": "A", "score": 0.30, "metric": "tm_score"},
            {"alias": "B", "score": 0.85, "metric": "tm_score"},
        ],
    ]
    w = {"esmc_cosine": 1.0, "tm_score": 1.0}

    raw = fuse_rbp_hits(
        hits, top_k=2, weights=w, use_rank_normalize=False,
        cross_metric_normalize=False,
    )
    raw_by = {d["alias"]: d["score"] for d in raw}
    # Raw: tm_score's wide spread dominates → B far ahead of A.
    assert raw[0]["alias"] == "B"
    assert raw_by["B"] - raw_by["A"] > 0.2

    norm = fuse_rbp_hits(
        hits, top_k=2, weights=w, use_rank_normalize=False,
        cross_metric_normalize=True,
    )
    norm_by = {d["alias"]: d["score"] for d in norm}
    # Equalized: neither metric's scale dominates → the two are ~tied.
    assert abs(norm_by["A"] - norm_by["B"]) < 0.01
    # Raw similarity values are still preserved for display/evidence.
    assert {d["alias"]: d["sim_by_modality"]["tm_score"] for d in norm} == {
        "A": 0.3,
        "B": 0.85,
    }


def test_cross_metric_normalize_noop_for_single_metric():
    """Single-metric fusion has nothing to cross-normalize → raw scale kept, so
    tau_drop still filters on the native similarity value."""
    from rbp_eval.scoring.fuse_hits import fuse_rbp_hits

    hits = [
        [
            {"alias": "A", "score": 0.9, "metric": "esmc_cosine"},
            {"alias": "B", "score": 0.2, "metric": "esmc_cosine"},
            {"alias": "C", "score": 0.35, "metric": "esmc_cosine"},
        ]
    ]
    donors = fuse_rbp_hits(
        hits, top_k=5, tau_drop=0.30, use_rank_normalize=False,
        cross_metric_normalize=True,
    )
    aliases = {d["alias"] for d in donors}
    assert aliases == {"A", "C"}  # B below 0.30, C (0.35) survives on raw scale


def test_sparse_single_axis_hit_cannot_outrank_esmc_neighbour():
    """A weak per-axis leader must not become a synthetic 1.0 donor."""
    from rbp_eval.scoring.fuse_hits import fuse_rbp_hits

    donors = fuse_rbp_hits(
        [
            [
                {"alias": "U2AF2", "score": 0.9635, "metric": "esmc_cosine"},
                {"alias": "QKI", "score": 0.91, "metric": "esmc_cosine"},
            ],
            [{"alias": "MATR3", "score": 0.354, "metric": "seq_identity"}],
            [{"alias": "SF3B4", "score": 0.82, "metric": "domain_overlap"}],
        ],
        top_k=5,
    )
    by_alias = {row["alias"]: row for row in donors}
    assert donors[0]["alias"] == "U2AF2"
    assert "U2AF2" in by_alias
    assert by_alias["U2AF2"]["vote_similarity"] == 0.9635
    assert by_alias["MATR3"]["score"] < by_alias["U2AF2"]["score"]
    assert by_alias["MATR3"]["vote_similarity"] < 0.1
    assert by_alias["MATR3"]["sim_by_modality"]["seq_identity"] == 0.354


def test_fuse_proxy_candidates_respects_tau_and_ncand():
    from rbp_eval.scoring.fuse_hits import fuse_proxy_candidates

    fused = fuse_proxy_candidates(
        {
            "seq": [
                {"alias": "A", "score": 0.9},
                {"alias": "B", "score": 0.1},
            ],
            "struct": [{"alias": "A", "score": 0.8}],
            "func": [{"alias": "A", "score": 0.7}, {"alias": "C", "score": 0.95}],
        },
        n_cand=5,
        tau_drop=0.30,
    )
    ids = {p["rbp_id"] for p in fused}
    assert "A" in ids
    assert "B" not in ids
    assert "C" in ids
    assert len(fused) <= 5
    for p in fused:
        assert "similarity_score" in p
        assert "similarity_breakdown" in p
        assert "rationale" in p
        assert p["similarity_score"] >= 0.30


def test_label_thresholds_proposal():
    from app.core.verdict_schema import label_from_p_hat

    assert label_from_p_hat(0.80) == "Strong"
    assert label_from_p_hat(0.60) == "Likely"
    assert label_from_p_hat(0.30) == "Unlikely"
    assert label_from_p_hat(0.10) == "No"


def test_stage3_verdict_from_llm_json():
    """LLM touchpoints live in Nanobot+SKILL; verdict parse is still core."""
    from app.core.verdict_schema import extract_verdict_from_content

    content = json.dumps(
        {
            "label": "Likely",
            "p_hat": 0.85,
            "confidence": "medium",
            "explanation": "Proxy A is similar and predicts binding.",
            "supporting_rbps": [{"rbp_id": "P09651", "alias": "HNRNPA1", "prob": 0.9}],
        }
    )
    v = extract_verdict_from_content(content)
    assert v["label"] == "Likely"
    assert v["p_hat"] == 0.85
    assert "Proxy A" in v["explanation"]


def test_stage1_deterministic_fusion_in_rbp_eval():
    from rbp_eval.scoring.fuse_hits import fuse_proxy_candidates

    proxies = fuse_proxy_candidates(
        {
            "seq": [{"alias": "ELAVL1", "score": 0.9}],
            "func": [{"alias": "ELAVL1", "score": 0.8}],
        },
        n_cand=5,
        tau_drop=0.30,
    )
    assert proxies
    assert proxies[0]["rbp_id"] == "ELAVL1"
    assert proxies[0]["similarity_score"] >= 0.30


def test_defaults_match_proposal():
    import yaml

    cfg = yaml.safe_load((ROOT / "config" / "defaults.yaml").read_text(encoding="utf-8"))
    assert float(cfg["tau_drop"]) == 0.30
    assert int(cfg["n_cand"]) == 5
    assert float(cfg["near_match_seq_identity"]) == 0.95
    thr = cfg["label_thresholds"]
    assert thr["strong"] == 0.75
    assert thr["likely"] == 0.50
    assert thr["unlikely"] == 0.25
    assert cfg["llm"]["stage1_function_reasoning"] is True
    assert cfg["llm"]["stage3_explanation"] is True
    assert cfg["predict"]["aggregate"] == "weighted"
    assert cfg["axes"]["use_af3"] is True
    assert cfg["structure_policy"]["use_af3_fallback"] is True


def test_proposal_tool_names_registered():
    """P0–P2 tools come from nanobot.agent.tools.rbp (single source of truth)."""
    from app.backends.delivery.client import SCRIPT_MAP
    from app.backends.delivery.registry import STAGE_RAW_WHITELIST, build_proposal_tools

    tools = build_proposal_tools()
    names = {t.name for t in tools}
    for required in (
        "predict_interaction",
        "get_known_rbp_list",
        "seq_similarity",
        "struct_similarity",
        "get_func_annotation",
        "predict_structure",
        "literature_search",
        "lookup_proxy_cache",
        "fuse_similarity_views",
        "commit_proxy_candidates",
    ):
        assert required in names, f"missing curated tool {required}"
    assert "rna_blastn" in STAGE_RAW_WHITELIST
    assert "rna_blastn" in SCRIPT_MAP
    assert "rna_similarity" not in STAGE_RAW_WHITELIST
    # Tools are the rbp package classes, not a second wrapper stack
    assert any("nanobot.agent.tools.rbp" in type(t).__module__ for t in tools)
    assert "literature_retrieval" not in STAGE_RAW_WHITELIST
    assert "resolve_rbp" in STAGE_RAW_WHITELIST


@pytest.mark.requires_delivery
def test_delivery_tree_untouched_marker():
    """Sanity: delivery package exists; science calls go through DeliveryToolClient."""
    delivery = ROOT.parent / "rhobind_agent_delivery"
    assert delivery.is_dir()
    client_src = (
        ROOT / "app" / "backends" / "delivery" / "client.py"
    ).read_text(encoding="utf-8")
    assert "DeliveryToolClient" in client_src


def test_near_match_threshold():
    from app.core.verdict_schema import is_near_match_score

    assert is_near_match_score(0.95) is True
    assert is_near_match_score(0.94) is False


def test_near_known_exact_resolve_bypasses_masked_mmseqs(monkeypatch):
    from nanobot.agent.tools.rbp import near_known
    from nanobot.agent.tools.rbp.near_known import CheckNearKnownTool
    from nanobot.agent.tools.rbp import turn_guards

    turn_guards.reset_stage_guards()
    turn_guards.set_canonical_request(
        {
            "alias": "PTBP1",
            "uniprot": "P26599",
            "cohort": "K562",
            "input_provenance": {
                "resolved": True,
                "in_panel": True,
                "query": "P26599",
            },
        }
    )
    monkeypatch.setattr(
        turn_guards,
        "alias_has_panel_head",
        lambda _q, **_kwargs: True,
    )
    monkeypatch.setattr(
        near_known,
        "get_delivery_client",
        lambda: (_ for _ in ()).throw(AssertionError("MMseqs must not run")),
    )
    raw = asyncio.run(
        CheckNearKnownTool().execute(sequence="MKWVTFISLLLLFSSAYSRGVFRR")
    )
    obj = json.loads(raw)
    assert obj["status"] == "ok"
    assert obj["value"]["near_match"] is True
    assert obj["value"]["match_basis"] == "resolve_exact_catalogue_identifier"
    assert obj["value"]["best_identity"] is None
    assert turn_guards.evidence_flags()["near_match"] is True


def test_near_known_exact_catalogue_sequence_bypasses_masked_mmseqs(monkeypatch):
    """Anonymous exact catalogue AA paste must near-match even if MMseqs under-reports."""
    from nanobot.agent.tools.rbp import near_known
    from nanobot.agent.tools.rbp.near_known import CheckNearKnownTool
    from nanobot.agent.tools.rbp import turn_guards

    # Simulate low-complexity self-hit: MMseqs would return ~0.93, but exact
    # FASTA equality still claims the headed catalogue donor.
    seq = "M" + ("A" * 40) + "K" + ("G" * 40)  # dummy AA; lookup is mocked
    turn_guards.reset_stage_guards()
    monkeypatch.setattr(
        turn_guards,
        "alias_has_panel_head",
        lambda q, cohort="K562": str(q).casefold() == "ptbp1",
    )
    monkeypatch.setattr(
        near_known,
        "find_exact_catalogue_entry",
        lambda _s: {"alias": "PTBP1", "uniprot": "P26599"},
    )
    monkeypatch.setattr(
        near_known,
        "get_delivery_client",
        lambda: (_ for _ in ()).throw(AssertionError("MMseqs must not run")),
    )
    raw = asyncio.run(CheckNearKnownTool().execute(sequence=seq))
    obj = json.loads(raw)
    assert obj["status"] == "ok"
    assert obj["value"]["near_match"] is True
    assert obj["value"]["donor_alias"] == "PTBP1"
    assert obj["value"]["match_basis"] == "exact_catalogue_sequence"
    assert obj["value"]["best_identity"] == 1.0
    assert turn_guards.evidence_flags()["near_match"] is True
    assert turn_guards.evidence_flags()["near_match_donor"] == "PTBP1"


def test_stage1_before_predict_in_skill_playbook():
    """Regression: SKILL playbook orders Stage 1 retrieval before Stage 2 predict."""
    skill = ROOT / "nanobot" / "skills" / "rbp-agent" / "SKILL.md"
    src = skill.read_text(encoding="utf-8")
    i_s0 = src.find("Stage 0")
    i_s1 = src.find("Stage 1")
    i_s2 = src.find("Stage 2")
    assert i_s0 > 0 and i_s1 > 0 and i_s2 > 0
    assert i_s0 < i_s1 < i_s2
    assert "Retrieve" in src[i_s1 : i_s1 + 120] or "retrieve" in src[i_s1 : i_s1 + 120].lower()
    assert "Predict" in src[i_s2 : i_s2 + 120] or "predict" in src[i_s2 : i_s2 + 80].lower()

def test_mvp_tool_whitelist_excludes_literature_raw():
    from nanobot.agent.tools.core.registry import ToolRegistry
    from nanobot.agent.tools.rbp.register import register_rbp_tools

    _reg, names = register_rbp_tools(ToolRegistry(), include_raw_delivery="whitelist")
    assert "literature_retrieval" not in names
    assert "resolve_rbp" in names
    assert "predict_interaction" in names
    # Curated P0–P2 + Stage 0/3 whitelist (count drifts with registry; keep bounded)
    assert 15 <= len(names) <= 40


def test_skill_playbook_locks_proposal_defaults_and_paths():
    """Proposal §4 / §8 + gate: SKILL must encode near-known, tau, N_cand, stages, caveats."""
    skill = ROOT / "nanobot" / "skills" / "rbp-agent" / "SKILL.md"
    src = skill.read_text(encoding="utf-8")
    assert "near-known" in src
    assert "0.30" in src or "0.3" in src
    assert "N_cand" in src or "n_cand" in src.lower()
    assert "Stage 3" in src
    assert "caveat" in src.lower()
    # Unseen path: retrieve before predict; own-head stops without transfer
    assert "in_panel=true" in src or "Own-head" in src or "own-head" in src
    assert "Stage 1" in src and "Stage 2" in src
    for key in ("label", "p_hat", "confidence", "explanation", "supporting_rbps"):
        assert key in src, f"verdict field {key} missing from SKILL"
    # Literature soft-fail is caveat-only (must not deduct confidence / checklist).
    assert "literature_unavailable" in src
    assert "caveat only" in src.lower() or "does **not** count as a checklist failure" in src


def test_similarity_breakdown_in_fuse_and_verdict_supports_caveats():
    """Proposal §4 proxy object + IR caveats field."""
    from rbp_eval.scoring.fuse_hits import fuse_proxy_candidates
    from app.core.verdict_schema import normalize_verdict

    proxies = fuse_proxy_candidates(
        {"seq": [{"alias": "ELAVL1", "score": 0.9}]},
        n_cand=5,
        tau_drop=0.30,
    )
    assert proxies and "similarity_breakdown" in proxies[0]

    v = normalize_verdict(
        {
            "label": "Likely",
            "p_hat": 0.6,
            "confidence": 0.7,
            "explanation": "Grounded on tool scores only.",
            "supporting_rbps": [],
            "caveats": ["structure_axis unavailable"],
        }
    )
    assert v.get("caveats") == ["structure_axis unavailable"]
    assert isinstance(v.get("confidence"), (int, float, str))


def test_proposal_sot_tool_modules_exist_at_transition_path():
    """SoT is repo-root nanobot/agent/tools/rbp/ (nanobot-like overlay)."""
    sot = ROOT / "nanobot" / "agent" / "tools" / "rbp"
    for name in (
        "predict.py",
        "catalogue.py",
        "seq.py",
        "structure.py",
        "annotation.py",
        "common.py",
    ):
        assert (sot / name).is_file(), f"missing SoT module {name}"
    assert (ROOT / "nanobot" / "skills" / "rbp-agent" / "SKILL.md").is_file()


def test_proposal_documents_present():
    """docs/ is local-only (gitignored); skip when absent (e.g. fresh clone / CI)."""
    guide_path = ROOT / "docs" / "工程指南.zh.md"
    if not guide_path.is_file():
        return
    guide = guide_path.read_text(encoding="utf-8")
    assert "## 9. 改动门禁" in guide
    assert "Proposal" in guide or "提案" in guide
    assert (ROOT / "docs" / "proposal.md").is_file()
    assert (ROOT / "docs" / "proposal.zh.md").is_file()
    assert (ROOT / "docs" / "remediation-checklist.md").is_file()


def test_evolved_live_requires_decision_artifact_when_present():
    """If live evolved.yaml claims evolved:true, prefer an evolve-eval decision note when it exists."""
    import yaml

    evolved = ROOT / "config" / "evolved.yaml"
    if not evolved.is_file():
        return
    cfg = yaml.safe_load(evolved.read_text(encoding="utf-8")) or {}
    if not cfg.get("evolved"):
        return
    decision = ROOT / "artifacts" / "reports" / "evolve_eval_decision.md"
    if decision.is_file():
        text = decision.read_text(encoding="utf-8")
        assert "HOLD" in text or "PROMOTE" in text or "promote" in text.lower()
