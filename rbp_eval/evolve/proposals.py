# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Any, Optional

# map modality → curated / delivery tool names
MODALITY_TO_TOOL = {
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


def _normalize_tool_key(t: str) -> str:
    return {
        "domain": "domain_architecture",
        "esm_similarity": "seq_similarity",
        "struct_similarity_foldseek": "struct_similarity",
        "protein_seq_similarity": "seq_similarity",
    }.get(t, t)


def _breakdown_mass(entry: dict[str, Any]) -> dict[str, float]:
    """Allocate one supporting_rbp's mass across tools via similarity_breakdown."""
    try:
        sim = float(entry.get("similarity_score") or 0.0)
    except (TypeError, ValueError):
        sim = 0.0
    try:
        raw_prob = entry.get("prob")
        prob = float(raw_prob) if raw_prob is not None else 1.0
    except (TypeError, ValueError):
        prob = 1.0
    donor_mass = max(sim, 0.0) * max(prob, 0.0)
    if donor_mass <= 0:
        return {}

    br = entry.get("similarity_breakdown") or entry.get("sim_by_modality") or {}
    if isinstance(br, dict) and br:
        weights: dict[str, float] = {}
        for mod, sc in br.items():
            try:
                w = max(float(sc), 0.0)
            except (TypeError, ValueError):
                w = 0.0
            tool = MODALITY_TO_TOOL.get(str(mod))
            if tool and w > 0:
                weights[tool] = weights.get(tool, 0.0) + w
        total = sum(weights.values()) or 1.0
        return {t: donor_mass * (w / total) for t, w in weights.items()}

    # Fallback: fuse tool only (no even split across all retrieval tools)
    return {"fuse_similarity_views": donor_mass}


def tool_attribution(
    results: list[dict[str, Any]],
    *,
    min_support_fraction: float = 0.05,
) -> dict[str, Any]:
    """
    Recover which evidence channels / tools supported successful verdicts.

    Proposal §7.2: allocate ``supporting_rbps`` mass via similarity_breakdown /
    evidence_table modalities — not uniform split over retrieval.*.ok tools.
    """
    modality_counts: dict[str, float] = {}
    tool_counts: dict[str, float] = {}
    support_tool_mass: dict[str, float] = {}
    n = 0
    n_with_support = 0
    n_success = 0

    for r in results:
        n += 1
        et = r.get("evidence_table") or []
        ret = r.get("retrieval") or {}
        verdict = r.get("verdict") or {}
        supporting = verdict.get("supporting_rbps") or []
        p_hat = verdict.get("p_hat")
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

        for row in et:
            if not isinstance(row, dict):
                continue
            sims = row.get("sim_by_modality") or row.get("similarity_breakdown") or {}
            for mod, sc in sims.items():
                try:
                    w = float(sc)
                except (TypeError, ValueError):
                    w = 0.0
                modality_counts[str(mod)] = modality_counts.get(str(mod), 0.0) + max(w, 0.0)
                tname = MODALITY_TO_TOOL.get(str(mod))
                if tname and success:
                    support_tool_mass[tname] = support_tool_mass.get(tname, 0.0) + max(w, 0.0)

        if success and supporting:
            for s in supporting:
                if not isinstance(s, dict):
                    continue
                for tool, mass in _breakdown_mass(s).items():
                    support_tool_mass[tool] = support_tool_mass.get(tool, 0.0) + mass

        for tname, meta in ret.items():
            if isinstance(meta, dict) and meta.get("ok"):
                tool_counts[_normalize_tool_key(tname)] = (
                    tool_counts.get(_normalize_tool_key(tname), 0.0) + 1.0
                )

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

        for t in r.get("tools_used") or []:
            if isinstance(t, str):
                tool_counts[_normalize_tool_key(t)] = (
                    tool_counts.get(_normalize_tool_key(t), 0.0) + 0.25
                )

    mod_sum = sum(modality_counts.values()) or 1.0
    tool_sum = sum(tool_counts.values()) or 1.0
    support_sum = sum(support_tool_mass.values()) or 1.0
    mod_frac = {k: round(v / mod_sum, 4) for k, v in sorted(modality_counts.items())}
    tool_frac = {k: round(v / tool_sum, 4) for k, v in sorted(tool_counts.items())}
    support_frac = {
        k: round(v / support_sum, 4) for k, v in sorted(support_tool_mass.items())
    }

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
        "soft_disabled_suggestions": list(retire),
        "note": (
            "Low-attribution tools are soft-disable suggestions only; "
            "human review required. Never auto-edit delivery."
        ),
    }


def _cluster_failure_embeddings(
    failure_aliases: list[str],
    *,
    k: int = 3,
) -> list[dict[str, Any]]:
    """Cluster failed target aliases by sequence embedding (best-effort)."""
    if len(failure_aliases) < 2:
        return []
    try:
        import numpy as np
        from nanobot.agent.tools.rbp.common import load_catalogue_sequence
    except Exception:
        return []

    vecs: list[list[float]] = []
    kept: list[str] = []
    for alias in failure_aliases:
        seq = load_catalogue_sequence(alias) or ""
        if len(seq) < 20:
            continue
        # Cheap hash embedding when ESM service unavailable (deterministic)
        # Prefer real ESM if DeliveryToolClient works.
        emb: Optional[list[float]] = None
        try:
            import os
            from app.backends.delivery.client import DeliveryToolClient

            cli = DeliveryToolClient(offline=False, use_conda=True, device="cpu")
            out = cli.call(
                "esm_embed",
                {
                    "sequence": seq[:1024],
                    "encoder": "esmc",
                    "device": os.environ.get("RHOBIND_DEVICE", "cpu"),
                },
            )
            raw = out.get("embedding") or out.get("vector") or out.get("mean_embedding")
            if isinstance(raw, list) and raw:
                emb = [float(x) for x in raw]
        except Exception:
            emb = None
        if emb is None:
            # bag-of-AA 20-d fallback
            aa = "ACDEFGHIKLMNPQRSTVWY"
            counts = [seq.count(a) / max(len(seq), 1) for a in aa]
            emb = counts
        vecs.append(emb)
        kept.append(alias)

    if len(kept) < 2:
        return []

    # Pad / truncate to common dim
    dim = max(len(v) for v in vecs)
    mat = np.array([v + [0.0] * (dim - len(v)) for v in vecs], dtype=float)
    kk = max(1, min(k, len(kept)))
    # Simple k-means
    rng = np.random.default_rng(42)
    centers = mat[rng.choice(len(mat), size=kk, replace=False)]
    labels = np.zeros(len(mat), dtype=int)
    for _ in range(15):
        d = ((mat[:, None, :] - centers[None, :, :]) ** 2).sum(axis=2)
        labels = d.argmin(axis=1)
        for i in range(kk):
            members = mat[labels == i]
            if len(members):
                centers[i] = members.mean(axis=0)
    clusters = []
    for i in range(kk):
        members = [kept[j] for j in range(len(kept)) if int(labels[j]) == i]
        if members:
            clusters.append({"cluster_id": i, "n": len(members), "aliases": members})
    return clusters


def propose_toolkit_expansions(
    results: list[dict[str, Any]],
    *,
    attribution: Optional[dict[str, Any]] = None,
) -> list[dict[str, Any]]:
    """Cluster failure modes → human-reviewable toolkit proposals (§7.4)."""
    proposals: list[dict[str, Any]] = []
    n_ood = 0
    n_no_donors = 0
    n_no_pred = 0
    n_struct_fail = 0
    n_emb_fail = 0
    n_null_phat = 0
    failure_reasons: dict[str, int] = {}
    failure_aliases: list[str] = []

    for r in results:
        abstain = r.get("abstain") or {}
        if abstain.get("confident") is False:
            n_ood += 1
        donors = r.get("donors") or []
        if not donors and r.get("mode") == "transfer":
            n_no_donors += 1
        preds = r.get("predictions") or []
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
        q = r.get("query") or {}
        alias = None
        if isinstance(q, dict):
            alias = q.get("alias") or q.get("query")
        elif isinstance(q, str):
            alias = q
        alias = alias or r.get("alias")
        failed = (
            (verdict.get("p_hat") is None and r.get("mode") != "retrieval_only")
            or abstain.get("confident") is False
            or (not donors and r.get("mode") == "transfer")
        )
        if failed and alias:
            failure_aliases.append(str(alias))
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
    emb_clusters = _cluster_failure_embeddings(sorted(set(failure_aliases)))
    if emb_clusters:
        proposals.append(
            {
                "id": "query_embedding_failure_clusters",
                "priority": "high",
                "failure_mode": "embedding_clustered_failures",
                "fraction": round(len(set(failure_aliases)) / n, 3),
                "clusters": emb_clusters,
                "proposal": (
                    "Failures clustered by target-sequence embedding. "
                    "Review each cluster for shared domain/motif gaps; "
                    "consider RNAcompete motifs or PPI neighbours per cluster. "
                    "Human review required — do not auto-install tools."
                ),
                "human_review": True,
            }
        )
    if n_null_phat / n >= 0.3:
        top_reason = (
            max(failure_reasons, key=lambda k: failure_reasons[k])
            if failure_reasons
            else "p_hat_null"
        )
        proposals.append(
            {
                "id": "cluster_null_phat",
                "priority": "high",
                "failure_mode": top_reason,
                "fraction": round(n_null_phat / n, 3),
                "cluster_counts": failure_reasons,
                "proposal": (
                    "Systematic null p_hat cluster. If predict_oom_kill: raise cgroup RAM. "
                    "If prior_missing dominates: expand agent-side LOO matrix "
                    "(nanobot-bio expand-loo-matrix) then re-run evolve / loo-matrix-ab. "
                    "Do not auto-edit delivery."
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

