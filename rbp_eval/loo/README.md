# rbp_eval/loo/

Leave-one-out evaluation: light policy LOO, heavy hide-own-head, matrix expand, A/B.

[English] · [中文](README.zh.md)

## Purpose

Quantifies transfer when a catalogue head is held out. Agent-side matrix expand never edits delivery SoT; set `RBP_LOO_TRANSFER_DIR` for evolve / run-eval.

## Layout

| Module | Role |
|--------|------|
| `loo_eval.py` | Light LOO report / CSV resolve |
| `heavy_loo.py` | Heavy hide-own-head + `test_fasta_for` (`RBP_TEST_DATA_ROOT`) |
| `batch_score_held.py` | Encode-once × all heads (rhobind env) |
| `expand_matrix.py` | Expand agent-side LOO matrix (resume, validate) |
| `matrix_ab_eval.py` | Delivery vs expanded matrix A/B |

## Entry points

```bash
# After source scripts/nbio.sh in nanobot-bio:
export BIO_ROOT="${BIO_ROOT:-$(cd .. && pwd)}"
export RBP_TEST_DATA_ROOT="${RBP_TEST_DATA_ROOT:-$BIO_ROOT/rhobind_testdata_v2/rhobind_testdata_v2/test_data}"

nanobot-bio expand-loo-matrix --cohort K562 --list-helds
nanobot-bio expand-loo-matrix --cohort K562 --max-seqs 256 --skip-existing-helds
nanobot-bio heavy-loo --medoids --max-seqs 64
nanobot-bio loo-matrix-ab
```

See [`../../README.md`](README.md) · [中文](README.md).
