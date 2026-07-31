# nanobot/agent/

Agent 循环、记忆/上下文、技能加载与工具包。

[English](README.md) · [中文]

## 功能

- 多轮 agent loop 与 runner 封装
- 上下文拼装、记忆钩子、技能加载
- 工具树：`tools/core`（运行时基建）、`tools/rbp`（产品）、`tools/legacy`（PA stub，默认不在 allow 列表）
- 可选框架能力（autocompact、subagent、cron turns）——产品路径保持收紧

## 实现方法

| 路径 | 角色 |
|------|------|
| `loop.py` / `runner.py` | 主循环与运行封装 |
| `context.py` | 上下文组装 |
| `memory.py` | 长期记忆钩子（科学模式下 PA memory 关闭） |
| `skills.py` | 技能加载 |
| `autocompact.py` / `hook.py` / `progress_hook.py` / `subagent.py` / `cron_turns.py` | 框架能力（RBP 产品路径收紧） |
| `model_presets.py` | 模型预设 |
| `tools/core/` | 工具运行时基础设施 |
| `tools/rbp/` | **产品工具包**（retrieve / predict / structure / …） |
| `tools/legacy/` | PA / 遗留 stub；默认不在 allow 列表 |

阶段纪律（阶段 0 own-head 快路径等）见 skill SoT：`nanobot/skills/rbp-agent/SKILL.md`。

会话/记忆规范存储在 `artifacts/`（见 [`ARCHITECTURE.md`](../../ARCHITECTURE.md) §2）；`workspace/` 多为符号链接。

## 怎么使用

经 `app.agent.RBPAgent` / `Nanobot.from_config` 间接加载；运维不把本包当 CLI。

默认：

- `NANOBOT_TOOL_ALLOW=rbp`
- `NANOBOT_TOOL_PLUGINS` 未设置 / 关闭

改完 `tools/rbp` 或 skill 后同步并跑合规测试：

```bash
python -m app.sync_overlay
pytest tests/test_proposal_compliance.py tests/test_package_layout.py
```

## 设计思路

- 产品科学行为由 **RBP tools + skill** 驱动，经 App delivery 桥出站。
- Legacy PA 工具留在磁盘以兼容框架，但默认不进 allow 列表（[`AGENTS.md`](../../AGENTS.md)）。
- LLM 不得绕过 `similarity_weighted_vote`，也不得编造 `prob` / `p_hat`。

## 相关文档

[`../README.zh.md`](../README.zh.md) · [`../sdk/README.zh.md`](../sdk/README.zh.md) · [`../../app/README.zh.md`](../../app/README.zh.md)
