# -*- coding: utf-8 -*-
"""Chat UX helpers (product CLI chrome)."""

from __future__ import annotations

import asyncio
from typing import Any, cast

from app.core.chat_ux import (
    CHAT_HELP,
    ThinkingSpinner,
    _color_label,
    _peek_verdict_label,
    print_chat_header,
    print_status_panel,
    print_turn_footer,
    print_verdict_block,
)


def test_help_lists_core_commands():
    for cmd in ("/help", "/status", "/tools", "/quit", "/thinking", "/caveats"):
        assert cmd in CHAT_HELP


def test_verdict_label_peek_and_color():
    body = '{\n  "label": "Strong",\n  "p_hat": 0.9\n}'
    assert _peek_verdict_label(body) == "Strong"
    from app.core.chat_ux import Style
    import io

    s = Style(io.StringIO())
    s.on = False
    assert "Strong" in _color_label("Strong", s)


def test_spinner_status_phases():
    sp = ThinkingSpinner(bot_name="rbp-agent")
    sp._enabled = False
    sp.update("thinking")
    t1 = sp._status_text()
    assert "Thinking" in t1
    sp.update("seq_similarity")
    t2 = sp._status_text()
    assert "seq_similarity" in t2
    # update with same hint must be a no-op (anti-flicker)
    sp.update("seq_similarity")
    assert sp._hint == "seq_similarity"


def test_spinner_start_accepts_wait_hint():
    sp = ThinkingSpinner(bot_name="rbp-agent")
    sp._enabled = False
    # Disabled spinner does not thread, but start() still returns early —
    # exercise hint formatting via update + status_text.
    sp.update("waiting for 3 tools")
    text = sp._status_text()
    assert "waiting for 3 tools" in text
    assert "s" in text


def test_trace_hook_starts_wait_spinner_during_tools():
    from types import SimpleNamespace

    from app.core.chat_ux import make_agent_trace_hook

    sp = ThinkingSpinner(bot_name="rbp-agent")
    sp._enabled = False
    started: list[tuple] = []

    def _fake_start(hint=None, *, reset_clock=False):
        started.append((hint, reset_clock))
        sp._active = True
        sp._hint = (hint or "Thinking")

    def _fake_stop():
        sp._active = False

    sp.start = _fake_start  # type: ignore[method-assign]
    sp.stop = _fake_stop  # type: ignore[method-assign]

    hook = make_agent_trace_hook(spinner=sp, show_args=False)
    ctx = SimpleNamespace(
        response=SimpleNamespace(content=""),
        streamed_reasoning=True,
        tool_calls=[
            SimpleNamespace(name="seq_similarity", arguments={}),
            SimpleNamespace(name="domain_architecture", arguments={}),
        ],
        tool_results=[],
        tool_events=[],
        iteration=0,
    )
    asyncio.run(hook.before_execute_tools(ctx))
    assert started, "wait spinner should start after tool list"
    hint, reset = started[-1]
    assert hint == "waiting for 2 tools"
    assert reset is True

    asyncio.run(hook.after_iteration(ctx))
    assert started[-1][0] == "Thinking"


def test_print_chrome_no_crash():
    import io

    header = io.StringIO()
    print_chat_header(
        llm_summary="deepseek / test",
        n_tools=12,
        skill_ok=True,
        session_key="chat-test",
        stream=header,
    )
    shown = header.getvalue()
    assert "RNA–RBP Agent" in shown
    assert "nanobot · delivery tools · Stage 0–3" in shown
    print_status_panel(
        llm_summary="deepseek / test",
        n_tools=12,
        session_key="chat-test",
        skill_ok=True,
        stream=io.StringIO(),
    )
    print_verdict_block(
        '{"label":"Likely","p_hat":0.6,"confidence":"low"}',
        stream=io.StringIO(),
    )
    print_turn_footer(
        elapsed_s=1.23, mode="nanobot_llm", n_tools=3, stream=io.StringIO()
    )


def test_banner_title_centered(monkeypatch):
    import io

    from app.core import chat_ux

    monkeypatch.setattr(chat_ux, "_term_width", lambda default=72: 72)
    stream = io.StringIO()
    chat_ux.print_banner(stream=stream)
    lines = stream.getvalue().splitlines()
    title = next(ln for ln in lines if "RNA–RBP Agent" in ln)
    subtitle = next(ln for ln in lines if "nanobot · delivery tools" in ln)
    assert title.lstrip().startswith("✶")
    assert "Stage 0–3" in subtitle
    # Centered (not left-indented with fixed "  "); leading pad from width.
    assert title.startswith(" ")
    assert subtitle.startswith(" ")
    assert title.index("✶") == (72 - chat_ux._visible_len("✶ RNA–RBP Agent")) // 2


def test_verdict_prints_evidence_before_verdict():
    import io
    from types import SimpleNamespace

    from app.core.chat_ux import format_verdict_display

    result = SimpleNamespace(
        content='{"p_hat":0.99}',
        verdict={
            "label": "Likely",
            "p_hat": 0.61,
            "confidence": "medium",
            "score_source": "delivery_similarity_weighted_vote",
            "explanation": "Grounded transfer result.",
            "supporting_rbps": [],
            "caveats": ["prior_missing"],
            "score_kind": "weighted_consensus",
            "score_disclaimer": (
                "multi-donor weighted consensus; not a calibrated binding probability"
            ),
            "mode": "multi_head",
            "score_provenance": {
                "aggregation": {
                    "terms": [
                        {
                            "donor": "FMR1",
                            "similarity": 0.9,
                            "prob": 0.7,
                            "transfer_prior": None,
                            "weight": 0.8,
                        }
                    ]
                }
            },
        },
    )
    stream = io.StringIO()
    print_verdict_block(format_verdict_display(result), stream=stream)
    shown = stream.getvalue()
    assert shown.index("▸ evidence") < shown.index("▸ verdict")
    assert "FMR1" in shown
    assert "confidence=medium" in shown
    assert "prior_missing" in shown
    assert "caveats: 1 (folded)" in shown
    assert '"p_hat": 0.61' in shown
    # path/mode is chrome-only (title + path=…), not public JSON.
    assert "path=multi_head" in shown
    assert '"mode"' not in shown
    # Folded: caveats key omitted from pretty JSON body.
    assert '"caveats"' not in shown
    # Engineering / provenance keys must not appear in user-facing chat output.
    for banned in (
        "score_source",
        "score_kind",
        "score_disclaimer",
        "weighted_consensus",
        "delivery_similarity_weighted_vote",
        "calibrated binding probability",
    ):
        assert banned not in shown, f"public verdict leaked {banned!r}"
    # Footer must not reintroduce score chrome.
    assert "score=" not in shown
    assert "disclaimer=" not in shown


def test_print_verdict_block_shows_rna_placeholder_banner():
    import io
    import json

    from app.core.chat_ux import print_verdict_block

    body = json.dumps(
        {
            "label": "Likely",
            "p_hat": 0.6,
            "confidence": "medium",
            "explanation": "demo path",
            "caveats": ["rna_placeholder"],
            "mode": "multi_head",
        }
    )
    stream = io.StringIO()
    print_verdict_block(body, stream=stream)
    shown = stream.getvalue()
    assert "PLACEHOLDER" in shown or "not experimental gold" in shown
    assert "rna_placeholder" in shown


def test_print_verdict_block_folds_caveats_by_default(monkeypatch):
    import io
    import json

    from app.core.chat_ux import format_caveats_fold_line, print_verdict_block

    monkeypatch.delenv("RBP_SHOW_CAVEATS", raising=False)
    caveats = [
        "prior_missing",
        "structure_axis_unavailable",
        "literature_unavailable",
        "domain_empty",
        "near_match_loo_disclosed",
        "single_donor_transfer",
        "rna_placeholder",
    ]
    fold = format_caveats_fold_line(caveats)
    assert "caveats: 7 (folded)" in fold
    assert "prior_missing" in fold
    assert "structure_axis_unavailable" in fold
    assert "expand: RBP_SHOW_CAVEATS=1" in fold
    assert "single_donor_transfer" not in fold  # only first 2 previewed

    body = json.dumps(
        {
            "label": "Likely",
            "p_hat": 0.6,
            "confidence": "low",
            "explanation": "demo",
            "caveats": caveats,
            "mode": "multi_head",
        }
    )
    stream = io.StringIO()
    print_verdict_block(body, stream=stream)
    shown = stream.getvalue()
    assert "caveats: 7 (folded)" in shown
    assert "expand: RBP_SHOW_CAVEATS=1" in shown
    # Full array not dumped into the pretty JSON body when folded.
    assert '"caveats"' not in shown
    assert "PLACEHOLDER" in shown or "not experimental gold" in shown


def test_print_verdict_block_expands_caveats_with_env(monkeypatch):
    import io
    import json

    from app.core.chat_ux import print_verdict_block

    monkeypatch.setenv("RBP_SHOW_CAVEATS", "1")
    caveats = [
        "prior_missing",
        "structure_axis_unavailable",
        "literature_unavailable",
        "domain_empty",
        "near_match_loo_disclosed",
    ]
    body = json.dumps(
        {
            "label": "Likely",
            "p_hat": 0.6,
            "confidence": "low",
            "explanation": "demo",
            "caveats": caveats,
        }
    )
    stream = io.StringIO()
    print_verdict_block(body, stream=stream)
    shown = stream.getvalue()
    assert '"caveats"' in shown
    for c in caveats:
        assert c in shown
    assert "(folded)" not in shown


def test_format_verdict_display_keeps_full_caveats_array():
    """Structured formatter still carries the full caveats list (fold is print-only)."""
    import json
    from types import SimpleNamespace

    from app.core.chat_ux import format_verdict_display

    caveats = [f"c{i}" for i in range(6)]
    shown = format_verdict_display(
        SimpleNamespace(
            content="",
            verdict={
                "label": "Likely",
                "p_hat": 0.5,
                "confidence": "low",
                "explanation": "demo",
                "supporting_rbps": [],
                "caveats": caveats,
            },
        )
    )
    parsed = json.loads(shown)
    assert parsed.get("caveats") == caveats


def test_format_verdict_display_omits_engineering_fields():
    from types import SimpleNamespace

    from app.core.chat_ux import format_verdict_display

    result = SimpleNamespace(
        content="",
        verdict={
            "label": "Likely",
            "p_hat": 0.61,
            "confidence": "medium",
            "score_source": "delivery_similarity_weighted_vote",
            "score_kind": "weighted_consensus",
            "score_disclaimer": "multi-donor weighted consensus",
            "mode": "multi_head",
            "explanation": "Grounded transfer result.",
            "supporting_rbps": [],
            "caveats": ["literature_unavailable"],
        },
    )
    shown = format_verdict_display(result)
    for banned in (
        "score_source",
        "score_kind",
        "score_disclaimer",
        "weighted_consensus",
    ):
        assert banned not in shown
    # mode is passed through for print_verdict_block chrome; JSON body strip is there.
    assert '"mode": "multi_head"' in shown
    assert '"confidence": "medium"' in shown
    assert "literature_unavailable" in shown
