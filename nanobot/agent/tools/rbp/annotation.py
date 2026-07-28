# -*- coding: utf-8 -*-
"""P1/P2 tools — get_func_annotation + literature_search."""

from __future__ import annotations

import asyncio
from typing import Any

from nanobot.agent.tools.core.base import Tool, tool_parameters

from nanobot.agent.tools.rbp.common import (
    dumps,
    err,
    get_delivery_client,
    literature_cache_get,
    literature_cache_put,
    ok,
    timed_call,
)


def reset_tool_turn_guards() -> None:
    """Clear per-turn anti-loop state (call at start of each chat / agent message)."""
    LiteratureSearchTool._calls_used = 0
    GetFuncAnnotationTool._cache.clear()
    GetFuncAnnotationTool._calls_used = 0
    try:
        from nanobot.agent.tools.rbp.turn_guards import reset_stage_guards

        reset_stage_guards()
    except Exception:
        pass
    try:
        from nanobot.agent.tools.rbp.predict import PredictInteractionTool

        PredictInteractionTool.reset_turn_guards()
    except Exception:
        pass


@tool_parameters(
    {
        "type": "object",
        "properties": {
            "uniprot": {"type": "string"},
            "rbp_id": {"type": "string", "description": "Alias or UniProt; resolved first"},
            "offline": {
                "type": "boolean",
                "default": False,
                "description": "Ignored for caching; one fetch always tries UniProt then GO/Pfam.",
            },
        },
        "required": [],
    }
)
class GetFuncAnnotationTool(Tool):
    """P1 annotation — cached once per UniProt; hard cap on total calls (anti-loop)."""

    _plugin_discoverable = True
    _scopes = {"core", "subagent"}
    _cache: dict[str, str] = {}
    _calls_used: int = 0
    _MAX_CALLS: int = 8  # target + ≤5 proxies + small headroom

    @property
    def name(self) -> str:
        return "get_func_annotation"

    @property
    def description(self) -> str:
        return (
            "Structured function JSON via delivery uniprot_annotation "
            "(falls back to go_pfam_lookup; attaches function_category + pdb_metadata). "
            "Checkpoint 1 input: function / go / rbd_type / category. "
            "Call once per UniProt; do not flip offline or re-query the same accession."
        )

    @property
    def read_only(self) -> bool:
        return True

    async def execute(self, **kwargs: Any) -> str:
        try:
            from nanobot.agent.tools.rbp.turn_guards import blocked_envelope_json

            blocked = blocked_envelope_json(self.name)
            if blocked:
                return blocked
        except Exception:
            pass
        raw = (kwargs.get("uniprot") or kwargs.get("rbp_id") or "").strip()
        if not raw:
            return dumps(err("uniprot or rbp_id required"))

        # Cache key ignores offline / rbp_id spelling variants after normalize.
        cache_key = raw.upper()
        cached = GetFuncAnnotationTool._cache.get(cache_key)
        if cached is not None:
            # Replay prior envelope so the model does not thrash on offline/online flips.
            return cached

        if GetFuncAnnotationTool._calls_used >= GetFuncAnnotationTool._MAX_CALLS:
            return dumps(
                err(
                    "get_func_annotation call budget exhausted this turn; "
                    "proceed to predict_interaction / verdict with available evidence"
                )
            )

        def _run():
            # Always try online UniProt first, then offline GO/Pfam — ignore offline flag.
            client = get_delivery_client(offline=False)
            up = raw
            res = client.call("resolve_rbp", {"query": up})
            if res.get("uniprot"):
                up = res["uniprot"]
            # After resolve, reuse any prior fetch for this accession.
            up_key = str(up).upper()
            hit = GetFuncAnnotationTool._cache.get(up_key)
            if hit is not None:
                return ("cached", up, hit)
            ann = client.call("uniprot_annotation", {"uniprot": up})
            payload: Any
            if not ann.get("error") and not ann.get("skipped"):
                payload = ann.get("annotation") or ann
            else:
                go = client.call("go_pfam_lookup", {"uniprot": up})
                if go.get("error"):
                    raise RuntimeError(go["error"])
                payload = go
            # Stage-1 function path: category + optional PDB metadata
            if isinstance(payload, dict):
                payload = dict(payload)
                try:
                    cat = client.call("function_category", {"uniprot": up})
                    if cat and not cat.get("error") and not cat.get("skipped"):
                        payload["function_category"] = cat.get("value") or cat.get(
                            "category"
                        ) or cat
                except Exception:
                    pass
                try:
                    from nanobot.agent.tools.rbp.common import axis_tool_enabled

                    allowed, _ax = axis_tool_enabled("pdb_metadata")
                    if allowed:
                        pdb_m = client.call("pdb_metadata", {"uniprot": up})
                        if pdb_m and not pdb_m.get("error"):
                            payload["pdb_metadata"] = pdb_m.get("value") or pdb_m
                except Exception:
                    pass
            return ("fresh", up, payload)

        value, ms, error = await asyncio.to_thread(lambda: timed_call(_run))
        GetFuncAnnotationTool._calls_used += 1
        if error:
            out = dumps(err(error, ms))
            GetFuncAnnotationTool._cache[cache_key] = out
            return out

        kind, up, payload = value  # type: ignore[misc]
        if kind == "cached":
            GetFuncAnnotationTool._cache[cache_key] = payload
            return payload
        out = dumps(ok(payload, ms))
        GetFuncAnnotationTool._cache[cache_key] = out
        if isinstance(up, str) and up.upper() != cache_key:
            GetFuncAnnotationTool._cache[up.upper()] = out
        return out


@tool_parameters(
    {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Gene / RBP symbol"},
            "rbp_name": {"type": "string"},
            "query": {
                "type": "string",
                "description": "Optional Europe PMC query override "
                "(e.g. MYC AND CLIP AND 2024:2026).",
            },
            "max_results": {"type": "integer", "default": 5},
        },
        "required": [],
    }
)
class LiteratureSearchTool(Tool):
    """P2 literature — hard-capped to one successful call per turn (anti-loop)."""

    _plugin_discoverable = True
    _scopes = {"core", "subagent"}
    _calls_used: int = 0
    _MAX_CALLS: int = 1

    @property
    def name(self) -> str:
        return "literature_search"

    @property
    def description(self) -> str:
        return (
            "Literature via Europe PMC (delivery). Prefer a precise `query` "
            "(CLIP/eCLIP/RBP + years). Bare name=MYC often returns off-topic hits — "
            "say so if irrelevant. At most ONE call per query. Not web_search."
        )

    @property
    def read_only(self) -> bool:
        return True

    async def execute(self, **kwargs: Any) -> str:
        try:
            from nanobot.agent.tools.rbp.turn_guards import blocked_envelope_json

            blocked = blocked_envelope_json(self.name)
            if blocked:
                return blocked
        except Exception:
            pass
        if LiteratureSearchTool._calls_used >= LiteratureSearchTool._MAX_CALLS:
            return dumps(
                err(
                    "literature_search already used once this session; "
                    "continue without more literature calls"
                )
            )
        name = (kwargs.get("name") or kwargs.get("rbp_name") or "").strip()
        query = (kwargs.get("query") or "").strip()
        if not name and not query:
            return dumps(err("name/rbp_name or query required"))
        # Delivery literature_retrieval requires name/alias even when query= is set.
        if not name and query:
            import re

            m = re.search(r"\b([A-Z][A-Z0-9]{1,14})\b", query)
            name = m.group(1) if m else "RBP"

        payload: dict[str, Any] = {
            "name": name,
            "max_results": int(kwargs.get("max_results") or 5),
        }
        if query:
            payload["query"] = query
        else:
            payload["query"] = (
                f'("{name}") AND (RBP OR "RNA-binding" OR CLIP OR eCLIP '
                f"OR seCLIP OR splicing) AND (FIRST_PDATE:[2020 TO 2026])"
            )

        # A6: cross-session TTL memo cache (default 7d). Hit → return immediately
        # without consuming the one-shot success budget or hitting the network.
        cache_key = f"{name}|{payload['query']}|{payload['max_results']}"
        cached = literature_cache_get(cache_key)
        if cached is not None:
            cached_value = dict(cached)
            cached_value["cache"] = "hit"
            LiteratureSearchTool._calls_used += 1
            return dumps(ok(cached_value, 0.0))

        def _run_once() -> dict[str, Any]:
            client = get_delivery_client(offline=False)
            return client.call("literature_retrieval", payload)

        # Network/TLS flakes: retry up to 2 times (3 attempts total); failures
        # do not consume the one-shot success budget.
        last_err = ""
        out: dict[str, Any] = {}
        ms_total = 0.0
        for attempt in range(3):
            if attempt:
                await asyncio.sleep(0.4 * (2 ** (attempt - 1)))
            out, ms, error = await asyncio.to_thread(lambda: timed_call(_run_once))
            ms_total += float(ms or 0.0)
            if error:
                last_err = str(error)
                if not _is_transient_network_error(last_err):
                    break
                continue
            if out.get("error") or out.get("skipped"):
                last_err = str(out.get("error") or out.get("reason") or "skipped")
                if not _is_transient_network_error(last_err):
                    break
                continue
            papers = out.get("papers") or out.get("results") or []
            if not isinstance(papers, list):
                papers = []
            possibly_off_topic = _papers_possibly_off_topic(papers, name)
            LiteratureSearchTool._calls_used += 1
            value = {
                "papers": papers,
                "query": out.get("query") or payload.get("query"),
                "n_papers": len(papers),
                "possibly_off_topic": possibly_off_topic,
                "retries": attempt,
                "cache": "miss",
            }
            # A6: persist to the cross-session TTL memo cache.
            literature_cache_put(cache_key, value)
            return dumps(ok(value, ms_total))

        try:
            from nanobot.agent.tools.rbp.turn_guards import add_evidence_flag

            add_evidence_flag("literature_unavailable", True)
        except Exception:
            pass
        return dumps(
            err(
                last_err or "literature_retrieval failed",
                ms_total,
            )
        )


def _is_transient_network_error(msg: str) -> bool:
    low = (msg or "").lower()
    needles = (
        "ssl",
        "tls",
        "eof",
        "timeout",
        "timed out",
        "connection",
        "urlopen",
        "temporarily",
        "reset by peer",
        "broken pipe",
    )
    return any(n in low for n in needles)


def _papers_possibly_off_topic(papers: list[Any], rbp_name: str) -> bool:
    """True when no paper title/snippet mentions the RBP symbol (coarse check)."""
    if not papers:
        return True
    needle = (rbp_name or "").strip().upper()
    if len(needle) < 2:
        return False
    for p in papers:
        if not isinstance(p, dict):
            continue
        blob = " ".join(
            str(p.get(k) or "")
            for k in ("title", "abstract_snippet", "abstract", "journal")
        ).upper()
        if needle in blob:
            return False
    return True
