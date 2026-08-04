# -*- coding: utf-8 -*-
"""Curated RhoBind / RBP agent tools (Stage 0–3 product surface).

P0–P2 ``Tool`` subclasses for catalogue lookup, multi-view retrieve, fuse /
commit, and ``predict_interaction``. When installed under nanobot
``agent/tools/rbp/``, ToolLoader can discover classes with
``_plugin_discoverable = True``.

Module map:

* ``catalogue`` / ``seq`` / ``structure`` / ``annotation`` / ``phmmer`` —
  Stage-0/1 retrieve axes (phmmer optional via ``RBP_PHMMER=1``)
* ``near_known`` — Stage-0 near-match Fast Path
* ``evolve_tools`` / ``commit_proxies`` — fuse + Checkpoint-1 commit
* ``predict`` / ``fasta_score`` — Stage-3 / batch own-head scoring
* ``common`` / ``path_guard`` / ``stage_contract`` / ``turn_guards`` —
  shared helpers, path jail, ordering policy, per-turn state
* ``project_doc`` / ``register`` — doc reader + registry mount
* ``prompt_suite`` — offline prompt-suite runner (eval harness)

Invariant across tools: never invent ``s_i`` / ``p_hat``; probs and
similarities come from delivery or upstream tool results only.
"""

import os

from nanobot.agent.tools.rbp.annotation import (
    GetFuncAnnotationTool,
    LiteratureSearchTool,
    RecordLitPeerDecisionsTool,
)
from nanobot.agent.tools.rbp.catalogue import GetKnownRBPListTool
from nanobot.agent.tools.rbp.commit_proxies import CommitProxyCandidatesTool
from nanobot.agent.tools.rbp.evolve_tools import (
    FuseSimilarityViewsTool,
    LookupProxyCacheTool,
)
from nanobot.agent.tools.rbp.fasta_score import ScoreBindingFastaTool
from nanobot.agent.tools.rbp.near_known import CheckNearKnownTool
from nanobot.agent.tools.rbp.phmmer import PhmmerSimilarityTool
from nanobot.agent.tools.rbp.predict import PredictInteractionTool
from nanobot.agent.tools.rbp.project_doc import ReadProjectDocTool
from nanobot.agent.tools.rbp.prompt_suite import RunPromptSuiteTool
from nanobot.agent.tools.rbp.seq import SeqSimilarityTool
from nanobot.agent.tools.rbp.structure import PredictStructureTool, StructSimilarityTool

# Explicit list for register_all()
ALL_RBP_TOOL_CLASSES = [
    PredictInteractionTool,
    GetKnownRBPListTool,
    SeqSimilarityTool,
    StructSimilarityTool,
    GetFuncAnnotationTool,
    PredictStructureTool,
    LiteratureSearchTool,
    RecordLitPeerDecisionsTool,
    LookupProxyCacheTool,
    FuseSimilarityViewsTool,
    CommitProxyCandidatesTool,
    CheckNearKnownTool,
    ScoreBindingFastaTool,
    ReadProjectDocTool,
    RunPromptSuiteTool,
]

# A2: phmmer remote-homology axis is OPTIONAL — not mounted by default (needs
# hmmer installed + adds latency). Opt in via RBP_PHMMER=1.
OPTIONAL_TOOL_CLASSES = [PhmmerSimilarityTool]


def _optional_tools() -> list:
    """Return optional tool classes enabled by env flags (A2 phmmer, etc.)."""
    enabled: list = []
    if os.environ.get("RBP_PHMMER") in ("1", "true", "yes", "on"):
        enabled.extend(OPTIONAL_TOOL_CLASSES)
    return enabled

__all__ = [
    "ALL_RBP_TOOL_CLASSES",
    "OPTIONAL_TOOL_CLASSES",
    "PredictInteractionTool",
    "GetKnownRBPListTool",
    "SeqSimilarityTool",
    "StructSimilarityTool",
    "GetFuncAnnotationTool",
    "PredictStructureTool",
    "LiteratureSearchTool",
    "RecordLitPeerDecisionsTool",
    "LookupProxyCacheTool",
    "FuseSimilarityViewsTool",
    "CommitProxyCandidatesTool",
    "CheckNearKnownTool",
    "ScoreBindingFastaTool",
    "ReadProjectDocTool",
    "RunPromptSuiteTool",
    "PhmmerSimilarityTool",
    "register_all",
]


def register_all(registry) -> list[str]:
    """Instantiate and register all curated RBP tools on a ToolRegistry.

    Honors ``tools.soft_disabled`` from evolved runtime config (self-evolution
    retirement candidates): those tools are **not** registered. Delivery code
    is never deleted.
    """
    skipped: set[str] = set()
    try:
        from app.core.runtime_config import soft_disabled_tools

        skipped = {str(t) for t in soft_disabled_tools()}
    except Exception:
        skipped = set()

    names = []
    for cls in ALL_RBP_TOOL_CLASSES:
        tool = cls()
        if tool.name in skipped:
            continue
        registry.register(tool)
        names.append(tool.name)
    # A2: optional axes (phmmer) — only when their env flag is set.
    for cls in _optional_tools():
        tool = cls()
        if tool.name in skipped:
            continue
        registry.register(tool)
        names.append(tool.name)
    return names
