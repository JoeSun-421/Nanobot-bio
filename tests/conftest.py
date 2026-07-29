# -*- coding: utf-8 -*-
"""Shared pytest fixtures — delivery-optional CI, RBP turn-guard reset."""

from __future__ import annotations

from pathlib import Path

import pytest


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "requires_delivery: needs DELIVERY_ROOT / sibling rhobind_agent_delivery",
    )


def _delivery_available() -> bool:
    from app.backends.delivery.env import try_delivery_root

    return try_delivery_root() is not None


@pytest.fixture(scope="session")
def delivery_available() -> bool:
    return _delivery_available()


@pytest.fixture
def delivery_root(delivery_available: bool) -> Path:
    """Resolved delivery package root; skips when bundle is absent (public CI)."""
    from app.backends.delivery.env import try_delivery_root

    root = try_delivery_root()
    if root is None:
        pytest.skip(
            "DELIVERY_ROOT not set and sibling rhobind_agent_delivery not found"
        )
    return root


@pytest.fixture(autouse=True)
def _skip_missing_delivery_via_hook():
    """Convert delivery_root() FileNotFoundError into skip during tests.

    Central path: any call to ``app.backends.delivery.env.delivery_root()`` when
    the bundle is absent invokes pytest.skip instead of failing ~40+ tests on
    public GitHub Actions (no sibling delivery).
    """
    import app.backends.delivery.env as env_mod

    def _hook() -> None:
        pytest.skip(
            "DELIVERY_ROOT not set and sibling rhobind_agent_delivery not found "
            "(public CI without delivery bundle)"
        )

    prev = env_mod._delivery_missing_hook
    env_mod._delivery_missing_hook = _hook
    try:
        yield
    finally:
        env_mod._delivery_missing_hook = prev


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    if _delivery_available():
        return
    skip = pytest.mark.skip(
        reason="DELIVERY_ROOT / sibling rhobind_agent_delivery not found"
    )
    for item in items:
        if "requires_delivery" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(autouse=True)
def _reset_rbp_turn_guards():
    try:
        from nanobot.agent.tools.rbp.turn_guards import reset_stage_guards

        reset_stage_guards()
    except Exception:
        pass
    try:
        from nanobot.agent.tools.rbp.predict import PredictInteractionTool

        PredictInteractionTool.reset_turn_guards()
    except Exception:
        pass
    try:
        from nanobot.agent.tools.rbp.annotation import reset_tool_turn_guards

        reset_tool_turn_guards()
    except Exception:
        pass
    yield
    try:
        from nanobot.agent.tools.rbp.turn_guards import reset_stage_guards

        reset_stage_guards()
    except Exception:
        pass
