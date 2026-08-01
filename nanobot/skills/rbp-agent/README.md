# nanobot/skills/rbp-agent/

Product skill pack (SoT): RNA–RBP interaction stages and tool discipline.

[English] · [中文](README.zh.md)

## Purpose

Always-on Nanobot skill that teaches the agent *when* to stop at own-head, how to handle near-known / unseen queries, and that `p_hat` may come **only** from predict / vote tools. Stages are scientific gates — not a fixed shortlist; the agent may use the full registered delivery surface (`RBP_RAW_TOOLS=all` by default; set `whitelist` to narrow). This directory is the source of truth; `python -m app.sync_overlay` copies it into `workspace/skills/rbp-agent/` for runtime. Do not invent a third copy under `plugin/`.

## Layout

| Path | Role |
|------|------|
| `SKILL.md` | Skill front-matter + stage rules (authoritative) |
| `references/` | Extra snippets (`stages.md`, `verdict.md`) |

Synced destination: [`../../../workspace/skills/rbp-agent/`](../../../workspace/skills/rbp-agent/) (runtime; may contain `DO_NOT_EDIT.md`).

## Entry points

```bash
$EDITOR nanobot/skills/rbp-agent/SKILL.md
python -m app.sync_overlay
nanobot-bio doctor
```

```python
from app.agent import skill_path, ensure_workspace_skill

print(skill_path())
print(ensure_workspace_skill())
```

Loaded by `nanobot.agent.skills.SkillsLoader` when the product workspace starts.

## Code examples

**Front-matter (from `SKILL.md`)**

```yaml
name: rbp-agent
metadata: {"nanobot":{"emoji":"🧬","always":true}}
always: true
```

**Locate + ensure overlay**

```python
from pathlib import Path
from app.agent import skill_path, ensure_workspace_skill

sot = Path(skill_path())
assert sot.name == "SKILL.md"
assert "rbp-agent" in str(sot)
ws = Path(ensure_workspace_skill())
print(ws)
```

Binding stages: [`../../../docs/product/BINDING_PREDICTION_FLOW.zh.md`](../../../docs/product/BINDING_PREDICTION_FLOW.zh.md).

## Dependencies / env

- Markdown skill + references only at rest.
- Runtime needs Nanobot + RBP tools from `nanobot/agent/tools/rbp/`.
- Edit SoT here; treat `workspace/skills/rbp-agent/` as generated overlay.

## See also

[`../README.md`](../README.md) · [`../../agent/tools/rbp/README.md`](../../agent/tools/rbp/README.md) · [`../../../workspace/skills/README.md`](../../../workspace/skills/README.md)
