# scripts/

Operator scripts for nanobot-bio. **Day-to-day entry:** [`nbio`](nbio).

[English] · [中文](README.zh.md)

## Features



## Portable layout (Linux)

```bash
export BIO_ROOT="${BIO_ROOT:-$HOME/bio_agent}"
cd "$BIO_ROOT/nanobot-bio"
source scripts/nbio.sh
```

- **`nbio`**: portable activate / status / doctor / setup / chat / **start** (one-shot)
- Setup: agent `.venv` + delivery science conda + AF3 stack selection
- CI / Cert / Docker / Data helpers (unchanged filenames)

## Path discovery (not AutoDL-specific)

`nbio` / `setup_*` **discover paths on the current host**. Trial-machine absolutes such as `/root/autodl-tmp/...` are optional last-resort candidates, never the only source of truth:

| Target | Candidate order (summary) |
|--------|---------------------------|
| `BIO_ROOT` / delivery | Relative to `scripts/nbio` checkout → `$BIO_ROOT` / `$DELIVERY_ROOT` (only if still present) |
| `AF3_BLACKWELL_ROOT` | `$AF3_BLACKWELL_ROOT` → `$BIO_ROOT/af3_blackwell` → sibling of BIO parent → `~/af3_blackwell` → `/opt/af3_blackwell` → other host layouts (incl. AutoDL) |
| `AF3_PYTHON` | `$ENV_PREFIX` → `conda info --base` → `$CONDA_PREFIX` / common miniconda·anaconda → host-specific |

`./scripts/nbio start` (or `--dry-run`) prints the candidate list and selection, then heals `.env` for this machine (backup `.env.bak.nbio.*`). On a new host: place delivery (+ optional af3_blackwell), then `nbio setup` → `nbio start` — no need to hand-copy AutoDL absolute paths.

## Implementation

| Path | Role |
|------|------|
| [`nbio`](nbio) | **Single user entry** (detect + activate; setup is explicit) |
| [`setup/`](setup/README.md) | Heavy install (`setup_all*`); `activate_env.sh` → `nbio` (compat wrappers) |
| [`ci/`](ci/README.md) | Secret scan + engineering gate |
| [`cert/`](cert/README.md) | Non-LLM certify, manifests, smokes |
| [`docker/`](docker/README.md) | Container entrypoint |
| [`data/`](data/README.md) | Idempotent delivery DB rebuild |

```
scripts/
  nbio                 ← daily entry (canonical)
  setup/               setup_all*; activate_env / ampere / blackwell = thin compat
  ci/ cert/ docker/ data/
```

## How to use

```bash
git clone https://github.com/JoeSun-421/Nanobot-bio.git
cd Nanobot-bio
./scripts/nbio setup                 # first time
./scripts/nbio start                 # one-shot: discover paths → heal AF3 → chat
# ./scripts/nbio start --dry-run     # show candidate list + adaptation only
# source scripts/nbio && nanobot-bio chat
```

`start` / `up` picks classic vs blackwell from GPU `compute_cap`, then aligns `AF3_DIR` / `AF3_PYTHON` / `AF3_CACHE` (default: heal `.env` with backup; `--no-heal` = session-only). Install narrative: [`INSTALL.md`](../INSTALL.md).

## Delivery bridge

Science I/O goes through the App delivery package (not scripts). Brief pointer: [`../app/backends/delivery/README.md`](../app/backends/delivery/README.md) · [中文](../app/backends/delivery/README.zh.md).

## See also

[`../README.md`](../README.md) · [`INSTALL.md`](../INSTALL.md) · [`nbio`](nbio)
