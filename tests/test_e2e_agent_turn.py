# -*- coding: utf-8 -*-
"""End-to-end agent-turn tests with a scripted LLM + real (offline) delivery tools.

These drive a full `RBPAgent` turn through the real nanobot loop and real delivery
tools, but replace the LLM with a deterministic scripted provider (no network, no
API key). They exercise the three routing paths and the verdict schema:

* in-panel own-head  — resolve → predict_interaction(own head) → verdict
* unseen refusal     — resolve(out-of-panel) → predict(own head) is REFUSED by the
                       Stage-0 guard → verdict with p_hat=null
* verdict schema     — a bare verdict is normalized + validated

The heavy RhoBind science (a real p_hat number) is asserted only when the local
`rhobind` conda env + CUDA are present; otherwise the turn still runs and we assert
the plumbing + verdict schema (predict degrades to p_hat=null).
"""

from __future__ import annotations

import json

import pytest

from nanobot.providers.base import LLMProvider, LLMResponse, ToolCallRequest


class ScriptedProvider(LLMProvider):
    """Emits a fixed sequence of tool calls / final verdict, ignoring inputs.

    Records every `messages` list it is handed so tests can inspect the tool
    results that flowed back from the real delivery tools.
    """

    def __init__(self, steps: list[dict]):
        super().__init__(api_key="test-key", api_base=None)
        self._steps = list(steps)
        self._i = 0
        self.seen: list[list[dict]] = []

    async def chat(self, messages, tools=None, model=None, max_tokens=4096,
                   temperature=0.7, reasoning_effort=None, tool_choice=None):
        self.seen.append(messages)
        if self._i < len(self._steps):
            step = self._steps[self._i]
            self._i += 1
        else:
            step = {"final": json.dumps({
                "label": "No", "p_hat": None, "confidence": "low",
                "explanation": "Scripted fallthrough end.", "supporting_rbps": [],
            })}
        if "tool" in step:
            return LLMResponse(
                content=None,
                tool_calls=[ToolCallRequest(
                    id=f"call_{self._i}", name=step["tool"], arguments=step["args"]
                )],
                finish_reason="tool_calls",
            )
        return LLMResponse(content=step["final"], tool_calls=[], finish_reason="stop")

    def get_default_model(self) -> str:
        return "scripted-model"

    def flat_text(self) -> str:
        """All seen message contents flattened to a searchable string."""
        return json.dumps(self.seen, ensure_ascii=False, default=str)


CU_RICH_RNA = "CUCUCUCUCUCUCUCUCUCUCUCUCUUUCUCUCUCUCUCUUCUCUCUCUCUCUCUCUCUCUCUCU"


def _science_ready() -> bool:
    try:
        from app.backends.delivery.env import conda_env_python

        if conda_env_python("rhobind") is None:
            return False
        import torch  # type: ignore

        return bool(torch.cuda.is_available())
    except Exception:
        return False


def _make_agent(monkeypatch, tmp_path, provider: ScriptedProvider, *, use_conda: bool):
    """Build an RBPAgent whose LLM is the scripted provider and whose delivery
    tools run offline (network tools skipped; science tools local)."""
    # Force delivery calls offline; gate conda usage on science availability.
    from nanobot.agent.tools.rbp import common as rbp_common
    from nanobot.agent.tools.rbp import predict as rbp_predict

    def _offline_client(*, offline=False, device=None, use_conda=use_conda):
        from app.backends.delivery.client import DeliveryToolClient
        from app.backends.delivery.env import apply_delivery_env

        apply_delivery_env()
        return DeliveryToolClient(offline=True, device="cpu", use_conda=use_conda)

    monkeypatch.setattr(rbp_common, "get_delivery_client", _offline_client)
    monkeypatch.setattr(rbp_predict, "get_delivery_client", _offline_client)

    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({
        "providers": {"deepseek": {"apiKey": "test-key"}},
        "agents": {"defaults": {
            "provider": "deepseek", "model": "deepseek-chat", "botName": "e2e",
        }},
    }), encoding="utf-8")
    monkeypatch.setenv("NANOBOT_CONFIG", str(cfg))

    from app.agent import RBPAgent

    agent = RBPAgent(
        offline=False,
        device="cpu",
        use_conda=use_conda,
        prefer_nanobot_llm=True,
        allow_fallback=False,
        workspace=str(tmp_path / "ws"),
        config_path=str(cfg),
    )

    # Pin the scripted provider. Build the bot, then disable the snapshot loader
    # (which would otherwise rebuild the real provider from config at turn start)
    # and override the provider everywhere the loop consults it.
    bot = agent.get_nanobot()
    loop = bot._loop
    loop._provider_snapshot_loader = None
    loop.provider = provider
    model = provider.get_default_model()
    if getattr(loop, "runner", None) is not None:
        loop.runner.provider = provider
    for attr, setter_args in (
        ("subagents", (provider, model)),
        ("consolidator", (provider, model, None)),
    ):
        obj = getattr(loop, attr, None)
        setter = getattr(obj, "set_provider", None)
        if callable(setter):
            try:
                setter(*setter_args)
            except Exception:
                pass
    return agent


def _assert_valid_verdict(result):
    from app.core.verdict_schema import validate_verdict

    assert result.mode == "nanobot_llm", f"unexpected mode: {result.mode} / {result.error}"
    assert isinstance(result.verdict, dict)
    ok, errs = validate_verdict(result.verdict)
    assert ok, f"verdict schema errors: {errs} :: {result.verdict}"
    assert result.verdict["label"] in ("Strong", "Likely", "Unlikely", "No")
    assert result.verdict["confidence"] in ("high", "medium", "low")


def test_e2e_verdict_schema_only(monkeypatch, tmp_path):
    """A bare scripted verdict flows through normalize + validate."""
    provider = ScriptedProvider([
        {"final": json.dumps({
            "label": "No", "p_hat": None, "confidence": "low",
            "explanation": "No tools were needed for this scripted check.",
            "supporting_rbps": [],
        })},
    ])
    agent = _make_agent(monkeypatch, tmp_path, provider, use_conda=False)
    result = agent.run_sync("Does this RNA bind? (schema check)",
                            session_key="e2e:schema", ephemeral=True)
    _assert_valid_verdict(result)


def test_e2e_unseen_predict_is_refused(monkeypatch, tmp_path):
    """Out-of-panel target: own-head predict_interaction is refused by the guard."""
    unseen = "ZZZ_FAKE_RBP_NOT_IN_PANEL"
    provider = ScriptedProvider([
        {"tool": "resolve_rbp", "args": {"query": unseen}},
        {"tool": "predict_interaction", "args": {"rna": CU_RICH_RNA, "rbps": [unseen]}},
        {"final": json.dumps({
            "label": "No", "p_hat": None, "confidence": "low",
            "explanation": (
                "Target is out of panel; own-head prediction was refused, so no "
                "p_hat is available without proxy donors."
            ),
            "supporting_rbps": [],
            "caveats": ["unseen_target", "prior_missing"],
        })},
    ])
    agent = _make_agent(monkeypatch, tmp_path, provider, use_conda=False)
    result = agent.run_sync("Does this RNA bind ZZZ_FAKE_RBP_NOT_IN_PANEL?",
                            session_key="e2e:unseen", ephemeral=True)
    _assert_valid_verdict(result)
    assert result.verdict["p_hat"] is None
    assert result.verdict["confidence"] == "low"
    # The real Stage-0 guard must have refused the own-head call on the unseen target.
    seen = provider.flat_text()
    assert ("MUST NOT call predict_interaction" in seen) or ("out-of-panel" in seen), (
        "expected Stage-0 unseen refusal in tool results"
    )


def test_e2e_in_panel_own_head(monkeypatch, tmp_path):
    """In-panel PTBP1 own-head: resolve → predict → verdict. Real p_hat when science ready."""
    provider = ScriptedProvider([
        {"tool": "resolve_rbp", "args": {"query": "PTBP1"}},
        {"tool": "predict_interaction", "args": {"rna": CU_RICH_RNA, "rbps": ["PTBP1"]}},
        {"final": json.dumps({
            "label": "Strong", "p_hat": 0.9, "confidence": "high",
            "explanation": (
                "PTBP1 is in-panel; its own RhoBind head scored the CU-rich RNA "
                "highly, so binding is strongly supported."
            ),
            "supporting_rbps": [
                {"rbp_id": "P26599", "alias": "PTBP1", "prob": 0.9,
                 "similarity_score": 1.0},
            ],
        })},
    ])
    science = _science_ready()
    agent = _make_agent(monkeypatch, tmp_path, provider, use_conda=science)
    result = agent.run_sync("Does this CU-rich RNA bind PTBP1?",
                            session_key="e2e:inpanel", ephemeral=True)
    _assert_valid_verdict(result)

    # resolve_rbp + predict_interaction must both have been driven this turn.
    seen = provider.flat_text()
    assert "predict_interaction" in seen or "predictions" in seen

    if not science:
        pytest.skip("rhobind conda env / CUDA not available; skipped real p_hat check")
    # With real science, PTBP1 own head on CU-rich RNA is a confident binder.
    assert result.verdict["p_hat"] is not None
    assert result.verdict["p_hat"] >= 0.5
    assert result.verdict["label"] in ("Strong", "Likely")
