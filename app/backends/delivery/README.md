# app/backends/delivery/

Read-only bridge from the agent process into sibling `rhobind_agent_delivery`.

[English] · [中文](README.zh.md)

## Purpose



## Portable layout (Linux)

```bash
export BIO_ROOT="${BIO_ROOT:-$HOME/bio_agent}"
cd "$BIO_ROOT/nanobot-bio"
source scripts/nbio.sh
```

All science I/O from the product agent must pass through this package. Light tools may run in-process; heavy tools spawn `conda run` subprocesses with JSON payloads. Mapping is fail-closed against delivery’s `agent/tools/registry.json` — stale bindings hard-fail rather than calling the wrong script. This package never invents binding scores when an env or binary is missing.

End-to-end stage flow (own-head → retrieve → fuse → predict → integrate) is described in [`docs/product/BINDING_PREDICTION_FLOW.zh.md`](../../../docs/product/BINDING_PREDICTION_FLOW.zh.md). Aggregation authority for transfer `p_hat` remains delivery `similarity_weighted_vote`.

## Layout

| File | Role |
|------|------|
| `client.py` | `DeliveryToolClient`; `PURE_PYTHON_TOOLS` vs conda maps |
| `env.py` | `delivery_root()` / `apply_delivery_env()` / path resolution |
| `mapping.yaml` | App orchestration: tool → script / env / timeout |
| `tool_mapping.py` | Validate mapping vs delivery registry; fail closed |
| `registry.py` | `register_tools`, `build_all_tools`, stage whitelist |
| `stage_tools.py` | Stage-oriented wrappers |
| `examples.py` | Example / fixture path helpers |
| `mmseqs_wrap.sh` | mmseqs wrapper when the tool chain needs it |
| `__init__.py` | Public re-exports |

Call chain:

```
nanobot RBP tool
  → DeliveryToolClient.call
      → apply_delivery_env / mapping
      → in-process OR conda run (protein_embed / rna / rhobind / af3…)
```

## Entry points

```python
from app.backends.delivery import (
    DeliveryToolClient,
    apply_delivery_env,
    delivery_root,
    resolve_delivery_paths,
    register_tools,
)
```

## Code examples

**Resolve an RBP alias**

```python
from app.backends.delivery.client import DeliveryToolClient
from app.backends.delivery.env import apply_delivery_env, delivery_root

apply_delivery_env()
print("DELIVERY_ROOT →", delivery_root())
client = DeliveryToolClient()
result = client.call("resolve_rbp", {"alias": "PTBP1"})
# result is a structured dict (status / value or error) — never a synthetic p_hat
```

**Register delivery-backed tools onto a Nanobot registry** (normally done by `RBPAgent`)

```python
from app.backends.delivery.registry import register_tools
from nanobot.agent.tools import ToolRegistry

reg = ToolRegistry()
names = register_tools(reg)  # default include_raw_delivery="all"
print(sorted(names)[:10])
# Narrow MVP: include_raw_delivery="whitelist" or RBP_RAW_TOOLS=whitelist
```

**Operator smoke**

```bash
python scripts/cert/smoke_delivery_tools.py
python scripts/cert/smoke_delivery_tools.py --network --af3
```

## Dependencies / env

| Variable | Notes |
|----------|-------|
| `DELIVERY_ROOT` | Delivery root; else sibling `rhobind_agent_delivery` |
| `AGENT_DB` / `RBP_REGISTRY` / `RHOBIND_RELEASE` / `AF3_*` / `PEAKS_DB` | Filled by `apply_delivery_env` |
| `RBP_BACKEND` | Product path is `delivery` |
| `RBP_RAW_TOOLS` | `all` (default) / `whitelist` (narrow MVP opt-out) / `none` |

Child envs scrub the agent `.venv` so torch / jax stacks do not mix. Full table: [`INSTALL.md`](../../../INSTALL.md). Operator path discovery / AF3 heal: `./scripts/nbio start` (see [`scripts/README.md`](../../../scripts/README.md)); AutoDL paths are candidates only.

## Design rationale

- **Read-only science boundary:** [`AGENTS.md`](../../../AGENTS.md) forbids editing delivery sources from the App.
- **Fail closed on stale mapping:** Prefer hard failure over silently calling the wrong script.
- **Honesty:** Structure / AF3 miss → caveat via capability matrix, not similarity `0`.

## See also

[`../README.md`](../README.md) · [`../../README.md`](../../README.md) · [`ARCHITECTURE.md`](../../../ARCHITECTURE.md) §4 · [`../../../docs/product/BINDING_PREDICTION_FLOW.zh.md`](../../../docs/product/BINDING_PREDICTION_FLOW.zh.md) · [`../../../scripts/cert/README.md`](../../../scripts/cert/README.md)
