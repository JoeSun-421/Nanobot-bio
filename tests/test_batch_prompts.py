# -*- coding: utf-8 -*-
"""Unit tests for outer-loop batch prompts + truncated-tool-markup hardening."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PROMPTS_MD = ROOT / "docs" / "eval" / "UNSEEN_RBP_TEST_PROMPTS_20.md"
TRANSFER_MD = ROOT / "docs" / "eval" / "transfer_test_prompts.md"


def test_parse_unseen_20_prompts():
    from rbp_eval.accept.batch_prompts import parse_prompt_cases

    assert PROMPTS_MD.is_file(), f"missing {PROMPTS_MD}"
    cases = parse_prompt_cases(PROMPTS_MD)
    assert len(cases) == 20
    assert cases[0].gene == "FUS"
    assert cases[0].case_id == "01"
    assert "OUT-OF-PANEL" in cases[0].message
    assert cases[-1].gene == "NPM1"
    genes = [c.gene for c in cases]
    assert len(set(genes)) == 20


def test_parse_transfer_test_prompts():
    from rbp_eval.accept.batch_prompts import parse_prompt_cases

    assert TRANSFER_MD.is_file(), f"missing {TRANSFER_MD}"
    cases = parse_prompt_cases(TRANSFER_MD)
    assert len(cases) == 20
    assert cases[0].prompt_id == "01"
    assert cases[0].case_id == "01"
    assert cases[0].gene == "PTBP1"
    assert "force transfer" in cases[0].message.lower() or "Force the transfer" in cases[0].message
    assert cases[-1].gene == "RPS6"
    genes = [c.gene for c in cases]
    # Transfer suite reuses panel genes across cases
    assert "PTBP1" in genes and "FXR2" in genes and "DROSHA" in genes


def test_batch_prompts_dry_run(tmp_path):
    from rbp_eval.accept.batch_prompts import run_batch_prompts

    report = run_batch_prompts(
        prompts_md=PROMPTS_MD,
        out_dir=tmp_path,
        dry_run=True,
        limit=3,
    )
    assert report["ok"] is True
    assert report["dry_run"] is True
    assert report["n_cases"] == 3
    jsonl = Path(report["jsonl"])
    assert jsonl.is_file()
    rows = [json.loads(line) for line in jsonl.read_text(encoding="utf-8").splitlines() if line]
    assert len(rows) == 3
    assert rows[0]["gene"] == "FUS"


def test_resolve_stream_flag_and_batch_stream_runner(tmp_path, capsys):
    """Suite runner accepts stream=True and invokes turn_runner (no live LLM)."""
    from rbp_eval.accept.batch_prompts import resolve_stream_flag, run_batch_prompts

    assert resolve_stream_flag(True) is True
    assert resolve_stream_flag(False) is False

    calls: list[dict] = []

    def fake_turn(agent, message, *, session_key, stream):
        calls.append(
            {
                "agent": agent,
                "session_key": session_key,
                "stream": stream,
                "chars": len(message),
            }
        )
        return SimpleNamespace(
            content='{"label":"Yes","p_hat":0.91,"confidence":"high",'
            '"explanation":"mock","supporting_rbps":[]}',
            mode="nanobot_llm",
            verdict={
                "label": "Yes",
                "p_hat": 0.91,
                "confidence": "high",
                "explanation": "mock",
                "supporting_rbps": [],
                "mode": "transfer",
            },
            verdict_valid=True,
            verdict_errors=[],
            tools_used=["resolve_rbp"],
            stop_reason="completed",
            error=None,
        )

    report = run_batch_prompts(
        prompts_md=TRANSFER_MD,
        out_dir=tmp_path,
        limit=2,
        stream=True,
        turn_runner=fake_turn,
    )
    assert report["ok"] is True
    assert report["stream"] is True
    assert report["n_cases"] == 2
    assert report["n_ok"] == 2
    assert len(calls) == 2
    assert all(c["stream"] is True for c in calls)
    assert all(c["agent"] is None for c in calls)  # injected runner skips RBPAgent
    assert calls[0]["session_key"].startswith("batch-prompt:")
    # Case banner for streamed path
    err = capsys.readouterr().err
    assert "[1/2] Prompt 01 — PTBP1" in err
    assert "[2/2] Prompt 02" in err

    quiet = run_batch_prompts(
        prompts_md=TRANSFER_MD,
        out_dir=tmp_path,
        limit=1,
        stream=False,
        turn_runner=fake_turn,
    )
    assert quiet["stream"] is False
    assert calls[-1]["stream"] is False


def test_run_prompt_suite_tool_dry_run(tmp_path):
    from nanobot.agent.tools.rbp.prompt_suite import RunPromptSuiteTool, run_prompt_suite

    out = run_prompt_suite(
        path=str(TRANSFER_MD),
        out_dir=str(tmp_path),
        dry_run=True,
        limit=2,
    )
    assert out["ok"] is True
    assert out["n_cases"] == 2
    assert out["runner"] == "batch_prompts.v1"
    assert Path(out["jsonl"]).is_file()

    tool = RunPromptSuiteTool()
    assert tool.name == "run_prompt_suite"
    raw = asyncio.run(
        tool.execute(path=str(PROMPTS_MD), dry_run=True, limit=1, out_dir=str(tmp_path))
    )
    payload = json.loads(raw)
    assert payload["status"] == "ok"
    assert payload["value"]["n_cases"] == 1


def test_extract_suite_path_from_chat_messages():
    from nanobot.agent.tools.rbp.prompt_suite import (
        extract_suite_path_candidate,
        is_prompt_suite_request,
    )

    assert extract_suite_path_candidate("docs/eval/UNSEEN_RBP_TEST_PROMPTS_20.md")
    assert extract_suite_path_candidate(
        "run this file: docs/eval/transfer_test_prompts.md"
    )
    assert extract_suite_path_candidate(
        "/suite docs/eval/transfer_test_prompts.md --dry-run"
    )
    # Single fenced case paste must not short-circuit
    pasted = (
        "```text\nTransfer validation\nProtein sequence:\nMAAA\n"
        "RNA:\nACGU\n```"
    )
    assert extract_suite_path_candidate(pasted) is None
    assert is_prompt_suite_request("docs/eval/UNSEEN_RBP_TEST_PROMPTS_20.md") is True
    assert is_prompt_suite_request(pasted) is False


def test_parse_suite_message_last_three_chinese_user_style():
    """Exact user-style paste: path + 读取最后三条… must select last 3, not all 20."""
    from nanobot.agent.tools.rbp.prompt_suite import (
        extract_suite_path_candidate,
        parse_suite_message_options,
        run_prompt_suite,
    )
    from rbp_eval.accept.batch_prompts import parse_prompt_cases, select_prompt_cases

    msg = (
        "'/home/user/bio_agent/nanobot-bio/docs/eval/transfer_test_prompts.md'"
        "读取最后三条测试语句进行预测"
    )
    path = extract_suite_path_candidate(msg)
    assert path is not None
    assert path.endswith("transfer_test_prompts.md")

    opts = parse_suite_message_options(msg)
    assert opts.last == 3
    assert opts.limit is None
    assert opts.needs_clarification is False
    assert opts.has_explicit_filter is True

    parsed = parse_prompt_cases(TRANSFER_MD)
    selected, note = select_prompt_cases(parsed, last=opts.last)
    assert len(selected) == 3
    assert note == "last 3 of 20"
    assert [c.prompt_id for c in selected] == ["18", "19", "20"]
    assert [c.gene for c in selected] == ["NSUN2", "DROSHA", "RPS6"]


def test_parse_suite_message_first_n_and_prompt_ids():
    from nanobot.agent.tools.rbp.prompt_suite import parse_suite_message_options

    first = parse_suite_message_options(
        "docs/eval/transfer_test_prompts.md 前三条"
    )
    assert first.limit == 3
    assert first.last is None
    assert first.needs_clarification is False

    eng = parse_suite_message_options(
        "/suite docs/eval/transfer_test_prompts.md last 3 --dry-run"
    )
    assert eng.last == 3
    assert eng.dry_run is True

    cli = parse_suite_message_options(
        "/suite docs/eval/transfer_test_prompts.md --last 3"
    )
    assert cli.last == 3

    prompts = parse_suite_message_options(
        "docs/eval/transfer_test_prompts.md run Prompt 18-20"
    )
    assert prompts.cases == ["18", "19", "20"]
    assert prompts.has_explicit_filter is True


def test_parse_suite_message_ambiguous_extra_text_needs_clarification():
    from nanobot.agent.tools.rbp.prompt_suite import parse_suite_message_options

    opts = parse_suite_message_options(
        "docs/eval/transfer_test_prompts.md 帮我挑难的几条仔细跑"
    )
    assert opts.has_extra_text is True
    assert opts.has_explicit_filter is False
    assert opts.needs_clarification is True

    bare = parse_suite_message_options("docs/eval/transfer_test_prompts.md")
    assert bare.needs_clarification is False
    assert bare.has_explicit_filter is False


def test_run_prompt_suite_last_three_dry_run(tmp_path, capsys):
    from nanobot.agent.tools.rbp.prompt_suite import (
        parse_suite_message_options,
        run_prompt_suite,
    )

    msg = (
        f"'{TRANSFER_MD}'"
        "读取最后三条测试语句进行预测"
    )
    opts = parse_suite_message_options(msg)
    assert opts.last == 3

    out = run_prompt_suite(
        path=str(TRANSFER_MD),
        out_dir=str(tmp_path),
        dry_run=True,
        last=opts.last,
        stream=True,
    )
    assert out["ok"] is True
    assert out["n_cases"] == 3
    assert out["n_parsed"] == 20
    assert out["selection"] == "last 3 of 20"
    assert out["last"] == 3
    case_keys = [
        r.get("case") for r in (out.get("results") or []) if isinstance(r, dict)
    ]
    assert case_keys == ["18_NSUN2", "19_DROSHA", "20_RPS6"]
    err = capsys.readouterr().err
    assert "3 case(s)" in err
    assert "last 3 of 20" in err


def test_run_prompt_suite_registered():
    from nanobot.agent.tools.rbp import ALL_RBP_TOOL_CLASSES

    names = {cls().name for cls in ALL_RBP_TOOL_CLASSES}
    assert "run_prompt_suite" in names


def test_run_prompt_suite_chat_default_limit(tmp_path):
    from nanobot.agent.tools.rbp.prompt_suite import (
        CHAT_DEFAULT_LIMIT,
        CHAT_HARD_MAX,
        _chat_effective_limit,
        run_prompt_suite,
    )

    lim, note = _chat_effective_limit(None)
    assert lim == CHAT_DEFAULT_LIMIT
    assert note and "default" in note
    lim2, note2 = _chat_effective_limit(999)
    assert lim2 == CHAT_HARD_MAX
    assert note2 and "clamped" in note2

    out = run_prompt_suite(
        path=str(PROMPTS_MD),
        out_dir=str(tmp_path),
        dry_run=True,
        # no limit → chat default 20 (suite has exactly 20)
    )
    assert out["ok"] is True
    assert out["n_cases"] == CHAT_DEFAULT_LIMIT
    assert out["limit"] == CHAT_DEFAULT_LIMIT


def test_looks_like_tool_markup_dsml():
    from app.core.verdict_schema import looks_like_tool_markup, normalize_verdict

    dsml = """
<｜｜DSML｜｜tool_calls>
<｜｜DSML｜｜invoke name="fuse_similarity_views">
<｜｜DSML｜｜parameter name="seq_hits" string="false">[{"alias":"EWSR1"}]</｜｜DSML｜｜parameter>
</｜｜DSML｜｜invoke>
</｜｜DSML｜｜tool_calls>
""".strip()
    assert looks_like_tool_markup(dsml) is True
    v = normalize_verdict(dsml)
    assert v["label"] == "No"
    assert v["p_hat"] is None
    assert "truncated_tool_markup" in (v.get("caveats") or [])
    assert "DSML" not in str(v.get("explanation") or "") or "Incomplete" in str(
        v.get("explanation") or ""
    )
    assert "Incomplete turn" in str(v.get("explanation") or "")


def test_format_verdict_display_rejects_dsml():
    from app.core.chat_ux import format_verdict_display

    content = (
        '<｜DSML｜tool_calls>\n'
        '<｜DSML｜invoke name="fuse_similarity_views">\n'
        "seq_hits=[...]\n"
        "</｜DSML｜tool_calls>"
    )
    shown = format_verdict_display(SimpleNamespace(content=content, verdict=None))
    assert "Incomplete turn" in shown
    assert "fuse_similarity_views" not in shown or "truncated" in shown.lower() or "Incomplete" in shown


def test_fuse_accepts_seq_hits_alias():
    import asyncio

    from nanobot.agent.tools.rbp.evolve_tools import FuseSimilarityViewsTool
    from nanobot.agent.tools.rbp.turn_guards import (
        mark_retrieve_done,
        reset_stage_guards,
    )

    reset_stage_guards()
    mark_retrieve_done("seq_similarity")
    mark_retrieve_done("struct_similarity")
    mark_retrieve_done("domain_architecture")
    tool = FuseSimilarityViewsTool()
    seq_hits = [
        {"alias": "U2AF2", "uniprot": "P26368", "score": 0.9, "metric": "esmc_cosine"},
    ]
    struct_hits = [
        {"alias": "U2AF2", "uniprot": "P26368", "score": 0.85, "metric": "tm_score"},
    ]
    out = asyncio.run(
        tool.execute(
            seq_hits=seq_hits,
            struct_hits=struct_hits,
            top_k=3,
            exclude_aliases=["FUS"],
            cohort="HepG2",
        )
    )
    data = json.loads(out)
    assert data["status"] == "ok", data
    donors = data["value"]["donors"]
    assert donors
    assert donors[0]["alias"] == "U2AF2"
