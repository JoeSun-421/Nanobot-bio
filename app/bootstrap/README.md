# app/bootstrap/

SoT locate, workspace skill sync, and RBP tool-install helpers.

**Does not** import `app.agent`, to avoid registry ↔ agent cycles.

[English] · [中文](README.zh.md)

## Modules

| Module | Role |
|--------|------|
| `sot.py` | `sot_root` / `skill_md` / `tools_rbp` |
| `sync_overlay.py` | Link into `workspace/skills/rbp-agent` |
| `rbp_bootstrap.py` | `install_rbp_tools_into_nanobot` |

Root-level compat entry only: `python -m app.sync_overlay` (thin re-export). New code should `from app.bootstrap import …`.

## Usage

```bash
export BIO_ROOT="${BIO_ROOT:-$HOME/bio_agent}"
cd "${NANOBOT_BIO_ROOT:-$BIO_ROOT/Nanobot-bio}"
source scripts/nbio.sh

# After editing nanobot/skills/rbp-agent or nanobot/agent/tools/rbp:
python -m app.sync_overlay
nanobot-bio doctor
```

## See also

[`../README.md`](../README.md) · [`../../nanobot/skills/rbp-agent/README.md`](../../nanobot/skills/rbp-agent/README.md) · [`../../workspace/skills/README.md`](../../workspace/skills/README.md)
