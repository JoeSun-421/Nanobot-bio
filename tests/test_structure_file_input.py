# -*- coding: utf-8 -*-
"""A1: structure_file input modality — resolve_rbp accepts a local PDB/CIF path."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_TMP = ROOT / "artifacts" / "tmp_structure_tests"


def _load_sot(name: str, rel: str):
    path = ROOT / rel
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _mk(name: str, data: bytes) -> Path:
    _TMP.mkdir(parents=True, exist_ok=True)
    p = _TMP / name
    p.write_bytes(data)
    return p.resolve()


def test_resolve_structure_file_validates_ext_and_existence():
    common = _load_sot("common_sot_a1", "nanobot/agent/tools/rbp/common.py")
    # missing path
    p, err = common.resolve_structure_file("")
    assert p is None and err is None
    # nonexistent
    p, err = common.resolve_structure_file("/nonexistent/foo.pdb")
    assert p is None and err and ("not found" in err or "outside allowlist" in err)
    # wrong ext (under allowlisted root)
    txt = _mk("bad.txt", b"x")
    try:
        p, err = common.resolve_structure_file(str(txt))
        assert p is None and err and "must be one of" in err
    finally:
        txt.unlink(missing_ok=True)
    # valid pdb under package root (allowlisted)
    pdb = _mk("ok.pdb", b"HEADER test\n")
    try:
        p, err = common.resolve_structure_file(str(pdb))
        assert err is None and p is not None and p.is_file()
    finally:
        pdb.unlink(missing_ok=True)
    # relative path rejected
    p, err = common.resolve_structure_file("relative/foo.pdb")
    assert p is None and err and "absolute" in err
    # jail: absolute path outside allowlist
    outside = Path("/etc/hosts")
    if outside.is_file():
        # rename trick won't change suffix; use a fake absolute under /etc
        p, err = common.resolve_structure_file("/etc/no_such_structure.pdb")
        assert p is None and err


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

    cif = _mk("ok.cif", b"data_test\n")
    try:
        out = json.loads(asyncio.run(tool.execute(structure_file=str(cif))))
        assert out.get("status") == "ok"
        val = out.get("value") or {}
        assert val.get("source") == "structure_file"
        assert Path(val["pdb_path"]).resolve() == cif.resolve()
        assert val.get("in_panel") is False
    finally:
        cif.unlink(missing_ok=True)
