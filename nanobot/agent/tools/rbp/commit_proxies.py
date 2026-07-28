# -*- coding: utf-8 -*-
"""Stage-1 Checkpoint 1 — select deterministic fused proxy candidates.

The LLM may select/explain donors, but cannot create or modify numeric ``s_i``.
All committed scores are copied from the immediately preceding deterministic
``fuse_similarity_views`` result.
"""

from __future__ import annotations

from typing import Any

from nanobot.agent.tools.core.base import Tool, tool_parameters

from nanobot.agent.tools.rbp.common import dumps, err, ok


def _candidate_id(row: dict[str, Any]) -> str | None:
    rid = (
        row.get("rbp_id")
        or row.get("alias")
        or row.get("uniprot")
        or row.get("donor")
    )
    return str(rid) if rid else None


def _row_similarity(row: dict[str, Any]) -> float | None:
    """Read authoritative scientific similarity, with legacy fallbacks."""
    raw = row.get("vote_similarity")
    if raw is None:
        raw = row.get("similarity_score")
    if raw is None:
        raw = row.get("score")
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _normalize_candidate(row: dict[str, Any], *, tau_drop: float) -> dict[str, Any] | None:
    rid = _candidate_id(row)
    if not rid:
        return None
    sim = _row_similarity(row)
    if sim is None:
        return None
    if sim < float(tau_drop):
        return None
    br = row.get("similarity_breakdown")
    if not isinstance(br, dict):
        br = {}
    # Normalize breakdown keys to proposal {seq, struct, func}
    mapped: dict[str, float] = {}
    for k, v in br.items():
        key = str(k).lower()
        if key in ("seq", "sequence", "esmc_cosine", "esm2_cosine", "seq_identity"):
            mapped["seq"] = max(mapped.get("seq", 0.0), float(v))
        elif key in ("struct", "structure", "tm_score", "lddt", "fident"):
            mapped["struct"] = max(mapped.get("struct", 0.0), float(v))
        elif key in (
            "func",
            "function",
            "domain_jaccard",
            "domain_overlap",
            "function_similarity",
        ):
            mapped["func"] = max(mapped.get("func", 0.0), float(v))
        else:
            mapped[key] = float(v)
    rationale = str(row.get("rationale") or "").strip()
    out = {
        "rbp_id": str(rid),
        "alias": str(row.get("alias") or rid),
        "similarity_score": round(sim, 4),
        "vote_similarity": round(sim, 4),
        "similarity_breakdown": {k: round(v, 4) for k, v in mapped.items()},
        "rationale": rationale
        or "deterministic multi-view fusion",
    }
    if row.get("fused_score") is not None or row.get("score") is not None:
        out["fused_score"] = round(
            float(row.get("fused_score", row.get("score"))), 4
        )
    if isinstance(row.get("sim_by_modality"), dict):
        out["sim_by_modality"] = dict(row["sim_by_modality"])
    if row.get("uniprot"):
        out["uniprot"] = str(row["uniprot"])
    return out


@tool_parameters(
    {
        "type": "object",
        "properties": {
            "candidates": {
                "type": "array",
                "description": (
                    "Donors selected from the preceding fuse result. Only rbp_id/"
                    "alias selection and textual rationale are accepted; numeric "
                    "similarity fields are copied from deterministic fusion."
                ),
                "items": {"type": "object"},
            },
            "tau_drop": {
                "type": "number",
                "description": "Drop candidates with similarity_score below this "
                "(default from config, usually 0.30).",
            },
            "n_cand": {
                "type": "integer",
                "description": "Max candidates to keep (default from config, usually 5).",
            },
            "force_transfer": {
                "type": "boolean",
                "default": False,
                "description": (
                    "If true, treat target as unseen for this turn: do not inject "
                    "near_match_donor into the commit pool (runtime keeps transfer path)."
                ),
            },
        },
        "required": ["candidates"],
    }
)
class CommitProxyCandidatesTool(Tool):
    """Persist selected deterministic Stage-1 proxies for Stage 2/3."""

    _plugin_discoverable = True
    _scopes = {"core", "subagent"}

    @property
    def name(self) -> str:
        return "commit_proxy_candidates"

    @property
    def description(self) -> str:
        return (
            "Checkpoint 1 (proposal §4): after fuse_similarity_views, commit the "
            "selected proxy list (≤ n_cand, drop < τ_drop). Numeric similarity_score "
            "and breakdown are copied from deterministic fusion and cannot be "
            "supplied or changed by the LLM. "
            "Required on the unseen/transfer path before confidence_abstain / "
            "predict_interaction."
        )

    @property
    def read_only(self) -> bool:
        return True

    async def execute(self, **kwargs: Any) -> str:
        try:
            from nanobot.agent.tools.rbp.turn_guards import (
                blocked_envelope_json,
                commit_blocked_reason,
            )

            blocked = blocked_envelope_json(self.name)
            if blocked:
                return blocked
            reason = commit_blocked_reason()
            if reason:
                return dumps(err(reason))
        except Exception:
            pass

        if kwargs.get("force_transfer"):
            try:
                from nanobot.agent.tools.rbp.turn_guards import set_force_transfer_active

                set_force_transfer_active(True)
            except Exception:
                pass

        try:
            from nanobot.agent.tools.rbp.turn_guards import (
                evidence_flags,
                force_transfer_active,
            )

            near_donor = evidence_flags().get("near_match_donor")
            skip_near_inject = force_transfer_active()
        except Exception:
            near_donor = None
            skip_near_inject = False
        near_donor_key = str(near_donor or "").casefold()

        raw = kwargs.get("candidates")
        if not isinstance(raw, list) or not raw:
            return dumps(err("candidates must be a non-empty list of proxy objects"))

        try:
            from nanobot.agent.tools.rbp.common import get_runtime_config

            cfg = get_runtime_config()
        except Exception:
            cfg = {}
        tau = kwargs.get("tau_drop")
        tau_f = float(tau) if tau is not None else float(cfg.get("tau_drop") or 0.30)
        n_cand = kwargs.get("n_cand")
        n_max = int(n_cand) if n_cand is not None else int(cfg.get("n_cand") or 5)
        integrate = cfg.get("integrate") or {}
        require_cohort_head = integrate.get("require_cohort_head", True) is not False
        min_vote_similarity = float(integrate.get("min_vote_similarity", 0.35))
        try:
            from nanobot.agent.tools.rbp.turn_guards import canonical_request

            canonical = canonical_request() or {}
        except Exception:
            canonical = {}
        cohort = str(canonical.get("cohort") or cfg.get("cohort") or "K562")

        def has_eligible_head(row: dict[str, Any]) -> bool:
            if not require_cohort_head:
                return True
            try:
                from nanobot.agent.tools.rbp.turn_guards import alias_has_cohort_head

                return alias_has_cohort_head(
                    str(_candidate_id(row) or ""), cohort=cohort
                )
            except Exception:
                return False

        try:
            from nanobot.agent.tools.rbp.turn_guards import fused_proxies

            fused = fused_proxies()
        except Exception:
            fused = []
        if not fused:
            return dumps(
                err(
                    "no deterministic fused candidates stored; rerun "
                    "fuse_similarity_views before commit"
                )
            )

        fused_by_id: dict[str, dict[str, Any]] = {}
        for row in fused:
            for key in ("rbp_id", "alias", "uniprot", "donor"):
                if row.get(key):
                    fused_by_id[str(row[key]).casefold()] = row

        normalized: list[dict[str, Any]] = []
        unknown_ids: list[str] = []
        below_tau: list[str] = []
        below_vote_floor: list[str] = []
        filtered_unheaded: list[str] = []
        missing_score: list[str] = []
        for selected in raw:
            if not isinstance(selected, dict):
                continue
            rid = _candidate_id(selected)
            if not rid:
                continue
            authoritative = fused_by_id.get(str(rid).casefold())
            if authoritative is None:
                unknown_ids.append(str(rid))
                continue
            source = dict(authoritative)
            if selected.get("rationale"):
                source["rationale"] = str(selected["rationale"])
            if not has_eligible_head(source):
                filtered_unheaded.append(str(rid))
                continue
            sim = _row_similarity(source)
            if sim is None:
                missing_score.append(str(rid))
                continue
            if sim < tau_f:
                below_tau.append(f"{rid}={sim}")
                continue
            if sim < min_vote_similarity:
                below_vote_floor.append(f"{rid}={sim}")
                continue
            item = _normalize_candidate(source, tau_drop=tau_f)
            if item:
                normalized.append(item)
        # Delivery calls hits_emb the best signal. Always reserve up to three
        # committed slots for deterministic ESM-C neighbours, even if the LLM
        # omitted them from its selection-only payload.
        selected_ids = {
            str(_candidate_id(row) or "").casefold() for row in normalized
        }
        esm_rows = sorted(
            (
                row
                for row in fused
                if isinstance(row.get("sim_by_modality"), dict)
                and row["sim_by_modality"].get("esmc_cosine") is not None
                and has_eligible_head(row)
                and (_row_similarity(row) or 0.0) >= min_vote_similarity
                and not (
                    skip_near_inject
                    and near_donor_key
                    and str(_candidate_id(row) or "").casefold() == near_donor_key
                )
            ),
            key=lambda row: float(row["sim_by_modality"]["esmc_cosine"]),
            reverse=True,
        )[: min(3, n_max)]
        esm_normalized: list[dict[str, Any]] = []
        for row in esm_rows:
            rid = str(_candidate_id(row) or "").casefold()
            if not rid or rid in selected_ids:
                continue
            item = _normalize_candidate(row, tau_drop=tau_f)
            if item:
                item["rationale"] = (
                    item.get("rationale")
                    or "delivery best-signal ESM-C top neighbour"
                )
                esm_normalized.append(item)
                selected_ids.add(rid)

        esm_ids = {
            str(_candidate_id(row) or "").casefold()
            for row in esm_rows
        }
        required_esm = [
            row
            for row in normalized + esm_normalized
            if str(_candidate_id(row) or "").casefold() in esm_ids
        ][: min(3, n_max)]
        required_ids = {
            str(_candidate_id(row) or "").casefold() for row in required_esm
        }
        remainder = sorted(
            (
                row
                for row in normalized
                if str(_candidate_id(row) or "").casefold() not in required_ids
            ),
            key=lambda x: x.get("fused_score", x["similarity_score"]),
            reverse=True,
        )
        kept = (required_esm + remainder)[:n_max]
        # Near-match donor must be present for dominant-head aggregation even if
        # the LLM omitted it from the selection payload — unless force_transfer
        # explicitly keeps the multi-donor transfer path.
        if near_donor and not skip_near_inject and (
            not require_cohort_head
            or has_eligible_head({"alias": str(near_donor)})
        ):
            near_key = str(near_donor).casefold()
            kept_ids = {
                str(_candidate_id(row) or "").casefold() for row in kept
            }
            if near_key not in kept_ids:
                near_row = fused_by_id.get(near_key)
                near_item = (
                    _normalize_candidate(near_row, tau_drop=0.0)
                    if near_row is not None
                    else None
                )
                if near_item is None:
                    near_item = {
                        "rbp_id": str(near_donor),
                        "alias": str(near_donor),
                        "similarity_score": 1.0,
                        "vote_similarity": 1.0,
                        "similarity_breakdown": {"seq": 1.0},
                        "rationale": "near_match_donor forced into commit pool",
                    }
                else:
                    near_item["rationale"] = (
                        near_item.get("rationale")
                        or "near_match_donor forced into commit pool"
                    )
                kept = ([near_item] + kept)[:n_max]
        elif near_donor:
            try:
                from nanobot.agent.tools.rbp.turn_guards import add_evidence_flag

                add_evidence_flag("near_match_donor_no_head", True)
            except Exception:
                pass
        kept.sort(
            key=lambda x: x.get("fused_score", x["similarity_score"]),
            reverse=True,
        )
        if not kept:
            available = sorted(
                {
                    str(r.get("alias") or r.get("rbp_id") or r.get("uniprot"))
                    for r in fused
                    if r.get("alias") or r.get("rbp_id") or r.get("uniprot")
                }
            )
            if unknown_ids and not below_tau and not missing_score:
                return dumps(
                    err(
                        "selected ids not found in fused store; "
                        f"unknown={unknown_ids}; available={available}; "
                        "rerun fuse_similarity_views then select alias/uniprot "
                        "from that donors list"
                    )
                )
            if missing_score and not below_tau:
                return dumps(
                    err(
                        "fused rows matched but lack similarity_score/score; "
                        f"missing_score={missing_score}; available={available}; "
                        "rerun fuse_similarity_views"
                    )
                )
            detail_parts = [
                f"no candidates survived τ_drop={tau_f}",
            ]
            if below_tau:
                detail_parts.append(f"below_tau={below_tau}")
            if unknown_ids:
                detail_parts.append(f"unknown={unknown_ids}")
            if missing_score:
                detail_parts.append(f"missing_score={missing_score}")
            if filtered_unheaded:
                detail_parts.append(
                    f"unheaded_for_{cohort}={sorted(set(filtered_unheaded))}"
                )
            if below_vote_floor:
                detail_parts.append(
                    f"below_min_vote_similarity={below_vote_floor}"
                )
            detail_parts.append(f"available={available}")
            detail_parts.append(
                "broaden retrieval or use a held-out-calibrated lower threshold"
            )
            return dumps(err("; ".join(detail_parts)))

        try:
            from nanobot.agent.tools.rbp.turn_guards import set_committed_proxies

            set_committed_proxies(kept)
        except Exception as exc:
            return dumps(err(f"failed to persist committed proxies: {exc}"))

        return dumps(
            ok(
                {
                    "candidates": kept,
                    "n": len(kept),
                    "tau_drop": tau_f,
                    "min_vote_similarity": min_vote_similarity,
                    "n_cand": n_max,
                    "cohort": cohort,
                    "n_filtered_unheaded": len(set(filtered_unheaded)),
                    "authoritative": True,
                    "numeric_source": "deterministic_fuse_similarity_views",
                    "next": "confidence_abstain on hits_emb, then predict_interaction "
                    "on committed donor aliases",
                }
            )
        )
