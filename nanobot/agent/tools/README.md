# nanobot/agent/tools/

Tool package root: core runtime, RBP product tools, and legacy PA stubs.

[English] · [中文](README.zh.md)

## Purpose

Tools are how the agent calls the outside world. This package re-exports the runtime primitives (`Tool`, `ToolRegistry`, `ToolLoader`, …) and hosts three subtrees with different product roles. Default allow-list for nanobot-bio is **rbp only**.

## Layout

| Path | Role |
|------|------|
| `__init__.py` | Re-exports `Schema`, `Tool`, `ToolContext`, `ToolLoader`, `ToolRegistry`, `tool_parameters` |
| [`core/`](core/README.md) | Base classes, registry, loader, sandbox, schema |
| [`rbp/`](rbp/README.md) | Product science tools (SoT) |
| [`legacy/`](legacy/README.md) | PA / filesystem / web stubs — not in default allow list |

## Entry points

```python
from nanobot.agent.tools import Tool, ToolRegistry, ToolLoader, ToolContext, Schema
from nanobot.agent.tools.rbp import register_all, ALL_RBP_TOOL_CLASSES
```

## Code examples

```python
from nanobot.agent.tools import ToolRegistry
from nanobot.agent.tools.rbp import register_all

registry = ToolRegistry()
mounted = register_all(registry)
assert "predict_interaction" in mounted

# Discover schemas for LLM tool calling:
for name in mounted:
 tool = registry.get(name)
 print(name, tool.schema() if hasattr(tool, "schema") else tool.name)
```

```bash
# Product default (set by app):
export NANOBOT_TOOL_ALLOW=rbp
# Optional remote-homology axis:
export RBP_PHMMER=1
```

## Dependencies / env

- `NANOBOT_TOOL_ALLOW` — comma list; product default `rbp`.
- `NANOBOT_TOOL_PLUGINS` — leave unset/off unless developing plugins.
- RBP tools require App delivery bridge for real scores.

## See also

[`rbp/README.md`](rbp/README.md) · [`../README.md`](../README.md) · [rbp-agent SKILL.md](../../skills/rbp-agent/SKILL.md)
