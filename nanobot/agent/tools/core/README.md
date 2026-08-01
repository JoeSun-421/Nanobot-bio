# nanobot/agent/tools/core/

Tool runtime infrastructure: base `Tool` class, registry, loader, schema, sandbox.

[English] · [中文](README.zh.md)

## Purpose

Product and legacy tools all subclass types defined here. This package does not implement science — it defines how tools declare parameters, register, load from packages, and execute under workspace constraints.

## Layout

| Module | Role |
|--------|------|
| `base.py` | `Tool`, `Schema`, `tool_parameters` |
| `registry.py` | `ToolRegistry` |
| `loader.py` | `ToolLoader` (package discovery) |
| `context.py` | `ToolContext` |
| `schema.py` | JSON-schema helpers |
| `sandbox.py` | Execution sandbox helpers |
| `path_utils.py` / `runtime_state.py` / `exec_session.py` | Path / state / exec session |
| `tool_configs.py` | Tool config helpers |

## Entry points

```python
from nanobot.agent.tools.core.base import Tool, Schema, tool_parameters
from nanobot.agent.tools.core.registry import ToolRegistry
from nanobot.agent.tools.core.loader import ToolLoader
# Or via parent re-export:
from nanobot.agent.tools import Tool, ToolRegistry, ToolLoader
```

## Code examples

**Minimal custom tool**

```python
from nanobot.agent.tools.core.base import Tool, tool_parameters

class PingTool(Tool):
    name = "ping"
    description = "Return pong"

    @tool_parameters({})
    async def execute(self, **kwargs):
        return {"status": "ok", "value": {"msg": "pong"}}

from nanobot.agent.tools import ToolRegistry
reg = ToolRegistry()
reg.register(PingTool())
assert reg.get("ping") is not None
```

**Load discoverable tools from a package path**

```python
from nanobot.agent.tools.core.loader import ToolLoader
from nanobot.agent.tools.core.registry import ToolRegistry

reg = ToolRegistry()
loader = ToolLoader(reg)
# Product code normally uses rbp.register_all / register_rbp_tools instead.
```

## Dependencies / env

- Pure framework; no delivery/GPU requirement.
- Product allow-list still controlled by `NANOBOT_TOOL_ALLOW` at higher layers.

## See also

[`../README.md`](../README.md) · [`../rbp/README.md`](../rbp/README.md) · [`../../README.md`](../../README.md)
