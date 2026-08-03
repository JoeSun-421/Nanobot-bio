# -*- coding: utf-8 -*-
"""Thin bootstrap helpers — no import of ``app.agent`` (breaks registry↔agent cycle)."""

from __future__ import annotations

import os
from pathlib import Path

_PKG_DIR = Path(__file__).resolve().parent
_ROOT = Path(os.environ.get("NANOBOT_BIO_ROOT", _PKG_DIR.parent)).expanduser().resolve()
_DEFAULT_NANOBOT_SRC = _ROOT / "nanobot"


def install_rbp_tools_into_nanobot() -> Path:
    """Sync SoT tools/skill into installed nanobot runtime + workspace."""
    from app.sync_overlay import sync_overlay

    sync_overlay()
    nb = Path(os.environ.get("NANOBOT_SRC", _DEFAULT_NANOBOT_SRC)).expanduser().resolve()
    return nb / "agent" / "tools" / "rbp"
