# -*- coding: utf-8 -*-
"""Stage-0 near-known Fast Path: exact catalogue match or high seq identity.

Tool: ``check_near_known``. Compares the query protein to the RhoBind catalogue
via exact AA equality and/or delivery MMseqs identity. When best identity ≥
``near_match_seq_identity`` (default 0.95) to a headed RBP → ``near_match=true``
and a donor alias for own-head ``predict_interaction``, then STOP.

Under LOO / ``force_transfer``, near_match is disclosed but own-head Fast Path
is overridden — continue Stage 1–3 on foreign donors only. Read-only; identity
scores come from delivery / catalogue FASTA only.
"""

from __future__ import annotations

import asyncio
from typing import Any, Optional

from nanobot.agent.tools.core.base import Tool, tool_parameters

from nanobot.agent.tools.rbp.common import (
    dumps,
    err,
    find_exact_catalogue_entry,
    get_delivery_client,
    looks_like_rna,
    ok,
    resolve_protein_sequence,
    timed_call,
)


def _near_threshold() -> float:
    try:
        from nanobot.agent.tools.rbp.common import get_runtime_config

        return float(get_runtime_config().get("near_match_seq_identity") or 0.95)
    except Exception:
        return 0.95


def _near_match_own_head_hint(*, donor_placeholder: str = "<donor_alias>") -> str:
    try:
        from nanobot.agent.tools.rbp.turn_guards import force_transfer_active

        if force_transfer_active():
            return (
                "near_match under LOO / force_transfer: disclose near_match in "
                "caveats; do NOT own-head on the query/target. Continue Stage 1–3 "
                "retrieve → fuse → commit(force_transfer=true) → abstain → "
                "predict(force_transfer=true, rbps=[foreign donors only]). "
                "Stage 0 own-head STOP is overridden."
            )
    except Exception:
        pass
    return (
        f"near_match own-head Fast Path: call predict_interaction once "
        f"with rbp_id={donor_placeholder} (no force_transfer), disclose "
        "near_match, then STOP. force_transfer=true disables own-head Fast Path."
    )


def _not_near_known_hint() -> str:
    try:
        from nanobot.agent.tools.rbp.turn_guards import force_transfer_active

        if force_transfer_active():
            return (
                "not near-known; LOO / force_transfer active — continue Stage 1 "
                "retrieve → fuse → commit(force_transfer=true) → abstain → "
                "predict on foreign donors only (exclude query/target)."
            )
    except Exception:
        pass
    return (
        "not near-known; continue characterize → parallel retrieve → "
        "fuse → abstain → predict"
    )


def _score_as_identity(hit: dict[str, Any]) -> Optional[float]:
    """Normalize hit score to [0,1] identity when metric looks like identity."""
    try:
        from nanobot.agent.tools.rbp.common import is_near_match_score_facade as is_near_match_score
    except Exception:
        is_near_match_score = None  # type: ignore

    score = hit.get("score")
    if score is None:
        score = hit.get("identity")
    if score is None:
        return None
    try:
        s = float(score)
    except (TypeError, ValueError):
        return None
    metric = str(hit.get("metric") or hit.get("method") or "").lower()
    # Prefer explicit identity-like metrics; ESM cosine is not %id.
    if metric and any(
        x in metric for x in ("ident", "mmseqs", "seq_id", "pident", "blast")
    ):
        if s > 1.0 + 1e-9:
            return s / 100.0
        return s
    if not metric or metric in ("seq_identity", "identity"):
        if s > 1.0 + 1e-9:
            return s / 100.0
        # Ambiguous 0–1: treat as identity only if already near threshold helper agrees
        if is_near_match_score and is_near_match_score(s, threshold=0.90):
            return s if s <= 1.0 else s / 100.0
    return None


@tool_parameters(
    {
        "type": "object",
        "properties": {
            "sequence": {"type": "string"},
            "uniprot": {"type": "string"},
            "alias": {"type": "string"},
            "query": {"type": "string"},
            "top_k": {"type": "integer", "default": 5},
            "threshold": {
                "type": "number",
                "description": "Override near_match_seq_identity (default 0.95).",
            },
        },
        "required": [],
    }
)
class CheckNearKnownTool(Tool):
    """Stage-0 near-match detector — exact catalogue AA or identity ≥ threshold."""

    _plugin_discoverable = True
    _scopes = {"core", "subagent"}

    @property
    def name(self) -> str:
        return "check_near_known"

    @property
    def description(self) -> str:
        return (
            "Near-known Fast Path check: exact catalogue AA match or MMseqs "
            "seq identity vs catalogue. Exact FASTA equality OR best identity "
            "≥ 0.95 to a headed RBP → near_match=true + donor alias. Prefer "
            "own-head Fast Path on that donor (disclose near_match); do not "
            "force multi-donor transfer. Read-only; does not invent scores."
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
        raw = (kwargs.get("sequence") or "").strip()
        if raw and looks_like_rna(raw):
            return dumps(err("sequence looks like RNA; pass protein AA / alias / uniprot"))
        seq, src = resolve_protein_sequence(kwargs)
        if not seq:
            return dumps(
                err(
                    "need alias/uniprot or protein AA sequence for near-known check"
                )
            )
        thr = kwargs.get("threshold")
        threshold = float(thr) if thr is not None else _near_threshold()

        def _run():
            cohort = str(kwargs.get("cohort") or "K562")
            # Exact catalogue identity is stronger than masked MMseqs, which can
            # report <0.95 for the same accession on low-complexity proteins
            # (e.g. PTBP1 self-hit ~0.93). Two Stage-0 fast paths:
            # (1) resolve_rbp already set in-panel canonical identity
            # (2) query AA exactly equals a catalogue FASTA entry
            # Preserve transfer semantics: this is near-match evidence for the
            # matched catalogue head, never permission to invent a new head.
            try:
                from nanobot.agent.tools.rbp.turn_guards import (
                    alias_has_panel_head,
                    canonical_request,
                )

                canonical = canonical_request() or {}
                cohort = str(kwargs.get("cohort") or canonical.get("cohort") or cohort)
                provenance = canonical.get("input_provenance") or {}
                resolved_exact = bool(
                    provenance.get("resolved") and provenance.get("in_panel")
                )
                exact_alias = canonical.get("alias")
                exact_uniprot = canonical.get("uniprot")
                exact_id = exact_alias or exact_uniprot
                if (
                    resolved_exact
                    and exact_id
                    and alias_has_panel_head(str(exact_id), cohort=cohort)
                ):
                    out = {
                        "near_match": True,
                        "threshold": threshold,
                        "best_identity": None,
                        "donor_alias": str(exact_alias or exact_id),
                        "donor_uniprot": (
                            str(exact_uniprot) if exact_uniprot else None
                        ),
                        "headed": True,
                        "hits": [],
                        "sequence_source": src,
                        "match_basis": "resolve_exact_catalogue_identifier",
                        "hint": _near_match_own_head_hint(
                            donor_placeholder=str(exact_alias or exact_id)
                        ),
                    }
                    try:
                        from nanobot.agent.tools.rbp.turn_guards import (
                            add_evidence_flag,
                        )

                        add_evidence_flag("near_match", True)
                        add_evidence_flag("near_match_donor", out["donor_alias"])
                        add_evidence_flag(
                            "near_match_basis", out["match_basis"]
                        )
                    except Exception:
                        pass
                    return out

                exact_fa = find_exact_catalogue_entry(seq)
                if exact_fa:
                    donor = str(exact_fa.get("alias") or exact_fa.get("uniprot") or "")
                    donor_up = str(exact_fa.get("uniprot") or "") or None
                    if donor and alias_has_panel_head(donor, cohort=cohort):
                        out = {
                            "near_match": True,
                            "threshold": threshold,
                            "best_identity": 1.0,
                            "donor_alias": donor,
                            "donor_uniprot": donor_up,
                            "headed": True,
                            "hits": [],
                            "sequence_source": src,
                            "match_basis": "exact_catalogue_sequence",
                            "hint": _near_match_own_head_hint(
                                donor_placeholder=donor
                            ),
                        }
                        try:
                            from nanobot.agent.tools.rbp.turn_guards import (
                                add_evidence_flag,
                            )

                            add_evidence_flag("near_match", True)
                            add_evidence_flag(
                                "near_match_donor", out["donor_alias"]
                            )
                            add_evidence_flag(
                                "near_match_basis", out["match_basis"]
                            )
                        except Exception:
                            pass
                        return out
            except Exception:
                pass

            client = get_delivery_client()
            mm = client.call(
                "protein_seq_similarity",
                {"sequence": seq, "top_k": int(kwargs.get("top_k") or 5)},
            )
            if mm.get("error") and not mm.get("hits"):
                raise RuntimeError(mm.get("error") or "protein_seq_similarity failed")
            hits = list(mm.get("hits") or [])
            best: Optional[dict[str, Any]] = None
            best_id = -1.0
            for h in hits:
                if not isinstance(h, dict):
                    continue
                ident = _score_as_identity(h)
                if ident is None:
                    continue
                if ident > best_id:
                    best_id = ident
                    best = h
            near = bool(best is not None and best_id >= threshold)
            donor_alias = None
            donor_uniprot = None
            if best is not None:
                donor_alias = best.get("alias") or best.get("rbp_id") or best.get("name")
                donor_uniprot = best.get("uniprot") or best.get("rbp_id")
            # Prefer headed donors when claiming near_match
            headed = False
            if near and donor_alias:
                try:
                    from nanobot.agent.tools.rbp.turn_guards import alias_has_panel_head

                    headed = alias_has_panel_head(str(donor_alias), cohort=cohort)
                    if not headed and donor_uniprot:
                        headed = alias_has_panel_head(
                            str(donor_uniprot), cohort=cohort
                        )
                except Exception:
                    headed = True  # delivery hit implies catalogue; soft
            if near and not headed:
                near = False
            out = {
                "near_match": near,
                "threshold": threshold,
                "best_identity": best_id if best_id >= 0 else None,
                "donor_alias": str(donor_alias) if near and donor_alias else None,
                "donor_uniprot": str(donor_uniprot) if near and donor_uniprot else None,
                "headed": headed if best is not None else False,
                "hits": hits[:5],
                "sequence_source": src,
                "hint": (
                    _near_match_own_head_hint(donor_placeholder="<donor_alias>")
                    if near
                    else _not_near_known_hint()
                ),
            }
            if near:
                try:
                    from nanobot.agent.tools.rbp.turn_guards import add_evidence_flag

                    add_evidence_flag("near_match", True)
                    add_evidence_flag("near_match_donor", out["donor_alias"])
                except Exception:
                    pass
            return out

        value, ms, error = await asyncio.to_thread(lambda: timed_call(_run))
        if error:
            return dumps(err(error, ms))
        return dumps(ok(value, ms))
