# app/backends/

Backend adapters for science I/O. Product path uses the **delivery** backend only.

[English] · [中文](README.zh.md)

## Purpose

This package is the namespace under which the App talks to external science stacks. Today the sole production backend is [`delivery/`](delivery/README.md): a read-only bridge into sibling `rhobind_agent_delivery`. Historical “mock” backends are not shipped as importable product code here — `RBP_BACKEND=delivery` is the supported setting.

> Parent package map and `$BIO_ROOT` layout: [`README.md`](../../README.md). Activate with `cd "${NANOBOT_BIO_ROOT:-$BIO_ROOT/Nanobot-bio}" && source scripts/nbio.sh`.

## Layout

| Path | Role |
|------|------|
| `__init__.py` | Package marker (`Backends: mock vs delivery`) |
| [`delivery/`](delivery/README.md) | `DeliveryToolClient`, env resolve, `mapping.yaml`, registry |

## Entry points

```python
from app.backends.delivery import DeliveryToolClient, apply_delivery_env, delivery_root

apply_delivery_env()
client = DeliveryToolClient()
print(delivery_root())
```

Prefer importing from `app.backends.delivery` (or its submodules) rather than reaching into delivery scripts.

## Code examples

```python
from app.backends.delivery.client import DeliveryToolClient
from app.backends.delivery.env import apply_delivery_env, resolve_delivery_paths

apply_delivery_env()
paths = resolve_delivery_paths()
client = DeliveryToolClient()
# Light tool (in-process when mapped as pure Python):
result = client.call("resolve_rbp", {"alias": "PTBP1"})
```

Operator smoke from repo root:

```bash
python scripts/cert/smoke_delivery_tools.py
```

## Dependencies / env

| Variable | Notes |
|----------|-------|
| `DELIVERY_ROOT` | Override; else sibling `../rhobind_agent_delivery` |
| `RBP_BACKEND` | Product path: `delivery` |
| Science conda envs | Heavy tools via `conda run` (see delivery `mapping.yaml`) |

## See also

[`delivery/README.md`](delivery/README.md) · [`../README.md`](../README.md) · [rbp-agent SKILL.md](../../nanobot/skills/rbp-agent/SKILL.md) · [`../../ARCHITECTURE.md`](../../ARCHITECTURE.md) §4
