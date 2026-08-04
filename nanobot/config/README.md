# nanobot/config/

Nanobot configuration loading, paths, and schema (`Config`).

[English] · [中文](README.zh.md)

> Parent package map and `$BIO_ROOT` layout: [`README.md`](../../README.md). Activate with `cd "$BIO_ROOT/nanobot-bio" && source scripts/nbio.sh`.

## Purpose

Loads `~/.nanobot/config.json` (or override path), resolves `${ENV}` placeholders, and exposes typed `Config` plus helper path getters. Product science knobs (fusion weights, thresholds) live in repo `config/*.yaml` via `app.core.runtime_config` — this package is the **framework** LLM/workspace config.

## Layout

| Module | Role |
|--------|------|
| `loader.py` | `load_config`, `save_config`, `resolve_config_env_vars`, `get_config_path` |
| `schema.py` | Pydantic / dataclass `Config` tree |
| `paths.py` | Data / workspace / cron / logs path helpers |
| `__init__.py` | Re-exports |

## Entry points

```python
from nanobot.config import load_config, get_config_path, Config, get_workspace_path
```

## Code examples

```python
from nanobot.config import load_config, get_config_path, get_workspace_path

print(get_config_path())          # usually ~/.nanobot/config.json
cfg = load_config()
print(get_workspace_path(cfg))    # workspace directory
```

```bash
nanobot-bio onboard   # writes provider/model refs; secrets in .env
```

## Dependencies / env

- Config may reference `${DEEPSEEK_API_KEY}` etc. — keep secrets out of git.
- Product YAML: [`../../config/README.md`](../../config/README.md).

## See also

[`../README.md`](../README.md) · [`../../app/core/README.md`](../../app/core/README.md) · [`INSTALL.md`](../../INSTALL.md)
