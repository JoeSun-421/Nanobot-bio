"""
nanobot - A lightweight AI agent framework
"""

from __future__ import annotations

import tomllib
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version
from pathlib import Path
from typing import TYPE_CHECKING, Any

# Static re-exports for IDEs / type checkers (Pylance, Pyright, PyCharm).
# Runtime still uses lazy __getattr__ below to keep import light, but
# TYPE_CHECKING makes `from nanobot import Nanobot` resolve correctly.
if TYPE_CHECKING:
    from nanobot.nanobot import (  # noqa: F401
        STREAM_EVENT_REASONING_COMPLETED,
        STREAM_EVENT_REASONING_DELTA,
        STREAM_EVENT_RUN_COMPLETED,
        STREAM_EVENT_RUN_FAILED,
        STREAM_EVENT_RUN_STARTED,
        STREAM_EVENT_TEXT_COMPLETED,
        STREAM_EVENT_TEXT_DELTA,
        STREAM_EVENT_TOOL_COMPLETED,
        STREAM_EVENT_TOOL_FAILED,
        STREAM_EVENT_TOOL_STARTED,
        STREAM_EVENT_TYPES,
        Nanobot,
        RunResult,
        RunStream,
        SessionInfo,
        SessionSnapshot,
        StreamEvent,
        StreamEventType,
    )


def _read_pyproject_version() -> str | None:
    """Read the source-tree version when package metadata is unavailable."""
    pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
    if not pyproject.exists():
        return None
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    return data.get("project", {}).get("version")


def _resolve_version() -> str:
    try:
        return _pkg_version("nanobot-bio")
    except PackageNotFoundError:
        pass
    try:
        return _pkg_version("nanobot-ai")
    except PackageNotFoundError:
        # Source checkouts: prefer nanobot-bio pyproject, then local.
        return _read_pyproject_version() or "0.5.1"


__version__ = _resolve_version()
__logo__ = "🐈"

_LAZY_EXPORTS = {
    "Nanobot": ".nanobot",
    "RunStream": ".nanobot",
    "RunResult": ".nanobot",
    "SessionInfo": ".nanobot",
    "SessionSnapshot": ".nanobot",
    "STREAM_EVENT_REASONING_COMPLETED": ".nanobot",
    "STREAM_EVENT_REASONING_DELTA": ".nanobot",
    "STREAM_EVENT_RUN_COMPLETED": ".nanobot",
    "STREAM_EVENT_RUN_FAILED": ".nanobot",
    "STREAM_EVENT_RUN_STARTED": ".nanobot",
    "STREAM_EVENT_TEXT_COMPLETED": ".nanobot",
    "STREAM_EVENT_TEXT_DELTA": ".nanobot",
    "STREAM_EVENT_TOOL_COMPLETED": ".nanobot",
    "STREAM_EVENT_TOOL_FAILED": ".nanobot",
    "STREAM_EVENT_TOOL_STARTED": ".nanobot",
    "STREAM_EVENT_TYPES": ".nanobot",
    "StreamEvent": ".nanobot",
    "StreamEventType": ".nanobot",
}


def __getattr__(name: str):
    module_path = _LAZY_EXPORTS.get(name)
    if module_path is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    from importlib import import_module
    mod = import_module(module_path, __name__)
    val = getattr(mod, name)
    globals()[name] = val
    return val


__all__ = [
    "Nanobot",
    "RunResult",
    "RunStream",
    "SessionInfo",
    "SessionSnapshot",
    "STREAM_EVENT_REASONING_COMPLETED",
    "STREAM_EVENT_REASONING_DELTA",
    "STREAM_EVENT_RUN_COMPLETED",
    "STREAM_EVENT_RUN_FAILED",
    "STREAM_EVENT_RUN_STARTED",
    "STREAM_EVENT_TEXT_COMPLETED",
    "STREAM_EVENT_TEXT_DELTA",
    "STREAM_EVENT_TOOL_COMPLETED",
    "STREAM_EVENT_TOOL_FAILED",
    "STREAM_EVENT_TOOL_STARTED",
    "STREAM_EVENT_TYPES",
    "StreamEvent",
    "StreamEventType",
]
