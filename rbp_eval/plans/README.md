# rbp_eval/plans/

Proposal evaluation plan harness (light / heavy) and faithfulness sheets.

[English] · [中文](README.zh.md)

> Parent package map and `$BIO_ROOT` layout: [`README.md`](../../README.md). Activate with `cd "$BIO_ROOT/nanobot-bio" && source scripts/nbio.sh`.

## Purpose

Implements the Proposal Evaluation Plan: hide own head → retrieve donors → score policy-level AUPRC/AUROC from delivery transfer CSVs (light), plus optional heavy instance metrics when RhoBind is available. Also writes a qualitative faithfulness rating CSV and heuristic acceptance strata tags (`own_head`, `in_panel_transfer`, `dark_protein`, `cross_kingdom`). Output defaults under `artifacts/reports/{json,md,csv}/`.

## Layout

| Module | Role |
|--------|------|
| `evaluation_plan.py` | Light/heavy plan, strata, faithfulness sheet, CLI |
| `__init__.py` | Package marker |

## Entry points

```bash
nanobot-bio eval-plan [--with-seq]
python -m rbp_eval.plans.evaluation_plan
python -m rbp_eval.plans.evaluation_plan --with-seq
python -m rbp_eval.plans.evaluation_plan --heavy   # needs ≥8 GiB + rhobind
```

```python
from rbp_eval.plans.evaluation_plan import (
    assign_strata,
    run_light_evaluation_plan,
    write_faithfulness_sheet,
)
```

## Code examples

**CLI (light, 2 GiB-safe)**

```bash
python -m rbp_eval.plans.evaluation_plan \
  --out artifacts/reports/json/evaluation_plan_report.json \
  --md artifacts/reports/md/evaluation_plan_report.md \
  --qual artifacts/reports/csv/faithfulness_rating_sheet.csv
```

**Strata helpers + light plan import**

```python
from rbp_eval.plans.evaluation_plan import assign_strata, strata_bucket_schema

tags = assign_strata(in_panel=True, mode="transfer", dark=False)
print(tags)  # e.g. includes in_panel_transfer / own_head heuristics
print(list(strata_bucket_schema().keys())[:4])
```

Light plan still needs delivery LOO / transfer matrix assets (same as `rbp_eval.loo`); it does **not** re-run RhoBind unless `--heavy`.

## Dependencies / env

- Light: delivery CSV transfer matrix + domain (optional `--with-seq` ESM) views.
- Heavy: `rhobind` conda, labeled FASTA subsample, GPU/CPU with enough RAM.
- Reports consumed by `nanobot-bio gate` / `promote-evolved` (`evaluation_plan_report.json`).

## See also

[`../README.md`](../README.md) · [`../loo/README.md`](../loo/README.md) · [`../scoring/README.md`](../scoring/README.md) · [`../../app/dev/README.md`](../../app/dev/README.md)
