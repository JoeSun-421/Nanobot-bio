# app/dev/

Engineering maturity gates only (C5 boundary). Fast checks that do **not** replace scientific acceptance under `rbp_eval.accept.*`.

[English] · [中文](README.zh.md)

## Purpose

This package answers: “Is the product tree wired correctly for CI and collaborators?” It runs ruff / pytest / SoT layout / MVP structural acceptance. Scientific scores (own-head AUPRC, transfer calibration, promote evidence) belong in [`rbp_eval/`](../../rbp_eval/README.md) and the `accept-*` / `promote-evolved` CLI commands — do not add science scoring paths here.

> Parent package map and `$BIO_ROOT` layout: [`README.md`](../../README.md). Activate with `cd "${NANOBOT_BIO_ROOT:-$BIO_ROOT/Nanobot-bio}" && source scripts/nbio.sh`.

## Layout

| Module | Role |
|--------|------|
| `gate.py` | `run_gate()` — ruff + pytest + layout (+ optional light eval asserts) |
| `layout.py` | Assert in-repo `nanobot/` SoT layout; forbid PA surfaces |
| `mvp.py` | Agent-Owner MVP levels A–F (engineering structure, may call `Nanobot.run`) |
| `compliance.py` | Delivery-path / SoT compliance self-check |

## Entry points

```bash
nanobot-bio gate
nanobot-bio layout
nanobot-bio mvp
nanobot-bio compliance
# equivalents:
python -m app gate
python -m app.dev.layout
bash scripts/ci/ci_gate.sh
```

```python
from app.dev.gate import run_gate
from app.dev.layout import main as layout_main

raise SystemExit(run_gate(light_eval=False))
```

## Code examples

**Run the engineering gate programmatically**

```python
from app.dev.gate import run_gate, delivery_loo_ready

# Full CI-style gate (ruff + pytest + layout)
rc = run_gate()
assert rc == 0

# Optional: only assert LOO report shape when delivery is ready
if delivery_loo_ready():
 from app.dev.gate import assert_loo_report
 assert_loo_report()
```

**Layout assertion (SoT)**

```bash
# Fails if required RBP tools missing or forbidden PA surfaces reappear
python -m app.dev.layout
# or:
nanobot-bio layout
```

## Dependencies / env

- Needs project `.venv` / editable install for ruff + pytest.
- `mvp` may need LLM credentials for levels that call `Nanobot.run`.
- Does **not** require science conda for `gate` / `layout` / `compliance` by default; light eval asserts are optional when delivery LOO artifacts exist.

## See also

[`../README.md`](../README.md) · [`../cli/README.md`](../cli/README.md) · [`../../scripts/ci/README.md`](../../scripts/ci/README.md) · [`../../AGENTS.md`](../../AGENTS.md)
