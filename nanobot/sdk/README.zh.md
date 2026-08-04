# nanobot/sdk/

高层 Nanobot Python API 的内部辅助。

[English](README.md) · [中文]

> 包地图与 `$BIO_ROOT` 布局见仓库根 [`README.zh.md`](../../README.zh.md)。激活：`cd "$BIO_ROOT/nanobot-bio" && source scripts/nbio.sh`。

## 用途

为 `nanobot.nanobot.Nanobot` 提供流式事件、薄客户端（session / memory / runtime）与共享类型。这**不是**给产品协作者的第二套公共 API——请优先 `from nanobot import Nanobot` 或 App CLI。

## 布局

| 文件 | 角色 |
|------|------|
| `clients.py` | `SessionClient`、`MemoryClient`、`RuntimeClient` |
| `runtime.py` | `SDKRuntimeController`、进程参数辅助 |
| `streaming.py` | `RunStream`、`SDKStreamEmitter`、流式 hook |
| `types.py` | `RunResult`、`StreamEvent`、流事件常量 |
| `__init__.py` | 包说明（内部辅助） |

## 入口

```python
from nanobot import Nanobot, RunResult, RunStream
from nanobot.sdk.types import STREAM_EVENT_TOOL_COMPLETED
```

## 代码示例

```python
from nanobot import Nanobot

bot = Nanobot.from_config(scientific_mode=True)
print(bot.sessions, bot.memory, bot.runtime)

async for event in bot.run_streamed("Ping"):
    print(event.type)
```

```bash
nanobot-bio chat|agent
```

## 依赖 / 环境

- 与 Nanobot 相同的 LLM 配置（`~/.nanobot/config.json` / `.env`）。
- 不要把 `nanobot.sdk.*` 当作跨版本稳定外部契约。

## 相关文档

[`../README.zh.md`](../README.zh.md) · [`../../app/README.zh.md`](../../app/README.zh.md)
