# nanobot/skills/

Skill source-of-truth directory (Markdown skill packs). Not a Python package.

[English] · [中文](README.zh.md)

## Purpose

Skills teach the agent *when* and *how* to call tools. For nanobot-bio the product skill is `rbp-agent`: Stage 0 own-head fast path, near-known handling, unseen retrieve→fuse→predict→integrate, and the rule that `p_hat` comes only from predict tools. This tree is SoT; `python -m app.sync_overlay` copies it into `workspace/skills/` for runtime.

## Layout

| Path | Role |
|------|------|
| [`rbp-agent/`](rbp-agent/README.md) · `SKILL.md` | Product skill (always-on) |
| `rbp-agent/references/` | Extra reference snippets for the skill |

Synced destination: `workspace/skills/rbp-agent/` (see [`../../workspace/README.md`](../../workspace/README.md)).

## Entry points

Loaded by `nanobot.agent.skills.SkillsLoader` when Nanobot starts with the product workspace. Operators edit the SoT file here (or rely on overlay sync).

```bash
# Edit SoT, then sync + verify:
$EDITOR nanobot/skills/rbp-agent/SKILL.md
python -m app.sync_overlay
nanobot-bio doctor
```

## Code examples

**Locate skill from product helpers**

```python
from app.agent import skill_path, ensure_workspace_skill

print(skill_path())
print(ensure_workspace_skill())  # ensures workspace/skills/rbp-agent/SKILL.md
```

**Skill front-matter (excerpt)**

```yaml
name: rbp-agent
metadata: {"nanobot":{"emoji":"🧬","always":true}}
always: true
```

Binding stages: [`docs/product/BINDING_PREDICTION_FLOW.zh.md`](../../docs/product/BINDING_PREDICTION_FLOW.zh.md).

## Dependencies / env

- Markdown only at rest; runtime needs Nanobot + RBP tools mounted.
- Do not duplicate a third copy of tools under `plugin/` — SoT is this tree + `agent/tools/rbp/`.

## See also

[`../README.md`](../README.md) · [`../agent/tools/rbp/README.md`](../agent/tools/rbp/README.md) · [`../../workspace/skills/README.md`](../../workspace/skills/README.md) · [`../../docs/product/BINDING_PREDICTION_FLOW.zh.md`](../../docs/product/BINDING_PREDICTION_FLOW.zh.md)
