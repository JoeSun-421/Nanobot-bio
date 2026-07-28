# -*- coding: utf-8 -*-
"""
RBPTraceHook as real nanobot.agent.hook.AgentHook.

Records structured tool calls / results / final verdict for offline self-evolution.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from nanobot.agent.hook import AgentHook, AgentHookContext, AgentRunHookContext


class RBPTraceHook(AgentHook):
    """Write structured traces for self-evolution."""

    def __init__(self, out_path: str | Path, session_key: str = "rbp:default"):
        super().__init__()
        self.out_path = Path(out_path)
        self.out_path.parent.mkdir(parents=True, exist_ok=True)
        self.session_key = session_key
        self._t0 = time.time()
        self._buffer: list[dict[str, Any]] = []
        self._tool_timeline: list[dict[str, Any]] = []
        self._last_donors: list[dict[str, Any]] = []
        self._query_hint: dict[str, Any] = {}

    def _write(self, event: dict[str, Any]) -> None:
        row = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "session_key": self.session_key,
            **event,
        }
        self._buffer.append(row)
        with open(self.out_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")

    def push_event(self, event: dict[str, Any]) -> None:
        """Also used by deterministic RBPAgent path / integrate query_end."""
        self._write(event)

    def note_query(
        self,
        *,
        rna: Optional[str] = None,
        alias: Optional[str] = None,
        uniprot: Optional[str] = None,
        raw: Optional[str] = None,
    ) -> None:
        """Optional hint for query_end when caller knows the user query."""
        if rna:
            self._query_hint["rna"] = rna
        if alias:
            self._query_hint["alias"] = alias
        if uniprot:
            self._query_hint["uniprot"] = uniprot
        if raw:
            self._query_hint["raw"] = raw

    async def before_execute_tools(self, context: AgentHookContext) -> None:
        calls = list(getattr(context, "tool_calls", None) or [])
        serialized = [_serialize_tool_call(c) for c in calls]
        self._write(
            {
                "type": "before_execute_tools",
                "iteration": getattr(context, "iteration", None),
                "tool_calls": serialized,
            }
        )

    async def after_iteration(self, context: AgentHookContext) -> None:
        calls = list(getattr(context, "tool_calls", None) or [])
        results = list(getattr(context, "tool_results", None) or [])
        events = list(getattr(context, "tool_events", None) or [])
        summaries: list[dict[str, Any]] = []
        for i, tc in enumerate(calls):
            name = getattr(tc, "name", None) or "tool"
            res = results[i] if i < len(results) else None
            if isinstance(res, tuple) and res:
                res = res[0]
            ev = events[i] if i < len(events) and isinstance(events[i], dict) else {}
            summary = _summarize_tool_payload(name, res)
            entry = {
                "name": name,
                "ok": ev.get("status") != "error",
                "status": ev.get("status"),
                "summary": summary,
            }
            summaries.append(entry)
            self._tool_timeline.append(entry)
            donors = _extract_donors(name, res)
            if donors:
                self._last_donors = donors
        self._write(
            {
                "type": "after_iteration",
                "iteration": getattr(context, "iteration", None),
                "elapsed_s": round(time.time() - self._t0, 3),
                "tool_results": summaries,
            }
        )

    async def after_run(self, context: AgentRunHookContext) -> None:
        content = getattr(context, "final_content", None)
        self.emit_query_end(content=content, tools_used=list(context.tools_used or []))

    def emit_query_end(
        self,
        *,
        content: Optional[str] = None,
        tools_used: Optional[list[str]] = None,
        verdict: Optional[dict[str, Any]] = None,
    ) -> None:
        """Write a query_end event (also callable from integrate after Nanobot.run)."""
        from app.core.verdict_schema import (
            extract_verdict_from_content,
            normalize_verdict,
        )

        v = verdict
        if v is None and content:
            v = extract_verdict_from_content(content)
        if v is not None:
            try:
                v = normalize_verdict(v)
            except Exception:
                pass
        donors = list(self._last_donors)
        if not donors and isinstance(v, dict):
            donors = list(v.get("supporting_rbps") or [])
        query = dict(self._query_hint)
        try:
            from nanobot.agent.tools.rbp.turn_guards import (
                canonical_request,
                evidence_records,
            )

            canonical = canonical_request()
            provenance = evidence_records()
        except Exception:
            canonical = None
            provenance = []
        self._write(
            {
                "type": "query_end",
                "query": query or None,
                "alias": query.get("alias"),
                "uniprot": query.get("uniprot"),
                "canonical_request": canonical,
                "evidence_records": provenance,
                "donors": donors,
                "verdict": v,
                "tools_used": tools_used or [t.get("name") for t in self._tool_timeline],
                "tool_timeline": self._tool_timeline[-40:],
                "elapsed_s": round(time.time() - self._t0, 3),
            }
        )


def _serialize_tool_call(tc: Any) -> dict[str, Any]:
    name = getattr(tc, "name", None) or getattr(tc, "function", None) or "tool"
    if not isinstance(name, str):
        name = str(name)
    args = getattr(tc, "arguments", None)
    if args is None:
        args = getattr(tc, "args", None)
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except json.JSONDecodeError:
            args = {"_raw": args[:500]}
    if not isinstance(args, dict):
        args = {"_repr": str(args)[:500]}
    slim: dict[str, Any] = {}
    for k, v in list(args.items())[:24]:
        if isinstance(v, str) and len(v) > 200:
            slim[k] = v[:200] + f"…(+{len(v) - 200})"
        else:
            slim[k] = v
    return {"name": name, "arguments": slim}


def _parse_envelope(res: Any) -> Any:
    if res is None:
        return None
    if isinstance(res, (dict, list)):
        return res
    if isinstance(res, str):
        s = res.strip()
        try:
            return json.loads(s)
        except json.JSONDecodeError:
            return {"_text": s[:400]}
    return {"_repr": str(res)[:400]}


def _summarize_tool_payload(name: str, res: Any) -> dict[str, Any]:
    obj = _parse_envelope(res)
    if not isinstance(obj, dict):
        return {"type": type(obj).__name__}
    if obj.get("status") == "error":
        return {"status": "error", "reason": str(obj.get("reason") or "")[:300]}
    value = obj.get("value") if "status" in obj and "value" in obj else obj
    if not isinstance(value, dict):
        return {"status": obj.get("status", "ok"), "keys": list(obj.keys())[:12]}
    out: dict[str, Any] = {"status": obj.get("status", "ok")}
    if "hits" in value:
        hits = value.get("hits") or []
        out["n_hits"] = len(hits) if isinstance(hits, list) else 0
        if isinstance(hits, list) and hits:
            top = hits[0] if isinstance(hits[0], dict) else {}
            out["top_alias"] = top.get("alias")
            out["top_score"] = top.get("score")
    if "predictions" in value:
        preds = value.get("predictions") or []
        out["n_predictions"] = len(preds) if isinstance(preds, list) else 0
    for k in ("alias", "uniprot", "in_panel", "matched", "score", "confident"):
        if k in value:
            out[k] = value[k]
    if "proxies" in value:
        out["n_proxies"] = len(value.get("proxies") or [])
    return out


def _extract_donors(name: str, res: Any) -> list[dict[str, Any]]:
    obj = _parse_envelope(res)
    if not isinstance(obj, dict):
        return []
    value = obj.get("value") if "status" in obj and "value" in obj else obj
    if not isinstance(value, dict):
        return []
    donors: list[dict[str, Any]] = []
    if name in (
        "seq_similarity",
        "struct_similarity",
        "domain_architecture",
        "fuse_similarity_views",
        "lookup_proxy_cache",
        "rna_blastn",
        "esm_similarity",
        "protein_seq_similarity",
    ):
        hits = value.get("hits") or value.get("donors") or value.get("proxies") or []
        if isinstance(hits, list):
            for h in hits[:10]:
                if isinstance(h, dict) and (h.get("alias") or h.get("rbp_id")):
                    donors.append(h)
    return donors
