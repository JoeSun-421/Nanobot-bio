# nanobot/sdk/

Internal helpers for the high-level Nanobot Python API surface.

[English] · [中文](README.zh.md)

## Purpose

Supports `nanobot.nanobot.Nanobot` with streaming events, thin clients (session / memory / runtime), and shared types. This is **not** a second public API for product collaborators — prefer `from nanobot import Nanobot` or the App CLI.

## Layout

| File | Role |
|------|------|
| `clients.py` | `SessionClient`, `MemoryClient`, `RuntimeClient` |
| `runtime.py` | `SDKRuntimeController`, process kwargs helpers |
| `streaming.py` | `RunStream`, `SDKStreamEmitter`, streaming hook |
| `types.py` | `RunResult`, `StreamEvent`, stream event constants |
| `__init__.py` | Package note (internal helpers) |

```
nanobot/nanobot.py  (public API)
    └── nanobot/sdk/*  (internal details)
app/agent.py        (product assembly → Nanobot)
```

## Entry points

```python
from nanobot import Nanobot, RunResult, RunStream
# Types also available via nanobot.sdk.types if needed internally:
from nanobot.sdk.types import STREAM_EVENT_TOOL_COMPLETED
```

## Code examples

```python
from nanobot import Nanobot

bot = Nanobot.from_config(scientific_mode=True)
# High-level clients hung off the facade:
print(bot.sessions, bot.memory, bot.runtime)

async for event in bot.run_streamed("Ping"):
    print(event.type, getattr(event, "delta", None) or getattr(event, "content", None))
```

```bash
nanobot-bio chat|agent   # product path — preferred over sdk imports
```

## Dependencies / env

- Same LLM config as Nanobot (`~/.nanobot/config.json` / `.env`).
- Do not treat `nanobot.sdk.*` as a stable external contract across releases.

## See also

[`../README.md`](../README.md) · [`../../app/README.md`](../../app/README.md)
