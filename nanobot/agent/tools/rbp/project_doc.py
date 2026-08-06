# -*- coding: utf-8 -*-
"""Allowlisted project-markdown reader for product / skill docs.

Tool: ``read_project_doc``. When the user pastes a ``docs/`` or ``skills/`` path,
returns a text chunk (offset / max_chars pagination). Paths resolve through
``path_guard.resolve_doc_path`` — not a general ``read_file``.

Does not read FASTA or code; use ``score_binding_fasta`` for labeled FASTA
eval. No scientific scores are produced here.

CLI examples:
  nanobot-bio agent --doc docs/eval/UNSEEN_RBP_TEST_PROMPTS_20.md
  nanobot-bio agent --message "Summarize workspace/skills/rbp-agent/SKILL.md via read_project_doc"
"""

from __future__ import annotations

import asyncio
from typing import Any

from nanobot.agent.tools.core.base import Tool, tool_parameters

from nanobot.agent.tools.rbp.common import dumps, err, ok, timed_call
from nanobot.agent.tools.rbp.path_guard import resolve_doc_path

_DEFAULT_MAX_CHARS = 12_000
_HARD_MAX_CHARS = 24_000


def read_project_doc(
    *,
    path: str,
    offset: int = 0,
    max_chars: int = _DEFAULT_MAX_CHARS,
) -> dict[str, Any]:
    """Read a slice of an allowlisted markdown file."""
    try:
        resolved = resolve_doc_path(path)
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    try:
        text = resolved.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        return {"ok": False, "error": f"cannot read: {e}"}

    off = max(0, int(offset or 0))
    limit = int(max_chars or _DEFAULT_MAX_CHARS)
    limit = max(1, min(limit, _HARD_MAX_CHARS))
    chunk = text[off : off + limit]
    next_off = off + len(chunk)
    eof = next_off >= len(text)
    return {
        "ok": True,
        "path": str(resolved),
        "offset": off,
        "next_offset": next_off,
        "max_chars": limit,
        "total_chars": len(text),
        "eof": eof,
        "content": chunk,
    }


@tool_parameters(
    {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path to a .md under docs/ or skills/ (allowlisted)",
            },
            "offset": {
                "type": "integer",
                "default": 0,
                "description": "Character offset for continued reads",
            },
            "max_chars": {
                "type": "integer",
                "default": _DEFAULT_MAX_CHARS,
                "description": f"Chunk size (default {_DEFAULT_MAX_CHARS}, max {_HARD_MAX_CHARS})",
            },
        },
        "required": ["path"],
    }
)
class ReadProjectDocTool(Tool):
    """Chunked allowlisted markdown reader for docs/skills — not general read_file."""

    _plugin_discoverable = True
    _scopes = {"core", "subagent"}

    @property
    def name(self) -> str:
        return "read_project_doc"

    @property
    def description(self) -> str:
        return (
            "Read an allowlisted project markdown file (.md) when the user pastes "
            "a docs/ or skills/ path. Returns a text chunk; if eof=false, call again "
            "with offset=next_offset. Does NOT read FASTA/code; use score_binding_fasta "
            "for .fasta. Not general read_file."
        )

    @property
    def read_only(self) -> bool:
        return True

    async def execute(self, **kwargs: Any) -> str:
        path = (kwargs.get("path") or "").strip()
        if not path:
            return dumps(err("path required"))
        try:
            offset = int(kwargs.get("offset") or 0)
        except (TypeError, ValueError):
            offset = 0
        try:
            max_chars = int(kwargs.get("max_chars") or _DEFAULT_MAX_CHARS)
        except (TypeError, ValueError):
            max_chars = _DEFAULT_MAX_CHARS

        def _run() -> dict[str, Any]:
            return read_project_doc(path=path, offset=offset, max_chars=max_chars)

        out, ms, error = await asyncio.to_thread(lambda: timed_call(_run))
        if error:
            return dumps(err(str(error), ms or 0.0))
        if not isinstance(out, dict):
            return dumps(err("read_project_doc failed", ms or 0.0))
        if out.get("ok") is False:
            return dumps(err(str(out.get("error") or "read failed"), ms or 0.0))
        return dumps(ok(out, ms or 0.0))


__all__ = ["ReadProjectDocTool", "read_project_doc"]
