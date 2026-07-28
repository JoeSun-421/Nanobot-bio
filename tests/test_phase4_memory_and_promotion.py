# -*- coding: utf-8 -*-
"""Focused Phase 4/4b grounding and promotion-gate tests."""

from __future__ import annotations

import asyncio
import hashlib
import json

import pytest
import yaml


def test_scientific_context_excludes_personal_memory_and_scopes_history(tmp_path):
    from nanobot.agent.context import ContextBuilder

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "AGENTS.md").write_text("scientific instructions", encoding="utf-8")
    (workspace / "USER.md").write_text("PERSONAL USER SECRET", encoding="utf-8")

    builder = ContextBuilder(workspace, scientific_mode=True)
    builder.memory.write_memory("PERSONAL MEMORY SECRET")
    builder.memory.append_history("same-session fact", session_key="science:one")
    builder.memory.append_history("other-session fact", session_key="science:two")

    prompt = builder.build_system_prompt(
        session_key="science:one",
        unified_session=False,
    )
    assert "scientific instructions" in prompt
    assert "PERSONAL USER SECRET" not in prompt
    assert "PERSONAL MEMORY SECRET" not in prompt
    assert "same-session fact" in prompt
    assert "other-session fact" not in prompt

    no_key = builder.build_system_prompt(session_key="", unified_session=False)
    unified = builder.build_system_prompt(
        session_key="science:one",
        unified_session=True,
    )
    assert "# Recent History" not in no_key
    assert "# Recent History" not in unified


def test_scientific_nanobot_disables_automatic_consolidation(tmp_path):
    from nanobot import Nanobot

    config = tmp_path / "config.json"
    config.write_text(
        json.dumps(
            {
                "providers": {"deepseek": {"apiKey": "test-key"}},
                "agents": {
                    "defaults": {
                        "provider": "deepseek",
                        "model": "deepseek-chat",
                        "unifiedSession": True,
                        "dream": {"enabled": True},
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    bot = Nanobot.from_config(
        config_path=config,
        workspace=tmp_path / "workspace",
        scientific_mode=True,
    )
    assert bot._loop._scientific_mode is True
    assert bot._loop._automatic_memory_consolidation is False
    assert bot._loop._unified_session is False
    assert bot._config.agents.defaults.dream.enabled is False


def test_ephemeral_scientific_turn_does_not_persist(tmp_path):
    from nanobot import Nanobot

    config = tmp_path / "config.json"
    config.write_text(
        json.dumps(
            {
                "providers": {"deepseek": {"apiKey": "test-key"}},
                "agents": {
                    "defaults": {
                        "provider": "deepseek",
                        "model": "deepseek-chat",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    bot = Nanobot.from_config(
        config_path=config,
        workspace=tmp_path / "workspace",
        scientific_mode=True,
    )
    loop = bot._loop
    session = loop.sessions.get_or_create("science:ephemeral")
    session.add_message("user", "persisted before")
    session.add_message("assistant", "existing answer")
    loop.sessions.save(session)
    before = [dict(message) for message in session.messages]

    async def fake_run(*args, **kwargs):
        return ("ephemeral answer", [], list(args[0]), "completed", False)

    loop._run_agent_loop = fake_run
    response = asyncio.run(
        loop.process_direct(
            "do not persist me",
            session_key="science:ephemeral",
            ephemeral=True,
        )
    )
    assert response is not None
    assert response.content == "ephemeral answer"
    after = loop.sessions.get_or_create("science:ephemeral")
    assert after.messages == before


def test_proxy_cache_is_trace_promoted_domain_memory(tmp_path):
    from rbp_eval.evolve.proxy_cache import promote_from_traces

    cache = tmp_path / "proxy_map.json"
    traces = [
        {
            "type": "query_end",
            "alias": "NSUN2",
            "donors": [{"alias": "NOP2"}, {"alias": "NSUN5"}],
        },
        {
            "type": "query_end",
            "alias": "NSUN2",
            "donors": [{"alias": "NOP2"}, {"alias": "NSUN5"}],
        },
    ]
    data = promote_from_traces(traces, path=cache, promote_after=2)
    assert data["role"] == "domain_memory"
    assert data["promotion"]["updater"] == "promote_from_traces"
    assert data["promotion"]["eligible"] == 2
    assert data["entries"]["alias:NSUN2"]["promoted"] is True


def _write_promotion_reports(
    root,
    *,
    candidate_sha,
    candidate_path,
    real=True,
    n=10,
    delta=0.05,
):
    source_input = root / "held.jsonl"
    source_input.write_text('{"case_id":"held:1"}\n', encoding="utf-8")
    source_sha = hashlib.sha256(source_input.read_bytes()).hexdigest()
    (root / "eval_loo_report.json").write_text(
        json.dumps(
            {
                "n": 10,
                "summary": {"n_ok": 10},
                "rows": [{"held_rbp": f"R{i}"} for i in range(10)],
            }
        ),
        encoding="utf-8",
    )
    (root / "evaluation_plan_report.json").write_text(
        json.dumps(
            {
                "held_out_split": {"n_held": 2, "held_out_rbps": ["V1", "V2"]},
                "primary_metrics": {"transfer_level": {"auprc": 0.7}},
            }
        ),
        encoding="utf-8",
    )
    (root / "evolve_eval_decision.json").write_text(
        json.dumps(
            {
                "schema": "evolve_decision/v1",
                "decision": "PROMOTE",
                "n": n,
                "delta_auprc": delta,
            }
        ),
        encoding="utf-8",
    )
    (root / "transfer_calibration.json").write_text(
        json.dumps(
            {
                "schema": "transfer_calibration.v1",
                "source_manifest": {
                    "score_source": "real_rhobind" if real else "synthetic",
                    "reference_score_source": "real_rhobind_own_head",
                    "synthetic": not real,
                    "inputs": [{"path": "held.jsonl", "sha256": source_sha}],
                },
                "split_manifest": {
                    "train_ids": ["T1", "T2"],
                    "validation_ids": ["V1", "V2"],
                },
                "objective": {"name": "delta_auprc"},
                "before_after_metrics": {
                    "baseline": {"auprc": 0.60},
                    "candidate": {"auprc": 0.65},
                },
                "promotion_metric": {
                    "name": "delta_auprc",
                    "score_source": "real_rhobind",
                    "n": n,
                    "value": delta,
                },
                "policy_manifest": {
                    "candidate_path": str(candidate_path),
                    "candidate_sha256": candidate_sha,
                },
                "rollback": {
                    "candidate_path": str(candidate_path),
                    "live_path": "config/evolved.yaml",
                },
            }
        ),
        encoding="utf-8",
    )


def test_promote_requires_real_transfer_metric_and_manifests(tmp_path):
    from rbp_eval.evolve.promote import promote_evolved_config

    reports = tmp_path / "reports"
    reports.mkdir()
    candidate = tmp_path / "candidate.yaml"
    live = tmp_path / "live.yaml"
    candidate.write_text(
        yaml.safe_dump(
            {
                "candidate": True,
                "evolved": False,
                "fusion_weights": {"rna_peak_homology": 0.0},
            }
        ),
        encoding="utf-8",
    )
    candidate_sha = hashlib.sha256(candidate.read_bytes()).hexdigest()
    _write_promotion_reports(
        reports,
        candidate_sha=candidate_sha,
        candidate_path=candidate,
    )

    assert promote_evolved_config(
        candidate=candidate,
        live=live,
        reports_dir=reports,
    ) == live

    _write_promotion_reports(
        reports,
        candidate_sha=candidate_sha,
        candidate_path=candidate,
        real=False,
    )
    with pytest.raises(ValueError, match="real_rhobind"):
        promote_evolved_config(
            candidate=candidate,
            live=live,
            reports_dir=reports,
        )


@pytest.mark.parametrize(
    ("n", "delta", "message"),
    [(9, 0.05, "n<10"), (10, 0.0, "delta_auprc<=0")],
)
def test_promote_retains_n_and_delta_gates(tmp_path, n, delta, message):
    from rbp_eval.evolve.promote import assert_legacy_evolve_decision

    report = tmp_path / "decision.json"
    report.write_text(
        json.dumps(
            {
                "decision": "PROMOTE",
                "n": n,
                "delta_auprc": delta,
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match=message):
        assert_legacy_evolve_decision(report)


def test_transfer_promotion_builder_uses_real_phase2_reports(tmp_path):
    from rbp_eval.evolve.transfer_promotion import build_promotion_report

    def write_report(path, auprc):
        rows = [
            {
                "status": "scored",
                "aggregation_source": "delivery_similarity_weighted_vote",
                "own_head_prob": 0.8,
            }
            for _ in range(12)
        ]
        path.write_text(
            json.dumps(
                {
                    "schema": "transfer_calibration.v1",
                    "regimes": {
                        "true_unseen": {
                            "n_scored": len(rows),
                            "metrics": {"all_scored": {"auprc": auprc}},
                            "rows": rows,
                        }
                    },
                }
            ),
            encoding="utf-8",
        )

    baseline = tmp_path / "baseline.json"
    candidate = tmp_path / "candidate.json"
    policy = tmp_path / "candidate.yaml"
    live = tmp_path / "live.yaml"
    write_report(baseline, 0.60)
    write_report(candidate, 0.66)
    policy.write_text("candidate: true\n", encoding="utf-8")
    report = build_promotion_report(
        baseline_report=baseline,
        candidate_report=candidate,
        candidate_policy=policy,
        train_ids=["T1", "T2"],
        validation_ids=["V1"],
        live_policy=live,
    )
    assert report["decision"] == "PROMOTE"
    assert report["promotion_metric"]["n"] == 12
    assert report["promotion_metric"]["value"] == pytest.approx(0.06)
    assert report["source_manifest"]["synthetic"] is False

