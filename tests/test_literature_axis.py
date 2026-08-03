# -*- coding: utf-8 -*-
"""Literature axis: related-protein query, soft fuse hits, off-topic → no hits."""

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
    build_literature_cooccurrence_hits,
    default_literature_query,
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


def test_build_literature_cooccurrence_hits_from_mock_papers():
    catalogue = (
        ("PTBP2", "PTBP2", "P0DUMMY1"),
        ("HNRNPL", "HNRNPL", "P0DUMMY2"),
        ("QKI", "QKI", "P0DUMMY3"),
    )
    papers = [
        {
            "title": "PTBP2, a paralog of PTBP1, regulates splicing",
            "abstract_snippet": "Compared with HNRNPL in RNA-binding assays.",
        },
        {
            "title": "Unrelated kinase cascade",
            "abstract_snippet": "No catalogue symbols here.",
        },
    ]
    hits = build_literature_cooccurrence_hits(
        papers, "PTBP1", catalogue=catalogue, max_hits=5
    )
    aliases = {h["alias"] for h in hits}
    assert "PTBP2" in aliases
    assert "HNRNPL" in aliases
    assert "PTBP1" not in aliases
    assert all(h["metric"] == "literature_cooccurrence" for h in hits)
    assert all(0.0 < float(h["score"]) <= 1.0 for h in hits)
    # Title mention ranks above abstract-only.
    by_alias = {h["alias"]: h["score"] for h in hits}
    assert by_alias["PTBP2"] >= by_alias["HNRNPL"]


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
    # Low weight: lit must not flip a clear emb leader.
    assert with_[0]["alias"] == without[0]["alias"] == "U2AF2"
    assert by1["QKI"]["score"] >= by0["QKI"]["score"] - 1e-9


def test_empty_lit_hits_do_not_change_fuse():
    from rbp_eval.scoring.fuse_hits import append_literature_gap_fill, fuse_rbp_hits

    hits = [
        [{"alias": "U2AF2", "score": 0.95, "metric": "esmc_cosine"}],
        [{"alias": "QKI", "score": 0.40, "metric": "seq_identity"}],
    ]
    a = fuse_rbp_hits(hits, top_k=5, use_rank_normalize=False)
    b = fuse_rbp_hits(hits + [[]], top_k=5, use_rank_normalize=False)
    assert [d["alias"] for d in a] == [d["alias"] for d in b]
    merged, filled = append_literature_gap_fill(a, [], top_k=5)
    assert filled == []
    assert [d["alias"] for d in merged] == [d["alias"] for d in a]


def test_gap_fill_appends_missing_panel_alias():
    from rbp_eval.scoring.fuse_hits import append_literature_gap_fill

    donors = [
        {
            "alias": "U2AF2",
            "score": 0.8,
            "fused_score": 0.8,
            "sim_by_modality": {"esmc_cosine": 0.9},
        }
    ]
    lit = [
        {"alias": "PTBP1", "score": 0.9, "metric": "literature_cooccurrence", "uniprot": "P26599"}
    ]
    out, filled = append_literature_gap_fill(
        donors, lit, top_k=5, max_gap=2, tau_drop=0.30, allowed_aliases={"u2af2", "ptbp1"}
    )
    assert filled == ["PTBP1"]
    by = {d["alias"]: d for d in out}
    assert "PTBP1" in by
    assert by["PTBP1"].get("gap_fill") == "literature_cooccurrence"
    assert float(by["PTBP1"]["score"]) < 0.30
    assert float(by["U2AF2"]["score"]) > float(by["PTBP1"]["score"])


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


def test_literature_success_builds_soft_hits(monkeypatch, tmp_path):
    _reset()

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
                        "abstract_snippet": "RNA-binding proteins PTBP1/PTBP2.",
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
    stored = turn_guards.literature_fuse_hits()
    assert any(h.get("alias") == "PTBP2" for h in stored)
    _reset()
