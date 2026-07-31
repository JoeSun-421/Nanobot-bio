# app/cli/

Argparse product CLI for `nanobot-bio` / `rbp-agent`.

[English] · [中文](README.zh.md)

## Features

- Stable command surface shared by console scripts and `python -m app`
- Grouped handlers: daily user commands, acceptance, offline eval/evolve, engineering maint
- Shared bootstrap in `common.py` (env / `sys.path` / path helpers)

## Implementation

| File | Domain (stable names) |
|------|------------------------|
| `parser.py` | Builds argparse; **command names stay stable** |
| `user.py` | `agent`, `chat`, `onboard`, `doctor`, `nanobot-smoke` |
| `accept.py` | `accept-golden` / `own-head`, `accept-llm`, `gap-closure` |
| `eval_cmds.py` | `run-eval`, `heavy-loo`, `evolve*`, `eval-plan`, `promote-evolved` |
| `maint.py` | `gate`, `layout`, `mvp`, `compliance` |
| `common.py` | Env / path bootstrap (import has intentional side effects) |
| `__init__.py` | `main()` entry used by `pyproject` scripts |

Entry wiring: `[project.scripts]` in `pyproject.toml` → `app.cli:main`.

## How to use

```bash
nanobot-bio --help
nanobot-bio doctor              # capability table; --verbose for path dumps
source scripts/nbio             # daily activate (see scripts/nbio)
python -m app chat
bash scripts/ci/ci_gate.sh          # → python -m app gate
```

Notable flags:

- `agent` / `chat`: `--device auto|cuda|cpu`, `--query` / `--rna-file` / `--example`
- `onboard`: interactive or `--provider` / `--model` / `--key` (keys land in `.env`, config keeps `${VAR}` refs)
- `gate`: engineering gate (ruff + pytest + layout); see `scripts/ci/`

Certification orchestration lives in [`scripts/cert/certify.sh`](../../scripts/cert/README.md) (calls doctor / accept modules).

## Design rationale

- Keep a thin argparse layer so product UX changes do not force Nanobot API churn.
- Split user / accept / eval / maint modules so CI can call maint/accept without loading chat UX.
- Do not bake science scores here — handlers delegate to `app.agent`, `rbp_eval.*`, or delivery.

## See also

[`../README.md`](../README.md) · [`INSTALL.md`](../../INSTALL.md) · [`../../scripts/ci/README.md`](../../scripts/ci/README.md)
