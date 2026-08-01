# nanobot/agent/tools/legacy/

PA / personal-assistant legacy tool stubs kept for framework compatibility.

[English] · [中文](README.zh.md)

## Purpose

These modules preserve Nanobot’s historical tool surface (filesystem, shell, web, cron, MCP, …) so the framework does not break when PA features are referenced. For **nanobot-bio product chat**, they are **not** on the default allow list (`NANOBOT_TOOL_ALLOW=rbp`). Do not use them for scientific scores.

## Layout

| Module | Role (legacy) |
|--------|----------------|
| `filesystem.py` / `shell.py` / `apply_patch.py` | Workspace file / shell ops |
| `web.py` / `search.py` | Web / search stubs |
| `message.py` / `spawn.py` / `self.py` | Messaging / spawn / introspection |
| `cron.py` / `long_task.py` | Scheduled / long tasks |
| `mcp.py` / `cli_apps.py` / `image_generation.py` | MCP / CLI apps / image gen |
| `file_state.py` | File-state helpers |

## Entry points

Imported only when allow-list / plugins explicitly enable legacy tools. Product path:

```python
# Prefer RBP tools — not legacy:
from nanobot.agent.tools.rbp import register_all
```

## Code examples

**Confirm product allow-list excludes legacy**

```bash
# Typical product env (set by app):
echo "${NANOBOT_TOOL_ALLOW:-rbp}"   # expect: rbp
nanobot-bio layout                  # asserts SoT; PA surfaces forbidden where listed
```

**Do not do this for science**

```python
# Anti-pattern for binding prediction:
# mounting shell/web tools and asking the LLM to invent p_hat
```

## Dependencies / env

- Left on disk for framework tests / optional PA experiments.
- Widen allow-list only with explicit maintainer policy ([`AGENTS.md`](../../../../AGENTS.md)).

## See also

[`../README.md`](../README.md) · [`../rbp/README.md`](../rbp/README.md) · [`../../../README.md`](../../../README.md)
