# -*- coding: utf-8 -*-
from __future__ import annotations

import copy
import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml

from rbp_eval.scoring.fuse_hits import DEFAULT_WEIGHTS, fuse_rbp_hits
from rbp_eval.evolve.proxy_cache import promote_from_traces
from app.core.paths import (
    DEFAULT_EVOLVE_REPORT,
    PACKAGE_ROOT,
    PROXY_CACHE,
    ensure_artifact_dirs,
)

DEFAULT_CONFIG = PACKAGE_ROOT / "config" / "defaults.yaml"
EVOLVED_CONFIG = PACKAGE_ROOT / "config" / "evolved.yaml"
CANDIDATE_CONFIG = PACKAGE_ROOT / "config" / "evolved.candidate.yaml"
CANDIDATE_SEED = PACKAGE_ROOT / "config" / "evolved.candidate.yaml.example"
EVOLVED_REPORT = DEFAULT_EVOLVE_REPORT
ensure_artifact_dirs()


def _load_loo_matrix() -> tuple[dict[str, dict[str, Any]], dict[tuple[str, str], float]]:
    import csv

    from rbp_eval.loo.loo_eval import resolve_loo_csvs

    summary_p, metrics_p = resolve_loo_csvs()

    summary: dict[str, dict[str, Any]] = {}
    if summary_p.is_file():
        with open(summary_p, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                summary[r["held_rbp"]] = r

    matrix: dict[tuple[str, str], float] = {}
    if metrics_p.is_file():
        with open(metrics_p, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                matrix[(r["held_rbp"], r["foreign_rbp"])] = float(r["auprc"])
    return summary, matrix


def _policy_score(
    held: str,
    hit_lists: list[list[dict[str, Any]]],
    matrix: dict[tuple[str, str], float],
    weights: dict[str, float],
    top_k: int,
) -> Optional[float]:
    donors = fuse_rbp_hits(
        hit_lists,
        weights=weights,
        top_k=top_k,
        exclude_aliases={held},
        use_rank_normalize=True,
    )
    vals = []
    for d in donors:
        a = matrix.get((held, d["alias"]))
        if a is not None:
            vals.append(float(a))
    if not vals:
        return None
    # objective: mean of top-k measured transfer AUPRC (proxy for calibrated CE)
    return sum(vals) / len(vals)


def _hit_lists_from_results(
    results: list[dict[str, Any]],
) -> dict[str, list[list[dict[str, Any]]]]:
    """Best-effort: rebuild single-list hits from evidence_table for each alias target."""
    out: dict[str, list[list[dict[str, Any]]]] = {}
    for r in results:
        q = r.get("query") or {}
        if isinstance(q, str):
            held = q
        else:
            held = q.get("alias") or q.get("query")
        if not held:
            held = r.get("alias")
        if not held:
            continue
        et = r.get("evidence_table") or r.get("donors") or []
        hits = []
        for row in et:
            a = row.get("alias")
            if not a or a == held:
                continue
            hits.append(
                {
                    "alias": a,
                    "uniprot": row.get("uniprot") or "",
                    "score": float(row.get("fused_similarity") or row.get("score") or 0),
                    "metric": "fused",
                    "rank": len(hits) + 1,
                }
            )
        if hits:
            out[str(held)] = [hits]
    return out


def retune_weights(
    held_to_hit_lists: dict[str, list[list[dict[str, Any]]]],
    *,
    base_weights: Optional[dict[str, float]] = None,
    top_k: int = 5,
    grid: Optional[list[float]] = None,
) -> dict[str, Any]:
    """
    Coordinate-wise grid search over fusion weights to maximise mean LOO
    transfer AUPRC of the fused donor policy.
    """
    _, matrix = _load_loo_matrix()
    weights = {**DEFAULT_WEIGHTS, **(base_weights or {})}
    grid = grid or [0.0, 0.3, 0.6, 1.0, 1.5]

    def mean_obj(w: dict[str, float]) -> tuple[float, int]:
        scores = []
        for held, lists in held_to_hit_lists.items():
            s = _policy_score(held, lists, matrix, w, top_k)
            if s is not None:
                scores.append(s)
        if not scores:
            return 0.0, 0
        return sum(scores) / len(scores), len(scores)

    base_score, n = mean_obj(weights)
    best = dict(weights)
    best_score = base_score
    history = [{"step": "init", "score": base_score, "n": n, "weights": dict(weights)}]

    # tune keys that appear in DEFAULT_WEIGHTS and matter for offline LOO
    tune_keys = [
        "esmc_cosine",
        "domain_jaccard",
        "domain_overlap",
        "seq_identity",
        "tm_score",
        "function_similarity",
    ]
    for key in tune_keys:
        if key not in best:
            continue
        local_best_val = best.get(key, 1.0)
        local_best_score = best_score
        for g in grid:
            trial = dict(best)
            trial[key] = g
            sc, _n = mean_obj(trial)
            if sc > local_best_score + 1e-9:
                local_best_score = sc
                local_best_val = g
        if local_best_val != best.get(key):
            best[key] = local_best_val
            best_score = local_best_score
            history.append(
                {
                    "step": f"tune:{key}",
                    "score": best_score,
                    "weights": {key: local_best_val},
                }
            )

    return {
        "status": "ok",
        "objective": "mean_loo_transfer_auprc_of_fused_donors",
        "n_held": len(held_to_hit_lists),
        "baseline_score": round(base_score, 6),
        "tuned_score": round(best_score, 6),
        "improvement": round(best_score - base_score, 6),
        "base_weights": weights,
        "tuned_weights": best,
        "history": history,
    }


def retune_label_thresholds(
    scored_labels: list[dict[str, Any]],
    *,
    base: Optional[dict[str, float]] = None,
) -> dict[str, Any]:
    """
    Re-fit Strong/Likely/Unlikely thresholds on scores with binary y*.

    Each item: {p_hat: float, y: 0|1} where y is ground-truth binding.
    Minimises calibrated binary cross-entropy for the ``likely`` cut, with
    Youden's J as a secondary report. When y is unavailable, keep defaults.
    """
    base_thr = {"strong": 0.75, "likely": 0.50, "unlikely": 0.25, **(base or {})}
    pairs = [
        (float(x["p_hat"]), int(x["y"]))
        for x in scored_labels
        if x.get("p_hat") is not None and x.get("y") is not None
    ]
    if len(pairs) < 5:
        return {
            "status": "skipped",
            "reason": "need ≥5 labeled (p_hat, y) pairs",
            "thresholds": base_thr,
            "n": len(pairs),
        }

    def _ce(t: float) -> float:
        # soft label via clipped probability around threshold (calibrated CE proxy)
        eps = 1e-6
        loss = 0.0
        for p, y in pairs:
            # map distance-to-threshold into a calibrated prob
            logit_scale = 8.0
            z = max(-20.0, min(20.0, logit_scale * (p - t)))
            # sigmoid
            pred = 1.0 / (1.0 + math.exp(-z))
            pred = min(1.0 - eps, max(eps, pred))
            loss += -(y * math.log(pred) + (1 - y) * math.log(1.0 - pred))
        return loss / len(pairs)

    def _youden(t: float) -> float:
        tp = fp = tn = fn = 0
        for p, y in pairs:
            pred = 1 if p >= t else 0
            if pred == 1 and y == 1:
                tp += 1
            elif pred == 1 and y == 0:
                fp += 1
            elif pred == 0 and y == 0:
                tn += 1
            else:
                fn += 1
        sens = tp / (tp + fn) if (tp + fn) else 0.0
        spec = tn / (tn + fp) if (tn + fp) else 0.0
        return sens + spec - 1.0

    best_t = float(base_thr["likely"])
    best_ce = _ce(best_t)
    best_j = _youden(best_t)
    for t100 in range(20, 80, 2):
        t = t100 / 100.0
        ce = _ce(t)
        j = _youden(t)
        # primary: minimise CE; tie-break: higher Youden
        if ce < best_ce - 1e-9 or (abs(ce - best_ce) < 1e-9 and j > best_j):
            best_ce = ce
            best_j = j
            best_t = t

    likely = best_t
    strong = min(0.95, max(likely + 0.15, float(base_thr["strong"])))
    unlikely = max(0.05, min(likely - 0.15, float(base_thr["unlikely"])))
    # keep ordering strong > likely > unlikely
    if strong <= likely:
        strong = min(0.95, likely + 0.15)
    if unlikely >= likely:
        unlikely = max(0.05, likely - 0.15)
    thr = {"strong": round(strong, 3), "likely": round(likely, 3), "unlikely": round(unlikely, 3)}
    return {
        "status": "ok",
        "objective": "calibrated_cross_entropy",
        "thresholds": thr,
        "ce": round(best_ce, 6),
        "youden_j": round(best_j, 4),
        "n": len(pairs),
        "base": base_thr,
    }


def retune_abstain_thresholds(
    held_to_hit_lists: dict[str, list[list[dict[str, Any]]]],
    *,
    base_thresholds: Optional[dict[str, float]] = None,
    weights: Optional[dict[str, float]] = None,
    top_k: int = 5,
    abstain_rate_band: tuple[float, float] = (0.05, 0.55),
    grid: Optional[list[float]] = None,
) -> dict[str, Any]:
    """Grid-search abstain thresholds on val LOO hit lists.

    Objective: maximise mean LOO transfer AUPRC among *non-abstained* held RBPs,
    while keeping the abstain rate inside ``abstain_rate_band``.
    """
    _, matrix = _load_loo_matrix()
    try:
        from app.core.runtime_config import abstain_thresholds as _ab

        live = dict(_ab())
    except Exception:
        live = {
            "esmc_cosine": 0.55,
            "esm2_cosine": 0.55,
            "domain_jaccard": 0.5,
            "domain_overlap": 0.5,
            "seq_identity": 0.30,
            "tm_score": 0.5,
            "fused": 0.45,
            "rna_embed": 0.40,
        }
    thr0 = {**live, **(base_thresholds or {})}
    wmap = {**DEFAULT_WEIGHTS, **(weights or {})}
    grid = grid or [0.25, 0.35, 0.45, 0.55, 0.65, 0.75]
    lo, hi = abstain_rate_band
    n_held = len(held_to_hit_lists)
    if n_held == 0:
        return {
            "status": "skipped",
            "reason": "no held_to_hit_lists",
            "thresholds": thr0,
        }

    def _eval(thr: dict[str, float]) -> tuple[float, float, int]:
        scores: list[float] = []
        n_abs = 0
        for held, lists in held_to_hit_lists.items():
            donors = fuse_rbp_hits(
                lists,
                weights=wmap,
                top_k=top_k,
                exclude_aliases={held},
                use_rank_normalize=True,
            )
            if not donors:
                n_abs += 1
                continue
            best = donors[0]
            metric = str(best.get("metric") or "fused")
            t = float(thr.get(metric, thr.get("fused", 0.45)))
            if float(best.get("score") or 0.0) < t:
                n_abs += 1
                continue
            vals = []
            for d in donors:
                a = matrix.get((held, d["alias"]))
                if a is not None:
                    vals.append(float(a))
            if not vals:
                # confident but no LOO cell — skip from mean, not abstain
                continue
            scores.append(sum(vals) / len(vals))
        rate = n_abs / n_held
        mean_s = sum(scores) / len(scores) if scores else 0.0
        return mean_s, rate, len(scores)

    base_mean, base_rate, base_n = _eval(thr0)
    best = dict(thr0)
    best_mean, best_rate, best_n = base_mean, base_rate, base_n
    history = [
        {
            "step": "init",
            "mean_transfer": round(base_mean, 6),
            "abstain_rate": round(base_rate, 4),
            "n_scored": base_n,
            "thresholds": dict(thr0),
        }
    ]

    def _in_band(rate: float) -> bool:
        return lo - 1e-9 <= rate <= hi + 1e-9

    def _better(mean_s: float, rate: float, cur_mean: float, cur_rate: float) -> bool:
        in_b = _in_band(rate)
        cur_in = _in_band(cur_rate)
        if in_b and not cur_in:
            return True
        if in_b == cur_in and mean_s > cur_mean + 1e-9:
            return True
        if in_b == cur_in and abs(mean_s - cur_mean) < 1e-9:
            # prefer rate closer to mid-band
            mid = 0.5 * (lo + hi)
            return abs(rate - mid) < abs(cur_rate - mid)
        return False

    tune_keys = ["fused", "esmc_cosine", "domain_jaccard", "domain_overlap", "rna_embed"]
    for key in tune_keys:
        if key not in best:
            best[key] = float(thr0.get(key, 0.45))
        local_val = best[key]
        local_mean, local_rate = best_mean, best_rate
        for g in grid:
            trial = dict(best)
            trial[key] = float(g)
            mean_s, rate, _n = _eval(trial)
            if _better(mean_s, rate, local_mean, local_rate):
                local_mean, local_rate, local_val = mean_s, rate, float(g)
        if abs(local_val - float(best.get(key, local_val))) > 1e-12:
            best[key] = local_val
            best_mean, best_rate, best_n = _eval(best)
            history.append(
                {
                    "step": f"tune:{key}",
                    "mean_transfer": round(best_mean, 6),
                    "abstain_rate": round(best_rate, 4),
                    "n_scored": best_n,
                    "thresholds": {key: local_val},
                }
            )

    return {
        "status": "ok",
        "objective": "mean_loo_transfer_among_non_abstained",
        "abstain_rate_band": [lo, hi],
        "n_held": n_held,
        "baseline": {
            "mean_transfer": round(base_mean, 6),
            "abstain_rate": round(base_rate, 4),
            "n_scored": base_n,
        },
        "tuned": {
            "mean_transfer": round(best_mean, 6),
            "abstain_rate": round(best_rate, 4),
            "n_scored": best_n,
        },
        "improvement": round(best_mean - base_mean, 6),
        "base_thresholds": thr0,
        "tuned_thresholds": best,
        "history": history,
    }


def retune_tau_drop(
    held_to_hit_lists: dict[str, list[list[dict[str, Any]]]],
    *,
    base_tau: Optional[float] = None,
    weights: Optional[dict[str, float]] = None,
    top_k: int = 5,
    drop_rate_band: tuple[float, float] = (0.0, 0.5),
    grid: Optional[list[float]] = None,
) -> dict[str, Any]:
    """Grid-search the Stage-1 ``tau_drop`` floor on the LOO val set.

    ``tau_drop`` drops fused donors whose score is below the floor before
    predicting. Too low → noisy low-similarity donors dilute ``p_hat``; too high
    → held RBPs lose all donors (no transfer). Objective: maximise mean LOO
    transfer AUPRC of the *surviving* donors while keeping the fraction of held
    RBPs left with zero donors ("dropped") inside ``drop_rate_band``. Calibrated
    on the same held-out catalogue as the weight/abstain retunes.
    """
    _, matrix = _load_loo_matrix()
    if base_tau is None:
        try:
            from app.core.runtime_config import tau_drop as _tau

            base_tau = float(_tau())
        except Exception:
            base_tau = 0.30
    wmap = {**DEFAULT_WEIGHTS, **(weights or {})}
    grid = grid or [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6]
    n_held = len(held_to_hit_lists)
    if n_held == 0:
        return {"status": "skipped", "reason": "no held_to_hit_lists", "tau_drop": base_tau}
    lo, hi = drop_rate_band

    def _eval(tau: float) -> tuple[float, float, int]:
        scores: list[float] = []
        n_dropped = 0
        for held, lists in held_to_hit_lists.items():
            donors = fuse_rbp_hits(
                lists,
                weights=wmap,
                top_k=top_k,
                exclude_aliases={held},
                use_rank_normalize=True,
                tau_drop=tau,
            )
            if not donors:
                n_dropped += 1
                continue
            vals = [
                float(matrix[(held, d["alias"])])
                for d in donors
                if (held, d["alias"]) in matrix
            ]
            if vals:
                scores.append(sum(vals) / len(vals))
        rate = n_dropped / n_held
        mean_s = sum(scores) / len(scores) if scores else 0.0
        return mean_s, rate, len(scores)

    def _in_band(rate: float) -> bool:
        return lo - 1e-9 <= rate <= hi + 1e-9

    base_mean, base_rate, base_n = _eval(float(base_tau))
    best_tau, best_mean, best_rate, best_n = float(base_tau), base_mean, base_rate, base_n
    history = [
        {"tau": round(float(base_tau), 3), "mean_transfer": round(base_mean, 6),
         "drop_rate": round(base_rate, 4), "n_scored": base_n}
    ]
    for g in grid:
        mean_s, rate, n_scored = _eval(float(g))
        history.append(
            {"tau": round(float(g), 3), "mean_transfer": round(mean_s, 6),
             "drop_rate": round(rate, 4), "n_scored": n_scored}
        )
        in_b, cur_in = _in_band(rate), _in_band(best_rate)
        better = (
            (in_b and not cur_in)
            or (in_b == cur_in and mean_s > best_mean + 1e-9)
        )
        if better:
            best_tau, best_mean, best_rate, best_n = float(g), mean_s, rate, n_scored

    return {
        "status": "ok",
        "objective": "mean_loo_transfer_among_surviving_donors",
        "drop_rate_band": [lo, hi],
        "n_held": n_held,
        "baseline": {"tau_drop": round(float(base_tau), 3),
                     "mean_transfer": round(base_mean, 6),
                     "drop_rate": round(base_rate, 4), "n_scored": base_n},
        "tuned": {"tau_drop": round(best_tau, 3),
                  "mean_transfer": round(best_mean, 6),
                  "drop_rate": round(best_rate, 4), "n_scored": best_n},
        "improvement": round(best_mean - base_mean, 6),
        "tuned_tau_drop": round(best_tau, 3),
        "history": history,
    }

