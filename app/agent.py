# -*- coding: utf-8 -*-
"""Product agent assembly: RBPAgent wires delivery tools onto Nanobot.run."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any, Optional, Union

_PKG_DIR = Path(__file__).resolve().parent  # .../nanobot-bio/app
_ROOT = Path(os.environ.get("NANOBOT_BIO_ROOT", _PKG_DIR.parent)).expanduser().resolve()

try:
    from app.dotenv_util import load_dotenv

    load_dotenv(_ROOT / ".env", override=False)
except Exception:
    pass

_BIO_ROOT = Path(os.environ.get("BIO_ROOT", _ROOT.parent)).expanduser().resolve()
# Slim vendor: runtime is in-repo nanobot-bio/nanobot (Proposal §6.2).
_DEFAULT_NANOBOT_SRC = _ROOT / "nanobot"

os.environ.setdefault("NANOBOT_BIO_ROOT", str(_ROOT))
os.environ.setdefault("BIO_ROOT", str(_BIO_ROOT))
os.environ.setdefault("NANOBOT_SRC", str(_DEFAULT_NANOBOT_SRC))

# Prefer in-repo nanobot package; keep BIO_ROOT for delivery sibling layout only.
_root_s = str(_ROOT)
_bio_s = str(_BIO_ROOT)
for _p in (_root_s, _bio_s):
    while _p in sys.path:
        sys.path.remove(_p)
# Put bio root first so `import nanobot` resolves to nanobot-bio/nanobot.
sys.path.insert(0, _root_s)
# BIO_ROOT second (delivery sibling paths); never ahead of in-repo package.
if _bio_s != _root_s:
    sys.path.insert(1, _bio_s)

from app.backends.delivery.client import DeliveryToolClient
from app.backends.delivery.env import apply_delivery_env
from app.core.paths import DEFAULT_AGENT_TRACE, ensure_artifact_dirs
from app.core.verdict_schema import (
    extract_verdict_from_content,
    normalize_verdict_with_turn_state,
    validate_verdict,
)

PACKAGE_ROOT = _ROOT
WORKSPACE = PACKAGE_ROOT / "workspace"
DEFAULT_TRACE = DEFAULT_AGENT_TRACE
ensure_artifact_dirs()

_SKILL_CANDIDATES = (
    PACKAGE_ROOT / "plugin" / "nanobot" / "skills" / "rbp-agent" / "SKILL.md",
    PACKAGE_ROOT / "workspace" / "skills" / "rbp-agent" / "SKILL.md",
)


# ---------------------------------------------------------------------------
# Install / skill
# ---------------------------------------------------------------------------

def install_rbp_tools_into_nanobot() -> Path:
    """Sync SoT tools/skill into installed nanobot runtime + workspace."""
    from app.sync_overlay import sync_overlay

    sync_overlay()
    nb = Path(os.environ.get("NANOBOT_SRC", _DEFAULT_NANOBOT_SRC)).expanduser().resolve()
    return nb / "agent" / "tools" / "rbp"


_AGENTS_BOOTSTRAP = """# RNA–RBP agent

You predict RNA–RBP interactions using delivery tools only.

## Stage 0 (mandatory when RBP is in catalogue)

1. `resolve_rbp` → if `in_panel=true`, call `predict_interaction` **once** with that alias (own head).
2. Map `predictions[0].prob` → `p_hat` / label; emit **JSON only**; **stop**.
3. Do **not** call transfer / seq_similarity / domain / literature for in-panel targets.

**LOO / force_transfer override:** when the user requests leave-one-out, treat-as-unseen, or `force_transfer=true`, Stage 0 own-head STOP does **not** apply. Still `resolve_rbp`, then retrieve → fuse → commit → abstain → predict on **foreign donors only** (never the query/target alias alone).

Golden: delivery `agent/examples/sample_rna_pos.txt` × PTBP1 → own-head ≈ 0.966.

Unseen RBPs: retrieve → predict donor heads → integrate (BUILD_SPEC §4).
`p_hat` comes only from predict tools; RNA is not passed into protein-only tools.

## Structure (unseen / AFDB miss)

AFDB `structure_fetch` → `struct_similarity`; **AF3 only on AFDB miss**.
No QUERY UniProt/alias → `predict_structure(sequence=…)` once. Never invent UniProt
or borrow a homolog accession to skip AF3. Failure ≠ sim 0.
"""


def ensure_workspace_skill(workspace: Optional[Path] = None) -> Path:
    """Skill + AGENTS.md under nanobot workspace (always-on Stage 0 rules)."""
    ws = Path(workspace or WORKSPACE)
    dest = ws / "skills" / "rbp-agent" / "SKILL.md"
    for src in _SKILL_CANDIDATES:
        if src.is_file():
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
            break
    agents = ws / "AGENTS.md"
    agents.parent.mkdir(parents=True, exist_ok=True)
    # Keep our Stage-0 contract at the top; preserve any extra user notes below a marker.
    marker = "\n<!-- user-notes -->\n"
    extra = ""
    if agents.is_file():
        old = agents.read_text(encoding="utf-8")
        if marker in old:
            extra = old.split(marker, 1)[1]
        elif not old.strip().startswith("# RNA–RBP agent"):
            extra = old
    agents.write_text(_AGENTS_BOOTSTRAP + marker + extra, encoding="utf-8")
    return dest


def skill_path() -> Optional[Path]:
    for p in _SKILL_CANDIDATES:
        if p.is_file():
            return p
    return None


def _raw_mode() -> str:
    """Product default all; narrow via RBP_RAW_TOOLS=whitelist|none."""
    import os

    return os.environ.get("RBP_RAW_TOOLS", "all")


def _register_tools(registry) -> list[str]:
    """Register curated P0–P2 tools + full delivery surface (default all)."""
    try:
        from nanobot.agent.tools.rbp.register import register_rbp_tools

        _reg, names = register_rbp_tools(registry, include_raw_delivery=_raw_mode())
        # Guard: empty ToolRegistry is falsy (has __len__); ensure tools land on caller registry
        if _reg is not registry and registry is not None:
            for n in names:
                t = _reg.get(n)
                if t is not None and registry.get(n) is None:
                    registry.register(t)
        return names
    except ImportError:
        pass

    # Try install then import
    try:
        install_rbp_tools_into_nanobot()
        from nanobot.agent.tools.rbp.register import register_rbp_tools

        _reg, names = register_rbp_tools(registry, include_raw_delivery=_raw_mode())
        if _reg is not registry and registry is not None:
            for n in names:
                t = _reg.get(n)
                if t is not None and registry.get(n) is None:
                    registry.register(t)
        return names
    except Exception:
        pass

    # Fallback: delivery registry (requires real nanobot Tool base)
    from app.backends.delivery.registry import register_tools

    if registry is None:
        raise TypeError("register_tools requires a ToolRegistry")
    return register_tools(registry, include_raw_delivery=_raw_mode())


# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------

class AgentResult:
    def __init__(
        self,
        content: str,
        *,
        mode: str,
        session_key: str,
        tool_names: list[str],
        verdict: Optional[dict[str, Any]] = None,
        traces: Optional[list[dict[str, Any]]] = None,
        error: Optional[str] = None,
        linux_notes: Optional[list[str]] = None,
        mvp_complete: bool = False,
        verdict_valid: bool = False,
        verdict_errors: Optional[list[str]] = None,
        tools_used: Optional[list[str]] = None,
        usage: Optional[dict[str, Any]] = None,
        stop_reason: Optional[str] = None,
    ):
        self.content = content
        self.mode = mode  # nanobot_llm | error (| fixture_pipeline if explicitly requested)
        self.session_key = session_key
        self.tool_names = tool_names
        self.verdict = verdict or {}
        self.traces = traces or []
        self.error = error
        self.linux_notes = linux_notes or []
        self.mvp_complete = mvp_complete
        self.verdict_valid = verdict_valid
        self.verdict_errors = verdict_errors or []
        self.tools_used = tools_used or []
        self.usage = usage or {}
        self.stop_reason = stop_reason

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "session_key": self.session_key,
            "mvp_complete": self.mvp_complete,
            "verdict_valid": self.verdict_valid,
            "verdict_errors": self.verdict_errors,
            "verdict": self.verdict,
            "error": self.error,
            "n_tools": len(self.tool_names),
            "n_traces": len(self.traces),
            "linux_notes": self.linux_notes,
            "content": self.content,
        }


# ---------------------------------------------------------------------------
# RBPAgent
# ---------------------------------------------------------------------------

class RBPAgent:
    """Nanobot controller + RBP delivery tools. No fixed pipeline fallback."""

    _bot: Any = None

    def __init__(
        self,
        *,
        offline: bool = False,
        device: str = "auto",
        use_conda: bool = True,
        workspace: Optional[Union[str, Path]] = None,
        config_path: Optional[Union[str, Path]] = None,
        hooks: Optional[list] = None,
        auto_install_into_nanobot: bool = False,
        prefer_nanobot_llm: bool = True,
        allow_fallback: bool = False,  # kept for API compat; ignored (always False)
    ):
        apply_delivery_env()
        # Prefer CUDA when available (HANDOFF device=cuda). Light resolve — no torch.
        try:
            from nanobot.agent.tools.rbp.common import resolve_device

            resolved = resolve_device(device)
        except Exception:
            resolved = "cuda" if str(device).lower() in ("cuda", "gpu", "auto", "") else str(device or "cpu")
        os.environ["RHOBIND_DEVICE"] = resolved
        self.workspace = Path(workspace or WORKSPACE)
        self.config_path = Path(config_path).expanduser() if config_path else None
        ensure_workspace_skill(self.workspace)
        self.client = DeliveryToolClient(
            offline=offline, device=resolved, use_conda=use_conda
        )
        self.hooks = list(hooks or [])
        self.device = resolved
        self.offline = offline
        self.prefer_nanobot_llm = prefer_nanobot_llm
        self.allow_fallback = False
        if allow_fallback:
            # core/pipeline removed — product path is Nanobot.run only
            pass

        # Sync only when asked, or when runtime overlay is missing (skip-if-fresh inside).
        need_install = bool(auto_install_into_nanobot)
        if not need_install:
            try:
                from nanobot.agent.tools.rbp.register import register_all  # noqa: F401
            except Exception:
                need_install = True
        if need_install:
            try:
                install_rbp_tools_into_nanobot()
            except Exception as e:
                if os.environ.get("RBP_DEBUG"):
                    print(f"[RBPAgent] install into nanobot (optional): {e}")

        self.registry = None
        self.tool_names: list[str] = []
        self._init_registry()
    def _init_registry(self) -> None:
        try:
            from nanobot.agent.tools.core.registry import ToolRegistry

            self.registry = ToolRegistry()
            self.tool_names = _register_tools(self.registry)
        except ImportError as e:
            self.registry = None
            self.tool_names = []
            print(f"[RBPAgent] nanobot not importable ({e}); tool registration deferred.")

    # ----- nanobot wiring -----

    def tool_schemas(self) -> list[dict[str, Any]]:
        if self.registry is None:
            return []
        return self.registry.get_definitions()

    def inject_into_nanobot(self, bot: Any) -> list[str]:
        """Register all RBP/delivery tools on live Nanobot AgentLoop.tools."""
        if self.registry is None:
            self._init_registry()
        if self.registry is None:
            raise RuntimeError("nanobot ToolRegistry unavailable; install nanobot first")
        loop = getattr(bot, "_loop", None)
        if loop is None or not hasattr(loop, "tools"):
            raise TypeError("Expected Nanobot instance with _loop.tools")
        # Drop shell/network/filesystem defaults that derail RNA–RBP evaluation
        # (LLM may pip install or read workspace dumps). These tools are simply
        # unregistered — the LLM will not see them. literature_search is the
        # supported retrieval path (see SKILL).
        for noisy in (
            "exec",
            "spawn",
            "write_stdin",
            "list_exec_sessions",
            "run_cli_app",
            "web_search",
            "web_fetch",
            "long_task",
            "apply_patch",
            "edit_file",
            "write_file",
            "find_files",
            "grep",
            "list_dir",
            "read_file",
        ):
            try:
                loop.tools.unregister(noisy)
            except Exception:
                pass
        names = []
        for name in self.tool_names:
            t = self.registry.get(name)
            if t is not None:
                loop.tools.register(t)
                names.append(name)
        active = sorted(loop.tools._tools.keys())
        if os.environ.get("RBP_DEBUG"):
            print(f"[RBPAgent] tools after inject ({len(active)}): {active}")
        return names

    def build_nanobot(self) -> Any:
        from nanobot import Nanobot

        try:
            from app.core.onboard import prepare_llm_config

            prepare_llm_config(persist=True)
        except Exception:
            pass

        ensure_workspace_skill(self.workspace)
        kwargs: dict[str, Any] = {
            "workspace": self.workspace,
            "scientific_mode": True,
        }
        if self.config_path is not None:
            kwargs["config_path"] = self.config_path
        bot = Nanobot.from_config(**kwargs)
        self.inject_into_nanobot(bot)
        self._bot = bot
        return bot

    def get_nanobot(self) -> Any:
        bot = getattr(self, "_bot", None)
        if bot is None:
            bot = self.build_nanobot()
        return bot

    async def run(
        self,
        message: str,
        *,
        session_key: str = "rbp:default",
        force_fallback: bool = False,
        fallback_kwargs: Optional[dict[str, Any]] = None,
        trace_path: Optional[Union[str, Path]] = None,
        extra_hooks: Optional[list[Any]] = None,
        ephemeral: bool = True,
        model: Optional[str] = None,
        model_preset: Optional[str] = None,
    ) -> AgentResult:
        """Run Nanobot LLM agent (primary path). No pipeline fallback.

        Defaults to ``ephemeral=True`` so each query does not persist or replay
        prior scientific tool/verdict transcripts as authoritative scores.
        """
        notes = linux_feasibility_notes()
        if force_fallback or fallback_kwargs:
            err = (
                "core/pipeline was removed. Product path is Nanobot.run only. "
                "Use rbp-agent agent|chat|own-head."
            )
            return AgentResult(
                content=json.dumps({"error": err}, ensure_ascii=False),
                mode="error",
                session_key=session_key,
                tool_names=list(self.tool_names),
                error=err,
                linux_notes=notes,
                mvp_complete=False,
            )

        tp = Path(trace_path or DEFAULT_TRACE)
        tp.parent.mkdir(parents=True, exist_ok=True)
        trace_hook = _make_trace_hook(tp, session_key)
        hooks = [trace_hook, *self.hooks, *(extra_hooks or [])]

        if self.offline or not self.prefer_nanobot_llm:
            err = (
                "Agent path requires Nanobot LLM "
                "(offline/prefer_nanobot_llm=False unsupported)"
            )
            return AgentResult(
                content=json.dumps({"error": err}, ensure_ascii=False),
                mode="error",
                session_key=session_key,
                tool_names=list(self.tool_names),
                error=err,
                linux_notes=notes,
                mvp_complete=False,
            )

        try:
            bot = self.get_nanobot()
            # Per-query Stage 0–3 guards (own-head STOP must not leak across turns).
            try:
                from nanobot.agent.tools.rbp.annotation import prepare_tool_turn_guards

                prepare_tool_turn_guards(message)
            except Exception:
                try:
                    from nanobot.agent.tools.rbp.turn_guards import reset_stage_guards

                    reset_stage_guards()
                except Exception:
                    pass
            run_kwargs: dict[str, Any] = {
                "session_key": session_key,
                "hooks": hooks,
                "ephemeral": ephemeral,
            }
            if model:
                run_kwargs["model"] = model
            if model_preset:
                run_kwargs["model_preset"] = model_preset
            result = await bot.run(message, **run_kwargs)
            content = getattr(result, "content", None) or str(result)
            tools_used = list(getattr(result, "tools_used", None) or [])
            usage = getattr(result, "usage", None)
            if usage is not None and hasattr(usage, "__dict__"):
                usage = dict(getattr(usage, "__dict__", {}) or {})
            elif not isinstance(usage, dict):
                usage = {}
            stop_reason = getattr(result, "stop_reason", None)
            # B3: merge per-turn evidence flags (literature offline / AF3 soft-fail /
            # axis skipped / …) so every soft-failure surfaces into verdict caveats.
            verdict = normalize_verdict_with_turn_state(content)
            ok_v, verrs = validate_verdict(verdict)
            if hasattr(trace_hook, "emit_query_end"):
                try:
                    trace_hook.emit_query_end(content=content, verdict=verdict)
                except Exception:
                    pass
            elif hasattr(trace_hook, "push_event"):
                try:
                    trace_hook.push_event(
                        {
                            "type": "query_end",
                            "verdict": verdict,
                            "donors": (verdict or {}).get("supporting_rbps")
                            if isinstance(verdict, dict)
                            else [],
                            "tools_used": tools_used,
                        }
                    )
                except Exception:
                    pass
            return AgentResult(
                content=content,
                mode="nanobot_llm",
                session_key=session_key,
                tool_names=list(self.tool_names),
                verdict=verdict,
                traces=list(getattr(trace_hook, "_buffer", [])),
                linux_notes=notes,
                mvp_complete=ok_v,
                verdict_valid=ok_v,
                verdict_errors=verrs,
                tools_used=tools_used,
                usage=usage if isinstance(usage, dict) else {},
                stop_reason=str(stop_reason) if stop_reason else None,
            )
        except Exception as e:
            fb_err = f"{type(e).__name__}: {e}"
            notes = notes + [
                f"Nanobot.run failed: {fb_err}",
                "Fix: rbp-agent onboard + LLM API; ensure Nanobot runtime at $NANOBOT_SRC.",
            ]
            if hasattr(trace_hook, "push_event"):
                trace_hook.push_event({"type": "nanobot_run_failed", "error": fb_err})
            return AgentResult(
                content=json.dumps(
                    {"error": fb_err, "mode": "error"},
                    ensure_ascii=False,
                ),
                mode="error",
                session_key=session_key,
                tool_names=list(self.tool_names),
                error=fb_err,
                linux_notes=notes,
                mvp_complete=False,
            )

    def run_sync(self, message: str, **kwargs: Any) -> AgentResult:
        """Sync wrapper; accepts the same kwargs as ``run`` (incl. extra_hooks)."""
        return asyncio.run(self.run(message, **kwargs))

    async def run_streamed(
        self,
        message: str,
        *,
        session_key: str = "rbp:default",
        extra_hooks: Optional[list[Any]] = None,
        renderer: Any = None,
        trace_path: Optional[Union[str, Path]] = None,
        ephemeral: bool = True,
        model: Optional[str] = None,
        model_preset: Optional[str] = None,
    ) -> AgentResult:
        """Like ``run`` but drives ``Nanobot.run_streamed`` into a StreamRenderer.

        Defaults to ``ephemeral=True`` (same contract as ``run``).
        """
        notes = linux_feasibility_notes()
        tp = Path(trace_path or DEFAULT_TRACE)
        tp.parent.mkdir(parents=True, exist_ok=True)
        trace_hook = _make_trace_hook(tp, session_key)
        hooks = [trace_hook, *self.hooks, *(extra_hooks or [])]

        if self.offline or not self.prefer_nanobot_llm:
            err = (
                "Agent path requires Nanobot LLM "
                "(offline/prefer_nanobot_llm=False unsupported)"
            )
            return AgentResult(
                content=json.dumps({"error": err}, ensure_ascii=False),
                mode="error",
                session_key=session_key,
                tool_names=list(self.tool_names),
                error=err,
                linux_notes=notes,
                mvp_complete=False,
            )

        try:
            from nanobot.sdk.types import (
                STREAM_EVENT_TEXT_COMPLETED,
                STREAM_EVENT_TEXT_DELTA,
            )

            bot = self.get_nanobot()
            try:
                from nanobot.agent.tools.rbp.annotation import prepare_tool_turn_guards

                prepare_tool_turn_guards(message)
            except Exception:
                try:
                    from nanobot.agent.tools.rbp.turn_guards import reset_stage_guards

                    reset_stage_guards()
                except Exception:
                    pass
            run_kwargs: dict[str, Any] = {
                "session_key": session_key,
                "hooks": hooks,
                "ephemeral": ephemeral,
            }
            if model:
                run_kwargs["model"] = model
            if model_preset:
                run_kwargs["model_preset"] = model_preset
            stream = await bot.run_streamed(
                message,
                **run_kwargs,
            )
            async for ev in stream.stream_events():
                et = getattr(ev, "type", None)
                if renderer is not None and et == STREAM_EVENT_TEXT_DELTA:
                    delta = getattr(ev, "content", None) or ""
                    if delta:
                        await renderer.on_delta(delta)
                elif renderer is not None and et == STREAM_EVENT_TEXT_COMPLETED:
                    # Defer final print — caller shows verdict JSON block
                    live = getattr(renderer, "_live", None)
                    if live is not None:
                        live.stop()
                        renderer._live = None
                    if hasattr(renderer, "_stop_spinner"):
                        renderer._stop_spinner()
                    # Clear buffer so on_end would not duplicate; we skip on_end print
                    if hasattr(renderer, "_buf"):
                        renderer._buf = ""
            run_result = await stream.wait()
            content = getattr(run_result, "content", None) or ""
            verdict = normalize_verdict_with_turn_state(content)
            ok_v, verrs = validate_verdict(verdict)
            return AgentResult(
                content=content,
                mode="nanobot_llm",
                session_key=session_key,
                tool_names=list(self.tool_names),
                verdict=verdict,
                traces=list(getattr(trace_hook, "_buffer", [])),
                linux_notes=notes,
                mvp_complete=ok_v,
                verdict_valid=ok_v,
                verdict_errors=verrs,
            )
        except Exception as e:
            fb_err = f"{type(e).__name__}: {e}"
            notes = notes + [
                f"Nanobot.run_streamed failed: {fb_err}",
                "Fix: rbp-agent onboard + LLM API; ensure Nanobot runtime at $NANOBOT_SRC.",
            ]
            return AgentResult(
                content=json.dumps(
                    {"error": fb_err, "mode": "error"},
                    ensure_ascii=False,
                ),
                mode="error",
                session_key=session_key,
                tool_names=list(self.tool_names),
                error=fb_err,
                linux_notes=notes,
                mvp_complete=False,
            )

    def run_streamed_sync(self, message: str, **kwargs: Any) -> AgentResult:
        return asyncio.run(self.run_streamed(message, **kwargs))


def linux_feasibility_notes() -> list[str]:
    return [
        "Agent path: Nanobot.run + RBP tools → delivery (RhoBind needs rhobind conda + RAM/GPU).",
        "LLM config: rbp-agent onboard",
        "Portable roots: BIO_ROOT, DELIVERY_ROOT, AGENT_DB, NANOBOT_CONFIG",
    ]


def _make_trace_hook(path: Path, session_key: str) -> Any:
    try:
        from rbp_eval.runtime.nanobot_hooks import RBPTraceHook

        return RBPTraceHook(path, session_key=session_key)
    except ImportError:
        from rbp_eval.runtime.hooks import JsonlTraceHook

        return JsonlTraceHook(path, session_key=session_key)
