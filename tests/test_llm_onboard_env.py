# -*- coding: utf-8 -*-
"""LLM onboard / missing-key chat bootstrap."""

from __future__ import annotations

import json
import os
from pathlib import Path

from app.core import onboard
from app.dotenv_util import read_dotenv_keys, upsert_dotenv


def test_no_default_provider(monkeypatch):
    assert getattr(onboard, "DEFAULT_PROVIDER", None) is None
    assert getattr(onboard, "DEFAULT_MODEL", None) is None
    # Hermetic: ignore shell / repo .env RBP_LLM_* so CI and local agree.
    monkeypatch.delenv("RBP_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("RBP_LLM_MODEL", raising=False)
    # Product must not invent a vendor when unset.
    provider, model = onboard.active_provider_model({})
    assert provider == ""
    assert model == ""


def test_env_key_for_all_featured_vendors():
    assert onboard.env_key_for("openai") == "OPENAI_API_KEY"
    assert onboard.env_key_for("anthropic") == "ANTHROPIC_API_KEY"
    assert onboard.env_key_for("deepseek") == "DEEPSEEK_API_KEY"
    assert onboard.env_key_for("siliconflow") == "SILICONFLOW_API_KEY"
    assert onboard.env_key_for("custom") == "CUSTOM_API_KEY"
    for name in onboard.PROVIDER_MODELS:
        key = onboard.env_key_for(name)
        assert key.endswith("_API_KEY"), (name, key)
        assert key in onboard.LLM_ENV_KEY_NAMES


def test_save_provider_writes_dotenv_ref(tmp_path, monkeypatch):
    cfg = tmp_path / "config.json"
    env = tmp_path / ".env"
    monkeypatch.setattr(onboard, "DEFAULT_CONFIG", cfg)
    monkeypatch.setattr(onboard, "dotenv_path", lambda: env)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("RBP_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("RBP_LLM_MODEL", raising=False)

    onboard.save_provider(
        provider="openai",
        model="gpt-4o",
        api_key="sk-test-not-real",
        path=cfg,
    )

    data = json.loads(cfg.read_text(encoding="utf-8"))
    assert data["agents"]["defaults"]["provider"] == "openai"
    assert data["agents"]["defaults"]["model"] == "gpt-4o"
    assert data["providers"]["openai"]["apiKey"] == "${OPENAI_API_KEY}"
    # Secret must not appear as plaintext in config.
    assert "sk-test-not-real" not in cfg.read_text(encoding="utf-8")

    keys = read_dotenv_keys(env)
    assert keys["OPENAI_API_KEY"] == "sk-test-not-real"
    assert keys["RBP_LLM_PROVIDER"] == "openai"
    assert keys["RBP_LLM_MODEL"] == "gpt-4o"
    assert os.environ.get("OPENAI_API_KEY") == "sk-test-not-real"


def test_save_deepseek_uses_dedicated_env(tmp_path, monkeypatch):
    cfg = tmp_path / "config.json"
    env = tmp_path / ".env"
    monkeypatch.setattr(onboard, "DEFAULT_CONFIG", cfg)
    monkeypatch.setattr(onboard, "dotenv_path", lambda: env)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    onboard.save_provider(
        provider="deepseek",
        model="deepseek-v4-pro",
        api_key="sk-ds-test",
        path=cfg,
    )
    data = json.loads(cfg.read_text(encoding="utf-8"))
    assert data["providers"]["deepseek"]["apiKey"] == "${DEEPSEEK_API_KEY}"
    assert data["agents"]["defaults"]["model"] == "deepseek-v4-pro"
    assert "sk-ds-test" not in cfg.read_text(encoding="utf-8")
    assert read_dotenv_keys(env)["DEEPSEEK_API_KEY"] == "sk-ds-test"


def test_llm_is_configured_false_without_key(tmp_path, monkeypatch):
    cfg = tmp_path / "config.json"
    env = tmp_path / ".env"
    monkeypatch.setattr(onboard, "DEFAULT_CONFIG", cfg)
    monkeypatch.setattr(onboard, "dotenv_path", lambda: env)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("RBP_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("RBP_LLM_MODEL", raising=False)

    cfg.write_text(
        json.dumps(
            {
                "agents": {"defaults": {"provider": "openai", "model": "gpt-4o"}},
                "providers": {"openai": {"apiKey": ""}},
            }
        ),
        encoding="utf-8",
    )
    assert onboard.llm_is_configured(cfg) is False


def test_llm_is_configured_false_without_provider(tmp_path, monkeypatch):
    cfg = tmp_path / "config.json"
    env = tmp_path / ".env"
    monkeypatch.setattr(onboard, "DEFAULT_CONFIG", cfg)
    monkeypatch.setattr(onboard, "dotenv_path", lambda: env)
    monkeypatch.delenv("RBP_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    cfg.write_text(
        json.dumps(
            {
                "agents": {"defaults": {"provider": "", "model": ""}},
                "providers": {},
            }
        ),
        encoding="utf-8",
    )
    upsert_dotenv("OPENAI_API_KEY", "sk-orphan", path=env)
    assert onboard.llm_is_configured(cfg) is False


def test_llm_is_configured_true_from_dotenv(tmp_path, monkeypatch):
    cfg = tmp_path / "config.json"
    env = tmp_path / ".env"
    monkeypatch.setattr(onboard, "DEFAULT_CONFIG", cfg)
    monkeypatch.setattr(onboard, "dotenv_path", lambda: env)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("RBP_LLM_PROVIDER", raising=False)

    cfg.write_text(
        json.dumps(
            {
                "agents": {"defaults": {"provider": "openai", "model": "gpt-4o"}},
                "providers": {"openai": {"apiKey": "${OPENAI_API_KEY}"}},
            }
        ),
        encoding="utf-8",
    )
    upsert_dotenv("OPENAI_API_KEY", "sk-from-env", path=env)
    assert onboard.llm_is_configured(cfg) is True


def test_prepare_prefers_dotenv_over_config_plaintext(tmp_path, monkeypatch):
    cfg = tmp_path / "config.json"
    env = tmp_path / ".env"
    monkeypatch.setattr(onboard, "DEFAULT_CONFIG", cfg)
    monkeypatch.setattr(onboard, "dotenv_path", lambda: env)

    cfg.write_text(
        json.dumps(
            {
                "agents": {"defaults": {"provider": "openai", "model": "gpt-4o"}},
                "providers": {"openai": {"apiKey": "sk-old-in-config"}},
            }
        ),
        encoding="utf-8",
    )
    upsert_dotenv("OPENAI_API_KEY", "sk-preferred-env", path=env, apply_environ=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    onboard.prepare_llm_config(cfg, persist=True)

    data = json.loads(cfg.read_text(encoding="utf-8"))
    assert data["providers"]["openai"]["apiKey"] == "${OPENAI_API_KEY}"
    assert "sk-old-in-config" not in cfg.read_text(encoding="utf-8")
    assert os.environ["OPENAI_API_KEY"] == "sk-preferred-env"


def test_prepare_does_not_invent_openai_from_auto(tmp_path, monkeypatch):
    cfg = tmp_path / "config.json"
    env = tmp_path / ".env"
    monkeypatch.setattr(onboard, "DEFAULT_CONFIG", cfg)
    monkeypatch.setattr(onboard, "dotenv_path", lambda: env)
    monkeypatch.delenv("RBP_LLM_PROVIDER", raising=False)

    cfg.write_text(
        json.dumps(
            {
                "agents": {"defaults": {"provider": "auto", "model": "gpt-4o"}},
                "providers": {},
            }
        ),
        encoding="utf-8",
    )
    onboard.prepare_llm_config(cfg, persist=True)
    data = json.loads(cfg.read_text(encoding="utf-8"))
    assert data["agents"]["defaults"]["provider"] == ""
    assert onboard.llm_is_configured(cfg) is False


def test_ensure_llm_triggers_onboard_when_key_missing(tmp_path, monkeypatch):
    """Missing key → interactive onboard path (not a silent config-file-exists OK)."""
    from app.cli import user as user_cli

    cfg = tmp_path / "config.json"
    env = tmp_path / ".env"
    cfg.write_text(
        json.dumps(
            {
                "agents": {"defaults": {"provider": "deepseek", "model": "deepseek-v4-pro"}},
                "providers": {"deepseek": {"apiKey": ""}},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("NANOBOT_CONFIG", str(cfg))
    monkeypatch.setattr(onboard, "DEFAULT_CONFIG", cfg)
    monkeypatch.setattr(onboard, "dotenv_path", lambda: env)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("RBP_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("RBP_LLM_MODEL", raising=False)

    called = {"n": 0}

    def _fake_onboard(path=None):
        called["n"] += 1
        onboard.save_provider(
            provider="openai",
            model="gpt-4o",
            api_key="sk-after-onboard",
            path=cfg,
        )
        return True

    monkeypatch.setattr(user_cli.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(user_cli.sys.stdout, "isatty", lambda: True)
    monkeypatch.setattr(onboard, "interactive_onboard", _fake_onboard)
    # user_cli imports interactive_onboard inside the function — patch the module attr used.
    monkeypatch.setattr(
        "app.core.onboard.interactive_onboard",
        _fake_onboard,
    )

    rc = user_cli._ensure_llm_configured()
    assert rc == 0
    assert called["n"] == 1
    assert onboard.llm_is_configured(cfg) is True
    data = json.loads(cfg.read_text(encoding="utf-8"))
    assert data["agents"]["defaults"]["provider"] == "openai"


def test_ensure_llm_noninteractive_fails_without_key(tmp_path, monkeypatch):
    from app.cli import user as user_cli

    cfg = tmp_path / "config.json"
    env = tmp_path / ".env"
    cfg.write_text(
        json.dumps(
            {
                "agents": {"defaults": {"provider": "openai", "model": "gpt-4o"}},
                "providers": {"openai": {"apiKey": ""}},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("NANOBOT_CONFIG", str(cfg))
    monkeypatch.setattr(onboard, "DEFAULT_CONFIG", cfg)
    monkeypatch.setattr(onboard, "dotenv_path", lambda: env)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("RBP_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("RBP_LLM_MODEL", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setattr(user_cli.sys.stdin, "isatty", lambda: False)
    monkeypatch.setattr(user_cli.sys.stdout, "isatty", lambda: False)

    assert onboard.llm_is_configured(cfg) is False
    assert user_cli._ensure_llm_configured() == 1
