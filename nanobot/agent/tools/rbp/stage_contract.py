# -*- coding: utf-8 -*-
"""Declarative Stage 0–3 tool-ordering contract (Proposal §5 / §9).

Single source of truth for which tools may run when. ``turn_guards`` holds
per-turn *state*; this module holds *policy*:

* ``STAGE_RETRIEVE`` — Stage-1 retrieve tools (read-only / concurrency-safe).
  The nanobot runner may ``asyncio.gather`` consecutive calls in one turn.
* ``REQUIRES`` — serial edges on the unseen/transfer path
  (retrieve → fuse → commit → abstain → predict). Keys are tool names;
  values are prerequisite tool names or sentinels such as
  ``__any_retrieve__``, ``__structure_axis__``, ``__domain_axis__``.
* ``OWN_HEAD_STOP_BLOCKED`` — tools refused after a successful in-catalogue
  own-head ``predict_interaction`` (Stage 0 STOP).

Kept data-driven so a future scheduler can consume the same edges instead of
post-hoc blocking only.

CLI examples:
  nanobot-bio agent --force-transfer --query PTBP1 --rna-file path/to/rna.txt
  nanobot-bio agent --example pos
  nanobot-bio mvp
"""

from __future__ import annotations

from typing import Any, Optional

from app.backends.delivery.tool_mapping import retrieve_tool_names

# Stage-1 retrieve tools (parallel-safe; runner batches them when emitted
# consecutively in one assistant turn). Curated and raw names are mapping-derived.
STAGE_RETRIEVE: frozenset[str] = retrieve_tool_names()

# Serial prerequisite edges on the unseen/transfer path.
#   key tool -> tuple of prerequisite tool names that must be done first.
# Special sentinels:
#   "__any_retrieve__" — at least one STAGE_RETRIEVE tool
#   "__structure_axis__" — structure retrieve attempted when axes.structure
#   "__domain_axis__" — domain retrieve attempted when axes.domain
# Delivery BUILD_SPEC: parallel multi-view = emb/seq + Foldseek + domain.
REQUIRES: dict[str, tuple[str, ...]] = {
    "fuse_similarity_views": (
        "__any_retrieve__",
        "__structure_axis__",
        "__domain_axis__",
    ),
    # Checkpoint 1: select a subset of deterministic fused proxies.
    "commit_proxy_candidates": ("fuse_similarity_views",),
    "confidence_abstain": ("commit_proxy_candidates",),
    "transfer_prior_lookup": ("fuse_similarity_views",),
    "donor_quality_prior": ("fuse_similarity_views",),
    "similarity_weighted_vote": ("confidence_abstain",),
    # predict_interaction on the transfer/multi-donor path requires abstain.
    # Own-head single-alias path is exempt (handled in turn_guards).
    "predict_interaction": ("confidence_abstain",),
}

# Tools that satisfy the structure / domain multi-view sentinels.
STRUCTURE_RETRIEVE: frozenset[str] = frozenset(
    {
        "struct_similarity",
        "struct_similarity_foldseek",
        "structure_fetch",
        "structure_consensus",
        "predict_structure",
        "structure_predict_af3",
        "struct_align_usalign",
    }
)
DOMAIN_RETRIEVE: frozenset[str] = frozenset({"domain_architecture"})

# Tools refused after own-head predict_interaction success (Stage 0 STOP).
OWN_HEAD_STOP_BLOCKED: frozenset[str] = frozenset(
    STAGE_RETRIEVE
    | {
        "fuse_similarity_views",
        "commit_proxy_candidates",
        "transfer_prior_lookup",
        "donor_quality_prior",
        "similarity_weighted_vote",
        "confidence_abstain",
        "predict_structure_af3",
        "literature_retrieval",
        "esm_similarity",
        "protein_seq_similarity",
        "struct_similarity_foldseek",
        "struct_align_usalign",
    }
)


def is_retrieve(tool_name: str) -> bool:
    return tool_name in STAGE_RETRIEVE


def prerequisite_for(tool_name: str) -> Optional[tuple[str, ...]]:
    return REQUIRES.get(tool_name)


_SENTINELS = frozenset(
    {"__any_retrieve__", "__structure_axis__", "__domain_axis__"}
)


def describe_unmet_prerequisite(tool_name: str, done: set[str]) -> Optional[str]:
    """Return a human reason if ``tool_name`` has unmet prerequisites, else None.

    ``done`` is the set of tool names already completed this turn.
    Structure/domain sentinels are advisory here (axis gating lives in
    ``turn_guards.fuse_blocked_reason`` so axes config can waive them).
    """
    prereqs = REQUIRES.get(tool_name)
    if not prereqs:
        return None
    for p in prereqs:
        if p == "__any_retrieve__":
            if not (done & STAGE_RETRIEVE):
                return (
                    f"Call at least one retrieve tool ({sorted(STAGE_RETRIEVE)[:4]}...) "
                    f"before {tool_name}."
                )
        elif p in ("__structure_axis__", "__domain_axis__"):
            continue  # enforced with axes awareness in turn_guards
        elif p not in done:
            return f"Call {p} before {tool_name}. BUILD_SPEC stage order."
    return None


def is_acyclic() -> bool:
    """Sanity: REQUIRES edges must not form a cycle (excludes the sentinel)."""
    graph: dict[str, list[str]] = {
        k: [p for p in v if p not in _SENTINELS] for k, v in REQUIRES.items()
    }
    color: dict[str, int] = {}

    def dfs(node: str) -> bool:
        color[node] = 1
        for nxt in graph.get(node, []):
            if color.get(nxt) == 1:
                return False
            if color.get(nxt, 0) == 0 and not dfs(nxt):
                return False
        color[node] = 2
        return True

    return all(dfs(n) for n in list(graph) if color.get(n, 0) == 0)


__all__ = [
    "STAGE_RETRIEVE",
    "STRUCTURE_RETRIEVE",
    "DOMAIN_RETRIEVE",
    "REQUIRES",
    "OWN_HEAD_STOP_BLOCKED",
    "is_retrieve",
    "prerequisite_for",
    "describe_unmet_prerequisite",
    "is_acyclic",
]
