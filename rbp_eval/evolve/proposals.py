# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Any, Optional

def tool_attribution(
    results: list[dict[str, Any]],
    *,
    min_support_fraction: float = 0.05,
) -> dict[str, Any]:
    """
    Recover which evidence channels / tools supported correct (or any) verdicts.

    Uses:
      - supporting_rbps similarity/prob mass on successful (numeric p_hat) queries
      - evidence_table[].sim_by_modality keys
      - retrieval.* ok flags
    """
    modality_counts: dict[str, float] = {}
    tool_counts: dict[str, float] = {}
    support_tool_mass: dict[str, float] = {}
    n = 0
    n_with_support = 0
    n_success = 0

    # map modality → curated / delivery tool names
    modality_to_tool = {
        "esmc_cosine": "seq_similarity",
        "esm2_cosine": "seq_similarity",
        "saprot_cosine": "seq_similarity",
        "domain_jaccard": "domain_architecture",
        "domain_overlap": "domain_architecture",
        "seq_identity": "seq_similarity",
        "tm_score": "struct_similarity",
        "lddt": "struct_similarity",
        "fident": "struct_similarity",
        "function_similarity": "get_func_annotation",
        "rna_embed": "rna_blastn",
        "rna_fm": "rna_blastn",
        "fused": "fuse_similarity_views",
    }

    for r in results:
        n += 1
        et = r.get("evidence_table") or []
        ret = r.get("retrieval") or {}
        verdict = r.get("verdict") or {}
        supporting = verdict.get("supporting_rbps") or []
        p_hat = verdict.get("p_hat")
        success = p_hat is not None and not (
            r.get("mode") == "retrieval_only" and p_hat is None
        )
        # retrieval_only stubs never count as "success"
        if r.get("mode") == "retrieval_only":
            success = False
        else:
            try:
                success = p_hat is not None and float(p_hat) == float(p_hat)
            except (TypeError, ValueError):
                success = False
        if success:
            n_success += 1

        if supporting or et:
            n_with_support += 1

        # modality mass from evidence table
        for row in et:
            sims = row.get("sim_by_modality") or {}
            for mod, sc in sims.items():
                try:
                    w = float(sc)
                except (TypeError, ValueError):
                    w = 1.0
                modality_counts[mod] = modality_counts.get(mod, 0.0) + max(w, 0.0)
                tname = modality_to_tool.get(str(mod))
                if tname and success:
                    support_tool_mass[tname] = support_tool_mass.get(tname, 0.0) + max(w, 0.0)

        # supporting_rbps quality mass
        if success and supporting:
            masses = []
            for s in supporting:
                if not isinstance(s, dict):
                    continue
                try:
                    sim = float(s.get("similarity_score") or 0.0)
                except (TypeError, ValueError):
                    sim = 0.0
                try:
                    prob = float(s.get("prob")) if s.get("prob") is not None else None
                except (TypeError, ValueError):
                    prob = None
                masses.append(max(sim, 0.0) * (prob if prob is not None else 1.0))
            total = sum(masses) or 1.0
            # attribute evenly across retrieval tools that succeeded this query
            active_tools = [
                t
                for t, meta in ret.items()
                if isinstance(meta, dict) and meta.get("ok")
            ]
            if not active_tools:
                active_tools = ["supporting_rbps"]
            share = (sum(masses) / total) / max(len(active_tools), 1)
            for t in active_tools:
                # normalize tool key names
                key = {
                    "domain": "domain_architecture",
                    "esm_similarity": "seq_similarity",
                    "struct_similarity_foldseek": "struct_similarity",
                }.get(t, t)
                support_tool_mass[key] = support_tool_mass.get(key, 0.0) + share

        # tool success counts
        for tname, meta in ret.items():
            if isinstance(meta, dict) and meta.get("ok"):
                tool_counts[tname] = tool_counts.get(tname, 0.0) + 1.0
            elif isinstance(meta, dict) and meta.get("error"):
                tool_counts[tname] = tool_counts.get(tname, 0.0)  # explicit 0 bump skip

        # integration tools used
        integ = r.get("integration") or {}
        if integ.get("contributions") is not None:
            tool_counts["similarity_weighted_vote"] = (
                tool_counts.get("similarity_weighted_vote", 0.0) + 1.0
            )
        if integ.get("transfer_priors"):
            tool_counts["transfer_prior_lookup"] = (
                tool_counts.get("transfer_prior_lookup", 0.0) + 1.0
            )
        if integ.get("donor_quality"):
            tool_counts["donor_quality_prior"] = (
                tool_counts.get("donor_quality_prior", 0.0) + 1.0
            )

        # timeline tools from agent traces embedded in result
        for t in r.get("tools_used") or []:
            if isinstance(t, str):
                tool_counts[t] = tool_counts.get(t, 0.0) + 0.25

    # normalize
    mod_sum = sum(modality_counts.values()) or 1.0
    tool_sum = sum(tool_counts.values()) or 1.0
    support_sum = sum(support_tool_mass.values()) or 1.0
    mod_frac = {k: round(v / mod_sum, 4) for k, v in sorted(modality_counts.items())}
    tool_frac = {k: round(v / tool_sum, 4) for k, v in sorted(tool_counts.items())}
    support_frac = {
        k: round(v / support_sum, 4) for k, v in sorted(support_tool_mass.items())
    }

    # retirement candidates: tools registered in retrieval but low fraction
    retire_src = support_frac if support_frac else tool_frac
    retire = [
        t
        for t, f in retire_src.items()
        if f < min_support_fraction and t not in ("resolve_rbp", "lookup_proxy_cache")
    ]

    return {
        "n_results": n,
        "n_with_support": n_with_support,
        "n_success": n_success,
        "modality_mass": mod_frac,
        "tool_success_fraction": tool_frac,
        "supporting_evidence_fraction": support_frac,
        "retirement_candidates": retire,
        "note": (
            "Low-attribution tools are candidates for retirement or skill demotion; "
            "human review required before removing from registry. "
            "Never auto-edit delivery."
        ),
    }


def propose_toolkit_expansions(
    results: list[dict[str, Any]],
    *,
    attribution: Optional[dict[str, Any]] = None,
) -> list[dict[str, Any]]:
    """Cluster failure modes → human-reviewable toolkit proposals."""
    proposals: list[dict[str, Any]] = []
    n_ood = 0
    n_no_donors = 0
    n_no_pred = 0
    n_struct_fail = 0
    n_emb_fail = 0
    n_null_phat = 0
    failure_reasons: dict[str, int] = {}

    for r in results:
        abstain = r.get("abstain") or {}
        if abstain.get("confident") is False:
            n_ood += 1
        donors = r.get("donors") or []
        if not donors and r.get("mode") == "transfer":
            n_no_donors += 1
        preds = r.get("predictions") or []
        # retrieval_only stubs intentionally omit predictions
        if donors and not preds and r.get("mode") in ("transfer", "nanobot_llm"):
            n_no_pred += 1
        ret = r.get("retrieval") or {}
        if ret.get("struct_similarity_foldseek", {}).get("error") or ret.get(
            "structure_fetch", {}
        ).get("error"):
            n_struct_fail += 1
        if ret.get("esm_similarity", {}).get("error"):
            n_emb_fail += 1
        verdict = r.get("verdict") or {}
        if verdict.get("p_hat") is None and r.get("mode") != "retrieval_only":
            n_null_phat += 1
            expl = str(verdict.get("explanation") or "")
            reason = "p_hat_null"
            if "rc=-9" in expl or "OOM" in expl or "killed" in expl.lower():
                reason = "predict_oom_kill"
            elif "prior_missing" in expl or verdict.get("prior_missing"):
                reason = "prior_missing"
            elif "structure" in expl.lower() and "unavail" in expl.lower():
                reason = "structure_unavailable"
            failure_reasons[reason] = failure_reasons.get(reason, 0) + 1

    n = max(len(results), 1)
    if n_null_phat / n >= 0.3:
        top_reason = max(failure_reasons, key=failure_reasons.get) if failure_reasons else "p_hat_null"
        proposals.append(
            {
                "id": "cluster_null_phat",
                "priority": "high",
                "failure_mode": top_reason,
                "fraction": round(n_null_phat / n, 3),
                "cluster_counts": failure_reasons,
                "proposal": (
                    "Systematic null p_hat cluster. If predict_oom_kill: raise cgroup RAM. "
                    "If prior_missing dominates: consider broader LOO coverage (delivery-side, "
                    "human-owned). Do not auto-edit delivery."
                ),
                "human_review": True,
            }
        )
    if n_ood / n >= 0.3:
        proposals.append(
            {
                "id": "motif_or_rnacompete",
                "priority": "high",
                "failure_mode": "high_ood_rate",
                "fraction": round(n_ood / n, 3),
                "proposal": (
                    "Add RNAcompete / motif-similarity tool for remote homologs "
                    "when embedding OOD abstain fires."
                ),
                "human_review": True,
            }
        )
    if n_no_donors / n >= 0.2:
        proposals.append(
            {
                "id": "ppi_network",
                "priority": "medium",
                "failure_mode": "no_donors",
                "fraction": round(n_no_donors / n, 3),
                "proposal": (
                    "Add protein–protein interaction network neighbours as "
                    "fallback donor candidates when multi-view retrieval is empty."
                ),
                "human_review": True,
            }
        )
    if n_emb_fail / n >= 0.3:
        proposals.append(
            {
                "id": "embedding_env",
                "priority": "ops",
                "failure_mode": "esm_unavailable",
                "fraction": round(n_emb_fail / n, 3),
                "proposal": (
                    "Ops: ensure protein_embed conda + GPU; not a new scientific tool."
                ),
                "human_review": True,
            }
        )
    if n_struct_fail / n >= 0.3:
        proposals.append(
            {
                "id": "structure_cache",
                "priority": "medium",
                "failure_mode": "structure_fail",
                "fraction": round(n_struct_fail / n, 3),
                "proposal": (
                    "Pre-cache AF3/AFDB for catalogue; enlarge foldseek DB coverage."
                ),
                "human_review": True,
            }
        )
    if n_no_pred / n >= 0.2:
        proposals.append(
            {
                "id": "rhobind_env",
                "priority": "ops",
                "failure_mode": "predict_fail",
                "fraction": round(n_no_pred / n, 3),
                "proposal": "Ops: rhobind conda + checkpoints; donors had no predictions.",
                "human_review": True,
            }
        )

    attr = attribution or {}
    for t in attr.get("retirement_candidates") or []:
        proposals.append(
            {
                "id": f"retire_{t}",
                "priority": "low",
                "failure_mode": "low_attribution",
                "proposal": f"Consider demoting or retiring tool `{t}` after human review.",
                "human_review": True,
            }
        )

    if not proposals:
        proposals.append(
            {
                "id": "none",
                "priority": "info",
                "failure_mode": "none_dominant",
                "proposal": "No systematic failure cluster above thresholds.",
                "human_review": False,
            }
        )
    return proposals

