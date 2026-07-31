# scripts/setup/

**First-time install / repair** scripts for Linux / SSH hosts. Day-to-day use [`../nbio`](../nbio) at the repo root.

[English] · [中文](README.zh.md)

## Features

- One-shot (re-runnable) setup of agent `.venv` + delivery science conda + optional AF3 harden
- **Import-level verify + heal**: `rhobind` (torch+transformers), `protein_embed` (transformers), `rna` (mmseqs), `af3` (usable python)
- Auto AF3 stack selection by GPU compute capability (Blackwell CC 12.* vs classic `af3`)
- Thin Ampere / Blackwell wrappers

## Daily vs first-time

| Scenario | Command |
|----------|---------|
| **Daily** | `source scripts/nbio` → `nanobot-bio doctor` → `nanobot-bio chat` |
| **First / hollow-env repair** | `./scripts/nbio setup` (or `setup_all.sh` here) |
| Legacy activate | `source scripts/setup/activate_env.sh` → forwards to `nbio activate` |

`nbio` **activate never** auto `pip install`s CUDA/torch; doctor marks FAIL and you repair with `nbio setup`.

## Implementation

| Script | When |
|--------|------|
| [`../nbio`](../nbio) | **User entry**: activate / status / doctor / setup / chat |
| `setup_all.sh` | Called by `nbio setup`; `AF3_STACK=auto` |
| `setup_all_ampere_or_older.sh` | Thin wrap: force `AF3_STACK=classic` |
| `setup_all_blackwell.sh` | Thin wrap: force `AF3_STACK=blackwell` |
| `setup_af3_blackwell.sh` | Out-of-tree AF3 only; override with `AF3_ROOT` / `ENV_PREFIX` |
| `activate_env.sh` | Compat wrap → `source ../nbio activate` |

## How to use

```bash
./scripts/nbio setup
./scripts/nbio setup --skip-conda
bash scripts/setup/setup_all_blackwell.sh

source scripts/nbio
./scripts/nbio status
nanobot-bio doctor
```

Full narrative: [`INSTALL.md`](../../INSTALL.md).

## See also

[`../README.md`](../README.md) · [`INSTALL.md`](../../INSTALL.md) · [`../nbio`](../nbio)
