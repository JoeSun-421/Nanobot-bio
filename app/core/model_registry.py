# -*- coding: utf-8 -*-
"""Model capability metadata — thin facade over ``capability_matrix`` (SoT)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.core.capability_matrix import (
    model_specs,
    probe_capabilities,
    probe_model_capabilities,
    write_capability_matrix,
)

__all__ = [
    "model_specs",
    "probe_model_capabilities",
    "probe_capabilities",
    "write_capability_matrix",
]


def write_model_matrix(path: Path | None = None) -> Path:
    """Alias kept for older call sites."""
    return write_capability_matrix(path)
