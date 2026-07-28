# -*- coding: utf-8
"""RNA axis — delivery rna_blastn only; fusion rna_peak_homology gated on PEAKS_DB."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_rna_blastn_in_stage1_and_mapping():
    import yaml

    from app.backends.delivery.stage_tools import STAGE_TOOL_SETS

    assert "rna_blastn" in STAGE_TOOL_SETS["stage1"]
    assert "rna_similarity" not in STAGE_TOOL_SETS["stage1"]

    mapping = yaml.safe_load(
        (ROOT / "app" / "backends" / "delivery" / "mapping.yaml").read_text(
            encoding="utf-8"
        )
    )
    assert "rna_blastn" in mapping
    assert "rna_similarity" not in mapping


def test_fuse_zeros_rna_peak_without_peaks_db(monkeypatch):
    from app.core import capability_matrix as cm
    from rbp_eval.scoring.fuse_hits import fuse_rbp_hits

    monkeypatch.setattr(
        cm,
        "rna_blastn_status",
        lambda: {"status": "degraded", "tool": "rna_blastn"},
    )
    hits = [
        [
            {"alias": "PTBP1", "score": 0.9, "metric": "rna_peak_homology"},
            {"alias": "QKI", "score": 0.5, "metric": "rna_peak_homology"},
        ],
        [
            {"alias": "PTBP1", "score": 0.8, "metric": "esmc_cosine"},
        ],
    ]
    donors = fuse_rbp_hits(
        hits, top_k=2, weights={"rna_peak_homology": 0.3, "esmc_cosine": 1.0}
    )
    assert donors
    assert donors[0]["alias"] == "PTBP1"


def test_current_default_keeps_rna_peak_as_evidence_only(monkeypatch):
    from app.core import capability_matrix as cm
    from rbp_eval.scoring.fuse_hits import fuse_rbp_hits

    monkeypatch.setattr(
        cm,
        "rna_blastn_status",
        lambda: {"status": "ready", "tool": "rna_blastn"},
    )
    donors = fuse_rbp_hits(
        [
            [{"alias": "RNA_ONLY", "score": 1.0, "metric": "rna_peak_homology"}],
            [{"alias": "PROTEIN", "score": 0.5, "metric": "esmc_cosine"}],
        ],
        top_k=2,
    )
    assert [row["alias"] for row in donors] == ["PROTEIN"]
