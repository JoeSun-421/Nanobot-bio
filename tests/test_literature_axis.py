# -*- coding: utf-8 -*-
"""Literature / Function axis: free weights, parallel peers, UniProt merge."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from nanobot.agent.tools.rbp import turn_guards  # noqa: E402
from nanobot.agent.tools.rbp.annotation import (  # noqa: E402
    LiteratureSearchTool,
    RecordLitPeerDecisionsTool,
    build_literature_cooccurrence_hits,
    default_literature_query,
    extract_literature_peers,
    extract_peers_from_annotation_text,
    peers_to_function_fuse_hits,
    split_lit_peers_vs_donors,
    _papers_possibly_off_topic,
    _surface_literature_axis_flags,
)
from rbp_eval.scoring.fuse_hits import (  # noqa: E402
    apply_fusion_weight_override,
    fuse_rbp_hits,
)
from app.core.verdict_schema import normalize_verdict_with_turn_state  # noqa: E402


def _reset():
    turn_guards.reset_stage_guards()
    LiteratureSearchTool._calls_used = 0


def test_default_literature_query_similarity_oriented():
    q = default_literature_query("PTBP1")
    assert '"PTBP1"' in q
    low = q.lower()
    assert "paralog" in low or "homolog" in low


def test_extract_requires_same_paper_query_and_peer():
    catalogue = (
        ("PTBP2", "PTBP2", "P0DUMMY1"),
        ("HNRNPL", "HNRNPL", "P0DUMMY2"),
    )
    papers = [
        {
            "title": "PTBP2, a paralog of PTBP1, regulates splicing",
            "abstract_snippet": "RNA-binding assays with PTBP1 and PTBP2.",
        },
        {
            "title": "HNRNPL binds RNA in unrelated assay",
            "abstract_snippet": "Kinase cascade without the query gene symbol.",
        },
    ]
    peers = extract_literature_peers(
        papers, "PTBP1", catalogue=catalogue, max_peers=5
    )
    aliases = {p["alias"] for p in peers}
    assert "PTBP2" in aliases
    assert "HNRNPL" not in aliases


def test_function_peers_enter_fuse_without_donors_ss():
    catalogue = (("PTBP2", "PTBP2", "P0X"),)
    papers = [
        {
            "title": "PTBP1 and PTBP2 splicing",
            "abstract_snippet": "RNA-binding proteins.",
        }
    ]
    hits = build_literature_cooccurrence_hits(
        papers,
        "PTBP1",
        catalogue=catalogue,
        donor_aliases=set(),
        corroboration_only=False,
    )
    assert any(h["alias"] == "PTBP2" for h in hits)
    assert hits[0]["score_kind"] == "function_peer"


def test_overlap_tagged_as_corroboration():
    peers = [
        {"alias": "PTBP2", "rule_score": 0.8, "score": 0.8, "source": "pmc"},
        {"alias": "QKI", "rule_score": 0.5, "score": 0.5, "source": "pmc"},
    ]
    hits = peers_to_function_fuse_hits(peers, donor_aliases={"PTBP2"})
    by = {h["alias"]: h for h in hits}
    assert by["PTBP2"]["score_kind"] == "literature_corroboration"
    assert by["QKI"]["score_kind"] == "function_peer"


def test_uniprot_annotation_peer_extract():
    catalogue = (("PTBP2", "PTBP2", "P0X"), ("QKI", "QKI", "P0Y"))
    ann = {
        "function": "Paralog of PTBP2 involved in splicing; unrelated kinase note.",
        "keywords": ["RNA-binding", "mRNA splicing"],
    }
    peers = extract_peers_from_annotation_text(
        ann, "PTBP1", catalogue=catalogue, source="uniprot"
    )
    assert any(p["alias"] == "PTBP2" and p["source"] == "uniprot" for p in peers)


def test_apply_fusion_weight_override_clamp():
    base = {"esmc_cosine": 1.0, "literature_cooccurrence": 0.1}
    applied, clamped = apply_fusion_weight_override(
        base, {"literature_cooccurrence": 0.85, "tm_score": 3.5, "bad": "x"}
    )
    assert applied["literature_cooccurrence"] == 0.85
    assert applied["tm_score"] == 2.0
    assert "tm_score" in clamped
    assert clamped["tm_score"]["requested"] == 3.5
    assert "bad" not in applied
    assert applied["esmc_cosine"] == 1.0


def test_high_lit_weight_can_reorder_fuse():
    lists = [
        [
            {"alias": "U2AF2", "score": 0.70, "metric": "esmc_cosine"},
            {"alias": "QKI", "score": 0.68, "metric": "esmc_cosine"},
        ],
        [{"alias": "QKI", "score": 0.95, "metric": "literature_cooccurrence"}],
    ]
    low = fuse_rbp_hits(
        lists,
        top_k=5,
        weights={"esmc_cosine": 1.0, "literature_cooccurrence": 0.1},
        use_rank_normalize=False,
    )
    high = fuse_rbp_hits(
        lists,
        top_k=5,
        weights={"esmc_cosine": 1.0, "literature_cooccurrence": 2.0},
        use_rank_normalize=False,
    )
    by_low = {d["alias"]: d["score"] for d in low}
    by_high = {d["alias"]: d["score"] for d in high}
    assert by_high["QKI"] > by_low["QKI"]


def test_fuse_tool_accepts_weight_override(monkeypatch):
    _reset()
    turn_guards.mark_retrieve_done("seq_similarity")
    turn_guards.mark_retrieve_done("struct_similarity")
    turn_guards.mark_retrieve_done("domain_architecture")
    turn_guards.add_evidence_flag("structure_axis_unavailable", True)
    turn_guards.add_evidence_flag("domain_empty", True)

    from nanobot.agent.tools.rbp.evolve_tools import FuseSimilarityViewsTool

    tool = FuseSimilarityViewsTool()
    raw = asyncio.run(
        tool.execute(
            hits_emb=[
                {"alias": "U2AF2", "score": 0.9, "metric": "esmc_cosine"},
                {"alias": "QKI", "score": 0.5, "metric": "esmc_cosine"},
            ],
            hits_lit=[
                {"alias": "QKI", "score": 0.9, "metric": "literature_cooccurrence"}
            ],
            fusion_weights={"literature_cooccurrence": 1.5, "esmc_cosine": 0.5},
            exclude_aliases=[],
            top_k=5,
            tau_drop=0.0,
        )
    )
    env = json.loads(raw)
    assert env.get("status") == "ok"
    value = env.get("value") or {}
    assert value["fusion_weights_applied"]["literature_cooccurrence"] == 1.5
    assert value["fusion_weights_applied"]["esmc_cosine"] == 0.5
    assert turn_guards.evidence_flags().get("fusion_weights_override") is True
    _reset()


def test_fuse_tool_clamps_over_wmax(monkeypatch):
    _reset()
    turn_guards.mark_retrieve_done("seq_similarity")
    turn_guards.mark_retrieve_done("struct_similarity")
    turn_guards.mark_retrieve_done("domain_architecture")
    turn_guards.add_evidence_flag("structure_axis_unavailable", True)
    turn_guards.add_evidence_flag("domain_empty", True)

    from nanobot.agent.tools.rbp.evolve_tools import FuseSimilarityViewsTool

    tool = FuseSimilarityViewsTool()
    raw = asyncio.run(
        tool.execute(
            hits_emb=[{"alias": "U2AF2", "score": 0.9, "metric": "esmc_cosine"}],
            fusion_weights={"literature_cooccurrence": 9.0},
            top_k=5,
            tau_drop=0.0,
        )
    )
    env = json.loads(raw)
    value = env.get("value") or {}
    assert value["fusion_weights_applied"]["literature_cooccurrence"] == 2.0
    assert "literature_cooccurrence" in (value.get("fusion_weights_clamped") or {})
    _reset()


def test_off_topic_surfaces_pmc_flag_not_always_axis_unusable():
    _reset()
    _surface_literature_axis_flags(True, function_still_usable=True)
    flags = turn_guards.evidence_flags()
    assert flags.get("literature_pmc_off_topic") is True
    assert flags.get("literature_off_topic") is True
    assert not flags.get("literature_axis_unusable")
    _reset()
    _surface_literature_axis_flags(True, function_still_usable=False)
    assert turn_guards.evidence_flags().get("literature_axis_unusable") is True
    _reset()


def test_normalize_merges_literature_off_topic_caveat_without_deduct():
    from app.core.verdict_schema import normalize_verdict

    _reset()
    turn_guards.add_evidence_flag("literature_off_topic", True)
    turn_guards.add_evidence_flag("literature_axis_unusable", True)
    turn_guards.set_authoritative_score(
        p_hat=0.7,
        mode="multi_head",
        source="test",
        provenance={
            "aggregation": {"terms": [{}, {}, {}], "n_transfer_priors": 3, "n_donor_quality": 3},
            "predictions": [{"prob": 0.7}, {"prob": 0.6}, {"prob": 0.5}],
        },
    )
    out = normalize_verdict_with_turn_state(
        {
            "label": "Likely",
            "p_hat": 0.7,
            "confidence": "medium",
            "explanation": "transfer with off-topic papers",
            "mode": "multi_head",
        }
    )
    assert "literature_off_topic" in (out.get("caveats") or [])
    assert out["confidence"] == "medium"
    _reset()


def test_record_lit_peer_weight_note():
    _reset()

    async def _run():
        tool = RecordLitPeerDecisionsTool()
        return await tool.execute(
            decisions=[
                {
                    "alias": "literature_cooccurrence",
                    "action": "weight_note",
                    "rationale": "PMC+UniProt agree on PTBP2; raise Function weight",
                }
            ]
        )

    env = json.loads(asyncio.run(_run()))
    assert env.get("status") == "ok"
    assert turn_guards.evidence_flags().get("literature_peer_decisions") is True
    _reset()


def test_literature_success_builds_function_hits(monkeypatch, tmp_path):
    _reset()

    import nanobot.agent.tools.rbp.annotation as ann
    import nanobot.agent.tools.rbp.common as common

    monkeypatch.setattr(
        common, "_literature_cache_dir", lambda: tmp_path / "literature"
    )
    monkeypatch.setattr(ann, "literature_cache_get", lambda *_a, **_k: None)
    monkeypatch.setattr(
        ann,
        "_catalogue_alias_index",
        lambda: (("PTBP2", "PTBP2", "P0X"), ("QKI", "QKI", "P0Y")),
    )
    monkeypatch.setattr(ann, "_try_load_func_annotation_for_lit", lambda _n: None)

    class _FakeClient:
        def call(self, name, payload):
            return {
                "papers": [
                    {
                        "title": "PTBP1 and its paralog PTBP2 in splicing",
                        "abstract_snippet": "RNA-binding proteins PTBP1/PTBP2; QKI also noted with PTBP1.",
                    }
                ],
                "query": payload.get("query"),
            }

    monkeypatch.setattr(ann, "get_delivery_client", lambda **_k: _FakeClient())
    monkeypatch.setattr(ann, "timed_call", lambda fn: (fn(), 1.0, None))

    tool = LiteratureSearchTool()
    raw = asyncio.run(tool.execute(name="PTBP1", max_results=3))
    value = json.loads(raw).get("value") or {}
    assert value.get("axis_usable") is True
    aliases = {h.get("alias") for h in (value.get("hits_lit") or [])}
    assert "PTBP2" in aliases
    assert "QKI" in aliases  # function peer without Donors_SS still in hits
    assert "europe_pmc" in (value.get("sources") or {})
    _reset()


def test_literature_merges_uniprot_peers_when_pmc_off_topic(monkeypatch, tmp_path):
    _reset()

    import nanobot.agent.tools.rbp.annotation as ann
    import nanobot.agent.tools.rbp.common as common

    monkeypatch.setattr(
        common, "_literature_cache_dir", lambda: tmp_path / "literature"
    )
    monkeypatch.setattr(ann, "literature_cache_get", lambda *_a, **_k: None)
    monkeypatch.setattr(
        ann,
        "_catalogue_alias_index",
        lambda: (("PTBP2", "PTBP2", "P0X"),),
    )
    monkeypatch.setattr(
        ann,
        "_try_load_func_annotation_for_lit",
        lambda _n: {
            "function": "Closely related to PTBP2 in the PTB family",
            "keywords": ["RNA-binding"],
            "uniprot": "P26599",
        },
    )

    class _FakeClient:
        def call(self, name, payload):
            return {
                "papers": [
                    {
                        "title": "Unrelated kinase cascade",
                        "abstract_snippet": "No mention of the target RBP.",
                    }
                ],
                "query": payload.get("query"),
            }

    monkeypatch.setattr(ann, "get_delivery_client", lambda **_k: _FakeClient())
    monkeypatch.setattr(ann, "timed_call", lambda fn: (fn(), 1.0, None))

    tool = LiteratureSearchTool()
    raw = asyncio.run(tool.execute(name="PTBP1", max_results=3))
    value = json.loads(raw).get("value") or {}
    assert value.get("possibly_off_topic") is True
    assert any(h.get("alias") == "PTBP2" for h in (value.get("hits_lit") or []))
    assert (value.get("sources") or {}).get("uniprot")
    flags = turn_guards.evidence_flags()
    assert flags.get("literature_pmc_off_topic") is True
    assert not flags.get("literature_axis_unusable")
    _reset()


def test_fuse_time_injects_all_stored_peers():
    _reset()
    peers = [
        {
            "alias": "PTBP2",
            "rule_score": 0.8,
            "score": 0.8,
            "metric": "literature_cooccurrence",
            "source": "pmc",
        },
        {
            "alias": "ORPHAN",
            "rule_score": 0.7,
            "score": 0.7,
            "metric": "literature_cooccurrence",
            "source": "uniprot",
        },
    ]
    turn_guards.set_literature_peers(peers, lit_only=[], axis_usable=True)
    hits = turn_guards.corroborate_literature_hits_for_aliases({"PTBP2"})
    aliases = {h["alias"] for h in hits}
    assert aliases == {"PTBP2", "ORPHAN"}
    _reset()
