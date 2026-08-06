# nanobot/legacy/

Quarantined non-product Nanobot subsystems (legacy apps / CLI).

[English] · [中文](README.zh.md)

## Purpose

Holds older Nanobot app/CLI surfaces that are not the nanobot-bio product path. Kept importable for framework continuity; product operators should use `nanobot-bio` / `app.cli` instead.

## Layout

| Path | Role |
|------|------|
| `__init__.py` | Package marker |
| [`apps/`](apps/README.md) · [`apps/cli/`](apps/cli/README.md) | Legacy app/CLI packages |

## Entry points

Prefer:

```bash
nanobot-bio --help
python -m app --help
```

Not:

```bash
# Avoid relying on nanobot.legacy.apps for RBP product work
```

## Code examples

```python
import nanobot.legacy
print(nanobot.legacy.__doc__)
```

```bash
nanobot-bio layout # asserts product SoT; PA surfaces constrained
```

## Dependencies / env

- Not required for RBP chat / eval / certify.
- May still be imported by framework tests.

## See also

[`../README.md`](../README.md) · [`../../app/cli/README.md`](../../app/cli/README.md)
