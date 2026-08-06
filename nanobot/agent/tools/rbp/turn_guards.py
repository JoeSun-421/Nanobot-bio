# -*- coding: utf-8 -*-
"""Per-turn Stage 0–3 hard guards (Proposal §9; SKILL alone is not enough).

The serial Stage-2/3 contract (fuse → abstain → predict) and the Stage-0 STOP
tool set are declared in :mod:`stage_contract` (single source of truth). This
module holds the per-turn *state* (flags + evidence) and the runtime checks
that consult the contract. A future runner-level scheduler can consume
``stage_contract.REQUIRES`` directly; until then these guards are the
scheduling-layer prevention that keeps the LLM from calling integrate tools
out of order (B2: dependency declaration, not just post-hoc blocking).

CLI examples:
  nanobot-bio agent --example pos
  nanobot-bio agent --force-transfer --query PTBP1 --rna-file path/to/rna.txt
  nanobot-bio chat
"""

from __future__ import annotations

import re
from typing import Any, Optional

from nanobot.agent.tools.rbp.stage_contract import (
    DOMAIN_RETRIEVE,
    OWN_HEAD_STOP_BLOCKED,
    REQUIRES,
    STAGE_RETRIEVE,
    STRUCTURE_RETRIEVE,
    describe_unmet_prerequisite,
)

# After successful own-head predict, retrieve / transfer tools must refuse.
_OWN_HEAD_STOP: bool = False
# Unseen path: fuse → commit_proxy_candidates → confidence_abstain → predict (§4).
_FUSE_DONE: bool = False
_COMMIT_DONE: bool = False
_ABSTAIN_DONE: bool = False

# Accumulated evidence flags for Stage-3 normalize_verdict (tool-sourced).
_EVIDENCE_FLAGS: dict[str, Any] = {}
_EVIDENCE_RECORDS: list[dict[str, Any]] = []
# Selected deterministic proxies from commit_proxy_candidates (authoritative s_i).
_COMMITTED_PROXIES: list[dict[str, Any]] = []
# Deterministic output of fuse_similarity_views; commit may select from it but
# may not replace its numeric similarity values.
_FUSED_PROXIES: list[dict[str, Any]] = []
# Target RBP alias from resolve_rbp this turn (for transfer_prior_lookup).
_QUERY_TARGET: Optional[str] = None
# Canonical identity/cohort/modality request established by resolve_rbp.
_CANONICAL_REQUEST: Optional[dict[str, Any]] = None
# Numeric verdict authority for this turn. Only deterministic tools may set this;
# the LLM can explain it but cannot supply or override it.
_AUTHORITATIVE_SCORE: Optional[dict[str, Any]] = None
# Explicit force_transfer=true (tool arg / commit / user LOO intent) disables
# near-match own-head Fast Path for this turn and overrides Stage 0 STOP.
_FORCE_TRANSFER_ACTIVE: bool = False
# Soft Function-axis hits for automatic fuse_similarity_views injection.
_LIT_FUSE_HITS: list[dict[str, Any]] = []
_LIT_AXIS_USABLE: bool = False
# Full pairwise Function peers (+ optional overlap annotation vs Donors_SS).
_LIT_PEERS: list[dict[str, Any]] = []
_LIT_ONLY_PEERS: list[dict[str, Any]] = []
_LIT_PEER_DECISIONS: list[dict[str, Any]] = []
# Aliases seen in seq/struct/domain retrieve hit lists this turn (Donors_SS).
_RETRIEVE_DONOR_ALIASES: set[str] = set()
# Per-turn agent fusion_weights override (after clamp).
_TURN_FUSION_WEIGHTS: dict[str, float] = {}
_TURN_FUSION_WEIGHTS_CLAMPED: dict[str, dict[str, float]] = {}
# Proxy-cache hit: skip Stage-1 multi-view retrieve (proposal §7.5).
_STAGE1_BYPASSED: bool = False
_CACHE_PROXIES: list[dict[str, Any]] = []

# Conservative user-message LOO cues (secondary to tool args / commit state).
_LOO_USER_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bforce[_\s-]?transfer\b", re.I),
    re.compile(r"\bleave[\s-]?one[\s-]?out\b", re.I),
    re.compile(r"\bLOO\b"),
    re.compile(r"留一法"),
    re.compile(r"\btreat[\s-]?as[\s-]?unseen\b", re.I),
    re.compile(r"\btreat[\s-]?.*\s+as[\s-]?(?:unseen|unknown)\b", re.I),
    re.compile(r"\bno[\s-]?own[\s-]?head\b", re.I),
    re.compile(r"\bdo[\s-]?not[\s-]?own[\s-]?head\b", re.I),
    re.compile(r"\bout[\s-]?of[\s-]?panel[\s-]?force[\s-]?transfer\b", re.I),
)

# Tools blocked after own-head success (Stage 0 STOP) — declared in stage_contract.
RETRIEVE_AFTER_OWN_HEAD: frozenset[str] = OWN_HEAD_STOP_BLOCKED


def reset_stage_guards() -> None:
    global _OWN_HEAD_STOP, _FUSE_DONE, _COMMIT_DONE, _ABSTAIN_DONE
    global _EVIDENCE_FLAGS, _EVIDENCE_RECORDS, _COMMITTED_PROXIES, _FUSED_PROXIES
    global _QUERY_TARGET, _CANONICAL_REQUEST, _AUTHORITATIVE_SCORE
    global _FORCE_TRANSFER_ACTIVE, _LIT_FUSE_HITS, _LIT_AXIS_USABLE
    global _LIT_PEERS, _LIT_ONLY_PEERS, _LIT_PEER_DECISIONS
    global _TURN_FUSION_WEIGHTS, _TURN_FUSION_WEIGHTS_CLAMPED
    global _STAGE1_BYPASSED, _CACHE_PROXIES
    _OWN_HEAD_STOP = False
    _FUSE_DONE = False
    _COMMIT_DONE = False
    _ABSTAIN_DONE = False
    _EVIDENCE_FLAGS = {}
    _EVIDENCE_RECORDS = []
    _COMMITTED_PROXIES = []
    _FUSED_PROXIES = []
    _QUERY_TARGET = None
    _CANONICAL_REQUEST = None
    _AUTHORITATIVE_SCORE = None
    _FORCE_TRANSFER_ACTIVE = False
    _LIT_FUSE_HITS = []
    _LIT_AXIS_USABLE = False
    _LIT_PEERS = []
    _LIT_ONLY_PEERS = []
    _LIT_PEER_DECISIONS = []
    _TURN_FUSION_WEIGHTS = {}
    _TURN_FUSION_WEIGHTS_CLAMPED = {}
    _RETRIEVE_DONOR_ALIASES.clear()
    _STAGE1_BYPASSED = False
    _CACHE_PROXIES = []
    _RETRIEVE_DONE.clear()


def mark_stage1_bypassed(proxies: list[dict[str, Any]] | None = None) -> None:
    """Cache hit: skip Stage-1 multi-view retrieve; allow fuse/commit from proxies."""
    global _STAGE1_BYPASSED, _CACHE_PROXIES
    _STAGE1_BYPASSED = True
    _CACHE_PROXIES = [dict(p) for p in (proxies or []) if isinstance(p, dict)]
    # Satisfy fuse multi-view sentinels without inventing retrieve tool runs.
    add_evidence_flag("stage1_bypassed", True)
    add_evidence_flag("structure_axis_skipped", True)
    add_evidence_flag("domain_axis_skipped", True)
    # Synthetic retrieve marker so __any_retrieve__ is satisfied.
    _RETRIEVE_DONE.add("lookup_proxy_cache")
    if _CACHE_PROXIES:
        set_fused_proxies(_CACHE_PROXIES)
        register_retrieve_donors(
            str(p.get("alias") or p.get("rbp_id") or "")
            for p in _CACHE_PROXIES
        )


def stage1_bypassed() -> bool:
    return bool(_STAGE1_BYPASSED)


def cache_proxies() -> list[dict[str, Any]]:
    return [dict(p) for p in _CACHE_PROXIES]


def set_literature_fuse_hits(
    hits: list[dict[str, Any]] | None,
    *,
    axis_usable: bool = True,
) -> None:
    """Store Function-axis RbpHit list for automatic fuse injection."""
    global _LIT_FUSE_HITS, _LIT_AXIS_USABLE
    _LIT_AXIS_USABLE = bool(axis_usable)
    if not axis_usable or not hits:
        _LIT_FUSE_HITS = []
        return
    _LIT_FUSE_HITS = [dict(h) for h in hits if isinstance(h, dict) and h.get("alias")]


def literature_fuse_hits() -> list[dict[str, Any]]:
    """Return Function-axis lit/UniProt hits (empty if axis unusable)."""
    if not _LIT_AXIS_USABLE:
        return []
    return [dict(h) for h in _LIT_FUSE_HITS]


def set_turn_fusion_weights(
    weights: dict[str, float] | None,
    *,
    clamped: dict[str, dict[str, float]] | None = None,
) -> None:
    """Store per-turn agent fusion_weights (already clamped) for audit/trace."""
    global _TURN_FUSION_WEIGHTS, _TURN_FUSION_WEIGHTS_CLAMPED
    _TURN_FUSION_WEIGHTS = {
        str(k): float(v) for k, v in (weights or {}).items()
    }
    _TURN_FUSION_WEIGHTS_CLAMPED = {
        str(k): dict(v)
        for k, v in (clamped or {}).items()
        if isinstance(v, dict)
    }
    if _TURN_FUSION_WEIGHTS:
        add_evidence_flag("fusion_weights_override", True)
    if _TURN_FUSION_WEIGHTS_CLAMPED:
        add_evidence_flag("fusion_weights_clamped", True)
        add_evidence_flag(
            "fusion_weights_clamped_keys",
            sorted(_TURN_FUSION_WEIGHTS_CLAMPED.keys()),
        )


def turn_fusion_weights() -> dict[str, float]:
    return dict(_TURN_FUSION_WEIGHTS)


def turn_fusion_weights_clamped() -> dict[str, dict[str, float]]:
    return {k: dict(v) for k, v in _TURN_FUSION_WEIGHTS_CLAMPED.items()}


def set_literature_peers(
    lit_peers: list[dict[str, Any]] | None,
    lit_only: list[dict[str, Any]] | None = None,
    *,
    axis_usable: bool = True,
) -> None:
    """Store pairwise lit peers and budgeted lit-only orphans for this turn."""
    global _LIT_PEERS, _LIT_ONLY_PEERS, _LIT_AXIS_USABLE
    if axis_usable:
        _LIT_AXIS_USABLE = True
    _LIT_PEERS = [
        dict(p) for p in (lit_peers or []) if isinstance(p, dict) and p.get("alias")
    ]
    _LIT_ONLY_PEERS = [
        dict(p) for p in (lit_only or []) if isinstance(p, dict) and p.get("alias")
    ]
    if _LIT_ONLY_PEERS:
        add_evidence_flag("literature_lit_only_peers", True)
        add_evidence_flag(
            "literature_lit_only_aliases",
            [str(p.get("alias")) for p in _LIT_ONLY_PEERS],
        )


def literature_peers() -> list[dict[str, Any]]:
    return [dict(p) for p in _LIT_PEERS]


def lit_only_peers() -> list[dict[str, Any]]:
    return [dict(p) for p in _LIT_ONLY_PEERS]


def register_retrieve_donors(aliases: Any) -> None:
    """Accumulate Donors_SS aliases from seq/struct/domain retrieve hits."""
    if aliases is None:
        return
    if isinstance(aliases, (str, bytes)):
        aliases = [aliases]
    for raw in aliases:
        alias = str(raw or "").strip()
        if alias:
            _RETRIEVE_DONOR_ALIASES.add(alias.upper())


def retrieve_donor_aliases() -> set[str]:
    """Uppercased aliases seen in this turn's hard retrieve hit lists."""
    return set(_RETRIEVE_DONOR_ALIASES)


def register_retrieve_donors_from_tool_result(
    tool_name: str, result: Any
) -> None:
    """Parse an ok tool envelope and register hit aliases into Donors_SS."""
    if tool_name not in STAGE_RETRIEVE:
        return
    # Literature itself is not a hard donor source.
    if tool_name in {"literature_search", "literature_retrieval", "get_func_annotation"}:
        return
    payload = result
    if isinstance(result, str):
        text = result.strip()
        if not text.startswith("{"):
            return
        try:
            import json

            payload = json.loads(text)
        except Exception:
            return
    if not isinstance(payload, dict):
        return
    value = payload.get("value") if payload.get("status") == "ok" else payload
    if not isinstance(value, dict):
        return
    aliases: list[str] = []
    for key in (
        "hits",
        "hits_emb",
        "hits_seq",
        "hits_struct",
        "hits_domain",
    ):
        rows = value.get(key)
        if not isinstance(rows, list):
            continue
        for hit in rows:
            if isinstance(hit, dict) and hit.get("alias"):
                aliases.append(str(hit["alias"]))
            elif isinstance(hit, dict) and hit.get("rbp_id"):
                aliases.append(str(hit["rbp_id"]))
    # Domain architecture may nest neighbours under similar keys.
    for key in ("neighbours", "neighbors", "domain_hits"):
        rows = value.get(key)
        if isinstance(rows, list):
            for hit in rows:
                if isinstance(hit, dict) and hit.get("alias"):
                    aliases.append(str(hit["alias"]))
    if aliases:
        register_retrieve_donors(aliases)


def record_lit_peer_decisions(
    decisions: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Store optional Function-axis rationale (weight notes / narrative).

    Recompare/drop actions remain accepted for backward compatibility but are
    **not** required for peers to enter fuse (Function is a first-class view).
    """
    global _LIT_PEER_DECISIONS
    cleaned: list[dict[str, Any]] = []
    allowed = {
        "recompare_seq",
        "recompare_struct",
        "drop",
        "weight_note",
        "keep",
    }
    for item in decisions or []:
        if not isinstance(item, dict):
            continue
        alias = str(item.get("alias") or item.get("metric") or "").strip()
        action = str(item.get("action") or "weight_note").strip().lower()
        if action not in allowed:
            continue
        if not alias and action != "weight_note":
            continue
        cleaned.append(
            {
                "alias": alias or "*",
                "action": action,
                "rationale": str(item.get("rationale") or "").strip()[:400],
            }
        )
    _LIT_PEER_DECISIONS = cleaned
    if cleaned:
        add_evidence_flag("literature_peer_decisions", True)
        add_evidence_flag(
            "literature_peer_decision_detail",
            [
                f"{d['alias']}:{d['action']}"
                + (f" ({d['rationale']})" if d.get("rationale") else "")
                for d in cleaned
            ],
        )
        record_evidence(
            {
                "kind": "lit_peer_decisions",
                "decisions": cleaned,
            }
        )
    return list(cleaned)


def lit_peer_decisions() -> list[dict[str, Any]]:
    return [dict(d) for d in _LIT_PEER_DECISIONS]


def corroborate_literature_hits_for_aliases(
    donor_aliases: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Refresh Function-axis fuse hits from stored lit_peers (all peers eligible).

    Overlap with Donors_SS is annotated as ``literature_corroboration``; peers
    only on the Function view are ``function_peer``. Agent fusion_weights
    control how strongly they affect ``s_i``.
    """
    if not _LIT_AXIS_USABLE or not _LIT_PEERS:
        return literature_fuse_hits()
    donors = set(retrieve_donor_aliases())
    if donor_aliases:
        donors |= {str(a).strip().upper() for a in donor_aliases if str(a).strip()}
    try:
        from nanobot.agent.tools.rbp.annotation import peers_to_function_fuse_hits

        hits = peers_to_function_fuse_hits(_LIT_PEERS, donor_aliases=donors)
    except Exception:
        return literature_fuse_hits()
    global _LIT_ONLY_PEERS
    _LIT_ONLY_PEERS = [
        dict(h)
        for h in hits
        if str(h.get("score_kind") or "") == "function_peer"
    ]
    set_literature_fuse_hits(hits, axis_usable=True)
    return literature_fuse_hits()


def mark_own_head_success() -> None:
    global _OWN_HEAD_STOP
    _OWN_HEAD_STOP = True


def mark_fuse_done() -> None:
    global _FUSE_DONE
    _FUSE_DONE = True


def mark_commit_done() -> None:
    global _COMMIT_DONE
    _COMMIT_DONE = True


def set_committed_proxies(proxies: list[dict[str, Any]]) -> None:
    """Store a selected subset of deterministic fused proxies."""
    global _COMMITTED_PROXIES
    _COMMITTED_PROXIES = [dict(p) for p in proxies if isinstance(p, dict)]
    mark_commit_done()
    add_evidence_flag("deterministic_fused_proxies", True)
    add_evidence_flag("n_committed_proxies", len(_COMMITTED_PROXIES))


def committed_proxies() -> list[dict[str, Any]]:
    return [dict(p) for p in _COMMITTED_PROXIES]


def _normalize_fused_proxy_row(proxy: dict[str, Any]) -> dict[str, Any]:
    """Normalize fuse_rbp_hits donor rows for Checkpoint 1 commit.

    ``score`` is the deterministic ranking score, while ``vote_similarity`` is
    the raw scientific similarity used by delivery voting. Keep both fields
    separate so rank normalization cannot leak into p_hat.
    """
    row = dict(proxy)
    if row.get("fused_score") is None and row.get("score") is not None:
        try:
            row["fused_score"] = float(row["score"])
        except (TypeError, ValueError):
            pass
    scientific = row.get("vote_similarity")
    raw_modalities = row.get("sim_by_modality")
    if (
        scientific is None
        and isinstance(raw_modalities, dict)
        and raw_modalities.get("esmc_cosine") is not None
    ):
        scientific = raw_modalities["esmc_cosine"]
    if scientific is None:
        # Backward compatibility for stored/legacy fused rows.
        scientific = row.get("similarity_score")
    if scientific is None:
        scientific = row.get("score")
    if scientific is not None:
        try:
            row["similarity_score"] = float(scientific)
            row["vote_similarity"] = float(scientific)
        except (TypeError, ValueError):
            pass
    if not row.get("rbp_id"):
        rid = row.get("alias") or row.get("uniprot") or row.get("donor")
        if rid:
            row["rbp_id"] = str(rid)
    return row


def set_fused_proxies(proxies: list[dict[str, Any]]) -> None:
    global _FUSED_PROXIES
    _FUSED_PROXIES = [
        _normalize_fused_proxy_row(p) for p in proxies if isinstance(p, dict)
    ]
    mark_fuse_done()
    add_evidence_flag("n_fused_proxies", len(_FUSED_PROXIES))


def fused_proxies() -> list[dict[str, Any]]:
    return [dict(p) for p in _FUSED_PROXIES]


def set_query_target(alias: str) -> None:
    """Store resolved target alias for integrate priors (transfer LOO lookup)."""
    global _QUERY_TARGET
    if alias:
        _QUERY_TARGET = str(alias)


def query_target() -> Optional[str]:
    return _QUERY_TARGET


def set_canonical_request(request: dict[str, Any]) -> None:
    """Persist the validated request once for downstream provenance."""
    global _CANONICAL_REQUEST
    _CANONICAL_REQUEST = dict(request)
    alias = _CANONICAL_REQUEST.get("alias")
    uniprot = _CANONICAL_REQUEST.get("uniprot")
    if alias or uniprot:
        set_query_target(str(alias or uniprot))


def canonical_request() -> Optional[dict[str, Any]]:
    return dict(_CANONICAL_REQUEST) if _CANONICAL_REQUEST is not None else None


_SCORE_DISCLAIMERS = {
    "near_match_proxy_head": (
        "near-match proxy head probability; not own-head; "
        "not calibrated binding probability"
    ),
    "weighted_consensus": (
        "multi-donor weighted consensus; not a calibrated binding probability"
    ),
}


def set_authoritative_score(
    p_hat: Optional[float],
    *,
    source: str,
    mode: str,
    provenance: Optional[dict[str, Any]] = None,
    score_kind: Optional[str] = None,
) -> None:
    """Store the only numeric score allowed into the product verdict.

    ``p_hat=None`` is still authoritative: a failed predictor/vote must not be
    replaced by an LLM guess or an unrelated similarity score.
    """
    global _AUTHORITATIVE_SCORE
    value = None if p_hat is None else float(p_hat)
    kind = str(score_kind or "").strip()
    if not kind:
        if mode == "own_head":
            kind = "own_head"
        elif source == "near_match_donor_head" or mode == "near_match_transfer":
            # Near-match without a usable donor head falls back to vote but keeps
            # transfer mode; score_kind then reflects the actual numeric source.
            kind = (
                "near_match_proxy_head"
                if source == "near_match_donor_head"
                else "weighted_consensus"
            )
        else:
            kind = "weighted_consensus"
    disclaimer = _SCORE_DISCLAIMERS.get(kind)
    prov = dict(provenance or {})
    prov.setdefault("score_kind", kind)
    if disclaimer:
        prov.setdefault("score_disclaimer", disclaimer)
    _AUTHORITATIVE_SCORE = {
        "p_hat": value,
        "source": str(source),
        "mode": str(mode),
        "score_kind": kind,
        "score_disclaimer": disclaimer,
        "provenance": prov,
    }


def authoritative_score() -> Optional[dict[str, Any]]:
    return dict(_AUTHORITATIVE_SCORE) if _AUTHORITATIVE_SCORE is not None else None


def mark_abstain_done() -> None:
    global _ABSTAIN_DONE
    _ABSTAIN_DONE = True
    add_evidence_flag("abstain_called", True)


def fuse_done() -> bool:
    return bool(_FUSE_DONE)


def commit_done() -> bool:
    return bool(_COMMIT_DONE)


def abstain_done() -> bool:
    return bool(_ABSTAIN_DONE)


def own_head_stop_active() -> bool:
    return bool(_OWN_HEAD_STOP)


def add_evidence_flag(key: str, value: Any = True) -> None:
    _EVIDENCE_FLAGS[str(key)] = value


def clear_evidence_flag(key: str) -> None:
    _EVIDENCE_FLAGS.pop(str(key), None)


def clear_structure_axis_unavailable() -> None:
    """Clear sticky AFDB-miss flags after a usable structure is recovered.

    ``structure_fetch`` / AFDB miss may set ``structure_axis_unavailable`` (and
    sometimes ``structure_unavailable``). A later successful AF3
    ``predict_structure`` or ``struct_similarity`` must clear those so
    ``normalize_verdict`` does not force low confidence. Intentional trust
    flags (``structure_mostly_disordered``, ``structure_low_plddt``, …) are
    left untouched.
    """
    clear_evidence_flag("structure_axis_unavailable")
    clear_evidence_flag("structure_unavailable")


def evidence_flags() -> dict[str, Any]:
    return dict(_EVIDENCE_FLAGS)


def set_force_transfer_active(active: bool = True, *, source: str = "tool_arg") -> None:
    """Record explicit LOO / force_transfer for this turn.

    Disables near-match own-head and overrides Stage 0 STOP so retrieve → fuse →
    predict on foreign donors can proceed.
    """
    global _FORCE_TRANSFER_ACTIVE
    _FORCE_TRANSFER_ACTIVE = bool(active)
    if active:
        add_evidence_flag("force_transfer_active", True)
        add_evidence_flag("loo_force_transfer", True)
        if source:
            add_evidence_flag("loo_force_transfer_source", str(source))


def force_transfer_active() -> bool:
    return bool(_FORCE_TRANSFER_ACTIVE)


def effective_force_transfer(explicit: bool = False) -> bool:
    """True when this turn is pinned to LOO / foreign-donor transfer."""
    return bool(explicit or _FORCE_TRANSFER_ACTIVE)


def user_message_requests_loo(text: str) -> bool:
    """Best-effort LOO intent from the user message (tool args take precedence)."""
    blob = (text or "").strip()
    if not blob:
        return False
    return any(p.search(blob) for p in _LOO_USER_PATTERNS)


def seed_loo_force_transfer_from_user_message(text: str) -> bool:
    """Sticky turn flag: operator LOO / force_transfer overrides Stage 0 own-head."""
    if user_message_requests_loo(text):
        set_force_transfer_active(True, source="user_message")
        return True
    return False


def loo_own_head_blocked_reason(
    *,
    rbps_list: list[str],
    cohort: str = "K562",
    allow_unseen: bool = False,
) -> Optional[str]:
    """Refuse predict on query/target alias alone when LOO is active."""
    if allow_unseen or not force_transfer_active():
        return None
    folded = [str(x).casefold() for x in rbps_list if str(x).strip()]
    if not folded:
        return None
    self_keys = force_transfer_self_aliases()
    if self_keys and all(x in self_keys for x in folded):
        return (
            "loo_force_transfer / force_transfer active: refuse own-head on the "
            "query/target alias — pass rbps=[foreign donor aliases with panel "
            "heads] only (single foreign donor OK). Stage 0 own-head STOP is "
            "overridden; continue retrieve → fuse → commit → abstain → predict."
        )
    if len(folded) == 1:
        try:
            qt = query_target()
            if qt and folded[0] == str(qt).casefold() and alias_has_panel_head(
                rbps_list[0], cohort=str(cohort)
            ):
                return (
                    "loo_force_transfer active: refuse predict_interaction on "
                    f"resolved target {rbps_list[0]!r} as own-head; use foreign "
                    "donors only."
                )
        except Exception:
            pass
    return None


def force_transfer_self_aliases() -> set[str]:
    """Aliases that are the QUERY/target itself under force_transfer / LOO.

    Used to refuse own-head disguised as transfer and to exclude the target's
    catalogue head from the donor pool. Includes resolve alias / UniProt and,
    when it matches those, near_match_donor (near-match-to-self).
    """
    keys: set[str] = set()
    qt = query_target()
    if qt:
        keys.add(str(qt).casefold())
    canon = canonical_request() or {}
    for field in ("alias", "uniprot", "rbp_id"):
        val = canon.get(field)
        if val:
            keys.add(str(val).casefold())
    near_d = _EVIDENCE_FLAGS.get("near_match_donor")
    if near_d:
        near_key = str(near_d).casefold()
        # near_match-to-self only — foreign near_match donors stay transferable
        # except via the separate near_match exclusion in predict/commit.
        if not keys or near_key in keys:
            keys.add(near_key)
    return keys


def record_evidence(record: dict[str, Any]) -> None:
    """Append an immutable provenance envelope for this scientific turn."""
    if isinstance(record, dict):
        _EVIDENCE_RECORDS.append(dict(record))


def evidence_records() -> list[dict[str, Any]]:
    return [dict(record) for record in _EVIDENCE_RECORDS]


def _done_set() -> set[str]:
    """Tools marked done this turn, for prerequisite checks."""
    done: set[str] = set()
    if _FUSE_DONE:
        done.add("fuse_similarity_views")
    if _COMMIT_DONE:
        done.add("commit_proxy_candidates")
    if _ABSTAIN_DONE:
        done.add("confidence_abstain")
    return done


# Retrieve tool names observed done this turn (for the fuse ``__any_retrieve__``
# edge). Populated by retrieve tools calling ``mark_retrieve_done``.
_RETRIEVE_DONE: set[str] = set()


def mark_retrieve_done(tool_name: str) -> None:
    if tool_name in STAGE_RETRIEVE:
        _RETRIEVE_DONE.add(tool_name)


def _any_retrieve_done() -> bool:
    return bool(_RETRIEVE_DONE)


def retrieve_blocked_reason(tool_name: str) -> Optional[str]:
    if _STAGE1_BYPASSED and tool_name in STAGE_RETRIEVE:
        return (
            f"Stage-1 bypassed (proxy cache hit): refusing {tool_name}. "
            "Use cached proxies → fuse_similarity_views / commit_proxy_candidates "
            "(stage1_bypassed=true). Do not re-run multi-view retrieve."
        )
    if force_transfer_active():
        return None
    if _OWN_HEAD_STOP and tool_name in RETRIEVE_AFTER_OWN_HEAD:
        return (
            f"Stage 0 STOP: own-head predict_interaction already succeeded this turn; "
            f"refusing {tool_name}. Emit JSON verdict now (do not retrieve/transfer). "
            "Operator LOO / force_transfer overrides this STOP — set "
            "force_transfer=true on commit/predict or restate LOO intent."
        )
    return None


def transfer_predict_blocked_reason(
    *,
    force_transfer: bool,
    rbps: list[str],
    cohort: str = "K562",
) -> Optional[str]:
    """Block donor/transfer predict until fuse → commit → abstain (when enabled).

    The edges are declared in :mod:`stage_contract` (``REQUIRES``); the messages
    below surface the earliest unmet prerequisite in stage order so the LLM gets
    the same guidance the contract encodes.
    """
    ft = effective_force_transfer(force_transfer)
    if _OWN_HEAD_STOP and not ft:
        return None
    rbps_list = [str(x) for x in rbps]
    # Own-head eligible single alias: no abstain gate (never under LOO)
    if (
        not ft
        and len(rbps_list) == 1
        and alias_has_panel_head(rbps_list[0], cohort=cohort)
    ):
        return None
    # Transfer / multi-donor path
    try:
        from nanobot.agent.tools.rbp.common import get_runtime_config

        integ = get_runtime_config().get("integrate") or {}
        if integ.get("use_abstain") is False:
            return None
    except Exception:
        pass
    # Data-driven: only enforce edges that stage_contract declares.
    predict_reqs = REQUIRES.get("predict_interaction", ())
    abstain_reqs = REQUIRES.get("confidence_abstain", ())
    commit_reqs = REQUIRES.get("commit_proxy_candidates", ())
    if "fuse_similarity_views" in commit_reqs and not _FUSE_DONE:
        return (
            "Transfer path: call fuse_similarity_views before "
            "commit_proxy_candidates / confidence_abstain / predict_interaction. "
            "Proposal §4: fuse → commit → abstain → predict."
        )
    if "commit_proxy_candidates" in abstain_reqs and not _COMMIT_DONE:
        return (
            "Transfer path: call commit_proxy_candidates after fuse "
                            "(select deterministic fused similarity rows) before "
            "confidence_abstain / predict_interaction. "
            "Proposal §4 Checkpoint 1."
        )
    if "fuse_similarity_views" in abstain_reqs and not _FUSE_DONE:
        return (
            "Transfer path: call fuse_similarity_views before confidence_abstain / "
            "predict_interaction. BUILD_SPEC: fuse → abstain → predict."
        )
    if "confidence_abstain" in predict_reqs and not _ABSTAIN_DONE:
        return (
            "Transfer path: call confidence_abstain after commit "
            "(prefer hits_emb / embedding hits) before predict_interaction. "
            "Proposal §4: fuse → commit → abstain → predict."
        )
    return None


def abstain_blocked_reason() -> Optional[str]:
    """Block confidence_abstain until fuse + commit on the unseen/transfer path."""
    if _OWN_HEAD_STOP and not force_transfer_active():
        return (
            "Stage 0 STOP: own-head already succeeded; refuse confidence_abstain. "
            "Emit JSON verdict now."
        )
    abstain_reqs = REQUIRES.get("confidence_abstain", ())
    if "commit_proxy_candidates" in abstain_reqs and not _COMMIT_DONE:
        return (
            "Call commit_proxy_candidates (select deterministic fused proxies) before "
            "confidence_abstain. Proposal §4: fuse → commit → abstain → predict."
        )
    if "fuse_similarity_views" in abstain_reqs and not _FUSE_DONE:
        return (
            "Call fuse_similarity_views before confidence_abstain. "
            "BUILD_SPEC: fuse → abstain → predict."
        )
    return None


def commit_blocked_reason() -> Optional[str]:
    """Block commit_proxy_candidates until fuse on the unseen path."""
    if _OWN_HEAD_STOP and not force_transfer_active():
        return (
            "Stage 0 STOP: own-head already succeeded; refuse commit_proxy_candidates. "
            "Emit JSON verdict now."
        )
    commit_reqs = REQUIRES.get("commit_proxy_candidates", ())
    if "fuse_similarity_views" in commit_reqs and not _FUSE_DONE:
        return (
            "Call fuse_similarity_views before commit_proxy_candidates. "
            "Proposal §4: fuse (evidence) → LLM commit (authoritative s_i)."
        )
    return None


def _axes_cfg() -> dict[str, Any]:
    try:
        from nanobot.agent.tools.rbp.common import get_runtime_config

        return dict(get_runtime_config().get("axes") or {})
    except Exception:
        return {}


def _structure_retrieve_done() -> bool:
    return bool(_RETRIEVE_DONE & STRUCTURE_RETRIEVE)


def _domain_retrieve_done() -> bool:
    return bool(_RETRIEVE_DONE & DOMAIN_RETRIEVE)


def _structure_axis_satisfied() -> bool:
    """True if structure retrieve ran, or honest unavailable/skipped flag set."""
    if _structure_retrieve_done():
        return True
    flags = evidence_flags() or {}
    return bool(
        flags.get("structure_axis_unavailable")
        or flags.get("structure_axis_skipped")
        or flags.get("af3_axis_skipped")
    )


def _domain_axis_satisfied() -> bool:
    """True if domain retrieve ran, or honest empty/skipped flag set."""
    if _domain_retrieve_done():
        return True
    flags = evidence_flags() or {}
    return bool(
        flags.get("domain_empty")
        or flags.get("axis_domain_skipped")
        or flags.get("domain_axis_skipped")
    )


def fuse_blocked_reason() -> Optional[str]:
    """Block fuse until multi-view retrieve is complete (delivery BUILD_SPEC).

    Requires at least one retrieve tool, plus structure + domain axes when those
    axes are enabled. Honest soft-fails (``structure_axis_unavailable``,
    ``domain_empty``, axis-skipped flags) satisfy the sentinel without inventing
    sim=0 hits. Proxy-cache Stage-1 bypass also satisfies these sentinels.
    """
    if _OWN_HEAD_STOP and not force_transfer_active():
        return (
            "Stage 0 STOP: own-head already succeeded; refuse fuse_similarity_views. "
            "Emit JSON verdict now."
        )
    if _STAGE1_BYPASSED:
        return None
    fuse_reqs = REQUIRES.get("fuse_similarity_views", ())
    if "__any_retrieve__" in fuse_reqs and not _any_retrieve_done():
        return (
            "Call at least one retrieve tool (seq_similarity / rna_blastn / "
            "struct_similarity / structure_fetch / domain_architecture / "
            "get_func_annotation) before fuse_similarity_views."
        )
    axes = _axes_cfg()
    if "__structure_axis__" in fuse_reqs and axes.get("structure") is not False:
        if not _structure_axis_satisfied():
            return (
                "Multi-view incomplete: call structure_fetch → struct_similarity "
                "(Foldseek; optional USalign refine) before fuse_similarity_views. "
                "On AFDB miss try predict_structure once; if structure is unavailable, "
                "surface structure_axis_unavailable (do not invent sim=0)."
            )
    if "__domain_axis__" in fuse_reqs and axes.get("domain") is not False:
        if not _domain_axis_satisfied():
            return (
                "Multi-view incomplete: call domain_architecture before "
                "fuse_similarity_views (Pfam-root Jaccard vs catalogue). "
                "If domain_source is none, surface domain_empty; optionally retry "
                "with network=true for InterProScan when critical."
            )
    return None


def blocked_envelope_json(tool_name: str) -> Optional[str]:
    """JSON error envelope if Stage-0 stop / soft-disable / Stage-1 bypass blocks."""
    try:
        from app.core.runtime_config import soft_disabled_tools

        if tool_name in set(soft_disabled_tools()):
            from nanobot.agent.tools.rbp.common import dumps, err

            return dumps(
                err(
                    f"disabled_by_evolution: {tool_name} is in tools.soft_disabled "
                    "(self-evolution retirement candidate; delivery untouched)."
                )
            )
    except Exception:
        pass
    reason = retrieve_blocked_reason(tool_name)
    if not reason:
        return None
    from nanobot.agent.tools.rbp.common import dumps, err

    return dumps(err(reason))


def alias_has_cohort_head(query: str, *, cohort: str = "K562") -> bool:
    """True only when ``query`` has a RhoBind head in exactly ``cohort``."""
    try:
        from rbp_eval.scoring.head_index import (
            alias_has_cohort_head as _alias_has_cohort_head,
        )

        return _alias_has_cohort_head(query, cohort=cohort)
    except Exception:
        return False


def cohort_head_aliases(cohort: str = "K562") -> set[str]:
    """Return canonical aliases backed by a real head in ``cohort``."""
    try:
        from rbp_eval.scoring.head_index import (
            cohort_head_aliases as _cohort_head_aliases,
        )

        return _cohort_head_aliases(cohort)
    except Exception:
        return set()


def alias_has_panel_head(query: str, *, cohort: str = "K562") -> bool:
    """Backward-compatible cohort-strict panel-head predicate."""
    return alias_has_cohort_head(query, cohort=cohort)


def alias_has_any_panel_head(query: str) -> bool:
    """True if ``query`` has a RhoBind head in either supported cohort."""
    q = (query or "").strip()
    if not q:
        return False
    try:
        from nanobot.agent.tools.rbp.common import (
            apply_delivery_env_facade,
            load_rbp_registry_facade,
        )

        apply_delivery_env_facade()
        reg = load_rbp_registry_facade()
    except Exception:
        return False
    q_up = q.upper()
    for up, rec in reg.items():
        if not isinstance(rec, dict):
            continue
        alias = str(rec.get("alias") or "").upper()
        if q_up not in (str(up).upper(), alias):
            continue
        heads = rec.get("head_index") or {}
        if isinstance(heads, dict) and any(value is not None for value in heads.values()):
            return True
    return False


__all__ = [
    "RETRIEVE_AFTER_OWN_HEAD",
    "STAGE_RETRIEVE",
    "reset_stage_guards",
    "set_literature_fuse_hits",
    "literature_fuse_hits",
    "set_literature_peers",
    "literature_peers",
    "lit_only_peers",
    "set_turn_fusion_weights",
    "turn_fusion_weights",
    "turn_fusion_weights_clamped",
    "register_retrieve_donors",
    "retrieve_donor_aliases",
    "register_retrieve_donors_from_tool_result",
    "record_lit_peer_decisions",
    "lit_peer_decisions",
    "corroborate_literature_hits_for_aliases",
    "mark_own_head_success",
    "mark_fuse_done",
    "mark_commit_done",
    "set_committed_proxies",
    "committed_proxies",
    "set_fused_proxies",
    "fused_proxies",
    "set_query_target",
    "query_target",
    "set_canonical_request",
    "canonical_request",
    "set_authoritative_score",
    "authoritative_score",
    "mark_abstain_done",
    "mark_retrieve_done",
    "mark_stage1_bypassed",
    "stage1_bypassed",
    "cache_proxies",
    "fuse_done",
    "commit_done",
    "abstain_done",
    "own_head_stop_active",
    "add_evidence_flag",
    "clear_evidence_flag",
    "clear_structure_axis_unavailable",
    "evidence_flags",
    "set_force_transfer_active",
    "force_transfer_active",
    "effective_force_transfer",
    "user_message_requests_loo",
    "seed_loo_force_transfer_from_user_message",
    "loo_own_head_blocked_reason",
    "force_transfer_self_aliases",
    "record_evidence",
    "evidence_records",
    "retrieve_blocked_reason",
    "transfer_predict_blocked_reason",
    "abstain_blocked_reason",
    "commit_blocked_reason",
    "fuse_blocked_reason",
    "blocked_envelope_json",
    "alias_has_cohort_head",
    "cohort_head_aliases",
    "alias_has_panel_head",
    "alias_has_any_panel_head",
]
