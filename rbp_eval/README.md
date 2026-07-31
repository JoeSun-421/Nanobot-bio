# rbp_eval/

Offline scientific evaluation, LOO, fusion scoring, acceptance, and self-evolution.

[English] · [中文](README.zh.md)

## Features

- Leave-one-out / hide-own-head evaluation and recovered AUPRC-style metrics
- Hit fusion scoring used by transfer similarity / weights
- Acceptance modules: own-head, transfer calibration, release metrics, LLM touchpoints, gap closure
- Self-evolution loop that writes `config/evolved.candidate.yaml` and a gated `promote` path
- Physical path = import path (no top-level facade)

## Implementation

| Subpackage | Role |
|------------|------|
| `scoring/` | Hit fusion (`fuse_hits.py`), head index helpers, metrics |
| `loo/` | `loo_eval.py` (light LOO), `heavy_loo.py` (hide-own-head) |
| `accept/` | `own_head`, `transfer_calibration`, `release_metrics`, `accept_llm`, `gap_closure` |
| `evolve/` | `run_eval`, `orchestrator`, `promote`, `runner`, `retune`, `proxy_cache`, … |
| `runtime/` | Eval runtime helpers |
| `rna/` | RNA-axis helpers |
| `plans/` | Evaluation plan / metrics reporting |

Reports default to `artifacts/reports/{json,md,csv}/` via `app.core.paths`.

Config relationship ([`ARCHITECTURE.md`](../ARCHITECTURE.md) §5):

- Defaults: `config/defaults.yaml`
- Candidate: `config/evolved.candidate.yaml` (gitignored)
- Promoted: `config/evolved.yaml` (deep-merged when `evolved: true`)

## How to use

```bash
python -m rbp_eval                          # common module help
python -m rbp_eval.loo.loo_eval --out artifacts/reports/json/eval_loo_report.json
python -m rbp_eval.accept.own_head
python -m rbp_eval.accept.transfer_calibration --regime both …
python -m rbp_eval.evolve.runner [--evolve]
bash scripts/cert/smoke_evolve_loop.sh      # dry-run evolve smoke

# CLI wrappers:
nanobot-bio run-eval
nanobot-bio heavy-loo
nanobot-bio evolve|evolve-eval|promote-evolved
```

Needs `DELIVERY_ROOT` + science conda for real scores. Public CI often skips heavy science — use local [`scripts/cert/`](../scripts/cert/README.md).

## Design rationale

- Keep offline tuning **off the chat hot path** so interactive UX stays thin.
- Promote requires gate + nested-split evidence (`delta_auprc > 0` or HOLD) — no silent hand-edits claiming evolution ([`AGENTS.md`](../AGENTS.md)).
- Fusion weights (e.g. `rna_peak_homology: 0` until peaks ablation promotes) stay honest to measured ablations.
- Never substitute LLM-invented scores for own-head / LOO metrics.

## See also

[`../README.md`](../README.md) · [`../config/README.md`](../config/README.md) · [`ARCHITECTURE.md`](../ARCHITECTURE.md) · [`../scripts/cert/README.md`](../scripts/cert/README.md)
