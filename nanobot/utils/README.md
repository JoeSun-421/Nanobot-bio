# nanobot/utils/

Shared framework utilities (paths, helpers, artifacts, logging bridges, …).

[English] · [中文](README.zh.md)

> Parent package map and `$BIO_ROOT` layout: [`README.md`](../../README.md). Activate with `cd "${NANOBOT_BIO_ROOT:-$BIO_ROOT/Nanobot-bio}" && source scripts/nbio.sh`.

## Purpose

Small helpers used across Nanobot modules. Product artifact *canonical roots* for nanobot-bio are owned by `app.core.paths`; this package still provides framework-level helpers (`ensure_dir`, `abbreviate_path`, gitstore, progress events, etc.).

## Layout

| Module | Role |
|--------|------|
| `helpers.py` | General helpers (`ensure_dir`, …) |
| `path.py` | Path abbreviation / utils |
| `artifacts.py` | Artifact helpers |
| `runtime.py` / `llm_runtime.py` | Runtime helpers |
| `gitstore.py` | Git-backed store helpers |
| `progress_events.py` / `file_edit_events.py` | Event helpers |
| `document.py` / `media_decode.py` / `tool_hints.py` / … | Misc utilities |

## Entry points

```python
from nanobot.utils import ensure_dir, abbreviate_path
```

## Code examples

```python
from pathlib import Path
from nanobot.utils import ensure_dir, abbreviate_path

p = ensure_dir(Path("artifacts/logs"))
print(abbreviate_path(p))
```

```python
# Product canonical dirs — prefer app.core.paths:
from app.core.paths import ensure_artifact_dirs
ensure_artifact_dirs()
```

## Dependencies / env

- Framework-only for most helpers.
- Do not confuse with `app.core.paths` (product artifact authority).

## See also

[`../README.md`](../README.md) · [`../../app/core/README.md`](../../app/core/README.md) · [`../../artifacts/README.md`](../../artifacts/README.md)
