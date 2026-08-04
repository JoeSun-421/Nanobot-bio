# Architecture

<p><b>English</b> · <a href="ARCHITECTURE.zh.md">中文</a></p>

Engineering map of `nanobot-bio`: layers, workspace stores, eval/promote,
slim-vendor policy, and release checklist. Setup: [`INSTALL.md`](INSTALL.md) /
[`INSTALL.zh.md`](INSTALL.zh.md). Agent gates: [`AGENTS.md`](AGENTS.md).
History: [`CHANGELOG.md`](CHANGELOG.md). Package map:
[`README.md`](README.md) / [`README.zh.md`](README.zh.md).
Local proposal detail may stay under git-ignored `docs/`.

## Portable layout (Linux)

```bash
export BIO_ROOT="${BIO_ROOT:-$HOME/bio_agent}"
cd "$BIO_ROOT/nanobot-bio"
source scripts/nbio.sh
# DELIVERY_ROOT=$BIO_ROOT/rhobind_agent_delivery
```

---

## 1. Layers

| Layer | Path | Role |
|-------|------|------|
| Agent CLI + core | `app/` | Argparse CLI (`rbp-agent` / `nanobot-bio`), verdict schema, runtime config, onboarding, delivery bridge. Never computes `p_hat` itself. |
| Runtime + skill (SoT) | `nanobot/` | Slim in-repo Nanobot **plus** `rbp-agent` skill and RBP tools. SoT == runtime — `import nanobot` must resolve here. |
| Offline eval + evolve | `rbp_eval/` | LOO, fusion, metrics, accept, self-evolution under real subpackages. |
| Science bundle (read-only) | `$BIO_ROOT/rhobind_agent_delivery/` | Delivery tools + data. Call via App bridge; do not edit. |

`NANOBOT_SRC` defaults to in-repo `nanobot/`. There is **no** sibling-clone runtime;
`rbp-agent layout` asserts PA surfaces (channels/webui/cli/…) are stripped.

| Area | Path |
|------|------|
| Loop / memory / context | `nanobot/agent/` |
| Tool runtime | `nanobot/agent/tools/core/` |
| Product toolkit | `nanobot/agent/tools/rbp/` |
| Legacy / PA stubs | `nanobot/agent/tools/legacy/` |
| Sessions | `nanobot/session/` |
| Skill SoT | `nanobot/skills/rbp-agent/` |

**ToolLoader:** `NANOBOT_TOOL_ALLOW=rbp` by default; plugins off unless
`NANOBOT_TOOL_PLUGINS=1`. Chat also unregisters noisy PA tools in `app/agent.py`.

**Eval packages:** `rbp_eval/{scoring,loo,evolve,accept,runtime,rna,plans}/` —
physical path = import path (no top-level facade).

---

## 2. Workspace: sessions vs long-term memory

**Canonical store is `artifacts/`** (`workspace/sessions` and `workspace/memory`
are symlinks only). Detail: [`docs/guides/MEMORY_AND_SESSIONS.md`](docs/guides/MEMORY_AND_SESSIONS.md) /
[`MEMORY_AND_SESSIONS.zh.md`](docs/guides/MEMORY_AND_SESSIONS.zh.md).

| Store | Path | Purpose |
|-------|------|---------|
| Session transcript | `artifacts/sessions/` | Per-chat turns by local start date. |
| PA long-term memory | `artifacts/memory/` | `MEMORY.md`, Dream cursors; off in scientific_mode. |
| Domain memory | `artifacts/cache/proxy_map.json` | Retrieval shortcuts only; not PA memory; does not alter RhoBind scores. |
| Eval reports | `artifacts/reports/{json,md,csv}/` | Machine JSON, Markdown, CSV. |
| Skill link | `workspace/skills/rbp-agent/` | Must track in-repo SoT (`python -m app.sync_overlay`). |

`USER.md` / `MEMORY.md` are personal-assistant state and are excluded from the
scientific prompt. Recent-history injection is allowed only for the exact,
nonempty current session key. Automatic Dream, idle compaction, and
token-triggered Consolidator runs are disabled for the RBP agent.

For `accept-llm` / eval / `nanobot-bio chat|agent`, use `ephemeral=True` (product
default on `RBPAgent.run` / `run_streamed`). Editing `MEMORY.md` alone will not
reset chat reuse. In **scientific mode**, an ephemeral turn does **not** replay
prior session tool/verdict transcripts into the LLM context (avoids skipping
Stage 0–3); it also does not append messages or write memory. Non-scientific
ephemeral turns may still read the current session for context.

Implementation: `nanobot/session/manager.py`, `nanobot/agent/memory.py`.
Do not remove the `session` / `memory` stacks casually.

---

## 3. Prediction pipeline

Question: *does this RNA bind RBP X?* — X may have **no trained head**.

1. **Retrieve** catalogue neighbours (seq / struct / func) → donors.
2. **Predict** query RNA on each donor head → `prob`.
3. **Integrate** → calibrated, explainable verdict.

Two LLM checkpoints: Stage-1 (retrieval / donors) and Stage-3 (explanation).
The LLM never fabricates `p_hat`, motifs, or annotations.

Own-head: `p_hat = max_windows fθ(RNA, head_target)`.

Transfer: `p_hat = Σ (sᵢ · πtrᵢ · qᵢ · pᵢ) / Σ (sᵢ · πtrᵢ · qᵢ)` via delivery
`similarity_weighted_vote` (`sᵢ` from `rbp_eval/scoring/fuse_hits.py`; `pᵢ` from
`rhobind_predict`). Cross-metric min–max when ≥2 metrics; `tau_drop` filters weak
donors. RNA peak-homology fusion stays `0` unless the BLAST peaks database is
ready. Honesty SoT: `app/core/capability_matrix.py`.

---

## 4. Delivery bridge

`app/backends/delivery/client.py` → `DeliveryToolClient.call(name, payload)`:

- Light tools: in-process `run(payload)`.
- Heavy tools: `--json` subprocess in conda envs (`protein_embed` / `rna` /
  `rhobind` / `af3`), agent `.venv` scrubbed from child env.

`mapping.yaml` is the App orchestration manifest; `tool_mapping.py` validates it
against delivery `agent/tools/registry.json` and fails closed on stale bindings.
`apply_delivery_env()` resolves paths, AF3 interpreter, USalign→Foldseek
fallback, `OMP_NUM_THREADS`.

Where delivery and `docs/product/proposal.md` conflict on transfer aggregation, code
follows delivery. Prediction rows keep the delivery shape
(`alias`, `prob`, `head_index`, `cohort`); agent provenance is stored separately.

---

## 5. Evaluation, self-evolution, promote

Offline tuning pipeline (not autonomous discovery): attribute tools, retune
fusion/abstention/`tau_drop`, write a candidate policy, run ablations, update
proxy cache. Deployment is a separate, human-invoked `promote-evolved`.

| Piece | Notes |
|-------|--------|
| Light LOO | `rbp_eval/loo/loo_eval.py` (CSV via `resolve_loo_csvs()`); regression gate, not instance-level transfer calibration |
| Heavy LOO | `rbp_eval/loo/heavy_loo.py` |
| Evolve | `rbp_eval/evolve/` → `config/evolved.candidate.yaml` (gitignored) |
| Runtime knobs | `config/defaults.yaml` deep-merged with `config/evolved.yaml` when `evolved: true` |

**Promote evidence** (normal path):

1. Light LOO + evaluation-plan reports exist and pass.
2. Retained evolve decision: `n >= 10` and `delta_auprc > 0`.
3. `transfer_calibration.json` with real RhoBind scores, positive AUPRC delta,
   ≥10 scored cases, disjoint train/validation IDs, source hashes, objective
   metadata, exact candidate-policy hash, rollback paths.
4. RNA-axis hold: nonzero RNA fusion weight rejected unless delivery RNA/PEAKS
   is ready.

`--force` escapes report checks only; it does not bypass the RNA capability hold.

```bash
rbp-agent evolve                 # writes evolved.candidate.yaml
rbp-agent gate
rbp-agent promote-evolved        # candidate → evolved.yaml
# fresh clone: rbp-agent promote-evolved --seed
```

Tracked seed: `config/evolved.candidate.yaml.example`.

---

## 6. Slim vendor (plan only — not a delete authorization)

In-repo `nanobot/` is the Agent Controller runtime (proposal §6.2: SoT == runtime).
Chat approval required before each cleanup phase. Out of scope: delivery source
and proposal rewrite.

### Keep / residual

**Must keep:** `tools/core` hot path, `tools/rbp/**`, `skills/rbp-agent/**`,
agent loop/runner/context/memory, `session/{manager,keys,…}`, LLM `providers/`
(except unused transcription), `app/`, `rbp_eval/`, `workspace/`, `tests/`,
`config/`, `scripts/`, `artifacts/` tree.

**Still wired (decouple before delete):** `legacy/{message,self,file_state,…}`,
`cron/`, PA bootstrap templates (`SOUL.md`, `USER.md`, dream helpers),
`session/webui_turns.py`.

**Already stripped:** channels/web/webui/cli/audio/bridge/gateway/pairing/api;
PA skills; heavy PA tools stubbed under `agent/tools/legacy/`.

| Kind | Action |
|------|--------|
| Empty stubs (`long_task`, `spawn`, `search`, …) | Delete candidates after approval |
| Schema-hung stubs (`shell`, `web`, …) | Slim `ToolsConfig` first |
| Loop-wired leftovers | Keep until decoupling PR |
| Session / memory stores | Keep |

### Phases

| Phase | Work | Risk |
|-------|------|------|
| **A** | Delete zero-ref layer; grep clean | Low |
| **B** | Slim `ToolsConfig`; drop schema-only stubs | Medium |
| **C** | Decouple MessageTool / MyTool / cron / MCP from loop | High |
| **D** | Anti-regression tests (no channels/webui return) | Low |

**Phase A accept:**

```bash
python -c "from nanobot import Nanobot; from nanobot.agent.tools.rbp import register_all"
pytest tests/test_package_layout.py tests/test_skeleton_imports.py -q
pytest tests/ -q --ignore=tests/science
```

Never mix “delete zero-ref stubs” with “change loop message semantics” in one PR.
Unused stubs left in-tree are **not** a release blocker; restoring
channels/webui or widening `NANOBOT_TOOL_ALLOW` **is** a product decision.

| Variable | Default | Note |
|----------|---------|------|
| `NANOBOT_WORKSPACE` | `workspace/` | Sessions + memory (§2) |
| `NANOBOT_CONFIG` | `~/.nanobot/config.json` | Local only; `chmod 600` |
| `NANOBOT_TOOL_ALLOW` | `rbp` | Do not widen casually |
| `NANOBOT_TOOL_PLUGINS` | off | `1`/`true` enables entry-points |

---

## 7. Release checklist

Version SoT: `pyproject.toml` (semver). README badge and `nanobot-bio --version`
follow it. History: [`CHANGELOG.md`](CHANGELOG.md) (Keep a Changelog;
`[Unreleased]` → `[X.Y.Z] — date` at cut time).

```bash
git checkout main && git pull
# bump pyproject.toml + README badges; finalize CHANGELOG
rbp-agent gate
# optional: rbp-agent accept-golden
bash scripts/ci/check_secrets.sh
git add pyproject.toml README.md README.zh.md CHANGELOG.md
git commit -m "release: vX.Y.Z"
git tag -a vX.Y.Z -m "vX.Y.Z"
git push origin main && git push origin vX.Y.Z
```

GitHub Release: paste the `## [X.Y.Z]` CHANGELOG block; attach
`artifacts/reports/json/gate_report.json` (and accept-golden / LOO if present).
If the release depends on a new delivery snapshot, note the bundle id in
CHANGELOG and update [`INSTALL.md`](INSTALL.md) §3 when layout/env vars change.

Optional images after tag: `docker build -t …:X.Y.Z` (agent) /
`--build-arg PROFILE=full` (science). Compose install path: [`INSTALL.md`](INSTALL.md) §1B.
