# scripts/data/

Idempotent rebuild helpers for the delivery operational database.

[English] · [中文](README.zh.md)

## Features

- Rebuild `agent_db/` (registry, embedding bank, foldseek, mmseqs, optional peaks) from raw protein/structure/benchmark sources
- Idempotent steps: skip when outputs are newer than inputs; `--force` rebuilds
- Does not edit delivery application source — calls build scripts under delivery `agent/database/build/`

## Implementation

| File | Role |
|------|------|
| `bootstrap_data.sh` | Orchestrates: embedding bank → foldseek DB → mmseqs seq DB → `rbp_registry.json` → peaks DB (optional) |

Root / delivery resolve via `$SCRIPT_DIR/../..` and `BIO_ROOT` / `DELIVERY_ROOT`. Steps documented in delivery `agent/database/SOURCES.md`.

Prereqs:

- Conda envs: `protein_embed` (foldseek / ESM), `rna` (mmseqs)
- Readable raw bundle `RB`, benchmark results, head index dir
- Peaks step needs `PROCESSED_ROOT` (default `$RB/../processed_260417`) or `--skip-peaks`

## How to use

```bash
bash scripts/data/bootstrap_data.sh \
 --rb /path/to/rbp_proteins_260417 \
 --benchmarks /path/to/results/benchmark_cluster \
 --head-index-dir /path/to/head_index_dir \
 --out /path/to/agent_db

# optional:
# --force
# --skip-peaks
# --skip-embeddings
```

Point runtime at the rebuilt DB via `AGENT_DB` / delivery env (see [`INSTALL.md`](../../INSTALL.md)).

## Design rationale

- Operational DB rebuild is an operator concern, not App chat logic — keep it under `scripts/data/`.
- Idempotency makes re-runs safe on large hosts.
- Peaks remain optional while fusion weight stays at `0` until ablation promotes ([`config/README.md`](../../config/README.md)).

## See also

[`../README.md`](../README.md) · [`INSTALL.md`](../../INSTALL.md) · [`../../app/backends/delivery/README.md`](../../app/backends/delivery/README.md)
