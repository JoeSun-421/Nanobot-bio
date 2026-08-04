# artifacts/

Canonical runtime outputs for sessions, reports, caches, and diagnostics.

[English] · [中文](README.zh.md)

> Parent package map and `$BIO_ROOT` layout: [`README.md`](../README.md). Activate with `cd "$BIO_ROOT/nanobot-bio" && source scripts/nbio.sh`.

## Features

- Single gitignored tree for all run products (`app.core.paths`)
- Sessions, PA memory, eval/cert reports, traces, caches, logs, diagnostics
- Symlinked from `workspace/sessions` and `workspace/memory` for Nanobot compatibility

## Implementation

| Subdir | Purpose |
|--------|---------|
| `sessions/` | Chat transcripts by local start date |
| `memory/` | PA long-term memory (`MEMORY.md`, …); excluded from scientific prompts |
| `reports/json/` · `reports/md/` · `reports/csv/` | Eval / certify / smoke / manifest reports |
| `traces/` | Run / eval traces (e.g. jsonl) |
| `cache/` | Structure / literature / `proxy_map.json` (proxy ≠ PA memory; does not alter RhoBind scores) |
| `logs/` | Logs |
| `diag/` | Diagnostics (e.g. AF3 setup smokes) |

Created by `ensure_artifact_dirs()` / setup. Path helpers: `ARTIFACTS`, `REPORTS_*`, `SESSIONS`, `report_path()`, …

### Gitignore

From [`.gitignore`](../.gitignore):

```
artifacts/**
!artifacts/README.md
!artifacts/README.zh.md
```

Tracked: only these README files. Everything else under `artifacts/` stays local.

### Who writes here?

- Agent chat / session manager
- `rbp_eval` and `scripts/cert/*`
- `environment_manifest.py`, `smoke_delivery_tools.py`
- Setup / AF3 diagnostics

## How to use

No need to create dirs by hand after setup/`doctor`. Point reports explicitly when needed:

```bash
python -m rbp_eval.loo.loo_eval --out artifacts/reports/json/eval_loo_report.json
bash scripts/cert/certify.sh
```

For eval turns, prefer `ephemeral=True` or clear the matching session file — editing `MEMORY.md` alone does not reset chat reuse ([`ARCHITECTURE.md`](../ARCHITECTURE.md) §2).

## Design rationale

- One canonical root prevents scattering secrets, large caches, and personal sessions into the git tree.
- Format-split report dirs (`json`/`md`/`csv`) keep machine and human artifacts discoverable.
- Proxy cache is a retrieval shortcut only — never a scientific score source.

## See also

[`../README.md`](../README.md) · [`../workspace/README.md`](../workspace/README.md) · [`ARCHITECTURE.md`](../ARCHITECTURE.md) · `app/core/paths.py`
