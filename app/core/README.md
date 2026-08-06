# app/core/

Product-runtime helpers for paths, config, capabilities, verdict JSON, and chat UX. This package does **not** run the agent loop and does **not** compute scientific `p_hat`.

[English] · [中文](README.zh.md)

## Purpose

`app.core` is the shared glue used by the CLI, `RBPAgent`, delivery bridge, and offline eval writers. It owns canonical artifact locations, deep-merged runtime YAML (`defaults.yaml` ± `evolved.yaml`), honesty probes for AF3 / peaks / delivery smoke, and the typed verdict normalize/validate path that turns LLM text into JSON the product can trust.

Eval-only fusion math lives under [`rbp_eval/`](../../rbp_eval/README.md). The interactive agent path is [`app.agent.RBPAgent`](../agent.py) → Nanobot — not a fixed pipeline module here.



## Portable layout (Linux)

```bash
export BIO_ROOT="${BIO_ROOT:-$HOME/bio_agent}"
# Checkout folder is often Nanobot-bio (GitHub); lowercase nanobot-bio also OK.
cd "${NANOBOT_BIO_ROOT:-$BIO_ROOT/Nanobot-bio}"
source scripts/nbio.sh
```

## Layout

| Module | Role |
|--------|------|
| `paths.py` | Canonical `artifacts/{sessions,traces,reports,cache,…}` dirs, report helpers, migrations |
| `runtime_config.py` | `load_runtime_config()`, `fusion_weights()`, label / abstain thresholds |
| `capability_matrix.py` | Probe AF3 / peaks / delivery; write capability matrix for `doctor` |
| `verdict_schema.py` | `normalize_verdict`, `validate_verdict`, `extract_verdict_from_content` |
| `onboard.py` | Interactive / non-interactive LLM provider + key setup |
| `chat_ux.py` | Quiet logs, visible tool steps, verdict pretty-print in chat |
| `science_request.py` | Parse user science asks (RNA / RBP hints) for UX |
| `product_authority.py` | Product authority notes for capability honesty |
| `model_registry.py` | Model id helpers |
| `fusion_rna_policy.py` | Zero RNA-peak fusion weight until peaks are ready |

## Entry points / imports

```python
from app.core.paths import ARTIFACTS, ensure_artifact_dirs, report_path, DEFAULT_LOO_REPORT
from app.core.runtime_config import load_runtime_config, fusion_weights, label_thresholds
from app.core.verdict_schema import normalize_verdict, validate_verdict, extract_verdict_from_content
from app.core.capability_matrix import probe_capabilities, write_capability_matrix

# Lazy re-exports also work:
from app.core import normalize_verdict, validate_verdict
```

## Code examples

**Artifacts and report paths**

```python
from app.core.paths import ensure_artifact_dirs, report_path, find_report

dirs = ensure_artifact_dirs() # creates artifacts/sessions, reports/json, …
out = report_path("eval_loo_report.json") # → artifacts/reports/json/…
existing = find_report("eval_loo_report.json")
```

**Runtime config + fusion weights**

```python
from app.core.runtime_config import load_runtime_config, fusion_weights, config_source

cfg = load_runtime_config(prefer_evolved=True)
print(config_source()) # which YAML layers are active
print(fusion_weights()) # rna_peak_homology may be forced to 0
```

**Verdict normalize / validate**

```python
from app.core.verdict_schema import extract_verdict_from_content, validate_verdict

raw = extract_verdict_from_content('{"label":"binds","p_hat":0.91,"confidence":"high"}')
ok, errors = validate_verdict(raw)
assert ok, errors
```

## Dependencies / env

- Reads `config/defaults.yaml` and optionally `config/evolved.yaml` (`evolved: true`).
- Capability probes may touch `DELIVERY_ROOT`, AF3 status files, and delivery smoke reports — see [`INSTALL.md`](../../INSTALL.md).
- No GPU required for path/config/verdict helpers; `probe_capabilities` may shell-check conda envs.

## See also

[`../README.md`](../README.md) · [rbp-agent SKILL.md](../../nanobot/skills/rbp-agent/SKILL.md) · [`../../config/README.md`](../../config/README.md) · [`../../ARCHITECTURE.md`](../../ARCHITECTURE.md)
