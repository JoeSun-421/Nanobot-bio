# -*- coding: utf-8 -*-
"""GPU-prefer device resolution + multi-vendor LLM catalog."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_resolve_device_respects_force_cpu(monkeypatch):
    monkeypatch.setenv("RHOBIND_FORCE_CPU", "1")
    monkeypatch.delenv("RHOBIND_DEVICE", raising=False)
    # Import from SoT overlay path via installed/sibling package after activate;
    # fall back to loading overlay module file if needed.
    try:
        from nanobot.agent.tools.rbp.common import resolve_device
    except ImportError:
        import importlib.util

        p = ROOT / "nanobot" / "agent" / "tools" / "rbp" / "common.py"
        spec = importlib.util.spec_from_file_location("rbp_common_sot", p)
        mod = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(mod)
        resolve_device = mod.resolve_device

    assert resolve_device("auto") == "cpu"
    assert resolve_device("cuda") == "cuda"  # explicit still honored
    assert resolve_device("cpu") == "cpu"


def test_resolve_device_explicit_cpu(monkeypatch):
    monkeypatch.delenv("RHOBIND_FORCE_CPU", raising=False)
    try:
        from nanobot.agent.tools.rbp.common import resolve_device
    except ImportError:
        import importlib.util

        p = ROOT / "nanobot" / "agent" / "tools" / "rbp" / "common.py"
        spec = importlib.util.spec_from_file_location("rbp_common_sot2", p)
        mod = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(mod)
        resolve_device = mod.resolve_device

    assert resolve_device("cpu") == "cpu"


def test_resolve_device_auto_does_not_import_torch(monkeypatch):
    """Chat startup must not pay for import torch."""
    monkeypatch.delenv("RHOBIND_FORCE_CPU", raising=False)
    monkeypatch.setenv("RHOBIND_DEVICE", "auto")
    import importlib.util

    # Load SoT module fresh so we can clear its CUDA cache
    p = ROOT / "nanobot" / "agent" / "tools" / "rbp" / "common.py"
    spec = importlib.util.spec_from_file_location("rbp_common_notorch", p)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    mod._CUDA_CACHE = None

    before = "torch" in sys.modules
    _ = mod.resolve_device("auto")
    after = "torch" in sys.modules
    if not before:
        assert not after, "resolve_device(auto) must not import torch"


def test_onboard_catalog_covers_mainstream_vendors():
    from app.core.onboard import FEATURED, PROVIDER_MODELS, list_models_text, models_for

    required = {
        "openai",
        "anthropic",
        "deepseek",
        "gemini",
        "dashscope",
        "zhipu",
        "moonshot",
        "mistral",
        "openrouter",
    }
    assert required.issubset(set(PROVIDER_MODELS))
    assert len(FEATURED) == len(PROVIDER_MODELS)
    for name in required:
        ms = models_for(name)
        assert ms, name
        assert all(isinstance(m, str) and m for m in ms)
    text = list_models_text()
    assert "OpenAI" in text or "openai" in text
    assert "gpt-" in text
    assert "claude" in text
    assert "deepseek" in text


def test_predict_schema_defaults_auto():
    from nanobot.agent.tools.rbp.predict import PredictInteractionTool

    tool = PredictInteractionTool()
    schema = tool.parameters
    props = schema.get("properties") or {}
    assert props.get("device", {}).get("default") == "auto"
