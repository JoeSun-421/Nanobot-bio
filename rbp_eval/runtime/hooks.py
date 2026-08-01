# -*- coding: utf-8 -*-
"""Trace hooks for self-evolution.

- ``JsonlTraceHook``: works without nanobot (fallback / CI).
- ``rbp_eval.runtime.nanobot_hooks.RBPTraceHook``: real AgentHook when nanobot installed.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


class JsonlTraceHook:
    """Minimal JSONL trace logger (usable offline without nanobot)."""

    def __init__(self, out_path: str | Path, session_key: str = "rbp:default"):
        self.out_path = Path(out_path)
        self.out_path.parent.mkdir(parents=True, exist_ok=True)
        self.session_key = session_key
        self._buffer: list[dict[str, Any]] = []

    def push_event(self, event: dict[str, Any]) -> None:
        type_ = str(event.get("type") or "query_end")
        extra = {
            k: v
            for k, v in event.items()
            if k not in ("type", "ts", "session_key", "schema")
        }
        try:
            from rbp_eval.runtime.trace_schema import make_event

            row = make_event(type_, session_key=self.session_key, **extra)
        except Exception:
            row = {
                "ts": datetime.now(timezone.utc).isoformat(),
                "session_key": self.session_key,
                **event,
            }
        self._buffer.append(row)
        with open(self.out_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    # alias for older code
    def log(self, event: dict[str, Any]) -> None:
        self.push_event(event)

    def emit_query_end(
        self,
        *,
        content: Optional[str] = None,
        tools_used: Optional[list[str]] = None,
        verdict: Optional[dict[str, Any]] = None,
    ) -> None:
        """API-compatible with ``nanobot_hooks.RBPTraceHook.emit_query_end``."""
        donors: list[Any] = []
        if isinstance(verdict, dict):
            donors = list(verdict.get("supporting_rbps") or [])
        self.push_event(
            {
                "type": "query_end",
                "verdict": verdict,
                "donors": donors,
                "tools_used": tools_used or [],
                "content": content,
            }
        )

    def on_query_end(
        self,
        query: str,
        result: dict[str, Any],
        tool_calls: Optional[list[dict[str, Any]]] = None,
    ) -> None:
        self.push_event(
            {
                "type": "query_end",
                "query": query,
                "tool_calls": tool_calls or [],
                "result_keys": list(result.keys()) if isinstance(result, dict) else [],
                "verdict": result.get("verdict") if isinstance(result, dict) else None,
            }
        )


# Back-compat name
RBPTraceHook = JsonlTraceHook
