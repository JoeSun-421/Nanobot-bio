# nanobot/bus/

用于 channel ↔ agent 解耦通信的消息总线。

[English](README.md) · [中文]

> 包地图与 `$BIO_ROOT` 布局见仓库根 [`README.zh.md`](../../README.zh.md)。激活：`cd "${NANOBOT_BIO_ROOT:-$BIO_ROOT/Nanobot-bio}" && source scripts/nbio.sh`。

## 用途

提供入站/出站消息类型与队列总线，使 UI channel（若启用）无需紧耦合即可与 agent loop 通信。精简后的 nanobot-bio 产品路径主要使用直接 `Nanobot.run` / CLI chat，但 bus 仍是框架核心的一部分。

## 布局

| 模块 | 角色 |
|------|------|
| `events.py` | `InboundMessage`、`OutboundMessage` |
| `queue.py` | `MessageBus` |
| `progress.py` | 进度事件辅助 |
| `runtime_events.py` | 运行时事件类型 |

## 入口

```python
from nanobot.bus import MessageBus, InboundMessage, OutboundMessage
```

## 代码示例

```python
from nanobot.bus import MessageBus, InboundMessage

bus = MessageBus()
msg = InboundMessage(channel="cli", sender_id="user", content="hello")
print(msg.channel, msg.content)
```

## 依赖 / 环境

- 仅框架；不依赖 delivery。
- PA channel 表面在 `nanobot-bio layout` 所列处被剥离/禁止。

## 相关文档

[`../README.zh.md`](../README.zh.md) · [`../agent/README.zh.md`](../agent/README.zh.md)
