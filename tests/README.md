# tests/

Pytest suite for layout, contracts, CLI/UX, delivery bridge, and offline eval logic.

[English] · [中文](README.zh.md)

## Features



## Portable layout (Linux)

```bash
export BIO_ROOT="${BIO_ROOT:-$HOME/bio_agent}"
# Checkout folder is often Nanobot-bio (GitHub); lowercase nanobot-bio also OK.
cd "${NANOBOT_BIO_ROOT:-$BIO_ROOT/Nanobot-bio}"
source scripts/nbio.sh
```

- Proposal / Table compliance and slim-vendor package layout asserts
- Capability-matrix honesty, soft-fail caveats, verdict / stage contracts
- Chat UX, onboard, device, session date layout, memory/promotion phase checks
- Mapping sync vs delivery registry; smoke contracts for cert scripts
- Markers so delivery/GPU-heavy cases skip cleanly on public CI

## Implementation

| File / pattern | Notes |
|----------------|-------|
| `conftest.py` | `requires_delivery` marker; skip without `DELIVERY_ROOT` / sibling bundle |
| `test_package_layout.py` | Directory + slim-vendor asserts |
| `test_proposal_compliance.py` | Table 3 / skill / config compliance |
| `test_capability_matrix.py` / `test_softfail_caveats.py` | Honesty + soft-fail |
| `test_*evolve*` / `test_run_eval.py` / `test_promote_evolved.py` | Evolve / eval |
| `test_smoke_delivery_tools.py` | Contracts around `scripts/cert/smoke_delivery_tools.py` |
| Other `test_*.py` | chat UX, onboard, own-head, session layout, mapping sync, … |

`pyproject.toml` sets `testpaths = ["tests"]`, coverage on `app` + `rbp_eval` (`--cov-fail-under=33`), and markers `science` / `requires_delivery`.

## How to use

```bash
source .venv/bin/activate
pytest -q
pytest tests/test_proposal_compliance.py tests/test_package_layout.py
bash scripts/ci/ci_gate.sh # ruff + pytest + layout (app gate)
bash scripts/cert/certify.sh # longer certify path including pytest
```

Useful env: `NANOBOT_BIO_ROOT`, optional `DELIVERY_ROOT`, `RHOBIND_DEVICE`.

## Design rationale

- Public CI has **no** delivery/GPU: science cases must skip rather than fake green.
- Do not delete `requires_delivery` or treat mocks as real scientific acceptance.
- Artifacts/caches write under `artifacts/`; tests must not require committed secrets.

## See also

[`../README.md`](../README.md) · [`../scripts/ci/README.md`](../scripts/ci/README.md) · [`AGENTS.md`](../AGENTS.md)
