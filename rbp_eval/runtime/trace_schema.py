# -*- coding: utf-8 -*-
"""Structured trace events for self-evolution (OpenHands / Agents-SDK style).

All agent/eval JSONL rows should be buildable via :func:`make_event` so
attribution and cache promotion can rely on stable keys.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

# Canonical event types (extensible; unknown types still allowed)
EVENT_TYPES = frozenset(
    {
        "before_execute_tools",
        "after_tools",
        "tool_result",
        "query_end",
        "nanobot_run_failed",
        "stage",
        "dedupe_hit",
        "axis_skipped",
    }
)

REQUIRED_KEYS = ("ts", "session_key", "type")


def utc_ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def make_event(
    type_: str,
    *,
    session_key: str = "rbp:default",
    tool: Optional[str] = None,
    args_hash: Optional[str] = None,
    status: Optional[str] = None,
    latency_ms: Optional[float] = None,
    **extra: Any,
) -> dict[str, Any]:
    """Build a structured TraceEvent dict."""
    row: dict[str, Any] = {
        "ts": utc_ts(),
        "session_key": session_key,
        "type": type_,
        "schema": "rbp_trace/v1",
    }
    if tool is not None:
        row["tool"] = tool
    if args_hash is not None:
        row["args_hash"] = args_hash
    if status is not None:
        row["status"] = status
    if latency_ms is not None:
        row["latency_ms"] = latency_ms
    for k, v in extra.items():
        if v is not None:
            row[k] = v
    return row


def validate_event(row: dict[str, Any]) -> list[str]:
    """Return list of validation problems (empty = ok)."""
    probs: list[str] = []
    for k in REQUIRED_KEYS:
        if k not in row:
            probs.append(f"missing:{k}")
    if row.get("type") and row["type"] not in EVENT_TYPES:
        # warn-level only — allow forward-compat types
        pass
    return probs
