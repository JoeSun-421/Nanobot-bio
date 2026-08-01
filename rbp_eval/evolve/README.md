# rbp_eval/evolve/

Offline self-evolution: batch val, retune knobs, candidate config, gated promote.

[English] · [中文](README.zh.md)

## Purpose

Runs the offline self-evolution loop that retunes fusion / abstain / label / `tau_drop` knobs from LOO-style validation batches, writes `config/evolved.candidate.yaml`, and promotes to `config/evolved.yaml` only when nested-split + transfer-calibration gates pass. Interactive chat never calls this path — operators use `nanobot-bio evolve` / `promote-evolved` or `python -m rbp_eval.evolve.*`.

Policy docs: [`../../docs/product/SELF_EVOLUTION.md`](../../docs/product/SELF_EVOLUTION.md).

## Layout

| Module | Role |
|--------|------|
| `runner.py` | LOO val batch + optional `--evolve` |
| `orchestrator.py` | `run_self_evolution`, `EvolutionReport` |
| `retune.py` | Weight / threshold / abstain / `tau_drop` retune |
| `proposals.py` | Tool attribution + toolkit expansion proposals |
| `proxy_cache.py` | Promote frequent target→proxy maps (`artifacts/cache/proxy_map.json`) |
| `promote.py` | Gate + promote candidate → `evolved.yaml` |
| `evolve_eval.py` | Light nested train/test split on LOO medoids |
| `run_eval.py` | Agent run_eval + modality ablation harness |
| `transfer_promotion.py` | Compare baseline vs candidate transfer reports |
| `__init__.py` | Package marker |

## Entry points

```bash
nanobot-bio evolve [--dry-run]
nanobot-bio evolve-eval
nanobot-bio run-eval
nanobot-bio promote-evolved [--seed]
python -m rbp_eval.evolve.runner --evolve
python -m rbp_eval.evolve.evolve_eval
python -m rbp_eval.evolve.run_eval
```

```python
from rbp_eval.evolve.orchestrator import run_self_evolution
from rbp_eval.evolve.promote import promote_evolved_config
from rbp_eval.evolve.proxy_cache import load_proxy_cache, lookup_proxies
```

## Code examples

**Batch val + write candidate (CLI)**

```bash
# Needs LOO / delivery assets for real scores; dry paths still exercise wiring.
python -m rbp_eval.evolve.runner --top-k 5 --out artifacts/reports/json/val_batch.json
python -m rbp_eval.evolve.runner --evolve --top-k 5

# Nested-split light eval → evolve_eval_decision.json
python -m rbp_eval.evolve.evolve_eval --seed 42 --n-test 5
```

**Programmatic promote (after gates exist)**

```python
from pathlib import Path
from rbp_eval.evolve.promote import promote_evolved_config, CANDIDATE_CONFIG

# Requires reports under artifacts/reports/: eval_loo_report.json,
# evaluation_plan_report.json, evolve_eval_decision.json (PROMOTE),
# transfer_calibration.json matching candidate sha256.
# Fresh clones can bootstrap the gitignored candidate from the example:
path = promote_evolved_config(seed=True, require_reports=True)
print("promoted:", path, "from", CANDIDATE_CONFIG)
```

**Proxy cache lookup**

```python
from rbp_eval.evolve.proxy_cache import load_proxy_cache, lookup_proxies

cache = load_proxy_cache()
hits = lookup_proxies(alias="PTBP1")  # keyword-only; loads cache internally
print("entries", len(cache.get("entries") or {}), "lookup", hits)
```

## Dependencies / env

- Real retune / promote needs delivery release + science conda (`DELIVERY_ROOT`, `rhobind` env).
- Candidate file `config/evolved.candidate.yaml` is gitignored; use `--seed` / example seed for bootstrap.
- Promote refuses synthetic retrieval-only evolve reports and requires positive nested-split `delta_auprc` (`n>=10`).
- Cert loop: [`../../scripts/cert/README.md`](../../scripts/cert/README.md) (`smoke_evolve_loop.sh`).

## See also

[`../README.md`](../README.md) · [`../accept/README.md`](../accept/README.md) · [`../loo/README.md`](../loo/README.md) · [`../../config/README.md`](../../config/README.md) · [`../../docs/product/SELF_EVOLUTION.md`](../../docs/product/SELF_EVOLUTION.md)
