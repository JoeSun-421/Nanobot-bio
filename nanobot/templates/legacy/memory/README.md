# nanobot/templates/legacy/memory/

Legacy long-term memory seed (`MEMORY.md`).

[English] · [中文](README.zh.md)

## Purpose

Historical template for `memory/MEMORY.md` under the unused `templates/legacy/` tree. Runtime memory I/O is handled by `nanobot.agent.memory` against the **workspace** `memory/MEMORY.md` (created/synced by workspace helpers), not by importing this package as a module.

## Layout

| File | Role |
|------|------|
| `MEMORY.md` | Placeholder sections: User Information, Preferences, Project Context |
| `__init__.py` | Empty package marker |

## Entry points

Prefer workspace sync / memory APIs:

```python
from nanobot.utils.helpers import sync_workspace_templates
from pathlib import Path

sync_workspace_templates(Path("workspace"), silent=True)
# → may create workspace/memory/MEMORY.md (from bundled seeds when present)
```

## Code examples

```python
from pathlib import Path

seed = Path(__file__).resolve().parents[0] / "MEMORY.md"  # when reading from source tree
# Or, when developing in-repo:
seed = Path("nanobot/templates/legacy/memory/MEMORY.md")
print(seed.read_text(encoding="utf-8").splitlines()[0])
# "# Long-term Memory"
```

## Dependencies / env

- Markdown only; no runtime imports required.
- Dream / consolidator prompts that *edit* memory live under [`../../agent/`](../../agent/README.md) (`dream.md`).

## See also

[`../README.md`](../README.md) · [`../../README.md`](../../README.md) · [`../../../agent/README.md`](../../../agent/README.md)
