# scripts/ci/

Lightweight CI / local engineering gates (secret scan needs no GPU science).

[English] · [中文](README.zh.md)

> Parent package map and `$BIO_ROOT` layout: [`README.md`](../../README.md). Activate with `cd "${NANOBOT_BIO_ROOT:-$BIO_ROOT/Nanobot-bio}" && source scripts/nbio.sh`.

## Features

- Scan tracked files for private-key / API-key shaped secrets before merge
- Thin wrapper that activates `.venv` (if present) and runs `python -m app gate`
- Used by GitHub Actions and local pre-merge checks

## Implementation

| Script | Role |
|--------|------|
| `check_secrets.sh` | Scan **git-tracked** files (or common source roots when not a git checkout); nonzero exit on hits. Does not read/print real keys from `~/.nanobot/config.json` — only permission / accidental track checks |
| `ci_gate.sh` | `exec python -m app gate …` (`nanobot-bio gate` / `rbp-agent gate`) |

Repo root: `$SCRIPT_DIR/../..`. `check_secrets` skips locks, binaries, `artifacts/`, and lines with `example` / `placeholder`.

Workflow: [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml) `check_secrets` job calls `scripts/ci/check_secrets.sh`.

## How to use

```bash
bash scripts/ci/check_secrets.sh
bash scripts/ci/ci_gate.sh
bash scripts/ci/ci_gate.sh --skip-eval
bash scripts/ci/ci_gate.sh --no-cov
```

For full science acceptance without LLM keys, use [`../cert/`](../cert/README.md) or local `rbp-agent gate` with delivery present.

## Design rationale

- Public CI often lacks delivery/GPU; keep a fast secret + engineering gate separate from heavy certify.
- Prefer scanning tracked files so CI matches what would be published.
- If `~/.nanobot/config.json` exists locally, `chmod 600`; never `git add -f` it.

## See also

[`../README.md`](../README.md) · [`../../tests/README.md`](../../tests/README.md) · [`INSTALL.md`](../../INSTALL.md)
