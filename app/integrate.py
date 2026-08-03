# -*- coding: utf-8 -*-
"""Backward-compatible re-export — prefer ``app.agent``.

Historical name kept so existing imports and layout checks keep working.
"""

from __future__ import annotations

from app.agent import (  # noqa: F401
    AgentResult,
    RBPAgent,
    ensure_workspace_skill,
    linux_feasibility_notes,
    skill_path,
)
from app.rbp_bootstrap import install_rbp_tools_into_nanobot  # noqa: F401

__all__ = [
    "AgentResult",
    "RBPAgent",
    "ensure_workspace_skill",
    "install_rbp_tools_into_nanobot",
    "linux_feasibility_notes",
    "skill_path",
]
