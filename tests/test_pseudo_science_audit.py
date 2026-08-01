# -*- coding: utf-8
"""Pseudo-science audit — anchored to proposal + delivery registry only."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Proposal Table 2 curated agent tools (proposal.zh.md §5) — no rna_similarity.
PROPOSAL_TABLE2_CURATED = frozenset(
    {
        "predict_interaction",
        "get_known_rbp_list",
        "seq_similarity",
        "struct_similarity",
        "get_func_annotation",
        "fuse_similarity_views",
        "commit_proxy_candidates",
        "predict_structure",
        "literature_search",
    }
)


def _load_delivery_registry() -> list[dict]:
    from app.core.product_authority import delivery_registry_path

    path = delivery_registry_path()
    if path is None:
        pytest.skip("DELIVERY_ROOT / registry.json not found")
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        return list(data.get("tools") or [])
    return list(data or [])


def test_authority_docs_exist():
    """Proposal authority docs — skip if absent (docs/ mostly gitignored on CI)."""
    from app.core.product_authority import PROPOSAL_MD, PROPOSAL_ZH_MD

    if not PROPOSAL_MD.is_file() or not PROPOSAL_ZH_MD.is_file():
        pytest.skip(
            "docs/product/proposal.md and/or proposal.zh.md missing "
            "(docs/ is local-only / optional; skipped when absent)"
        )
    assert PROPOSAL_MD.is_file()
    assert PROPOSAL_ZH_MD.is_file()


def test_delivery_registry_has_rna_blastn_not_rna_similarity():
    tools = _load_delivery_registry()
    names = {t.get("name") for t in tools if isinstance(t, dict)}
    assert "rna_blastn" in names
    assert "rna_similarity" not in names


def test_proposal_tool_names_match_table2():
    from app.backends.delivery.registry import PROPOSAL_TOOL_NAMES, STAGE_RAW_WHITELIST

    assert PROPOSAL_TABLE2_CURATED <= PROPOSAL_TOOL_NAMES
    assert "rna_similarity" not in PROPOSAL_TOOL_NAMES
    assert "rna_blastn" in STAGE_RAW_WHITELIST


def test_stage1_has_rna_blastn_not_rna_similarity():
    from app.backends.delivery.stage_tools import STAGE_TOOL_SETS

    assert "rna_blastn" in STAGE_TOOL_SETS["stage1"]
    assert "rna_similarity" not in STAGE_TOOL_SETS["stage1"]


def test_fusion_weights_zero_rna_peak_without_peaks():
    from app.core.runtime_config import fusion_weights

    fw = fusion_weights()
    assert float(fw.get("rna_peak_homology", 0)) == 0.0
    assert fw.get("rna_embed") is None
    assert fw.get("rna_fm") is None


def test_no_rna_similarity_tool_registered():
    from nanobot.agent.tools.rbp import ALL_RBP_TOOL_CLASSES

    names = {cls().name for cls in ALL_RBP_TOOL_CLASSES}
    assert "rna_similarity" not in names
    assert "rna_blastn" not in names  # raw delivery; mounted via RBP_RAW_TOOLS (default all)


def test_vote_aligns_with_predict_p_hat():
    from app.core.capability_matrix import SIMILARITY_WEIGHTED_VOTE_DRIVES_P_HAT

    assert SIMILARITY_WEIGHTED_VOTE_DRIVES_P_HAT is True


def test_capability_matrix_rna_blastn_feature():
    from app.core.capability_matrix import probe_capabilities

    feats = probe_capabilities()["features"]
    assert "rna_blastn" in feats
    assert "rna_similarity" not in feats
    assert feats["similarity_weighted_vote_drives_p_hat"] is True


def test_synthetic_promote_refused():
    from rbp_eval.evolve.run_eval import (
        assert_not_synthetic_promote_input,
        results_are_retrieval_only_synthetic,
    )

    results = [{"mode": "retrieval_only", "verdict": {"p_hat": None}}]
    assert results_are_retrieval_only_synthetic(results)
    with pytest.raises(ValueError, match="Refuse promote"):
        assert_not_synthetic_promote_input(results)


def test_structure_py_forbids_sim_zero_guard():
    src = (ROOT / "nanobot" / "agent" / "tools" / "rbp" / "structure.py").read_text(
        encoding="utf-8"
    )
    assert "structure_axis=unavailable" in src
    assert "sim=0" in src
