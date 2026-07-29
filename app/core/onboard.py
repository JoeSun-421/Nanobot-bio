# -*- coding: utf-8 -*-
"""LLM setup for the RNA–RBP agent.

Persists provider + model in ``~/.nanobot/config.json`` and stores the API key
in repo-root ``nanobot-bio/.env`` (gitignored), referenced as ``${ENV_VAR}``
from config so secrets are not committed. ``Nanobot.from_config`` expands the
refs after ``load_dotenv``.
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

# No product default provider — the user must pick one during onboard / configure.
# Nanobot schema may still say ``provider: "auto"``; we treat that as unset.

# Curated model catalogs (API model ids). Order = picker order (not a default).
# Vendors map to nanobot ``providers.<name>`` registry keys.
PROVIDER_MODELS: dict[str, tuple[str, ...]] = {
    # OpenAI: GPT-5.6 Sol is the current flagship (gpt-5.6 aliases to it).
    "openai": (
        "gpt-5.6",
        "gpt-5.6-terra",
        "gpt-5.6-luna",
        "gpt-5.5",
        "gpt-5.4",
        "gpt-4.1",
    ),
    # Anthropic: start with Opus 5; Fable 5 is highest capability.
    "anthropic": (
        "claude-opus-5",
        "claude-fable-5",
        "claude-sonnet-5",
        "claude-haiku-4-5",
        "claude-opus-4-8",
        "claude-sonnet-4-6",
    ),
    # Google Gemini: 3.1 Pro preview flagship; 3.6 Flash is current Flash GA.
    "gemini": (
        "gemini-3.1-pro-preview",
        "gemini-3.6-flash",
        "gemini-3.5-flash",
        "gemini-3.5-flash-lite",
        "gemini-2.5-pro",
    ),
    # OpenRouter: curated cross-vendor slugs (optional gateway).
    "openrouter": (
        "anthropic/claude-opus-5",
        "openai/gpt-5.6",
        "google/gemini-3.1-pro-preview",
        "deepseek/deepseek-v4-pro",
        "qwen/qwen3.7-max",
    ),
    # DeepSeek: legacy deepseek-chat / deepseek-reasoner retired after 2026-07-24.
    "deepseek": (
        "deepseek-v4-pro",
        "deepseek-v4-flash",
    ),
    # DashScope / Qwen: 3.7 Max flagship; 3.6 Plus/Flash recommended workhorses.
    "dashscope": (
        "qwen3.7-max",
        "qwen3.7-plus",
        "qwen3.6-plus",
        "qwen3.6-flash",
        "qwen3-max",
    ),
    # Zhipu / Z.AI BigModel (lowercase ids).
    "zhipu": (
        "glm-5.1",
        "glm-5",
        "glm-4.7",
        "glm-4.6",
        "glm-4-flash",
    ),
    # Moonshot / Kimi: K3 is current flagship; kimi-latest / moonshot-v1 sunsetting.
    "moonshot": (
        "kimi-k3",
        "kimi-k2.7-code",
        "kimi-k2.7-code-highspeed",
        "kimi-k2.6",
    ),
    # Mistral: Medium 3.5 is current frontier; Magistral line is deprecated.
    "mistral": (
        "mistral-medium-latest",
        "mistral-large-latest",
        "mistral-small-latest",
        "codestral-latest",
    ),
    # MiniMax: M3 is latest M-series; keep recent M2.x options.
    "minimax": (
        "MiniMax-M3",
        "MiniMax-M2.7",
        "MiniMax-M2.5",
        "MiniMax-M2",
    ),
    # Groq: Llama 3.3 / Qwen3-32B deprecating; prefer GPT-OSS + Qwen 3.6.
    "groq": (
        "openai/gpt-oss-120b",
        "openai/gpt-oss-20b",
        "qwen/qwen3.6-27b",
    ),
    # SiliconFlow: org-prefixed hosted model ids.
    "siliconflow": (
        "deepseek-ai/DeepSeek-V4-Pro",
        "deepseek-ai/DeepSeek-V4-Flash",
        "Qwen/Qwen3.5-397B-A17B",
        "Qwen/Qwen3.6-27B",
    ),
}

# Featured vendors shown in the interactive picker (nanobot registry names).
# First entry is list order only — not a pre-selected product default.
FEATURED: tuple[tuple[str, str], ...] = tuple(
    (name, models[0]) for name, models in PROVIDER_MODELS.items()
)

_OTHER_MODEL = "__other__"

# Product env var names for curated vendors (keys live in nanobot-bio/.env only).
_FALLBACK_ENV_KEYS: dict[str, str] = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "dashscope": "DASHSCOPE_API_KEY",
    "zhipu": "ZAI_API_KEY",
    "moonshot": "MOONSHOT_API_KEY",
    "mistral": "MISTRAL_API_KEY",
    "minimax": "MINIMAX_API_KEY",
    "groq": "GROQ_API_KEY",
    "siliconflow": "SILICONFLOW_API_KEY",
    "custom": "CUSTOM_API_KEY",
}

# Env vars we prefer from repo ``.env`` over stale shell exports.
LLM_ENV_KEY_NAMES: tuple[str, ...] = tuple(sorted(set(_FALLBACK_ENV_KEYS.values())))


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


def env_key_for(provider: str) -> str:
    """Env var name for this provider's API key (stored in ``.env`` as plaintext)."""
    if provider in _FALLBACK_ENV_KEYS:
        return _FALLBACK_ENV_KEYS[provider]
    try:
        from nanobot.providers.registry import find_by_name

        spec = find_by_name(provider)
        if spec and spec.env_key:
            return spec.env_key
    except Exception:
        pass
    # Unknown vendor: dedicated var, never silently reuse OPENAI_API_KEY.
    safe = "".join(c if c.isalnum() else "_" for c in provider.strip().upper())
    return f"{safe or 'CUSTOM'}_API_KEY"


def dotenv_path() -> Path:
    from app.dotenv_util import default_dotenv_path

    return default_dotenv_path()


def _is_env_ref(value: str | None) -> bool:
    if not value:
        return False
    v = value.strip()
    return v.startswith("${") and v.endswith("}") and len(v) > 3


def _env_ref_name(value: str) -> str:
    return value.strip()[2:-1]


def _resolve_key_value(raw: str | None, *, env_name: str | None = None) -> str | None:
    """Prefer environ / .env over plaintext config. Never log the result."""
    if env_name:
        env_val = (os.environ.get(env_name) or "").strip()
        if env_val:
            return env_val
    if not raw:
        return None
    raw = str(raw).strip()
    if not raw:
        return None
    if _is_env_ref(raw):
        return (os.environ.get(_env_ref_name(raw)) or "").strip() or None
    return raw


def load_config(path: Path = DEFAULT_CONFIG) -> dict:
    """Read the existing config, or synthesize nanobot defaults if absent.

    Does **not** invent a provider — the user must pick one during onboard.
    """
    path = Path(path).expanduser()
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    try:
        from nanobot.config.schema import Config

        data = Config().model_dump(by_alias=True, mode="json")
    except Exception:
        data = {"agents": {"defaults": {}}, "providers": {}}
    defaults = data.setdefault("agents", {}).setdefault("defaults", {})
    # Nanobot schema defaults provider to "auto"; treat as unset for product UX.
    if str(defaults.get("provider") or "").strip() in ("", "auto"):
        defaults["provider"] = ""
        defaults["model"] = defaults.get("model") or ""
    defaults.setdefault("botName", "RNA–RBP")
    return data


def active_provider_model(cfg: dict | None = None) -> tuple[str, str]:
    """Return (provider, model) from env / config. Empty provider if unset.

    Never invents a vendor (no OpenAI/DeepSeek/auto fallback).
    """
    cfg = cfg if cfg is not None else {}
    defaults = (cfg.get("agents") or {}).get("defaults") or {}
    provider = (
        (os.environ.get("RBP_LLM_PROVIDER") or "").strip()
        or str(defaults.get("provider") or "").strip()
    )
    if provider == "auto":
        provider = ""
    model = (
        (os.environ.get("RBP_LLM_MODEL") or "").strip()
        or str(defaults.get("model") or "").strip()
    )
    if provider and not model:
        catalog = models_for(provider)
        model = catalog[0] if catalog else ""
    return provider, model


def llm_is_configured(path: Path = DEFAULT_CONFIG) -> bool:
    """True when a provider was chosen and has a usable API key (env preferred)."""
    path = Path(path).expanduser()
    prepare_llm_config(path, persist=False)
    cfg = load_config(path) if path.is_file() else {}
    provider, _model = active_provider_model(cfg if path.is_file() else None)
    if not provider:
        return False
    env_name = env_key_for(provider)
    block = ((cfg.get("providers") or {}).get(provider) or {}) if cfg else {}
    raw = block.get("apiKey") or block.get("api_key")
    return bool(_resolve_key_value(raw if isinstance(raw, str) else None, env_name=env_name))


def prepare_llm_config(path: Path = DEFAULT_CONFIG, *, persist: bool = True) -> None:
    """Load ``.env``, prefer env keys over config plaintext, apply ``RBP_LLM_*``.

    When *persist* is True, migrate plaintext keys from config into ``.env`` and
    rewrite config ``apiKey`` values to ``${ENV_VAR}`` references.
    """
    from app.dotenv_util import load_dotenv, read_dotenv_keys, upsert_dotenv

    env_file = dotenv_path()
    load_dotenv(env_file, override=False)

    # Prefer values present in the repo ``.env`` over stale shell exports for
    # known LLM key vars (and RBP_LLM_*), matching product preference for .env.
    dotenv_vals = read_dotenv_keys(env_file)
    prefer_exact = set(LLM_ENV_KEY_NAMES) | {
        "ZHIPUAI_API_KEY",  # zhipu registry env_extra
        "HF_TOKEN",
    }
    for k, v in dotenv_vals.items():
        if not v:
            continue
        if k.startswith("RBP_LLM_") or k.endswith("_API_KEY") or k in prefer_exact:
            os.environ[k] = v

    if not path.is_file():
        return

    cfg = json.loads(path.read_text(encoding="utf-8"))
    defaults = cfg.setdefault("agents", {}).setdefault("defaults", {})
    providers = cfg.setdefault("providers", {})
    changed = False

    env_provider = (os.environ.get("RBP_LLM_PROVIDER") or "").strip()
    env_model = (os.environ.get("RBP_LLM_MODEL") or "").strip()
    if env_provider and defaults.get("provider") != env_provider:
        defaults["provider"] = env_provider
        changed = True
    if env_model and defaults.get("model") != env_model:
        defaults["model"] = env_model
        changed = True

    # Clear nanobot's "auto" sentinel — never invent OpenAI/DeepSeek/etc.
    if str(defaults.get("provider") or "").strip() == "auto":
        defaults["provider"] = ""
        changed = True

    for name, block in list(providers.items()):
        if not isinstance(block, dict):
            continue
        env_name = env_key_for(str(name))
        raw = block.get("apiKey") or block.get("api_key")
        raw_s = str(raw).strip() if raw else ""
        env_val = (os.environ.get(env_name) or "").strip()
        ref = f"${{{env_name}}}"

        if env_val:
            # Prefer .env / environ: keep only a reference in config.
            if block.get("apiKey") != ref:
                block["apiKey"] = ref
                block.pop("api_key", None)
                changed = True
        elif raw_s and not _is_env_ref(raw_s):
            # Migrate plaintext secret out of config.json into .env.
            if persist:
                upsert_dotenv(env_name, raw_s, path=env_file)
                block["apiKey"] = ref
                block.pop("api_key", None)
                changed = True
        elif raw_s and _is_env_ref(raw_s) and _env_ref_name(raw_s) != env_name:
            # Normalize wrong/legacy refs (e.g. siliconflow → OPENAI_API_KEY).
            if persist:
                block["apiKey"] = ref
                block.pop("api_key", None)
                changed = True

    if changed and persist:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        try:
            path.chmod(0o600)
        except OSError:
            pass


def save_provider(
    *,
    provider: str,
    model: str,
    api_key: Optional[str] = None,
    api_base: Optional[str] = None,
    path: Path = DEFAULT_CONFIG,
) -> Path:
    """Persist provider + model; store API key in ``.env`` and reference it."""
    from app.dotenv_util import upsert_dotenv

    path = Path(path).expanduser()
    cfg = load_config(path)
    cfg.setdefault("providers", {})
    block = dict(cfg["providers"].get(provider) or {})

    env_name = env_key_for(provider)
    key = (api_key or "").strip() or None
    if key:
        upsert_dotenv(env_name, key, path=dotenv_path())
        block["apiKey"] = f"${{{env_name}}}"
        # Also record which provider/model the product should use.
        upsert_dotenv("RBP_LLM_PROVIDER", provider, path=dotenv_path())
        upsert_dotenv("RBP_LLM_MODEL", model, path=dotenv_path())
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
    path = Path(path).expanduser()
    prepare_llm_config(path, persist=False)
    if not path.is_file() and not (os.environ.get("RBP_LLM_PROVIDER") or "").strip():
        return "no config"
    cfg = load_config(path) if path.is_file() else {"agents": {"defaults": {}}, "providers": {}}
    provider, model = active_provider_model(cfg if path.is_file() else None)
    if not provider:
        return "no provider selected"
    block = (cfg.get("providers") or {}).get(provider) or {}
    raw = block.get("apiKey") or block.get("api_key")
    keyed = (
        "key set"
        if _resolve_key_value(raw if isinstance(raw, str) else None, env_name=env_key_for(provider))
        else "no key"
    )
    return f"{provider} · {model or '?'} · {keyed}"


def _print_login_banner() -> None:
    try:
        from app.core.chat_ux import print_banner, Style
    except Exception:
        print("RNA–RBP Agent — LLM login", flush=True)
        return
    print_banner(
        "RNA–RBP Agent",
        "LLM login  ·  pick vendor + model  ·  key → .env",
        stream=sys.stderr,
    )
    s = Style(sys.stderr)
    env_rel = "nanobot-bio/.env"
    sys.stderr.write(
        s.dim(
            f"  API key is stored in {env_rel} (gitignored) and referenced from\n"
            f"  ~/.nanobot/config.json as ${{PROVIDER_API_KEY}}. No default provider —\n"
            f"  you must choose one.\n\n"
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
    prepare_llm_config(path, persist=True)
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
        "LLM provider (required — no default)",
        choices=choices,
        qmark="▸",
        style=qstyle,
        instruction="(↑/↓, Enter to confirm)",
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
        env_p = dotenv_path()
        sys.stderr.write(
            "\n"
            + s.green("✓ saved")
            + f"  {path}\n"
            + f"  key → {env_p}  ({env_key_for(provider)}=…)\n"
            + f"  {s.bold(provider)} · {model}\n"
            + s.dim("  Next:  rbp-agent chat   (Nanobot.from_config → Nanobot.run)\n\n")
        )
        sys.stderr.write(
            s.yellow(
                "  ⚠ API key lives in .env (gitignored). Do NOT commit it, share it,\n"
                "    or paste it into chats. Rotate/delete the key in the vendor\n"
                "    console when you are done testing.\n\n"
            )
        )
        sys.stderr.flush()
    except Exception:
        print(f"saved → {path}  [{provider} · {model}]")
        print(f"API key → {dotenv_path()} ({env_key_for(provider)})")
        print("WARNING: do not commit .env or share your API key.")
    return True


def _plain_onboard(path: Path) -> bool:
    """Non-TTY fallback: numbered menu with plain prompts."""
    print("Select an LLM provider (required — no default):")
    for i, (n, dm) in enumerate(FEATURED, 1):
        print(f"  {i}. {_display_name(n)}  (suggested model {dm})")
    print(f"  {len(FEATURED) + 1}. Custom (OpenAI-compatible)")
    raw = input("number › ").strip()
    if not raw:
        print("aborted: choose a provider number (no default)")
        return False
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
        mraw = input("model number › ").strip()
        if not mraw:
            print("aborted: choose a model (no default)")
            return False
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
        model = input("model id › ").strip()

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
    print(f"API key → {dotenv_path()} ({env_key_for(provider)})")
    print("WARNING: do not commit .env or share your API key.")
    return True
