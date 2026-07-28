# -*- coding: utf-8 -*-
"""
Plugin SoT RBP tools — nanobot/agent/tools/rbp/

P0–P2 tools as nanobot.agent.tools.core.base.Tool subclasses.
When this package is installed into the real nanobot tree
(``agent/tools/rbp/``), ToolLoader can discover classes with
``_plugin_discoverable = True``.
"""

import os

from nanobot.agent.tools.rbp.annotation import (
    GetFuncAnnotationTool,
    LiteratureSearchTool,
)
from nanobot.agent.tools.rbp.catalogue import GetKnownRBPListTool
from nanobot.agent.tools.rbp.commit_proxies import CommitProxyCandidatesTool
from nanobot.agent.tools.rbp.evolve_tools import (
    FuseSimilarityViewsTool,
    LookupProxyCacheTool,
)
from nanobot.agent.tools.rbp.near_known import CheckNearKnownTool
from nanobot.agent.tools.rbp.phmmer import PhmmerSimilarityTool
from nanobot.agent.tools.rbp.predict import PredictInteractionTool
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
    LookupProxyCacheTool,
    FuseSimilarityViewsTool,
    CommitProxyCandidatesTool,
    CheckNearKnownTool,
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
    "LookupProxyCacheTool",
    "FuseSimilarityViewsTool",
    "CommitProxyCandidatesTool",
    "CheckNearKnownTool",
    "PhmmerSimilarityTool",
    "register_all",
]


def register_all(registry) -> list[str]:
    """Instantiate and register all curated RBP tools on a ToolRegistry."""
    names = []
    for cls in ALL_RBP_TOOL_CLASSES:
        tool = cls()
        registry.register(tool)
        names.append(tool.name)
    # A2: optional axes (phmmer) — only when their env flag is set.
    for cls in _optional_tools():
        tool = cls()
        registry.register(tool)
        names.append(tool.name)
    return names
