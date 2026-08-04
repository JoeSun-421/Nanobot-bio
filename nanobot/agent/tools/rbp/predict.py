# -*- coding: utf-8 -*-
"""P0 tool: ``predict_interaction`` — RhoBind fθ(RNA, RBP) binding probabilities.

Bridges the nanobot Tool to delivery ``rhobind_predict``
(``agent/backbone/predict_api.py``). Two product paths:

* Own-head (Stage 0): in-panel or near-known headed alias → call once with
  ``rbp_id``, emit JSON, STOP (unless LOO / ``force_transfer``)
* Transfer / multi-donor (Stage 3): after fuse → commit → abstain, pass
  ``rbps=[donor aliases]``; probs come only from delivery heads

Invariant: never invent ``p_hat``. On error/OOM return null and do not retry.
Per-turn call/cache guards prevent anti-loops; cache hits re-apply Stage
guard side-effects (own-head STOP, low-head-coverage flags).
"""

from __future__ import annotations

import asyncio
import hashlib
from typing import Any

from nanobot.agent.tools.core.base import Tool, tool_parameters

from nanobot.agent.tools.rbp.common import (
    dumps,
    err,
    get_delivery_client,
    ok,
    resolve_device,
    timed_call,
)


def _predict_cache_key(rna: str, rbps: list[str], cohort: str, device: str) -> str:
    raw = "|".join(
        [
            rna.strip().upper(),
            ",".join(sorted(str(x).upper() for x in rbps)),
            str(cohort or "K562").upper(),
            str(device or "auto").lower(),
        ]
    )
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:24]


def _replay_predict_guards(cached: str, rbps_list: list[str]) -> None:
    """Re-apply stage-guard side-effects for a cache-hit predict result.

    Keeps a cached success contract-equivalent to a fresh one: own-head STOP and
    the low-head-coverage evidence flag. Best-effort; never raises to the caller.
    """
    try:
        import json

        payload = json.loads(cached)
        value = payload.get("value") if isinstance(payload, dict) else None
        if not isinstance(value, dict):
            return
        path = value.get("path")
        if path == "own_head":
            from nanobot.agent.tools.rbp.turn_guards import mark_own_head_success

            mark_own_head_success()
        elif path == "multi_head":
            preds = value.get("predictions") or []
            n_with_head = sum(
                1 for p in preds if isinstance(p, dict) and p.get("prob") is not None
            )
            n_requested = len(rbps_list)
            if n_requested > 0 and 0 < n_with_head < n_requested:
                from nanobot.agent.tools.rbp.turn_guards import add_evidence_flag

                add_evidence_flag("low_head_coverage", n_with_head / n_requested)
    except Exception:
        pass


def _pred_alias(row: dict[str, Any]) -> str:
    return str(row.get("alias") or row.get("rbp_id") or row.get("donor") or "")


def _find_donor_prob(
    predictions: list[Any], donor: str
) -> tuple[float | None, dict[str, Any] | None]:
    target = str(donor or "").casefold()
    if not target:
        return None, None
    for row in predictions:
        if not isinstance(row, dict):
            continue
        if _pred_alias(row).casefold() != target:
            continue
        if row.get("prob") is None:
            return None, row
        try:
            return float(row["prob"]), row
        except (TypeError, ValueError):
            return None, row
    return None, None


@tool_parameters(
    {
        "type": "object",
        "properties": {
            "rna": {"type": "string", "description": "RNA sequence (A/C/G/U/T)"},
            "rbp_id": {
                "type": "string",
                "description": "Single RBP alias (e.g. PTBP1); mapped to rbps=[alias]",
            },
            "rbps": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of RBP aliases (donors or own head)",
            },
            "cohort": {"type": "string", "enum": ["K562", "HepG2"], "default": "K562"},
            "device": {
                "type": "string",
                "enum": ["auto", "cuda", "cpu"],
                "default": "auto",
                "description": "Prefer cuda when available (ideal GPU env)",
            },
            "aggregate": {
                "type": "string",
                "enum": ["max", "mean", "weighted"],
                "default": "weighted",
                "description": (
                    "Cross-donor aggregation when multiple rbps are scored. "
                    "'weighted' = delivery similarity_weighted_vote: "
                    "Σ(s_i × tprior_i × quality_i × prob_i) / Σ(s_i × tprior_i × quality_i) "
                    "using committed proxy similarity_score. "
                    "Window aggregation inside each head stays max/mean at delivery."
                ),
            },
            "target": {
                "type": "string",
                "description": (
                    "Target RBP alias for transfer_prior_lookup on multi-donor path. "
                    "Defaults to resolve_rbp alias stored this turn."
                ),
            },
            "force_transfer": {
                "type": "boolean",
                "default": False,
                "description": (
                    "LOO / leave-one-out: treat target as unseen. Pass "
                    "rbps=[foreign donor aliases with panel heads] — a single "
                    "foreign donor is valid (weighted vote degenerates). "
                    "Refuses rbps solely equal to the query/target alias. "
                    "Also set on commit_proxy_candidates; sticky for the turn "
                    "when the user requests LOO. Disables near-match own-head "
                    "Fast Path (runtime stays multi_head)."
                ),
            },
            "allow_unseen_own_head": {
                "type": "boolean",
                "default": False,
                "description": "Internal/test override — do not use in product path.",
            },
        },
        "required": ["rna"],
    }
)
class PredictInteractionTool(Tool):
    """P0 Stage-0/3 predictor — own-head Fast Path or multi-donor transfer probs."""

    _plugin_discoverable = True
    _scopes = {"core", "subagent"}
    # Anti-loop: same (rna, rbps, cohort) only runs once per turn.
    _cache: dict[str, str] = {}
    _calls_used: int = 0
    _MAX_CALLS: int = 6  # own head + ≤5 proxies
    _DEFAULT_TIMEOUT_S: int = 180  # fail fast on OOM/hang instead of retry forever

    @property
    def name(self) -> str:
        return "predict_interaction"

    @property
    def description(self) -> str:
        return (
            "RhoBind interaction classifier (delivery rhobind_predict). "
            "OWN-HEAD fast path: after resolve_rbp in_panel=true OR "
            "check_near_known near_match to a headed catalogue RBP, call once with "
            "rbp_id=<matched alias> then STOP and emit JSON (do not transfer) — "
            "unless operator LOO / force_transfer (sticky turn flag or tool arg). "
            "True unseen RBP: pass rbps=[donor aliases]. "
            "On error/OOM do NOT retry — p_hat=null."
        )

    @property
    def read_only(self) -> bool:
        return True

    @classmethod
    def reset_turn_guards(cls) -> None:
        cls._cache.clear()
        cls._calls_used = 0
        try:
            from nanobot.agent.tools.rbp.turn_guards import reset_stage_guards

            reset_stage_guards()
        except Exception:
            pass

    async def execute(self, **kwargs: Any) -> str:
        rna = kwargs.get("rna") or ""
        rbps = kwargs.get("rbps")
        if not rbps and kwargs.get("rbp_id"):
            rbps = [kwargs["rbp_id"]]
        if not rna or not rbps:
            return dumps(err("rna and rbps (or rbp_id) are required"))
        rbps_list = [str(x) for x in list(rbps)]
        cohort = kwargs.get("cohort") or "K562"
        force_transfer_kw = bool(kwargs.get("force_transfer"))
        allow_unseen = bool(kwargs.get("allow_unseen_own_head"))
        near_match_promoted = False
        near_match_donor: str | None = None

        try:
            from nanobot.agent.tools.rbp.turn_guards import (
                effective_force_transfer,
                loo_own_head_blocked_reason,
                set_force_transfer_active,
            )

            if force_transfer_kw:
                set_force_transfer_active(True, source="predict_arg")
            force_transfer = effective_force_transfer(force_transfer_kw)
            loo_block = loo_own_head_blocked_reason(
                rbps_list=rbps_list,
                cohort=str(cohort),
                allow_unseen=allow_unseen,
            )
            if loo_block:
                return dumps(err(loo_block))
        except Exception:
            force_transfer = force_transfer_kw

        # Proposal Stage 0 near-match Fast Path: if catalogue identity is already
        # established, use that headed RBP as own-head (do not pretend unknown).
        # LOO / force_transfer (sticky turn flag or tool arg) keeps multi_head.
        if not force_transfer:
            try:
                from nanobot.agent.tools.rbp.turn_guards import (
                    add_evidence_flag,
                    alias_has_panel_head,
                    evidence_flags,
                )

                flags = evidence_flags() or {}
                donor = flags.get("near_match_donor")
                if flags.get("near_match") and donor:
                    donor_s = str(donor)
                    if alias_has_panel_head(donor_s, cohort=str(cohort)):
                        near_match_donor = donor_s
                        near_match_promoted = True
                        if [x.casefold() for x in rbps_list] != [donor_s.casefold()]:
                            rbps_list = [donor_s]
                        add_evidence_flag("near_match_own_head", True)
                        add_evidence_flag("near_match_own_head_donor", donor_s)
            except Exception:
                near_match_promoted = False

        # Proposal §9.2: never call fθ on an unseen target without proxy donors.
        # LOO force_transfer: a single *foreign* donor is valid (weighted vote
        # degenerates). Refuse only true own-head disguised as transfer —
        # rbps equals the query/target alias alone (or only self aliases).
        if not allow_unseen and (force_transfer or len(rbps_list) == 1):
            try:
                from nanobot.agent.tools.rbp.turn_guards import (
                    alias_has_panel_head,
                    force_transfer_self_aliases,
                    loo_own_head_blocked_reason,
                )

                loo_block = loo_own_head_blocked_reason(
                    rbps_list=rbps_list,
                    cohort=str(cohort),
                    allow_unseen=allow_unseen,
                )
                if loo_block:
                    return dumps(err(loo_block))
                if force_transfer and not near_match_promoted:
                    self_keys = force_transfer_self_aliases()
                    folded = [x.casefold() for x in rbps_list]
                    if self_keys and folded and all(x in self_keys for x in folded):
                        return dumps(
                            err(
                                "force_transfer=true: refuse own-head disguised as "
                                "transfer — rbps must be foreign donor aliases with "
                                "panel heads (single foreign donor OK for LOO). "
                                "Do not pass the query/target alias alone. "
                                "Explicit force_transfer disables near-match "
                                "own-head Fast Path."
                            )
                        )
                if (
                    not force_transfer
                    and len(rbps_list) == 1
                    and not alias_has_panel_head(rbps_list[0], cohort=str(cohort))
                ):
                    return dumps(
                        err(
                            f"Unseen / out-of-panel target {rbps_list[0]!r}: "
                            "MUST NOT call predict_interaction as own-head. "
                            "Retrieve proxy donors (seq/domain/structure), then "
                            "predict only on donor aliases that have heads."
                        )
                    )
            except Exception:
                # If registry unavailable, fall through to delivery (will fail soft).
                pass

        # BUILD_SPEC: fuse → confidence_abstain → predict on transfer path.
        # Near-match own-head promotion skips the transfer gate.
        try:
            from nanobot.agent.tools.rbp.turn_guards import (
                transfer_predict_blocked_reason,
            )

            blocked_abs = transfer_predict_blocked_reason(
                force_transfer=force_transfer,
                rbps=rbps_list,
                cohort=str(cohort),
            )
            if blocked_abs and not near_match_promoted:
                return dumps(err(blocked_abs))
        except Exception:
            pass

        # Product transfer must never send a donor without a real head for the
        # requested cohort into RhoBind. Fuse and commit apply the same filter;
        # this is the fail-closed boundary immediately before model execution.
        transfer_request = (
            not near_match_promoted and (force_transfer or len(rbps_list) > 1)
        )
        if transfer_request:
            try:
                from nanobot.agent.tools.rbp.common import get_runtime_config
                from nanobot.agent.tools.rbp.turn_guards import (
                    add_evidence_flag,
                    alias_has_cohort_head,
                    canonical_request,
                    evidence_flags,
                    set_authoritative_score,
                )

                cfg = get_runtime_config()
                integrate = cfg.get("integrate") or {}
                if integrate.get("require_cohort_head", True) is not False:
                    requested_donors = list(rbps_list)
                    rbps_list = [
                        donor
                        for donor in requested_donors
                        if alias_has_cohort_head(donor, cohort=str(cohort))
                    ]
                    n_filtered = len(requested_donors) - len(rbps_list)
                    if n_filtered:
                        add_evidence_flag("n_filtered_unheaded", n_filtered)
                        add_evidence_flag(
                            "low_head_coverage",
                            len(rbps_list) / len(requested_donors),
                        )
                    if force_transfer:
                        from nanobot.agent.tools.rbp.turn_guards import (
                            force_transfer_self_aliases,
                        )

                        # Never use the query/target own head; also drop
                        # near_match_donor so Fast Path cannot leak into LOO.
                        exclude_self = set(force_transfer_self_aliases())
                        near_d = (evidence_flags() or {}).get("near_match_donor")
                        if near_d:
                            exclude_self.add(str(near_d).casefold())
                        if exclude_self:
                            before = list(rbps_list)
                            rbps_list = [
                                donor
                                for donor in rbps_list
                                if donor.casefold() not in exclude_self
                            ]
                            if len(rbps_list) < len(before):
                                add_evidence_flag(
                                    "force_transfer_excluded_self",
                                    sorted(exclude_self),
                                )
                    if not rbps_list:
                        add_evidence_flag("no_headed_donors", True)
                        set_authoritative_score(
                            None,
                            source="delivery_similarity_weighted_vote",
                            mode="multi_head",
                            score_kind="weighted_consensus",
                            provenance={
                                "cohort": cohort,
                                "reason": "no_headed_donors",
                                "requested_donors": requested_donors,
                                "canonical_request": canonical_request(),
                            },
                        )
                        req_agg = str(
                            kwargs.get("aggregate")
                            or (cfg.get("predict") or {}).get("aggregate")
                            or "weighted"
                        )
                        return dumps(
                            ok(
                                {
                                    "predictions": [],
                                    "cohort": cohort,
                                    "path": "multi_head",
                                    "prob": None,
                                    "aggregate": req_agg,
                                    "aggregation": {
                                        "error": "no_headed_donors",
                                        "requested_donors": requested_donors,
                                    },
                                    "score_kind": "weighted_consensus",
                                    "near_match_promoted": False,
                                    "stop_hint": (
                                        "No eligible donor has a head in the requested "
                                        "cohort; emit p_hat=null, confidence=low."
                                    ),
                                }
                            )
                        )
                    if len(rbps_list) == 1:
                        add_evidence_flag("single_donor_transfer", True)
            except Exception:
                # Registry/read failures fail soft here; delivery will still reject
                # aliases without a usable cohort head.
                pass

        device = resolve_device(kwargs.get("device"))
        key = _predict_cache_key(rna, rbps_list, cohort, device)

        cached = PredictInteractionTool._cache.get(key)
        if cached is not None:
            # Replay stage-guard side-effects so a cache hit is contract-equivalent
            # to a fresh success (own-head STOP + low-head-coverage flag). Without
            # this, a repeated identical call would silently drop the own-head STOP.
            _replay_predict_guards(cached, rbps_list)
            return cached

        if PredictInteractionTool._calls_used >= PredictInteractionTool._MAX_CALLS:
            out = dumps(
                err(
                    "predict_interaction call budget exhausted this turn; "
                    "do not retry — proceed to verdict with p_hat=null if no probs"
                )
            )
            return out

        # Cross-donor aggregate mode (proposal §4 weighted). Delivery only
        # accepts max/mean for per-window pooling inside each head.
        cfg_agg = None
        try:
            from nanobot.agent.tools.rbp.common import get_runtime_config

            cfg_agg = (get_runtime_config().get("predict") or {}).get("aggregate")
        except Exception:
            cfg_agg = None
        req_agg = str(kwargs.get("aggregate") or cfg_agg or "weighted")
        delivery_agg = req_agg if req_agg in ("max", "mean") else "max"

        def _run():
            client = get_delivery_client(device=device)
            return client.call(
                "rhobind_predict",
                {
                    "rna": rna,
                    "rbps": rbps_list,
                    "cohort": cohort,
                    "device": device,
                    "aggregate": delivery_agg,
                    # delivery subprocess timeout (seconds)
                    "timeout_s": int(
                        kwargs.get("timeout_s")
                        or PredictInteractionTool._DEFAULT_TIMEOUT_S
                    ),
                },
            )

        PredictInteractionTool._calls_used += 1
        try:
            out, ms, error = await asyncio.wait_for(
                asyncio.to_thread(lambda: timed_call(_run)),
                timeout=float(PredictInteractionTool._DEFAULT_TIMEOUT_S) + 30.0,
            )
        except asyncio.TimeoutError:
            result = dumps(
                err(
                    "predict_interaction timed out (likely RhoBind OOM / slow env); "
                    "do not retry — emit verdict with p_hat=null, confidence=low",
                    0.0,
                )
            )
            PredictInteractionTool._cache[key] = result
            return result

        if error:
            result = dumps(
                err(
                    f"{error}; do not retry predict_interaction — "
                    "continue with annotation/similarity evidence, p_hat=null",
                    ms,
                )
            )
            PredictInteractionTool._cache[key] = result
            return result
        if not isinstance(out, dict):
            result = dumps(
                err(
                    "rhobind_predict returned no payload; "
                    "do not retry — emit verdict with p_hat=null",
                    ms,
                )
            )
            PredictInteractionTool._cache[key] = result
            return result
        if out.get("error") or out.get("ok") is False:
            result = dumps(
                err(
                    f"{out.get('error') or 'rhobind_predict failed'}; "
                    "do not retry — emit verdict with p_hat=null",
                    ms,
                )
            )
            PredictInteractionTool._cache[key] = result
            return result
        preds = out.get("predictions") or []
        # Own-head: single panel alias without force_transfer, including near-match
        # Fast Path promotion onto the matched catalogue head.
        path = "own_head" if len(rbps_list) == 1 and not force_transfer else "multi_head"
        if near_match_promoted and len(rbps_list) == 1:
            path = "own_head"
        # Explicit loop: comprehension filters do not narrow .get() for basedpyright.
        probs: list[float] = []
        for p in preds:
            if not isinstance(p, dict):
                continue
            raw = p.get("prob")
            if raw is None:
                continue
            try:
                probs.append(float(raw))
            except (TypeError, ValueError):
                continue
        if not probs:
            # e.g. unknown alias / no K562 head — not a successful own-head
            try:
                from nanobot.agent.tools.rbp.turn_guards import (
                    canonical_request,
                    set_authoritative_score,
                )

                set_authoritative_score(
                    None,
                    source="delivery_rhobind_predict",
                    mode=path,
                    provenance={
                        "cohort": out.get("cohort"),
                        "reason": "no_usable_prob",
                        "canonical_request": canonical_request(),
                    },
                )
            except Exception:
                pass
            result = dumps(
                ok(
                    {
                        "predictions": preds,
                        "cohort": out.get("cohort"),
                        "n_windows": out.get("n_windows"),
                        "path": path,
                        "prob": None,
                        "aggregate": req_agg,
                        "stop_hint": (
                            "No usable prob (unknown RBP or no cohort head). "
                            "Do NOT treat as own-head success. "
                            "If resolve_rbp.in_panel=false: transfer with donors that "
                            "have heads, or emit verdict p_hat=null, confidence=low."
                        ),
                        "_delivery_script": out.get("_script"),
                    },
                    ms,
                )
            )
            PredictInteractionTool._cache[key] = result
            return result

        # Cross-donor p_hat policy:
        # - own_head: single panel head (includes near-match Fast Path promotion)
        # - otherwise: delivery similarity_weighted_vote (weighted consensus)
        p_hat: float | None
        agg_meta: dict[str, Any] | None = None
        score_source = "delivery_similarity_weighted_vote"
        score_kind = "weighted_consensus"
        if path == "own_head":
            if near_match_promoted and near_match_donor:
                near_prob, near_row = _find_donor_prob(list(preds), near_match_donor)
                p_hat = float(near_prob if near_prob is not None else probs[0])
                score_source = "delivery_rhobind_predict"
                score_kind = "own_head"
                agg_meta = {
                    "formula": "near_match_own_head",
                    "source": "delivery_rhobind_predict",
                    "near_match_promoted": True,
                    "dominant_donor": near_match_donor,
                    "dominant_prob": p_hat,
                    "note": (
                        "Near-match Fast Path: catalogue head used as own-head; "
                        "disclose near_match in explanation."
                    ),
                }
                if near_row and near_row.get("head_index") is not None:
                    agg_meta["dominant_head_index"] = near_row.get("head_index")
            else:
                p_hat = float(probs[0])
                score_source = "delivery_rhobind_predict"
                score_kind = "own_head"
        elif req_agg == "weighted":
            try:
                from nanobot.agent.tools.rbp.common import get_runtime_config
                from nanobot.agent.tools.rbp.turn_guards import (
                    committed_proxies,
                    query_target,
                )
                from rbp_eval.scoring.fuse_hits import (
                    map_donor_quality,
                    map_transfer_priors,
                )

                proxies = committed_proxies()
                if proxies:
                    integ = get_runtime_config().get("integrate") or {}
                    predicted_donors = {
                        donor.casefold() for donor in rbps_list
                    }
                    proxies = [
                        proxy
                        for proxy in proxies
                        if str(
                            proxy.get("rbp_id")
                            or proxy.get("alias")
                            or ""
                        ).casefold()
                        in predicted_donors
                    ]
                    max_vote_donors = int(integ.get("max_vote_donors", 2))
                    if max_vote_donors > 0 and len(proxies) > max_vote_donors:
                        n_before_vote_limit = len(proxies)
                        proxies = sorted(
                            proxies,
                            key=lambda proxy: float(
                                proxy.get("similarity_score")
                                or proxy.get("vote_similarity")
                                or 0.0
                            ),
                            reverse=True,
                        )[:max_vote_donors]
                        from nanobot.agent.tools.rbp.turn_guards import (
                            add_evidence_flag,
                        )

                        add_evidence_flag(
                            "n_filtered_vote_tail",
                            n_before_vote_limit - len(proxies),
                        )
                    tprior_map: dict[str, float] = {}
                    quality_map: dict[str, float] = {}
                    donors = [
                        str(p.get("rbp_id") or p.get("alias"))
                        for p in proxies
                        if p.get("rbp_id") or p.get("alias")
                    ]
                    target = (
                        kwargs.get("target")
                        or kwargs.get("rbp_id")
                        or query_target()
                    )
                    client = get_delivery_client()
                    if integ.get("use_transfer_prior", True) and target and donors:
                        tp_raw = client.call(
                            "transfer_prior_lookup",
                            {"target": str(target), "donors": donors},
                        )
                        if (
                            not tp_raw.get("error")
                            and tp_raw.get("ok") is not False
                        ):
                            tprior_map = map_transfer_priors(tp_raw)
                    if integ.get("use_donor_quality", True) and donors:
                        q_raw = client.call(
                            "donor_quality_prior",
                            {
                                "donors": donors,
                                "cohort": str(cohort or "K562"),
                            },
                        )
                        if (
                            not q_raw.get("error")
                            and q_raw.get("ok") is not False
                        ):
                            quality_map = map_donor_quality(q_raw)
                    min_donor_quality = float(
                        integ.get("min_donor_quality", 0.0)
                    )
                    if min_donor_quality > 0:
                        quality_folded = {
                            str(alias).casefold(): float(score)
                            for alias, score in quality_map.items()
                        }
                        eligible_donors = [
                            donor
                            for donor in donors
                            if quality_folded.get(donor.casefold(), 0.0)
                            >= min_donor_quality
                        ]
                        n_quality_filtered = len(donors) - len(eligible_donors)
                        if n_quality_filtered:
                            from nanobot.agent.tools.rbp.turn_guards import (
                                add_evidence_flag,
                            )

                            add_evidence_flag(
                                "n_filtered_low_donor_quality",
                                n_quality_filtered,
                            )
                        donors = eligible_donors
                        eligible_folded = {
                            donor.casefold() for donor in eligible_donors
                        }
                        quality_map = {
                            alias: score
                            for alias, score in quality_map.items()
                            if str(alias).casefold() in eligible_folded
                        }
                        tprior_map = {
                            alias: score
                            for alias, score in tprior_map.items()
                            if str(alias).casefold() in eligible_folded
                        }
                        if len(donors) == 1:
                            from nanobot.agent.tools.rbp.turn_guards import (
                                add_evidence_flag,
                            )

                            add_evidence_flag("single_donor_transfer", True)
                        elif not donors:
                            from nanobot.agent.tools.rbp.turn_guards import (
                                add_evidence_flag,
                            )

                            add_evidence_flag("no_headed_donors", True)
                    eligible_folded = {donor.casefold() for donor in donors}
                    vote_predictions = [
                        {
                            "donor": str(
                                p.get("alias") or p.get("rbp_id") or ""
                            ),
                            "prob": p.get("prob"),
                        }
                        for p in preds
                        if isinstance(p, dict)
                        and (p.get("alias") or p.get("rbp_id"))
                        and p.get("prob") is not None
                        and str(
                            p.get("alias") or p.get("rbp_id") or ""
                        ).casefold()
                        in eligible_folded
                    ]
                    vote_hits = [
                        {
                            "alias": str(
                                p.get("alias") or p.get("rbp_id") or ""
                            ),
                            "score": p.get("similarity_score"),
                        }
                        for p in proxies
                        if isinstance(p, dict)
                        and (p.get("alias") or p.get("rbp_id"))
                        and p.get("similarity_score") is not None
                        and str(
                            p.get("alias") or p.get("rbp_id") or ""
                        ).casefold()
                        in eligible_folded
                    ]
                    vote_raw = (
                        client.call(
                            "similarity_weighted_vote",
                            {
                                "predictions": vote_predictions,
                                "hits": vote_hits,
                                "transfer_priors": tprior_map,
                                "donor_quality": quality_map,
                            },
                        )
                        if donors
                        else {"ok": False, "error": "no_donors_after_quality_filter"}
                    )
                    if vote_raw.get("error") or vote_raw.get("ok") is False:
                        p_hat = None
                        agg_meta = {
                            "formula": "delivery_similarity_weighted_vote",
                            "source": "delivery_similarity_weighted_vote",
                            "error": vote_raw.get("error") or "vote failed",
                        }
                    else:
                        p_hat = vote_raw.get("score")
                        agg_meta = {
                            "p_hat": p_hat,
                            "terms": list(vote_raw.get("contributions") or []),
                            "weighting": vote_raw.get("weighting"),
                            "formula": "delivery_similarity_weighted_vote",
                            "source": "delivery_similarity_weighted_vote",
                            "note": vote_raw.get("note"),
                            "_delivery_script": vote_raw.get("_script"),
                        }
                    score_source = "delivery_similarity_weighted_vote"
                    score_kind = "weighted_consensus"
                    agg_meta["target"] = target
                    agg_meta["n_transfer_priors"] = len(tprior_map)
                    agg_meta["n_donor_quality"] = len(quality_map)
                    agg_meta["min_donor_quality"] = min_donor_quality
                    missing_prior = bool(donors) and len(tprior_map) < len(
                        set(donors)
                    )
                    agg_meta["prior_missing"] = missing_prior
                    if missing_prior:
                        from nanobot.agent.tools.rbp.turn_guards import (
                            add_evidence_flag,
                        )

                        add_evidence_flag("prior_missing", True)
                else:
                    p_hat = None
                    agg_meta = {
                        "formula": "delivery_similarity_weighted_vote",
                        "source": "delivery_similarity_weighted_vote",
                        "error": "no_committed_proxies",
                    }
            except Exception as exc:
                p_hat = None
                agg_meta = {
                    "formula": "delivery_similarity_weighted_vote",
                    "source": "delivery_similarity_weighted_vote",
                    "error": f"{type(exc).__name__}: {exc}",
                }
        else:
            p_hat = None
            agg_meta = {
                "error": (
                    f"aggregate={req_agg!r} is diagnostic-only for multiple donors; "
                    "authoritative transfer p_hat requires aggregate='weighted'"
                ),
                "diagnostic": (
                    sum(float(x) for x in probs) / len(probs)
                    if req_agg == "mean"
                    else max(float(x) for x in probs)
                ),
            }

        try:
            from nanobot.agent.tools.rbp.turn_guards import (
                canonical_request,
                evidence_records,
                set_authoritative_score,
            )

            if p_hat is not None:
                try:
                    from app.core.runtime_config import apply_logit_scale

                    p_hat = float(apply_logit_scale(float(p_hat)))
                except Exception:
                    pass

            set_authoritative_score(
                p_hat,
                source=score_source,
                mode=path,
                score_kind=score_kind,
                provenance={
                    "cohort": out.get("cohort"),
                    "predictions": preds,
                    "aggregation": agg_meta,
                    "canonical_request": canonical_request(),
                    "evidence_records": evidence_records(),
                    "score_kind": score_kind,
                    "near_match_promoted": near_match_promoted,
                    "near_match_donor": near_match_donor,
                },
            )
        except Exception:
            pass

        if path == "own_head":
            if near_match_promoted:
                stop_hint = (
                    "NEAR-MATCH OWN-HEAD success: catalogue head used as own-head "
                    f"(donor={near_match_donor}); disclose near_match in explanation, "
                    "emit JSON verdict now. Do NOT continue multi-donor transfer."
                )
            else:
                stop_hint = (
                    "OWN-HEAD success: map predictions[0].prob → p_hat/label, "
                    "emit JSON verdict now. Do NOT call transfer/similarity/domain."
                )
        elif req_agg == "weighted":
            near_disclosure = ""
            try:
                from nanobot.agent.tools.rbp.turn_guards import evidence_flags

                flags = evidence_flags() or {}
                if force_transfer and flags.get("near_match"):
                    donor = flags.get("near_match_donor")
                    near_disclosure = (
                        f" Near-match to {donor!r} detected; disclose in caveats "
                        "(force_transfer kept multi_head path)."
                    )
            except Exception:
                near_disclosure = ""
            stop_hint = (
                "Multi-head: p_hat is multi-donor weighted consensus "
                "(s_i × transfer_prior × donor_quality × prob), not a calibrated "
                f"binding probability; continue Stage 3 explanation.{near_disclosure}"
            )
        else:
            stop_hint = "Multi-head: continue Stage 3 integrate if proxies."

        result = dumps(
            ok(
                {
                    "predictions": preds,
                    "cohort": out.get("cohort"),
                    "n_windows": out.get("n_windows"),
                    "path": path,
                    "prob": p_hat,
                    "aggregate": req_agg,
                    "aggregation": agg_meta,
                    "score_kind": score_kind,
                    "near_match_promoted": near_match_promoted,
                    "stop_hint": stop_hint,
                    "_delivery_script": out.get("_script"),
                },
                ms,
            )
        )
        # F2: surface low head-coverage on the transfer path. When donors were
        # requested but some had no cohort head (prob=null), the abstain gate
        # (which only sees retrieval similarity) can still pass — flag it so the
        # verdict forces low confidence and lists it as a caveat.
        if path == "multi_head":
            n_requested = len(rbps_list)
            n_with_head = len(probs)
            n_no_head = n_requested - n_with_head
            if n_no_head > 0 and n_requested > 0:
                coverage = n_with_head / n_requested
                try:
                    from nanobot.agent.tools.rbp.turn_guards import add_evidence_flag

                    add_evidence_flag("low_head_coverage", coverage)
                except Exception:
                    pass
        if path == "own_head":
            try:
                from nanobot.agent.tools.rbp.turn_guards import mark_own_head_success

                mark_own_head_success()
            except Exception:
                pass
        PredictInteractionTool._cache[key] = result
        return result
