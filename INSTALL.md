# Installation guide

<p><b>English</b> · <a href="INSTALL.zh.md">中文</a></p>

> **Single entry for install / env / acceptance.** Overview: [README.md](README.md) / [README.zh.md](README.zh.md). Architecture: [ARCHITECTURE.md](ARCHITECTURE.md) / [ARCHITECTURE.zh.md](ARCHITECTURE.zh.md). Agent gates: [AGENTS.md](AGENTS.md).

## Portable layout (Linux)

```bash
export BIO_ROOT="${BIO_ROOT:-$HOME/bio_agent}"
cd "$BIO_ROOT/nanobot-bio"
source scripts/nbio.sh
# Conventions (discovered by nbio, or export explicitly):
#   DELIVERY_ROOT=$BIO_ROOT/rhobind_agent_delivery
#   RHOBIND_RELEASE=$DELIVERY_ROOT/release/rhobind_release_v1
#   RBP_TEST_DATA_ROOT=$BIO_ROOT/rhobind_testdata_v2/rhobind_testdata_v2/test_data
```

Do **not** treat a trial-machine absolute path as the only source of truth; `nbio` discovers paths on the host.

---

## 0. Prerequisites

| Item | Requirement | Notes |
|------|-------------|-------|
| OS | Linux x86_64 (Ubuntu 20.04+ verified) | macOS/WSL may run the agent layer; science stack unverified |
| Disk | ≥ 30 GB free | delivery bundle ~15 GB; conda science stack ~10 GB |
| Python | ≥ 3.10 (3.13 recommended) | In-repo slim nanobot shares the agent venv interpreter |
| conda / mamba | Required for full path; optional for agent-only | mamba recommended |
| GPU | Optional | Helps rhobind_predict / ESM / AF3; CPU can run doctor + chat |
| LLM API key | Required for `agent` / `chat` / `accept-llm` | `nanobot-bio onboard` picks provider; key in `.env` |

---

## 1. Three install paths

### Path A: One-shot script (fastest; recommended first install)

```bash
export BIO_ROOT="${BIO_ROOT:-$HOME/bio_agent}"
mkdir -p "$BIO_ROOT"
# Place this repo and delivery as siblings:
#   $BIO_ROOT/nanobot-bio/
#   $BIO_ROOT/rhobind_agent_delivery/
cd "$BIO_ROOT/nanobot-bio"

./scripts/nbio setup                  # full science stack + agent venv (= setup_all.sh)
# Optional GPU-specific thin wrappers (still call setup_all.sh):
# bash scripts/setup/setup_all_ampere_or_older.sh   # A100/H100/4090… → classic af3
# bash scripts/setup/setup_all_blackwell.sh         # CC12 → af3_blackwell
# Agent layer only (no conda):
# ./scripts/nbio setup --skip-conda

nanobot-bio onboard                   # pick LLM provider + key → .env
./scripts/nbio start                  # daily one-shot: heal AF3 → chat
# ./scripts/nbio start --dry-run
# source scripts/nbio && nanobot-bio doctor
```

`setup_all.sh` (via `nbio setup`) uses in-repo slim `nanobot/`. `pip install -e .` installs the in-repo package; do **not** also install `nanobot-ai` (it steals `import nanobot`). GPU selection: [docs/guides/AF3_RUNTIME_AND_RELEASE.md](docs/guides/AF3_RUNTIME_AND_RELEASE.md). Scripts map: [`scripts/README.md`](scripts/README.md).

**Env name present ≠ deps installed.** Delivery `setup_envs.sh` only creates missing conda **names**; a bare `conda create -n rhobind` leaves a hollow env. `nbio setup` / `setup_all.sh` run **import-level checks** and heal. Daily use `./scripts/nbio start` (or `source scripts/nbio` + `nanobot-bio chat`) — you need not re-run setup every time. `start` auto-discovers AF3 / conda on the host (`$AF3_BLACKWELL_ROOT`, sibling `af3_blackwell`, `~/af3_blackwell`, `conda info --base`, …). Use `start --dry-run` to list candidates only.

### Path B: Docker (isolated; good for operators who do not develop)

```bash
cd "$BIO_ROOT/nanobot-bio"
docker compose build                              # agent-only (light)
# docker compose --profile full build             # full science (heavy; GPU)
docker compose run --rm app onboard
docker compose run --rm app doctor
docker compose up app                             # = nanobot-bio chat
```

Data bundles mount via volumes (see `docker-compose.yml`), not baked into the image. See comments at the top of [Dockerfile](Dockerfile).

### Path C: Manual venv + conda (fine control)

> Running only `setup_envs.sh` will **not** heal an existing hollow env. After install, check with  
> `conda run -n rhobind python -c "import torch, transformers"` or use Path A.

```bash
cd "$BIO_ROOT/rhobind_agent_delivery"
bash agent/setup_envs.sh             # protein_embed / rna / rhobind / af3

cd "$BIO_ROOT/nanobot-bio"
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.lock
pip uninstall -y nanobot-ai nanobot 2>/dev/null || true
pip install -e ".[dev]"

python -c "import nanobot; print(nanobot.__file__)"   # must contain nanobot-bio/nanobot
python -m app.sync_overlay
cp .env.example .env
nanobot-bio doctor
```

---

## 2. Environment variables

Merged from README, [`.env.example`](.env.example), [`app/backends/delivery/env.py`](app/backends/delivery/env.py), and delivery setup. `apply_delivery_env()` fills defaults for missing keys — set vars only to override.

| Variable | Default | Required | Purpose |
|----------|---------|----------|---------|
| `BIO_ROOT` | parent of `nanobot-bio` | no | Workspace parent |
| `DELIVERY_ROOT` | `$BIO_ROOT/rhobind_agent_delivery` | yes* | Delivery bundle root |
| `NANOBOT_SRC` | `$NANOBOT_BIO_ROOT/nanobot` | yes* | In-repo slim nanobot (SoT == runtime) |
| `NANOBOT_BIO_ROOT` | `nanobot-bio/` | no | App package root |
| `NANOBOT_WORKSPACE` | `$NANOBOT_BIO_ROOT/workspace` | no | Workspace; sessions/memory → [ARCHITECTURE.md](ARCHITECTURE.md) §2 |
| `NANOBOT_CONFIG` | `~/.nanobot/config.json` | yes** | LLM provider/model + `${…_API_KEY}` refs |
| `AGENT_DB` | `$DELIVERY_ROOT/agent_db` | no | Registry / embeddings / DBs |
| `RBP_REGISTRY` | `$AGENT_DB/registry/rbp_registry.json` | no | RBP registry |
| `RHOBIND_RELEASE` | `$DELIVERY_ROOT/release/rhobind_release_v1` | no | Predictor checkpoints |
| `RBP_PROTEINS` | `$DELIVERY_ROOT/reference` | no | Reference proteins/structures |
| `AFDB_DIR` | `$RBP_PROTEINS/structures/afdb` | no | AFDB PDB dir |
| `TRANSFER_DIR` | `$AGENT_DB/transfer` | no | Delivery LOO transfer CSVs |
| `RBP_LOO_TRANSFER_DIR` | — | no | Agent-side expanded LOO copy (`rbp_eval/data/transfer`) |
| `RBP_TEST_DATA_ROOT` | — | no | Labeled FASTA root for expand-loo |
| `EMB_BANK` | `$AGENT_DB/embedding_bank` | no | ESM embedding bank |
| `FOLDSEEK_DB` / `SEQ_DB` / `PEAKS_DB` | under `$AGENT_DB` | no | Retrieve indexes |
| `USALIGN` | `$AGENT_DB/bin/USalign` | no | Structure align binary |
| `AF3_DIR` / `AF3_PARAMS` / `AF3_PYTHON` | delivery / conda | no | AF3 source, weights, interpreter |
| `RHOBIND_DEVICE` | `auto` | no | `auto`/`cuda`/`cpu` |
| `RBP_BACKEND` | `delivery` | no | Tool backend |
| `RBP_LLM_PROVIDER` / `RBP_LLM_MODEL` | (none) | no** | Set by `onboard` |
| Provider API keys | — | no** | Only in `nanobot-bio/.env`; config uses `${VAR}` |
| `HF_ENDPOINT` | `https://hf-mirror.com` | no | HF mirror for ESM weights |
| `OMP_NUM_THREADS` | `4` | no | Science tool threads |

\* Set automatically by `setup_all.sh` / Docker; export yourself on the manual path.  
\*\* `onboard` writes `.env` (secrets) and `~/.nanobot/config.json` (provider/model + `${…_API_KEY}`); no default provider.

`RNA_FM_CHECKPOINT` is **N/A** for current delivery. RNA evidence comes from `rna_blastn` and `PEAKS_DB` — do not invent RNA-FM paths to “enable” the RNA axis.

Workspace stores, slim-vendor residuals, and tool allowlists: [ARCHITECTURE.md](ARCHITECTURE.md) §2 / §6.

**RTX 5090 / Blackwell (CC 12):** delivery-pinned `af3` (jax 0.4.34) cannot infer. Install a parallel stack without editing delivery:

```bash
bash scripts/setup/setup_all_blackwell.sh
./scripts/nbio start --dry-run    # list AF3_BLACKWELL_ROOT / AF3_PYTHON candidates
./scripts/nbio start --heal       # write discovered paths into .env (backup first)
```

Do **not** hand-copy another machine’s absolute paths. Details: [docs/guides/AF3_RUNTIME_AND_RELEASE.md](docs/guides/AF3_RUNTIME_AND_RELEASE.md).

---

## 3. Data acquisition

The delivery bundle (`rhobind_agent_delivery/`) holds registry, embeddings, foldseek/mmseqs indexes, AFDB structures, LOO transfer matrix, rhobind checkpoints, and AF3 weights.

- **Existing bundle (recommended):** place `rhobind_agent_delivery/` next to `nanobot-bio/` under `$BIO_ROOT/`.
- **Rebuild from scratch:** see delivery `agent/database/SOURCES.md` and [`scripts/data/bootstrap_data.sh`](scripts/data/bootstrap_data.sh).

All data paths are env-driven; the bundle may live anywhere as long as `DELIVERY_ROOT` / `AGENT_DB` point correctly.

Optional labeled testdata for LOO expand:

```bash
export RBP_TEST_DATA_ROOT="${RBP_TEST_DATA_ROOT:-$BIO_ROOT/rhobind_testdata_v2/rhobind_testdata_v2/test_data}"
```

---

## 4. Acceptance

Authoritative path: `nanobot-bio accept-golden`. Full no-LLM cert:

```bash
bash scripts/cert/certify.sh --full
```

```bash
nanobot-bio doctor           # 1. env / paths / registry / skill / axes / AF3
nanobot-bio accept-golden    # 2. own-head golden
nanobot-bio accept-llm       # 3. LLM touchpoint (needs API key)
nanobot-bio gap-closure      # 4. Stage-0 / unseen fixture pack
nanobot-bio gate             # 5. ruff + pytest + layout (+ optional LOO)
```

Reports land under `artifacts/reports/{json,md,csv}/`. Sessions / PA memory / domain memory (`proxy_map`): [docs/guides/MEMORY_AND_SESSIONS.md](docs/guides/MEMORY_AND_SESSIONS.md).

### 4.1 CI and self-hosted runners

| job | runner | trigger | role |
| --- | --- | --- | --- |
| `test` | `ubuntu-latest` | every push/PR | ruff + pytest + layout + secret scan |
| `science` | `self-hosted, linux, science` | tag / manual | `accept-golden` |
| `eval` | `self-hosted, linux, science` | tag / manual | Stage-3 ablation + ECE |

Register a science runner with labels `self-hosted, linux, science` and set repo secret `DELIVERY_BUNDLE_PATH`. Release / promote: [ARCHITECTURE.md](ARCHITECTURE.md) §5 / §7.

---

## 5. FAQ

- **`predict_interaction` / doctor missing `torch` (hollow rhobind):** env name exists but release requirements were never installed. Fix with `bash scripts/setup/setup_all.sh`, not delivery `setup_envs.sh` alone.
- **AF3 deferred/broken:** Skill prefers AFDB `structure_fetch`; call `predict_structure` only on AFDB miss. Failure → caveat; do not invent structure sim=0.
- **Chat still “no key” after onboard:** secrets in `nanobot-bio/.env`; `~/.nanobot/config.json` holds `${…_API_KEY}` refs only.
- **CI skips own-head/LOO / delivery tests:** public CI has no GPU/bundle; locally set `DELIVERY_ROOT` or keep the sibling layout.
- **`docs/` not on GitHub:** local-only product docs may be gitignored; architecture policy remains in root [ARCHITECTURE.md](ARCHITECTURE.md).
