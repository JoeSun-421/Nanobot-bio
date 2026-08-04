# rbp_eval/accept/

Scientific acceptance: own-head golden, transfer calibration, release metrics, LLM accept, gap closure.

[English] · [中文](README.zh.md)

## Purpose

Holds **scientific** accept paths for nanobot-bio. Engineering gates (`gate` / `compliance` / `layout` / `mvp`) stay in `app/dev`. Here: delivery own-head (no LLM), Phase-2 transfer calibration, immutable release metric reproduction, LLM product-path accept, and gap-closure evidence reports. CLI aliases: `nanobot-bio own-head` / `accept-golden` / `accept-llm` / `gap-closure`.

## Layout



## Portable layout (Linux)

```bash
export BIO_ROOT="${BIO_ROOT:-$HOME/bio_agent}"
cd "$BIO_ROOT/nanobot-bio"
source scripts/nbio.sh
```

| Module | Role |
|--------|------|
| `own_head.py` | Ideal-env: `resolve_rbp(PTBP1)` → `rhobind_predict` vs golden |
| `transfer_calibration.py` | Live / records transfer calibration (`transfer_calibration.v1`) |
| `release_metrics.py` | Reproduce delivery `expected_metrics.csv` without editing delivery |
| `accept_llm.py` | Strict `nanobot_llm` product path + LLM touchpoint evidence |
| `gap_closure.py` | Unseen-trace shape, faithfulness schema, own-head golden checks |
| `__init__.py` | Package marker |

## Entry points

```bash
nanobot-bio own-head
nanobot-bio accept-golden          # alias of own-head
nanobot-bio accept-llm
nanobot-bio gap-closure
python -m rbp_eval.accept.own_head
python -m rbp_eval.accept.transfer_calibration --regime both
python -m rbp_eval.accept.release_metrics --cohort K562
python -m rbp_eval.accept.gap_closure
```

```python
from rbp_eval.accept.accept_llm import run_accept_llm
from rbp_eval.accept.gap_closure import build_gap_closure_report
from rbp_eval.accept.transfer_calibration import build_calibration_report
```

## Code examples

**Own-head golden (delivery, no LLM)**

```bash
# Needs rhobind conda + GPU/CPU; exit 0 ≈ golden prob, 3 = science blocked
python -m rbp_eval.accept.own_head
# or:
nanobot-bio own-head
```

**Transfer calibration (regime both)**

```bash
python -m rbp_eval.accept.transfer_calibration \
  --regime both --cohort K562 --top-k 5 --out artifacts/reports/json/transfer_calibration.json
```

```python
from rbp_eval.accept.gap_closure import check_unseen_trace_shape, build_gap_closure_report

shape = check_unseen_trace_shape(
    [
        "resolve_rbp",
        "fuse_similarity_views",
        "confidence_abstain",
        "predict_interaction",
        "similarity_weighted_vote",
    ],
    predict_targets=["DONOR1"],
)
print(shape.get("ok"), shape.get("errors"))

report = build_gap_closure_report(live_own_head=False)
print(report.get("ok"), list(report.keys()))
# CLI equivalent: python -m rbp_eval.accept.gap_closure --no-live
```

**LLM accept (product path)**

```python
from rbp_eval.accept.accept_llm import run_accept_llm

# Requires LLM provider configured; prefer_nanobot_llm, no fallback
out = run_accept_llm(run_catalogue=True, run_unseen=True, strict=True)
print(out.get("ok"), out.get("mode"), list((out.get("touchpoints") or {}).keys())[:4])
```

## Dependencies / env

- Own-head / release metrics / live calibration: `DELIVERY_ROOT`, `rhobind` conda, adequate RAM/GPU.
- `accept_llm`: Nanobot + LLM API (see `~/.nanobot/config.json` / providers); clears `accept-llm_*` sessions under `artifacts/sessions/`.
- Transfer promote gate expects schema `transfer_calibration.v1` with `score_source=real_rhobind` and `synthetic=false`.

## See also

[`../README.md`](../README.md) · [`../evolve/README.md`](../evolve/README.md) · [`../../app/dev/README.md`](../../app/dev/README.md) · [`../../app/backends/delivery/README.md`](../../app/backends/delivery/README.md) · [`../../docs/product/BINDING_PREDICTION_FLOW.zh.md`](../../docs/product/BINDING_PREDICTION_FLOW.zh.md)
