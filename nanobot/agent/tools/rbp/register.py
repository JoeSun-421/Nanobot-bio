# -*- coding: utf-8 -*-
"""Register curated RBP tools + optional raw delivery tools onto a ToolRegistry."""

from __future__ import annotations

from typing import Optional, Union

from nanobot.agent.tools.core.registry import ToolRegistry

from nanobot.agent.tools.rbp import register_all as register_proposal_tools

RawMode = Union[bool, str]

# Product default: whitelist (curated P0-P2 + Stage extras). Set env RBP_RAW_TOOLS=all
# to opt into the full 37-tool set for debugging / exhaustive delivery coverage.
DEFAULT_RAW_MODE = "whitelist"


def _normalize_raw_mode(include_raw_delivery: RawMode) -> str:
    """Map API → none | whitelist | all. Default for True / all_ready is all."""
    if include_raw_delivery is False or include_raw_delivery in ("none", "false", 0):
        return "none"
    if include_raw_delivery in ("whitelist", "mvp"):
        return "whitelist"
    if include_raw_delivery in (True, "all", "all_ready", "ready"):
        return "all"
    # Unknown strings → whitelist (product default), not full-open
    return "whitelist"


def register_rbp_tools(
    registry: Optional[ToolRegistry] = None,
    *,
    include_raw_delivery: RawMode = DEFAULT_RAW_MODE,
) -> tuple[ToolRegistry, list[str]]:
    """
    Register RBP tools onto a Nanobot ToolRegistry.

    ``include_raw_delivery``:
      - ``"all"`` / ``"all_ready"`` / ``True`` — every delivery SCRIPT_MAP tool (final)
      - ``"whitelist"`` / ``"mvp"`` — Stage extras only (narrow MVP)
      - ``False`` / ``"none"`` — curated P0–P2 tools only

    Returns (registry, registered_names).
    """
    reg = registry if registry is not None else ToolRegistry()
    names = register_proposal_tools(reg)
    mode = _normalize_raw_mode(include_raw_delivery)

    if mode != "none":
        from nanobot.agent.tools.rbp.common import (
            ensure_nanobot_bio_on_path,
            get_delivery_client,
        )
        from app.backends.delivery.registry import (
            STAGE_RAW_WHITELIST,
            build_delivery_raw_tools,
        )

        ensure_nanobot_bio_on_path()
        client = get_delivery_client()
        existing = set(names)
        allow = None if mode == "all" else STAGE_RAW_WHITELIST
        for t in build_delivery_raw_tools(client, allow_names=allow):
            if t.name not in existing:
                reg.register(t)
                names.append(t.name)
                existing.add(t.name)

    # Re-export for callers that imported STAGE_RAW_WHITELIST from here
    return reg, names


# Back-compat alias (canonical: app.backends.delivery.registry)
def __getattr__(name: str):
    if name == "STAGE_RAW_WHITELIST":
        from app.backends.delivery.registry import STAGE_RAW_WHITELIST as _w

        return _w
    raise AttributeError(name)
