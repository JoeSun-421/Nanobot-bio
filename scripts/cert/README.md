# scripts/cert/

Non-LLM certification path, environment manifests, and delivery / evolve smokes.

[English] · [中文](README.zh.md)

> Parent package map and `$BIO_ROOT` layout: [`README.md`](../../README.md). Activate with `cd "${NANOBOT_BIO_ROOT:-$BIO_ROOT/Nanobot-bio}" && source scripts/nbio.sh`.

## Features

- Reproducible pre-delivery certify chain that never reads or prints LLM API keys
- Environment + immutable-input hash manifest
- Delivery tool smoke (offline-safe subset by default; optional network / AF3)
- Evolve → candidate → promote dry-run smoke with temporary fixtures

## Implementation

| File | Role |
|------|------|
| `certify.sh` | Orchestrates the certify path; flags `--network` / `--transfer` / `--release-metrics` / `--full` |
| `environment_manifest.py` | Writes → `artifacts/reports/json/environment_manifest.json` |
| `smoke_delivery_tools.py` | Bridge smoke vs registry / mapping; `--network` / `--af3` / `--report` |
| `smoke_evolve_loop.sh` | Self-evolution → candidate → promote dry-run without long real evals |

`certify.sh` flow (conceptually):

```
certify.sh
 ├─ environment_manifest.py
 ├─ python -m app doctor
 ├─ python -m rbp_eval.accept.own_head
 ├─ smoke_delivery_tools.py
 ├─ (optional) release_metrics / transfer_calibration
 └─ pytest
```

Root: `$SCRIPT_DIR/../..`. Prefer agent Python `$ROOT/.venv/bin/python`.

## How to use

```bash
bash scripts/cert/certify.sh
bash scripts/cert/certify.sh --full
bash scripts/cert/certify.sh --transfer # CERTIFY_TARGET / CERTIFY_MAX_SEQS optional

python scripts/cert/environment_manifest.py
python scripts/cert/smoke_delivery_tools.py
python scripts/cert/smoke_delivery_tools.py --network --af3

bash scripts/cert/smoke_evolve_loop.sh
```

Transfer calibration can also be invoked as `python -m rbp_eval.accept.transfer_calibration` (see root README).

## Design rationale

- Collaborators need a **key-free** acceptance path for science stack health.
- Default smoke stays offline-safe; network / AF3 are opt-in to avoid flaky public CI.
- Evolve smoke uses fixtures so promote wiring can be tested without multi-hour LOO.

## See also

[`../README.md`](../README.md) · [`../../rbp_eval/README.md`](../../rbp_eval/README.md) · [`INSTALL.md`](../../INSTALL.md)
