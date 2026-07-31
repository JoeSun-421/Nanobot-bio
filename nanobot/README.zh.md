# nanobot/

仓内精简 Nanobot 运行时 **外加** RBP skill 与工具。SoT == 运行时：`import nanobot` 必须解析到这里。

[English](README.md) · [中文]

## 功能

- 高阶 `Nanobot` API（`from_config` / `run` / `run_streamed`）供产品 CLI 使用
- Agent loop、会话存储、LLM providers、内部 SDK 辅助
- 产品 skill SoT：`skills/rbp-agent/SKILL.md`
- 产品工具包：`agent/tools/rbp/`（retrieve / predict / structure / …）
- Slim-vendor：去掉 PA 面（channels / webui 等），由 `rbp-agent layout` 断言

## 实现方法

| 路径 | 角色 |
|------|------|
| `nanobot.py` | 对外高阶 API |
| [`agent/`](agent/README.zh.md) | loop、memory、context、skills、**tools** |
| [`sdk/`](sdk/README.zh.md) | 内部 SDK 辅助（clients / streaming / types） |
| `session/` | 会话存储与管理（规范数据在 `artifacts/sessions`） |
| `skills/rbp-agent/` | Skill 源真相；同步到 `workspace/skills/` |
| `providers/` | LLM provider 适配 |
| `config/` · `bus/` · `command/` · `cron/` · `security/` · `utils/` | 框架支撑 |
| `legacy/` · `templates/` | 遗留 / 模板；非主产品路径 |

工具加载默认：`NANOBOT_TOOL_ALLOW=rbp`；`NANOBOT_TOOL_PLUGINS` 默认关。Chat 路径还会在 `app/agent.py` 注销嘈杂 PA 工具。

打包：`pyproject.toml` 通过 setuptools 包含 `nanobot*`，editable install 即暴露本树。

## 怎么使用

产品侧通常走 App CLI，而不是直接 `python -m nanobot`：

```bash
nanobot-bio chat|agent
# App 内：Nanobot.from_config → run / run_streamed
# MVP / eval 优先 ephemeral=True
```

改完 skill 或 RBP tools 后：

```bash
python -m app.sync_overlay
nanobot-bio doctor
```

**禁止**再 `pip install nanobot-ai`，否则会抢包名。

## 设计思路

- **SoT == 运行时** 避免第三套 tools 树与同步漂移（提案 / ARCHITECTURE §6）。
- 重科学（torch / jax 模型）不进 Nanobot 进程；经 App delivery 桥出站。
- 科学模式关闭自动 Dream / idle compaction / token consolidator，并在科学提示中排除 PA `MEMORY.md`（[`ARCHITECTURE.md`](../ARCHITECTURE.md) §2）。
- 即便收紧 PA 默认行为，仍保留 session/memory 栈接线——勿盲目删除。

## 相关文档

[`../README.zh.md`](../README.zh.md) · [`ARCHITECTURE.md`](../ARCHITECTURE.md) · [`../app/README.zh.md`](../app/README.zh.md) · [`../workspace/README.zh.md`](../workspace/README.zh.md)
