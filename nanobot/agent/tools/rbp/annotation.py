# -*- coding: utf-8 -*-
"""P1/P2 tools — get_func_annotation + literature_search."""

from __future__ import annotations

import asyncio
import re
from functools import lru_cache
from typing import Any, Optional

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

# Metric name for lit-derived catalogue co-mentions fed into fuse_similarity_views.
# Semantics: functional-literature corroboration of hard seq/struct/domain donors
# (weight 0.1) — not a stand-alone similarity score invented from co-mention heat.
LITERATURE_COOCCURRENCE_METRIC = "literature_cooccurrence"
LIT_ONLY_PEER_BUDGET = 3

_RELATEDNESS_MARKERS = (
    "PARALOG",
    "HOMOLOG",
    "ORTHOLOG",
    "PROTEIN FAMILY",
    "RELATED RBP",
    "RELATED PROTEIN",
    "FAMILY MEMBER",
    "SIMILAR TO",
)
_RBP_CONTEXT_MARKERS = (
    "RNA-BINDING",
    "RNA BINDING",
    " RBP",
    "RBP ",
    "SPLICING",
    "ECLIP",
    "CLIP",
)
# Function / family cues that raise peer evidence strength (rule_score only).
_FUNCTION_CUES = (
    "RNA-BINDING",
    "RNA BINDING",
    " RBP",
    "RBP ",
    "SPLICING",
    "ALTERNATIVE SPLICING",
    "ECLIP",
    "CLIP",
    "RRM",
    "KH DOMAIN",
    "ZINC FINGER",
    "PARALOG",
    "HOMOLOG",
    "ORTHOLOG",
    "PROTEIN FAMILY",
    "FAMILY MEMBER",
)


def default_literature_query(rbp_name: str) -> str:
    """Europe PMC default: papers on proteins similar/related to this RBP.

    Anchors on the resolved symbol while biasing toward family / paralog /
    homolog / co-mentioned RBP neighbors — not a narrow CLIP+year filter
    that often returns zero hits.
    """
    name = (rbp_name or "").strip() or "RBP"
    return (
        f'("{name}") AND (paralog* OR paralogue OR homolog* OR ortholog* '
        f'OR "related protein" OR "related RBP" OR "protein family" '
        f'OR "family member" OR "similar to" OR "RNA-binding protein" OR RBP)'
    )


@lru_cache(maxsize=1)
def _catalogue_alias_index() -> tuple[tuple[str, str, str], ...]:
    """Return ``(ALIAS_UPPER, display_alias, uniprot)`` sorted longest-first."""
    try:
        from nanobot.agent.tools.rbp.common import (
            apply_delivery_env_facade,
            load_rbp_registry_facade,
        )

        apply_delivery_env_facade()
        reg = load_rbp_registry_facade()
    except Exception:
        return ()
    rows: list[tuple[str, str, str]] = []
    for up, rec in (reg or {}).items():
        if not isinstance(rec, dict):
            continue
        alias = str(rec.get("alias") or "").strip()
        if not alias or len(alias) < 2:
            continue
        rows.append((alias.upper(), alias, str(up)))
    rows.sort(key=lambda r: (-len(r[0]), r[0]))
    return tuple(rows)


def _token_in_blob(token_upper: str, blob_upper: str) -> bool:
    if not token_upper or not blob_upper:
        return False
    return (
        re.search(
            rf"(?<![A-Z0-9]){re.escape(token_upper)}(?![A-Z0-9])",
            blob_upper,
        )
        is not None
    )


def _paper_has_function_cue(blob_upper: str) -> bool:
    return any(cue in blob_upper for cue in _FUNCTION_CUES)


def extract_literature_peers(
    papers: list[Any],
    query_name: str,
    *,
    max_peers: int = 12,
    catalogue: Optional[tuple[tuple[str, str, str], ...]] = None,
) -> list[dict[str, Any]]:
    """Rule-extract catalogue peers co-mentioned with the query in the same paper.

    A peer counts only when the **same** title/abstract blob contains both the
    query symbol and the peer (token boundaries). ``rule_score`` is evidence
    strength (paper rank × mention locus × optional function-cue boost) — **not**
    sequence/structure similarity and must not be treated as ``s_i``.
    """
    if not papers:
        return []
    index = catalogue if catalogue is not None else _catalogue_alias_index()
    if not index:
        return []
    query_up = (query_name or "").strip().upper()
    if len(query_up) < 2:
        return []
    scores: dict[str, float] = {}
    uniprot_of: dict[str, str] = {}
    display_of: dict[str, str] = {}
    snippets_of: dict[str, list[str]] = {}
    n = len(papers)
    for i, paper in enumerate(papers):
        if not isinstance(paper, dict):
            continue
        title = str(paper.get("title") or "").strip()
        abstract = str(
            paper.get("abstract_snippet") or paper.get("abstract") or ""
        ).strip()
        title_u = title.upper()
        abs_u = abstract.upper()
        blob_u = f"{title_u} {abs_u}".strip()
        if not blob_u:
            continue
        if not _token_in_blob(query_up, blob_u):
            continue
        paper_w = max(0.35, 1.0 - (i / max(n, 1)) * 0.55)
        func_boost = 0.15 if _paper_has_function_cue(blob_u) else 0.0
        for alias_up, alias_disp, uniprot in index:
            if alias_up == query_up:
                continue
            in_title = _token_in_blob(alias_up, title_u)
            in_abs = _token_in_blob(alias_up, abs_u)
            if not in_title and not in_abs:
                continue
            bump = (0.55 if in_title else 0.30) * paper_w + func_boost
            scores[alias_up] = min(1.0, scores.get(alias_up, 0.0) + bump)
            uniprot_of[alias_up] = uniprot
            display_of[alias_up] = alias_disp
            snip = title or abstract[:160]
            if snip:
                bucket = snippets_of.setdefault(alias_up, [])
                if snip not in bucket and len(bucket) < 3:
                    bucket.append(snip)
    ranked = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
    peers: list[dict[str, Any]] = []
    for rank, (alias_up, score) in enumerate(
        ranked[: max(1, int(max_peers))], start=1
    ):
        peers.append(
            {
                "alias": display_of[alias_up],
                "uniprot": uniprot_of.get(alias_up, ""),
                "rule_score": round(float(score), 4),
                "score": round(float(score), 4),
                "metric": LITERATURE_COOCCURRENCE_METRIC,
                "score_kind": "literature_evidence",
                "rank": rank,
                "evidence_snippets": list(snippets_of.get(alias_up) or []),
            }
        )
    return peers


def peers_to_function_fuse_hits(
    lit_peers: list[dict[str, Any]],
    *,
    donor_aliases: Optional[set[str]] = None,
    max_hits: int = 12,
) -> list[dict[str, Any]]:
    """Convert Function peers into fuse hits (independent of Donors_SS).

    Peers also present in seq/struct/domain donors are tagged
    ``literature_corroboration``; others ``function_peer``. Scores remain
    evidence strength (``rule_score``), never seq/struct similarity.
    """
    donors = {
        str(a).strip().upper()
        for a in (donor_aliases or set())
        if str(a).strip()
    }
    ordered = sorted(
        (p for p in (lit_peers or []) if isinstance(p, dict) and p.get("alias")),
        key=lambda p: (
            -float(p.get("rule_score") or p.get("score") or 0.0),
            str(p.get("alias") or ""),
        ),
    )
    hits: list[dict[str, Any]] = []
    for rank, peer in enumerate(ordered[: max(0, int(max_hits))], start=1):
        alias_up = str(peer.get("alias") or "").strip().upper()
        score = float(peer.get("rule_score") or peer.get("score") or 0.0)
        kind = (
            "literature_corroboration" if alias_up in donors else "function_peer"
        )
        hits.append(
            {
                "alias": peer.get("alias"),
                "uniprot": peer.get("uniprot") or "",
                "score": round(score, 4),
                "rule_score": round(score, 4),
                "metric": LITERATURE_COOCCURRENCE_METRIC,
                "score_kind": kind,
                "rank": rank,
                "source": peer.get("source") or "pmc",
                "evidence_snippets": list(peer.get("evidence_snippets") or []),
            }
        )
    return hits


def split_lit_peers_vs_donors(
    lit_peers: list[dict[str, Any]],
    donor_aliases: Optional[set[str]] = None,
    *,
    lit_only_budget: int = LIT_ONLY_PEER_BUDGET,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Annotate overlap with Donors_SS; all peers remain eligible for fuse.

    Returns ``(all_fuse_hits, function_only_peers, all_peers)``.
    ``function_only_peers`` is capped for optional LLM notes (not a fuse gate).
    """
    peers = [dict(p) for p in (lit_peers or []) if isinstance(p, dict) and p.get("alias")]
    hits = peers_to_function_fuse_hits(peers, donor_aliases=donor_aliases)
    function_only = [
        h for h in hits if str(h.get("score_kind") or "") == "function_peer"
    ][: max(0, int(lit_only_budget))]
    return hits, function_only, peers


def merge_lit_peers(
    *peer_lists: list[dict[str, Any]],
    max_peers: int = 12,
) -> list[dict[str, Any]]:
    """Merge peers from PMC / UniProt / … keeping max rule_score per alias."""
    best: dict[str, dict[str, Any]] = {}
    for peers in peer_lists:
        for peer in peers or []:
            if not isinstance(peer, dict) or not peer.get("alias"):
                continue
            key = str(peer["alias"]).strip().upper()
            if not key:
                continue
            score = float(peer.get("rule_score") or peer.get("score") or 0.0)
            prev = best.get(key)
            if prev is None or score > float(
                prev.get("rule_score") or prev.get("score") or 0.0
            ):
                row = dict(peer)
                row["rule_score"] = round(score, 4)
                row["score"] = round(score, 4)
                # Preserve multi-source tag when upgrading.
                if prev and prev.get("source") and prev.get("source") != row.get("source"):
                    row["source"] = f"{prev.get('source')}+{row.get('source')}"
                best[key] = row
            elif prev is not None:
                src = str(peer.get("source") or "")
                if src and src not in str(prev.get("source") or ""):
                    prev["source"] = f"{prev.get('source')}+{src}"
                snips = list(prev.get("evidence_snippets") or [])
                for s in peer.get("evidence_snippets") or []:
                    if s not in snips and len(snips) < 3:
                        snips.append(s)
                prev["evidence_snippets"] = snips
    ranked = sorted(
        best.values(),
        key=lambda p: (
            -float(p.get("rule_score") or 0.0),
            str(p.get("alias") or ""),
        ),
    )
    out = ranked[: max(1, int(max_peers))] if ranked else []
    for i, row in enumerate(out, start=1):
        row["rank"] = i
    return out


def extract_peers_from_annotation_text(
    annotation: dict[str, Any] | None,
    query_name: str,
    *,
    max_peers: int = 8,
    catalogue: Optional[tuple[tuple[str, str, str], ...]] = None,
    source: str = "uniprot",
) -> list[dict[str, Any]]:
    """Rule-extract catalogue peers from UniProt/GO/PDB free-text fields.

    Query is implicit (this is the target's own annotation), so peers need only
    appear in the annotation blob — unlike PMC which requires same-paper
    query+peer co-mention.
    """
    if not isinstance(annotation, dict):
        return []
    parts: list[str] = []
    for key in (
        "function",
        "protein_name",
        "gene_synonyms",
        "function_category",
        "keywords",
    ):
        val = annotation.get(key)
        if isinstance(val, list):
            parts.extend(str(x) for x in val if x)
        elif val:
            parts.append(str(val))
    go = annotation.get("go")
    if isinstance(go, dict):
        for v in go.values():
            if isinstance(v, list):
                parts.extend(str(x) for x in v)
            elif v:
                parts.append(str(v))
    elif isinstance(go, list):
        parts.extend(str(x) for x in go)
    for feat in annotation.get("features") or []:
        if isinstance(feat, dict) and feat.get("desc"):
            parts.append(str(feat["desc"]))
    for pfam in annotation.get("pfam") or []:
        if isinstance(pfam, dict):
            parts.append(str(pfam.get("name") or pfam.get("id") or ""))
        else:
            parts.append(str(pfam))
    pdb = annotation.get("pdb_metadata")
    if isinstance(pdb, dict):
        parts.append(str(pdb))
    blob = " ".join(p for p in parts if p).strip()
    if not blob:
        return []
    index = catalogue if catalogue is not None else _catalogue_alias_index()
    if not index:
        return []
    query_up = (query_name or "").strip().upper()
    blob_u = blob.upper()
    func_boost = 0.15 if _paper_has_function_cue(blob_u) else 0.0
    scores: dict[str, float] = {}
    uniprot_of: dict[str, str] = {}
    display_of: dict[str, str] = {}
    snippets_of: dict[str, list[str]] = {}
    for alias_up, alias_disp, uniprot in index:
        if alias_up == query_up:
            continue
        if not _token_in_blob(alias_up, blob_u):
            continue
        bump = min(1.0, 0.45 + func_boost)
        scores[alias_up] = min(1.0, scores.get(alias_up, 0.0) + bump)
        uniprot_of[alias_up] = uniprot
        display_of[alias_up] = alias_disp
        snip = blob[:160]
        snippets_of.setdefault(alias_up, []).append(snip)
    ranked = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
    peers: list[dict[str, Any]] = []
    for rank, (alias_up, score) in enumerate(
        ranked[: max(1, int(max_peers))], start=1
    ):
        peers.append(
            {
                "alias": display_of[alias_up],
                "uniprot": uniprot_of.get(alias_up, ""),
                "rule_score": round(float(score), 4),
                "score": round(float(score), 4),
                "metric": LITERATURE_COOCCURRENCE_METRIC,
                "score_kind": "literature_evidence",
                "rank": rank,
                "source": source,
                "evidence_snippets": list(snippets_of.get(alias_up) or [])[:3],
            }
        )
    return peers


def _try_load_func_annotation_for_lit(name: str) -> dict[str, Any] | None:
    """Best-effort UniProt annotation for Function-axis merge (uses tool cache)."""
    raw = (name or "").strip()
    if not raw:
        return None
    cache_key = raw.upper()
    cached = GetFuncAnnotationTool._cache.get(cache_key)
    if cached:
        try:
            import json

            env = json.loads(cached)
            if env.get("status") == "ok" and isinstance(env.get("value"), dict):
                return env["value"]
        except Exception:
            pass
    # Soft pull via delivery without consuming literature budget.
    try:
        client = get_delivery_client(offline=False)
        up = raw
        res = client.call("resolve_rbp", {"query": up})
        if res.get("uniprot"):
            up = res["uniprot"]
        ann = client.call("uniprot_annotation", {"uniprot": up})
        if ann.get("error") or ann.get("skipped"):
            return None
        payload = ann.get("annotation") or ann
        return payload if isinstance(payload, dict) else None
    except Exception:
        return None


def build_literature_cooccurrence_hits(
    papers: list[Any],
    query_name: str,
    *,
    max_hits: int = 8,
    catalogue: Optional[tuple[tuple[str, str, str], ...]] = None,
    donor_aliases: Optional[set[str]] = None,
    corroboration_only: bool = False,
) -> list[dict[str, Any]]:
    """Build Function-axis fuse hits from pairwise query+peer evidence.

    Default: all peers enter fuse as ``literature_cooccurrence`` (agent sets
    modality weight). ``corroboration_only=True`` keeps the legacy filter.
    """
    peers = extract_literature_peers(
        papers, query_name, max_peers=max(max_hits, 12), catalogue=catalogue
    )
    donors = donor_aliases
    if donors is None:
        try:
            from nanobot.agent.tools.rbp.turn_guards import retrieve_donor_aliases

            donors = retrieve_donor_aliases()
        except Exception:
            donors = set()
    hits = peers_to_function_fuse_hits(
        peers, donor_aliases=donors, max_hits=max_hits
    )
    if corroboration_only:
        hits = [
            h
            for h in hits
            if str(h.get("score_kind") or "") == "literature_corroboration"
        ]
    return hits


def _attach_literature_fuse_hits(
    value: dict[str, Any],
    papers: list[Any],
    name: str,
    *,
    axis_usable: bool,
    extra_peers: Optional[list[dict[str, Any]]] = None,
) -> dict[str, Any]:
    """Attach Function peers from PMC (+ optional UniProt peers); all may fuse."""
    pmc_peers: list[dict[str, Any]] = []
    if axis_usable and papers:
        pmc_peers = [
            {**p, "source": p.get("source") or "pmc"}
            for p in extract_literature_peers(papers, name)
        ]
    extra = list(extra_peers or [])
    lit_peers = merge_lit_peers(pmc_peers, extra, max_peers=12)
    # Function axis usable if PMC on-topic OR UniProt/extra peers exist.
    function_usable = bool(axis_usable or extra)
    try:
        from nanobot.agent.tools.rbp.turn_guards import retrieve_donor_aliases

        donors = retrieve_donor_aliases()
    except Exception:
        donors = set()
    hits: list[dict[str, Any]] = []
    function_only: list[dict[str, Any]] = []
    if function_usable and lit_peers:
        hits, function_only, lit_peers = split_lit_peers_vs_donors(
            lit_peers, donors, lit_only_budget=LIT_ONLY_PEER_BUDGET
        )
    value["lit_peers"] = lit_peers
    value["corroborated"] = [
        h for h in hits if str(h.get("score_kind") or "") == "literature_corroboration"
    ]
    value["lit_only_peers"] = function_only
    value["hits"] = hits
    value["hits_lit"] = hits
    value["n_lit_hits"] = len(hits)
    value["n_lit_peers"] = len(lit_peers)
    value["n_lit_only"] = len(function_only)
    value["function_axis_usable"] = function_usable
    value["lit_only_action"] = (
        "Function peers already enter fuse as literature_cooccurrence; set "
        "fusion_weights on fuse_similarity_views to raise/lower that axis. "
        "Optional: record_lit_peer_decisions with weight_note rationale."
        if hits
        else ""
    )
    try:
        from nanobot.agent.tools.rbp.turn_guards import (
            set_literature_fuse_hits,
            set_literature_peers,
        )

        set_literature_peers(lit_peers, function_only, axis_usable=function_usable)
        set_literature_fuse_hits(hits, axis_usable=function_usable)
    except Exception:
        pass
    return value


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


def prepare_tool_turn_guards(user_message: str = "") -> None:
    """Reset per-turn guards and seed sticky LOO / force_transfer from the user turn."""
    reset_tool_turn_guards()
    text = (user_message or "").strip()
    if not text:
        return
    try:
        from nanobot.agent.tools.rbp.turn_guards import (
            seed_loo_force_transfer_from_user_message,
        )

        seed_loo_force_transfer_from_user_message(text)
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
                "description": (
                    "Optional Europe PMC query you craft for similar/related "
                    "RBPs (family, paralogs, homologs, shared RRM/function). "
                    "Omit to use server default_literature_query. Do not invent "
                    "fuse/s_i scores from papers."
                ),
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
            "Function-view retrieve (proposal Table 1): Europe PMC + merges "
            "UniProt/GO/PDB annotation when available. Craft `query` for "
            "similar RBPs or omit for default_literature_query. Returns papers, "
            "`sources`, and `lit_peers` / `hits_lit` "
            f"(`{LITERATURE_COOCCURRENCE_METRIC}`) that enter fuse as a "
            "first-class Function axis — set `fusion_weights` on "
            "fuse_similarity_views to raise/lower this axis (never invent "
            "s_i or p_hat). Parallel with seq/struct. ≤1 PMC call/turn. "
            "Not web_search."
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
            payload["query"] = default_literature_query(name)

        # A6: cross-session TTL memo cache (default 7d). Hit → return immediately
        # without consuming the one-shot success budget or hitting the network.
        cache_key = f"{name}|{payload['query']}|{payload['max_results']}"
        cached = literature_cache_get(cache_key)
        if cached is not None:
            cached_value = dict(cached)
            cached_value["cache"] = "hit"
            papers = cached_value.get("papers") or []
            if not isinstance(papers, list):
                papers = []
            possibly_off_topic = bool(
                cached_value.get("possibly_off_topic")
            ) or _papers_possibly_off_topic(papers, name)
            cached_value["possibly_off_topic"] = possibly_off_topic
            axis_usable = not possibly_off_topic
            cached_value["axis_usable"] = axis_usable
            _finalize_literature_value(cached_value, papers, name, axis_usable)
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
            axis_usable = not possibly_off_topic
            LiteratureSearchTool._calls_used += 1
            value = {
                "papers": papers,
                "query": out.get("query") or payload.get("query"),
                "n_papers": len(papers),
                "possibly_off_topic": possibly_off_topic,
                "axis_usable": axis_usable,
                "retries": attempt,
                "cache": "miss",
            }
            _finalize_literature_value(value, papers, name, axis_usable)
            # A6: persist to the cross-session TTL memo cache.
            literature_cache_put(cache_key, value)
            return dumps(ok(value, ms_total))

        try:
            from nanobot.agent.tools.rbp.turn_guards import (
                add_evidence_flag,
                set_literature_fuse_hits,
            )

            add_evidence_flag("literature_unavailable", True)
            set_literature_fuse_hits([], axis_usable=False)
        except Exception:
            pass
        return dumps(
            err(
                last_err or "literature_retrieval failed",
                ms_total,
            )
        )


@tool_parameters(
    {
        "type": "object",
        "properties": {
            "decisions": {
                "type": "array",
                "description": (
                    "Optional Function-axis notes. Items: "
                    "{alias?, action: weight_note|keep|drop|recompare_*, "
                    "rationale}. Peers already enter fuse; use this for "
                    "audit/caveats, not as a gate."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "alias": {"type": "string"},
                        "metric": {"type": "string"},
                        "action": {
                            "type": "string",
                            "enum": [
                                "weight_note",
                                "keep",
                                "drop",
                                "recompare_seq",
                                "recompare_struct",
                            ],
                        },
                        "rationale": {"type": "string"},
                    },
                    "required": ["rationale"],
                },
            },
        },
        "required": ["decisions"],
    }
)
class RecordLitPeerDecisionsTool(Tool):
    """Optional Function-axis rationale / weight notes (no scores invented)."""

    _plugin_discoverable = True
    _scopes = {"core", "subagent"}

    @property
    def name(self) -> str:
        return "record_lit_peer_decisions"

    @property
    def description(self) -> str:
        return (
            "Optional: record why you raised/lowered Function-axis "
            "fusion_weights or notes on lit_peers. Does not invent similarity "
            "scores and is not required for peers to enter fuse. Prefer "
            "fuse_similarity_views(fusion_weights={...}) for actual weighting."
        )

    @property
    def read_only(self) -> bool:
        return True

    async def execute(self, **kwargs: Any) -> str:
        decisions = kwargs.get("decisions")
        if not isinstance(decisions, list) or not decisions:
            return dumps(err("decisions list required"))
        cleaned: list[dict[str, Any]] = []
        allowed = {
            "recompare_seq",
            "recompare_struct",
            "drop",
            "weight_note",
            "keep",
        }
        for item in decisions[: max(LIT_ONLY_PEER_BUDGET, 8)]:
            if not isinstance(item, dict):
                continue
            alias = str(item.get("alias") or item.get("metric") or "").strip()
            action = str(item.get("action") or "weight_note").strip().lower()
            if action not in allowed:
                continue
            cleaned.append(
                {
                    "alias": alias or "*",
                    "action": action,
                    "rationale": str(item.get("rationale") or "").strip()[:400],
                }
            )
        if not cleaned:
            return dumps(err("no valid decisions (need rationale)"))
        try:
            from nanobot.agent.tools.rbp.turn_guards import (
                record_lit_peer_decisions,
            )

            stored = record_lit_peer_decisions(cleaned)
        except Exception as exc:
            return dumps(err(f"failed to record decisions: {exc}"))
        return dumps(
            ok(
                {
                    "recorded": stored,
                    "n": len(stored),
                    "next": (
                        "Call fuse_similarity_views with fusion_weights "
                        "reflecting Function/seq/struct evidence strength."
                    ),
                }
            )
        )


def _finalize_literature_value(
    value: dict[str, Any],
    papers: list[Any],
    name: str,
    pmc_axis_usable: bool,
) -> dict[str, Any]:
    """Merge UniProt/GO/PDB into Function envelope and attach fuse hits."""
    uniprot_ann = _try_load_func_annotation_for_lit(name)
    extra_peers: list[dict[str, Any]] = []
    sources: dict[str, Any] = {
        "europe_pmc": {"papers": papers, "n": len(papers), "usable": bool(pmc_axis_usable)}
    }
    if isinstance(uniprot_ann, dict):
        sources["uniprot"] = {
            "uniprot": uniprot_ann.get("uniprot"),
            "alias": uniprot_ann.get("alias"),
            "function": uniprot_ann.get("function"),
            "keywords": uniprot_ann.get("keywords"),
            "rbd_type": uniprot_ann.get("rbd_type"),
            "function_category": uniprot_ann.get("function_category"),
            "source": uniprot_ann.get("source"),
        }
        if uniprot_ann.get("go") is not None:
            sources["go_pfam"] = uniprot_ann.get("go")
        if uniprot_ann.get("pdb_metadata") is not None:
            sources["pdb"] = uniprot_ann.get("pdb_metadata")
        extra_peers = extract_peers_from_annotation_text(uniprot_ann, name)
    value["sources"] = sources
    _surface_literature_axis_flags(
        possibly_off_topic=not pmc_axis_usable,
        function_still_usable=bool(extra_peers) or bool(pmc_axis_usable),
    )
    return _attach_literature_fuse_hits(
        value,
        papers if pmc_axis_usable else [],
        name,
        axis_usable=pmc_axis_usable,
        extra_peers=extra_peers,
    )


def _surface_literature_axis_flags(
    possibly_off_topic: bool,
    *,
    function_still_usable: bool = False,
) -> None:
    """Mark PMC off-topic; full Function axis unusable only if no UniProt peers."""
    if not possibly_off_topic:
        return
    try:
        from nanobot.agent.tools.rbp.turn_guards import add_evidence_flag

        add_evidence_flag("literature_off_topic", True)
        add_evidence_flag("literature_pmc_off_topic", True)
        if not function_still_usable:
            add_evidence_flag("literature_axis_unusable", True)
    except Exception:
        pass


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


def _blob_has_related_rbp_context(blob_upper: str) -> bool:
    """True when snippet discusses relatedness in an RBP/RNA-binding context."""
    if not blob_upper:
        return False
    has_rel = any(m in blob_upper for m in _RELATEDNESS_MARKERS)
    has_rbp = any(m in blob_upper for m in _RBP_CONTEXT_MARKERS)
    return has_rel and has_rbp


def _papers_possibly_off_topic(papers: list[Any], rbp_name: str) -> bool:
    """True when papers look off-topic for the query RBP / related-RBP axis.

    On-topic if any paper mentions the RBP symbol, or (for relatedness-oriented
    defaults) discusses paralog/homolog/family language together with
    RNA-binding context — so family-neighbor papers are not falsely flagged.
    """
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
        if _blob_has_related_rbp_context(blob):
            return False
    return True
