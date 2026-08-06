# nanobot/agent/tools/legacy/

为框架兼容保留的 PA / 个人助手遗留工具 stubs。

[English](README.md) · [中文]

## 用途

这些模块保留 Nanobot 历史工具面（文件系统、shell、web、cron、MCP 等），避免引用 PA 特性时框架断裂。对 **nanobot-bio 产品 chat**，它们**不在**默认 allow list（`NANOBOT_TOOL_ALLOW=rbp`）。不要用它们产生科学分数。

## 布局

| 模块 | 角色（遗留） |
|------|-------------|
| `filesystem.py` / `shell.py` / `apply_patch.py` | 工作区文件 / shell |
| `web.py` / `search.py` | Web / 搜索 stubs |
| `message.py` / `spawn.py` / `self.py` | 消息 / 派生 / 自省 |
| `cron.py` / `long_task.py` | 定时 / 长任务 |
| `mcp.py` / `cli_apps.py` / `image_generation.py` | MCP / CLI apps / 图像生成 |
| `file_state.py` | 文件状态辅助 |

## 入口

仅在 allow-list / plugins 显式启用 legacy 时导入。产品路径：

```python
from nanobot.agent.tools.rbp import register_all
```

## 代码示例

**确认产品 allow-list 排除 legacy**

```bash
echo "${NANOBOT_TOOL_ALLOW:-rbp}" # 期望：rbp
nanobot-bio layout
```

## 依赖 / 环境

- 留在磁盘上供框架测试 / 可选 PA 实验。
- 仅在维护者明确政策下扩大 allow-list（[`AGENTS.md`](../../../../AGENTS.md)）。

## 相关文档

[`../README.zh.md`](../README.zh.md) · [`../rbp/README.zh.md`](../rbp/README.zh.md) · [`../../../README.zh.md`](../../../README.zh.md)
