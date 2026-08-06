# nanobot/legacy/apps/

Legacy Nanobot “apps” protocol (manifest vocabulary). Not the RBP product path.

[English] · [中文](README.zh.md)

## Purpose

Shared helpers for settings-managed agent apps: a small descriptive manifest schema (`agent-app.v1`) used by older WebUI / registry surfaces. Installers still live in their own adapters; this package only builds compact manifest dicts. Product operators should use `nanobot-bio` / `app.cli` instead of wiring RBP through these apps.

## Layout

| Path | Role |
|------|------|
| `protocol.py` | `APP_PROTOCOL_SCHEMA`, `app_manifest`, `compact_dict` |
| `__init__.py` | Re-exports `APP_PROTOCOL_SCHEMA`, `app_manifest` |
| [`cli/`](cli/README.md) | Disabled CLI Apps manager stub + session helpers |

## Entry points

```python
from nanobot.legacy.apps import APP_PROTOCOL_SCHEMA, app_manifest
from nanobot.legacy.apps.protocol import compact_dict
```

No product CLI entry under `nanobot-bio`.

## Code examples

```python
from nanobot.legacy.apps import APP_PROTOCOL_SCHEMA, app_manifest

manifest = app_manifest(
 app_id="example.echo",
 display_name="Echo",
 description="Legacy protocol demo only",
 category="utility",
 source="local",
 capabilities=[{"name": "echo", "description": "Echo text"}],
 install={"kind": "noop"},
 remove={"kind": "noop"},
 trust={"level": "untrusted"},
 version="0.0.0",
)
assert manifest["schema"] == APP_PROTOCOL_SCHEMA # "agent-app.v1"
assert manifest["id"] == "example.echo"
print(sorted(manifest.keys())[:6])
```

```python
from nanobot.legacy.apps.protocol import compact_dict

assert compact_dict({"a": 1, "b": None, "c": "", "d": False}) == {"a": 1, "d": False}
```

## Dependencies / env

- Pure Python; not required for RBP chat / eval / certify.
- May still be imported by Nanobot framework / settings tests.

## See also

[`../README.md`](../README.md) · [`cli/README.md`](cli/README.md) · [`../../../app/cli/README.md`](../../../app/cli/README.md)
