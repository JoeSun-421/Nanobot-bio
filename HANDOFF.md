# Nanobot-bio — collaborator hand-off

**Audience.** Engineers picking up this repo (or the sibling science bundle) who need a correct mental model in minutes.

**Pair docs.** Delivery science toolkit: [`../rhobind_agent_delivery/agent/HANDOFF.md`](../rhobind_agent_delivery/agent/HANDOFF.md). Product constraints: [`AGENTS.md`](AGENTS.md). Layers: [`ARCHITECTURE.md`](ARCHITECTURE.md). Setup: [`INSTALL.md`](INSTALL.md).

**Version.** Package `nanobot-bio` **0.5.1** (`pyproject.toml`). CLI entry points: `nanobot-bio` and `rbp-agent` → `app.cli:main`.

---

## What this repo is

A **command-line RNA–RBP binding agent**: resolve an RBP + RNA → typed JSON verdict (`label`, `confidence`, `p_hat`, `explanation`, `supporting_rbps`).

| Mode | When | What happens |
|------|------|--------------|
| **Own-head** | Target RBP is in-panel with a RhoBind head | Score that head; stop |
| **Transfer** | Out-of-panel / unseen | Multi-modal retrieve donors → `predict_interaction` on donors → `similarity_weighted_vote` |

Stages **0→1→2→3** and tool discipline live in [`nanobot/skills/rbp-agent/SKILL.md`](nanobot/skills/rbp-agent/SKILL.md). The LLM **never** invents `p_hat` / motifs / annotations.

---

## Layout on disk (this host / portable)

```text
$BIO_ROOT/                          # e.g. ~/bio_agent or /workspace/.../bio_agent
  Nanobot-bio/                      # THIS repo (GitHub folder name; package = nanobot-bio)
  rhobind_agent_delivery/           # science tools + DB + release (read-only from agent)
  rhobind_testdata_v2/              # optional LOO expand data
```

```bash
export BIO_ROOT="${BIO_ROOT:-$HOME/bio_agent}"
cd "${NANOBOT_BIO_ROOT:-$BIO_ROOT/Nanobot-bio}"
source scripts/nbio.sh              # or: ./scripts/nbio.sh start
```

- Checkout folder is often **`Nanobot-bio`** (capital N). Lowercase `nanobot-bio` also works if that is your clone path.
- Prefer `NANOBOT_BIO_ROOT` or `cd` into the tree that contains `scripts/nbio.sh` — do not hardcode trial-machine absolute paths.
- **Never edit** `rhobind_agent_delivery/` from this agent; call science only via `app/backends/delivery`.

---

## 60-second start

```bash
./scripts/nbio.sh setup             # once: .venv + delivery conda envs
nanobot-bio onboard                 # LLM provider + key → .env (no default provider)
./scripts/nbio.sh start             # discover paths → heal AF3/.env → chat
nanobot-bio doctor                  # capability matrix
nanobot-bio agent --example pos     # golden one-shot (no free-form RNA needed)
```

Daily activate without chat: `source scripts/nbio.sh`.

---

## Layers (who owns what)

```text
CLI (app/cli)  →  RBPAgent (app/agent.py)
                    →  nanobot/  (loop · skill · tools SoT)
                         →  app.backends.delivery  (read-only bridge)
                              →  rhobind_agent_delivery/
Offline eval / evolve  →  rbp_eval/   (not on the chat hot path)
```

| Tree | Role |
|------|------|
| `app/` | Product shell: CLI, verdict unwrap, onboard, capability matrix, delivery client |
| `nanobot/` | Slim in-repo Nanobot **SoT == runtime**; `import nanobot` must resolve here. **Do not** `pip install nanobot-ai`. |
| `nanobot/skills/rbp-agent/` | Skill SoT; sync to workspace with `python -m app.sync_overlay` |
| `nanobot/agent/tools/rbp/` | Product toolkit classes |
| `rbp_eval/` | LOO / accept / evolve / scoring (physical path = import path) |
| `config/` | `defaults.yaml` + evolved candidates |
| `scripts/nbio.sh` | Portable entry: setup / start / status / doctor / chat |
| `workspace/` | Runtime skill overlay + symlinks → `artifacts/` |
| `artifacts/` | Canonical sessions / memory / outputs (data gitignored) |

---

## Hard rules (from AGENTS.md)

**MUST NOT**

- Edit delivery; invent `p_hat` with the LLM; call `predict_interaction` on an unseen target without proxy donors.
- Treat AF3/structure miss as similarity `0`; promote evolved config without gate + nested-split.
- Add a third tools tree; install PyPI `nanobot-ai`; import science torch into the nanobot process.
- Reuse prior session / transcript tool results as authoritative scores to skip Stage 0–3.

**MUST**

- Enter via `nanobot-bio` / `rbp-agent` / `python -m app`.
- Stage 0→1→2→3; own-head fast path when in-panel; \(N_{\mathrm{cand}}\le5\); drop fused similarity \(<0.30\).
- Transfer `p_hat` authority = delivery `similarity_weighted_vote` (not LLM max/mean).
- After skill/tool edits: `python -m app.sync_overlay` then `pytest tests/test_proposal_compliance.py tests/test_package_layout.py`.

---

## Docs that ship vs local-only

| Shipped (in git) | Local-only (`docs/` gitignored) |
|------------------|----------------------------------|
| README, INSTALL, ARCHITECTURE, AGENTS, CHANGELOG, HANDOFF | Product guides formerly under `docs/product/*`, `docs/guides/*` |
| Package `README.md` / `README.zh.md` | Feishu / proposal scratch |
| `nanobot/skills/rbp-agent/SKILL.md` | |

If a README still mentions `docs/…`, treat it as obsolete; use SKILL / ARCHITECTURE / package READMEs instead.

---

## Docker notes

Services in `docker-compose.yml`: **`app`**, **`app-full`**, **`doctor`** (there is no `chat` service name).

```bash
docker compose up app                          # agent profile
docker compose --profile full up app-full      # science profile
docker compose run --rm doctor
```

Known divergence: some Docker build paths historically assumed a lowercase `nanobot-bio/` sibling and/or cloning upstream Nanobot. Prefer host `./scripts/nbio.sh` + in-repo `nanobot/` SoT unless you have verified the image. See [`INSTALL.md`](INSTALL.md) Path B and [`scripts/docker/README.md`](scripts/docker/README.md).

---

## Useful CLI map

| Goal | Command |
|------|---------|
| Chat / one-shot | `nanobot-bio chat` · `nanobot-bio agent` |
| Caps / paths | `nanobot-bio doctor [--verbose]` |
| Own-head accept | `nanobot-bio accept-golden` |
| LLM accept | `nanobot-bio accept-llm` |
| LOO / evolve | `nanobot-bio run-eval` · `heavy-loo` · `evolve` · `promote-evolved` |
| Engineering gate | `nanobot-bio gate` · `bash scripts/ci/ci_gate.sh` |
| Cert / transfer | `bash scripts/cert/certify.sh` · `python -m rbp_eval.accept.transfer_calibration` |

Full list: `nanobot-bio --help`.

---

## Where to read next

1. This file + [`AGENTS.md`](AGENTS.md)
2. [`INSTALL.md`](INSTALL.md) — env vars, conda, AF3, Docker
3. [`ARCHITECTURE.md`](ARCHITECTURE.md) — memory/sessions, bridge, release
4. [`nanobot/skills/rbp-agent/SKILL.md`](nanobot/skills/rbp-agent/SKILL.md) — stage rules
5. Delivery hand-off: `rhobind_agent_delivery/agent/HANDOFF.md` + `SETUP.md` + `tools/registry.json`

中文版：[HANDOFF.zh.md](HANDOFF.zh.md).
