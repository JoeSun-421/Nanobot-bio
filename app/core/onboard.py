# -*- coding: utf-8 -*-
"""LLM setup for the RNA–RBP agent.

Writes provider + API key + model into ``~/.nanobot/config.json`` using
nanobot's provider registry — the same config ``Nanobot.from_config`` loads.

Users pick a **vendor** then a **model** (curated 2026 mainstream IDs, or type
any model id the vendor accepts).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Optional

DEFAULT_CONFIG = Path(
    os.environ.get("NANOBOT_CONFIG", "~/.nanobot/config.json")
).expanduser()

# Curated model catalogs (API model ids). Order = picker order.
# Vendors map to nanobot ``providers.<name>`` registry keys.
PROVIDER_MODELS: dict[str, tuple[str, ...]] = {
    "openai": (
        "gpt-5.5",
        "gpt-5.4",
        "gpt-4.1",
        "gpt-4o",
        "o3",
        "o4-mini",
    ),
    "anthropic": (
        "claude-opus-4-6",
        "claude-sonnet-4-6",
        "claude-haiku-4-5",
        "claude-opus-4-5",
        "claude-sonnet-4-5",
    ),
    "deepseek": (
        "deepseek-chat",
        "deepseek-reasoner",
        "deepseek-v4-pro",
        "deepseek-v4-flash",
    ),
    "gemini": (
        "gemini-2.5-pro",
        "gemini-2.5-flash",
        "gemini-3.1-pro-preview",
        "gemini-3-flash-preview",
        "gemini-2.0-flash",
    ),
    "dashscope": (
        "qwen-max",
        "qwen-plus",
        "qwen-turbo",
        "qwen3-max",
        "qwen3-plus",
    ),
    "zhipu": (
        "glm-5",
        "glm-4.6",
        "glm-4.5",
        "glm-4-flash",
    ),
    "moonshot": (
        "kimi-k2.5",
        "kimi-k2.6",
        "kimi-latest",
        "moonshot-v1-128k",
    ),
    "mistral": (
        "mistral-large-latest",
        "mistral-medium-latest",
        "magistral-medium-latest",
        "codestral-latest",
    ),
    "minimax": (
        "MiniMax-M2",
        "MiniMax-Text-01",
    ),
    "openrouter": (
        "anthropic/claude-sonnet-4.5",
        "openai/gpt-4o",
        "google/gemini-2.5-pro",
        "deepseek/deepseek-chat",
        "qwen/qwen3-max",
    ),
    "groq": (
        "llama-3.3-70b-versatile",
        "openai/gpt-oss-120b",
        "qwen/qwen3-32b",
    ),
    "siliconflow": (
        "deepseek-ai/DeepSeek-V3",
        "Qwen/Qwen3-235B-A22B",
        "moonshotai/Kimi-K2-Instruct",
    ),
}

# Featured vendors shown in the interactive picker (nanobot registry names).
FEATURED: tuple[tuple[str, str], ...] = tuple(
    (name, models[0]) for name, models in PROVIDER_MODELS.items()
)

_OTHER_MODEL = "__other__"


def models_for(provider: str) -> tuple[str, ...]:
    return PROVIDER_MODELS.get(provider, ())


def list_models_text() -> str:
    lines = ["Curated LLM vendors → models (type any id the vendor accepts):", ""]
    for name, models in PROVIDER_MODELS.items():
        lines.append(f"  {_display_name(name)}  [{name}]")
        for m in models:
            lines.append(f"    - {m}")
        lines.append("")
    lines.append("  Custom  [custom]  — any OpenAI-compatible base URL + model id")
    return "\n".join(lines)


def _display_name(name: str) -> str:
    try:
        from nanobot.providers.registry import find_by_name

        spec = find_by_name(name)
        if spec:
            return spec.label
    except Exception:
        pass
    labels = {
        "openai": "OpenAI",
        "anthropic": "Anthropic",
        "deepseek": "DeepSeek",
        "gemini": "Google Gemini",
        "dashscope": "Alibaba Qwen",
        "zhipu": "Zhipu GLM",
        "moonshot": "Moonshot Kimi",
        "mistral": "Mistral",
        "minimax": "MiniMax",
        "openrouter": "OpenRouter",
        "groq": "Groq",
        "siliconflow": "SiliconFlow",
        "custom": "Custom",
    }
    return labels.get(name, name.title())


def _needs_api_base(name: str) -> bool:
    return name == "custom"


def load_config() -> dict:
    """Read the existing config, or synthesize nanobot defaults if absent."""
    if DEFAULT_CONFIG.is_file():
        return json.loads(DEFAULT_CONFIG.read_text(encoding="utf-8"))
    try:
        from nanobot.config.schema import Config

        return Config().model_dump(by_alias=True, mode="json")
    except Exception:
        return {"agents": {"defaults": {}}, "providers": {}}


def save_provider(
    *,
    provider: str,
    model: str,
    api_key: Optional[str] = None,
    api_base: Optional[str] = None,
    path: Path = DEFAULT_CONFIG,
) -> Path:
    """Persist provider credentials + active model into the nanobot config."""
    cfg = load_config()
    cfg.setdefault("providers", {})
    block = dict(cfg["providers"].get(provider) or {})
    if api_key is not None:
        block["apiKey"] = api_key
    if api_base:
        block["apiBase"] = api_base
    cfg["providers"][provider] = block

    defaults = cfg.setdefault("agents", {}).setdefault("defaults", {})
    defaults["provider"] = provider
    defaults["model"] = model
    defaults.setdefault("botName", "RNA–RBP")
    defaults.setdefault("botIcon", "")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return path


def current_summary(path: Path = DEFAULT_CONFIG) -> str:
    """One-line description of the active provider/model, keys redacted."""
    if not path.is_file():
        return "no config"
    cfg = json.loads(path.read_text(encoding="utf-8"))
    d = (cfg.get("agents") or {}).get("defaults") or {}
    provider = d.get("provider") or "auto"
    model = d.get("model") or "?"
    block = (cfg.get("providers") or {}).get(provider) or {}
    keyed = "key set" if (block.get("apiKey") or block.get("api_key")) else "no key"
    return f"{provider} · {model} · {keyed}"


def _print_login_banner() -> None:
    try:
        from app.core.chat_ux import print_banner, Style
    except Exception:
        print("RNA–RBP Agent — LLM login", flush=True)
        return
    print_banner(
        "RNA–RBP Agent",
        "LLM login  ·  pick vendor + model  ·  → ~/.nanobot/config.json",
        stream=sys.stderr,
    )
    s = Style(sys.stderr)
    sys.stderr.write(
        s.dim(
            "  Nanobot.from_config reads this file. Choose any supported vendor;\n"
            "  then pick a model (or type a custom model id).\n\n"
        )
    )
    sys.stderr.flush()


def _pick_model_interactive(
    provider: str,
    default_model: str,
    *,
    questionary,
    qstyle,
) -> Optional[str]:
    """Second-step model picker for a vendor."""
    catalog = list(models_for(provider))
    if not catalog:
        model = questionary.text(
            "Model id",
            default=default_model or "",
            qmark="▸",
            style=qstyle,
        ).ask()
        return (model or "").strip() or None

    choices = [questionary.Choice(title=m, value=m) for m in catalog]
    choices.append(
        questionary.Choice(title="Other… (type model id)", value=_OTHER_MODEL)
    )
    picked = questionary.select(
        f"Model for {_display_name(provider)}",
        choices=choices,
        qmark="▸",
        style=qstyle,
        instruction="(↑/↓, Enter)",
        default=default_model if default_model in catalog else catalog[0],
    ).ask()
    if picked is None:
        return None
    if picked == _OTHER_MODEL:
        model = questionary.text(
            "Model id",
            default=default_model or catalog[0],
            qmark="▸",
            style=qstyle,
        ).ask()
        return (model or "").strip() or None
    return str(picked).strip()


def interactive_onboard(path: Path = DEFAULT_CONFIG) -> bool:
    """Arrow-key provider + model picker + hidden key entry."""
    _print_login_banner()
    try:
        import questionary
        from questionary import Style as QStyle
    except Exception:
        return _plain_onboard(path)

    if not (os.isatty(0) and os.isatty(1)):
        return _plain_onboard(path)

    qstyle = QStyle(
        [
            ("qmark", "fg:cyan bold"),
            ("question", "bold"),
            ("answer", "fg:cyan"),
            ("pointer", "fg:cyan bold"),
            ("highlighted", "fg:cyan bold"),
            ("selected", "fg:green"),
            ("separator", "fg:#6c6c6c"),
            ("instruction", "fg:#6c6c6c"),
            ("text", ""),
        ]
    )

    choices = [
        questionary.Choice(
            title=f"{_display_name(n):<16}  {dm}",
            value=(n, dm),
        )
        for n, dm in FEATURED
    ]
    choices.append(
        questionary.Choice(
            title=f"{'Custom':<16}  OpenAI-compatible endpoint",
            value=("custom", ""),
        )
    )

    picked = questionary.select(
        "LLM provider",
        choices=choices,
        qmark="▸",
        style=qstyle,
        instruction="(↑/↓, Enter)",
    ).ask()
    if picked is None:
        return False
    provider, default_model = picked

    api_base = None
    if _needs_api_base(provider):
        api_base = questionary.text(
            "API base URL",
            qmark="▸",
            style=qstyle,
        ).ask()
        if not api_base:
            print("aborted: custom provider needs an API base URL")
            return False

    model = _pick_model_interactive(
        provider, default_model, questionary=questionary, qstyle=qstyle
    )
    if not model:
        print("aborted: model is required")
        return False

    api_key = questionary.password(
        "API key",
        qmark="▸",
        style=qstyle,
    ).ask()
    if api_key is None:
        return False

    save_provider(
        provider=provider,
        model=model,
        api_key=api_key.strip() or None,
        api_base=(api_base or "").strip() or None,
        path=path,
    )
    try:
        from app.core.chat_ux import Style

        s = Style(sys.stderr)
        sys.stderr.write(
            "\n"
            + s.green("✓ saved")
            + f"  {path}\n"
            + f"  {s.bold(provider)} · {model}\n"
            + s.dim("  Next:  rbp-agent chat   (Nanobot.from_config → Nanobot.run)\n\n")
        )
        # Secrets hygiene reminder (config.json lives outside the repo; never
        # commit it, and rotate the key when done testing).
        sys.stderr.write(
            s.yellow(
                "  ⚠ This file contains your API key. Do NOT commit it, share it,\n"
                "    or paste it into chats. Rotate/delete the key in the vendor\n"
                "    console when you are done testing.\n\n"
            )
        )
        sys.stderr.flush()
    except Exception:
        print(f"saved → {path}  [{provider} · {model}]")
        print("WARNING: this file contains your API key — do not commit or share it.")
    return True


def _plain_onboard(path: Path) -> bool:
    """Non-TTY fallback: numbered menu with plain prompts."""
    print("Select an LLM provider:")
    for i, (n, dm) in enumerate(FEATURED, 1):
        print(f"  {i}. {_display_name(n)}  (default {dm})")
    print(f"  {len(FEATURED) + 1}. Custom (OpenAI-compatible)")
    raw = input("number › ").strip()
    try:
        idx = int(raw)
    except ValueError:
        print("aborted: not a number")
        return False
    if 1 <= idx <= len(FEATURED):
        provider, default_model = FEATURED[idx - 1]
        api_base = None
    elif idx == len(FEATURED) + 1:
        provider, default_model = "custom", ""
        api_base = input("API base URL › ").strip()
        if not api_base:
            print("aborted: custom needs an API base")
            return False
    else:
        print("aborted: out of range")
        return False

    catalog = list(models_for(provider))
    if catalog:
        print(f"Models for {_display_name(provider)}:")
        for i, m in enumerate(catalog, 1):
            print(f"  {i}. {m}")
        print(f"  {len(catalog) + 1}. Other (type id)")
        mraw = input(f"model number [{default_model}] › ").strip()
        if not mraw:
            model = default_model
        else:
            try:
                mi = int(mraw)
            except ValueError:
                model = mraw  # typed id directly
            else:
                if 1 <= mi <= len(catalog):
                    model = catalog[mi - 1]
                elif mi == len(catalog) + 1:
                    model = input("model id › ").strip()
                else:
                    print("aborted: out of range")
                    return False
    else:
        model = input(f"model [{default_model}] › ").strip() or default_model

    if not model:
        print("aborted: model required")
        return False
    api_key = input("API key › ").strip()
    save_provider(
        provider=provider,
        model=model,
        api_key=api_key or None,
        api_base=api_base or None,
        path=path,
    )
    print(f"saved → {path}  [{provider} · {model}]")
    print("WARNING: this file contains your API key — do not commit or share it.")
    return True
