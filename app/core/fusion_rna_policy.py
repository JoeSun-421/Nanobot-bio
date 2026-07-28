# -*- coding: utf-8 -*-
"""RNA fusion weight policy — rna_peak_homology stays 0 unless peaks DB is ready."""

from __future__ import annotations

from typing import Any

DEFAULT_REAL_WEIGHT = 0.30


def apply_fusion_rna_policy(weights: dict[str, float]) -> dict[str, float]:
    """Zero delivery rna_blastn fusion metric when PEAKS_DB is unavailable."""
    out = {str(k): float(v) for k, v in weights.items()}
    # Drop legacy RNA-FM keys from older configs.
    out.pop("rna_embed", None)
    out.pop("rna_fm", None)
    try:
        from app.core.capability_matrix import rna_blastn_status

        if rna_blastn_status().get("status") != "ready":
            out["rna_peak_homology"] = 0.0
    except Exception:
        out["rna_peak_homology"] = 0.0
    return out


def write_gate(payload: dict[str, Any]) -> None:
    """No-op — RNA-FM eval gate removed; peaks DB readiness is runtime-only."""
    del payload
