# nanobot/templates/

Bundled workspace bootstrap files and Jinja2 agent prompt templates.

[English] · [中文](README.zh.md)

## Purpose

Two roles:

1. **Workspace seeds** — root `AGENTS.md`, `SOUL.md`, `USER.md` copied into a new workspace by `nanobot.utils.helpers.sync_workspace_templates` (creates missing files only; never overwrites user edits).
2. **Prompt templates** — Markdown under `agent/` rendered by `nanobot.utils.prompt_templates.render_template` (Jinja2, `autoescape=False`). Pass names like `agent/identity.md`.

`legacy/` holds unused residue (old HEARTBEAT / memory seeds); prefer `agent/` for active prompts.

## Layout

| Path | Role |
|------|------|
| `AGENTS.md` · `SOUL.md` · `USER.md` | Workspace bootstrap seeds |
| [`agent/`](agent/README.md) | Active Jinja prompt templates + `_snippets/` |
| [`legacy/`](legacy/README.md) | Unused template residue |
| `__init__.py` | Package marker |

## Entry points

```python
from nanobot.utils.prompt_templates import render_template
from nanobot.utils.helpers import sync_workspace_templates, load_bundled_template
```

## Code examples

**Render an agent prompt template**

```python
from nanobot.utils.prompt_templates import render_template

# Name is relative to nanobot/templates/
text = render_template(
    "agent/skills_section.md",
    skills_summary="- **rbp-agent**: RNA–RBP binding workflow",
)
print(text[:200])

identity = render_template("agent/identity.md")
print("identity chars:", len(identity))
```

**Seed a workspace (missing files only)**

```python
from pathlib import Path
from nanobot.utils.helpers import sync_workspace_templates, load_bundled_template

ws = Path("/tmp/nanobot-ws-demo")
ws.mkdir(parents=True, exist_ok=True)
added = sync_workspace_templates(ws, silent=True)
print("added:", added)
print("bundled SOUL exists:", bool(load_bundled_template("SOUL.md")))
```

## Dependencies / env

- Jinja2 for `render_template`.
- Package data must ship `nanobot/templates/**` (see package packaging config).
- Product RBP skill content lives under [`../skills/`](../skills/README.md), not here.

## See also

[`../README.md`](../README.md) · [`agent/README.md`](agent/README.md) · [`../utils/README.md`](../utils/README.md) · [`../../workspace/README.md`](../../workspace/README.md)
