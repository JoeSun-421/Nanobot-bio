# -*- coding: utf-8 -*-
"""P0 transfer fidelity: cohort heads, donor floors and fragile verdicts."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import patch

from app.backends.delivery.registry import _normalize_delivery_payload
from app.core.verdict_schema import normalize_verdict
from nanobot.agent.tools.rbp import turn_guards
from nanobot.agent.tools.rbp.commit_proxies import CommitProxyCandidatesTool
from nanobot.agent.tools.rbp.evolve_tools import FuseSimilarityViewsTool
from nanobot.agent.tools.rbp.predict import PredictInteractionTool
from rbp_eval.scoring.head_index import (
    alias_has_cohort_head,
    cohort_head_aliases,
)


def _ready_for_fuse(cohort: str = "HepG2") -> None:
    turn_guards.reset_stage_guards()
    turn_guards.set_canonical_request({"cohort": cohort, "alias": "FUS"})
    turn_guards.mark_retrieve_done("seq_similarity")
    turn_guards.mark_retrieve_done("structure_fetch")
    turn_guards.mark_retrieve_done("domain_architecture")


def test_head_lookup_is_cohort_strict():
    hepg2 = cohort_head_aliases("HepG2")
    k562 = cohort_head_aliases("K562")
    assert "TAF15" in hepg2 and "TAF15" in k562
    assert "SF3B1" in k562 and "SF3B1" not in hepg2
    assert "IGF2BP3" in hepg2 and "IGF2BP3" not in k562
    assert alias_has_cohort_head("O75533", cohort="K562") is True
    assert alias_has_cohort_head("O75533", cohort="HepG2") is False


def test_product_fuse_filters_wrong_cohort_donors():
    _ready_for_fuse("HepG2")
    raw = asyncio.run(
        FuseSimilarityViewsTool().execute(
            cohort="HepG2",
            hits_emb=[
                {"alias": "SF3B1", "score": 0.95, "metric": "esmc_cosine"},
                {"alias": "TAF15", "score": 0.90, "metric": "esmc_cosine"},
            ],
        )
    )
    value = json.loads(raw)["value"]
    assert [row["alias"] for row in value["donors"]] == ["TAF15"]
    assert value["n_filtered_unheaded"] == 1
    assert value["cohort"] == "HepG2"


def test_commit_defense_filters_wrong_cohort_and_weak_donors():
    turn_guards.reset_stage_guards()
    turn_guards.set_canonical_request({"cohort": "HepG2", "alias": "FUS"})
    turn_guards.set_fused_proxies(
        [
            {
                "alias": "SF3B1",
                "score": 0.9,
                "vote_similarity": 0.9,
                "sim_by_modality": {"esmc_cosine": 0.9},
            },
            {
                "alias": "TAF15",
                "score": 0.8,
                "vote_similarity": 0.8,
                "sim_by_modality": {"esmc_cosine": 0.8},
            },
            {
                "alias": "U2AF2",
                "score": 0.34,
                "vote_similarity": 0.34,
                "sim_by_modality": {"esmc_cosine": 0.34},
            },
        ]
    )
    raw = asyncio.run(
        CommitProxyCandidatesTool().execute(
            candidates=[
                {"alias": "SF3B1"},
                {"alias": "TAF15"},
                {"alias": "U2AF2"},
            ]
        )
    )
    value = json.loads(raw)["value"]
    assert [row["alias"] for row in value["candidates"]] == ["TAF15"]
    assert value["n_filtered_unheaded"] == 1
    assert value["min_vote_similarity"] == 0.35


def test_predict_filters_heads_then_low_quality_before_vote(monkeypatch):
    PredictInteractionTool.reset_turn_guards()
    turn_guards.set_canonical_request({"cohort": "HepG2", "alias": "FUS"})
    proxies = [
        {"alias": "SF3B1", "similarity_score": 0.95},
        {"alias": "TAF15", "similarity_score": 0.90},
        {"alias": "U2AF2", "similarity_score": 0.85},
    ]
    turn_guards.set_fused_proxies(proxies)
    turn_guards.set_committed_proxies(proxies)
    turn_guards.mark_abstain_done()

    monkeypatch.setattr(
        "nanobot.agent.tools.rbp.common.get_runtime_config",
        lambda: {
            "cohort": "HepG2",
            "integrate": {
                "require_cohort_head": True,
                "use_transfer_prior": False,
                "use_donor_quality": True,
                "min_donor_quality": 0.5,
            },
            "predict": {"aggregate": "weighted"},
        },
    )

    class _Client:
        def call(self, name, payload):
            if name == "rhobind_predict":
                assert payload["rbps"] == ["TAF15", "U2AF2"]
                return {
                    "ok": True,
                    "cohort": "HepG2",
                    "n_windows": 1,
                    "predictions": [
                        {"alias": "TAF15", "prob": 0.8},
                        {"alias": "U2AF2", "prob": 0.2},
                    ],
                }
            if name == "donor_quality_prior":
                return {
                    "ok": True,
                    "quality": [
                        {"donor": "TAF15", "mt_all_auprc": 0.7},
                        {"donor": "U2AF2", "mt_all_auprc": 0.4},
                    ],
                }
            if name == "similarity_weighted_vote":
                assert [p["donor"] for p in payload["predictions"]] == ["TAF15"]
                assert [h["alias"] for h in payload["hits"]] == ["TAF15"]
                return {"ok": True, "score": 0.8, "contributions": []}
            raise AssertionError(name)

    with patch(
        "nanobot.agent.tools.rbp.predict.get_delivery_client",
        return_value=_Client(),
    ):
        raw = asyncio.run(
            PredictInteractionTool().execute(
                rna="ACGU" * 32,
                rbps=["SF3B1", "TAF15", "U2AF2"],
                cohort="HepG2",
                force_transfer=True,
            )
        )
    value = json.loads(raw)["value"]
    assert value["prob"] == 0.8
    flags = turn_guards.evidence_flags()
    assert flags["n_filtered_unheaded"] == 1
    assert flags["n_filtered_low_donor_quality"] == 1
    assert flags["single_donor_transfer"] is True


def test_predict_returns_null_when_no_cohort_heads(monkeypatch):
    PredictInteractionTool.reset_turn_guards()
    turn_guards.set_canonical_request({"cohort": "HepG2", "alias": "FUS"})
    proxies = [
        {"alias": "SF3B1", "similarity_score": 0.9},
        {"alias": "FUS", "similarity_score": 0.8},
    ]
    turn_guards.set_fused_proxies(proxies)
    turn_guards.set_committed_proxies(proxies)
    turn_guards.mark_abstain_done()

    with patch(
        "nanobot.agent.tools.rbp.predict.get_delivery_client"
    ) as delivery:
        raw = asyncio.run(
            PredictInteractionTool().execute(
                rna="ACGU" * 32,
                rbps=["SF3B1", "FUS"],
                cohort="HepG2",
                force_transfer=True,
            )
        )
    delivery.assert_not_called()
    value = json.loads(raw)["value"]
    assert value["prob"] is None
    assert value["aggregation"]["error"] == "no_headed_donors"
    assert turn_guards.evidence_flags()["no_headed_donors"] is True


def test_predict_votes_only_top_two_committed_donors():
    PredictInteractionTool.reset_turn_guards()
    turn_guards.set_canonical_request({"cohort": "K562", "alias": "FUS"})
    proxies = [
        {"alias": "TAF15", "similarity_score": 0.95},
        {"alias": "U2AF2", "similarity_score": 0.90},
        {"alias": "MATR3", "similarity_score": 0.80},
    ]
    turn_guards.set_fused_proxies(proxies)
    turn_guards.set_committed_proxies(proxies)
    turn_guards.mark_abstain_done()

    class _Client:
        def call(self, name, payload):
            if name == "rhobind_predict":
                return {
                    "ok": True,
                    "cohort": "K562",
                    "n_windows": 1,
                    "predictions": [
                        {"alias": "TAF15", "prob": 0.9},
                        {"alias": "U2AF2", "prob": 0.8},
                        {"alias": "MATR3", "prob": 0.1},
                    ],
                }
            if name in {"transfer_prior_lookup", "donor_quality_prior"}:
                return {"ok": False, "error": "not available"}
            if name == "similarity_weighted_vote":
                assert [row["alias"] for row in payload["hits"]] == [
                    "TAF15",
                    "U2AF2",
                ]
                assert [row["donor"] for row in payload["predictions"]] == [
                    "TAF15",
                    "U2AF2",
                ]
                return {"ok": True, "score": 0.85, "contributions": []}
            raise AssertionError(name)

    with patch(
        "nanobot.agent.tools.rbp.predict.get_delivery_client",
        return_value=_Client(),
    ):
        raw = asyncio.run(
            PredictInteractionTool().execute(
                rna="ACGU" * 32,
                rbps=["TAF15", "U2AF2", "MATR3"],
                cohort="K562",
                force_transfer=True,
            )
        )
    assert json.loads(raw)["value"]["prob"] == 0.85
    assert turn_guards.evidence_flags()["n_filtered_vote_tail"] == 1


def test_domain_payload_injects_canonical_identifier():
    turn_guards.reset_stage_guards()
    turn_guards.set_canonical_request(
        {"cohort": "K562", "alias": "PTBP1", "uniprot": "P26599"}
    )
    payload = _normalize_delivery_payload(
        "domain_architecture",
        {"sequence": "M" * 100},
    )
    assert payload["alias"] == "PTBP1"
    assert payload["uniprot"] == "P26599"
    assert payload.get("network") is not True


def test_fragile_single_donor_caps_label_and_confidence():
    out = normalize_verdict(
        {
            "label": "Strong",
            "p_hat": 0.92,
            "confidence": "high",
            "explanation": "transfer",
            "evidence_flags": {
                "single_donor_transfer": True,
                "domain_empty": True,
            },
        }
    )
    assert out["label"] == "Likely"
    assert out["confidence"] == "low"
    assert "single_donor_transfer" in out["caveats"]


def test_no_headed_donors_forces_null_no_verdict():
    out = normalize_verdict(
        {
            "label": "Strong",
            "p_hat": 0.99,
            "confidence": "high",
            "explanation": "unsupported",
            "evidence_flags": {"no_headed_donors": True},
        }
    )
    assert out["label"] == "No"
    assert out["p_hat"] is None
    assert out["confidence"] == "low"
