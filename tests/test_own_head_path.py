# -*- coding: utf-8 -*-
"""Stage-0 own-head contract (delivery BUILD_SPEC §4 / examples)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_skill_always_on_and_own_head_playbook(tmp_path):
    from app.integrate import ensure_workspace_skill
    from nanobot.agent.skills import SkillsLoader

    skill = ROOT / "nanobot" / "skills" / "rbp-agent" / "SKILL.md"
    text = skill.read_text(encoding="utf-8")
    assert text.startswith("---")
    assert "always: true" in text
    assert "in_panel" in text
    assert "own-head" in text.lower() or "OWN HEAD" in text
    assert "STOP" in text

    ensure_workspace_skill(tmp_path)
    loader = SkillsLoader(tmp_path, builtin_skills_dir=ROOT / "nanobot" / "skills")
    always = loader.get_always_skills()
    assert "rbp-agent" in always


def test_delivery_example_pos_rna_matches_readme():
    from app.backends.delivery.examples import load_example, own_head_prompt

    ex = load_example("pos")
    assert ex["query"] == "PTBP1"
    assert ex["uniprot"] == "P26599"
    assert ex["path"] == "own_head"
    assert len(ex["rna"]) == 128
    assert ex["rna"].startswith("TTTTGTGGTTGAAAATC")
    prompt = own_head_prompt("pos")
    assert "PTBP1" in prompt
    assert "own-head" in prompt.lower()
    assert ex["rna"] in prompt


def test_resolve_ptbp1_in_panel():
    from app.backends.delivery.client import DeliveryToolClient

    r = DeliveryToolClient(offline=True, use_conda=False).call(
        "resolve_rbp", {"query": "PTBP1"}
    )
    assert r.get("in_panel") is True
    assert r.get("alias") == "PTBP1"
    assert r.get("uniprot") == "P26599"
    assert "K562" in (r.get("head_index") or {})


def test_predict_envelope_marks_own_head_path():
    """Unit-level: tool success payload includes path=own_head for single alias."""
    import asyncio
    import json
    from unittest.mock import patch

    from nanobot.agent.tools.rbp.predict import PredictInteractionTool

    PredictInteractionTool.reset_turn_guards()
    tool = PredictInteractionTool()

    fake = {
        "ok": True,
        "predictions": [{"alias": "PTBP1", "prob": 0.966, "head_index": 73, "cohort": "K562"}],
        "cohort": "K562",
        "n_windows": 1,
        "_script": "predict_api.py",
    }

    class _Cli:
        def call(self, name, payload):
            assert name == "rhobind_predict"
            assert payload["rbps"] == ["PTBP1"]
            return fake

    with patch(
        "nanobot.agent.tools.rbp.predict.get_delivery_client",
        return_value=_Cli(),
    ):
        out = asyncio.run(
            tool.execute(rna="ACGU" * 32, rbp_id="PTBP1", cohort="K562")
        )
    env = json.loads(out)
    assert env["status"] == "ok"
    assert env["value"]["path"] == "own_head"
    assert "OWN-HEAD" in env["value"]["stop_hint"]


def test_near_match_without_donor_falls_back_to_multi_head_vote():
    """near_match flag alone (no headed donor) stays multi_head weighted vote."""
    import asyncio
    import json
    from unittest.mock import patch

    from nanobot.agent.tools.rbp.predict import PredictInteractionTool
    from nanobot.agent.tools.rbp import turn_guards

    PredictInteractionTool.reset_turn_guards()
    turn_guards.set_fused_proxies(
        [
            {
                "alias": "U2AF2",
                "score": 0.8,
                "vote_similarity": 0.9635,
                "sim_by_modality": {"esmc_cosine": 0.9635},
            },
            {
                "alias": "QKI",
                "score": 0.7,
                "vote_similarity": 0.9572,
                "sim_by_modality": {"esmc_cosine": 0.9572},
            },
        ]
    )
    turn_guards.set_committed_proxies(turn_guards.fused_proxies())
    turn_guards.mark_abstain_done()
    turn_guards.add_evidence_flag("near_match", True)
    # No near_match_donor → weighted consensus on multi_head (not own_head).

    class _Cli:
        def call(self, name, payload):
            if name == "rhobind_predict":
                return {
                    "ok": True,
                    "predictions": [
                        {"alias": "U2AF2", "prob": 0.1},
                        {"alias": "QKI", "prob": 0.2},
                    ],
                    "cohort": "K562",
                    "n_windows": 1,
                }
            if name in ("transfer_prior_lookup", "donor_quality_prior"):
                return {"ok": False, "error": "not available in unit test"}
            if name == "similarity_weighted_vote":
                return {
                    "ok": True,
                    "score": 0.15,
                    "contributions": [
                        {
                            "donor": "U2AF2",
                            "similarity": 0.9635,
                            "prob": 0.1,
                            "weight": 0.9635,
                        }
                    ],
                }
            raise AssertionError(name)

    with patch(
        "nanobot.agent.tools.rbp.predict.get_delivery_client",
        return_value=_Cli(),
    ):
        raw = asyncio.run(
            PredictInteractionTool().execute(
                rna="ACGU" * 32,
                rbps=["U2AF2", "QKI"],
                cohort="K562",
                force_transfer=True,
            )
        )
    env = json.loads(raw)
    assert env["status"] == "ok"
    assert env["value"]["path"] == "multi_head"
    auth = turn_guards.authoritative_score()
    assert auth is not None
    assert auth["mode"] == "multi_head"
    assert auth["score_kind"] == "weighted_consensus"
    assert auth["p_hat"] == 0.15


def test_near_match_donor_head_promotes_to_own_head():
    """Headed near_match donor → own_head Fast Path when force_transfer is not set."""
    import asyncio
    import json
    from unittest.mock import patch

    from app.core.verdict_schema import normalize_verdict_with_turn_state
    from nanobot.agent.tools.rbp.predict import PredictInteractionTool
    from nanobot.agent.tools.rbp import turn_guards

    PredictInteractionTool.reset_turn_guards()
    turn_guards.set_fused_proxies(
        [
            {
                "alias": "PTBP1",
                "score": 1.0,
                "vote_similarity": 1.0,
                "sim_by_modality": {"esmc_cosine": 1.0},
            },
            {
                "alias": "U2AF2",
                "score": 0.8,
                "vote_similarity": 0.9635,
                "sim_by_modality": {"esmc_cosine": 0.9635},
            },
        ]
    )
    turn_guards.set_committed_proxies(turn_guards.fused_proxies())
    turn_guards.mark_abstain_done()
    turn_guards.add_evidence_flag("near_match", True)
    turn_guards.add_evidence_flag("near_match_donor", "PTBP1")

    predict_payloads: list[dict] = []

    class _Cli:
        def call(self, name, payload):
            if name == "rhobind_predict":
                predict_payloads.append(dict(payload))
                return {
                    "ok": True,
                    "predictions": [
                        {"alias": "PTBP1", "prob": 0.966, "head_index": 73},
                    ],
                    "cohort": "K562",
                    "n_windows": 1,
                }
            raise AssertionError(f"should not call {name} on near-match own-head")

    with patch(
        "nanobot.agent.tools.rbp.predict.get_delivery_client",
        return_value=_Cli(),
    ), patch(
        "nanobot.agent.tools.rbp.turn_guards.alias_has_panel_head",
        side_effect=lambda q, cohort="K562": str(q).casefold() == "ptbp1",
    ):
        raw = asyncio.run(
            PredictInteractionTool().execute(
                rna="ACGU" * 32,
                rbps=["PTBP1", "U2AF2"],
                cohort="K562",
            )
        )
    env = json.loads(raw)
    assert env["status"] == "ok"
    assert env["value"]["path"] == "own_head"
    assert env["value"]["prob"] == 0.966
    assert env["value"]["score_kind"] == "own_head"
    assert env["value"].get("near_match_promoted") is True
    assert predict_payloads and predict_payloads[0]["rbps"] == ["PTBP1"]
    assert turn_guards.evidence_flags().get("near_match_own_head") is True
    auth = turn_guards.authoritative_score()
    assert auth is not None
    assert auth["p_hat"] == 0.966
    assert auth["mode"] == "own_head"
    assert auth["source"] == "delivery_rhobind_predict"
    assert auth["score_kind"] == "own_head"

    verdict = normalize_verdict_with_turn_state(
        {
            "label": "Unlikely",
            "p_hat": 0.1,
            "score_kind": "weighted_consensus",
            "explanation": "llm attempt",
        }
    )
    assert verdict["p_hat"] == 0.966
    assert verdict["mode"] == "own_head"
    assert verdict["score_kind"] == "own_head"


def test_force_transfer_single_foreign_donor_succeeds():
    """LOO: force_transfer + single foreign donor is valid multi_head transfer."""
    import asyncio
    import json
    from unittest.mock import patch

    from nanobot.agent.tools.rbp.predict import PredictInteractionTool
    from nanobot.agent.tools.rbp import turn_guards

    PredictInteractionTool.reset_turn_guards()
    turn_guards.set_canonical_request(
        {"alias": "FXR2", "uniprot": "P51116", "cohort": "K562"}
    )
    turn_guards.set_fused_proxies(
        [
            {
                "alias": "HNRNPU",
                "score": 0.85,
                "vote_similarity": 0.85,
                "sim_by_modality": {"esmc_cosine": 0.85},
            }
        ]
    )
    turn_guards.set_committed_proxies(
        [
            {
                "alias": "HNRNPU",
                "similarity_score": 0.85,
                "vote_similarity": 0.85,
            }
        ]
    )
    turn_guards.mark_abstain_done()
    # In-panel / near-match-to-self must not block foreign-donor LOO.
    turn_guards.add_evidence_flag("near_match", True)
    turn_guards.add_evidence_flag("near_match_donor", "FXR2")

    predict_payloads: list[dict] = []

    class _Cli:
        def call(self, name, payload):
            if name == "rhobind_predict":
                predict_payloads.append(dict(payload))
                return {
                    "ok": True,
                    "predictions": [{"alias": "HNRNPU", "prob": 0.42}],
                    "cohort": "K562",
                    "n_windows": 1,
                }
            if name in ("transfer_prior_lookup", "donor_quality_prior"):
                return {"ok": False, "error": "skip"}
            if name == "similarity_weighted_vote":
                return {
                    "ok": True,
                    "score": 0.42,
                    "contributions": [
                        {
                            "donor": "HNRNPU",
                            "similarity": 0.85,
                            "prob": 0.42,
                            "weight": 0.85,
                        }
                    ],
                }
            raise AssertionError(name)

    with patch(
        "nanobot.agent.tools.rbp.predict.get_delivery_client",
        return_value=_Cli(),
    ), patch(
        "nanobot.agent.tools.rbp.turn_guards.alias_has_panel_head",
        side_effect=lambda q, cohort="K562": str(q).casefold()
        in ("fxr2", "hnrnpu"),
    ), patch(
        "nanobot.agent.tools.rbp.turn_guards.alias_has_cohort_head",
        side_effect=lambda q, cohort="K562": str(q).casefold()
        in ("fxr2", "hnrnpu"),
    ):
        raw = asyncio.run(
            PredictInteractionTool().execute(
                rna="ACGU" * 32,
                rbps=["HNRNPU"],
                cohort="K562",
                force_transfer=True,
            )
        )
    env = json.loads(raw)
    assert env["status"] == "ok", env
    assert env["value"]["path"] == "multi_head"
    assert env["value"]["prob"] == 0.42
    assert env["value"].get("near_match_promoted") is not True
    assert predict_payloads and predict_payloads[0]["rbps"] == ["HNRNPU"]
    assert turn_guards.evidence_flags().get("single_donor_transfer") is True
    assert turn_guards.evidence_flags().get("near_match_own_head") is None
    auth = turn_guards.authoritative_score()
    assert auth is not None
    assert auth["mode"] == "multi_head"
    assert auth["score_kind"] == "weighted_consensus"
    assert auth["p_hat"] == 0.42


def test_force_transfer_refuses_query_alias_alone():
    """force_transfer + rbps=[query itself] is own-head disguised — refuse."""
    import asyncio
    import json
    from unittest.mock import patch

    from nanobot.agent.tools.rbp.predict import PredictInteractionTool
    from nanobot.agent.tools.rbp import turn_guards

    PredictInteractionTool.reset_turn_guards()
    turn_guards.set_canonical_request(
        {"alias": "FXR2", "uniprot": "P51116", "cohort": "K562"}
    )
    turn_guards.add_evidence_flag("near_match", True)
    turn_guards.add_evidence_flag("near_match_donor", "FXR2")
    turn_guards.mark_fuse_done()
    turn_guards.set_committed_proxies(
        [{"alias": "HNRNPU", "similarity_score": 0.8, "vote_similarity": 0.8}]
    )
    turn_guards.mark_abstain_done()

    with patch(
        "nanobot.agent.tools.rbp.predict.get_delivery_client"
    ) as delivery, patch(
        "nanobot.agent.tools.rbp.turn_guards.alias_has_panel_head",
        return_value=True,
    ):
        raw = asyncio.run(
            PredictInteractionTool().execute(
                rna="ACGU" * 32,
                rbps=["FXR2"],
                cohort="K562",
                force_transfer=True,
            )
        )
    delivery.assert_not_called()
    env = json.loads(raw)
    assert env["status"] == "error"
    reason = str(env.get("reason") or env.get("error") or "").lower()
    assert "own-head" in reason or "foreign donor" in reason


def test_force_transfer_near_match_to_self_does_not_own_head_promote():
    """near_match donor == query under force_transfer stays multi_head on foreign donors."""
    import asyncio
    import json
    from unittest.mock import patch

    from nanobot.agent.tools.rbp.predict import PredictInteractionTool
    from nanobot.agent.tools.rbp import turn_guards

    PredictInteractionTool.reset_turn_guards()
    turn_guards.set_canonical_request(
        {"alias": "FXR2", "uniprot": "P51116", "cohort": "K562"}
    )
    turn_guards.set_fused_proxies(
        [
            {
                "alias": "FXR2",
                "score": 1.0,
                "vote_similarity": 1.0,
                "sim_by_modality": {"esmc_cosine": 1.0},
            },
            {
                "alias": "HNRNPU",
                "score": 0.8,
                "vote_similarity": 0.8,
                "sim_by_modality": {"esmc_cosine": 0.8},
            },
        ]
    )
    turn_guards.set_committed_proxies(
        [
            {
                "alias": "HNRNPU",
                "similarity_score": 0.8,
                "vote_similarity": 0.8,
            }
        ]
    )
    turn_guards.mark_abstain_done()
    turn_guards.add_evidence_flag("near_match", True)
    turn_guards.add_evidence_flag("near_match_donor", "FXR2")

    predict_payloads: list[dict] = []

    class _Cli:
        def call(self, name, payload):
            if name == "rhobind_predict":
                predict_payloads.append(dict(payload))
                return {
                    "ok": True,
                    "predictions": [
                        {"alias": "FXR2", "prob": 0.987},
                        {"alias": "HNRNPU", "prob": 0.33},
                    ],
                    "cohort": "K562",
                    "n_windows": 1,
                }
            if name in ("transfer_prior_lookup", "donor_quality_prior"):
                return {"ok": False, "error": "skip"}
            if name == "similarity_weighted_vote":
                assert all(
                    c["donor"].casefold() != "fxr2"
                    for c in payload.get("predictions") or []
                )
                return {
                    "ok": True,
                    "score": 0.33,
                    "contributions": [
                        {
                            "donor": "HNRNPU",
                            "similarity": 0.8,
                            "prob": 0.33,
                            "weight": 0.8,
                        }
                    ],
                }
            raise AssertionError(name)

    with patch(
        "nanobot.agent.tools.rbp.predict.get_delivery_client",
        return_value=_Cli(),
    ), patch(
        "nanobot.agent.tools.rbp.turn_guards.alias_has_panel_head",
        side_effect=lambda q, cohort="K562": str(q).casefold()
        in ("fxr2", "hnrnpu"),
    ), patch(
        "nanobot.agent.tools.rbp.turn_guards.alias_has_cohort_head",
        side_effect=lambda q, cohort="K562": str(q).casefold()
        in ("fxr2", "hnrnpu"),
    ):
        raw = asyncio.run(
            PredictInteractionTool().execute(
                rna="ACGU" * 32,
                rbps=["FXR2", "HNRNPU"],
                cohort="K562",
                force_transfer=True,
            )
        )
    env = json.loads(raw)
    assert env["status"] == "ok"
    assert env["value"]["path"] == "multi_head"
    assert env["value"].get("near_match_promoted") is not True
    assert env["value"]["prob"] == 0.33
    assert turn_guards.evidence_flags().get("near_match_own_head") is None
    assert predict_payloads and predict_payloads[0]["rbps"] == ["HNRNPU"]
    assert "fxr2" in {
        x.casefold()
        for x in (turn_guards.evidence_flags().get("force_transfer_excluded_self") or [])
    }


def test_near_match_with_force_transfer_stays_multi_head():
    """PTBP1-like near_match + force_transfer=true stays multi_head (not own_head)."""
    import asyncio
    import json
    from unittest.mock import patch

    from nanobot.agent.tools.rbp.predict import PredictInteractionTool
    from nanobot.agent.tools.rbp import turn_guards

    PredictInteractionTool.reset_turn_guards()
    turn_guards.set_query_target("QueryProtein_A")
    turn_guards.set_fused_proxies(
        [
            {
                "alias": "PTBP1",
                "score": 1.0,
                "vote_similarity": 1.0,
                "sim_by_modality": {"esmc_cosine": 1.0},
            },
            {
                "alias": "U2AF2",
                "score": 0.8,
                "vote_similarity": 0.9635,
                "sim_by_modality": {"esmc_cosine": 0.9635},
            },
        ]
    )
    turn_guards.set_committed_proxies(
        [
            {
                "alias": "U2AF2",
                "similarity_score": 0.9635,
                "vote_similarity": 0.9635,
            }
        ]
    )
    turn_guards.mark_abstain_done()
    turn_guards.add_evidence_flag("near_match", True)
    turn_guards.add_evidence_flag("near_match_donor", "PTBP1")

    predict_payloads: list[dict] = []

    class _Cli:
        def call(self, name, payload):
            if name == "rhobind_predict":
                predict_payloads.append(dict(payload))
                return {
                    "ok": True,
                    "predictions": [
                        {"alias": "U2AF2", "prob": 0.2},
                    ],
                    "cohort": "K562",
                    "n_windows": 1,
                }
            if name in ("transfer_prior_lookup", "donor_quality_prior"):
                return {"ok": False, "error": "skip"}
            if name == "similarity_weighted_vote":
                return {
                    "ok": True,
                    "score": 0.2,
                    "contributions": [
                        {
                            "donor": "U2AF2",
                            "similarity": 0.9635,
                            "prob": 0.2,
                            "weight": 0.9635,
                        }
                    ],
                }
            raise AssertionError(name)

    with patch(
        "nanobot.agent.tools.rbp.predict.get_delivery_client",
        return_value=_Cli(),
    ), patch(
        "nanobot.agent.tools.rbp.turn_guards.alias_has_panel_head",
        side_effect=lambda q, cohort="K562": str(q).casefold() in ("ptbp1", "u2af2"),
    ), patch(
        "nanobot.agent.tools.rbp.turn_guards.alias_has_cohort_head",
        side_effect=lambda q, cohort="K562": str(q).casefold() in ("ptbp1", "u2af2"),
    ):
        raw = asyncio.run(
            PredictInteractionTool().execute(
                rna="ACGU" * 32,
                rbps=["PTBP1", "U2AF2"],
                cohort="K562",
                force_transfer=True,
            )
        )
    env = json.loads(raw)
    assert env["status"] == "ok"
    assert env["value"]["path"] == "multi_head"
    assert env["value"].get("near_match_promoted") is not True
    assert env["value"]["prob"] == 0.2
    assert turn_guards.force_transfer_active() is True
    assert turn_guards.evidence_flags().get("near_match_own_head") is None
    assert predict_payloads and predict_payloads[0]["rbps"] == ["U2AF2"]
    auth = turn_guards.authoritative_score()
    assert auth is not None
    assert auth["mode"] == "multi_head"
    assert auth["score_kind"] == "weighted_consensus"
    assert auth["source"] == "delivery_similarity_weighted_vote"


def test_near_match_donor_without_head_falls_back_to_vote():
    """near_match donor without a panel head → multi_head weighted vote."""
    import asyncio
    import json
    from unittest.mock import patch

    from nanobot.agent.tools.rbp.predict import PredictInteractionTool
    from nanobot.agent.tools.rbp import turn_guards

    PredictInteractionTool.reset_turn_guards()
    turn_guards.set_fused_proxies(
        [
            {
                "alias": "NOHEAD",
                "score": 1.0,
                "vote_similarity": 1.0,
                "sim_by_modality": {"esmc_cosine": 1.0},
            },
            {
                "alias": "U2AF2",
                "score": 0.8,
                "vote_similarity": 0.9635,
                "sim_by_modality": {"esmc_cosine": 0.9635},
            },
        ]
    )
    turn_guards.set_committed_proxies(turn_guards.fused_proxies())
    turn_guards.mark_abstain_done()
    turn_guards.add_evidence_flag("near_match", True)
    turn_guards.add_evidence_flag("near_match_donor", "NOHEAD")

    class _Cli:
        def call(self, name, payload):
            if name == "rhobind_predict":
                return {
                    "ok": True,
                    "predictions": [
                        {"alias": "NOHEAD", "prob": None, "error": "no head"},
                        {"alias": "U2AF2", "prob": 0.2},
                    ],
                    "cohort": "K562",
                    "n_windows": 1,
                }
            if name in ("transfer_prior_lookup", "donor_quality_prior"):
                return {"ok": False, "error": "skip"}
            if name == "similarity_weighted_vote":
                return {
                    "ok": True,
                    "score": 0.2,
                    "contributions": [
                        {
                            "donor": "U2AF2",
                            "similarity": 0.9635,
                            "prob": 0.2,
                            "weight": 0.9635,
                        }
                    ],
                }
            raise AssertionError(name)

    with patch(
        "nanobot.agent.tools.rbp.predict.get_delivery_client",
        return_value=_Cli(),
    ), patch(
        "nanobot.agent.tools.rbp.turn_guards.alias_has_panel_head",
        return_value=False,
    ):
        raw = asyncio.run(
            PredictInteractionTool().execute(
                rna="ACGU" * 32,
                rbps=["NOHEAD", "U2AF2"],
                cohort="K562",
                force_transfer=True,
            )
        )
    env = json.loads(raw)
    assert env["status"] == "ok"
    assert env["value"]["path"] == "multi_head"
    assert env["value"]["prob"] == 0.2
    assert env["value"].get("near_match_promoted") is not True
    auth = turn_guards.authoritative_score()
    assert auth is not None
    assert auth["mode"] == "multi_head"
    assert auth["score_kind"] == "weighted_consensus"
    assert auth["source"] == "delivery_similarity_weighted_vote"
    assert "near_match_donor_no_head" not in (turn_guards.evidence_flags() or {})
    assert "near_match_own_head" not in (turn_guards.evidence_flags() or {})


def test_commit_forces_near_match_donor_when_llm_omits_it():
    import asyncio
    import json

    from nanobot.agent.tools.rbp.commit_proxies import CommitProxyCandidatesTool
    from nanobot.agent.tools.rbp.turn_guards import (
        committed_proxies,
        reset_stage_guards,
        set_fused_proxies,
        add_evidence_flag,
    )

    reset_stage_guards()
    set_fused_proxies(
        [
            {
                "alias": "PTBP1",
                "score": 1.0,
                "vote_similarity": 1.0,
                "sim_by_modality": {"esmc_cosine": 1.0},
            },
            {
                "alias": "U2AF2",
                "score": 0.9,
                "vote_similarity": 0.96,
                "sim_by_modality": {"esmc_cosine": 0.96},
            },
        ]
    )
    add_evidence_flag("near_match", True)
    add_evidence_flag("near_match_donor", "PTBP1")
    raw = asyncio.run(
        CommitProxyCandidatesTool().execute(
            candidates=[{"alias": "U2AF2"}],
            tau_drop=0.30,
            n_cand=5,
        )
    )
    obj = json.loads(raw)
    assert obj["status"] == "ok"
    aliases = {c["alias"] for c in committed_proxies()}
    assert "PTBP1" in aliases
    assert "U2AF2" in aliases


def test_commit_skips_near_match_donor_when_force_transfer_active():
    import asyncio
    import json

    from nanobot.agent.tools.rbp.commit_proxies import CommitProxyCandidatesTool
    from nanobot.agent.tools.rbp.turn_guards import (
        committed_proxies,
        reset_stage_guards,
        set_fused_proxies,
        add_evidence_flag,
    )

    reset_stage_guards()
    set_fused_proxies(
        [
            {
                "alias": "PTBP1",
                "score": 1.0,
                "vote_similarity": 1.0,
                "sim_by_modality": {"esmc_cosine": 1.0},
            },
            {
                "alias": "U2AF2",
                "score": 0.9,
                "vote_similarity": 0.96,
                "sim_by_modality": {"esmc_cosine": 0.96},
            },
        ]
    )
    add_evidence_flag("near_match", True)
    add_evidence_flag("near_match_donor", "PTBP1")
    raw = asyncio.run(
        CommitProxyCandidatesTool().execute(
            candidates=[{"alias": "U2AF2"}],
            tau_drop=0.30,
            n_cand=5,
            force_transfer=True,
        )
    )
    obj = json.loads(raw)
    assert obj["status"] == "ok"
    aliases = {c["alias"] for c in committed_proxies()}
    assert "PTBP1" not in aliases
    assert "U2AF2" in aliases
    from nanobot.agent.tools.rbp.turn_guards import evidence_flags

    flags = evidence_flags() or {}
    assert flags.get("near_match_loo_disclosed") is True
    assert "near_match_donor_no_head" not in flags


def test_sticky_loo_user_message_refuses_target_without_predict_force_transfer_kwarg():
    """User LOO intent seeds loo_force_transfer; predict on target alone is refused."""
    import asyncio
    import json
    from unittest.mock import patch

    from nanobot.agent.tools.rbp.annotation import prepare_tool_turn_guards
    from nanobot.agent.tools.rbp.predict import PredictInteractionTool
    from nanobot.agent.tools.rbp import turn_guards

    prepare_tool_turn_guards(
        "DROSHA LOO leave-one-out force transfer — treat as unseen, no own-head"
    )
    turn_guards.set_canonical_request(
        {"alias": "DROSHA", "uniprot": "Q9NRR4", "cohort": "K562"}
    )
    turn_guards.add_evidence_flag("near_match", True)
    turn_guards.add_evidence_flag("near_match_donor", "DROSHA")
    assert turn_guards.force_transfer_active() is True

    with patch(
        "nanobot.agent.tools.rbp.predict.get_delivery_client"
    ) as delivery, patch(
        "nanobot.agent.tools.rbp.turn_guards.alias_has_panel_head",
        return_value=True,
    ):
        raw = asyncio.run(
            PredictInteractionTool().execute(
                rna="ACGU" * 32,
                rbp_id="DROSHA",
                cohort="K562",
            )
        )
    delivery.assert_not_called()
    env = json.loads(raw)
    assert env["status"] == "error"
    reason = str(env.get("reason") or env.get("error") or "").lower()
    assert "own-head" in reason or "foreign donor" in reason or "loo" in reason


def test_sticky_loo_foreign_donor_multi_head_without_predict_force_transfer_kwarg():
    """Sticky LOO + rbps=[foreign] succeeds as multi_head without predict force_transfer kwarg."""
    import asyncio
    import json
    from unittest.mock import patch

    from nanobot.agent.tools.rbp.annotation import prepare_tool_turn_guards
    from nanobot.agent.tools.rbp.predict import PredictInteractionTool
    from nanobot.agent.tools.rbp import turn_guards

    prepare_tool_turn_guards("FXR2 LOO force transfer treat as unseen")
    turn_guards.set_canonical_request(
        {"alias": "FXR2", "uniprot": "P51116", "cohort": "K562"}
    )
    turn_guards.set_fused_proxies(
        [
            {
                "alias": "HNRNPU",
                "score": 0.8,
                "vote_similarity": 0.8,
                "sim_by_modality": {"esmc_cosine": 0.8},
            }
        ]
    )
    turn_guards.set_committed_proxies(
        [{"alias": "HNRNPU", "similarity_score": 0.8, "vote_similarity": 0.8}]
    )
    turn_guards.mark_abstain_done()
    turn_guards.add_evidence_flag("near_match", True)
    turn_guards.add_evidence_flag("near_match_donor", "FXR2")

    class _Cli:
        def call(self, name, payload):
            if name == "rhobind_predict":
                return {
                    "ok": True,
                    "predictions": [{"alias": "HNRNPU", "prob": 0.42, "cohort": "K562"}],
                    "cohort": "K562",
                }
            if name == "similarity_weighted_vote":
                return {"ok": True, "score": 0.42, "contributions": []}
            if name in ("transfer_prior_lookup", "donor_quality_prior"):
                return {"ok": True, "priors": {}, "quality": {}}
            return {"ok": True}

    with patch(
        "nanobot.agent.tools.rbp.predict.get_delivery_client",
        return_value=_Cli(),
    ), patch(
        "nanobot.agent.tools.rbp.turn_guards.alias_has_cohort_head",
        return_value=True,
    ), patch(
        "nanobot.agent.tools.rbp.turn_guards.alias_has_panel_head",
        return_value=True,
    ):
        raw = asyncio.run(
            PredictInteractionTool().execute(
                rna="ACGU" * 32,
                rbps=["HNRNPU"],
                cohort="K562",
            )
        )
    env = json.loads(raw)
    assert env["status"] == "ok"
    assert env["value"]["path"] == "multi_head"
    assert env["value"].get("near_match_promoted") is not True


def test_loo_overrides_stage0_stop_for_retrieve_tools():
    """force_transfer / loo_force_transfer must not block retrieve after own-head mistake."""
    from nanobot.agent.tools.rbp import turn_guards

    turn_guards.reset_stage_guards()
    turn_guards.set_force_transfer_active(True, source="user_message")
    turn_guards.mark_own_head_success()
    assert turn_guards.retrieve_blocked_reason("seq_similarity") is None
    assert turn_guards.retrieve_blocked_reason("fuse_similarity_views") is None
    blocked = turn_guards.commit_blocked_reason() or ""
    assert "Stage 0 STOP" not in blocked
    blocked_abs = turn_guards.abstain_blocked_reason() or ""
    assert "Stage 0 STOP" not in blocked_abs


def test_skill_documents_loo_overrides_stage0_stop():
    skill = (ROOT / "nanobot" / "skills" / "rbp-agent" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    stages = (
        ROOT / "nanobot" / "skills" / "rbp-agent" / "references" / "stages.md"
    ).read_text(encoding="utf-8")
    assert "Operator LOO overrides Stage 0 STOP" in skill
    assert "Stage 0 own-head STOP is overridden" in stages
    assert "unless" in skill.lower() and "force_transfer" in skill


def test_workspace_skill_sync_copies_always_frontmatter(tmp_path):
    from app.integrate import ensure_workspace_skill

    dest = ensure_workspace_skill(tmp_path)
    text = dest.read_text(encoding="utf-8")
    assert "always: true" in text or '"always": true' in text
    agents = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    assert "in_panel" in agents
    assert "own-head" in agents.lower() or "own head" in agents.lower()
    assert "LOO" in agents or "force_transfer" in agents
