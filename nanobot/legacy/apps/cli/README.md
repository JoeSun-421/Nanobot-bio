# nanobot/legacy/apps/cli/

Legacy CLI Apps adapter — catalog/runner stub is disabled.

[English] · [中文](README.zh.md)

## Purpose

Slim vendor stub for the unified Apps domain’s CLI surface. `CliAppManager` always reports no installed apps; helpers extract `@app` session metadata lines for older agent loops. This is **not** used by the RBP product CLI (`nanobot-bio` / `app.cli`).

## Layout

| Module | Role |
|--------|------|
| `service.py` | `CliAppError`, `CliAppsRuntimeConfig`, `CliAppManager` (empty catalog) |
| `utils.py` | `session_extra`, `runtime_lines` for model-visible annotations |
| `__init__.py` | Re-exports service types |

## Entry points

```python
from nanobot.legacy.apps.cli import CliAppManager, CliAppError, CliAppsRuntimeConfig
from nanobot.legacy.apps.cli.utils import session_extra, runtime_lines
```

## Code examples

```python
from pathlib import Path
from nanobot.legacy.apps.cli import CliAppManager, CliAppsRuntimeConfig

mgr = CliAppManager(workspace=Path("."), runtime=CliAppsRuntimeConfig(run_timeout=30))
assert mgr.installed_names() == []
assert mgr.mentioned_installed_apps("@echo hello") == []
```

```python
from nanobot.legacy.apps.cli.utils import session_extra

assert session_extra({"cli_apps": [{"name": "echo"}]}) == {
    "cli_apps": [{"name": "echo"}]
}
assert session_extra({}) == {}
```

## Dependencies / env

- Pure Python stub; installing “CLI apps” via this manager is a no-op.
- Prefer product tools under `nanobot/agent/tools/rbp/` for RBP workflows.

## See also

[`../README.md`](../README.md) · [`../../README.md`](../../README.md) · [`../../../../app/cli/README.md`](../../../../app/cli/README.md)
