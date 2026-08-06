# nanobot/bus/

Message bus for decoupled channel ↔ agent communication.

[English] · [中文](README.zh.md)

> Parent package map and `$BIO_ROOT` layout: [`README.md`](../../README.md). Activate with `cd "${NANOBOT_BIO_ROOT:-$BIO_ROOT/Nanobot-bio}" && source scripts/nbio.sh`.

## Purpose

Provides inbound/outbound message types and a queue bus so UI channels (when enabled) can talk to the agent loop without tight coupling. The slim nanobot-bio product path primarily uses direct `Nanobot.run` / CLI chat rather than external channel bridges, but the bus remains part of the framework core.

## Layout

| Module | Role |
|--------|------|
| `events.py` | `InboundMessage`, `OutboundMessage` |
| `queue.py` | `MessageBus` |
| `progress.py` | Progress event helpers |
| `runtime_events.py` | Runtime event types |

## Entry points

```python
from nanobot.bus import MessageBus, InboundMessage, OutboundMessage
```

## Code examples

```python
from nanobot.bus import MessageBus, InboundMessage

bus = MessageBus()
msg = InboundMessage(channel="cli", sender_id="user", content="hello")
# Framework loop consumes bus messages when channels are wired.
print(msg.channel, msg.content)
```

## Dependencies / env

- Framework-only; no delivery dependency.
- PA channel surfaces are stripped/forbidden by `nanobot-bio layout` where listed.

## See also

[`../README.md`](../README.md) · [`../agent/README.md`](../agent/README.md)
