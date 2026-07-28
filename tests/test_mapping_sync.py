# -*- coding: utf-8 -*-
"""mapping.yaml covers SCRIPT_MAP whitelist + curated tool wrappers."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_mapping_covers_stage_whitelist_and_proposal():
    from app.backends.delivery.client import SCRIPT_MAP
    from app.backends.delivery.registry import PROPOSAL_TOOL_NAMES, STAGE_RAW_WHITELIST

    mapping = yaml.safe_load(
        (ROOT / "app" / "backends" / "delivery" / "mapping.yaml").read_text(
            encoding="utf-8"
        )
    )
    assert isinstance(mapping, dict)

    for name in STAGE_RAW_WHITELIST:
        assert name in mapping, f"whitelist tool {name} missing from mapping.yaml"
        assert name in SCRIPT_MAP, f"whitelist tool {name} missing from SCRIPT_MAP"

    for name in PROPOSAL_TOOL_NAMES:
        assert name in mapping, f"curated tool {name} missing from mapping.yaml"


def test_script_map_and_axis_gates_are_mapping_derived():
    from app.backends.delivery.client import SCRIPT_MAP
    from app.backends.delivery.stage_tools import TOOL_AXIS_GATE
    from app.backends.delivery.tool_mapping import (
        delivery_script_map,
        retrieve_tool_names,
    )

    assert SCRIPT_MAP == delivery_script_map()
    assert TOOL_AXIS_GATE["struct_similarity_foldseek"] == "structure"
    assert TOOL_AXIS_GATE["structure_predict_af3"] == "use_af3"
    assert TOOL_AXIS_GATE["esm_similarity"] == "sequence"
    assert "fuse_similarity_views" not in retrieve_tool_names()


def test_delivery_registry_mapping_validates_fail_closed():
    from app.backends.delivery.client import load_delivery_registry
    from app.backends.delivery.tool_mapping import (
        MappingValidationError,
        validate_delivery_registry,
    )

    registry = load_delivery_registry()
    broken = {**registry, "tools": [*registry["tools"], {"name": "new_ready", "status": "ready"}]}
    with pytest.raises(MappingValidationError, match="missing_bindings"):
        validate_delivery_registry(broken)
