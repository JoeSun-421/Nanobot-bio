# -*- coding: utf-8 -*-
"""Outer-loop batch runner: one agent turn per markdown prompt case.

Avoids the chat failure mode where pasting many cases into one turn hits
``max_tokens`` (8192), truncates tool calls (raw DSML dumped as "verdict"),
and never finishes Stage 1–3 for each protein.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

# Unseen suite: ## Prompt 01 — Case 01 — FUS / P35637 …
_PROMPT_CASE_RE = re.compile(
    r"^#{2,3}\s*Prompt\s+(\d+)\s*[—\-]+\s*Case\s*(\d+)\s*[—\-]+\s*(\S+).*?\n"
    r".*?```text\n(.*?)```",
    re.MULTILINE | re.DOTALL,
)

# Transfer smoke suite: ### Prompt 01 — PTBP1 / K562 → transfer
_TRANSFER_PROMPT_RE = re.compile(
    r"^#{2,3}\s*Prompt\s+(\d+)\s*[—\-]+\s*([A-Za-z0-9][\w\-]*)\b.*?\n"
    r".*?```text\n(.*?)```",
    re.MULTILINE | re.DOTALL,
)

_DEFAULT_PROMPTS = (
    Path(__file__).resolve().parents[2]
    / "docs"
    / "eval"
    / "UNSEEN_RBP_TEST_PROMPTS_20.md"
)


@dataclass
class PromptCase:
    prompt_id: str
    case_id: str
    gene: str
    message: str

    @property
    def key(self) -> str:
        return f"{self.case_id}_{self.gene}"


def parse_prompt_cases(md_path: str | Path) -> list[PromptCase]:
    """Extract paste-ready ```text``` blocks from prompt-suite markdown.

    Supports:
    - Unseen: ``## Prompt 01 — Case 01 — FUS …`` + fenced ``text``
    - Transfer: ``### Prompt 01 — PTBP1 / K562 → transfer`` + fenced ``text``
    """
    path = Path(md_path).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"prompt markdown not found: {path}")
    text = path.read_text(encoding="utf-8")
    cases: list[PromptCase] = []

    for prompt_id, case_id, gene, body in _PROMPT_CASE_RE.findall(text):
        msg = str(body).strip()
        if not msg:
            continue
        gene_s = str(gene).strip().rstrip("/")
        cases.append(
            PromptCase(
                prompt_id=str(prompt_id).zfill(2),
                case_id=str(case_id).zfill(2),
                gene=gene_s,
                message=msg,
            )
        )

    if not cases:
        for prompt_id, gene, body in _TRANSFER_PROMPT_RE.findall(text):
            msg = str(body).strip()
            if not msg:
                continue
            # Skip accidental matches on "Case" from the unseen header style
            gene_s = str(gene).strip().rstrip("/")
            if gene_s.lower() == "case":
                continue
            pid = str(prompt_id).zfill(2)
            cases.append(
                PromptCase(
                    prompt_id=pid,
                    case_id=pid,
                    gene=gene_s,
                    message=msg,
                )
            )

    if not cases:
        raise ValueError(
            f"no Prompt/Case ```text``` blocks found in {path}; "
            "expected headers like '## Prompt 01 — Case 01 — FUS …' "
            "or '### Prompt 01 — PTBP1 / K562 → transfer'"
        )
    return cases


def _clear_session(session_key: str) -> None:
    """Drop persisted session files so ephemeral runs do not reuse memory."""
    try:
        from app.core.paths import SESSIONS

        safe = session_key.replace(":", "_").replace("/", "_")
        for p in (
            *SESSIONS.glob(f"{safe}*.jsonl"),
            *SESSIONS.glob(f"*/{safe}*.jsonl"),
            *SESSIONS.glob(f"batch-prompt_{safe}*.jsonl"),
            *SESSIONS.glob(f"*/batch-prompt_{safe}*.jsonl"),
        ):
            p.unlink(missing_ok=True)
    except Exception:
        pass


def _slim_verdict(verdict: dict[str, Any]) -> dict[str, Any]:
    keep = (
        "label",
        "p_hat",
        "confidence",
        "explanation",
        "supporting_rbps",
        "caveats",
        "mode",
        "path",
        "near_match",
        "abstain",
    )
    return {k: verdict[k] for k in keep if k in verdict}


def resolve_stream_flag(stream: Optional[bool]) -> bool:
    """Resolve ``stream``: explicit bool wins; ``None`` → stderr is a TTY."""
    if stream is not None:
        return bool(stream)
    try:
        return bool(sys.stderr.isatty())
    except Exception:
        return False


def select_prompt_cases(
    parsed: list[PromptCase],
    *,
    cases: Optional[list[str]] = None,
    limit: Optional[int] = None,
    offset: Optional[int] = None,
    last: Optional[int] = None,
) -> tuple[list[PromptCase], Optional[str]]:
    """Filter/slice parsed cases. Returns ``(selected, selection_note)``.

    Order: name filter → ``last N`` (if set) → else ``offset`` then ``limit``.
    ``selection_note`` is a short banner fragment like ``last 3 of 20``.
    """
    selected = list(parsed)
    if cases:
        wanted = {str(c).strip().upper() for c in cases}
        selected = [
            c
            for c in selected
            if c.case_id.upper() in wanted
            or c.prompt_id.upper() in wanted
            or c.gene.upper() in wanted
            or c.key.upper() in wanted
        ]
        if not selected:
            raise ValueError(f"no cases matched filter {sorted(wanted)}")

    n_pool = len(selected)

    if last is not None and int(last) > 0:
        take = min(int(last), n_pool)
        selected = selected[-take:]
        return selected, f"last {take} of {n_pool}"

    off = 0
    if offset is not None:
        try:
            off = max(0, int(offset))
        except (TypeError, ValueError):
            off = 0
    if off:
        selected = selected[off:]
    if limit is not None and int(limit) > 0:
        selected = selected[: int(limit)]

    note: Optional[str] = None
    if off or (limit is not None and int(limit) > 0 and len(selected) < n_pool):
        if off and limit is not None and int(limit) > 0:
            note = f"offset {off} limit {int(limit)} of {n_pool}"
        elif off:
            note = f"offset {off} of {n_pool}"
        else:
            note = f"first {len(selected)} of {n_pool}"
    return selected, note


def _print_case_banner(case: PromptCase, *, index: int, n_total: int) -> None:
    print(
        f"\n  [{index}/{n_total}] Prompt {case.prompt_id} — {case.gene}",
        file=sys.stderr,
    )
    sys.stderr.flush()


def _run_case_turn(
    agent: Any,
    message: str,
    *,
    session_key: str,
    stream: bool = False,
) -> Any:
    """One agent turn; when ``stream``, reuse chat UX (thinking + tool lines)."""
    if stream:
        from app.core.chat_ux import (
            format_verdict_display,
            print_turn_footer,
            print_verdict_block,
            run_agent_turn_streamed_sync,
        )

        result = run_agent_turn_streamed_sync(
            agent,
            message,
            session_key=session_key,
            ephemeral=True,
        )
        print_verdict_block(format_verdict_display(result))
        elapsed = float(getattr(result, "_ux_elapsed", None) or 0.0)
        n_tools = len(getattr(result, "_ux_tools", None) or [])
        print_turn_footer(
            elapsed_s=elapsed,
            mode=getattr(result, "mode", "") or "",
            n_tools=n_tools,
        )
        return result
    return agent.run_sync(
        message,
        ephemeral=True,
        session_key=session_key,
    )


# Optional injectable turn runner for tests: (agent, message, *, session_key, stream) -> result
TurnRunner = Callable[..., Any]


def run_batch_prompts(
    *,
    prompts_md: str | Path,
    out_dir: Optional[str | Path] = None,
    cases: Optional[list[str]] = None,
    limit: Optional[int] = None,
    offset: Optional[int] = None,
    last: Optional[int] = None,
    device: str = "auto",
    dry_run: bool = False,
    continue_on_error: bool = True,
    stream: Optional[bool] = None,
    turn_runner: Optional[TurnRunner] = None,
) -> dict[str, Any]:
    """Run one Nanobot turn per case; write JSONL + summary JSON.

    ``stream`` controls chat-like per-case UX (case banner, thinking/tool
    lines, verdict block). ``None`` means auto: stream when stderr is a TTY.
    Pass ``turn_runner`` to inject a mock (skips ``RBPAgent`` construction).

    Selection: optional ``cases`` name filter, then ``last`` (tail) or
    ``offset``+``limit`` (head/slice).
    """
    from app.core.paths import ensure_artifact_dirs, report_path
    from app.core.verdict_schema import looks_like_tool_markup

    ensure_artifact_dirs()
    parsed = parse_prompt_cases(prompts_md)
    selected, selection_note = select_prompt_cases(
        parsed,
        cases=cases,
        limit=limit,
        offset=offset,
        last=last,
    )

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    if out_dir is None:
        # Keep jsonl beside the summary under reports/json/
        out_summary = report_path(f"batch_prompts_{stamp}.json")
        out_jsonl = out_summary.with_suffix(".jsonl")
    else:
        od = Path(out_dir).expanduser().resolve()
        od.mkdir(parents=True, exist_ok=True)
        out_jsonl = od / f"batch_prompts_{stamp}.jsonl"
        out_summary = od / f"batch_prompts_{stamp}.json"

    effective_stream = resolve_stream_flag(stream)
    rows: list[dict[str, Any]] = []
    if dry_run:
        if effective_stream:
            sel = f" · {selection_note}" if selection_note else ""
            print(
                f"  ▸ suite stream · {len(selected)} case(s){sel} · dry-run",
                file=sys.stderr,
            )
        for c in selected:
            rows.append(
                {
                    "case": c.key,
                    "prompt_id": c.prompt_id,
                    "case_id": c.case_id,
                    "gene": c.gene,
                    "message_chars": len(c.message),
                    "dry_run": True,
                }
            )
        summary = {
            "schema": "batch_prompts.v1",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "prompts_md": str(Path(prompts_md).expanduser().resolve()),
            "dry_run": True,
            "stream": effective_stream,
            "n_parsed": len(parsed),
            "n_cases": len(rows),
            "n_ok": len(rows),
            "n_failed": 0,
            "selection": selection_note,
            "cases": [r["case"] for r in rows],
            "jsonl": str(out_jsonl),
            "ok": True,
        }
        out_jsonl.write_text(
            "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
            encoding="utf-8",
        )
        out_summary.write_text(
            json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        summary["path"] = str(out_summary)
        return summary

    runner = turn_runner or _run_case_turn
    agent: Any = None
    if turn_runner is None:
        from app.agent import RBPAgent

        # One agent for the whole suite — sync_overlay at most once (not per case).
        agent = RBPAgent(prefer_nanobot_llm=True, allow_fallback=False, device=device)

    if effective_stream:
        sel = f" · {selection_note}" if selection_note else ""
        print(
            f"  ▸ suite stream · {len(selected)} case(s){sel} · "
            "thinking/tools per case like chat",
            file=sys.stderr,
        )

    t0 = time.time()
    for idx, case in enumerate(selected, start=1):
        session_key = f"batch-prompt:{case.key}"
        _clear_session(session_key)
        row: dict[str, Any] = {
            "case": case.key,
            "prompt_id": case.prompt_id,
            "case_id": case.case_id,
            "gene": case.gene,
            "session_key": session_key,
            "index": idx,
            "n_total": len(selected),
            "stream": effective_stream,
        }
        if effective_stream:
            _print_case_banner(case, index=idx, n_total=len(selected))
        started = time.time()
        try:
            result = runner(
                agent,
                case.message,
                session_key=session_key,
                stream=effective_stream,
            )
            content = getattr(result, "content", None) or ""
            verdict = result.verdict if isinstance(result.verdict, dict) else {}
            markup = looks_like_tool_markup(content)
            row.update(
                {
                    "ok": bool(result.verdict_valid) and not markup,
                    "mode": result.mode,
                    "verdict_valid": bool(result.verdict_valid),
                    "verdict_errors": list(result.verdict_errors or []),
                    "tools_used": list(result.tools_used or []),
                    "stop_reason": result.stop_reason,
                    "error": result.error,
                    "truncated_tool_markup": markup,
                    "verdict": _slim_verdict(verdict),
                    "p_hat": verdict.get("p_hat"),
                    "label": verdict.get("label"),
                    "confidence": verdict.get("confidence"),
                    "path_mode": verdict.get("mode") or verdict.get("path"),
                    "elapsed_s": round(time.time() - started, 3),
                }
            )
            if markup:
                row["ok"] = False
                row["error"] = (
                    row.get("error")
                    or "final content looks like truncated tool markup (DSML/XML); "
                    "not a JSON verdict — rerun this single case"
                )
        except Exception as e:
            row.update(
                {
                    "ok": False,
                    "error": f"{type(e).__name__}: {e}",
                    "elapsed_s": round(time.time() - started, 3),
                }
            )
            if not continue_on_error:
                rows.append(row)
                break
        rows.append(row)
        with out_jsonl.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")

    n_ok = sum(1 for r in rows if r.get("ok"))
    summary = {
        "schema": "batch_prompts.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "prompts_md": str(Path(prompts_md).expanduser().resolve()),
        "dry_run": False,
        "stream": effective_stream,
        "n_parsed": len(parsed),
        "n_cases": len(rows),
        "n_ok": n_ok,
        "n_failed": len(rows) - n_ok,
        "selection": selection_note,
        "elapsed_s": round(time.time() - t0, 3),
        "cases": [asdict(c) | {"message": f"<{len(c.message)} chars>"} for c in selected],
        "results": [
            {
                "case": r.get("case"),
                "ok": r.get("ok"),
                "label": r.get("label"),
                "p_hat": r.get("p_hat"),
                "path_mode": r.get("path_mode"),
                "truncated_tool_markup": r.get("truncated_tool_markup"),
                "error": r.get("error"),
            }
            for r in rows
        ],
        "jsonl": str(out_jsonl),
        "ok": n_ok == len(rows) and len(rows) > 0,
    }
    out_summary.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    summary["path"] = str(out_summary)
    return summary


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description=(
            "Outer-loop batch: one nanobot-bio agent turn per markdown case "
            "(reliable multi-verdict; avoids 20-in-one-chat truncation)."
        )
    )
    ap.add_argument(
        "--prompts",
        default=str(_DEFAULT_PROMPTS),
        help="Markdown with ## Prompt NN — Case NN — GENE + ```text``` blocks",
    )
    ap.add_argument("--out-dir", default=None, help="Directory for jsonl + summary json")
    ap.add_argument(
        "--case",
        action="append",
        default=None,
        help="Filter by case id / prompt id / gene (repeatable)",
    )
    ap.add_argument("--limit", type=int, default=None, help="Run at most N cases")
    ap.add_argument(
        "--offset",
        type=int,
        default=None,
        help="Skip the first N cases (0-based) before applying --limit",
    )
    ap.add_argument(
        "--last",
        type=int,
        default=None,
        help="Run only the last N cases (after --case filter)",
    )
    ap.add_argument("--device", default="auto", choices=["auto", "cuda", "cpu"])
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and list cases only (no LLM / science tools)",
    )
    ap.add_argument(
        "--stop-on-error",
        action="store_true",
        help="Abort after the first failed case (default: continue)",
    )
    ap.add_argument(
        "--stream",
        action="store_true",
        help="Force chat-like per-case tool streaming (default: on when stderr is a TTY)",
    )
    ap.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress per-case banners / tool streaming (quiet outer loop only)",
    )
    args = ap.parse_args(argv)
    stream_flag: Optional[bool]
    if args.quiet:
        stream_flag = False
    elif args.stream:
        stream_flag = True
    else:
        stream_flag = None
    report = run_batch_prompts(
        prompts_md=args.prompts,
        out_dir=args.out_dir,
        cases=args.case,
        limit=args.limit,
        offset=args.offset,
        last=args.last,
        device=args.device,
        dry_run=bool(args.dry_run),
        continue_on_error=not bool(args.stop_on_error),
        stream=stream_flag,
    )
    print(
        f"batch-prompts ok={report.get('ok')} "
        f"n_ok={report.get('n_ok', 0)}/{report.get('n_cases', 0)} "
        f"summary={report.get('path')} "
        f"jsonl={report.get('jsonl')}"
    )
    if report.get("dry_run"):
        for c in report.get("cases") or []:
            print(f"  - {c}")
    else:
        for r in report.get("results") or []:
            status = "ok" if r.get("ok") else "FAIL"
            print(
                f"  [{status}] {r.get('case')} "
                f"label={r.get('label')} p_hat={r.get('p_hat')} "
                f"mode={r.get('path_mode')}"
                + (f" err={r.get('error')}" if r.get("error") else "")
            )
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
