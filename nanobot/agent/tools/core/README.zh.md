# nanobot/agent/tools/core/

工具运行时基础设施：基类 `Tool`、registry、loader、schema、sandbox。

[English](README.md) · [中文]

## 用途

产品与 legacy 工具都继承这里定义的类型。本包不实现科学计算——它定义工具如何声明参数、注册、从包发现，以及在 workspace 约束下执行。

## 布局

| 模块 | 角色 |
|------|------|
| `base.py` | `Tool`、`Schema`、`tool_parameters` |
| `registry.py` | `ToolRegistry` |
| `loader.py` | `ToolLoader`（包发现） |
| `context.py` | `ToolContext` |
| `schema.py` | JSON-schema 辅助 |
| `sandbox.py` | 执行沙箱辅助 |
| `path_utils.py` / `runtime_state.py` / `exec_session.py` | 路径 / 状态 / 执行会话 |
| `tool_configs.py` | 工具配置辅助 |

## 入口

```python
from nanobot.agent.tools.core.base import Tool, Schema, tool_parameters
from nanobot.agent.tools.core.registry import ToolRegistry
from nanobot.agent.tools.core.loader import ToolLoader
from nanobot.agent.tools import Tool, ToolRegistry, ToolLoader
```

## 代码示例

**最小自定义工具**

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

## 依赖 / 环境

- 纯框架；不需要 delivery/GPU。
- 产品 allow-list 仍由上层 `NANOBOT_TOOL_ALLOW` 控制。

## 相关文档

[`../README.zh.md`](../README.zh.md) · [`../rbp/README.zh.md`](../rbp/README.zh.md) · [`../../README.zh.md`](../../README.zh.md)
