# -*- coding: utf-8 -*-
"""Product authority paths — proposal + delivery only (not 工程指南 / 整改清单)."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

PROPOSAL_MD = REPO_ROOT / "docs" / "product" / "proposal.md"
PROPOSAL_ZH_MD = REPO_ROOT / "docs" / "product" / "proposal.zh.md"

DELIVERY_AGENT_MD = (
    "AGENT_BUILD_SPEC.zh.md",
    "HANDOFF.zh.md",
    "DESIGN.zh.md",
    "SETUP.zh.md",
)

# Machine-readable delivery tool SoT (BUILD_SPEC §2).
DELIVERY_REGISTRY_NAME = "agent/tools/registry.json"


def delivery_root() -> Path | None:
    """Resolve delivery package root (delegates to delivery env)."""
    from app.backends.delivery.env import try_delivery_root

    return try_delivery_root()


def delivery_registry_path() -> Path | None:
    root = delivery_root()
    if root is None:
        return None
    p = root / DELIVERY_REGISTRY_NAME
    return p if p.is_file() else None
