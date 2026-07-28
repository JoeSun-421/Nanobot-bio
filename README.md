<div align="center">
  <img src="assets/nanobot_logo.png" alt="nanobot-bio" width="420">

  <h1>Nanobot-bio</h1>
  <p>RNA–RBP interaction prediction agent</p>

  <p>
    <a href="https://github.com/JoeSun-421/rbp-nanobot-bio/stargazers"><img src="https://img.shields.io/github/stars/JoeSun-421/rbp-nanobot-bio?style=flat" alt="Stars"></a>
    <a href="https://github.com/HKUDS/nanobot"><img src="https://img.shields.io/badge/Nanobot-HKUDS%2Fnanobot-111111?logo=github" alt="Nanobot"></a>
    <img src="https://img.shields.io/badge/python-%E2%89%A53.10-blue" alt="Python ≥3.10">
    <img src="https://img.shields.io/badge/version-0.5.1-green" alt="Version">
    <a href="https://github.com/JoeSun-421/rbp-nanobot-bio/actions/workflows/ci.yml"><img src="https://img.shields.io/github/actions/workflow/status/JoeSun-421/rbp-nanobot-bio/ci.yml?branch=main&label=CI" alt="CI"></a>
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


## Quick start

Place `rhobind_agent_delivery/` next to this repository under the same parent directory (currently not included in this repo):

```bash
cd nanobot-bio
bash scripts/setup_all.sh
source .venv/bin/activate

nanobot-bio onboard    # configure LLM and API key → ~/.nanobot/config.json
nanobot-bio doctor     # path / conda / science-stack self-check
nanobot-bio chat
```

Step-by-step install and path notes: [INSTALL.md](INSTALL.md).

One-shot prediction example:

```bash
nanobot-bio agent --message "Does PTBP1 bind this RNA? <RNA sequence>"
# or structured inputs:
nanobot-bio agent --query PTBP1 --rna-file path/to/rna.txt --device auto
```

## Common commands & features

| Command | Purpose |
|---------|---------|
| `nanobot-bio chat` | Multi-turn session; in-chat `/status`, `/help`, `/tools`, `/quit` |
| `nanobot-bio agent --message "..."` | One-shot prediction (also `--query` / `--rna-file` / `--example`) |
| `nanobot-bio doctor` | Delivery paths, science envs, `PEAKS_DB`, AF3, LLM config self-check |
| `nanobot-bio onboard` | Write LLM provider / API key / model |
| `nanobot-bio accept-golden` | Own-head golden acceptance (no LLM; `own-head` is its alias) |
| `nanobot-bio run-eval` | LOO ceiling comparison and modality ablation |
| `nanobot-bio heavy-loo` | Hide-own-head LOO: recovered AUPRC and instance-level metrics |
| `python -m rbp_eval.accept.transfer_calibration` | Transfer calibration report (also `bash scripts/certify.sh --transfer`) |
| `nanobot-bio gate` | Code/layout gate: ruff + pytest + layout |

## Environment

| Item | Notes |
|------|-------|
| Layout | `rhobind_agent_delivery/` **sibling** to this repo; override with `DELIVERY_ROOT` |
| Agent env | `nanobot-bio/.venv` (created by `setup_all.sh`) |
| Science conda | delivery: `protein_embed` / `rna` / `rhobind` / `af3` |
| LLM | `nanobot-bio onboard` → `~/.nanobot/config.json` (`NANOBOT_CONFIG` can change the path) |
| Device | `RHOBIND_DEVICE=auto\|cuda\|cpu`; `chat` / `agent` also support `--device` |
| Memory | RhoBind / ESM prefer ample RAM and CUDA first; low cgroup memory limits risk OOM |

Env vars, Docker, and more detailed install paths: [INSTALL.md](INSTALL.md).
