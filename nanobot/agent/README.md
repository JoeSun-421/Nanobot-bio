# nanobot/agent/

Agent loop, memory/context, skills loader, and tool packages.

[English] · [中文](README.zh.md)

## Features

- Multi-turn agent loop and runner wrappers
- Context assembly, memory hooks, skill loading
- Tool trees: `tools/core` (runtime infra), `tools/rbp` (product), `tools/legacy` (PA stubs, not in default allow list)
- Optional framework helpers (autocompact, subagent, cron turns) — product path keeps these constrained

## Implementation

| Path | Role |
|------|------|
| `loop.py` / `runner.py` | Main loop and run wrappers |
| `context.py` | Context assembly |
| `memory.py` | Long-term memory hooks (PA memory off in scientific_mode) |
| `skills.py` | Skill loading |
| `autocompact.py` / `hook.py` / `progress_hook.py` / `subagent.py` / `cron_turns.py` | Framework capabilities (tightened for RBP product) |
| `model_presets.py` | Model presets |
| `tools/core/` | Tool runtime infrastructure |
| `tools/rbp/` | **Product toolkit** (retrieve / predict / structure / …) |
| `tools/legacy/` | PA / legacy stubs; default not allow-listed |

Skill SoT for stage discipline (Stage 0 own-head fast path, etc.): `nanobot/skills/rbp-agent/SKILL.md`.

Canonical session/memory stores live under `artifacts/` (see [`ARCHITECTURE.md`](../../ARCHITECTURE.md) §2); `workspace/` holds symlinks.

## How to use

Loaded indirectly via `app.agent.RBPAgent` / `Nanobot.from_config`. Operators do not invoke this package as a CLI.

Defaults:

- `NANOBOT_TOOL_ALLOW=rbp`
- `NANOBOT_TOOL_PLUGINS` unset / off

After editing `tools/rbp` or the skill, sync overlay and run compliance tests:

```bash
python -m app.sync_overlay
pytest tests/test_proposal_compliance.py tests/test_package_layout.py
```

## Design rationale

- Product science behaviour is driven by **RBP tools + skill**, with outbound calls through the App delivery bridge.
- Legacy PA tools remain on disk for framework compatibility but stay off the allow list unless maintainers widen policy ([`AGENTS.md`](../../AGENTS.md)).
- LLM must not bypass `similarity_weighted_vote` or invent `prob` / `p_hat`.

## See also

[`../README.md`](../README.md) · [`../sdk/README.md`](../sdk/README.md) · [`../../app/README.md`](../../app/README.md)
