# nanobot/agent/

Agent loop, memory/context, skills loader, and tool packages.

[English] · [中文](README.zh.md)

> Parent package map and `$BIO_ROOT` layout: [`README.md`](../../README.md). Activate with `cd "$BIO_ROOT/nanobot-bio" && source scripts/nbio.sh`.

## Purpose

This package is the heart of a Nanobot turn: build context, call the LLM provider, execute tools, stream progress, and persist memory/session side effects. For nanobot-bio, product science behaviour is driven by **RBP tools + skill**, with outbound science calls through the App delivery bridge. Operators do not invoke this package as a CLI — `RBPAgent` / `Nanobot.from_config` load it.

## Layout

| Path | Role |
|------|------|
| `loop.py` / `runner.py` | Main loop and run wrappers |
| `context.py` | Context assembly (`ContextBuilder`) |
| `memory.py` | Long-term memory hooks (PA memory off in `scientific_mode`) |
| `skills.py` | Skill loading (`SkillsLoader`) |
| `hook.py` / `progress_hook.py` | Hook interfaces / progress |
| `autocompact.py` / `subagent.py` / `cron_turns.py` | Framework capabilities (tightened for RBP) |
| `model_presets.py` | Model presets |
| [`tools/`](tools/README.md) | Tool package root |
| [`tools/core/`](tools/core/README.md) | Tool runtime infrastructure |
| [`tools/rbp/`](tools/rbp/README.md) | **Product toolkit** |
| [`tools/legacy/`](tools/legacy/README.md) | PA / legacy stubs; default not allow-listed |

Skill SoT: [`../skills/rbp-agent/SKILL.md`](../skills/README.md). Canonical session/memory stores: `artifacts/` ([`ARCHITECTURE.md`](../../ARCHITECTURE.md) §2).

## Entry points / imports

```python
from nanobot.agent import AgentLoop, ContextBuilder, MemoryStore, SkillsLoader
from nanobot.agent.tools import ToolRegistry, Tool
```

Loaded indirectly via:

```python
from nanobot import Nanobot
from app.agent import RBPAgent
```

## Code examples

**Register curated RBP tools**

```python
from nanobot.agent.tools import ToolRegistry
from nanobot.agent.tools.rbp import register_all

reg = ToolRegistry()
names = register_all(reg)
print(names)  # predict_interaction, seq_similarity, …
```

**Defaults after product chat start**

```bash
# Env typically set by app bootstrap:
# NANOBOT_TOOL_ALLOW=rbp
# NANOBOT_TOOL_PLUGINS unset / off
python -m app.sync_overlay
pytest tests/test_proposal_compliance.py tests/test_package_layout.py
```

## Dependencies / env

- Requires a configured LLM provider for real turns.
- RBP tools call `app.backends.delivery` — need `DELIVERY_ROOT` for science.
- Optional: `RBP_PHMMER=1` enables phmmer remote-homology tool.

## Design rationale

- Legacy PA tools remain on disk for framework compatibility but stay off the allow list unless maintainers widen policy ([`AGENTS.md`](../../AGENTS.md)).
- LLM must not bypass `similarity_weighted_vote` or invent `prob` / `p_hat`.

## See also

[`../README.md`](../README.md) · [`tools/rbp/README.md`](tools/rbp/README.md) · [`../sdk/README.md`](../sdk/README.md) · [`../../docs/product/BINDING_PREDICTION_FLOW.zh.md`](../../docs/product/BINDING_PREDICTION_FLOW.zh.md) · [`../../app/README.md`](../../app/README.md)
