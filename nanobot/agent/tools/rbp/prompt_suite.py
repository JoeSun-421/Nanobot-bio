# -*- coding: utf-8 -*-
"""run_prompt_suite — allowlisted eval markdown → outer-loop batch-prompts.

Reads a prompt-suite ``.md`` under docs/ (via path_guard), parses fenced
``text`` cases, and runs one agent turn per case (same runner as
``nanobot-bio batch-prompts``). Does **not** ask the LLM to fuse 20 cases
in a single turn.

CLI examples:
  nanobot-bio batch-prompts --dry-run
  nanobot-bio batch-prompts --limit 2
  nanobot-bio batch-prompts --case PTBP1
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from nanobot.agent.tools.core.base import Tool, tool_parameters

from nanobot.agent.tools.rbp.common import dumps, err, ok, timed_call
from nanobot.agent.tools.rbp.path_guard import resolve_doc_path

# Chat / tool safety: avoid accidentally launching huge suites from interactive UX.
# CLI ``nanobot-bio batch-prompts`` calls ``run_batch_prompts`` directly (no cap).
CHAT_DEFAULT_LIMIT = 20
CHAT_HARD_MAX = 50

# Path-like tokens pointing at eval prompt suites
_MD_PATH_TOKEN = re.compile(
    r"(?P<path>(?:~|/|\./)?(?:[\w.\-]+/)*docs/eval/[\w.\-]+\.md"
    r"|/(?:[\w.\-]+/)+[\w.\-]+\.md"
    r"|(?:~|/|\./)?[\w.\-/]*UNSEEN_RBP_TEST_PROMPTS_20\.md"
    r"|(?:~|/|\./)?[\w.\-/]*transfer_test_prompts\.md)",
    re.IGNORECASE,
)

_RUN_PREFIX = re.compile(
    r"(?is)^\s*(?:please\s+)?(?:run|execute|batch|score)\s+"
    r"(?:this\s+|the\s+)?(?:file|suite|prompts?|markdown)?\s*[:\-]?\s*"
)

_SUITE_SLASH = re.compile(r"(?is)^\s*/suite\b")

# Natural-language "last N" (最后三条 / 末尾 3 条 / last 3)
_LAST_N_RE = re.compile(
    r"(?:"
    r"(?:最后|末尾)\s*(?P<cn>[0-9]+|[一二两兩三四五六七八九十百]+)\s*条?"
    r"|\blast\s+(?P<en>\d+)\s*(?:cases?|prompts?|items?)?"
    r")",
    re.IGNORECASE,
)

# Natural-language "first N" (前三条 / 最先 3 条 / first 3)
_FIRST_N_RE = re.compile(
    r"(?:"
    r"(?:前|最先|开头)\s*(?P<cn>[0-9]+|[一二两兩三四五六七八九十百]+)\s*条?"
    r"|\b(?:first|top)\s+(?P<en>\d+)\s*(?:cases?|prompts?|items?)?"
    r")",
    re.IGNORECASE,
)

_PROMPT_RANGE_RE = re.compile(
    r"(?:prompt|case)s?\s*(\d{1,2})\s*[-–—to]{1,3}\s*(\d{1,2})\b",
    re.IGNORECASE,
)
_PROMPT_ID_RE = re.compile(r"(?:prompt|case)\s*(\d{1,2})\b", re.IGNORECASE)
_PROMPT_CN_RE = re.compile(
    r"第\s*(\d{1,2})\s*(?:号)?\s*(?:个)?\s*(?:prompt|题|案例|测试)",
    re.IGNORECASE,
)

# Benign verbs/nouns left after stripping path + understood filters
_BENIGN_RESIDUAL_RE = re.compile(
    r"\b(?:"
    r"please|run|execute|batch|score|predict|prediction|suite|file|markdown|"
    r"prompts?|cases?|this|the|and|with|for|from|of|to|a|an"
    r")\b|"
    r"(?:读取|进行|预测|测试|语句|跑|一下|这个|文件|套件|全部|所有|帮忙|帮我|"
    r"开始|执行|批量|评估|验证|那|个|的|了|吧|呀|呢|吗|请)",
    re.IGNORECASE,
)

_CN_DIGIT = {
    "零": 0,
    "〇": 0,
    "一": 1,
    "二": 2,
    "两": 2,
    "兩": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
}


@dataclass
class SuiteMessageOptions:
    """Filters parsed from a chat /suite message or path+instruction paste."""

    dry_run: bool = False
    limit: Optional[int] = None
    offset: Optional[int] = None
    last: Optional[int] = None
    cases: Optional[list[str]] = None
    has_explicit_filter: bool = False
    has_extra_text: bool = False
    needs_clarification: bool = False


def _parse_count_token(token: str) -> Optional[int]:
    """Parse arabic or simple Chinese numerals (1–99)."""
    tok = (token or "").strip()
    if not tok:
        return None
    if tok.isdigit():
        n = int(tok)
        return n if n > 0 else None
    if tok in _CN_DIGIT:
        n = _CN_DIGIT[tok]
        return n if n > 0 else None
    if tok == "十":
        return 10
    if tok.startswith("十") and len(tok) == 2 and tok[1] in _CN_DIGIT:
        return 10 + _CN_DIGIT[tok[1]]
    if tok.endswith("十") and len(tok) == 2 and tok[0] in _CN_DIGIT:
        return _CN_DIGIT[tok[0]] * 10
    if len(tok) == 3 and tok[1] == "十" and tok[0] in _CN_DIGIT and tok[2] in _CN_DIGIT:
        return _CN_DIGIT[tok[0]] * 10 + _CN_DIGIT[tok[2]]
    if tok == "百":
        return 100
    return None


def _parse_prompt_id_filters(text: str) -> list[str]:
    """Extract Prompt/Case numbers mentioned in the message (zero-padded)."""
    ids: list[str] = []
    for a, b in _PROMPT_RANGE_RE.findall(text or ""):
        lo, hi = int(a), int(b)
        if lo > hi:
            lo, hi = hi, lo
        for n in range(lo, min(hi, 99) + 1):
            ids.append(f"{n:02d}")
    for n in _PROMPT_ID_RE.findall(text or ""):
        ids.append(f"{int(n):02d}")
    for n in _PROMPT_CN_RE.findall(text or ""):
        ids.append(f"{int(n):02d}")
    seen: set[str] = set()
    out: list[str] = []
    for pid in ids:
        if pid not in seen:
            seen.add(pid)
            out.append(pid)
    return out


def _residual_suite_instruction(message: str, path: Optional[str]) -> str:
    """Return non-path, non-filter residue (empty ⇒ path-only / understood)."""
    text = message or ""
    text = _SUITE_SLASH.sub(" ", text, count=1)
    text = _RUN_PREFIX.sub(" ", text)
    if path:
        for form in (f"'{path}'", f'"{path}"', f"`{path}`", path):
            text = text.replace(form, " ")
    text = _MD_PATH_TOKEN.sub(" ", text)
    text = re.sub(r"(?i)--dry-run\b", " ", text)
    text = re.sub(r"(?i)--limit\s+\d+", " ", text)
    text = re.sub(r"(?i)--offset\s+\d+", " ", text)
    text = re.sub(r"(?i)--case\s+\S+", " ", text)
    text = re.sub(r"(?i)--last\s+\d+", " ", text)
    text = _LAST_N_RE.sub(" ", text)
    text = _FIRST_N_RE.sub(" ", text)
    text = _PROMPT_RANGE_RE.sub(" ", text)
    text = _PROMPT_ID_RE.sub(" ", text)
    text = _PROMPT_CN_RE.sub(" ", text)
    text = _BENIGN_RESIDUAL_RE.sub(" ", text)
    text = re.sub(r"[\s`'\"‘’“”，。、！？!?:：;；\-_/\\()（）\[\]{}]+", " ", text)
    return text.strip()


def parse_suite_message_options(message: str) -> SuiteMessageOptions:
    """Parse CLI-like flags and natural-language filters from the full message.

    Supports ``--dry-run``, ``--limit N``, ``--offset N``, ``--case NAME``,
    ``--last N``, NL ``最后N条`` / ``末尾N`` / ``last N``, ``前N条`` /
    ``first N``, and Prompt/Case number mentions.

    When the message has a suite path plus leftover instruction text that we
    cannot map to a filter, ``needs_clarification`` is True so chat must not
    silently run the full suite.
    """
    text = message or ""
    path = extract_suite_path_candidate(text)

    dry_run = bool(re.search(r"(?i)(?:^|\s)--dry-run\b", text))
    limit: Optional[int] = None
    offset: Optional[int] = None
    last: Optional[int] = None

    m_lim = re.search(r"(?i)(?:^|\s)--limit\s+(\d+)\b", text)
    if m_lim:
        try:
            limit = int(m_lim.group(1))
        except ValueError:
            limit = None
    m_off = re.search(r"(?i)(?:^|\s)--offset\s+(\d+)\b", text)
    if m_off:
        try:
            offset = int(m_off.group(1))
        except ValueError:
            offset = None
    m_last_flag = re.search(r"(?i)(?:^|\s)--last\s+(\d+)\b", text)
    if m_last_flag:
        try:
            last = int(m_last_flag.group(1))
        except ValueError:
            last = None

    case_hits = re.findall(r"(?i)(?:^|\s)--case\s+(\S+)", text)
    prompt_ids = _parse_prompt_id_filters(text)
    cases_list = list(case_hits)
    for pid in prompt_ids:
        if pid not in {c.upper() for c in cases_list} and pid not in cases_list:
            cases_list.append(pid)
    cases = cases_list or None

    # NL slice when CLI did not already set limit/offset/last
    if last is None and limit is None and offset is None:
        m_last = _LAST_N_RE.search(text)
        if m_last:
            raw = m_last.group("cn") or m_last.group("en") or ""
            last = _parse_count_token(raw)
        else:
            m_first = _FIRST_N_RE.search(text)
            if m_first:
                raw = m_first.group("cn") or m_first.group("en") or ""
                limit = _parse_count_token(raw)

    has_explicit = any(
        v is not None and (v if not isinstance(v, list) else len(v) > 0)
        for v in (limit, offset, last, cases)
    )
    residual = _residual_suite_instruction(text, path)
    has_extra = bool(residual)
    needs_clarification = bool(path) and has_extra and not has_explicit

    return SuiteMessageOptions(
        dry_run=dry_run,
        limit=limit,
        offset=offset,
        last=last,
        cases=cases,
        has_explicit_filter=has_explicit,
        has_extra_text=has_extra,
        needs_clarification=needs_clarification,
    )


def extract_suite_path_candidate(message: str) -> Optional[str]:
    """Return a path string if ``message`` looks like a suite-path request.

    Accepts bare paths, ``run this file: docs/eval/….md``, and ``/suite path``.
    Returns ``None`` for single-case fenced pastes or unrelated chat.
    """
    text = (message or "").strip()
    if not text:
        return None
    # Whole-file / multi-case paste → not a path request
    if text.count("```") >= 2 or "Protein sequence" in text:
        return None
    if len(text) > 800:
        return None

    work = text
    if _SUITE_SLASH.match(work):
        work = _SUITE_SLASH.sub("", work, count=1).strip()
        # Drop optional flags before the path
        work = re.sub(
            r"(?is)^(?:--dry-run|--limit\s+\d+|--offset\s+\d+|--last\s+\d+|--case\s+\S+\s*)+",
            "",
            work,
        ).strip()
    else:
        work = _RUN_PREFIX.sub("", work).strip()

    m = _MD_PATH_TOKEN.search(work)
    if m:
        return m.group("path").strip().strip("`'\"")

    # Bare relative path without docs/eval/ prefix (still allowlisted later)
    # Strip a leading quote-wrapped token: 'path.md'读取…
    bare_m = re.match(
        r"^[`'\"]?(?P<p>(?:~|/|\./)?[\w.\-/]+\.md)[`'\"]?",
        work,
        re.IGNORECASE,
    )
    if bare_m:
        bare = bare_m.group("p")
        if "/" in bare or bare.startswith("."):
            return bare
    bare = work.split()[0].strip().strip("`'\"") if work.split() else ""
    if bare.lower().endswith(".md") and ("/" in bare or bare.startswith(".")):
        return bare
    return None


def is_prompt_suite_request(message: str) -> bool:
    """True when the user message should short-circuit to outer-loop batch."""
    candidate = extract_suite_path_candidate(message)
    if not candidate:
        return False
    try:
        path = resolve_doc_path(candidate)
    except ValueError:
        return False
    try:
        from rbp_eval.accept.batch_prompts import parse_prompt_cases

        return len(parse_prompt_cases(path)) > 0
    except Exception:
        return False


def _chat_effective_limit(
    limit: Optional[int],
    max_cases: Optional[int] = None,
) -> tuple[Optional[int], Optional[str]]:
    """Apply chat default / hard-max caps. Returns (effective_limit, note)."""
    hard = CHAT_HARD_MAX
    if max_cases is not None:
        try:
            hard = max(1, min(CHAT_HARD_MAX, int(max_cases)))
        except (TypeError, ValueError):
            hard = CHAT_HARD_MAX
    note: Optional[str] = None
    if limit is None:
        return min(CHAT_DEFAULT_LIMIT, hard), (
            f"chat default limit={min(CHAT_DEFAULT_LIMIT, hard)} "
            f"(hard max {CHAT_HARD_MAX}; CLI batch-prompts has no cap)"
        )
    try:
        requested = int(limit)
    except (TypeError, ValueError):
        return min(CHAT_DEFAULT_LIMIT, hard), "invalid limit; using chat default"
    if requested <= 0:
        return min(CHAT_DEFAULT_LIMIT, hard), "non-positive limit; using chat default"
    if requested > hard:
        note = f"limit {requested} clamped to hard max {hard}"
        return hard, note
    return requested, None


def run_prompt_suite(
    *,
    path: str,
    out_dir: Optional[str] = None,
    cases: Optional[list[str]] = None,
    limit: Optional[int] = None,
    offset: Optional[int] = None,
    last: Optional[int] = None,
    max_cases: Optional[int] = None,
    device: str = "auto",
    dry_run: bool = False,
    continue_on_error: bool = True,
    chat_safe: bool = True,
    stream: Optional[bool] = None,
) -> dict[str, Any]:
    """Resolve allowlisted suite path and run ``batch_prompts`` outer loop.

    When ``chat_safe`` is True (tool / chat UX), apply default limit 20 and
    hard max 50. CLI ``batch-prompts`` should call ``run_batch_prompts``
    directly so it is not capped.

    ``last`` selects the last N parsed cases (after ``cases`` filter).
    ``offset`` / ``limit`` slice from the start of the filtered list.

    ``stream``: chat-like per-case tool UX. Chat short-circuit should pass
    ``True``. ``None`` → auto (TTY). Tool path defaults to TTY auto.
    """
    try:
        resolved = resolve_doc_path(path)
    except ValueError as e:
        return {"ok": False, "error": str(e)}

    from rbp_eval.accept.batch_prompts import parse_prompt_cases, run_batch_prompts

    try:
        parsed = parse_prompt_cases(resolved)
    except (FileNotFoundError, ValueError) as e:
        return {"ok": False, "error": str(e), "path": str(resolved)}

    limit_note: Optional[str] = None
    effective_limit = limit
    effective_last = last
    effective_offset = offset
    if chat_safe:
        if last is not None:
            # Cap "last N" like an explicit limit; do not first-N truncate before it.
            effective_last, limit_note = _chat_effective_limit(last, max_cases)
            effective_limit = None
        else:
            effective_limit, limit_note = _chat_effective_limit(limit, max_cases)

    report = run_batch_prompts(
        prompts_md=resolved,
        out_dir=out_dir,
        cases=cases,
        limit=effective_limit,
        offset=effective_offset,
        last=effective_last,
        device=device or "auto",
        dry_run=bool(dry_run),
        continue_on_error=continue_on_error,
        stream=stream,
    )
    # Slim tool payload — full rows live in jsonl/summary on disk
    results = report.get("results")
    if not results and report.get("dry_run"):
        results = [{"case": c} for c in (report.get("cases") or [])]
    # Prefer short per-case rows for the LLM (alias/gene, label, p_hat, error)
    short_rows: list[dict[str, Any]] = []
    for r in results or []:
        if not isinstance(r, dict):
            short_rows.append({"case": r})
            continue
        short_rows.append(
            {
                "case": r.get("case"),
                "gene": r.get("gene"),
                "ok": r.get("ok"),
                "label": r.get("label"),
                "p_hat": r.get("p_hat"),
                "error": r.get("error"),
            }
        )
    slim = {
        "ok": bool(report.get("ok")),
        "path": str(resolved),
        "n_parsed": len(parsed),
        "n_cases": report.get("n_cases"),
        "n_ok": report.get("n_ok"),
        "n_failed": report.get("n_failed"),
        "limit": effective_limit,
        "offset": effective_offset,
        "last": effective_last,
        "selection": report.get("selection"),
        "dry_run": bool(report.get("dry_run")),
        "summary_json": report.get("path"),
        "jsonl": report.get("jsonl"),
        "elapsed_s": report.get("elapsed_s"),
        "stream": report.get("stream"),
        "results": short_rows,
        "runner": "batch_prompts.v1",
        "note": (
            "Outer-loop complete: one agent turn per case. "
            "Do not re-score these cases in the current chat turn."
            + (f" ({limit_note})" if limit_note else "")
        ),
    }
    if limit_note:
        slim["limit_note"] = limit_note
    return slim


@tool_parameters(
    {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": (
                    "Allowlisted path to a prompt-suite markdown under docs/eval/ "
                    "(e.g. docs/eval/UNSEEN_RBP_TEST_PROMPTS_20.md or "
                    "docs/eval/transfer_test_prompts.md)"
                ),
            },
            "limit": {
                "type": "integer",
                "description": (
                    "Optional max number of cases to run from the start "
                    f"(chat default {CHAT_DEFAULT_LIMIT}, hard max {CHAT_HARD_MAX})"
                ),
            },
            "offset": {
                "type": "integer",
                "description": "Optional 0-based start index into the filtered case list",
            },
            "last": {
                "type": "integer",
                "description": (
                    "Optional: run only the last N cases (after case filter). "
                    "Overrides limit/offset when set from chat NL filters."
                ),
            },
            "max_cases": {
                "type": "integer",
                "description": (
                    f"Optional lower hard cap (≤ {CHAT_HARD_MAX}). "
                    "Does not raise the chat hard max."
                ),
            },
            "case": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional filters by case id / prompt id / gene",
            },
            "dry_run": {
                "type": "boolean",
                "default": False,
                "description": "Parse/list cases only (no LLM / science tools)",
            },
            "device": {
                "type": "string",
                "default": "auto",
                "description": "auto | cuda | cpu",
            },
            "out_dir": {
                "type": "string",
                "description": "Optional directory for jsonl + summary json",
            },
        },
        "required": ["path"],
    }
)
class RunPromptSuiteTool(Tool):
    """Outer-loop batch runner for docs/eval prompt-suite markdown files."""

    _plugin_discoverable = True
    _scopes = {"core", "subagent"}

    @property
    def name(self) -> str:
        return "run_prompt_suite"

    @property
    def description(self) -> str:
        return (
            "When the user pastes a path to a prompt-suite markdown under docs/eval/ "
            "(e.g. transfer_test_prompts.md or UNSEEN_RBP_TEST_PROMPTS_20.md) or asks "
            "to run that file: read the FULL user message (not only the path) for "
            "filters such as 最后N条 / last N / 前N条 / --limit / --offset / --case / "
            "Prompt NN, then parse fenced ```text``` cases and run the outer-loop "
            "batch (one agent turn per case → JSONL/summary). "
            "Do NOT try to score all cases inside the current chat turn. "
            "Not general read_file; for a single fenced prompt paste use the normal "
            "Stage 0–3 pipeline instead. CLI equivalent: nanobot-bio batch-prompts."
        )

    @property
    def read_only(self) -> bool:
        return False

    async def execute(self, **kwargs: Any) -> str:
        path = (kwargs.get("path") or "").strip()
        if not path:
            return dumps(err("path required"))
        cases = kwargs.get("case") or kwargs.get("cases")
        if isinstance(cases, str):
            cases = [cases]
        elif cases is not None and not isinstance(cases, list):
            cases = None
        def _opt_int(key: str) -> Optional[int]:
            raw = kwargs.get(key)
            if raw is None:
                return None
            try:
                return int(raw)
            except (TypeError, ValueError):
                return None

        limit_i = _opt_int("limit")
        offset_i = _opt_int("offset")
        last_i = _opt_int("last")
        max_cases_i = _opt_int("max_cases")

        def _run() -> dict[str, Any]:
            return run_prompt_suite(
                path=path,
                out_dir=(kwargs.get("out_dir") or None),
                cases=list(cases) if cases else None,
                limit=limit_i,
                offset=offset_i,
                last=last_i,
                max_cases=max_cases_i,
                device=str(kwargs.get("device") or "auto"),
                dry_run=bool(kwargs.get("dry_run")),
                chat_safe=True,
            )

        out, ms, error = await asyncio.to_thread(lambda: timed_call(_run))
        if error:
            return dumps(err(str(error), ms or 0.0))
        if not isinstance(out, dict):
            return dumps(err("run_prompt_suite failed", ms or 0.0))
        if out.get("ok") is False and out.get("error"):
            return dumps(err(str(out.get("error")), ms or 0.0))
        return dumps(ok(out, ms or 0.0))


__all__ = [
    "RunPromptSuiteTool",
    "run_prompt_suite",
    "extract_suite_path_candidate",
    "is_prompt_suite_request",
    "parse_suite_message_options",
    "SuiteMessageOptions",
    "CHAT_DEFAULT_LIMIT",
    "CHAT_HARD_MAX",
]
