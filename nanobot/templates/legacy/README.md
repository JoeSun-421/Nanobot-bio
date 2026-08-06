# nanobot/templates/legacy/

Unused template residue from older Nanobot workspace layouts.

[English] · [中文](README.zh.md)

## Purpose

Package docstring: *“Unused template residue.”* Keeps historical `HEARTBEAT.md` and a nested `memory/` seed that are **not** the active prompt path. Live Jinja prompts are under [`../agent/`](../agent/README.md); current workspace bootstrap files sit at [`../`](../README.md) (`AGENTS.md` / `SOUL.md` / `USER.md`).

Do not add new product prompts here.

## Layout

| Path | Role |
|------|------|
| `HEARTBEAT.md` | Legacy heartbeat cron checklist seed |
| [`memory/`](memory/README.md) | Legacy `MEMORY.md` seed |
| `__init__.py` | Marks residue package |

## Entry points

None for product code. Prefer:

```python
from nanobot.utils.prompt_templates import render_template

render_template("agent/identity.md") # active path
```

## Code examples

```python
from pathlib import Path
from importlib.resources import files

legacy = files("nanobot") / "templates" / "legacy" / "HEARTBEAT.md"
# May be a Traversable; read if present:
try:
 text = legacy.read_text(encoding="utf-8")
 print("legacy HEARTBEAT lines:", len(text.splitlines()))
except Exception as exc:
 print("not packaged or unreadable:", type(exc).__name__)
```

## Dependencies / env

- Not required for RBP chat / eval.
- Safe to ignore unless migrating old workspaces that still reference HEARTBEAT.

## See also

[`../README.md`](../README.md) · [`../agent/README.md`](../agent/README.md) · [`memory/README.md`](memory/README.md)
