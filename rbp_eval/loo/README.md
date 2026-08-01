# rbp_eval/loo/

Leave-one-out evaluation: light policy LOO and heavy hide-own-head runs.

[English] · [中文](README.zh.md)

## Purpose

Quantifies how well transfer policies recover when a catalogue head is held out. `loo_eval.py` is the lighter report path (policy vs own-head AUPRC-style summaries). `heavy_loo.py` exercises the expensive hide-own-head protocol used for stronger certification. Reports land under `artifacts/reports/`.

## Layout

| Module | Role |
|--------|------|
| `loo_eval.py` | Light LOO report CLI (`python -m rbp_eval.loo.loo_eval`) |
| `heavy_loo.py` | Heavy hide-own-head CLI |
| `__init__.py` | Package marker |

## Entry points

```bash
python -m rbp_eval.loo.loo_eval --out artifacts/reports/json/eval_loo_report.json
python -m rbp_eval.loo.heavy_loo --help
nanobot-bio run-eval
nanobot-bio heavy-loo
```

## Code examples

```bash
# Light LOO (needs prior delivery LOO CSVs / summaries on disk)
python -m rbp_eval.loo.loo_eval \
  --out artifacts/reports/json/eval_loo_report.json

# Heavy path via product CLI wrapper
nanobot-bio heavy-loo --help
```

```python
from rbp_eval.loo.loo_eval import load_loo_summary, resolve_loo_csvs

# Helpers used by the CLI when assembling the report
print(resolve_loo_csvs)
print(load_loo_summary)
```

## Dependencies / env

- Needs delivery LOO artifacts / science envs for meaningful numbers.
- `app.dev.gate.delivery_loo_ready()` detects when light asserts can run in CI.

## See also

[`../README.md`](../README.md) · [`../scoring/README.md`](../scoring/README.md) · [`../../scripts/cert/README.md`](../../scripts/cert/README.md)
