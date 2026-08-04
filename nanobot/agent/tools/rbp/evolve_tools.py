# -*- coding: utf-8 -*-
"""Self-evolution runtime tools: proxy cache lookup + multi-view fusion."""

from __future__ import annotations

import asyncio
from typing import Any

from nanobot.agent.tools.core.base import Tool, tool_parameters

from nanobot.agent.tools.rbp.common import dumps, err, ok, timed_call


@tool_parameters(
    {
        "type": "object",
        "properties": {
            "alias": {
                "type": "string",
                "description": "Target RBP gene symbol (e.g. NSUN2).",
            },
            "uniprot": {
                "type": "string",
                "description": "Target UniProt accession.",
            },
            "min_hits": {
                "type": "integer",
                "default": 2,
                "description": "Minimum promotions before cache is trusted.",
            },
        },
        "required": [],
    }
)
class LookupProxyCacheTool(Tool):
    """Bypass Stage 1 when (p* → proxies) has been promoted."""

    _plugin_discoverable = True
    _scopes = {"core", "subagent"}

    @property
    def name(self) -> str:
        return "lookup_proxy_cache"

    @property
    def description(self) -> str:
        return (
            "Look up promoted proxy donors for an unseen RBP from the offline "
            "self-evolution cache. On hit, skip Stage 1 multi-view retrieval and "
            "predict with returned proxies. Call after resolve_rbp when in_panel=false."
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
        def _run():
            from rbp_eval.evolve.proxy_cache import lookup_proxies

            alias = (kwargs.get("alias") or "").strip() or None
            uniprot = (kwargs.get("uniprot") or "").strip() or None
            if not alias and not uniprot:
                return err("provide alias and/or uniprot")
            proxies = lookup_proxies(
                alias=alias,
                uniprot=uniprot,
                min_hits=int(kwargs.get("min_hits") or 2),
            )
            if not proxies:
                return ok(
                    {
                        "hit": False,
                        "alias": alias,
                        "uniprot": uniprot,
                        "proxies": [],
                        "stage1_bypassed": False,
                        "note": "no promoted cache entry — run Stage 1 multi-view retrieval",
                    }
                )
            return ok(
                {
                    "hit": True,
                    "alias": alias,
                    "uniprot": uniprot,
                    "proxies": proxies,
                    "n": len(proxies),
                    "stage1_bypassed": True,
                    "note": (
                        "cache hit — Stage 1 multi-view retrieve is hard-blocked; "
                        "fuse/commit with these proxies"
                    ),
                }
            )

        # A7: time the proxy-cache lookup so latency_ms is real wall-time, not 0.0.
        out, ms, error = await asyncio.to_thread(lambda: timed_call(_run))
        if error is not None:
            return dumps(err(error, ms))
        if isinstance(out, dict):
            out["latency_ms"] = round(float(ms or 0.0), 3)
            value = out.get("value") if out.get("status") == "ok" else out
            if isinstance(value, dict) and value.get("hit"):
                try:
                    from nanobot.agent.tools.rbp.turn_guards import mark_stage1_bypassed

                    mark_stage1_bypassed(list(value.get("proxies") or []))
                except Exception:
                    pass
        return dumps(out)


@tool_parameters(
    {
        "type": "object",
        "properties": {
            "hit_lists": {
                "type": "array",
                "description": (
                    "List of per-modality RbpHit lists. Preferred shape: "
                    "[[{alias,score,...}, ...], [{...}, ...]]. "
                    "Also accepted: [{hits:[...]}, {hits:[...]}] (tool unwraps)."
                ),
                "items": {
                    "anyOf": [
                        {"type": "array"},
                        {
                            "type": "object",
                            "properties": {
                                "hits": {"type": "array"},
                            },
                        },
                    ]
                },
            },
            "hits": {
                "type": "array",
                "description": "Single flat RbpHit list (wrapped as one modality).",
            },
            "top_k": {"type": "integer", "default": 5},
            "cohort": {
                "type": "string",
                "enum": ["K562", "HepG2"],
                "description": "Cohort whose RhoBind heads are eligible as donors.",
            },
            "exclude_aliases": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Aliases to exclude (usually the held/target RBP).",
            },
            "tau_drop": {
                "type": "number",
                "description": "Drop donors with fused score below this (default from config).",
            },
        },
        "required": [],
    }
)
class FuseSimilarityViewsTool(Tool):
    """Fuse multi-view hits with evolved (or default) fusion_weights."""

    _plugin_discoverable = True
    _scopes = {"core", "subagent"}

    @property
    def name(self) -> str:
        return "fuse_similarity_views"

    @property
    def description(self) -> str:
        return (
            "Fuse multi-view RbpHit lists into ranked donors using runtime "
            "fusion_weights (delivery-style: emb/seq + Foldseek structure + "
            "domain Jaccard). Auto-injects literature_cooccurrence (weight 0.1) "
            "only for peers that corroborate hard Donors_SS — never lit-only "
            "gap-fill or LLM-invented s_i. Runtime blocks fuse until structure "
            "+ domain retrieves have been attempted (or honest unavailable / "
            "domain_empty flags are set). Each donor includes an authoritative "
            "deterministic similarity_score and breakdown for Checkpoint 1. "
            "After fuse: select donors with commit_proxy_candidates (numeric "
            "scores cannot be changed), then confidence_abstain, then "
            "predict_interaction (proposal §4: fuse → commit → abstain → predict)."
        )

    @property
    def read_only(self) -> bool:
        return True

    async def execute(self, **kwargs: Any) -> str:
        try:
            from nanobot.agent.tools.rbp.turn_guards import (
                blocked_envelope_json,
                fuse_blocked_reason,
            )

            blocked = blocked_envelope_json(self.name)
            if blocked:
                return blocked
            reason = fuse_blocked_reason()
            if reason:
                return dumps(err(reason))
        except Exception:
            pass
        def _run():
            from nanobot.agent.tools.rbp.common import (
                config_source_facade as config_source,
                fusion_weights_facade as fusion_weights,
                get_runtime_config,
                tau_drop_facade as cfg_tau,
            )
            from nanobot.agent.tools.rbp.turn_guards import (
                add_evidence_flag,
                cache_proxies,
                canonical_request,
                cohort_head_aliases,
                corroborate_literature_hits_for_aliases,
                register_retrieve_donors,
                stage1_bypassed,
            )
            from rbp_eval.scoring.fuse_hits import fuse_rbp_hits

            # Remap common LLM aliases (seq_hits → hits_seq, …) before fuse.
            _alias_map = {
                "emb_hits": "hits_emb",
                "seq_hits": "hits_seq",
                "struct_hits": "hits_struct",
                "dom_hits": "hits_dom",
                "rna_hits": "hits_rna",
                "lit_hits": "hits_lit",
                "func_hits": "hits_func",
            }
            for alias, canonical in _alias_map.items():
                if kwargs.get(canonical) is None and isinstance(kwargs.get(alias), list):
                    kwargs[canonical] = kwargs[alias]

            hit_lists = kwargs.get("hit_lists")
            if not hit_lists:
                # Dual-axis convenience: hits_emb + hits_seq (+ optional others)
                axes = []
                for key in (
                    "hits_emb",
                    "hits_seq",
                    "hits_struct",
                    "hits_dom",
                    "hits_rna",
                    "hits_lit",
                    "hits_func",
                    "hits",
                ):
                    part = kwargs.get(key)
                    if isinstance(part, list) and part:
                        axes.append(part)
                if axes:
                    hit_lists = axes
                elif stage1_bypassed() and cache_proxies():
                    hit_lists = [cache_proxies()]
                else:
                    return err(
                        "provide hit_lists, or hits_emb/hits_seq(/hits_struct/…), "
                        "or aliases seq_hits/struct_hits/…, or hits"
                    )
            # LLM sometimes passes a modality dict at the top level
            if isinstance(hit_lists, dict):
                if "hits" in hit_lists and isinstance(hit_lists.get("hits"), list):
                    hit_lists = [hit_lists["hits"]]
                else:
                    hit_lists = list(hit_lists.values())
            if not isinstance(hit_lists, list):
                return err("hit_lists must be a list")
            lists: list[list] = []
            for item in hit_lists:
                if isinstance(item, list):
                    lists.append(item)
                elif isinstance(item, dict) and "hits" in item:
                    lists.append(list(item.get("hits") or []))
                elif isinstance(item, dict) and (
                    "alias" in item or "score" in item or "rbp_id" in item
                ):
                    # accidental flat list wrapped as one dict — skip noise
                    continue
            if not lists and stage1_bypassed() and cache_proxies():
                lists = [cache_proxies()]
            if not lists:
                return err(
                    "no hit lists to fuse; pass hit_lists as "
                    "[[{alias,score,...}], ...] or [{hits:[...]}, ...]"
                )

            # Register hard-retrieve aliases (Donors_SS) then corroborate lit peers.
            aliases_from_lists = {
                str(hit.get("alias") or hit.get("rbp_id") or "")
                for rows in lists
                for hit in (rows or [])
                if isinstance(hit, dict)
                and (hit.get("alias") or hit.get("rbp_id"))
                and str(hit.get("metric") or "") != "literature_cooccurrence"
            }
            register_retrieve_donors(aliases_from_lists)
            lit_hits = corroborate_literature_hits_for_aliases(aliases_from_lists)
            # Auto-inject corroborated literature soft hits only (never lit-only gap-fill).
            has_lit = any(
                isinstance(h, dict)
                and str(h.get("metric") or "") == "literature_cooccurrence"
                for lst in lists
                for h in (lst or [])
            )
            explicit_lit = kwargs.get("hits_lit")
            if isinstance(explicit_lit, list) and explicit_lit and not has_lit:
                # Accept explicit lit only for aliases already in hard Donors_SS.
                donors_up = {a.upper() for a in aliases_from_lists if a}
                filtered = [
                    h
                    for h in explicit_lit
                    if isinstance(h, dict)
                    and str(h.get("alias") or "").upper() in donors_up
                ]
                if filtered:
                    lists.append(filtered)
                    lit_hits = filtered
                    has_lit = True
            elif lit_hits and not has_lit:
                lists.append(lit_hits)
                has_lit = True

            excl = set(kwargs.get("exclude_aliases") or [])
            top_k = int(kwargs.get("top_k") or 5)
            tau = kwargs.get("tau_drop")
            tau_f = float(tau) if tau is not None else cfg_tau()
            weights = fusion_weights()
            cfg = get_runtime_config()
            canonical = canonical_request() or {}
            cohort = str(
                kwargs.get("cohort")
                or canonical.get("cohort")
                or cfg.get("cohort")
                or "K562"
            )
            integrate = cfg.get("integrate") or {}
            require_cohort_head = integrate.get("require_cohort_head", True) is not False
            allowed_aliases = (
                cohort_head_aliases(cohort) if require_cohort_head else None
            )
            aliases_seen = {
                str(hit.get("alias") or "")
                for rows in lists
                for hit in rows
                if isinstance(hit, dict) and hit.get("alias")
            }
            donors = fuse_rbp_hits(
                lists,
                weights=weights,
                top_k=top_k,
                exclude_aliases=excl,
                allowed_aliases=allowed_aliases,
                use_rank_normalize=True,
                tau_drop=tau_f,
            )
            # Lit-only peers must not gap-fill into fuse; they need seq/struct recompare.
            gap_aliases: list[str] = []
            if lit_hits:
                try:
                    add_evidence_flag("literature_corroboration", True)
                    add_evidence_flag(
                        "literature_corroboration_aliases",
                        [
                            str(h.get("alias"))
                            for h in lit_hits
                            if isinstance(h, dict) and h.get("alias")
                        ],
                    )
                except Exception:
                    pass
            # Honest multi-view provenance: which delivery axes contributed hits.
            metrics_seen: set[str] = set()
            for lst in lists:
                for h in lst or []:
                    if isinstance(h, dict) and h.get("metric"):
                        metrics_seen.add(str(h["metric"]))
            coverage = {
                "embedding": any(
                    m in metrics_seen for m in ("esmc_cosine", "esm2_cosine", "saprot_cosine")
                ),
                "sequence": any(
                    m in metrics_seen for m in ("seq_identity", "fident", "pident")
                ),
                "structure": any(
                    m in metrics_seen for m in ("tm_score", "lddt", "alntmscore")
                ),
                "domain": any(
                    m in metrics_seen for m in ("domain_overlap", "domain_jaccard")
                ),
                "function": any(
                    m in metrics_seen
                    for m in ("function_similarity", "literature_cooccurrence")
                ),
                "literature": "literature_cooccurrence" in metrics_seen,
                "rna": "rna_peak_homology" in metrics_seen,
            }
            missing = [k for k, present in coverage.items() if not present and k in (
                "embedding", "sequence", "structure", "domain"
            )]
            return ok(
                {
                    "donors": donors,
                    "hits": donors,
                    "n": len(donors),
                    "cohort": cohort,
                    "require_cohort_head": require_cohort_head,
                    "n_filtered_unheaded": (
                        len(
                            {
                                alias
                                for alias in aliases_seen
                                if alias.upper() not in (allowed_aliases or set())
                            }
                        )
                        if allowed_aliases is not None
                        else 0
                    ),
                    "weights_source": config_source(),
                    "tau_drop": tau_f,
                    "fusion_weights": weights,
                    "modality_coverage": coverage,
                    "missing_modalities": missing,
                    "metrics_present": sorted(metrics_seen),
                    "literature_injected": bool(has_lit and lit_hits),
                    "literature_gap_fill": gap_aliases,
                    "next": "commit_proxy_candidates (select deterministic s_i), then "
                    "confidence_abstain, then predict_interaction",
                }
            )

        out = await asyncio.to_thread(_run)
        try:
            parsed = out if isinstance(out, dict) else None
            # dumps path below — mark fuse when status ok
        except Exception:
            parsed = None
        result = dumps(out)
        try:
            import json as _json

            obj = _json.loads(result) if isinstance(result, str) else None
            if isinstance(obj, dict) and obj.get("status") == "ok":
                from nanobot.agent.tools.rbp.turn_guards import set_fused_proxies

                raw_value = obj.get("value")
                value = raw_value if isinstance(raw_value, dict) else {}
                set_fused_proxies(list(value.get("donors") or []))
        except Exception:
            pass
        return result
