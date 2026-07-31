# nanobot/sdk/

Internal helpers for the high-level Nanobot Python API surface.

[English] · [中文](README.zh.md)

## Features

- Support modules behind `nanobot.nanobot.Nanobot` (streaming events, clients, runtime types)
- Not a second public API for product collaborators

## Implementation

| File | Role |
|------|------|
| `clients.py` | SDK client helpers |
| `runtime.py` | Runtime glue |
| `streaming.py` | Streaming event helpers |
| `types.py` | Shared types |
| `__init__.py` | Package note (internal helpers) |

Relationship:

```
nanobot/nanobot.py  (public API)
    └── nanobot/sdk/*  (internal details)
app/agent.py        (product assembly → Nanobot)
```

## How to use

Prefer the product CLI or the high-level import:

```bash
nanobot-bio chat|agent
```

```python
from nanobot import Nanobot  # or Nanobot.from_config
```

Do not treat `nanobot.sdk.*` as a stable external contract.

## Design rationale

- Keep a small public surface (`Nanobot` + CLI) while allowing internal refactor of streaming/client details.
- LLM credentials still flow through onboard / `.env` / `~/.nanobot/config.json` — never hardcoded here.

## See also

[`../README.md`](../README.md) · [`../../app/README.md`](../../app/README.md)
