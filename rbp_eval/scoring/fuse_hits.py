"""Retrieval fusion helpers: multi-axis RbpHit merge, Stage-1 proxies, Stage-3 aggregation."""

from __future__ import annotations

from typing import Any, Optional


DEFAULT_WEIGHTS = {
    "esmc_cosine": 1.0,
    "esm2_cosine": 0.5,
    "domain_jaccard": 0.6,
    "domain_overlap": 0.6,
    "seq_identity": 0.3,
    "tm_score": 0.3,
    "lddt": 0.3,
    "fident": 0.2,
    "saprot_cosine": 0.0,
    "function_similarity": 0.4,
    # Collected when PEAKS_DB is ready, but promoted into fusion only after a
    # held-out ablation; the current certified policy keeps this at zero.
    "rna_peak_homology": 0.0,
}


def _rank_normalize(scores: dict[str, float]) -> dict[str, float]:
    """Per-metric rank normalize to (0,1] across aliases."""
    if not scores:
        return {}
    ordered = sorted(scores.items(), key=lambda x: x[1])
    n = len(ordered)
    out = {}
    for i, (alias, _s) in enumerate(ordered):
        out[alias] = (i + 1) / n
    return out


def _minmax_normalize(scores: dict[str, float]) -> dict[str, float]:
    """Per-metric min–max scale to [0,1] across aliases (cross-metric equalizer).

    Delivery caveat §9: retrieval scores are all [0,1] similarities but *different
    metrics live on different scales* (e.g. ESM-C cosine clusters near 0.85–0.95
    while TM-score/seq-identity span 0.2–0.9). Averaging their raw values across
    metrics lets the narrow, high-sitting metric dominate. Min–max per metric
    column makes each metric's spread comparable before fusion. Degenerate
    columns (all-equal) map to 1.0 so a unanimous metric still counts.
    """
    if not scores:
        return {}
    vals = list(scores.values())
    lo, hi = min(vals), max(vals)
    if hi - lo <= 1e-12:
        return {a: 1.0 for a in scores}
    return {a: (v - lo) / (hi - lo) for a, v in scores.items()}


# Metric → proposal Stage-1 view buckets (evidence for LLM Checkpoint 1).
_SEQ_METRICS = frozenset(
    {
        "esmc_cosine",
        "esm2_cosine",
        "seq_identity",
        "pident",
        "phmmer_evalue",
        "rna_peak_homology",
    }
)
_STRUCT_METRICS = frozenset({"tm_score", "lddt", "fident", "alntmscore"})
_FUNC_METRICS = frozenset(
    {"domain_jaccard", "domain_overlap", "function_similarity"}
)


def proposal_breakdown(sim_by_modality: dict[str, Any]) -> dict[str, float]:
    """Collapse per-metric scores into proposal ``{seq, struct, func}``."""
    buckets: dict[str, list[float]] = {"seq": [], "struct": [], "func": []}
    for k, v in (sim_by_modality or {}).items():
        try:
            score = float(v)
        except (TypeError, ValueError):
            continue
        key = str(k).lower()
        if key in _SEQ_METRICS or key in ("seq", "sequence"):
            buckets["seq"].append(score)
        elif key in _STRUCT_METRICS or key in ("struct", "structure"):
            buckets["struct"].append(score)
        elif key in _FUNC_METRICS or key in ("func", "function"):
            buckets["func"].append(score)
    return {k: round(max(vals), 4) for k, vals in buckets.items() if vals}


def fuse_rbp_hits(
    hit_lists: list[list[dict[str, Any]]],
    *,
    weights: Optional[dict[str, float]] = None,
    top_k: int = 5,
    exclude_aliases: Optional[set[str]] = None,
    allowed_aliases: Optional[set[str]] = None,
    use_rank_normalize: bool = True,
    cross_metric_normalize: bool = True,
    tau_drop: Optional[float] = None,
) -> list[dict[str, Any]]:
    """Merge RbpHit[] lists into ranked donors with fused and vote scores.

    If ``tau_drop`` is set (Stage 1 floor), drop donors with fused
    score below that threshold before applying ``top_k``.

    ``score`` is a normalized multi-view ranking score. ``vote_similarity`` is
    the biologically interpretable score used downstream: raw ESM-C cosine when
    present, otherwise a raw weighted average over the full set of active
    metrics. Missing modalities count as zero in both multi-view denominators,
    preventing a weak single-axis leader from being promoted to 1.0.

    ``cross_metric_normalize`` (delivery caveat §9) min–max scales each metric
    column to a common [0,1] spread for ranking only. Single-metric fusion keeps
    its raw scale.
    """
    wmap = {**DEFAULT_WEIGHTS, **(weights or {})}
    # Honesty: rna_blastn fusion only when peaks DB is present (delivery registry).
    try:
        from app.core.capability_matrix import rna_blastn_status

        if rna_blastn_status().get("status") != "ready":
            wmap["rna_peak_homology"] = 0.0
    except Exception:
        wmap["rna_peak_homology"] = 0.0
    # Legacy config keys (pre-alignment) must not pollute fusion.
    wmap.pop("rna_embed", None)
    wmap.pop("rna_fm", None)
    exclude_aliases = {str(alias).casefold() for alias in (exclude_aliases or set())}
    allowed_aliases_folded = (
        {str(alias).casefold() for alias in allowed_aliases}
        if allowed_aliases is not None
        else None
    )
    acc: dict[str, dict[str, Any]] = {}
    for hits in hit_lists:
        for h in hits or []:
            alias = h.get("alias")
            if not alias or str(alias).casefold() in exclude_aliases:
                continue
            if (
                allowed_aliases_folded is not None
                and str(alias).casefold() not in allowed_aliases_folded
            ):
                continue
            metric = str(h.get("metric") or "unknown")
            score = float(h.get("score") or 0.0)
            # Normalize percent-scale identity (0–100) to [0,1] before clamp
            if score > 1.0 + 1e-9 and (
                "identity" in metric.lower()
                or metric in ("seq_identity", "fident", "pident")
            ):
                score = score / 100.0
            score = max(0.0, min(1.0, score))
            slot = acc.setdefault(
                alias,
                {"alias": alias, "uniprot": h.get("uniprot") or "", "metrics": {}},
            )
            if h.get("uniprot"):
                slot["uniprot"] = h["uniprot"]
            prev = slot["metrics"].get(metric)
            if prev is None or score > prev:
                slot["metrics"][metric] = score

    if not acc:
        return []

    metrics_present: set[str] = set()
    for slot in acc.values():
        metrics_present |= set(slot["metrics"].keys())

    # Cross-metric scaling only matters when fusing ≥2 different metrics.
    apply_cross = cross_metric_normalize and len(metrics_present) > 1

    normed: dict[str, dict[str, float]] = {a: {} for a in acc}
    for m in metrics_present:
        col = {a: slot["metrics"][m] for a, slot in acc.items() if m in slot["metrics"]}
        # §9: put each metric on a common [0,1] spread before it is weighted in.
        base = _minmax_normalize(col) if apply_cross and len(col) > 1 else dict(col)
        if use_rank_normalize and len(col) > 1:
            rn = _rank_normalize(col)
            for a in col:
                normed[a][m] = 0.5 * base[a] + 0.5 * rn[a]
        else:
            for a in col:
                normed[a][m] = base[a]

    active_metrics = [
        m for m in metrics_present if float(wmap.get(m, 0.2)) > 0
    ]
    full_den = sum(float(wmap.get(m, 0.2)) for m in active_metrics)

    fused: list[dict[str, Any]] = []
    for alias, slot in acc.items():
        metrics = normed.get(alias) or {}
        raw_metrics = slot.get("metrics") or {}
        if not any(m in raw_metrics for m in active_metrics):
            # Evidence-only / zero-weight modalities must not create donors.
            continue
        num = 0.0
        for m in active_metrics:
            w = float(wmap.get(m, 0.2))
            num += w * float(metrics.get(m, 0.0))
        if full_den <= 0:
            continue
        fused_score = num / full_den
        if raw_metrics.get("esmc_cosine") is not None:
            vote_similarity = float(raw_metrics["esmc_cosine"])
            vote_similarity_source = "raw_esmc_cosine"
        else:
            raw_num = sum(
                float(wmap.get(m, 0.2)) * float(raw_metrics.get(m, 0.0))
                for m in active_metrics
            )
            vote_similarity = raw_num / full_den
            vote_similarity_source = "raw_full_coverage_weighted"
        sim_raw = {
            k: round(v, 4) for k, v in raw_metrics.items()
        }
        fused.append(
            {
                "alias": alias,
                "uniprot": slot.get("uniprot") or "",
                "score": round(fused_score, 4),
                "fused_score": round(fused_score, 4),
                "vote_similarity": round(vote_similarity, 4),
                "vote_similarity_source": vote_similarity_source,
                "metric": "fused",
                "rank": 0,
                "sim_by_modality": sim_raw,
                "sim_normalized": {k: round(v, 4) for k, v in metrics.items()},
                # Evidence shape for LLM Checkpoint 1 (not authoritative s_i).
                "similarity_breakdown": proposal_breakdown(sim_raw),
            }
        )
    fused.sort(key=lambda x: x["score"], reverse=True)
    eligible = (
        [r for r in fused if float(r.get("score") or 0) >= float(tau_drop)]
        if tau_drop is not None
        else list(fused)
    )
    # Delivery declares hits_emb the best signal. Reserve up to three slots for
    # raw ESM-C neighbours that clear the biological similarity floor, then fill
    # remaining slots by fused ranking.
    esm_seeds = sorted(
        (
            r
            for r in fused
            if r.get("sim_by_modality", {}).get("esmc_cosine") is not None
            and (
                tau_drop is None
                or float(r["sim_by_modality"]["esmc_cosine"]) >= float(tau_drop)
            )
        ),
        key=lambda r: float(r["sim_by_modality"]["esmc_cosine"]),
        reverse=True,
    )[: min(3, top_k)]
    seed_aliases = {str(r["alias"]).casefold() for r in esm_seeds}
    selected = list(esm_seeds)
    selected.extend(
        r
        for r in eligible
        if str(r["alias"]).casefold() not in seed_aliases
    )
    selected = selected[:top_k]
    selected.sort(key=lambda x: x["score"], reverse=True)
    for i, row in enumerate(selected, start=1):
        row["rank"] = i
    return selected


def fuse_proxy_candidates(
    views: dict[str, list[dict[str, Any]]],
    *,
    n_cand: int = 5,
    tau_drop: float = 0.30,
) -> list[dict[str, Any]]:
    """Deterministic baseline for Stage-1 LLM fusion checkpoint.

    Each output item matches the proxy schema (subset):
      rbp_id, similarity_score, similarity_breakdown, rationale
    """
    scores: dict[str, dict[str, float]] = {}
    for view, hits in views.items():
        for h in hits or []:
            rid = h.get("rbp_id") or h.get("uniprot") or h.get("alias")
            if not rid:
                continue
            raw = float(h.get("score") or h.get("similarity") or 0.0)
            if raw > 1.0 + 1e-9:
                raw = raw / 100.0
            scores.setdefault(rid, {})
            scores[rid][view] = max(0.0, min(1.0, raw))

    fused: list[dict[str, Any]] = []
    for rid, br in scores.items():
        vals = list(br.values())
        sim = sum(vals) / len(vals) if vals else 0.0
        if sim < tau_drop:
            continue
        fused.append(
            {
                "rbp_id": rid,
                "similarity_score": round(sim, 4),
                "similarity_breakdown": br,
                "rationale": f"deterministic mean over views {sorted(br)}",
            }
        )
    fused.sort(key=lambda x: x["similarity_score"], reverse=True)
    return fused[:n_cand]


def map_transfer_priors(raw: dict[str, Any] | None) -> dict[str, float]:
    """Normalize ``transfer_prior_lookup`` output to {donor: auprc}."""
    out: dict[str, float] = {}
    for item in (raw or {}).get("priors") or []:
        if not isinstance(item, dict):
            continue
        donor = item.get("donor") or item.get("alias")
        val = item.get("transfer_auprc")
        if donor is not None and val is not None:
            out[str(donor)] = float(val)
    return out


def map_donor_quality(raw: dict[str, Any] | None) -> dict[str, float]:
    """Normalize ``donor_quality_prior`` output to {donor: head_auprc}."""
    out: dict[str, float] = {}
    for item in (raw or {}).get("quality") or []:
        if not isinstance(item, dict):
            continue
        donor = item.get("donor") or item.get("alias")
        val = item.get("mt_all_auprc")
        if val is None:
            val = item.get("single_task_auprc")
        if donor is not None and val is not None:
            out[str(donor)] = float(val)
    return out


def aggregate_p_hat(
    proxies: list[dict[str, Any]],
    predictions: list[dict[str, Any]],
    *,
    transfer_priors: dict[str, float] | None = None,
    donor_quality: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Delivery ``similarity_weighted_vote`` formula (BUILD_SPEC §4).

    ``p_hat = Σ(s_i × tprior_i × quality_i × prob_i) / Σ(s_i × tprior_i × quality_i)``

    Optional priors multiply only when present and non-null (same as delivery script).
    ``s_i`` comes from committed proxy ``similarity_score``.
    """
    tprior = transfer_priors or {}
    quality = donor_quality or {}
    pred_by: dict[str, dict[str, Any]] = {}
    for p in predictions:
        if not isinstance(p, dict):
            continue
        for key in (p.get("rbp_id"), p.get("alias"), p.get("uniprot")):
            if key:
                pred_by[str(key).upper()] = p
    num = den = 0.0
    parts: list[dict[str, Any]] = []
    for px in proxies:
        rid = px.get("rbp_id") or px.get("alias")
        if not rid:
            continue
        rid_s = str(rid)
        s = float(px.get("similarity_score") or 0.0)
        pr = (
            pred_by.get(rid_s.upper())
            or pred_by.get(str(px.get("alias") or "").upper())
            or {}
        )
        prob = pr.get("prob")
        if prob is None:
            continue
        w = s
        tp = tprior.get(rid_s)
        if tp is None:
            for k, v in tprior.items():
                if str(k).upper() == rid_s.upper():
                    tp = v
                    break
        if tp is not None:
            w *= float(tp)
        q = quality.get(rid_s)
        if q is None:
            for k, v in quality.items():
                if str(k).upper() == rid_s.upper():
                    q = v
                    break
        if q is not None:
            w *= float(q)
        num += w * float(prob)
        den += w
        parts.append(
            {
                "rbp_id": rid_s,
                "s": round(s, 6),
                "prob": round(float(prob), 6),
                "transfer_prior": None if tp is None else round(float(tp), 6),
                "donor_quality": None if q is None else round(float(q), 6),
                "weight": round(w, 6),
            }
        )
    # Match delivery ``similarity_weighted_vote.run`` exactly: its public score
    # is rounded to four decimals. Keep higher precision only in term weights.
    p_hat = round(num / den, 4) if den > 0 else None
    weighting = "similarity"
    if tprior:
        weighting += " x transfer_prior"
    if quality:
        weighting += " x donor_quality"
    return {
        "p_hat": p_hat,
        "terms": parts,
        "weighting": weighting,
        "formula": "delivery_similarity_weighted_vote",
    }


def aggregate_probability(
    proxies: list[dict[str, Any]],
    predictions: list[dict[str, Any]],
    *,
    transfer_priors: dict[str, float] | None = None,
    donor_quality: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Alias for :func:`aggregate_p_hat` (delivery-aligned cross-donor aggregation)."""
    return aggregate_p_hat(
        proxies,
        predictions,
        transfer_priors=transfer_priors,
        donor_quality=donor_quality,
    )


def label_from_p_hat(
    p_hat: Optional[float],
    thresholds: Optional[dict[str, float]] = None,
) -> str:
    """Delegate to App SoT (``verdict_schema``) so label cuts stay single-sourced."""
    from app.core.verdict_schema import label_from_p_hat as _label

    return _label(p_hat, thresholds)
