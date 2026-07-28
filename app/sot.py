# -*- coding: utf-8 -*-
"""Locate toolkit SoT (skills + tools/rbp).

Single source of truth: ``nanobot/`` under ``NANOBOT_BIO_ROOT``
(Proposal §6.2). After slim-vendor, this tree *is* the runtime.
"""

from __future__ import annotations

import os
from pathlib import Path


def sot_root() -> Path:
    """Return the SoT directory (contains ``skills/`` and ``agent/tools/rbp/``)."""
    bio = Path(
        os.environ.get("NANOBOT_BIO_ROOT", Path(__file__).resolve().parents[1])
    ).expanduser().resolve()
    preferred = bio / "nanobot"
    skill = preferred / "skills" / "rbp-agent" / "SKILL.md"
    legacy = bio / "plugin" / "nanobot"
    if skill.is_file():
        return preferred.resolve()
    if (legacy / "skills" / "rbp-agent" / "SKILL.md").is_file():
        raise FileNotFoundError(
            f"Legacy SoT found at {legacy}; move it to {preferred} "
            "(repo-root nanobot/). plugin/nanobot is no longer supported."
        )
    raise FileNotFoundError(f"Missing SoT skill at {skill}")


def skill_md() -> Path:
    return sot_root() / "skills" / "rbp-agent" / "SKILL.md"


def tools_rbp() -> Path:
    return sot_root() / "agent" / "tools" / "rbp"
