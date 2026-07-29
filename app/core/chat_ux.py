# -*- coding: utf-8 -*-
"""Chat UX: quiet framework logs + visible agent steps + terminal chrome."""

from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Optional, TextIO


# ---------------------------------------------------------------------------
# ANSI / chrome
# ---------------------------------------------------------------------------

_ANSI_RE = re.compile(r"\033\[[0-9;]*m")


def _use_color(stream: TextIO = sys.stderr) -> bool:
    if os.environ.get("NO_COLOR") or os.environ.get("RBP_NO_COLOR"):
        return False
    return bool(getattr(stream, "isatty", lambda: False)())


class Style:
    """Lightweight ANSI styles (disabled on non-TTY / NO_COLOR)."""

    def __init__(self, stream: TextIO = sys.stderr) -> None:
        self.on = _use_color(stream)
        self.stream = stream

    def _s(self, code: str, text: str) -> str:
        return f"\033[{code}m{text}\033[0m" if self.on else text

    def dim(self, t: str) -> str:
        return self._s("2", t)

    def bold(self, t: str) -> str:
        return self._s("1", t)

    def cyan(self, t: str) -> str:
        return self._s("36", t)

    def green(self, t: str) -> str:
        return self._s("32", t)

    def yellow(self, t: str) -> str:
        return self._s("33", t)

    def red(self, t: str) -> str:
        return self._s("31", t)

    def magenta(self, t: str) -> str:
        return self._s("35", t)


def _term_width(default: int = 72) -> int:
    try:
        return max(48, min(100, os.get_terminal_size().columns))
    except OSError:
        return default


def _visible_len(text: str) -> int:
    """Length of ``text`` with ANSI CSI sequences stripped."""
    return len(_ANSI_RE.sub("", text))


def _center_line(text: str, width: int) -> str:
    """Pad ``text`` to center within ``width`` (ANSI-safe)."""
    pad = max(0, (width - _visible_len(text)) // 2)
    return (" " * pad) + text


def print_banner(
    title: str = "RNA–RBP Agent",
    subtitle: str = "nanobot · delivery tools · Stage 0–3",
    *,
    stream: TextIO = sys.stderr,
) -> None:
    """Top-of-session brand line (Claude Code–like chrome, science product)."""
    s = Style(stream)
    w = _term_width()
    bar = "─" * w
    stream.write("\n")
    stream.write(s.cyan(bar) + "\n")
    stream.write(_center_line(s.bold(s.cyan(f"✶ {title}")), w) + "\n")
    stream.write(_center_line(s.dim(subtitle), w) + "\n")
    stream.write(s.cyan(bar) + "\n")
    stream.flush()


def print_chat_header(
    *,
    llm_summary: str,
    n_tools: int,
    skill_ok: bool,
    mem_warn: Optional[str] = None,
    session_key: Optional[str] = None,
    stream: TextIO = sys.stderr,
) -> None:
    s = Style(stream)
    print_banner(stream=stream)
    skill = s.green("always-on") if skill_ok else s.red("missing")
    stream.write(f"  {s.dim('LLM')}      {s.bold(llm_summary)}\n")
    stream.write(f"  {s.dim('Tools')}    {s.bold(str(n_tools))} registered\n")
    stream.write(f"  {s.dim('Skill')}    rbp-agent ({skill})\n")
    if session_key:
        short = session_key if len(session_key) <= 28 else session_key[:25] + "…"
        stream.write(f"  {s.dim('Session')}  {short}\n")
    stream.write(
        s.dim(
            "  Commands  /help  /status  /tools  /new  /clear  /thinking  "
            "/onboard  /quit\n"
        )
    )
    stream.write(
        s.dim(
            "  Tips      Paste RNA+protein in one message · Esc+Enter for "
            "multiline · thoughts folded (RBP_SHOW_THINKING=1)\n"
        )
    )
    stream.write(
        s.dim(
            "  Try       “Does this RNA interact with PTBP1?” + paste RNA, "
            "or resolve an unseen UniProt\n"
        )
    )
    if mem_warn:
        stream.write(s.yellow(f"\n  ⚠ {mem_warn}\n"))
    stream.write("\n")
    stream.flush()


CHAT_HELP = """\
  /help       Show this help
  /status     LLM, tools, session, paths
  /tools      List registered tool names
  /new        Start a fresh session (clears conversation memory)
  /clear      Clear the terminal screen (keeps session)
  /thinking   Toggle expanded thinking (RBP_SHOW_THINKING)
  /onboard    Reconfigure LLM provider / API key
  /quit       Exit chat

  Input       Esc+Enter = multiline · ↑ history · Ctrl+C cancel line · Ctrl+D exit
"""


def print_status_panel(
    *,
    llm_summary: str,
    n_tools: int,
    session_key: str,
    skill_ok: bool,
    stream: TextIO = sys.stderr,
) -> None:
    s = Style(stream)
    from app.core.paths import ARTIFACTS, PACKAGE_ROOT

    stream.write(s.bold(s.cyan("▸ status")) + "\n")
    stream.write(f"  llm       {llm_summary}\n")
    stream.write(f"  tools     {n_tools}\n")
    stream.write(f"  skill     {'ok' if skill_ok else 'missing'}\n")
    stream.write(f"  session   {session_key}\n")
    stream.write(f"  package   {PACKAGE_ROOT}\n")
    stream.write(f"  artifacts {ARTIFACTS}\n")
    stream.write(
        s.dim(
            f"  thinking  "
            f"{'expanded' if _show_full_thinking() else 'folded'} "
            f"(RBP_SHOW_THINKING)\n"
        )
    )
    stream.flush()


# Engineering / provenance keys kept in turn state but never shown in chat JSON.
_PUBLIC_VERDICT_STRIP = frozenset(
    {
        "score_source",
        "score_kind",
        "score_disclaimer",
        "mode",
        "score_provenance",
        "evidence_flags",
        "prior_missing",
        "structure_unavailable",
        "_deterministic_confidence",
    }
)


def print_verdict_block(body: str, *, stream: TextIO = sys.stdout) -> None:
    s = Style(stream)
    w = _term_width()
    parsed: dict[str, Any] | None = None
    try:
        candidate = json.loads(body)
        parsed = candidate if isinstance(candidate, dict) else None
    except (TypeError, ValueError, json.JSONDecodeError):
        parsed = None
    evidence = []
    caveats: list[str] = []
    confidence = None
    if parsed is not None:
        evidence = list(parsed.pop("evidence_table", []) or [])
        for key in _PUBLIC_VERDICT_STRIP:
            parsed.pop(key, None)
        caveats = [str(x) for x in (parsed.get("caveats") or [])]
        confidence = parsed.get("confidence")
        body = json.dumps(parsed, indent=2, ensure_ascii=False) + "\n"
    if evidence:
        stream.write("\n" + s.bold("▸ evidence") + "\n")
        stream.write(s.dim("donor            sim(raw)   prob    prior   weight\n"))
        for row in evidence[:8]:
            if not isinstance(row, dict):
                continue
            donor = str(row.get("donor") or row.get("alias") or row.get("rbp_id") or "—")
            sim = row.get("similarity", row.get("s", row.get("similarity_score")))
            prob = row.get("prob")
            prior = row.get("transfer_prior")
            weight = row.get("weight")
            fmt = lambda x: "—" if x is None else f"{float(x):.3f}"
            stream.write(
                f"{donor[:14]:<14} {fmt(sim):>9}   {fmt(prob):>5}   "
                f"{fmt(prior):>5}   {fmt(weight):>6}\n"
            )
    label = _peek_verdict_label(body)
    title = "▸ verdict"
    if label:
        colored = _color_label(label, s)
        title = f"▸ verdict  {colored}"
    stream.write("\n")
    stream.write(s.bold(title) + "\n")
    stream.write(s.dim("─" * min(w, 48)) + "\n")
    stream.write(body if body.endswith("\n") else body + "\n")
    if confidence or caveats:
        detail = f"confidence={confidence or 'unknown'}"
        if caveats:
            detail += " · caveats=" + ", ".join(caveats)
        stream.write(s.dim(detail) + "\n")
    stream.write(s.dim("─" * min(w, 48)) + "\n")
    stream.flush()


def print_turn_footer(
    *,
    elapsed_s: float,
    mode: str = "nanobot_llm",
    n_tools: int = 0,
    stream: TextIO = sys.stderr,
) -> None:
    """Clear 'turn is over' signal (Claude Code lesson: avoid lingering spinner)."""
    s = Style(stream)
    parts = [s.green("✓"), s.dim(f"{elapsed_s:.1f}s")]
    if n_tools:
        parts.append(s.dim(f"{n_tools} tools"))
    if mode and mode != "nanobot_llm":
        parts.append(s.yellow(mode))
    stream.write("  " + "  ·  ".join(parts) + "\n\n")
    stream.flush()


def _peek_verdict_label(body: str) -> Optional[str]:
    try:
        data = json.loads(body)
        if isinstance(data, dict) and data.get("label"):
            return str(data["label"])
    except Exception:
        pass
    for line in body.splitlines()[:8]:
        if '"label"' in line or "label:" in line.lower():
            for cand in ("Strong", "Likely", "Unlikely", "No", "Unknown"):
                if cand in line:
                    return cand
    return None


def _color_label(label: str, s: Style) -> str:
    low = label.lower()
    if low == "strong":
        return s.green(s.bold(label))
    if low == "likely":
        return s.cyan(s.bold(label))
    if low == "unlikely":
        return s.yellow(s.bold(label))
    if low in ("no", "unknown"):
        return s.dim(s.bold(label))
    return s.bold(label)


def print_registration(
    tool_names: list[str],
    *,
    skill_path: Optional[Path] = None,
    stream: TextIO = sys.stderr,
) -> None:
    """Show tool/skill registration before the agent loop."""
    s = Style(stream)
    stream.write(s.bold(s.cyan("▸ register")) + s.dim("  agent API / tools\n"))
    if skill_path:
        stream.write(s.dim(f"  skill  {skill_path}\n"))
    stage0 = {"resolve_rbp", "predict_interaction", "check_near_known"}
    shown = sorted(tool_names)
    primary = [
        n
        for n in shown
        if n in stage0
        or n.startswith(
            (
                "transfer",
                "seq_",
                "domain",
                "structure",
                "literature",
                "get_func",
                "fuse",
                "integrate",
                "predict_",
                "lookup_",
            )
        )
    ]
    rest = [n for n in shown if n not in primary]
    line = ", ".join(primary[:12] or shown[:12])
    if len(shown) > 12:
        line += f", … (+{len(shown) - 12})"
    stream.write(f"  {s.green('✓')} {len(shown)} tools  {s.dim(line)}\n")
    if rest and len(primary) >= 8:
        stream.write(s.dim(f"  + {len(rest)} delivery extras\n"))
    stream.write("\n")
    stream.flush()


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def configure_chat_logging(*, verbose: bool = False, log_file: Optional[Path] = None) -> None:
    """Silence nanobot/loguru DEBUG on the terminal; keep DETAIL in a file."""
    from loguru import logger

    logger.remove()
    if verbose:
        logger.add(
            sys.stderr,
            level="DEBUG",
            format="<level>{level: <5}</level> | <level>{message}</level>",
            colorize=True,
        )
    else:
        logger.add(
            sys.stderr,
            level="ERROR",
            format="<level>{level}</level> | <level>{message}</level>",
            colorize=True,
            filter=lambda r: "LLM transient error" not in str(r.get("message") or ""),
        )
    if log_file is None:
        from app.core.paths import DEFAULT_CHAT_LOG, ensure_artifact_dirs

        ensure_artifact_dirs()
        log_file = Path(os.environ.get("RBP_CHAT_LOG", str(DEFAULT_CHAT_LOG)))
    log_file = Path(log_file)
    log_file.parent.mkdir(parents=True, exist_ok=True)
    logger.add(
        str(log_file),
        level="DEBUG",
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <5} | {name}:{function}:{line} - {message}",
        rotation="10 MB",
        retention=3,
    )


# ---------------------------------------------------------------------------
# Input (prompt_toolkit — Claude Code–like ❯ + slash completion)
# ---------------------------------------------------------------------------

_PROMPT_SESSION: Any = None
_SLASH_COMMANDS = (
    "/help",
    "/status",
    "/tools",
    "/new",
    "/reset",
    "/clear",
    "/thinking",
    "/onboard",
    "/login",
    "/quit",
    "/exit",
)


def _init_prompt_session(history_dir: Optional[Path] = None) -> None:
    """Create a PromptSession with file history under artifacts/sessions/ (root sidecar)."""
    global _PROMPT_SESSION
    if _PROMPT_SESSION is not None:
        return
    try:
        from prompt_toolkit import PromptSession
        from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
        from prompt_toolkit.completion import WordCompleter
        from prompt_toolkit.history import FileHistory
        from prompt_toolkit.key_binding import KeyBindings
    except ImportError:
        _PROMPT_SESSION = False  # type: ignore[assignment]
        return

    if history_dir is None:
        from app.core.paths import SESSIONS, ensure_artifact_dirs

        ensure_artifact_dirs()
        base = SESSIONS
    else:
        base = Path(history_dir)
    base.mkdir(parents=True, exist_ok=True)
    hist = base / "rbp_chat_history"

    kb = KeyBindings()

    @kb.add("escape", "enter")
    def _multiline_submit(event) -> None:  # type: ignore[no-untyped-def]
        """Esc+Enter inserts a newline (Claude Code–style multiline paste)."""
        event.current_buffer.insert_text("\n")

    completer = WordCompleter(list(_SLASH_COMMANDS), ignore_case=True, sentence=True)
    _PROMPT_SESSION = PromptSession(
        history=FileHistory(str(hist)),
        enable_open_in_editor=False,
        multiline=False,
        completer=completer,
        complete_while_typing=True,
        auto_suggest=AutoSuggestFromHistory(),
        key_bindings=kb,
    )


def read_user_message(prompt: str = "❯ ") -> Optional[str]:
    """Read one chat turn via prompt_toolkit (history + paste); fallback to input()."""
    _init_prompt_session()
    if _PROMPT_SESSION and _PROMPT_SESSION is not False:
        try:
            from prompt_toolkit.formatted_text import HTML
            from prompt_toolkit.patch_stdout import patch_stdout

            with patch_stdout():
                text = _PROMPT_SESSION.prompt(
                    HTML(f"<b fg='ansicyan'>{prompt}</b>"),
                    rprompt=HTML("<ansibrightblack>/help</ansibrightblack>"),
                )
            return (text or "").rstrip()
        except (EOFError, KeyboardInterrupt):
            return None
        except Exception:
            pass

    s = Style(sys.stdout)
    try:
        first = input(s.cyan(prompt) if s.on else prompt)
    except (EOFError, KeyboardInterrupt):
        return None
    return (first or "").strip()


# ---------------------------------------------------------------------------
# Spinner — single in-place line (anti-flicker; no Rich status / verb rotation)
# ---------------------------------------------------------------------------

_BRAILLE = ("⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏")


class ThinkingSpinner:
    """One TTY status line: braille + stable label + elapsed.

    Flicker sources we avoid vs older Rich ``Console.status``:
      - no rotating Thinking/Reasoning/Planning verbs
      - no ``update()`` on every reasoning token
      - pause/resume only clears the status line around persistent prints
    """

    def __init__(self, label: str = "thinking", bot_name: str = "rbp-agent") -> None:
        del label
        self._bot = bot_name
        self._hint = "Thinking"
        self._enabled = bool(sys.stderr.isatty()) and not (
            os.environ.get("RBP_NO_SPINNER", "").strip().lower() in ("1", "true", "yes")
        )
        self._stream: TextIO = sys.stderr
        self._s = Style(self._stream)
        self._t0 = time.perf_counter()
        self._frame = 0
        self._stop = None
        self._thread = None
        self._active = False
        self._paused = False
        self._lock = __import__("threading").Lock()
        # Rich-compat no-ops (older code paths)
        self._inner = None
        self._console = None
        self._pause_cm = None

    def elapsed(self) -> float:
        return max(0.0, time.perf_counter() - self._t0)

    def _status_text(self) -> str:
        """Plain status label (tests + paint)."""
        hint = (self._hint or "").strip() or "Thinking"
        if hint in ("thinking", "responding"):
            hint = "Thinking"
        if hint.startswith("turn "):
            return f"{self._bot}  {hint}  ·  {self.elapsed():.0f}s"
        return f"{hint}  ·  {self.elapsed():.0f}s"

    def update(self, hint: str) -> None:
        """Change label only when it actually changes (no thrash)."""
        raw = (hint or "").strip()[:48]
        if raw in ("", "thinking", "responding"):
            nxt = "Thinking"
        elif raw.startswith("turn "):
            nxt = raw
        else:
            nxt = raw
        with self._lock:
            if nxt == self._hint:
                return
            self._hint = nxt

    def _paint(self) -> None:
        if self._paused or not self._active or not self._enabled:
            return
        sp = _BRAILLE[self._frame % len(_BRAILLE)]
        self._frame += 1
        line = (
            f"\r\x1b[2K  {self._s.cyan(sp)} "
            f"{self._s.dim(self._status_text())}"
        )
        try:
            self._stream.write(line)
            self._stream.flush()
        except Exception:
            pass

    def _loop(self) -> None:
        # ~5 fps — smooth enough, far less thrash than Rich status + verb spin
        while self._stop is not None and not self._stop.wait(0.2):
            self._paint()

    def _clear_line(self) -> None:
        if not self._enabled:
            return
        try:
            self._stream.write("\r\x1b[2K")
            self._stream.flush()
        except Exception:
            pass

    def start(self, hint: str | None = None, *, reset_clock: bool = False) -> None:
        """Start status spinner.

        ``hint`` sets the label (default ``Thinking``). ``reset_clock=True``
        restarts the elapsed counter — used for tool-wait phases so Xs reflects
        wait time, not total turn time.
        """
        if not self._enabled or self._active:
            return
        import threading

        self._frame = 0
        if reset_clock or not getattr(self, "_clock_started", False):
            self._t0 = time.perf_counter()
            self._clock_started = True
        raw = (hint or "").strip()
        if raw in ("", "thinking", "responding"):
            self._hint = "Thinking"
        else:
            self._hint = raw[:48]
        self._stop = threading.Event()
        self._active = True
        self._paused = False
        self._thread = threading.Thread(target=self._loop, name="rbp-spin", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._stop is not None:
            self._stop.set()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=0.5)
        self._thread = None
        self._stop = None
        self._active = False
        self._paused = False
        self._clear_line()

    def pause(self) -> None:
        """Freeze paint so scrollback lines do not fight the status row."""
        if not self._active:
            return
        self._paused = True
        self._clear_line()

    def resume(self) -> None:
        if self._active:
            self._paused = False

    def __enter__(self) -> "ThinkingSpinner":
        self._clock_started = False
        self.start()
        return self

    def __exit__(self, *exc: Any) -> None:
        self.stop()
        self._clock_started = False
        return None


# keep alias used by older imports
ProductSpinner = ThinkingSpinner


# ---------------------------------------------------------------------------
# Agent step trace (thinking + tools)
# ---------------------------------------------------------------------------

def _short_json(obj: Any, limit: int = 120) -> str:
    try:
        raw = json.dumps(obj, ensure_ascii=False, default=str)
    except Exception:
        raw = str(obj)
    raw = raw.replace("\n", " ")
    if len(raw) > limit:
        return raw[: limit - 1] + "…"
    return raw


def _summarize_tool_result(result: Any) -> str:
    """Compact status line from delivery envelope or plain result."""
    text = result
    if isinstance(result, dict) and "content" in result:
        text = result.get("content")
    if isinstance(text, str):
        try:
            text = json.loads(text)
        except Exception:
            t = text.replace("\n", " ").strip()
            return (t[:100] + "…") if len(t) > 100 else t
    if isinstance(text, dict):
        st = text.get("status")
        if st == "ok":
            val = text.get("value")
            if isinstance(val, dict):
                bits = []
                for k in ("in_panel", "alias", "matched", "path", "stop_hint"):
                    if k in val:
                        bits.append(f"{k}={val[k]}")
                preds = val.get("predictions")
                if isinstance(preds, list) and preds:
                    p0 = preds[0] if isinstance(preds[0], dict) else {}
                    if "prob" in p0:
                        bits.append(f"prob={p0.get('prob')}")
                if bits:
                    return "ok · " + ", ".join(str(b) for b in bits[:5])
            return "ok · " + _short_json(val, 90)
        if st == "error":
            return f"error · {text.get('reason') or text.get('message') or 'failed'}"
        return _short_json(text, 100)
    return _short_json(text, 100)


def _show_full_thinking() -> bool:
    """Expand folded thoughts (Cursor-style default = collapsed)."""
    return os.environ.get("RBP_SHOW_THINKING", "").strip().lower() in (
        "1", "true", "yes", "full", "expand",
    )


def _slim_tool_args(args: dict[str, Any]) -> dict[str, Any]:
    prefer = (
        "rbp_id", "rbps", "query", "uniprot", "alias", "name",
        "cohort", "rna", "sequence", "target", "encoder", "device",
    )
    slim: dict[str, Any] = {}
    for k in prefer:
        if k not in args:
            continue
        v = args[k]
        if k in ("rna", "sequence") and isinstance(v, str) and len(v) > 24:
            unit = "nt" if k == "rna" else "aa"
            slim[k] = f"{v[:12]}…({len(v)}{unit})"
        else:
            slim[k] = v
    if not slim:
        slim = {k: args[k] for k in list(args)[:4]}
    return slim


def make_agent_trace_hook(
    *,
    spinner: Optional[ThinkingSpinner] = None,
    stream: TextIO = sys.stderr,
    show_args: bool = True,
):
    """AgentHook: tools visible; thinking buffered then folded (Cursor-like).

    Live token spam is suppressed. Full thought text only when
    ``RBP_SHOW_THINKING=1`` (also saved under artifacts/sessions/ root).
    """
    from nanobot.agent.hook import AgentHook, AgentHookContext, AgentRunHookContext

    class _AgentTraceHook(AgentHook):
        def __init__(self) -> None:
            super().__init__()
            self._s = Style(stream)
            self._thought_parts: list[str] = []
            self._thought_t0: Optional[float] = None
            self._thought_folded = False
            self._tools_this_run: list[str] = []
            self._step = 0
            self._journal = False  # True while printing tool lines (spinner stopped)

        def _out(self, line: str) -> None:
            # During tool journal the spinner is stopped — no pause/resume thrash.
            if spinner and spinner._active and not self._journal:
                spinner.pause()
            stream.write(line + "\n")
            stream.flush()
            if spinner and spinner._active and not self._journal:
                spinner.resume()

        def _thought_text(self) -> str:
            return "".join(self._thought_parts).strip()

        def _save_thought(self, text: str) -> Optional[Path]:
            if not text:
                return None
            try:
                from app.core.paths import SESSIONS, ensure_artifact_dirs

                ensure_artifact_dirs()
                path = SESSIONS / "last_thinking.txt"
                path.write_text(text + "\n", encoding="utf-8")
                return path
            except OSError:
                return None

        def _fold_thought(self) -> None:
            """Replace live thinking with one Cursor-like collapsed line."""
            if self._thought_folded:
                return
            text = self._thought_text()
            if not text and self._thought_t0 is None:
                return
            self._thought_folded = True
            elapsed = 0.0
            if self._thought_t0 is not None:
                elapsed = max(0.0, time.perf_counter() - self._thought_t0)
            path = self._save_thought(text)
            preview = " ".join(text.split())
            if len(preview) > 96:
                preview = preview[:95] + "…"
            # Collapsed header (always)
            self._out(
                f"  {self._s.magenta('✻')} {self._s.bold('Thought')}"
                + self._s.dim(f"  ·  {elapsed:.1f}s  ·  folded")
                + (self._s.dim(f"  ·  {len(text)} chars") if text else "")
            )
            if preview:
                self._out(self._s.dim(f"      {preview}"))
            if _show_full_thinking() and text:
                self._out(self._s.dim("      ── full thinking ──"))
                for ln in text.splitlines() or [text]:
                    self._out(self._s.dim(f"      {ln}"))
                self._out(self._s.dim("      ──────────────────"))
            elif path is not None:
                self._out(
                    self._s.dim(
                        f"      full: {path}  ·  expand: RBP_SHOW_THINKING=1"
                    )
                )
            self._thought_parts.clear()
            self._thought_t0 = None

        async def before_run(self, context: AgentRunHookContext) -> None:
            self._tools_this_run.clear()
            self._step = 0
            self._thought_parts.clear()
            self._thought_folded = False
            self._thought_t0 = None
            self._journal = False
            self._run_t0 = time.perf_counter()
            if spinner and not spinner._active:
                spinner.start()
            self._out(self._s.bold(self._s.cyan("✶ agent")) + self._s.dim("  working"))

        async def before_iteration(self, context: AgentHookContext) -> None:
            n = context.iteration + 1
            # Soft turn marker only; keep spinner label stable ("Thinking")
            self._out(self._s.dim(f"── turn {n} ──"))
            self._thought_folded = False
            if spinner and not spinner._active:
                spinner.start()

        async def emit_reasoning(self, reasoning_content: str | None) -> None:
            # Buffer only — never touch spinner per token (that caused flicker).
            if not reasoning_content:
                return
            if self._thought_t0 is None:
                self._thought_t0 = time.perf_counter()
            self._thought_parts.append(reasoning_content)

        async def emit_reasoning_end(self) -> None:
            self._fold_thought()

        async def before_execute_tools(self, context: AgentHookContext) -> None:
            # Non-streaming models put a plan in response.content
            resp = context.response
            thought = (getattr(resp, "content", None) or "").strip() if resp else ""
            if thought and not context.streamed_reasoning and not self._thought_parts:
                self._thought_t0 = self._thought_t0 or time.perf_counter()
                self._thought_parts.append(thought)
            self._fold_thought()

            # Stop LLM-thinking spinner while we print the tool list.
            if spinner and spinner._active:
                spinner.stop()
            self._journal = True

            calls = list(context.tool_calls or [])
            if not calls:
                self._journal = False
                if spinner:
                    spinner.start()
                return
            self._out(self._s.dim("  tools"))
            for tc in calls:
                self._step += 1
                name = getattr(tc, "name", "?")
                self._tools_this_run.append(name)
                args = getattr(tc, "arguments", None) or {}
                arg_s = ""
                if show_args and isinstance(args, dict):
                    arg_s = _short_json(_slim_tool_args(args), 160)
                self._out(
                    f"  {self._s.yellow(f'{self._step:>2}.')} "
                    f"{self._s.bold(name)}"
                    + (self._s.dim(f"  {arg_s}") if arg_s else "")
                )

            # Keep a wait spinner while tools run (esp. parallel / slow science).
            # Model is not thinking here — show wait feedback instead of a blank TTY.
            n = len(calls)
            wait_hint = f"waiting for {n} tool" + ("s" if n != 1 else "")
            self._journal = False
            if spinner and not spinner._active:
                spinner.start(wait_hint, reset_clock=True)

        async def after_iteration(self, context: AgentHookContext) -> None:
            self._fold_thought()
            # Stop wait spinner before result journal lines.
            if spinner and spinner._active:
                spinner.stop()
            self._journal = True
            results = list(context.tool_results or [])
            calls = list(context.tool_calls or [])
            events = list(context.tool_events or [])
            for i, tc in enumerate(calls):
                name = getattr(tc, "name", "tool")
                res = results[i] if i < len(results) else None
                if isinstance(res, tuple) and res:
                    res = res[0]
                ev = events[i] if i < len(events) and isinstance(events[i], dict) else {}
                if ev.get("status") == "error":
                    summary = f"error · {ev.get('detail') or _summarize_tool_result(res)}"
                    ok = False
                else:
                    summary = _summarize_tool_result(res) if res is not None else "—"
                    ok = not str(summary).startswith("error")
                mark = self._s.green("←") if ok else self._s.red("←")
                self._out(
                    f"  {mark} {self._s.bold(name) if ok else self._s.red(name)}"
                    f"  {self._s.dim(summary)}"
                )

            self._journal = False
            if spinner and not spinner._active:
                spinner.start("Thinking")

        async def after_run(self, context: AgentRunHookContext) -> None:
            self._fold_thought()
            self._journal = False
            if spinner and spinner._active:
                spinner.stop()
            used = list(context.tools_used or self._tools_this_run)
            seen: list[str] = []
            for n in used:
                if n not in seen:
                    seen.append(n)
            elapsed = 0.0
            if getattr(self, "_run_t0", None) is not None:
                elapsed = max(0.0, time.perf_counter() - self._run_t0)
            elif spinner is not None and hasattr(spinner, "elapsed"):
                try:
                    elapsed = float(spinner.elapsed())
                except Exception:
                    elapsed = 0.0
            bits = [self._s.dim("done"), self._s.dim(f"{elapsed:.1f}s")]
            if seen:
                bits.append(self._s.dim(f"{len(seen)} tools"))
                bits.append(
                    self._s.dim(
                        ", ".join(seen[:10])
                        + (f" (+{len(seen) - 10})" if len(seen) > 10 else "")
                    )
                )
            self._out("  " + "  ·  ".join(bits))
            self.last_tools = seen
            self.last_elapsed = elapsed

        async def on_error(self, context: AgentRunHookContext) -> None:
            self._fold_thought()
            self._journal = False
            if spinner and spinner._active:
                spinner.stop()
            err = context.error or (
                type(context.exception).__name__ if context.exception else "error"
            )
            self._out(self._s.red(f"▸ error  {err}"))

    return _AgentTraceHook()


def make_progress_hook(spinner: ThinkingSpinner):
    """Back-compat alias: full agent step trace driven by spinner."""
    return make_agent_trace_hook(spinner=spinner)


# ---------------------------------------------------------------------------
# Verdict display
# ---------------------------------------------------------------------------

def format_verdict_display(result: Any) -> str:
    """Pretty-print a clean verdict JSON (unwrap nested fences).

    Also supports multi-part acceptance answers ``{"A": {...}, "B": {...}, "C": ...}``
    without collapsing them into a placeholder No/null verdict.
    """
    from app.core.verdict_schema import (
        _parse_json_object,
        extract_verdict_from_content,
        normalize_verdict,
    )

    content = getattr(result, "content", None) or ""
    parsed = _parse_json_object(content) if content else None
    if isinstance(parsed, dict) and (
        ("A" in parsed and isinstance(parsed.get("A"), dict))
        or ("a" in parsed and isinstance(parsed.get("a"), dict))
    ):
        # Acceptance / multi-case runs: show the structured report as-is
        return json.dumps(parsed, indent=2, ensure_ascii=False) + "\n"

    authoritative = getattr(result, "verdict", None)
    verdict = (
        normalize_verdict(authoritative)
        if isinstance(authoritative, dict)
        else (extract_verdict_from_content(content) if content else {})
    )
    # Placeholder detection: normalize filled a generic sentence when LLM
    # returned a non-flat object (e.g. only nested keys).
    expl = str(verdict.get("explanation") or "")
    if (
        not verdict.get("p_hat")
        and verdict.get("label") == "No"
        and "Mode=unknown" in expl
        and content
        and len(content) > 200
    ):
        return content.strip() + "\n"

    if not verdict.get("explanation") or "Mode=unknown" in expl:
        alt = normalize_verdict(getattr(result, "verdict", None) or {})
        if alt.get("explanation") and "Mode=unknown" not in str(alt.get("explanation")):
            verdict = alt

    display = {
        "label": verdict.get("label"),
        "p_hat": verdict.get("p_hat"),
        "confidence": verdict.get("confidence"),
        "explanation": verdict.get("explanation"),
        "supporting_rbps": verdict.get("supporting_rbps") or [],
        "caveats": verdict.get("caveats") or [],
    }
    display = {k: v for k, v in display.items() if v is not None}
    # Internal provenance stays on the turn verdict; only donor terms surface
    # as evidence_table above the public JSON (then stripped from the body).
    provenance = verdict.get("score_provenance")
    if isinstance(provenance, dict):
        aggregation = provenance.get("aggregation")
        if isinstance(aggregation, dict) and isinstance(aggregation.get("terms"), list):
            display["evidence_table"] = aggregation["terms"]
    return json.dumps(display, indent=2, ensure_ascii=False) + "\n"


def cgroup_memory_gb() -> Optional[float]:
    """Return cgroup memory.max in GiB, or None if unlimited / unknown."""
    for path in (
        Path("/sys/fs/cgroup/memory.max"),
        Path("/sys/fs/cgroup/memory/memory.limit_in_bytes"),
    ):
        try:
            raw = path.read_text().strip()
        except OSError:
            continue
        if raw in ("max", ""):
            return None
        try:
            n = int(raw)
        except ValueError:
            continue
        if n >= 2**60:
            return None
        return n / (1024**3)
    return None


def memory_blocker_message(min_gb: float = 8.0) -> Optional[str]:
    """Advisory only: ideal GPU host needs enough RAM for RhoBind / ESM.

    Does not change agent behaviour or force CPU — product path still prefers
    CUDA via ``RHOBIND_DEVICE=auto``. Raise the cgroup / instance size before
    claiming scientific goldens.
    """
    gb = cgroup_memory_gb()
    if gb is not None and gb < min_gb:
        return (
            f"NOTE: cgroup memory.max ≈ {gb:.1f} GiB "
            f"(ideal env ≥ {min_gb:.0f} GiB RAM + CUDA for RhoBind/ESM). "
            "This host may OOM science tools (rc=137) → p_hat stays null "
            "(scores remain tool-sourced). Upgrade instance for acceptance runs."
        )
    return None


def run_agent_turn_streamed_sync(
    agent: Any,
    prompt: str,
    *,
    session_key: str,
    extra_hooks: Optional[list[Any]] = None,
    bot_name: str = "rbp-agent",
) -> Any:
    """Sync helper: streamed run + phase spinner + folded thought + tool steps.

    Final JSON is not printed here — caller uses ``print_verdict_block``.
    Answer tokens are not Live-rendered (JSON contract → verdict box only).
    """
    import asyncio

    spinner = ThinkingSpinner(bot_name=bot_name)
    progress = make_agent_trace_hook(spinner=spinner)
    hooks = [progress, *(extra_hooks or [])]
    with spinner:
        result = asyncio.run(
            agent.run_streamed(
                prompt,
                session_key=session_key,
                extra_hooks=hooks,
                renderer=None,
            )
        )
    try:
        result._ux_elapsed = float(
            getattr(progress, "last_elapsed", None) or spinner.elapsed()
        )
        result._ux_tools = list(getattr(progress, "last_tools", []) or [])
    except Exception:
        pass
    return result
