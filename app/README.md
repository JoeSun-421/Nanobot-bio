# app/

Product shell: CLI, `RBPAgent` assembly, delivery bridge, and runtime config. Never computes `p_hat` itself.

[English] · [中文](README.zh.md)

## Portable layout (Linux)

```bash
export BIO_ROOT="${BIO_ROOT:-$HOME/bio_agent}"
cd "$BIO_ROOT/nanobot-bio"
source scripts/nbio.sh
```

## Purpose

`app/` is the operator-facing product layer of **nanobot-bio**. It wires the in-repo Nanobot runtime, filters tools for RBP science mode, normalizes typed JSON verdicts, and bridges every science call through the read-only delivery client. Collaborators and CI should enter here (`nanobot-bio` / `rbp-agent` / `python -m app`) rather than calling Nanobot or delivery scripts ad hoc.

Offline evaluation and self-evolution live in [`rbp_eval/`](../rbp_eval/README.md) and are intentionally off the chat hot path. Binding-stage semantics: [`BINDING_PREDICTION_FLOW.md`](../docs/product/BINDING_PREDICTION_FLOW.md) · [中文](../docs/product/BINDING_PREDICTION_FLOW.zh.md).

## Layout

| Path | Role |
|------|------|
| `__main__.py` | `python -m app` → CLI |
| `agent.py` | `RBPAgent` / `AgentResult`: session, tool filter, Nanobot integration, verdict unwrap |
| [`cli/`](cli/README.md) | argparse command groups (user / accept / eval / maint) |
| [`backends/`](backends/README.md) · [`backends/delivery/`](backends/delivery/README.md) | `DeliveryToolClient`, `mapping.yaml`, env resolve |
| [`core/`](core/README.md) | paths, runtime_config, capability_matrix, verdict_schema, onboard, chat_ux |
| [`dev/`](dev/README.md) | gate / layout / mvp / compliance (engineering, not science scores) |
| `sync_overlay.py` | SoT skill/tools → runtime + `workspace/skills` |
| `dotenv_util.py` | Load package-root `.env` |
| `sot.py` / `integrate.py` | SoT helpers; prefer `app.agent` over legacy `integrate` |

Layering ([`ARCHITECTURE.md`](../ARCHITECTURE.md) §1):

```
CLI (app/cli)
  → app.agent.RBPAgent
      → nanobot/ (loop · tools · skill)
          → app.backends.delivery
              → ../rhobind_agent_delivery (read-only)
Offline eval → rbp_eval/ (not on the chat hot path)
```

## Entry points

Console scripts (from `pyproject.toml`): `nanobot-bio`, `rbp-agent` → `app.cli:main`.

```bash
nanobot-bio doctor|chat|agent|onboard|gate|…
python -m app doctor
rbp-agent chat
```

## Code examples

**One-shot agent via CLI**

```bash
# Activate env first (see INSTALL.md / scripts/nbio)
nanobot-bio doctor
nanobot-bio agent --query "Does this RNA bind PTBP1?" --example
# or with explicit RNA file:
nanobot-bio agent --rna-file /path/to/rna.fa --query "Predict binding to PTBP1"
```

**Programmatic `RBPAgent`**

```python
from app.agent import RBPAgent

agent = RBPAgent()  # applies delivery env, registers RBP tools
result = agent.run_sync("Predict whether the sample RNA binds PTBP1.")
print(result.verdict_valid, result.verdict)
print(result.tools_used)
# Async equivalent:
# result = await agent.run("…")
```

**Sync SoT after editing skill / RBP tools**

```bash
python -m app.sync_overlay
nanobot-bio doctor
```

## Dependencies / env

- Editable install of this repo + LLM key via `nanobot-bio onboard` (`.env` / `~/.nanobot/config.json`).
- Science path needs sibling `rhobind_agent_delivery` (or `DELIVERY_ROOT`) and mapped conda envs.
- `NANOBOT_SRC` / `sys.path` prefer in-repo `nanobot/` so PyPI `nanobot-ai` cannot steal the import.

Setup: [`scripts/setup/`](../scripts/setup/README.md) · [`INSTALL.md`](../INSTALL.md). Constraints: [`AGENTS.md`](../AGENTS.md).

## Design rationale

- **Separation of concerns:** App orchestrates; delivery owns RhoBind / Foldseek / AF3. The LLM never invents `p_hat`, motifs, or annotations.
- **Stable CLI names:** Collaborators and CI depend on argparse names in `cli/parser.py`.
- **Honest capabilities:** Missing AF3 / peaks become caveats via `capability_matrix`, not fake similarity `0`.

## See also

[`../README.md`](../README.md) · [`ARCHITECTURE.md`](../ARCHITECTURE.md) · [`../docs/product/BINDING_PREDICTION_FLOW.zh.md`](../docs/product/BINDING_PREDICTION_FLOW.zh.md) · [`../nanobot/README.md`](../nanobot/README.md) · [`../artifacts/README.md`](../artifacts/README.md)
