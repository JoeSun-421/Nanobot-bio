# -*- coding: utf-8 -*-
"""App delivery bridge hardening: ok semantics, fail-closed gates, script jail."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _client_stub(**meta):
    from app.backends.delivery.client import DeliveryToolClient

    client = DeliveryToolClient.__new__(DeliveryToolClient)
    client.offline = False
    client.prefer_import = True
    client.device = "cpu"
    client.use_conda = False
    client.conda_envs = {}
    client.meta = meta or {"toy": {}}
    client._dedupe_ttl_s = 90.0
    client._recent_calls = {}
    client.root = ROOT
    return client


def test_client_ok_defaults_false_when_error_present():
    from app.backends.delivery.client import DeliveryToolClient

    client = _client_stub()
    with patch(
        "app.backends.delivery.stage_tools.axis_enabled",
        return_value=(True, None),
    ):
        with patch.object(DeliveryToolClient, "script_path", return_value=ROOT / "dummy.py"):
            with patch.object(
                client,
                "_call_import",
                return_value={"error": "boom", "hits": []},
            ):
                with patch(
                    "app.backends.delivery.client.PURE_PYTHON_TOOLS",
                    frozenset({"toy"}),
                ):
                    with patch(
                        "app.backends.delivery.client.SCRIPT_MAP",
                        {"toy": "x.py"},
                    ):
                        out = client.call("toy", {"q": 1})
    assert out.get("ok") is False
    assert client._recent_calls == {}


def test_client_success_enters_dedupe():
    from app.backends.delivery.client import DeliveryToolClient

    client = _client_stub()
    with patch(
        "app.backends.delivery.stage_tools.axis_enabled",
        return_value=(True, None),
    ):
        with patch.object(DeliveryToolClient, "script_path", return_value=ROOT / "dummy.py"):
            with patch.object(
                client,
                "_call_import",
                return_value={"ok": True, "hits": [{"alias": "PTBP1"}]},
            ):
                with patch(
                    "app.backends.delivery.client.PURE_PYTHON_TOOLS",
                    frozenset({"toy"}),
                ):
                    with patch(
                        "app.backends.delivery.client.SCRIPT_MAP",
                        {"toy": "x.py"},
                    ):
                        out1 = client.call("toy", {"q": 1})
                        out2 = client.call("toy", {"q": 1})
    assert out1.get("ok") is True
    assert out2.get("_deduped") is True
    assert len(client._recent_calls) == 1


def test_retrieve_guard_fail_closed_on_exception():
    from app.backends.delivery.registry import DeliveryBackedTool
    import nanobot.agent.tools.rbp.turn_guards as tg

    tool = DeliveryBackedTool(
        tool_name="esm_similarity",
        description="x",
        parameters={"type": "object"},
        client=None,
        delivery_name="esm_similarity",
    )
    with patch.object(tg, "retrieve_blocked_reason", side_effect=RuntimeError("guards down")):
        raw = asyncio.run(tool.execute(sequence="M" * 40))
    env = json.loads(raw)
    assert env.get("status") == "error"
    assert "turn_guard_unavailable" in str(env.get("reason") or "")


def test_script_path_rejects_escape(tmp_path, monkeypatch):
    from app.backends.delivery import client as client_mod

    root = tmp_path / "delivery"
    root.mkdir()
    outside = tmp_path / "evil.py"
    outside.write_text("# evil\n", encoding="utf-8")
    link = root / "tools" / "evil.py"
    link.parent.mkdir(parents=True)
    link.symlink_to(outside)

    c = client_mod.DeliveryToolClient.__new__(client_mod.DeliveryToolClient)
    c.root = root
    monkeypatch.setitem(client_mod.SCRIPT_MAP, "evil_tool", "tools/evil.py")
    try:
        c.script_path("evil_tool")
        assert False, "expected escape to raise"
    except FileNotFoundError as e:
        assert "escapes DELIVERY_ROOT" in str(e)
