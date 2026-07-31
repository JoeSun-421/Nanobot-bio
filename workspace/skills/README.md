# workspace/skills/

Runtime skill copies synced from in-repo SoT.

[English] · [中文](README.zh.md)

## Features

- Workspace skill directory Nanobot loads at runtime
- Current product skill: `rbp-agent/`
- Sync from SoT; may include a `DO_NOT_EDIT.md` hint after overlay

## Implementation

| Location | Role |
|----------|------|
| **SoT (edit here)** | `nanobot/skills/rbp-agent/SKILL.md` |
| **Runtime copy** | `workspace/skills/rbp-agent/` (from `sync_overlay`) |

`rbp-agent` skill highlights (see SoT for full stage rules):

- Stage 0: in-catalogue RBP → `resolve_rbp` + one `predict_interaction` (own-head), then stop with JSON verdict
- Unseen RBP: retrieve → donor predict → integrate; `p_hat` only from predict / vote tools
- Two LLM checkpoints (retrieval reasoning / explanation); no fabricated scores

## How to use

```bash
python -m app.sync_overlay
# or
nanobot-bio doctor
```

Then run `nanobot-bio chat` / `agent`. For authoring, open the SoT file under `nanobot/skills/`, not only this copy.

## Design rationale

- Runtime workspace needs a skill path; keeping SoT inside `nanobot/` preserves slim-vendor “SoT == runtime” for tools while still syncing a workspace-visible skill tree.
- Editing only the workspace copy loses changes on the next sync.
- Skill text must never instruct the model to invent probabilities or skip delivery voting ([`AGENTS.md`](../../AGENTS.md)).

## See also

[`../README.md`](../README.md) · [`../../nanobot/README.md`](../../nanobot/README.md) · [`AGENTS.md`](../../AGENTS.md)
