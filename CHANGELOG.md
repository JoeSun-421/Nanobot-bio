# Changelog

Changes to the RBP Agent application (`nanobot-bio`). Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Changed — maturity packaging & honesty

- **Capability matrix SoT:** `app/core/capability_matrix.py` drives doctor/layout honesty (AF3 real-smoke state, RNA peak-homology weights `0` without `PEAKS_DB`, `feature_attribution_source=unavailable`).
- **Tool / eval layout:** `nanobot.agent.tools.{core,rbp,legacy}` and `rbp_eval.{scoring,loo,evolve,accept,runtime,rna,plans}` — physical path = import path; ToolLoader default allowlist `rbp` only.
- **Vote / fuse guards:** delivery `similarity_weighted_vote` is the authoritative transfer score; deterministic fuse values cannot be replaced by LLM numbers; promote hard-fails nonzero RNA weight without a peaks DB; no retrieval-only synthetic promote path.
- **Evolve loop:** real `rbp_eval.evolve.run_eval` + modality ablation; smoke script `scripts/smoke_evolve_loop.sh`.
- **Chat UX:** tool-wait spinner shows active tool count / elapsed time.
- **Docs:** session/memory, slim inventory, keep-vs-delete, and cleanup phases consolidated in [`ARCHITECTURE.md`](ARCHITECTURE.md) §2 / §6 (not a deletion authorization).

### Changed — delivery-aligned transfer scoring

- **Deterministic Stage-1 fusion:** `commit_proxy_candidates` may select/explain candidates, but authoritative `s_i` and modality breakdowns are copied from `fuse_similarity_views`. Stage contract: fuse → commit → abstain → predict.
- **Default aggregation `weighted`:** transfer `p_hat = Σ(s_i·πtr_i·q_i·p_i) / Σ(s_i·πtr_i·q_i)` is computed by delivery `similarity_weighted_vote`. The proposal-only donor-confidence factor is not implemented because delivery prediction rows contain only `alias, prob, head_index, cohort`.
- **AF3 fallback default on:** `axes.use_af3=true`, `structure_policy.use_af3_fallback=true` (probe failure → caveat, ≠ sim 0).
- **Conflict recorded:** `docs/proposal.md` remains untouched; agent runtime and documentation follow delivery where the aggregation definitions differ.

## [0.5.1] — 2026-07-24

### Fixed

- **CI matrix vs lock mismatch:** `requirements.lock` pins `numpy==2.5.1` (needs Python ≥3.12) but the matrix still tested `3.10` → install failed on the 3.10 slot. Matrix changed to `["3.12", "3.13"]` (matches the lock and local dev env).
- **`science` job queued indefinitely with no runner:** the `science` (accept-golden) job ran on every push to main with `runs-on: [self-hosted, linux, science]`, but no runner is registered → it stayed queued forever and made every CI run look stuck. Gated `science` to tag/`workflow_dispatch` only (same as `eval`), so regular push/PR CI stays green via the `test` job alone.
- **`accept-llm` short-circuited on cached session:** `ephemeral=True` did not discard pre-existing session memory, so the LLM reused a prior verdict ("unchanged from previous run") instead of calling tools → touchpoints failed. `accept_llm` now clears the `accept-llm:<case>` session files before each run, so the LLM exercises the full tool chain fresh. Verified: `accept-llm ok=True` with all four touchpoints hit (incl. the F3-required `get_func_annotation` + `literature_search`).

### Changed

- **INSTALL.md §4.1:** documents the three CI jobs, their runners/triggers, and how to register a `self-hosted, linux, science` runner + `DELIVERY_BUNDLE_PATH` secret to enable the `science`/`eval` jobs.

## [0.5.0] — 2026-07-23

### Added — functional gaps (delivery contract alignment)

- **A1 structure-file input modality:** `resolve_rbp` accepts a local PDB/CIF `structure_file` path; short-circuits delivery resolve and hands `pdb_path` straight to `struct_similarity`.
- **A2 phmmer remote-homology axis:** optional `phmmer_similarity` curated tool (opt-in via `RBP_PHMMER=1`); documented in SKILL as a distant-homology fallback, default off.
- **A3 concurrency_safe:** curated Stage-1 retrieve tools declare `concurrency_safe` so the runner can truly parallelize the four-view retrieve.
- **A4 Stage-3 no-LLM-explanation ablation:** `evaluation_plan --no-llm-explanation` + `--labels-llm` produce a delta-metrics block (AUROC/AUPRC/ECE) for the proposal §9(iii) ablation.
- **A5 ECE in loo_eval:** `loo_eval --labels` emits an instance-level metrics block (AUROC/AUPRC/ECE).
- **A6 literature TTL cache:** `literature_search` memoizes results under `artifacts/cache/literature/<rbp>.json` with a 7-day TTL (cross-session, AF3-cache pattern).
- **A7 latency_ms consistency:** all `execute` paths use `timed_call`; cache hits report real wall-time `latency_ms` (no more `0.0` on hits).

### Changed — optimizations (faithfulness)

- **B1 AF3 confidence fields on demand:** `predict_structure` filters heavy AF3 payload fields; `region_plddt`/`mean_plddt`/`iptm` surface into caveats when low (<50); SKILL directs passing `regions=[[start,end]]` after `domain_architecture`.
- **B2 stage scheduling prevention:** declarative `stage_contract.py` (STAGE_RETRIEVE / REQUIRES / OWN_HEAD_STOP_BLOCKED) drives `turn_guards` data-driven prerequisite checks instead of ad-hoc guards.
- **B3 caveats evidence-completeness audit:** `normalize_verdict_with_turn_state` merges turn-state evidence flags into `caveats`; delivery-backed `structure_fetch`/`domain_architecture`/`literature` soft-fails now surface as `structure_axis_unavailable` / `domain_empty` / `literature_unavailable` flags.
- **B4 unified metrics:** shared `rbp_eval/metrics.py::metrics_from_pairs` (AUROC/AUPRC/ECE) consumed by both `evaluation_plan` and `loo_eval`.
- **B5 CI science job:** `.github/workflows/ci.yml` `eval` job (tag-triggered, self-hosted `science` runner) runs the Stage-3 ablation + ECE and uploads `eval-reports`.

### Changed — simplifications

- **C1 trimmed 6 redirect stubs:** removed `web_search`/`web_fetch`/`read_file`/`grep`/`list_dir`/`find_files` stubs from `ALL_RBP_TOOL_CLASSES`.
- **C2 raw-delivery whitelist default:** `include_raw_delivery` default narrowed from `all` (37) to `whitelist`; opt into `all` via `RBP_RAW_TOOLS=all`.
- **C3 acceptance-path unification:** `accept-golden` is the authoritative acceptance path; delivery `run_example.sh` left untouched (read-only) and documented as delivery-native smoke only.
- **C5 app/dev ↔ rbp_eval boundary:** scientific `accept-*` (`accept_llm`, `own_head`/`accept-golden`) consolidated into `rbp_eval/`; `app/dev` retains engineering gates only.
- **C6 evolved-config promote link:** tracked `config/evolved.candidate.yaml.example` seed + `promote-evolved --seed` bootstrap; flow documented in `RELEASE.md §9`.

### Added — v0.5.0 review fixes (RBM20 trace)

- **F1 delivery-backed soft-fail surfacing:** `structure_fetch` error → `structure_axis_unavailable`; `domain_architecture` `domain_source:"none"` → `domain_empty` evidence flags reach verdict caveats.
- **F2 head-coverage caveat:** `predict_interaction` multi-head with null-prob donors surfaces `low_head_coverage`; verdict schema forces low confidence and lists it as a caveat (abstain gate no longer passes on embedding similarity alone when heads are missing).
- **F3 function/annotation axis hard rule:** SKILL marks `get_func_annotation` + `literature_search` required on the unseen path; motifs/domain/family annotations must come from tools, never model memory.
- **F4 AF3-fallback/caveat:** SKILL directs `predict_structure` on `structure_fetch` error when `use_af3_fallback` is on, else surface `structure_axis_unavailable` caveat.
- **F5 domain network re-call doc:** SKILL documents the `domain_architecture` `network=true` slow InterProScan path and the default (accept empty axis + `domain_empty` caveat).

### Changed

- **Layout:** physical SoT at repo-root `nanobot/` (removed `plugin/`); deleted orphan `app/artifacts`, `app/workspace`, `app/acceptance`, and unwired dead modules.
- **Guards:** transfer path requires fuse → confidence_abstain → predict (`turn_guards` + DeliveryBackedTool).
- **CLI:** `accept-golden`, `accept-llm`, `gap-closure` top-level; CI ruff checks `app rbp_eval tests`.
- Defaults: structure/rna_blastn/literature on; `use_af3` false (AFDB preferred).

### Changed (earlier)

- **Layout (safer pass):** repo-root `nanobot/` → SoT path (symlink to `plugin/nanobot`); `app/sot` prefers `nanobot/`; acceptance logic lives in `app/dev/` with `app/acceptance` as shim; root `AGENTS.md` restored.
- Defaults: enable `structure` / `rna_blastn` / `literature` axes (`use_af3` still false); `setup_all.sh` jax probe accepts ≥0.4.

## [0.4.0] — 2026-07-23

### Added

- Final delivery alignment: `include_raw_delivery=all`; `check_near_known`; dual-axis `hits_emb`/`hits_seq`; AF3 `regions`; `function_category` in annotation; abstain-before-predict guards.
- App-side `mmseqs_wrap.sh` for `rna_blastn` / `protein_seq_similarity` (injects `--threads` without editing delivery).
- Eval helpers: `rbp_eval/{accept_llm,gap_closure,heavy_loo,rna_fm_gate}.py`; worklog under `docs/worklog/`.

### Changed

- **Layout:** product packages are `app/` + `plugin/nanobot/` SoT only; removed dual trees `rbp_agent/` and in-repo `nanobot/` overlay.
- Product README (EN/ZH): final full-open toolkit; fuse → abstain → predict; honest calibration (no fake online `score_calibration`).
- SKILL / Stage tool sets: `confidence_abstain` post-fuse / pre-predict (BUILD_SPEC).

### Fixed

- mmseqs all-core segfault path (`World Size: … dbSize: …`) via App wrap + `DeliveryToolClient` wiring.

## [0.3.0] — 2026-07-21

### Added

- **Layout:** `rbp_app` → `app/`; SoT → `plugin/nanobot/`; runtime data → `~/.nanobot-bio/{workspace,artifacts}`; added `AGENTS.md` / `CONTRIBUTING.md`.
- Proposal-anchored change gates (`docs/工程指南.zh.md` §9 / §9.10) and Cursor rule
- `config/defaults.yaml` `models:` metadata; doctor writes `model_capability_matrix.json`
- Agent-local `rna_similarity` (mock by default); ESM disk cache under `artifacts/cache/esm/`
- `evolve-eval`, evaluation-plan strata, Stage-3 checklist enforcement in `normalize_verdict`
- Product README rewrite (EN/ZH); proposal PDF/DOCX kept external (not required in-repo)

### Changed

- **Product CLI surface:** user commands are `doctor|onboard|agent|chat`; maintainer tools under `rbp-agent dev …`. Removed `mvp` acceptance entry.
- **App package renamed** `rbp_agent` → **`app`** (application shell only). `workspace/` and `artifacts/` live under `app/` only (repo-root compat symlinks removed).
- Single plugin SoT at repo-root `nanobot/`; removed `_proposal_sot` packaging tree
- Workspace skill sync prefers symlink to SoT; `fusion.py` shim removed (`fuse_hits` only)
- Default `rna_*` fusion weights set to 0 until a real RNA-FM checkpoint is configured
- `Nanobot.run` eval/MVP path supports `ephemeral=True`; `AgentResult` surfaces `tools_used` / `usage`

### Fixed

- Layout/compliance tests for SoT paths and proposal document presence
- Stale `__editable__.nanobot_bio-*.pth` cleanup pattern in setup
## [0.2.0] — 2026-07-20

### Added

- Layer documentation: App / SoT / Eval / Runtime / Science; installation entry `setup_all.sh`
- Chat UX; multi-vendor `onboard`; light LOO / eval-plan / evolve / evolve-eval
- Engineering Phase 1: `requirements.lock`, ruff/pytest-cov, `rbp-agent gate`, CI, doctor JSON, secret scan
- Offline evolution workflow: candidate → gate → promote; TraceEvent schema; axes hard-gate

### Changed

- Plugin overlay under `nanobot/`; full framework only at `$NANOBOT_SRC`
- `scripts/` limited to setup and gate helpers (acceptance under `app.dev`)
- Documentation consolidated into `docs/工程指南.zh.md`

### Fixed

- Foldseek / seq_similarity alias-only / disabled `web_search` error handling

## [0.1.0] — 2026-07-18

### Added

- Initial application: `rbp-agent` CLI, delivery bridge, RBP tools, skills via `Nanobot.run`

[0.4.0]: https://github.com/JoeSun-421/rbp-nanobot-bio/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/JoeSun-421/rbp-nanobot-bio/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/JoeSun-421/rbp-nanobot-bio/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/JoeSun-421/rbp-nanobot-bio/releases/tag/v0.1.0
