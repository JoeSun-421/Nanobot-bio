# nanobot/command/

Slash-command routing and built-in handlers for the Nanobot CLI/chat surface.

[English] · [中文](README.zh.md)

> Parent package map and `$BIO_ROOT` layout: [`README.md`](../../README.md). Activate with `cd "$BIO_ROOT/nanobot-bio" && source scripts/nbio.sh`.

## Purpose

Routes in-chat slash commands (`/…`) to handlers via `CommandRouter`, and registers built-ins through `register_builtin_commands`. The product CLI (`nanobot-bio …`) is separate (`app.cli`); this package is the framework’s in-session command layer.

## Layout

| Module | Role |
|--------|------|
| `router.py` | `CommandRouter`, `CommandContext` |
| `builtin.py` | `register_builtin_commands` |
| `__init__.py` | Re-exports |

## Entry points

```python
from nanobot.command import CommandRouter, CommandContext, register_builtin_commands
```

## Code examples

```python
from nanobot.command.router import CommandRouter, CommandContext

router = CommandRouter()
# Handlers are registered via register_builtin_commands(router) when the
# framework chat loop starts (see nanobot.command.builtin).
print(CommandRouter, CommandContext)
```

## Dependencies / env

- Framework-only. Product science commands live under `app.cli` / `rbp_eval`.

## See also

[`../README.md`](../README.md) · [`../../app/cli/README.md`](../../app/cli/README.md)
