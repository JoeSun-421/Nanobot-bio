# nanobot/providers/openai_responses/

Converters/parsers for the OpenAI Responses API shape.

[English] · [中文](README.zh.md)

## Purpose

Small subpackage that translates between Nanobot’s internal message/tool structures and OpenAI Responses API payloads. Used by OpenAI-family providers when Responses mode is selected — not a standalone CLI.

## Layout

| Module | Role |
|--------|------|
| `converters.py` | Request/response conversion |
| `parsing.py` | Parse Responses API streams / objects |
| `__init__.py` | Package exports |

## Entry points

```python
from nanobot.providers.openai_responses import converters, parsing
# Or import symbols re-exported from __init__ if present
```

## Code examples

```python
from nanobot.providers import openai_responses

# Used internally by OpenAI-compatible / Responses providers.
print(openai_responses.__name__)
```

```python
from nanobot.providers.factory import make_provider
from nanobot.config import load_config

provider = make_provider(load_config())
# Provider implementation may call openai_responses converters under the hood.
```

## Dependencies / env

- Same credentials as the parent OpenAI-compatible provider.
- No science stack required.

## See also

[`../README.md`](../README.md) · [`../../README.md`](../../README.md)
