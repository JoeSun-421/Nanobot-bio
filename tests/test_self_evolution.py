# -*- coding: utf-8 -*-
"""Self-evolution smoke tests (agent-side only; no delivery edits)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_runtime_config_loads():
    from app.core.runtime_config import (
        abstain_thresholds,
        clear_runtime_config_cache,
        fusion_weights,
        label_thresholds,
        load_runtime_config,
    )

    clear_runtime_config_cache()
    cfg = load_runtime_config()
    assert isinstance(cfg, dict)
    w = fusion_weights()
    assert "esmc_cosine" in w
    thr = label_thresholds()
    assert thr["strong"] >= thr["likely"] >= thr["unlikely"]
    ab = abstain_thresholds()
    assert ab["esmc_cosine"] > 0
    assert "fused" in ab


def test_deep_merge_preserves_nested_siblings():
    """Partial evolved overrides of predict/structure_policy/integrate must keep
    sibling defaults instead of clobbering the whole nested block."""
    from app.core.runtime_config import _deep_merge

    base = {
        "top_k": 5,
        "predict": {"aggregate": "weighted", "timeout_s": 180},
        "structure_policy": {"prefer_afdb": True, "use_af3_fallback": True},
        "integrate": {"use_transfer_prior": True, "use_donor_quality": True},
        "axes": {"embedding": True, "structure": True},
    }
    evo = {
        "evolved": True,
        "top_k": 7,
        "predict": {"aggregate": "mean"},
        "structure_policy": {"use_af3_fallback": False},
        "integrate": {"use_donor_quality": False},
    }
    merged = _deep_merge(base, evo)
    assert merged["top_k"] == 7
    assert merged["predict"] == {"aggregate": "mean", "timeout_s": 180}
    assert merged["structure_policy"] == {"prefer_afdb": True, "use_af3_fallback": False}
    assert merged["integrate"] == {"use_transfer_prior": True, "use_donor_quality": False}
    # untouched nested block survives intact
    assert merged["axes"] == {"embedding": True, "structure": True}
    # inputs not mutated
    assert base["predict"] == {"aggregate": "weighted", "timeout_s": 180}


def test_resolve_loo_csvs_single_source():
    """resolve_loo_csvs is the single resolver shared by loo_eval/evaluator/gate."""
    from rbp_eval.loo.loo_eval import resolve_loo_csvs

    summary, metrics = resolve_loo_csvs()
    assert summary.name == "loo_summary.csv"
    assert metrics.name == "loo_transfer_metrics.csv"


def test_confidence_abstain_injects_evolved_thresholds():
    from app.backends.delivery.registry import _normalize_delivery_payload
    from app.core.runtime_config import abstain_thresholds, clear_runtime_config_cache

    clear_runtime_config_cache()
    expected = abstain_thresholds()
    out = _normalize_delivery_payload(
        "confidence_abstain",
        {"hits": [{"alias": "PTBP1", "score": 0.9, "metric": "esmc_cosine"}]},
    )
    assert out["thresholds"]["esmc_cosine"] == expected["esmc_cosine"]
    # explicit override wins
    out2 = _normalize_delivery_payload(
        "confidence_abstain",
        {
            "hits": [{"alias": "PTBP1", "score": 0.9}],
            "thresholds": {"esmc_cosine": 0.99},
        },
    )
    assert out2["thresholds"]["esmc_cosine"] == 0.99
    assert out2["thresholds"]["fused"] == expected["fused"]


def test_fuse_similarity_views_tool():
    from nanobot.agent.tools.rbp.evolve_tools import FuseSimilarityViewsTool
    from nanobot.agent.tools.rbp.turn_guards import (
        fused_proxies,
        mark_retrieve_done,
        reset_stage_guards,
    )
    import asyncio

    reset_stage_guards()
    mark_retrieve_done("seq_similarity")
    mark_retrieve_done("struct_similarity")
    mark_retrieve_done("domain_architecture")
    tool = FuseSimilarityViewsTool()
    hits_a = [
        {"alias": "U2AF2", "uniprot": "P26368", "score": 0.9, "metric": "esmc_cosine"},
        {"alias": "QKI", "uniprot": "Q96PU8", "score": 0.8, "metric": "esmc_cosine"},
    ]
    hits_b = [
        {"alias": "U2AF2", "uniprot": "P26368", "score": 1.0, "metric": "domain_overlap"},
    ]
    out = asyncio.run(
        tool.execute(hit_lists=[hits_a, hits_b], top_k=3, exclude_aliases=["PTBP1"])
    )
    data = json.loads(out)
    assert data["status"] == "ok"
    donors = data["value"]["donors"]
    assert donors
    assert donors[0]["alias"] == "U2AF2"
    # Stored fused proxies must expose similarity_score for commit lookup.
    stored = fused_proxies()
    assert stored
    assert "similarity_score" in stored[0]
    assert stored[0]["similarity_score"] == 0.9
    assert stored[0]["vote_similarity"] == 0.9
    assert stored[0]["fused_score"] == stored[0]["score"]


def test_fuse_then_commit_selection_only():
    """Integration: fuse stores donors → commit with aliases only succeeds."""
    import asyncio

    from nanobot.agent.tools.rbp.commit_proxies import CommitProxyCandidatesTool
    from nanobot.agent.tools.rbp.evolve_tools import FuseSimilarityViewsTool
    from nanobot.agent.tools.rbp.turn_guards import (
        committed_proxies,
        mark_retrieve_done,
        reset_stage_guards,
    )

    reset_stage_guards()
    mark_retrieve_done("seq_similarity")
    mark_retrieve_done("struct_similarity")
    mark_retrieve_done("domain_architecture")
    fuse = FuseSimilarityViewsTool()
    fuse_out = asyncio.run(
        fuse.execute(
            hit_lists=[
                [
                    {"alias": "U2AF2", "uniprot": "P26368", "score": 0.95, "metric": "esmc_cosine"},
                    {"alias": "MATR3", "uniprot": "P43243", "score": 0.8, "metric": "esmc_cosine"},
                ],
                [
                    {"alias": "U2AF2", "uniprot": "P26368", "score": 0.9, "metric": "tm_score"},
                ],
            ],
            top_k=5,
            tau_drop=0.0,
        )
    )
    fuse_data = json.loads(fuse_out)
    assert fuse_data["status"] == "ok"
    aliases = [d["alias"] for d in fuse_data["value"]["donors"]]
    assert "U2AF2" in aliases

    commit = CommitProxyCandidatesTool()
    commit_out = asyncio.run(
        commit.execute(
            candidates=[{"alias": a} for a in aliases[:3]],
            tau_drop=0.30,
        )
    )
    commit_data = json.loads(commit_out)
    assert commit_data["status"] == "ok", commit_data
    assert commit_data["value"]["n"] >= 1
    assert committed_proxies()
    assert all("similarity_score" in c for c in committed_proxies())


def test_lookup_proxy_cache_tool_miss(tmp_path, monkeypatch):
    from rbp_eval.evolve import proxy_cache as pc
    import asyncio
    from nanobot.agent.tools.rbp.evolve_tools import LookupProxyCacheTool

    cache_path = tmp_path / "proxy_map.json"
    cache_path.write_text(
        json.dumps({"version": 1, "entries": {}, "stats": {}}), encoding="utf-8"
    )
    monkeypatch.setattr(pc, "DEFAULT_CACHE", cache_path)
    tool = LookupProxyCacheTool()
    out = asyncio.run(tool.execute(alias="NSUN2"))
    data = json.loads(out)
    assert data["status"] == "ok"
    assert data["value"]["hit"] is False


def test_lookup_proxy_cache_tool_hit(tmp_path, monkeypatch):
    from rbp_eval.evolve import proxy_cache as pc
    import asyncio
    from nanobot.agent.tools.rbp.evolve_tools import LookupProxyCacheTool

    cache_path = tmp_path / "proxy_map.json"
    cache_path.write_text(
        json.dumps(
            {
                "version": 1,
                "entries": {
                    "alias:NSUN2": {
                        "alias": "NSUN2",
                        "hits": 5,
                        "promoted": True,
                        "proxies": [{"alias": "NOP2"}, {"alias": "NSUN5"}],
                    }
                },
                "stats": {"n_entries": 1, "n_promoted": 1},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(pc, "DEFAULT_CACHE", cache_path)
    tool = LookupProxyCacheTool()
    out = asyncio.run(tool.execute(alias="NSUN2"))
    data = json.loads(out)
    assert data["value"]["hit"] is True
    assert data["value"]["proxies"][0]["alias"] == "NOP2"


def test_retune_label_thresholds_ce():
    from rbp_eval.evolve.retune import retune_label_thresholds

    labels = [{"p_hat": 0.9, "y": 1} for _ in range(4)] + [
        {"p_hat": 0.1, "y": 0} for _ in range(4)
    ]
    out = retune_label_thresholds(labels)
    assert out["status"] == "ok"
    assert out["objective"] == "calibrated_cross_entropy"
    assert out["thresholds"]["likely"] > 0.2


def test_tool_attribution_supporting_mass():
    from rbp_eval.evolve.proposals import tool_attribution

    results = [
        {
            "mode": "transfer",
            "retrieval": {"domain": {"ok": True}, "esm_similarity": {"ok": True}},
            "evidence_table": [
                {
                    "alias": "U2AF2",
                    "sim_by_modality": {"esmc_cosine": 0.9, "domain_overlap": 0.8},
                }
            ],
            "verdict": {
                "p_hat": 0.7,
                "supporting_rbps": [
                    {"alias": "U2AF2", "similarity_score": 0.9, "prob": 0.7}
                ],
            },
        }
    ]
    attr = tool_attribution(results)
    assert attr["n_success"] == 1
    assert attr["supporting_evidence_fraction"] or attr["modality_mass"]


def test_rbp_trace_hook_query_end(tmp_path):
    import asyncio
    from rbp_eval.runtime.nanobot_hooks import RBPTraceHook

    path = tmp_path / "t.jsonl"
    hook = RBPTraceHook(path, session_key="test")
    hook.note_query(alias="NSUN2")
    hook._last_donors = [{"alias": "NOP2", "score": 0.8}]
    content = json.dumps(
        {
            "label": "Likely",
            "p_hat": 0.6,
            "confidence": "medium",
            "explanation": "test",
            "supporting_rbps": [{"alias": "NOP2", "prob": 0.6, "similarity_score": 0.8}],
        }
    )
    hook.emit_query_end(content=content, tools_used=["resolve_rbp", "lookup_proxy_cache"])
    rows = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
    assert any(r.get("type") == "query_end" for r in rows)
    qe = next(r for r in rows if r["type"] == "query_end")
    assert qe["verdict"]["p_hat"] == 0.6
    assert qe["donors"]


def test_run_self_evolution_offline(tmp_path, monkeypatch):
    from rbp_eval.evolve import orchestrator as orch
    from rbp_eval.evolve import promote as promo
    from rbp_eval.evolve.orchestrator import run_self_evolution

    # redirect report/config writes
    report_path = tmp_path / "self_evolution_report.json"
    cfg_path = tmp_path / "evolved.yaml"
    cand_path = tmp_path / "evolved.candidate.yaml"
    monkeypatch.setattr(orch, "EVOLVED_REPORT", report_path)
    monkeypatch.setattr(orch, "CANDIDATE_CONFIG", cand_path)
    monkeypatch.setattr(promo, "EVOLVED_REPORT", report_path)
    monkeypatch.setattr(promo, "EVOLVED_CONFIG", cfg_path)
    monkeypatch.setattr(promo, "CANDIDATE_CONFIG", cand_path)

    results = [
        {
            "query": {"alias": "PTBP1"},
            "mode": "retrieval_only",
            "donors": [
                {"alias": "U2AF2", "score": 0.9, "metric": "domain_overlap"},
                {"alias": "ELAVL1", "score": 0.7, "metric": "domain_overlap"},
            ],
            "retrieval": {"domain": {"ok": True, "n": 2}},
            "evidence_table": [
                {"alias": "U2AF2", "score": 0.9, "sim_by_modality": {"domain_overlap": 0.9}},
            ],
            "verdict": {
                "label": "No",
                "p_hat": None,
                "confidence": "low",
                "explanation": "stub",
                "supporting_rbps": [{"alias": "U2AF2", "similarity_score": 0.9}],
            },
        }
    ]
    held = {
        "PTBP1": [
            [
                {"alias": "U2AF2", "score": 0.9, "metric": "domain_overlap"},
                {"alias": "ELAVL1", "score": 0.7, "metric": "domain_overlap"},
            ]
        ]
    }
    # weight retune needs LOO matrix; if missing, status may still be ok with 0 score
    report = run_self_evolution(
        results,
        held_to_hit_lists=held,
        traces=[
            {
                "type": "query_end",
                "alias": "NSUN2",
                "donors": [{"alias": "NOP2"}, {"alias": "NSUN5"}],
                "verdict": {},
            },
            {
                "type": "query_end",
                "alias": "NSUN2",
                "donors": [{"alias": "NOP2"}, {"alias": "NSUN5"}],
                "verdict": {},
            },
        ],
        write_config=True,
        require_loo_report=False,
        allow_retrieval_only=True,
    )
    assert report_path.is_file()
    d = report.to_dict()
    assert "tool_attribution" in d
    assert "toolkit_proposals" in d


def test_retune_abstain_thresholds_grid():
    from rbp_eval.evolve.retune import retune_abstain_thresholds

    held = {
        "PTBP1": [
            [
                {"alias": "U2AF2", "score": 0.9, "metric": "domain_overlap"},
                {"alias": "ELAVL1", "score": 0.4, "metric": "domain_overlap"},
            ]
        ],
        "QKI": [
            [
                {"alias": "HNRNPC", "score": 0.2, "metric": "esmc_cosine"},
            ]
        ],
    }
    out = retune_abstain_thresholds(held, top_k=3, grid=[0.2, 0.45, 0.7])
    assert out["status"] == "ok"
    assert "tuned_thresholds" in out
    assert "fused" in out["tuned_thresholds"]
    assert "history" in out


def test_retune_tau_drop_grid(monkeypatch):
    from rbp_eval.evolve import retune as ev

    # Hermetic LOO matrix: high-scoring donors carry high transfer AUPRC, so a
    # higher tau_drop that keeps only them should not lose coverage here.
    fake_matrix = {
        ("PTBP1", "U2AF2"): 0.80,
        ("PTBP1", "ELAVL1"): 0.30,
        ("QKI", "HNRNPC"): 0.55,
    }
    monkeypatch.setattr(ev, "_load_loo_matrix", lambda: ({}, fake_matrix))

    held = {
        "PTBP1": [
            [
                {"alias": "U2AF2", "score": 0.9, "metric": "domain_overlap"},
                {"alias": "ELAVL1", "score": 0.4, "metric": "domain_overlap"},
            ]
        ],
        "QKI": [
            [{"alias": "HNRNPC", "score": 0.6, "metric": "esmc_cosine"}]
        ],
    }
    out = ev.retune_tau_drop(held, top_k=3, grid=[0.0, 0.3, 0.6])
    assert out["status"] == "ok"
    assert "tuned_tau_drop" in out
    assert 0.0 <= out["tuned_tau_drop"] <= 0.6
    assert out["history"] and all("drop_rate" in h for h in out["history"])
    # improvement is measured vs the live baseline tau, never negative in the report
    assert out["tuned"]["mean_transfer"] >= out["baseline"]["mean_transfer"] - 1e-9


def test_run_self_evolution_includes_abstain_retune(tmp_path, monkeypatch):
    from rbp_eval.evolve import orchestrator as orch
    from rbp_eval.evolve import promote as promo
    from rbp_eval.evolve.orchestrator import run_self_evolution

    report_path = tmp_path / "self_evolution_report.json"
    cfg_path = tmp_path / "evolved.yaml"
    cand_path = tmp_path / "evolved.candidate.yaml"
    monkeypatch.setattr(orch, "EVOLVED_REPORT", report_path)
    monkeypatch.setattr(orch, "CANDIDATE_CONFIG", cand_path)
    monkeypatch.setattr(promo, "EVOLVED_REPORT", report_path)
    monkeypatch.setattr(promo, "EVOLVED_CONFIG", cfg_path)
    monkeypatch.setattr(promo, "CANDIDATE_CONFIG", cand_path)

    results = [
        {
            "query": {"alias": "PTBP1"},
            "mode": "retrieval_only",
            "donors": [{"alias": "U2AF2", "score": 0.9, "metric": "domain_overlap"}],
            "retrieval": {"domain": {"ok": True, "n": 1}},
            "evidence_table": [
                {"alias": "U2AF2", "score": 0.9, "sim_by_modality": {"domain_overlap": 0.9}},
            ],
            "verdict": {
                "label": "No",
                "p_hat": None,
                "confidence": "low",
                "explanation": "stub",
                "supporting_rbps": [{"alias": "U2AF2", "similarity_score": 0.9}],
            },
        }
    ]
    held = {
        "PTBP1": [
            [{"alias": "U2AF2", "score": 0.9, "metric": "domain_overlap"}]
        ]
    }
    report = run_self_evolution(
        results,
        held_to_hit_lists=held,
        write_config=True,
        require_loo_report=False,
        allow_retrieval_only=True,
    )
    d = report.to_dict()
    assert "abstain_retune" in d
    assert d["abstain_retune"].get("status") in ("ok", "skipped")
    if d["abstain_retune"].get("status") == "ok":
        assert cand_path.is_file()
        text = cand_path.read_text(encoding="utf-8")
        assert "abstain_thresholds" in text


def test_proposal_tools_include_evolve():
    from app.backends.delivery.registry import PROPOSAL_TOOL_NAMES, build_proposal_tools

    assert "lookup_proxy_cache" in PROPOSAL_TOOL_NAMES
    assert "fuse_similarity_views" in PROPOSAL_TOOL_NAMES
    from app.backends.delivery.registry import STAGE_RAW_WHITELIST

    assert "rna_blastn" in STAGE_RAW_WHITELIST
    names = {t.name for t in build_proposal_tools()}
    assert "lookup_proxy_cache" in names
    assert "fuse_similarity_views" in names
