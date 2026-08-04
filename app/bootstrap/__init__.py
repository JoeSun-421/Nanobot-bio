# -*- coding: utf-8 -*-
"""In-package bootstrap: SoT paths, workspace skill sync, tool install helpers.

Do **not** import ``app.agent`` here (avoids registry↔agent cycles).

Compatibility: ``python -m app.sync_overlay`` remains a thin re-export of
``sync_overlay``. Prefer ``from app.bootstrap import …`` in new code.
"""

from __future__ import annotations

from app.bootstrap.rbp_bootstrap import install_rbp_tools_into_nanobot
from app.bootstrap.sot import skill_md, sot_root, tools_rbp
from app.bootstrap.sync_overlay import sync_overlay

__all__ = [
    "install_rbp_tools_into_nanobot",
    "skill_md",
    "sot_root",
    "sync_overlay",
    "tools_rbp",
]
