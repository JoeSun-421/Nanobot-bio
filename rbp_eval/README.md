# rbp_eval/

Offline scientific evaluation, LOO, fusion scoring, acceptance, and self-evolution.

[English] · [中文](README.zh.md)

## Purpose

This package is the offline science lab for nanobot-bio. It measures own-head / LOO ceilings, fuses multi-view hits, calibrates transfer, and runs gated self-evolution that writes `config/evolved.candidate.yaml`. It is intentionally **off the chat hot path** — interactive UX stays in `app/` + `nanobot/`. Physical path = import path (no facade); use `python -m rbp_eval.<subpkg>.<module>`.

Binding product flow: [rbp-agent/SKILL.md](../nanobot/skills/rbp-agent/SKILL.md). Evolution: [self-evolution (evolve)](evolve/README.md) · [中文](evolve/README.zh.md).

## Self-evolution (summary)

Policy and five steps: [self-evolution (evolve)](evolve/README.md). 
Matrix expand: [LOO expand](loo/README.md).

```bash
export BIO_ROOT="${BIO_ROOT:-$HOME/bio_agent}"
cd "${NANOBOT_BIO_ROOT:-$BIO_ROOT/Nanobot-bio}" && source scripts/nbio.sh
export RHOBIND_RELEASE="${RHOBIND_RELEASE:-$DELIVERY_ROOT/release/rhobind_release_v1}"
export RBP_TEST_DATA_ROOT="${RBP_TEST_DATA_ROOT:-$BIO_ROOT/rhobind_testdata_v2/rhobind_testdata_v2/test_data}"
nanobot-bio expand-loo-matrix --cohort K562 --max-seqs 256 --skip-existing-helds
export RBP_LOO_TRANSFER_DIR="$(pwd)/rbp_eval/data/transfer"
nanobot-bio evolve --transfer-dir "$RBP_LOO_TRANSFER_DIR" --medoids --max-seqs 64 \
 --collect-agent-traces --require-traces
nanobot-bio run-eval --medoids --transfer-dir "$RBP_LOO_TRANSFER_DIR" \
 --policy config/evolved.candidate.yaml --max-seqs 64
nanobot-bio review-toolkit-proposals --list
nanobot-bio promote-evolved
```

## Layout

| Subpackage | Role |
|------------|------|
| [`scoring/`](scoring/README.md) | Hit fusion (`fuse_hits.py`), head index, metrics |
| [`loo/`](loo/README.md) | Light LOO + heavy hide-own-head |
| [`accept/`](accept/README.md) | own-head, transfer calibration, release metrics, LLM accept, gap closure |
| [`evolve/`](evolve/README.md) | runner, orchestrator, promote, retune, proxy cache |
| [`runtime/`](runtime/README.md) | Eval hooks / trace schema |
| [`rna/`](rna/README.md) | RNA-axis gate helpers |
| [`plans/`](plans/README.md) | Evaluation plan / faithfulness reports |

Reports default to `artifacts/reports/{json,md,csv}/` via `app.core.paths`.

Config ([`ARCHITECTURE.md`](../ARCHITECTURE.md) §5):

- Defaults: `config/defaults.yaml`
- Candidate: `config/evolved.candidate.yaml` (gitignored)
- Promoted: `config/evolved.yaml` (deep-merged when `evolved: true`)

## Entry points

```bash
python -m rbp_eval # module help
nanobot-bio run-eval|heavy-loo|evolve|promote-evolved|review-toolkit-proposals|eval-plan|own-head
```

## Code examples

```bash
python -m rbp_eval.loo.loo_eval --out artifacts/reports/json/eval_loo_report.json
python -m rbp_eval.accept.own_head
python -m rbp_eval.accept.transfer_calibration --regime both
python -m rbp_eval.evolve.runner --evolve
python -m rbp_eval.plans.evaluation_plan --with-seq
bash scripts/cert/smoke_evolve_loop.sh
```

```python
from rbp_eval.scoring.fuse_hits import fuse_rbp_hits, aggregate_p_hat

donors = fuse_rbp_hits([
 [{"alias": "PTBP1", "metric": "esm_cosine", "score": 0.82}],
 [{"alias": "PTBP1", "metric": "foldseek", "score": 0.71}],
], top_k=5)
print(donors[0]["alias"], donors[0].get("score"))
```

## Dependencies / env

- Real scores need `DELIVERY_ROOT` + science conda envs.
- Public CI often skips heavy science — use local [`scripts/cert/`](../scripts/cert/README.md).
- Promote requires gate + nested-split evidence ([`AGENTS.md`](../AGENTS.md)).

## Design rationale

- Keep offline tuning off the chat hot path.
- Never substitute LLM-invented scores for own-head / LOO metrics.
- Fusion weights stay honest to measured ablations (e.g. `rna_peak_homology: 0` until peaks promote).

## See also

[`../README.md`](../README.md) · [`../config/README.md`](../config/README.md) · [rbp-agent SKILL.md](../nanobot/skills/rbp-agent/SKILL.md) · [`ARCHITECTURE.md`](../ARCHITECTURE.md) · [`../scripts/cert/README.md`](../scripts/cert/README.md)
