# -*- coding: utf-8 -*-
"""Shared evaluation metrics for rbp_eval (B4: single source of truth).

Used by both ``evaluation_plan.py`` and ``loo_eval.py`` so instance-level
AUROC / AUPRC / ECE are computed identically across harnesses (A5 unifies ECE
into the LOO light report; A4 records the Stage-3 de-LLM-explanation ablation
against the same metrics).
"""

from __future__ import annotations

from typing import Any, Optional


def binary_from_four_level(label: str) -> int:
    """Collapse Strong|Likely → 1, Unlikely|No → 0."""
    return 1 if label in ("Strong", "Likely") else 0


def roc_auc(scores: list[float], labels: list[int]) -> Optional[float]:
    """Mann–Whitney AUROC; None if single class."""
    pos = [s for s, y in zip(scores, labels) if y == 1]
    neg = [s for s, y in zip(scores, labels) if y == 0]
    if not pos or not neg:
        return None
    pairs = 0
    wins = 0.0
    for p in pos:
        for n in neg:
            pairs += 1
            if p > n:
                wins += 1.0
            elif p == n:
                wins += 0.5
    return wins / pairs if pairs else None


def average_precision(scores: list[float], labels: list[int]) -> Optional[float]:
    """AUPRC via ranked precision average."""
    if not scores or sum(labels) == 0:
        return None
    order = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
    tp = 0
    ap_sum = 0.0
    n_pos = sum(labels)
    for rank, i in enumerate(order, start=1):
        if labels[i] == 1:
            tp += 1
            ap_sum += tp / rank
    return ap_sum / n_pos if n_pos else None


def expected_calibration_error(
    scores: list[float],
    labels: list[int],
    *,
    n_bins: int = 10,
) -> Optional[float]:
    """ECE on ˆp ∈ [0,1] vs binary y."""
    if len(scores) < 2 or not any(labels) or not any(1 - y for y in labels):
        if len(scores) < n_bins:
            return None
    bins: list[list[tuple[float, int]]] = [[] for _ in range(n_bins)]
    for s, y in zip(scores, labels):
        s = max(0.0, min(1.0, float(s)))
        b = min(n_bins - 1, int(s * n_bins))
        bins[b].append((s, int(y)))
    ece = 0.0
    n = len(scores)
    for bucket in bins:
        if not bucket:
            continue
        conf = sum(s for s, _ in bucket) / len(bucket)
        acc = sum(y for _, y in bucket) / len(bucket)
        ece += (len(bucket) / n) * abs(acc - conf)
    return ece


def metrics_from_pairs(pairs: list[dict[str, Any]]) -> dict[str, Any]:
    """Instance-level metrics from ``[{p_hat|score, y, label?}, ...]``.

    Returns AUROC / AUPRC / ECE when ≥5 labeled (score, y) pairs are available,
    else a ``skipped`` envelope with the reason.
    """
    scores: list[float] = []
    labels: list[int] = []
    for p in pairs:
        if p.get("p_hat") is None and p.get("score") is None:
            continue
        s = float(p.get("p_hat") if p.get("p_hat") is not None else p["score"])
        if p.get("y") is not None:
            y = int(p["y"])
        elif p.get("label"):
            y = binary_from_four_level(str(p["label"]))
        else:
            continue
        scores.append(s)
        labels.append(y)
    if len(scores) < 5:
        return {
            "status": "skipped",
            "reason": "need ≥5 labeled (score,y) pairs",
            "n": len(scores),
        }
    return {
        "status": "ok",
        "n": len(scores),
        "n_pos": sum(labels),
        "n_neg": len(labels) - sum(labels),
        "auroc": roc_auc(scores, labels),
        "auprc": average_precision(scores, labels),
        "ece": expected_calibration_error(scores, labels),
    }


__all__ = [
    "binary_from_four_level",
    "roc_auc",
    "average_precision",
    "expected_calibration_error",
    "metrics_from_pairs",
]
