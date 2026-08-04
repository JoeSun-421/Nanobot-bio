# app/cli/

Argparse product CLI for `nanobot-bio` / `rbp-agent`.

[English] · [中文](README.zh.md)

## Purpose

This package is the thin, stable command surface shared by console scripts and `python -m app`. Handlers stay grouped so daily chat, scientific acceptance, offline evolve, and engineering gates can evolve independently without renaming public commands. Science scoring is never implemented here — handlers delegate to `app.agent`, `rbp_eval.*`, `app.dev.*`, or delivery.

## Layout



## Portable layout (Linux)

```bash
export BIO_ROOT="${BIO_ROOT:-$HOME/bio_agent}"
cd "$BIO_ROOT/nanobot-bio"
source scripts/nbio.sh
```

| File | Domain (stable command names) |
|------|-------------------------------|
| `parser.py` | Builds argparse; **names stay stable** |
| `user.py` | `doctor`, `onboard`, `nanobot-smoke`, `agent`, `chat` |
| `accept.py` | `own-head` / `accept-golden`, `accept-llm`, `gap-closure` |
| `eval_cmds.py` | `run-eval`, `heavy-loo`, `evolve*`, `eval-plan`, `promote-evolved` |
| `maint.py` | `gate`, `layout`, `mvp`, `compliance` |
| `common.py` | Env / `sys.path` bootstrap (import has intentional side effects) |
| `__init__.py` | `main()`, `build_parser()` — `[project.scripts]` target |
| `__main__.py` | `python -m app.cli` |

## Entry points

```bash
nanobot-bio --help
python -m app --help
python -m app.cli --help
```

```python
from app.cli import main, build_parser

raise SystemExit(main(["doctor"]))
# or inspect flags:
build_parser().print_help()
```

## Code examples

**Daily user path**

```bash
source scripts/nbio                 # optional daily activate helper
nanobot-bio doctor                  # capability table; --verbose for path dumps
nanobot-bio onboard                 # interactive LLM setup
nanobot-bio chat                    # multi-turn
nanobot-bio agent --example --query "Does PTBP1 bind this RNA?"
```

**Acceptance / eval / maint**

```bash
nanobot-bio own-head                # delivery own-head (no LLM)
nanobot-bio accept-llm
nanobot-bio run-eval
nanobot-bio heavy-loo
nanobot-bio evolve --dry-run
nanobot-bio gate                    # engineering: ruff + pytest + layout
bash scripts/ci/ci_gate.sh          # → python -m app gate
```

**Notable flags** (`parser.py` / `user.py`):

- `agent` / `chat`: `--device auto|cuda|cpu`, `--query`, `--rna-file`, `--example`
- `onboard`: `--provider` / `--model` / `--key` (keys in `.env`; config keeps `${VAR}` refs)
- `gate`: engineering only — see [`../dev/`](../dev/README.md)

Certification orchestration: [`scripts/cert/certify.sh`](../../scripts/cert/README.md).

## Dependencies / env

- Same as [`app/`](../README.md): editable install, optional delivery for science commands.
- Importing `app.cli.common` bootstraps paths intentionally — keep that side effect when embedding `main()`.

## Design rationale

- Thin argparse so product UX can change without forcing Nanobot API churn.
- Split user / accept / eval / maint so CI can call maint without loading chat UX.
- Never invent scores in the CLI layer.

## See also

[`../README.md`](../README.md) · [`../dev/README.md`](../dev/README.md) · [`INSTALL.md`](../../INSTALL.md) · [`../../docs/product/BINDING_PREDICTION_FLOW.zh.md`](../../docs/product/BINDING_PREDICTION_FLOW.zh.md) · [`../../scripts/ci/README.md`](../../scripts/ci/README.md)
