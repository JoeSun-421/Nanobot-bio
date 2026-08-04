# nanobot/providers/

LLM provider adapters and factory.

[English] · [中文](README.zh.md)

> Parent package map and `$BIO_ROOT` layout: [`README.md`](../../README.md). Activate with `cd "$BIO_ROOT/nanobot-bio" && source scripts/nbio.sh`.

## Purpose

Abstracts chat/completions (and related) backends behind `LLMProvider`. Product onboard configures an OpenAI-compatible endpoint (e.g. DeepSeek) via `~/.nanobot/config.json` + `.env`; the factory (`make_provider`) builds the live provider for `Nanobot.from_config`.

## Layout

| Module | Role |
|--------|------|
| `base.py` | `LLMProvider`, `LLMResponse` |
| `factory.py` | `make_provider`, snapshots |
| `registry.py` | Provider registry helpers |
| `openai_compat_provider.py` | OpenAI-compatible (DeepSeek, etc.) |
| `anthropic_provider.py` / `azure_openai_provider.py` / `bedrock_provider.py` / … | Other backends |
| `fallback_provider.py` | Fallback chain |
| `openai_codex_provider.py` / `github_copilot_provider.py` | Extra adapters |
| `image_generation.py` / `transcription.py` | Multimodal helpers |
| [`openai_responses/`](openai_responses/README.md) | Responses API convert/parse |

## Entry points

```python
from nanobot.providers import LLMProvider, LLMResponse, OpenAICompatProvider
from nanobot.providers.factory import make_provider
from nanobot.config import load_config
```

## Code examples

```python
from nanobot.config import load_config
from nanobot.providers.factory import make_provider

cfg = load_config()
provider = make_provider(cfg)
print(type(provider).__name__)
```

```bash
nanobot-bio onboard --provider openai --model deepseek-chat
nanobot-bio doctor   # shows LLM readiness
```

## Dependencies / env

- API keys via env vars referenced from config — never hardcode.
- No delivery/GPU requirement for provider construction itself.

## See also

[`openai_responses/README.md`](openai_responses/README.md) · [`../config/README.md`](../config/README.md) · [`../../app/core/README.md`](../../app/core/README.md) (onboard)
