# nanobot/agent/tools/rbp/

Product RBP toolkit (SoT). Tool subclasses call delivery for scores; the LLM only orchestrates.

[English] · [中文](README.zh.md)

## Purpose

These tools implement the scientific stages described in [`docs/product/BINDING_PREDICTION_FLOW.zh.md`](../../../../docs/product/BINDING_PREDICTION_FLOW.zh.md): catalogue resolve / own-head predict, multi-view retrieve, fuse, structure, annotation, and evolve helpers. Numbers (`prob`, similarities, sequences, citations) come **only** from tool returns — never from model memory. Registration is curated via `ALL_RBP_TOOL_CLASSES` + optional `RBP_PHMMER`.

## Layout

| Module | Tools / role |
|--------|----------------|
| `predict.py` | `PredictInteractionTool` — own-head / donor-head predict |
| `seq.py` | `SeqSimilarityTool` — sequence similarity retrieve |
| `structure.py` | `PredictStructureTool`, `StructSimilarityTool` |
| `annotation.py` | `GetFuncAnnotationTool`, `LiteratureSearchTool` |
| `catalogue.py` | `GetKnownRBPListTool` |
| `near_known.py` | `CheckNearKnownTool` |
| `phmmer.py` | `PhmmerSimilarityTool` (optional; `RBP_PHMMER=1`) |
| `evolve_tools.py` | `FuseSimilarityViewsTool`, `LookupProxyCacheTool` |
| `commit_proxies.py` | `CommitProxyCandidatesTool` |
| `common.py` | Shared helpers / envelopes |
| `stage_contract.py` | Stage contracts / guards |
| `turn_guards.py` | Per-turn safety guards |
| `register.py` | `register_rbp_tools()` used by `app.agent` |
| `__init__.py` | `register_all()`, `ALL_RBP_TOOL_CLASSES` |

## Entry points

```python
from nanobot.agent.tools.rbp import (
    register_all,
    ALL_RBP_TOOL_CLASSES,
    PredictInteractionTool,
)
from nanobot.agent.tools.rbp.register import register_rbp_tools
```

## Code examples

**Mount default product set**

```python
from nanobot.agent.tools import ToolRegistry
from nanobot.agent.tools.rbp import register_all

reg = ToolRegistry()
print(register_all(reg))
# ['predict_interaction', 'get_known_rbp_list', 'seq_similarity', ...]
```

**App path (full delivery surface by default)**

```python
from nanobot.agent.tools import ToolRegistry
from nanobot.agent.tools.rbp.register import register_rbp_tools

reg = ToolRegistry()
_, names = register_rbp_tools(reg)  # default include_raw_delivery="all"
print(len(names), "tools mounted")
# Narrow MVP: include_raw_delivery="whitelist" or RBP_RAW_TOOLS=whitelist
```

**After editing this package**

```bash
python -m app.sync_overlay
nanobot-bio doctor
pytest tests/test_proposal_compliance.py
```

## Dependencies / env

- Runtime calls go through `app.backends.delivery.DeliveryToolClient` (needs `DELIVERY_ROOT` + conda maps).
- `RBP_RAW_TOOLS=all|whitelist|none` controls raw delivery tool mounting (default **`all`**; set `whitelist` to narrow).
- `RBP_PHMMER=1` adds `PhmmerSimilarityTool` (needs hmmer).

## Design rationale

- Fail closed: OOM / timeout / null prob → structured error / null `p_hat`, no invented retry scores.
- Transfer aggregation authority stays in delivery `similarity_weighted_vote`.
- Skill (`nanobot/skills/rbp-agent`) encodes Stage 0 STOP discipline; tools enforce envelopes.

## See also

[`../README.md`](../README.md) · [`../../../skills/README.md`](../../../skills/README.md) · [`../../../../app/backends/delivery/README.md`](../../../../app/backends/delivery/README.md) · [`../../../../docs/product/BINDING_PREDICTION_FLOW.zh.md`](../../../../docs/product/BINDING_PREDICTION_FLOW.zh.md)
