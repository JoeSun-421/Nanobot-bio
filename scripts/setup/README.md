# scripts/setup/

**First-time install / repair** scripts for Linux / SSH hosts. Day-to-day use [`../nbio.sh`](../nbio.sh) at the repo root.

[English] · [中文](README.zh.md)

> Parent package map and `$BIO_ROOT` layout: [`README.md`](../../README.md). Activate with `cd "${NANOBOT_BIO_ROOT:-$BIO_ROOT/Nanobot-bio}" && source scripts/nbio.sh`.

## Features

- One-shot (re-runnable) setup of agent `.venv` + delivery science conda + optional AF3 harden
- **Import-level verify + heal**: `rhobind` (torch+transformers), `protein_embed` (transformers), `rna` (mmseqs), `af3` (usable python)
- Auto AF3 stack selection by GPU compute capability (Blackwell CC 12.* vs classic `af3`)
- Thin Ampere / Blackwell wrappers

## Daily vs first-time

| Scenario | Command |
|----------|---------|
| **Daily** | `./scripts/nbio.sh start` (or `source scripts/nbio.sh` → chat) |
| **First / hollow-env repair** | `./scripts/nbio.sh setup` (or `setup_all.sh` here) |
| Legacy activate | `source scripts/setup/activate_env.sh` → forwards to `nbio activate` |

Paths (`AF3_ROOT` / `ENV_PREFIX` / delivery) are discovered on the host; see [`../README.md`](../README.md) “Path discovery”. AutoDL layouts are candidates only.

`nbio` **activate never** auto `pip install`s CUDA/torch; doctor marks FAIL and you repair with `nbio setup`.

## Implementation

| Script | When |
|--------|------|
| [`../nbio.sh`](../nbio.sh) | **User entry (canonical)**: activate / status / doctor / setup / chat / start |
| `setup_all.sh` | Called by `nbio setup`; `AF3_STACK=auto`; portable AF3 path discovery |
| `setup_all_ampere_or_older.sh` | Thin compat wrap: force `AF3_STACK=classic` |
| `setup_all_blackwell.sh` | Thin compat wrap: force `AF3_STACK=blackwell` |
| `setup_af3_blackwell.sh` | Out-of-tree AF3 only; override with `AF3_ROOT` / `ENV_PREFIX`; host discovery, not AutoDL-specific |
| `activate_env.sh` | Compat wrap → `source ../nbio activate` |

## How to use

```bash
./scripts/nbio.sh setup
./scripts/nbio.sh setup --skip-conda
bash scripts/setup/setup_all_blackwell.sh

./scripts/nbio.sh start # daily: discover → heal AF3 → chat
# source scripts/nbio.sh && nanobot-bio doctor
./scripts/nbio.sh status
```

Full narrative: [`INSTALL.md`](../../INSTALL.md).

## See also

[`../README.md`](../README.md) · [`INSTALL.md`](../../INSTALL.md) · [`../nbio.sh`](../nbio.sh)
