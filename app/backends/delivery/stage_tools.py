# -*- coding: utf-8 -*-
"""Stage tool subsets + axes → tool hard-gates (mature agent allowlists)."""

from __future__ import annotations

from typing import Optional

from app.backends.delivery.tool_mapping import stage_tool_sets, tool_axis_gates

# Curated + whitelist tools grouped by playbook stage, and all axis gates, come
# from the validated App mapping layer.
STAGE_TOOL_SETS: dict[str, frozenset[str]] = stage_tool_sets()
TOOL_AXIS_GATE: dict[str, str] = tool_axis_gates()


def axis_enabled(tool_name: str, axes: Optional[dict] = None) -> tuple[bool, Optional[str]]:
    """Return (allowed, blocking_axis_or_None)."""
    axis = TOOL_AXIS_GATE.get(tool_name)
    if not axis:
        return True, None
    if axes is None:
        try:
            from app.core.runtime_config import load_runtime_config

            axes = (load_runtime_config().get("axes") or {})
        except Exception as exc:
            return False, f"{axis}:runtime_config_unavailable:{type(exc).__name__}"
    if axes.get(axis) is False:
        return False, axis
    return True, None


# Product-required axes for multi-view MVP (AF3 intentionally optional).
REQUIRED_AXES_ON: tuple[str, ...] = (
    "embedding",
    "sequence",
    "domain",
    "structure",
    "function_annotation",
    "rna_blastn",
    "literature",
)
OPTIONAL_AXES_OFF_OK: tuple[str, ...] = (
    "use_af3",
    "struct_align_refine",
)


def assert_full_axes_enabled(axes: Optional[dict] = None) -> list[str]:
    """Return list of required axes that are off (empty ⇒ multi-view OK).

    ``use_af3`` may stay false (AFDB preferred). Does not raise.
    """
    if axes is None:
        try:
            from app.core.runtime_config import load_runtime_config

            axes = dict(load_runtime_config().get("axes") or {})
        except Exception:
            axes = {}
    off: list[str] = []
    for key in REQUIRED_AXES_ON:
        if axes.get(key) is False:
            off.append(key)
    return off


def axis_status_matrix(axes: Optional[dict] = None) -> dict[str, str]:
    """Per-axis ready|off|degraded (AF3 reads host status file when enabled)."""
    if axes is None:
        try:
            from app.core.runtime_config import load_runtime_config

            axes = dict(load_runtime_config().get("axes") or {})
        except Exception:
            axes = {}
    out: dict[str, str] = {}
    for key, val in sorted(axes.items()):
        if val is False:
            out[key] = "off"
            continue
        if key == "use_af3":
            out[key] = _af3_runtime_status()
        else:
            out[key] = "ready"
    return out


def _af3_runtime_status() -> str:
    """Map host AF3 status file + AF3_PYTHON to ready|degraded|off."""
    from app.core.capability_matrix import af3_runtime_status

    return af3_runtime_status()
