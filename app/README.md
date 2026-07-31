# app/

Product shell: CLI, `RBPAgent` assembly, delivery bridge, and runtime config. Never computes `p_hat` itself.

[English] · [中文](README.zh.md)

## Features

- Expose stable console commands `nanobot-bio` / `rbp-agent` (`python -m app`) for chat, one-shot agent, doctor, onboard, accept, eval, and engineering gates
- Assemble `RBPAgent` (`agent.py`): wire in-repo Nanobot, filter tools, normalize typed JSON verdicts
- Bridge all science I/O through [`backends/delivery/`](backends/delivery/README.md) (read-only sibling `rhobind_agent_delivery`)
- Own paths, onboard, capability honesty, verdict schema, and SoT → workspace overlay sync

## Implementation

| Path | Role |
|------|------|
| `__main__.py` | `python -m app` → CLI |
| `agent.py` | `RBPAgent`: session / tool filter / Nanobot integration / verdict unwrap |
| [`cli/`](cli/README.md) | argparse command groups (user / accept / eval / maint) |
| [`backends/delivery/`](backends/delivery/README.md) | `DeliveryToolClient`, `mapping.yaml`, env resolve |
| `core/` | `paths`, `runtime_config`, `capability_matrix`, `verdict_schema`, `onboard`, `chat_ux`, … |
| `dev/` | `gate` / `layout` / `mvp` / `compliance` (engineering, not science scores) |
| `sync_overlay.py` | SoT skill/tools → runtime + `workspace/skills` |
| `dotenv_util.py` | Load package-root `.env` |
| `sot.py` / `integrate.py` | SoT helpers; prefer `app.agent` over legacy `integrate` |

Layering (see [`ARCHITECTURE.md`](../ARCHITECTURE.md) §1):

```
CLI (app/cli)
  → app.agent.RBPAgent
      → nanobot/ (loop · tools · skill)
          → app.backends.delivery
              → ../rhobind_agent_delivery (read-only)
Offline eval → rbp_eval/ (not on the chat hot path)
```

## How to use

```bash
nanobot-bio doctor|chat|agent|onboard|gate|…
# equivalents:
python -m app doctor
rbp-agent chat
```

Setup entrypoints: [`scripts/setup/`](../scripts/setup/README.md). Install detail: [`INSTALL.md`](../INSTALL.md). Constraints: [`AGENTS.md`](../AGENTS.md).

After editing skill / RBP tools under `nanobot/`:

```bash
python -m app.sync_overlay
# or: nanobot-bio doctor
```

## Design rationale

- **Separation of concerns:** App orchestrates; delivery owns RhoBind / Foldseek / AF3. The LLM never invents `p_hat`, motifs, or annotations.
- **Stable CLI names:** Collaborators and CI depend on argparse command names in `cli/parser.py`.
- **Single import root:** `NANOBOT_SRC` / `sys.path` prefer in-repo `nanobot/` so `import nanobot` cannot be stolen by PyPI `nanobot-ai`.
- **Honest capabilities:** Missing AF3 / peaks become caveats via `capability_matrix`, not fake similarity `0`.

## See also

[`../README.md`](../README.md) · [`ARCHITECTURE.md`](../ARCHITECTURE.md) · [`INSTALL.md`](../INSTALL.md) · [`../nanobot/README.md`](../nanobot/README.md) · [`../artifacts/README.md`](../artifacts/README.md)
