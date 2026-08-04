# -*- coding: utf-8 -*-
"""Literature axis: pairwise lit_peers, corroboration fuse, lit-only recompare."""

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
    split_lit_peers_vs_donors,
    _papers_possibly_off_topic,
    _surface_literature_axis_flags,
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
    assert "related" in low or "family" in low
    assert "first_pdate" not in low
    assert "2020 to 2026" not in low


def test_papers_possibly_off_topic_when_name_absent():
    papers = [
        {
            "title": "Myc transcriptional networks in cancer",
            "abstract_snippet": "Oncogene signalling without RNA binding.",
        }
    ]
    assert _papers_possibly_off_topic(papers, "PTBP1") is True


def test_papers_on_topic_when_name_in_title():
    papers = [
        {
            "title": "PTBP1 regulates alternative splicing",
            "abstract_snippet": "RNA-binding protein PTBP1 binds polypyrimidine tracts.",
        }
    ]
    assert _papers_possibly_off_topic(papers, "PTBP1") is False


def test_papers_on_topic_via_relatedness_context():
    papers = [
        {
            "title": "Paralog RNA-binding proteins in the PTB family",
            "abstract_snippet": "Homologs of a related RBP share splicing roles.",
        }
    ]
    assert _papers_possibly_off_topic(papers, "PTBP1") is False


def test_extract_requires_same_paper_query_and_peer():
    catalogue = (
        ("PTBP2", "PTBP2", "P0DUMMY1"),
        ("HNRNPL", "HNRNPL", "P0DUMMY2"),
        ("QKI", "QKI", "P0DUMMY3"),
    )
    papers = [
        {
            "title": "PTBP2, a paralog of PTBP1, regulates splicing",
            "abstract_snippet": "RNA-binding assays with PTBP1 and PTBP2.",
        },
        {
            # Peer alone — no query → must not count.
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
    assert "PTBP1" not in aliases
    assert all(p.get("score_kind") == "literature_evidence" for p in peers)
    assert all(0.0 < float(p["rule_score"]) <= 1.0 for p in peers)


def test_function_cue_boosts_rule_score():
    catalogue = (("PTBP2", "PTBP2", "P0X"),)
    with_cue = [
        {
            "title": "PTBP1 and PTBP2 in alternative splicing",
            "abstract_snippet": "RNA-binding proteins with RRM domains.",
        }
    ]
    bare = [
        {
            "title": "PTBP1 and PTBP2 interaction study",
            "abstract_snippet": "Two proteins compared in vitro.",
        }
    ]
    s_cue = extract_literature_peers(with_cue, "PTBP1", catalogue=catalogue)[0][
        "rule_score"
    ]
    s_bare = extract_literature_peers(bare, "PTBP1", catalogue=catalogue)[0][
        "rule_score"
    ]
    assert s_cue >= s_bare


def test_corroboration_only_hits_overlap_donors():
    catalogue = (
        ("PTBP2", "PTBP2", "P0DUMMY1"),
        ("HNRNPL", "HNRNPL", "P0DUMMY2"),
    )
    papers = [
        {
            "title": "PTBP1 with PTBP2 and HNRNPL in splicing",
            "abstract_snippet": "RNA-binding protein family members.",
        }
    ]
    hits = build_literature_cooccurrence_hits(
        papers,
        "PTBP1",
        catalogue=catalogue,
        donor_aliases={"PTBP2"},
        corroboration_only=True,
        max_hits=5,
    )
    assert [h["alias"] for h in hits] == ["PTBP2"]
    assert hits[0]["score_kind"] == "literature_corroboration"
    assert hits[0]["metric"] == "literature_cooccurrence"


def test_split_lit_only_budget():
    peers = [
        {"alias": "A1", "rule_score": 0.9, "score": 0.9},
        {"alias": "A2", "rule_score": 0.8, "score": 0.8},
        {"alias": "A3", "rule_score": 0.7, "score": 0.7},
        {"alias": "A4", "rule_score": 0.6, "score": 0.6},
        {"alias": "KEEP", "rule_score": 0.5, "score": 0.5},
    ]
    corr, orphan, all_p = split_lit_peers_vs_donors(
        peers, {"KEEP"}, lit_only_budget=3
    )
    assert [c["alias"] for c in corr] == ["KEEP"]
    assert len(orphan) == 3
    assert {o["alias"] for o in orphan} == {"A1", "A2", "A3"}
    assert len(all_p) == 5


def test_lit_only_does_not_auto_enter_fuse_hits():
    """Without Donors_SS overlap, build hits must be empty (no gap-fill path)."""
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
        corroboration_only=True,
    )
    assert hits == []


def test_off_topic_surfaces_axis_unusable_flags():
    _reset()
    _surface_literature_axis_flags(True)
    flags = turn_guards.evidence_flags()
    assert flags.get("literature_off_topic") is True
    assert flags.get("literature_axis_unusable") is True
    _reset()


def test_on_topic_does_not_set_axis_flags():
    _reset()
    _surface_literature_axis_flags(False)
    flags = turn_guards.evidence_flags()
    assert not flags.get("literature_off_topic")
    assert not flags.get("literature_axis_unusable")
    _reset()


def test_normalize_merges_literature_off_topic_caveat_without_deduct():
    """Off-topic literature is caveat-only (does not alone force low confidence)."""
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
    raw = {
        "label": "Likely",
        "p_hat": 0.7,
        "confidence": "medium",
        "explanation": "transfer with off-topic papers",
        "mode": "multi_head",
    }
    out = normalize_verdict_with_turn_state(raw)
    caveats = out.get("caveats") or []
    assert "literature_off_topic" in caveats
    assert "literature_axis_unusable" in caveats
    assert out["confidence"] == "medium"

    out2 = normalize_verdict(
        {
            "label": "Likely",
            "p_hat": 0.7,
            "confidence": "medium",
            "explanation": "transfer",
            "mode": "multi_head",
            "evidence_flags": {
                "literature_off_topic": True,
                "literature_axis_unusable": True,
            },
        }
    )
    assert out2["confidence"] == "medium"
    assert "literature_off_topic" in (out2.get("caveats") or [])
    _reset()


def test_lit_soft_hits_enter_fuse_with_low_weight():
    """literature_cooccurrence boosts an existing donor under low fuse weight."""
    from rbp_eval.scoring.fuse_hits import DEFAULT_WEIGHTS, fuse_rbp_hits

    assert float(DEFAULT_WEIGHTS["literature_cooccurrence"]) == 0.1
    assert float(DEFAULT_WEIGHTS["literature_cooccurrence"]) < float(
        DEFAULT_WEIGHTS["seq_identity"]
    )
    assert float(DEFAULT_WEIGHTS["literature_cooccurrence"]) < float(
        DEFAULT_WEIGHTS["domain_jaccard"]
    )

    base = [
        [
            {"alias": "U2AF2", "score": 0.90, "metric": "esmc_cosine"},
            {"alias": "QKI", "score": 0.88, "metric": "esmc_cosine"},
        ],
        [{"alias": "U2AF2", "score": 0.40, "metric": "seq_identity"}],
    ]
    with_lit = base + [
        [{"alias": "QKI", "score": 0.85, "metric": "literature_cooccurrence"}]
    ]
    w = {
        "esmc_cosine": 1.0,
        "seq_identity": 0.3,
        "literature_cooccurrence": 0.1,
    }
    without = fuse_rbp_hits(base, top_k=5, weights=w, use_rank_normalize=False)
    with_ = fuse_rbp_hits(with_lit, top_k=5, weights=w, use_rank_normalize=False)
    by0 = {d["alias"]: d for d in without}
    by1 = {d["alias"]: d for d in with_}
    assert "literature_cooccurrence" in by1["QKI"]["sim_by_modality"]
    assert by1["QKI"]["similarity_breakdown"].get("func", 0) > 0
    assert with_[0]["alias"] == without[0]["alias"] == "U2AF2"
    assert by1["QKI"]["score"] >= by0["QKI"]["score"] - 1e-9


def test_empty_lit_hits_do_not_change_fuse():
    from rbp_eval.scoring.fuse_hits import fuse_rbp_hits

    hits = [
        [{"alias": "U2AF2", "score": 0.95, "metric": "esmc_cosine"}],
        [{"alias": "QKI", "score": 0.40, "metric": "seq_identity"}],
    ]
    a = fuse_rbp_hits(hits, top_k=5, use_rank_normalize=False)
    b = fuse_rbp_hits(hits + [[]], top_k=5, use_rank_normalize=False)
    assert [d["alias"] for d in a] == [d["alias"] for d in b]


def test_fuse_time_corroboration_from_stored_peers():
    """Literature before seq still corroborates at fuse via stored lit_peers."""
    _reset()
    peers = [
        {
            "alias": "PTBP2",
            "uniprot": "P0X",
            "rule_score": 0.8,
            "score": 0.8,
            "metric": "literature_cooccurrence",
            "score_kind": "literature_evidence",
        },
        {
            "alias": "ORPHAN",
            "uniprot": "P0Y",
            "rule_score": 0.7,
            "score": 0.7,
            "metric": "literature_cooccurrence",
            "score_kind": "literature_evidence",
        },
    ]
    turn_guards.set_literature_peers(peers, lit_only=[peers[1]], axis_usable=True)
    turn_guards.set_literature_fuse_hits([], axis_usable=True)
    hits = turn_guards.corroborate_literature_hits_for_aliases({"PTBP2"})
    assert any(h.get("alias") == "PTBP2" for h in hits)
    assert not any(h.get("alias") == "ORPHAN" for h in hits)
    _reset()


def test_record_lit_peer_decisions_writes_flags():
    _reset()

    async def _run():
        tool = RecordLitPeerDecisionsTool()
        return await tool.execute(
            decisions=[
                {
                    "alias": "PTBP2",
                    "action": "recompare_seq",
                    "rationale": "distant homolog may miss MMseqs threshold",
                },
                {
                    "alias": "QKI",
                    "action": "drop",
                    "rationale": "off-family mention",
                },
            ]
        )

    raw = asyncio.run(_run())
    envelope = json.loads(raw)
    assert envelope.get("status") == "ok"
    flags = turn_guards.evidence_flags()
    assert flags.get("literature_peer_decisions") is True
    assert flags.get("literature_lit_only_recompare") is True
    assert flags.get("literature_lit_only_dropped") is True
    detail = turn_guards.lit_peer_decisions()
    assert {d["alias"] for d in detail} == {"PTBP2", "QKI"}
    records = turn_guards.evidence_records()
    assert any(r.get("kind") == "lit_peer_decisions" for r in records)
    _reset()


def test_literature_success_off_topic_empty_soft_hits(monkeypatch, tmp_path):
    """Off-topic papers → axis_usable false + empty hits_lit."""
    _reset()

    import nanobot.agent.tools.rbp.annotation as ann
    import nanobot.agent.tools.rbp.common as common

    monkeypatch.setattr(
        common,
        "_literature_cache_dir",
        lambda: tmp_path / "literature",
    )
    monkeypatch.setattr(ann, "literature_cache_get", lambda *_a, **_k: None)

    class _FakeClient:
        def call(self, name, payload):
            assert name == "literature_retrieval"
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
    monkeypatch.setattr(
        ann,
        "timed_call",
        lambda fn: (fn(), 1.0, None),
    )

    tool = LiteratureSearchTool()
    raw = asyncio.run(tool.execute(name="PTBP1", max_results=3))
    envelope = json.loads(raw)
    assert envelope.get("status") == "ok"
    value = envelope.get("value") or {}
    assert value.get("possibly_off_topic") is True
    assert value.get("axis_usable") is False
    assert value.get("hits") == []
    assert value.get("hits_lit") == []
    assert turn_guards.literature_fuse_hits() == []
    flags = turn_guards.evidence_flags()
    assert flags.get("literature_off_topic") is True
    assert flags.get("literature_axis_unusable") is True
    _reset()


def test_literature_success_corroborates_when_donors_present(monkeypatch, tmp_path):
    _reset()
    turn_guards.register_retrieve_donors(["PTBP2"])

    import nanobot.agent.tools.rbp.annotation as ann
    import nanobot.agent.tools.rbp.common as common

    monkeypatch.setattr(
        common,
        "_literature_cache_dir",
        lambda: tmp_path / "literature",
    )
    monkeypatch.setattr(ann, "literature_cache_get", lambda *_a, **_k: None)
    monkeypatch.setattr(
        ann,
        "_catalogue_alias_index",
        lambda: (("PTBP2", "PTBP2", "P0X"), ("QKI", "QKI", "P0Y")),
    )

    class _FakeClient:
        def call(self, name, payload):
            assert "paralog" in (payload.get("query") or "").lower() or "homolog" in (
                payload.get("query") or ""
            ).lower()
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
    envelope = json.loads(raw)
    value = envelope.get("value") or {}
    assert value.get("axis_usable") is True
    assert any(h.get("alias") == "PTBP2" for h in (value.get("hits_lit") or []))
    assert any(h.get("alias") == "PTBP2" for h in (value.get("corroborated") or []))
    # QKI co-mentioned with query but not in Donors_SS → lit_only, not fuse hits.
    lit_only = {p.get("alias") for p in (value.get("lit_only_peers") or [])}
    assert "QKI" in lit_only
    assert not any(h.get("alias") == "QKI" for h in (value.get("hits_lit") or []))
    stored = turn_guards.literature_fuse_hits()
    assert any(h.get("alias") == "PTBP2" for h in stored)
    _reset()


def test_literature_crafted_query_passed_through(monkeypatch, tmp_path):
    _reset()

    import nanobot.agent.tools.rbp.annotation as ann
    import nanobot.agent.tools.rbp.common as common

    monkeypatch.setattr(
        common,
        "_literature_cache_dir",
        lambda: tmp_path / "literature",
    )
    monkeypatch.setattr(ann, "literature_cache_get", lambda *_a, **_k: None)
    monkeypatch.setattr(ann, "_catalogue_alias_index", lambda: ())

    seen: dict = {}

    class _FakeClient:
        def call(self, name, payload):
            seen["query"] = payload.get("query")
            return {
                "papers": [
                    {
                        "title": "PTBP1 RRM family",
                        "abstract_snippet": "PTBP1 RNA-binding.",
                    }
                ],
                "query": payload.get("query"),
            }

    monkeypatch.setattr(ann, "get_delivery_client", lambda **_k: _FakeClient())
    monkeypatch.setattr(ann, "timed_call", lambda fn: (fn(), 1.0, None))

    tool = LiteratureSearchTool()
    crafted = 'PTBP1 AND ("protein family" OR paralog*) AND RBP'
    raw = asyncio.run(tool.execute(name="PTBP1", query=crafted, max_results=2))
    envelope = json.loads(raw)
    assert envelope.get("status") == "ok"
    assert seen["query"] == crafted
    assert (envelope.get("value") or {}).get("query") == crafted
    _reset()
