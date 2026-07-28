# Slim vendor notes (maintainer)

In-repo `nanobot/` is the Agent Controller runtime (Proposal §6.2: SoT == runtime).
Snapshot origin: sibling `/root/autodl-tmp/bio_agent/nanobot` (metadata 0.1.0) at migrate time
(sibling may already be removed).

**This file does not authorize deletion.** Need an explicit chat approval before
removing remaining hard-wired paths (cron loop, MessageTool/MyTool, PA templates).

**Single SoT for inventory / phases / keep-vs-delete:** [`ARCHITECTURE.md`](ARCHITECTURE.md) §6.

Last reviewed: 2026-07-26 (merged into ARCHITECTURE.md).

---

## What we keep under `nanobot/`

| Area | Notes |
|------|--------|
| Core | `__init__.py`, `nanobot.py`, `config_base.py`, `agent/` (loop/runner/…), `providers/`, `config/`, `sdk/`, `session/`, `bus/`, `command/`, `security/`, `utils/`, `templates/` |
| RBP SoT | `skills/rbp-agent/` only, `agent/tools/rbp/` |
| Tool packages | `agent/tools/core/` (base/loader/registry/schema/…), `agent/tools/rbp/`, `agent/tools/legacy/` (PA stubs + MessageTool/MyTool/cron tool) |
| Quarantine | `nanobot/legacy/apps/` (CLI-Anything stub); unused templates under `templates/legacy/` |
| Still wired | `cron/` package, `legacy.message` / `legacy.self` / `legacy.file_state` (loop dependencies) |

**ToolLoader:** `NANOBOT_TOOL_ALLOW=rbp` by default. Plugins off unless `NANOBOT_TOOL_PLUGINS=1`.

**rbp_eval layout:** `scoring/`, `loo/`, `evolve/`, `accept/`, `runtime/`, `rna/`, `plans/` — import real submodules (no top-level facade).

---

## Already stripped / stubbed

- Product surfaces: `channels/`, `web/`, `webui/`, `cli/`, `audio/`, `bridge/`, `gateway/`, `pairing/`, `api/`, nested package metadata
- PA skills: `weather`, `tmux`, `github`, … and (2026-07-25) **`long-goal` / `memory` / `my`**
- Heavy PA tools live under `agent/tools/legacy/` as stubs: `shell`, `web`, `filesystem`, …
- Shared configs: `agent/tools/core/tool_configs.py`
- `/tmp/nanobot-bio-*` layout backups removed (2026-07-25)

---

## Proposal checklist (migrate gates)

- [x] §3 layers: Controller=`Nanobot.run` · Toolkit=rbp tools · Predictor=delivery bridge
- [x] §6.1 providers + Tool subclasses + `skills/rbp-agent` + session + hooks
- [x] §6.2 in-repo `nanobot/skills/rbp-agent` + `nanobot/agent/tools/rbp`
- [x] §6.3 `from nanobot import Nanobot` → `from_config` → `run`
- [x] §8 lightweight: no channels/WebUI; default tools = RBP
- [x] delivery untouched; `p_hat` only from predict tools

---

## Residual (do not blind-delete)

Still imported by schema/loop/memory — need deeper refactor first:

`message` / `self` / `file_state` / `cron` (+ `nanobot/cron/`) / `session/webui_turns.py` /
PA bootstrap templates (`SOUL.md`, `USER.md`, dream-related utils).

---

## Remaining delete candidates (new approval)

1. Deeper loop decoupling → drop MessageTool/MyTool/cron when RBP chat path no longer needs them
2. Slim `templates/` PA prose (`AGENTS.md` HEARTBEAT sections) once gateway is gone
3. Optional: delete any recreated fat sibling under `bio_agent/nanobot`

## Must keep (product)

`nanobot/` slim + rbp SoT · `app/` · `config/` · `rbp_eval/` · `workspace/` · `tests/` ·
`scripts/` · `artifacts/` tree · local `docs/` · root `README` / `INSTALL` / `AGENTS` /
`CHANGELOG` / `RELEASE`
