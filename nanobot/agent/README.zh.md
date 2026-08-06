# nanobot/agent/

Agent loop、memory/context、skills 加载与工具包。

[English](README.md) · [中文]

> 包地图与 `$BIO_ROOT` 布局见仓库根 [`README.zh.md`](../../README.zh.md)。激活：`cd "${NANOBOT_BIO_ROOT:-$BIO_ROOT/Nanobot-bio}" && source scripts/nbio.sh`。

## 用途

本包是 Nanobot 一轮对话的核心：组装 context、调用 LLM provider、执行工具、推送进度，并持久化 memory/session 副作用。在 nanobot-bio 中，产品科学行为由 **RBP tools + skill** 驱动，出站科学调用经 App delivery 桥。操作者不把本包当 CLI——由 `RBPAgent` / `Nanobot.from_config` 加载。

## 布局

| 路径 | 角色 |
|------|------|
| `loop.py` / `runner.py` | 主循环与 run 包装 |
| `context.py` | Context 组装（`ContextBuilder`） |
| `memory.py` | 长期记忆钩子（`scientific_mode` 下关闭 PA memory） |
| `skills.py` | Skill 加载（`SkillsLoader`） |
| `hook.py` / `progress_hook.py` | Hook 接口 / 进度 |
| `autocompact.py` / `subagent.py` / `cron_turns.py` | 框架能力（RBP 产品中收紧） |
| `model_presets.py` | 模型预设 |
| [`tools/`](tools/README.zh.md) | 工具包根 |
| [`tools/core/`](tools/core/README.zh.md) | 工具运行时基础设施 |
| [`tools/rbp/`](tools/rbp/README.zh.md) | **产品工具包** |
| [`tools/legacy/`](tools/legacy/README.zh.md) | PA / 遗留 stubs；默认不在 allow list |

Skill SoT：[`../skills/rbp-agent/SKILL.md`](../skills/README.zh.md)。规范会话/记忆存储：`artifacts/`（[`ARCHITECTURE.md`](../../ARCHITECTURE.md) §2）。

## 入口 / 导入

```python
from nanobot.agent import AgentLoop, ContextBuilder, MemoryStore, SkillsLoader
from nanobot.agent.tools import ToolRegistry, Tool
```

间接加载：

```python
from nanobot import Nanobot
from app.agent import RBPAgent
```

## 代码示例

**注册精选 RBP tools**

```python
from nanobot.agent.tools import ToolRegistry
from nanobot.agent.tools.rbp import register_all

reg = ToolRegistry()
names = register_all(reg)
print(names) # predict_interaction, seq_similarity, …
```

**产品 chat 启动后的默认**

```bash
# 通常由 app bootstrap 设置：
# NANOBOT_TOOL_ALLOW=rbp
# NANOBOT_TOOL_PLUGINS 未设置 / 关闭
python -m app.sync_overlay
pytest tests/test_proposal_compliance.py tests/test_package_layout.py
```

## 依赖 / 环境

- 真实回合需要已配置的 LLM provider。
- RBP tools 调用 `app.backends.delivery`——科学路径需要 `DELIVERY_ROOT`。
- 可选：`RBP_PHMMER=1` 启用 phmmer 远程同源工具。

## 设计思路

- Legacy PA tools 保留在磁盘上以兼容框架，但默认不在 allow list（[`AGENTS.md`](../../AGENTS.md)）。
- LLM 不得绕过 `similarity_weighted_vote` 或编造 `prob` / `p_hat`。

## 相关文档

[`../README.zh.md`](../README.zh.md) · [`tools/rbp/README.zh.md`](tools/rbp/README.zh.md) · [`../sdk/README.zh.md`](../sdk/README.zh.md) · [rbp-agent SKILL.md](../skills/rbp-agent/SKILL.md) · [`../../app/README.zh.md`](../../app/README.zh.md)
