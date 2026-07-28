# Architecture

Engineering map of `nanobot-bio`: layers, workspace stores, slim-vendor policy,
and phased cleanup. Setup: [`INSTALL.md`](INSTALL.md). Agent gates:
[`AGENTS.md`](AGENTS.md). Release process: [`RELEASE.md`](RELEASE.md). Maintainer
vendor notes: [`VENDOR.md`](VENDOR.md). Local proposal / maturity detail stays
under git-ignored `docs/` (e.g. [`docs/maturity_matrix.md`](docs/maturity_matrix.md)).

**This file is the single home** for session/memory layout, leftover-module
inventory, keep-vs-delete guidance, and slim phases. Other root docs only link here.

---

## 1. Layers

| Layer | Path | Role |
|-------|------|------|
| Agent CLI + core | `app/` | Argparse CLI (`rbp-agent` / `nanobot-bio`), verdict schema, runtime config, onboarding, delivery bridge. Never computes `p_hat` itself. |
| Runtime + skill (SoT) | `nanobot/` | Slim in-repo Nanobot **plus** `rbp-agent` skill and RBP tools. SoT == runtime — `import nanobot` must resolve here. |
| Offline eval + evolve | `rbp_eval/` | LOO, fusion, metrics, accept, self-evolution under real subpackages. |
| Science bundle (read-only) | `../rhobind_agent_delivery/` | Delivery tools + data. Call via App bridge; do not edit (one flagged exception in §7). |

`NANOBOT_SRC` defaults to in-repo `nanobot/` in every entry point. There is **no**
sibling-clone runtime; `rbp-agent layout` asserts PA surfaces
(channels/webui/cli/…) are stripped.

### 1.1 In-repo `nanobot/` layout

| Area | Path | Role |
|------|------|------|
| Loop / memory / context | `nanobot/agent/` | Controller: `Nanobot.run`, compaction, Dream I/O |
| Tool runtime | `nanobot/agent/tools/core/` | `Tool` base, registry, `ToolLoader` |
| Product toolkit | `nanobot/agent/tools/rbp/` | RBP SoT (auto-discovered) |
| Legacy / PA | `nanobot/agent/tools/legacy/` | Loop leftovers + disabled stubs |
| Sessions | `nanobot/session/` | Conversation JSONL (`SessionManager`) |
| Skill SoT | `nanobot/skills/rbp-agent/` | Stage contract + SKILL |

**ToolLoader:** `NANOBOT_TOOL_ALLOW=rbp` by default; plugins off unless
`NANOBOT_TOOL_PLUGINS=1`. Chat also unregisters noisy PA tools in `app/agent.py`.

**Eval packages:** `rbp_eval/{scoring,loo,evolve,accept,runtime,rna,plans}/` —
physical path = import path (no top-level facade).

---

## 2. Workspace: sessions vs long-term memory

Default workspace: `nanobot-bio/workspace/` (`NANOBOT_WORKSPACE`). Distinct from
`~/.nanobot/workspace` unless you point the env there.

| Store | Path | Purpose |
|-------|------|---------|
| Session transcript | `workspace/sessions/<key>.jsonl` | Per-chat turns. Here usually `workspace/sessions` → `artifacts/sessions/`. |
| Long-term memory | `workspace/memory/` | `MEMORY.md`, append-only `history.jsonl`, Dream cursors; optional `SOUL.md` / `USER.md`. |
| Skill link | `workspace/skills/rbp-agent/` | Must track in-repo SoT (`python -m app.sync_overlay`). |

Do not confuse session JSONL (full trace) with `MEMORY.md` (consolidated facts).
For `accept-llm` / eval, use `ephemeral=True` or clear the matching session file —
editing `MEMORY.md` alone will not reset chat reuse.
An ephemeral turn may read the existing session as context, but does not append
messages, persist runtime checkpoints, compact, or write memory history.

Implementation: `nanobot/session/manager.py`, `nanobot/agent/memory.py`.
Slimming may remove `session/webui_turns.py`; never remove the whole `session` /
`memory` stacks casually.

---

## 3. Prediction pipeline (proposal §3–4)

Question: *does this RNA bind RBP X?* — X may have **no trained head**.

1. **Retrieve** catalogue neighbours (seq / struct / func) → donors.
2. **Predict** query RNA on each donor head → `prob`.
3. **Integrate** → calibrated, explainable verdict.

Two LLM checkpoints: Stage-1 (retrieval / donors) and Stage-3 (explanation).
The LLM never fabricates `p_hat`, motifs, or annotations.

In-panel: `resolve_rbp` → own-head `predict_interaction` → verdict.

### Aggregation

Exact own-head: `p_hat = max_windows fθ(RNA, head_target)`.

Transfer: `p_hat = Σ (sᵢ · πtrᵢ · qᵢ · pᵢ) / Σ (sᵢ · πtrᵢ · qᵢ)`.

- `sᵢ` — fused similarity (`rbp_eval/scoring/fuse_hits.py`)
- `pᵢ` — delivery `rhobind_predict`
- `πtrᵢ` — optional measured transfer prior from delivery
- `qᵢ` — optional delivery donor-head quality prior

Cross-metric min–max when ≥2 metrics; `tau_drop` filters weak donors.
Delivery `similarity_weighted_vote` is the authoritative transfer scorer. The
proposal-only per-donor confidence factor is intentionally not implemented:
delivery provides no such prediction field, so runtime code follows delivery.
RNA peak-homology fusion stays `0` unless the BLAST peaks database is ready; promote must not
use retrieval-only synthetic scores. Honesty SoT:
`app/core/capability_matrix.py` (doctor → `artifacts/reports/model_capability_matrix.json`).

---

## 4. Delivery bridge

`app/backends/delivery/client.py` → `DeliveryToolClient.call(name, payload)`:

- Light tools: in-process `run(payload)`.
- Heavy tools: `--json` subprocess in conda envs (`protein_embed` / `rna` /
  `rhobind` / `af3`), agent `.venv` scrubbed from child env.

`app/backends/delivery/mapping.yaml` is the App orchestration manifest for
agent wrapper names, script bindings, stages, retrieve roles, axis gates and
raw exposure. `tool_mapping.py` validates it against delivery
`agent/tools/registry.json` and fails closed on missing/stale tools or scripts.
`SCRIPT_MAP`, stage sets, retrieve prerequisites and axis gates are generated
from that validated layer rather than maintained as independent whitelists.

`apply_delivery_env()` resolves paths, AF3 interpreter, USalign→Foldseek
fallback, `OMP_NUM_THREADS`.

---

## 5. Evaluation & self-evolution

- **Light LOO** — `rbp_eval/loo/loo_eval.py` (CSV via `resolve_loo_csvs()`).
- **Heavy LOO** — `rbp_eval/loo/heavy_loo.py` (`rbp-agent heavy-loo`).
- **Science smoke** — `tests/test_science_gate.py` (`@pytest.mark.science`).
- **Evolve** — `rbp_eval/evolve/` (`run_eval` + orchestrator) → candidate →
  `rbp-agent gate` → `promote-evolved`.

Runtime knobs: `config/defaults.yaml` deep-merged with `config/evolved.yaml`
when `evolved: true`.

---

## 6. Slim vendor: leftovers, keep-vs-delete, phases

Status: **plan only** — this section does **not** authorize deletion. Chat
approval required before each phase. Scope: in-repo `nanobot/` (+ schema/tests/
`VENDOR.md`). Out of scope: delivery source and proposal rewrite.

### 6.1 Keeping unused files — consequences

| If you keep zero-ref / stub files | Effect |
|-----------------------------------|--------|
| Runtime / `p_hat` / evolve | **None** (Loader does not load them) |
| Engineering | Noise; easy to mistake for unfinished product (e.g. `webui_turns` once mis-labeled “still wired”) |
| Risk | Someone widens `NANOBOT_TOOL_ALLOW` or enables plugins and resurfaces PA tools |

| Kind | Examples | Useful for future RBP work? |
|------|----------|-----------------------------|
| Empty stubs | `long_task`, `spawn`, `search` | **No** — rewrite if needed; do not “revive” |
| Unwired large modules | `exec_session`, `transcription`, `webui_turns`, `bound_runner` | Only if restoring full PA/WebUI/voice; otherwise git history is enough |
| Schema-hung stubs | `shell`, `web`, `cli_apps`, `image_generation` | Not for RBP agent; block schema slim first |
| Loop-wired | `message`, `self`, `file_state`, Dream fs helpers | **Keep** until a decoupling PR |
| Session / memory stores | `session/manager`, `workspace/memory` | **Keep** — product persistence |

Focus on RNA–RBP: layer-A leftovers are noise. Unsure → leave them; cost is
repo bulk, not science progress.

### 6.2 Inventory (baseline 2026-07-26)

~136 `.py` under `nanobot/`. Not all are hot-path.

**Layer A — zero external refs (safe delete candidates)**

`legacy/{long_task,search,spawn}.py`, `core/{exec_session,sandbox}.py`,
`cron/{bound_runner,session_delivery,webui_metadata}.py`, `session/webui_turns.py`,
`providers/transcription.py`, `utils/{artifacts,evaluator,logging_bridge,media_decode}.py`,
empty `templates/**/__init__.py` package markers (templates load via
`pkg_files("nanobot")/"templates"`).

**Layer B — schema lazy-default only**

`legacy/{web,shell,cli_apps,image_generation}.py` via `config/schema.py`
`ToolsConfig`. Remove schema fields / move dataclasses before deleting modules.

**Layer C — loop/memory hard deps (decouple first)**

`legacy/{message,self,file_state,filesystem,apply_patch,mcp,cron}.py`,
`cron/service.py`, PA bootstrap `SOUL.md` / `USER.md` / dream templates.

**Must keep:** `tools/core` hot path, `tools/rbp/**`, `skills/rbp-agent/**`,
`agent/{loop,runner,context,memory,…}`, `session/{manager,keys,goal_state,turn_continuation}`,
LLM `providers/` (except unused transcription), `app/`, `rbp_eval/`, `workspace/`,
`tests/`, `config/`.

### 6.3 Phases

| Phase | Work | Risk |
|-------|------|------|
| **A** | Delete layer A; fix `VENDOR.md`; grep clean | Low |
| **B** | Slim `ToolsConfig`; drop layer B stubs; sync `app/agent.py` unregister list | Medium |
| **C** | Decouple MessageTool / MyTool / cron / MCP from loop (separate PRs); keep Dream fs until redesigned | High |
| **D** | Anti-regression tests (no channels/webui return); docs/`VENDOR` final | Low |

**Phase A accept:**

```bash
python -c "from nanobot import Nanobot; from nanobot.agent.tools.rbp import register_all"
pytest tests/test_package_layout.py tests/test_skeleton_imports.py -q
pytest tests/ -q --ignore=tests/science
```

**Phase C accept:** one real chat (catalogue → predict → optional fuse) writing
`artifacts/sessions/`; memory history still appends if Dream kept;
`test_chat_ux` + layout/isolation green.

**PR slicing:** never mix “delete zero-ref stubs” with “change loop message
semantics” in one PR. Suggested: PR-A → PR-B → PR-C1 (message/self) → PR-C2
(cron/mcp) → PR-D.

**Gates each phase:** no remaining imports of deleted modules; layout tests;
doctor/matrix still runs; no secrets committed; commit only when user asks.

### 6.4 Execution checklist (after chat approval)

- [ ] Approve + land Phase A
- [ ] Approve + land Phase B
- [ ] Approve Phase C scope (C1/C2) + land
- [ ] Phase D guards + `VENDOR.md` date
- [ ] Release tag: if a tag deletes residue, call it out in `CHANGELOG`; unused
      stubs left in-tree are **not** a release blocker; restoring
      channels/webui/gateway or widening the tool allowlist **is** a product
      decision

### 6.5 Related env / install notes

| Variable | Default | Note |
|----------|---------|------|
| `NANOBOT_WORKSPACE` | `workspace/` | Sessions + memory (§2) |
| `NANOBOT_CONFIG` | `~/.nanobot/config.json` | Local only; `chmod 600`; rotate keys after paste |
| `NANOBOT_TOOL_ALLOW` | `rbp` | Do not widen casually |
| `NANOBOT_TOOL_PLUGINS` | off | `1`/`true` enables entry-points |

---

## 7. Delivery alignment ledger

Delivery and `docs/proposal.md` are immutable inputs. Where they conflict on
transfer aggregation, code follows delivery `similarity_weighted_vote`; prediction
rows remain the delivery shape (`alias`, `prob`, `head_index`, `cohort`) and all
agent provenance is stored separately.
