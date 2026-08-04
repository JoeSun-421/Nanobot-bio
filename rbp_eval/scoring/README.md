# rbp_eval/scoring/

Hit fusion, head-index helpers, and offline metrics for transfer ranking.

[English] · [中文](README.zh.md)

## Purpose

Implements multi-view fusion used when ranking donor RBPs and aggregating transfer probabilities in offline eval (and mirrored conceptually by product tools). `fuse_rbp_hits` merges per-modality hit lists; `aggregate_p_hat` turns donor head probabilities + similarities into a transfer score for reports. Chat-time transfer aggregation authority remains delivery `similarity_weighted_vote`.

## Layout



## Portable layout (Linux)

```bash
export BIO_ROOT="${BIO_ROOT:-$HOME/bio_agent}"
cd "$BIO_ROOT/nanobot-bio"
source scripts/nbio.sh
```

| Module | Role |
|--------|------|
| `fuse_hits.py` | `fuse_rbp_hits`, `fuse_proxy_candidates`, `aggregate_p_hat`, `label_from_p_hat` |
| `head_index.py` | Head / catalogue index helpers |
| `metrics.py` | Offline metric helpers |
| `__init__.py` | Package marker |

## Entry points

```python
from rbp_eval.scoring.fuse_hits import (
    fuse_rbp_hits,
    aggregate_p_hat,
    fuse_proxy_candidates,
    DEFAULT_WEIGHTS,
)
```

## Code examples

```python
from rbp_eval.scoring.fuse_hits import fuse_rbp_hits, aggregate_p_hat, label_from_p_hat

hits = fuse_rbp_hits(
    [
        [{"alias": "HNRNPA1", "metric": "esm_cosine", "score": 0.9}],
        [{"alias": "HNRNPA1", "metric": "domain_jaccard", "score": 0.6}],
    ],
    top_k=5,
    tau_drop=None,
)
print(hits[0]["alias"], hits[0].get("vote_similarity"), hits[0].get("score"))

# Aggregate donor head probs (shapes vary by caller; see fuse_hits.aggregate_p_hat docstring)
# p = aggregate_p_hat(donor_probs=..., similarities=..., method="mean")
# print(label_from_p_hat(p))
```

```bash
# Fusion is exercised via LOO / evolve / eval-plan modules:
python -m rbp_eval.loo.loo_eval --out artifacts/reports/json/eval_loo_report.json
```

## Dependencies / env

- May consult `app.core.capability_matrix.rna_blastn_status` to zero `rna_peak_homology` when peaks DB is absent.
- Weights often come from `app.core.runtime_config.fusion_weights()`.

## See also

[`../README.md`](../README.md) · [`../loo/README.md`](../loo/README.md) · [`../../config/README.md`](../../config/README.md) · [`../../docs/product/BINDING_PREDICTION_FLOW.zh.md`](../../docs/product/BINDING_PREDICTION_FLOW.zh.md)
