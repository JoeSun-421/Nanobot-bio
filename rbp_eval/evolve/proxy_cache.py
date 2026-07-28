# -*- coding: utf-8 -*-
"""Promote frequent (p* → proxies) mappings to a fast cache.

When a target repeatedly resolves to the same donor set, Stage 1 can be
bypassed on subsequent queries (agent reads this cache before multi-view retrieval).
"""

from __future__ import annotations

import json
import time
from collections import Counter
from pathlib import Path
from typing import Any, Optional

def _default_cache_path() -> Path:
    try:
        from app.core.paths import PROXY_CACHE

        return PROXY_CACHE
    except Exception:
        return Path(__file__).resolve().parents[1] / "artifacts" / "cache" / "proxy_map.json"


# Resolved at import for tests that monkeypatch DEFAULT_CACHE.
DEFAULT_CACHE = _default_cache_path()


def load_proxy_cache(path: Optional[Path] = None) -> dict[str, Any]:
    p = Path(path or DEFAULT_CACHE)
    if not p.is_file():
        return {
            "version": 2,
            "role": "domain_memory",
            "entries": {},
            "stats": {},
            "promotion": {"updater": "promote_from_traces"},
        }
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {
            "version": 2,
            "role": "domain_memory",
            "entries": {},
            "stats": {},
            "promotion": {"updater": "promote_from_traces"},
        }


def save_proxy_cache(data: dict[str, Any], path: Optional[Path] = None) -> Path:
    p = Path(path or DEFAULT_CACHE)
    p.parent.mkdir(parents=True, exist_ok=True)
    data["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return p


def cache_key(uniprot: Optional[str], alias: Optional[str]) -> str:
    if uniprot:
        return f"up:{uniprot}"
    if alias:
        return f"alias:{alias}"
    return ""


def lookup_proxies(
    *,
    uniprot: Optional[str] = None,
    alias: Optional[str] = None,
    path: Optional[Path] = None,
    min_hits: int = 2,
) -> Optional[list[dict[str, Any]]]:
    """Return promoted proxy list if cache entry is strong enough."""
    data = load_proxy_cache(path)
    key = cache_key(uniprot, alias)
    if not key:
        return None
    ent = (data.get("entries") or {}).get(key)
    if not ent:
        return None
    if int(ent.get("hits") or 0) < min_hits:
        return None
    if not ent.get("promoted"):
        return None
    return list(ent.get("proxies") or [])


def record_mapping(
    *,
    uniprot: Optional[str],
    alias: Optional[str],
    proxies: list[dict[str, Any]],
    path: Optional[Path] = None,
    promote_after: int = 3,
) -> dict[str, Any]:
    """Update hit counts; promote when seen ≥ promote_after times with same top donors."""
    data = load_proxy_cache(path)
    key = cache_key(uniprot, alias)
    if not key:
        return data
    entries = data.setdefault("entries", {})
    ent = entries.get(key) or {
        "uniprot": uniprot,
        "alias": alias,
        "hits": 0,
        "proxies": [],
        "promoted": False,
        "history": [],
    }
    # signature = ordered top aliases
    sig = tuple(
        (p.get("alias") or p.get("rbp_id") or "")
        for p in proxies[:5]
        if (p.get("alias") or p.get("rbp_id"))
    )
    hist = ent.setdefault("history", [])
    hist.append({"sig": list(sig), "t": time.time()})
    hist[:] = hist[-20:]  # keep last 20
    ent["hits"] = int(ent.get("hits") or 0) + 1

    # majority signature among recent history
    ctr: Counter[tuple] = Counter(tuple(h["sig"]) for h in hist if h.get("sig"))
    if ctr:
        best_sig, best_n = ctr.most_common(1)[0]
        if best_n >= promote_after and best_sig:
            ent["proxies"] = [{"alias": a} for a in best_sig if a]
            ent["promoted"] = True
            ent["promoted_count"] = best_n
        elif not ent.get("promoted"):
            ent["proxies"] = [{"alias": a} for a in sig if a]

    entries[key] = ent
    data["stats"] = {
        "n_entries": len(entries),
        "n_promoted": sum(1 for e in entries.values() if e.get("promoted")),
    }
    save_proxy_cache(data, path)
    return data


def promote_from_traces(
    traces: list[dict[str, Any]],
    *,
    path: Optional[Path] = None,
    promote_after: int = 3,
) -> dict[str, Any]:
    """Scan query-end traces and update the agent's donor-set domain memory."""
    data = load_proxy_cache(path)
    scanned = 0
    eligible = 0
    for row in traces:
        scanned += 1
        if row.get("type") not in ("query_end", "fallback_end", "agent_result"):
            continue
        q = row.get("query") or row.get("target") or {}
        if isinstance(q, str):
            q = {"alias": q}
        uniprot = q.get("uniprot") or row.get("uniprot")
        alias = q.get("alias") or row.get("alias") or q.get("raw")
        if not alias and isinstance(row.get("query"), str):
            alias = row.get("query")
        donors = row.get("donors") or row.get("supporting_rbps") or []
        if not donors:
            v = row.get("verdict") or {}
            donors = v.get("supporting_rbps") or []
        if not donors:
            continue
        # skip own-head (single self donor with sim≈1.0)
        if (
            len(donors) == 1
            and isinstance(donors[0], dict)
            and (donors[0].get("alias") or "") == (alias or "")
            and float(donors[0].get("similarity_score") or 0) >= 0.999
        ):
            continue
        eligible += 1
        record_mapping(
            uniprot=uniprot,
            alias=alias,
            proxies=donors if isinstance(donors, list) else [],
            path=path,
            promote_after=promote_after,
        )
    data = load_proxy_cache(path)
    data["version"] = max(int(data.get("version") or 1), 2)
    data["role"] = "domain_memory"
    data["promotion"] = {
        "updater": "promote_from_traces",
        "source": "agent_query_end_traces",
        "scanned": scanned,
        "eligible": eligible,
        "promote_after": promote_after,
        "rule": "repeated_identical_ordered_donor_signature",
        "scientific_scores_modified": False,
    }
    save_proxy_cache(data, path)
    return data
