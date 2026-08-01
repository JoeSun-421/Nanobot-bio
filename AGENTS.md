# Agent / CI constraints (nanobot-bio)

Committed short gate for agents and CI. Layout / memory / eval / slim-vendor /
release: [`ARCHITECTURE.md`](ARCHITECTURE.md). Setup: [`INSTALL.md`](INSTALL.md).
Local detail (git-ignored): `docs/工程指南.zh.md` §9. Chat agreements do **not**
override these rules.

## MUST NOT

- Edit `rhobind_agent_delivery/` — science only via App bridge.
- Call \(f_\theta\) / `predict_interaction` on an **unseen** target without proxy donors; invent `p_hat` / `prob` with the LLM; treat AF3/structure miss as similarity `0`.
- Change Table 3 defaults without eval evidence + `config/defaults.yaml` + `tests/test_proposal_compliance.py`.
- Online weight writes / auto-edit delivery registry; promote evolved config without gate + nested-split (`delta_auprc > 0` or HOLD).
- Add a third tools tree (edit `nanobot/` SoT only); give mock RNA-FM fusion weight; commit secrets / push `docs/`; import science torch into the nanobot process; add LangGraph/CrewAI/AutoGen as product deps.
- Treat legacy PA stubs as product features; widen `NANOBOT_TOOL_ALLOW` / enable `NANOBOT_TOOL_PLUGINS` / restore channels·webui without maintainer approval (ARCHITECTURE §6).
- Blind-delete loop-wired leftovers or the session/memory stores (ARCHITECTURE §2 / §6).
- Let the LLM or a diagnostic max/mean override delivery `similarity_weighted_vote`; promote on retrieval-only synthetic scores; claim capabilities the matrix marks unavailable.
- Reuse prior session / chat-transcript tool results or verdicts as authoritative scores to skip Stage 0–3; invent `p_hat` from history (“identical LOO case already run”).

## MUST

- Layers: Agent Controller (in-repo slim `nanobot/`) / Toolkit / Predictor + offline `rbp_eval/`.
- Product path: `Nanobot.from_config` → `run` / `run_streamed` (`nanobot-bio agent|chat`). Default `ephemeral=True` for chat/agent so each user query recomputes (tools re-called); scientific tool caches OK only on an executed tool path. Do not install `nanobot-ai`.
- Default tools = RBP only; physical path = import path (`tools.{core,rbp,legacy}`, `rbp_eval.*` subpackages).
- Stage 0→1→2→3 + two LLM checkpoints; Stage 0 own-head / near-known Fast Path; \(N_{\mathrm{cand}}\le5\); drop fused similarity \(<0.30\).
- Tool contract: JSON Schema, error envelope, `latency_ms`, retrieve tools `read_only=True`.
- Skill SoT: `nanobot/skills/rbp-agent/SKILL.md`. Model metadata in `config/defaults.yaml` → `models:`.

## After edits

```bash
pytest tests/test_proposal_compliance.py tests/test_package_layout.py
```
