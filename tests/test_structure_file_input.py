# -*- coding: utf-8 -*-
"""A1: structure_file input modality — resolve_rbp accepts a local PDB/CIF path."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _load_sot(name: str, rel: str):
    path = ROOT / rel
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_resolve_structure_file_validates_ext_and_existence():
    common = _load_sot("common_sot_a1", "nanobot/agent/tools/rbp/common.py")
    # missing path
    p, err = common.resolve_structure_file("")
    assert p is None and err is None
    # nonexistent
    p, err = common.resolve_structure_file("/nonexistent/foo.pdb")
    assert p is None and err and "not found" in err
    # wrong ext
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
        f.write(b"x")
        txt = f.name
    try:
        p, err = common.resolve_structure_file(txt)
        assert p is None and err and "must be one of" in err
    finally:
        Path(txt).unlink(missing_ok=True)
    # valid pdb
    with tempfile.NamedTemporaryFile(suffix=".pdb", delete=False) as f:
        f.write(b"HEADER test\n")
        pdb = f.name
    try:
        p, err = common.resolve_structure_file(pdb)
        assert err is None and p is not None and p.is_file()
    finally:
        Path(pdb).unlink(missing_ok=True)
    # relative path rejected
    p, err = common.resolve_structure_file("relative/foo.pdb")
    assert p is None and err and "absolute" in err


def test_resolve_rbp_tool_short_circuits_on_structure_file(monkeypatch):
    """The resolve_rbp DeliveryBackedTool must skip the delivery call when a
    valid structure_file is supplied and return pdb_path for struct_similarity."""
    from app.backends.delivery.registry import DeliveryBackedTool

    tool = DeliveryBackedTool(
        tool_name="resolve_rbp",
        description="resolve",
        parameters={"type": "object", "properties": {}},
        client=None,
        delivery_name="resolve_rbp",
        read_only=True,
    )
    # turn guards: ensure no Stage-0 STOP blocks retrieve
    from nanobot.agent.tools.rbp import turn_guards

    turn_guards.reset_stage_guards()

    with tempfile.NamedTemporaryFile(suffix=".cif", delete=False) as f:
        f.write(b"data_test\n")
        cif = f.name
    try:
        out = json.loads(asyncio.run(tool.execute(structure_file=cif)))
        assert out["status"] == "ok"
        v = out["value"]
        assert v["in_panel"] is False
        assert v["pdb_path"] == cif
        assert v["source"] == "structure_file"
    finally:
        Path(cif).unlink(missing_ok=True)

    # invalid path → error envelope, no delivery call
    out = json.loads(asyncio.run(tool.execute(structure_file="/nope/x.pdb")))
    assert out["status"] == "error"
    blob = out.get("error") or out.get("reason") or ""
    assert "not found" in blob


def test_resolve_rbp_schema_advertises_structure_file():
    from app.backends.delivery.registry import build_delivery_raw_tools
    from app.backends.delivery.client import DeliveryToolClient

    tools = build_delivery_raw_tools(DeliveryToolClient(), allow_names={"resolve_rbp"})
    assert tools, "resolve_rbp must be registered"
    tool = next(t for t in tools if t.name == "resolve_rbp")
    props = tool.parameters.get("properties", {})
    assert "structure_file" in props
