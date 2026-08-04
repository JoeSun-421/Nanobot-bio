# nanobot/

Slim in-repo Nanobot runtime **plus** RBP skill & tools. SoT == runtime: `import nanobot` must resolve here.

[English] · [中文](README.zh.md)

## Purpose

This tree is the agent framework used by the product: high-level `Nanobot` API, agent loop, session store, LLM providers, and the RBP skill/toolkit. Packaging (`pyproject.toml`) includes `nanobot*` so an editable install exposes **this** directory — never install PyPI `nanobot-ai` alongside it.

Product collaborators normally enter through [`app/`](../app/README.md) (`nanobot-bio chat|agent`). Direct `python -m nanobot` is framework-oriented and not the RBP product UX. Stage discipline and tool contracts live in `skills/rbp-agent/SKILL.md` and [`docs/product/BINDING_PREDICTION_FLOW.zh.md`](../docs/product/BINDING_PREDICTION_FLOW.zh.md).



## Portable layout (Linux)

```bash
export BIO_ROOT="${BIO_ROOT:-$HOME/bio_agent}"
cd "$BIO_ROOT/nanobot-bio"
source scripts/nbio.sh
```

## Layout

| Path | Role |
|------|------|
| `nanobot.py` | Public high-level API (`Nanobot.from_config` / `run` / `run_streamed`) |
| [`agent/`](agent/README.md) | Loop, memory, context, skills, **tools** |
| [`agent/tools/rbp/`](agent/tools/rbp/README.md) | Product toolkit (retrieve / predict / structure / …) |
| [`sdk/`](sdk/README.md) | Internal SDK helpers (clients / streaming / types) |
| [`session/`](session/README.md) | Session storage (canonical data under `artifacts/sessions`) |
| [`skills/`](skills/README.md) | Skill SoT (`rbp-agent/SKILL.md`); synced to `workspace/skills/` |
| [`providers/`](providers/README.md) | LLM provider adapters |
| [`config/`](config/README.md) · [`bus/`](bus/README.md) · [`command/`](command/README.md) · [`cron/`](cron/README.md) · [`security/`](security/README.md) · [`utils/`](utils/README.md) | Framework support |
| [`legacy/`](legacy/README.md) · [`templates/`](templates/README.md) | Legacy / templates; not the primary product path |

Defaults: `NANOBOT_TOOL_ALLOW=rbp`; `NANOBOT_TOOL_PLUGINS` off unless set. Chat also unregisters noisy PA tools in `app/agent.py`.

## Entry points

```python
from nanobot import Nanobot, RunResult
```

```bash
nanobot-bio chat|agent          # product path
python -m app.sync_overlay      # after editing skill / RBP tools
nanobot-bio doctor
```

## Code examples

**High-level Nanobot (framework)**

```python
from nanobot import Nanobot

bot = Nanobot.from_config(workspace="workspace", scientific_mode=True)
# Prefer ephemeral turns for MVP / eval:
result = await bot.run("Summarize workspace AGENTS.md", ephemeral=True)
print(result.content)
```

**Product assembly (preferred)**

```python
from app.agent import RBPAgent

agent = RBPAgent()
result = agent.run_sync("Predict binding for PTBP1 on the sample RNA.")
print(result.verdict)
```

## Dependencies / env

- LLM credentials via `~/.nanobot/config.json` / `.env` (`nanobot-bio onboard`).
- Science tools need delivery (`DELIVERY_ROOT`) — Nanobot itself stays free of torch/jax model stacks.
- Do **not** `pip install nanobot-ai` — it steals the import name.

## Design rationale

- **SoT == runtime** avoids a third tools tree and sync drift ([`ARCHITECTURE.md`](../ARCHITECTURE.md) §6).
- Scientific mode disables automatic Dream / idle compaction / token consolidator and excludes PA `MEMORY.md` from the science prompt.
- Session/memory stacks stay wired even when product defaults tighten PA behaviour — do not blind-delete them.

## See also

[`../README.md`](../README.md) · [`ARCHITECTURE.md`](../ARCHITECTURE.md) · [`../app/README.md`](../app/README.md) · [`../docs/product/BINDING_PREDICTION_FLOW.zh.md`](../docs/product/BINDING_PREDICTION_FLOW.zh.md) · [`../workspace/README.md`](../workspace/README.md)
