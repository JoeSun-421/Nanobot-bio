# nanobot/security/

Workspace access policy and network safety helpers.

[English] · [中文](README.zh.md)

> Parent package map and `$BIO_ROOT` layout: [`README.md`](../../README.md). Activate with `cd "$BIO_ROOT/nanobot-bio" && source scripts/nbio.sh`.

## Purpose

Constrains what tools/channels may read or write under the workspace and applies network / SSRF-oriented guards. Important when legacy filesystem/web tools are enabled; product RBP mode still benefits from workspace policy defaults.

## Layout

| Module | Role |
|--------|------|
| `workspace_access.py` | Scope / sandbox status, `ToolWorkspace`, access modes |
| `workspace_policy.py` | `resolve_path`, `is_path_allowed`, `require_path_within` |
| `network.py` | `validate_url_target`, SSRF whitelist helpers |

## Entry points

```python
from nanobot.security.workspace_policy import resolve_path, is_path_within, require_path_within
from nanobot.security.network import validate_url_target, configure_ssrf_whitelist
from nanobot.security.workspace_access import default_workspace_scope, workspace_sandbox_status
```

`__init__.py` is intentionally minimal — import from the modules above.

## Code examples

```python
from pathlib import Path
from nanobot.security.workspace_policy import is_path_within, resolve_path

ws = Path("workspace").resolve()
target = resolve_path("notes.md", workspace=ws)
assert is_path_within(target, ws)

from nanobot.security.network import validate_url_target
ok, reason = validate_url_target("https://example.com/api")
print(ok, reason)
```

```bash
# Product path keeps science tools sandboxed via delivery subprocesses;
# layout gate forbids reintroducing broad PA surfaces:
nanobot-bio layout
```

## Dependencies / env

- Config-driven whitelist may be applied during `load_config` (see `nanobot.config.loader`).
- No science/conda dependency.

## See also

[`../README.md`](../README.md) · [`../config/README.md`](../config/README.md)
