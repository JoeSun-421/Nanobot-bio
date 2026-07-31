# nanobot/

Slim in-repo Nanobot runtime **plus** RBP skill & tools. SoT == runtime: `import nanobot` must resolve here.

[English] · [中文](README.zh.md)

## Features

- High-level `Nanobot` API (`from_config` / `run` / `run_streamed`) for the product CLI
- Agent loop, session store, LLM providers, and internal SDK helpers
- Product skill SoT: `skills/rbp-agent/SKILL.md`
- Product toolkit under `agent/tools/rbp/` (retrieve / predict / structure / …)
- Slim-vendor policy: PA surfaces (channels / webui / …) stripped; asserted by `rbp-agent layout`

## Implementation

| Path | Role |
|------|------|
| `nanobot.py` | Public high-level API |
| [`agent/`](agent/README.md) | Loop, memory, context, skills, **tools** |
| [`sdk/`](sdk/README.md) | Internal SDK helpers (clients / streaming / types) |
| `session/` | Session storage/management (canonical data under `artifacts/sessions`) |
| `skills/rbp-agent/` | Skill source of truth; synced to `workspace/skills/` |
| `providers/` | LLM provider adapters |
| `config/` · `bus/` · `command/` · `cron/` · `security/` · `utils/` | Framework support |
| `legacy/` · `templates/` | Legacy / templates; not the primary product path |

Tool loading defaults: `NANOBOT_TOOL_ALLOW=rbp`; `NANOBOT_TOOL_PLUGINS` off unless set. Chat also unregisters noisy PA tools in `app/agent.py`.

Packaging: `pyproject.toml` includes `nanobot*` via setuptools so editable install exposes this tree.

## How to use

Product users normally go through the App CLI, not `python -m nanobot`:

```bash
nanobot-bio chat|agent
# Inside App: Nanobot.from_config → run / run_streamed
# Prefer ephemeral=True for MVP / eval turns
```

After editing skill or RBP tools:

```bash
python -m app.sync_overlay
nanobot-bio doctor
```

Do **not** `pip install nanobot-ai` alongside this package — it steals the import name.

## Design rationale

- **SoT == runtime** avoids a third tools tree and sync drift (Proposal / ARCHITECTURE §6).
- Keep heavy science (torch / jax models) out of the Nanobot process; call delivery via App bridge.
- Scientific mode disables automatic Dream / idle compaction / token consolidator and excludes PA `MEMORY.md` from the science prompt ([`ARCHITECTURE.md`](../ARCHITECTURE.md) §2).
- Session/memory stacks stay wired even when product defaults tighten PA behaviour — do not blind-delete them.

## See also

[`../README.md`](../README.md) · [`ARCHITECTURE.md`](../ARCHITECTURE.md) · [`../app/README.md`](../app/README.md) · [`../workspace/README.md`](../workspace/README.md)
