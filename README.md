<div align="center">
  <img src="assets/nanobot_logo.png" alt="nanobot-bio" width="420">

  <h1>Nanobot-bio</h1>
  <p>RNA–RBP interaction prediction agent</p>

  <p>
    <a href="https://github.com/JoeSun-421/Nanobot-bio/stargazers"><img src="https://img.shields.io/github/stars/JoeSun-421/Nanobot-bio?style=flat" alt="Stars"></a>
    <a href="https://github.com/HKUDS/nanobot"><img src="https://img.shields.io/badge/Nanobot-HKUDS%2Fnanobot-111111?logo=github" alt="Nanobot"></a>
    <img src="https://img.shields.io/badge/python-%E2%89%A53.10-blue" alt="Python ≥3.10">
    <img src="https://img.shields.io/badge/version-0.5.1-green" alt="Version">
    <a href="https://github.com/JoeSun-421/Nanobot-bio/actions/workflows/ci.yml"><img src="https://img.shields.io/github/actions/workflow/status/JoeSun-421/Nanobot-bio/ci.yml?branch=main&label=CI" alt="CI"></a>
    <img src="https://img.shields.io/badge/license-MIT-green" alt="License">
  </p>

  <p><b>English</b> · <a href="README.zh.md">中文</a></p>
</div>

## Project intro

**nanobot-bio** is a command-line scientific agent for RNA–protein binding prediction, built on [Nanobot](https://github.com/HKUDS/nanobot) and bridged to the RhoBind and multi-modal retrieval stack via the sibling `rhobind_agent_delivery` toolkit. Given an RBP identity and an RNA sequence, the system returns a typed JSON verdict: `label`, `confidence`, `p_hat`, `explanation`, `supporting_rbps`.

Two operating modes:

- **Own-head:** the target RBP is in the catalogue / panel and has a RhoBind head → score that head directly and produce a verdict.
- **Transfer:** out-of-panel or unseen target → retrieve donor RBPs via multi-modal search, then aggregate donor predictions with weighted voting (`similarity_weighted_vote`).

Prediction pipeline overview:

| Stage | Role |
|-------|------|
| **0** | Resolve RBP identity; if in-panel → own-head predict and stop |
| **1** | Multi-view retrieve → fuse similarities → select donors (abstain if needed) |
| **2** | Batched `predict_interaction` on donors; default weighted aggregate |
| **3** | Evidence checklist + optional priors → write verdict |

Stage rules and tool discipline: [`nanobot/skills/rbp-agent/SKILL.md`](nanobot/skills/rbp-agent/SKILL.md). Collaborator hand-off: [`HANDOFF.md`](HANDOFF.md).

## Portable layout (Linux)

```bash
export BIO_ROOT="${BIO_ROOT:-$HOME/bio_agent}"
# GitHub checkout is typically Nanobot-bio; lowercase nanobot-bio is also fine.
# Or set NANOBOT_BIO_ROOT to the directory that contains scripts/nbio.sh.
cd "${NANOBOT_BIO_ROOT:-$BIO_ROOT/Nanobot-bio}"
source scripts/nbio.sh
```

Expected siblings under `$BIO_ROOT`:

```text
$BIO_ROOT/
  Nanobot-bio/                 # this repo (package name: nanobot-bio)
  rhobind_agent_delivery/      # science toolkit (read-only from the agent)
  rhobind_testdata_v2/         # optional; LOO expand
```

Do not hardcode a trial-machine absolute path; `nbio.sh` discovers `DELIVERY_ROOT` / AF3 / conda on the host.

> **Note:** Product guides under `docs/` are **local-only** (gitignored; never pushed). Public SoT is this README, [`INSTALL.md`](INSTALL.md), [`ARCHITECTURE.md`](ARCHITECTURE.md), [`AGENTS.md`](AGENTS.md), package READMEs, and `SKILL.md`.

## Quick start

```bash
export BIO_ROOT="${BIO_ROOT:-$HOME/bio_agent}"
cd "${NANOBOT_BIO_ROOT:-$BIO_ROOT/Nanobot-bio}"

./scripts/nbio.sh setup              # first-time: agent .venv + science conda
nanobot-bio onboard                  # pick LLM provider + API key → .env + config refs
./scripts/nbio.sh start              # daily one-shot: discover paths → heal AF3/.env → chat
# ./scripts/nbio.sh start --dry-run
# source scripts/nbio.sh && nanobot-bio doctor
```

Install: [INSTALL.md](INSTALL.md) · [中文](INSTALL.zh.md). Scripts: [`scripts/README.md`](scripts/README.md). Delivery bridge: [`app/backends/delivery/README.md`](app/backends/delivery/README.md).

One-shot prediction example:

```bash
nanobot-bio agent --message "Does PTBP1 bind this RNA? <RNA sequence>"
# or structured inputs:
nanobot-bio agent --query PTBP1 --rna-file path/to/rna.txt --device auto
# or delivery golden RNA:
nanobot-bio agent --example pos
```

## Common commands & features

| Command | Purpose |
|---------|---------|
| `./scripts/nbio.sh start` | Daily one-shot: path discovery → GPU/AF3 adapt → heal `.env` → chat (`up` alias) |
| `nanobot-bio chat` | Multi-turn session; in-chat `/help` lists slash cmds (`/status`, `/tools`, `/new`, `/quit`, …) |
| `nanobot-bio agent --message "..."` | One-shot prediction (also `--query` / `--rna-file` / `--example pos\|neg`) |
| `nanobot-bio doctor` | Capability table: paths, rhobind/ESM/RNA/AF3/LLM (`--verbose` for dumps) |
| `source scripts/nbio.sh` | Portable activate only (also `status` / `setup` / `chat`) |
| `nanobot-bio onboard` | Write LLM provider / API key / model |
| `nanobot-bio accept-golden` | Own-head golden acceptance (no LLM; `own-head` is its alias) |
| `nanobot-bio accept-llm` | LLM touchpoint acceptance |
| `nanobot-bio run-eval` | LOO ceiling comparison and modality ablation |
| `nanobot-bio evolve` | Offline self-evolution → `config/evolved.candidate.yaml` |
| `nanobot-bio promote-evolved` | Promote candidate → `evolved.yaml` (gated) |
| `nanobot-bio heavy-loo` | Hide-own-head LOO: recovered AUPRC and instance-level metrics |
| `nanobot-bio expand-loo-matrix` | Expand agent-side LOO transfer CSV copy |
| `python -m rbp_eval.accept.transfer_calibration` | Transfer calibration report (also `bash scripts/cert/certify.sh --transfer`) |
| `nanobot-bio gate` | Code/layout gate: ruff + pytest + layout |

Full CLI inventory: `nanobot-bio --help` · [`app/cli/README.md`](app/cli/README.md).

## Environment

| Item | Notes |
|------|-------|
| Layout | `rhobind_agent_delivery/` **sibling** to this repo; override with `DELIVERY_ROOT` |
| Agent env | `.venv` via `./scripts/nbio.sh setup` (wraps `setup_all.sh`) |
| Science conda | delivery: `protein_embed` / `rna` / `rhobind` / `af3` |
| Paths | `nbio.sh` discovers `BIO_ROOT` / `AF3_BLACKWELL_ROOT` / conda on the host; AutoDL layouts are candidates only |
| Structure | Skill: AFDB `structure_fetch` first; AF3 `predict_structure` only on AFDB miss (sequence-only must call it) |
| LLM | `nanobot-bio onboard` → pick provider (no default); key in package `.env`, refs in `~/.nanobot/config.json` |
| Device | `RHOBIND_DEVICE=auto\|cuda\|cpu`; `chat` / `agent` also support `--device` |
| Memory | RhoBind / ESM prefer ample RAM and CUDA first; low cgroup memory limits risk OOM |
| Tools | Default `RBP_RAW_TOOLS=all`; set `whitelist` to narrow |

Env vars, Docker, and more detailed install paths: [INSTALL.md](INSTALL.md).

## Package map

Each package has English + Chinese README (`README.md` / `README.zh.md`): role, Linux usage under `$BIO_ROOT`, and links upstream/downstream.

| Path | Role | Docs |
|------|------|------|
| [`app/`](app/) | CLI + orchestration; [`cli/`](app/cli/), [`backends/delivery/`](app/backends/delivery/) | [EN](app/README.md) · [中文](app/README.zh.md) |
| [`nanobot/`](nanobot/) | Slim runtime + skill/tools SoT; [`agent/tools/rbp/`](nanobot/agent/tools/rbp/) | [EN](nanobot/README.md) · [中文](nanobot/README.zh.md) |
| [`rbp_eval/`](rbp_eval/) | Offline LOO / accept / evolve | [EN](rbp_eval/README.md) · [中文](rbp_eval/README.zh.md) |
| [`config/`](config/) | Defaults + evolved YAML | [EN](config/README.md) · [中文](config/README.zh.md) |
| [`scripts/`](scripts/) | Setup / CI / cert / Docker / data helpers | [EN](scripts/README.md) · [中文](scripts/README.zh.md) |
| [`tests/`](tests/) | Pytest contracts | [EN](tests/README.md) · [中文](tests/README.zh.md) |
| [`workspace/`](workspace/) | Skills sync + session/memory symlinks | [EN](workspace/README.md) · [中文](workspace/README.zh.md) |
| [`artifacts/`](artifacts/) | Canonical runtime outputs (gitignored data) | [EN](artifacts/README.md) · [中文](artifacts/README.zh.md) |

## Docs

| Doc | Contents |
|-----|----------|
| [HANDOFF.md](HANDOFF.md) · [HANDOFF.zh.md](HANDOFF.zh.md) | Collaborator hand-off (start here if new to the repo) |
| [INSTALL.md](INSTALL.md) · [INSTALL.zh.md](INSTALL.zh.md) | Setup, env vars, Docker, acceptance, CI |
| [ARCHITECTURE.md](ARCHITECTURE.md) · [ARCHITECTURE.zh.md](ARCHITECTURE.zh.md) | Layers, memory, bridge, eval/promote, release |
| [AGENTS.md](AGENTS.md) | Agent / CI must / must-not |
| [CHANGELOG.md](CHANGELOG.md) | Version history |
| [`nanobot/skills/rbp-agent/SKILL.md`](nanobot/skills/rbp-agent/SKILL.md) | Stage discipline + tool contracts (product SoT) |
