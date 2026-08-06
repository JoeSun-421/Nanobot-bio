# nanobot/agent/tools/

工具包根：core 运行时、RBP 产品工具与 legacy PA stubs。

[English](README.md) · [中文]

## 用途

Tools 是 agent 调用外部世界的方式。本包再导出运行时原语（`Tool`、`ToolRegistry`、`ToolLoader` 等），并托管三棵职责不同的子树。nanobot-bio 默认 allow-list **仅为 rbp**。

## 布局

| 路径 | 角色 |
|------|------|
| `__init__.py` | 再导出 `Schema`、`Tool`、`ToolContext`、`ToolLoader`、`ToolRegistry`、`tool_parameters` |
| [`core/`](core/README.zh.md) | 基类、registry、loader、sandbox、schema |
| [`rbp/`](rbp/README.zh.md) | 产品科学工具（SoT） |
| [`legacy/`](legacy/README.zh.md) | PA / 文件系统 / web stubs — 默认不在 allow list |

## 入口

```python
from nanobot.agent.tools import Tool, ToolRegistry, ToolLoader, ToolContext, Schema
from nanobot.agent.tools.rbp import register_all, ALL_RBP_TOOL_CLASSES
```

## 代码示例

```python
from nanobot.agent.tools import ToolRegistry
from nanobot.agent.tools.rbp import register_all

registry = ToolRegistry()
mounted = register_all(registry)
assert "predict_interaction" in mounted

for name in mounted:
 tool = registry.get(name)
 print(name, tool.name)
```

```bash
export NANOBOT_TOOL_ALLOW=rbp
export RBP_PHMMER=1 # 可选远程同源轴
```

## 依赖 / 环境

- `NANOBOT_TOOL_ALLOW` — 逗号列表；产品默认 `rbp`。
- `NANOBOT_TOOL_PLUGINS` — 除非开发插件，否则保持未设置/关闭。
- RBP tools 真实打分需要 App delivery 桥。

## 相关文档

[`rbp/README.zh.md`](rbp/README.zh.md) · [`../README.zh.md`](../README.zh.md) · [rbp-agent SKILL.md](../../skills/rbp-agent/SKILL.md)
