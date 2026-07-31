# scripts/

Operator scripts for nanobot-bio. **Day-to-day entry:** [`nbio`](nbio).

[English] · [中文](README.zh.md)

## Features

- **`nbio`**: portable activate / status / doctor / setup / chat (Linux)
- Setup: agent `.venv` + delivery science conda + AF3 stack selection
- CI / Cert / Docker / Data helpers (unchanged filenames)

## Implementation

| Path | Role |
|------|------|
| [`nbio`](nbio) | **Single user entry** (detect + activate; setup is explicit) |
| [`setup/`](setup/README.md) | Heavy install (`setup_all*`); `activate_env.sh` → `nbio` |
| [`ci/`](ci/README.md) | Secret scan + engineering gate |
| [`cert/`](cert/README.md) | Non-LLM certify, manifests, smokes |
| [`docker/`](docker/README.md) | Container entrypoint |
| [`data/`](data/README.md) | Idempotent delivery DB rebuild |

```
scripts/
  nbio                 ← daily entry
  setup/               setup_all*, activate_env.sh (compat)
  ci/ cert/ docker/ data/
```

## How to use

```bash
git clone https://github.com/JoeSun-421/Nanobot-bio.git
cd Nanobot-bio
./scripts/nbio setup
source scripts/nbio
nanobot-bio doctor
nanobot-bio chat
```

Install narrative: [`INSTALL.md`](../INSTALL.md).

## See also

[`../README.md`](../README.md) · [`INSTALL.md`](../INSTALL.md) · [`nbio`](nbio)
