# workspace/

Nanobot workspace root: synced skills and symlinked session/memory views.

[English] · [中文](README.zh.md)

## Features

- Runtime workspace expected by Nanobot (`NANOBOT_WORKSPACE`)
- Synced skill copies under `skills/` (see [`skills/README.md`](skills/README.md))


## Portable layout (Linux)

```bash
export BIO_ROOT="${BIO_ROOT:-$HOME/bio_agent}"
cd "$BIO_ROOT/nanobot-bio"
source scripts/nbio.sh
```

- Symlinks `sessions` → `../artifacts/sessions`, `memory` → `../artifacts/memory` (no dual-write)
- Short workspace bootstrap notes in `AGENTS.md`

## Implementation

| Path | Notes |
|------|-------|
| `skills/rbp-agent/` | Produced by `python -m app.sync_overlay` from SoT; not the long-term edit target |
| `sessions` → `../artifacts/sessions` | Session transcripts symlink |
| `memory` → `../artifacts/memory` | PA long-term memory symlink (excluded from scientific prompts) |
| `AGENTS.md` | Workspace-level short cues (Stage 0 own-head, …) |

Canonical stores and helpers: `app.core.paths.ensure_artifact_dirs()`. Detail: [`ARCHITECTURE.md`](../ARCHITECTURE.md) §2 (local `docs/guides/MEMORY_AND_SESSIONS.zh.md` if present).

Env:

- `NANOBOT_WORKSPACE` defaults to `$NANOBOT_BIO_ROOT/workspace`
- Session/memory bytes still land under `artifacts/`

`.gitignore` ignores `workspace/memory/*`, `workspace/.nanobot/`, and the `workspace/sessions` symlink path pattern as configured.

## How to use

```bash
export NANOBOT_WORKSPACE=$PWD/workspace   # usually set by setup / defaults
python -m app.sync_overlay
nanobot-bio chat
```

Edit skill SoT at `nanobot/skills/rbp-agent/SKILL.md`, then sync — do not treat the workspace copy as the only source.

## Design rationale

- Nanobot historically expects a workspace directory; artifacts remain the **canonical** store so large/sensitive outputs stay gitignored in one tree.
- Symlinks avoid copying session/memory blobs into two places.
- Overlay sync keeps runtime skill copies aligned with in-repo SoT without a third tools tree.

## See also

[`skills/README.md`](skills/README.md) · [`../artifacts/README.md`](../artifacts/README.md) · [`../nanobot/README.md`](../nanobot/README.md) · [`ARCHITECTURE.md`](../ARCHITECTURE.md)
