# -*- coding: utf-8 -*-
"""Focused tests for the registry-driven delivery smoke matrix."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.cert import smoke_delivery_tools as smoke


class FakeClient:
    def __init__(self, outputs: dict[str, dict] | None = None):
        self.outputs = outputs or {}
        self.calls: list[tuple[str, dict]] = []

    def call(self, name: str, payload: dict) -> dict:
        self.calls.append((name, payload))
        return dict(self.outputs.get(name) or {"ok": True, "tool": name})


def _row(name: str, *, network: bool = False) -> dict:
    return {
        "name": name,
        "category": "test",
        "registry_status": "ready",
        "metadata": {
            "network": network,
            "gpu": False,
            "runtime": "s",
            "conda": None,
            "input": {},
            "output": {},
            "prerequisites": [],
            "fallback": "test fallback",
        },
        "scenario_defined": True,
    }


def test_registry_matrix_covers_every_delivery_tool_and_metadata():
    from app.backends.delivery.client import load_delivery_registry

    registry = load_delivery_registry()
    matrix, coverage = smoke.build_scenario_matrix(registry)

    assert coverage["ok"] is True
    assert len(matrix) == len(registry["tools"])
    assert {row["name"] for row in matrix} == {
        tool["name"] for tool in registry["tools"]
    }
    required = {
        "network",
        "gpu",
        "runtime",
        "conda",
        "input",
        "output",
        "prerequisites",
        "fallback",
    }
    assert all(required <= set(row["metadata"]) for row in matrix)


def test_external_skips_and_cached_af3_are_separate_from_failures():
    client = FakeClient()
    rows = smoke.run_scenario_matrix(
        [
            _row("structure_fetch", network=True),
            _row("structure_predict_af3", network=True),
            _row("resolve_rbp"),
        ],
        client=client,
        af3_client=client,
        device="cpu",
        network=False,
        run_af3=False,
        sequence="ACDEFGHIK",
        cached_af3=lambda: {"source": "af3_status", "artifact": "/tmp/model.cif"},
    )

    assert [row["status"] for row in rows] == [
        smoke.STATUS_SKIPPED,
        smoke.STATUS_CACHED,
        smoke.STATUS_PASSED,
    ]
    assert [name for name, _ in client.calls] == ["resolve_rbp"]


def test_af3_flag_executes_bridge_even_without_network_flag():
    client = FakeClient()
    af3_client = FakeClient(
        {"structure_predict_af3": {"ok": True, "structure": "/tmp/model.cif"}}
    )

    rows = smoke.run_scenario_matrix(
        [_row("structure_predict_af3", network=True)],
        client=client,
        af3_client=af3_client,
        device="cuda",
        network=False,
        run_af3=True,
        sequence="ACDEFGHIK",
    )

    assert rows[0]["status"] == smoke.STATUS_PASSED
    assert client.calls == []
    assert af3_client.calls[0][0] == "structure_predict_af3"


def test_report_summary_and_capability_status(tmp_path: Path):
    results = [
        {**_row("resolve_rbp"), "status": smoke.STATUS_PASSED},
        {**_row("structure_fetch"), "status": smoke.STATUS_SKIPPED},
    ]
    report = smoke.build_report(
        registry={"schema_version": "1.0", "tools": [{}, {}]},
        coverage={"ok": True},
        results=results,
        options={"network": False},
    )
    path = tmp_path / "delivery-smoke.json"
    path.write_text(json.dumps(report), encoding="utf-8")

    from app.core.capability_matrix import delivery_smoke_report_status

    status = delivery_smoke_report_status(path)
    assert report["status"] == "pass"
    assert report["summary"][smoke.STATUS_SKIPPED] == 1
    assert status["status"] == "ready"
    assert status["coverage_ok"] is True
