# Agent-side LOO transfer matrix (experimental copy)

<p><b>English</b> · <a href="README.zh.md">中文</a></p>

This directory holds an **expanded LOO transfer matrix copy** for nanobot-bio
self-evolution / A–B experiments.

- **Scientific SoT** remains under `rhobind_agent_delivery` (do not edit from here).
- Populate with: `nanobot-bio expand-loo-matrix`
- Prefer this copy by exporting:

```bash
export BIO_ROOT="${BIO_ROOT:-$HOME/bio_agent}"
cd "$BIO_ROOT/nanobot-bio"
source scripts/nbio.sh
export RBP_LOO_TRANSFER_DIR="$(pwd)/rbp_eval/data/transfer"
export TRANSFER_DIR="$RBP_LOO_TRANSFER_DIR"
export RBP_TEST_DATA_ROOT="${RBP_TEST_DATA_ROOT:-$BIO_ROOT/rhobind_testdata_v2/rhobind_testdata_v2/test_data}"
```

## Held selection (not limited to seed ~10)

`expand-loo-matrix` plans **every cohort-catalogue RBP that has**
`release/rhobind_release_v1/test_data/{k562|hepg2}/<ALIAS>/test.fasta`
(labeled POS/NEG). The seed `loo_summary.csv` (~10 helds) is only a starting
CSV copy — it does **not** cap which helds are scored.

```bash
# See what would run (no GPU work)
nanobot-bio expand-loo-matrix --cohort K562 --list-helds

# Resume scoring (skips manifest completed_held)
RHOBIND_DEVICE=cuda nanobot-bio expand-loo-matrix --cohort K562 --max-seqs 64 --device cuda

# Only score helds not already in loo_summary.csv
nanobot-bio expand-loo-matrix --cohort K562 --skip-existing-helds --list-helds
```

If `n_held_planned` is small (e.g. 5), that is a **data gap**: install more
labeled `test.fasta` under the release tree. `agent_db/peaks_db/peaks.fasta`
has POS peaks for ~118 K562 RBPs but is **not** a drop-in LOO test set (needs NEG).

Large CSV outputs are gitignored; `manifest.json` records cohort / resume state.
