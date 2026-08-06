# nanobot/

精简仓内 Nanobot 运行时 **加上** RBP skill 与工具。SoT == runtime：`import nanobot` 必须解析到这里。

[English](README.md) · [中文]

## 用途

本树是产品所用的 agent 框架：高层 `Nanobot` API、agent loop、会话存储、LLM providers，以及 RBP skill/工具包。打包（`pyproject.toml`）包含 `nanobot*`，editable install 暴露的是**本目录**——切勿同时安装 PyPI `nanobot-ai`。

产品协作者通常经 [`app/`](../app/README.zh.md)（`nanobot-bio chat|agent`）进入。直接 `python -m nanobot` 偏框架，不是 RBP 产品 UX。阶段纪律与工具契约见 `skills/rbp-agent/SKILL.md` 与 [rbp-agent SKILL.md](skills/rbp-agent/SKILL.md)。



## 通用布局（Linux）

```bash
export BIO_ROOT="${BIO_ROOT:-$HOME/bio_agent}"
# 检出目录常见为 Nanobot-bio（GitHub）；小写 nanobot-bio 亦可。
cd "${NANOBOT_BIO_ROOT:-$BIO_ROOT/Nanobot-bio}"
source scripts/nbio.sh
```

## 布局

| 路径 | 角色 |
|------|------|
| `nanobot.py` | 公共高层 API（`Nanobot.from_config` / `run` / `run_streamed`） |
| [`agent/`](agent/README.zh.md) | Loop、memory、context、skills、**tools** |
| [`agent/tools/rbp/`](agent/tools/rbp/README.zh.md) | 产品工具包（retrieve / predict / structure / …） |
| [`sdk/`](sdk/README.zh.md) | 内部 SDK 辅助（clients / streaming / types） |
| [`session/`](session/README.zh.md) | 会话存储（规范数据在 `artifacts/sessions`） |
| [`skills/`](skills/README.zh.md) | Skill SoT（`rbp-agent/SKILL.md`）；同步到 `workspace/skills/` |
| [`providers/`](providers/README.zh.md) | LLM provider 适配 |
| [`config/`](config/README.zh.md) · [`bus/`](bus/README.zh.md) · [`command/`](command/README.zh.md) · [`cron/`](cron/README.zh.md) · [`security/`](security/README.zh.md) · [`utils/`](utils/README.zh.md) | 框架支持 |
| [`legacy/`](legacy/README.zh.md) · [`templates/`](templates/README.zh.md) | 遗留 / 模板；非主产品路径 |

默认：`NANOBOT_TOOL_ALLOW=rbp`；除非设置，否则关闭 `NANOBOT_TOOL_PLUGINS`。Chat 还会在 `app/agent.py` 中注销嘈杂 PA 工具。

## 入口

```python
from nanobot import Nanobot, RunResult
```

```bash
nanobot-bio chat|agent # 产品路径
python -m app.sync_overlay # 改完 skill / RBP tools 后
nanobot-bio doctor
```

## 代码示例

**高层 Nanobot（框架）**

```python
from nanobot import Nanobot

bot = Nanobot.from_config(workspace="workspace", scientific_mode=True)
result = await bot.run("Summarize workspace AGENTS.md", ephemeral=True)
print(result.content)
```

**产品组装（推荐）**

```python
from app.agent import RBPAgent

agent = RBPAgent()
result = agent.run_sync("Predict binding for PTBP1 on the sample RNA.")
print(result.verdict)
```

## 依赖 / 环境

- LLM 凭证经 `~/.nanobot/config.json` / `.env`（`nanobot-bio onboard`）。
- 科学工具需要 delivery（`DELIVERY_ROOT`）——Nanobot 进程本身不承载 torch/jax 模型栈。
- **不要** `pip install nanobot-ai`——会抢占 import 名。

## 设计思路

- **SoT == runtime** 避免第三套 tools 树与同步漂移（[`ARCHITECTURE.md`](../ARCHITECTURE.md) §6）。
- 科学模式关闭自动 Dream / idle compaction / token consolidator，并从科学 prompt 排除 PA `MEMORY.md`。
- 即使产品默认收紧 PA 行为，会话/记忆栈仍保持接线——勿盲目删除。

## 相关文档

[`../README.zh.md`](../README.zh.md) · [`ARCHITECTURE.md`](../ARCHITECTURE.md) · [`../app/README.zh.md`](../app/README.zh.md) · [rbp-agent SKILL.md](skills/rbp-agent/SKILL.md) · [`../workspace/README.zh.md`](../workspace/README.zh.md)
