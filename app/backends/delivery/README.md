# app/backends/delivery/

Read-only bridge from the agent process into sibling `rhobind_agent_delivery`.

[English] · [中文](README.zh.md)

## Features

- Single App entrypoint `DeliveryToolClient.call(name, payload)` for all delivery tools
- Light tools: in-process `run(payload)`; heavy tools: `--json` subprocess inside conda envs
- Manifest + fail-closed validation against delivery `agent/tools/registry.json`
- Path / AF3 interpreter / USalign→Foldseek fallback / thread knobs via `apply_delivery_env()`

## Implementation

| File | Role |
|------|------|
| `client.py` | `DeliveryToolClient`; `PURE_PYTHON_TOOLS` vs `DEFAULT_CONDA_ENV` maps |
| `env.py` | `delivery_root()` / `apply_delivery_env()` / path resolution |
| `mapping.yaml` | App orchestration: tool → script / env / timeout |
| `tool_mapping.py` | Validate mapping vs delivery registry; stale bindings fail closed |
| `registry.py` | Registry helpers |
| `stage_tools.py` | Stage-oriented wrappers |
| `examples.py` | Example / fixture path helpers |
| `mmseqs_wrap.sh` | mmseqs wrapper when the tool chain needs it |

Call chain:

```
nanobot RBP tool
  → DeliveryToolClient.call
      → apply_delivery_env / mapping
      → in-process OR conda run (protein_embed / rna / rhobind / af3…)
```

Child envs scrub the agent `.venv` so torch / jax stacks do not mix. On missing conda env, calls fall back carefully and return structured errors — **never** synthetic binding scores.

## How to use

Product code should not call delivery scripts directly. Prefer:

```python
from app.backends.delivery.client import DeliveryToolClient
client = DeliveryToolClient()
result = client.call("resolve_rbp", {"alias": "PTBP1"})
```

Operator smoke (repo root):

```bash
python scripts/cert/smoke_delivery_tools.py
python scripts/cert/smoke_delivery_tools.py --network --af3
```

Key env vars (full table in [`INSTALL.md`](../../../INSTALL.md)):

| Variable | Notes |
|----------|-------|
| `DELIVERY_ROOT` | Delivery root; else sibling `rhobind_agent_delivery` |
| `AGENT_DB` / `RBP_REGISTRY` / `RHOBIND_RELEASE` / `AF3_*` / `PEAKS_DB` | Filled by `apply_delivery_env` |
| `RBP_BACKEND` | Product path is `delivery` |

## Design rationale

- **Read-only science boundary:** [`AGENTS.md`](../../../AGENTS.md) forbids editing delivery sources from the App.
- **Fail closed on stale mapping:** Prefer hard failure over silently calling the wrong script.
- **Aggregation authority:** Transfer `p_hat` uses delivery `similarity_weighted_vote`; LLM / diagnostics must not override.
- **Honesty:** Structure / AF3 miss → caveat via capability matrix, not similarity `0`.

## See also

[`../../README.md`](../../README.md) · [`ARCHITECTURE.md`](../../../ARCHITECTURE.md) §4 · [`../../../scripts/cert/README.md`](../../../scripts/cert/README.md)
