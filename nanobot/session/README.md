# nanobot/session/

Session persistence and turn-continuation helpers.

[English] · [中文](README.zh.md)

## Purpose

Owns `Session` / `SessionManager` for storing conversation state. In nanobot-bio, canonical session files live under `artifacts/sessions/` (with workspace symlinks) — see [`docs/guides/MEMORY_AND_SESSIONS.zh.md`](../../docs/guides/MEMORY_AND_SESSIONS.zh.md) and [`ARCHITECTURE.md`](../../ARCHITECTURE.md) §2.

## Layout

| Module | Role |
|--------|------|
| `manager.py` | `Session`, `SessionManager` |
| `keys.py` | Session key helpers |
| `goal_state.py` | Goal-state tracking |
| `turn_continuation.py` | Multi-turn continuation |
| `webui_turns.py` | Legacy WebUI turn helpers |

## Entry points

```python
from nanobot.session import SessionManager, Session
```

## Code examples

```python
from nanobot import Nanobot
from app.core.paths import SESSIONS, ensure_artifact_dirs

ensure_artifact_dirs()
print("canonical sessions dir:", SESSIONS)

bot = Nanobot.from_config(workspace="workspace", scientific_mode=True)
# Session APIs are available via the facade:
print(bot.sessions)
```

```bash
ls artifacts/sessions/   # canonical store
nanobot-bio chat         # creates/updates session artifacts
```

## Dependencies / env

- Disk under package `artifacts/sessions` (via `app.core.paths`).
- Ephemeral turns (`ephemeral=True`) avoid polluting long-lived science sessions.

## See also

[`../README.md`](../README.md) · [`../../artifacts/README.md`](../../artifacts/README.md) · [`../../docs/guides/MEMORY_AND_SESSIONS.zh.md`](../../docs/guides/MEMORY_AND_SESSIONS.zh.md)
