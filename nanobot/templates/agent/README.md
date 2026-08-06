# nanobot/templates/agent/

Jinja2 Markdown prompts injected into the Nanobot agent loop.

[English] · [中文](README.zh.md)

## Purpose

Active prompt fragments rendered by `nanobot.utils.prompt_templates.render_template`. Callers pass paths relative to `nanobot/templates/` (e.g. `agent/identity.md`). Shared includes live under `_snippets/` and are pulled in with `{% include 'agent/_snippets/....md' %}`.

Consumed by `nanobot.agent.context`, `memory`, `runner`, `subagent`, cron, and the evaluator.

## Layout

| File | Role |
|------|------|
| `identity.md` | Core agent identity / RBP-oriented framing |
| `tool_contract.md` | Tool-use contract text |
| `skills_section.md` | Skills block (`{{ skills_summary }}`) |
| `platform_policy.md` | Platform policy snippet |
| `dream.md` · `consolidator_archive.md` | Memory consolidation prompts |
| `evaluator.md` | Evaluator system/user parts |
| `subagent_system.md` · `subagent_announce.md` | Subagent prompts |
| `cron_reminder.md` · `max_iterations_message.md` | Cron / iteration messages |
| `_snippets/` | Shared includes (e.g. `untrusted_content.md`) |

## Entry points

```python
from nanobot.utils.prompt_templates import render_template

render_template("agent/identity.md")
render_template("agent/skills_section.md", skills_summary="...")
render_template("agent/platform_policy.md", system="linux")
```

## Code examples

```python
from nanobot.utils.prompt_templates import render_template

contract = render_template("agent/tool_contract.md")
assert "tool" in contract.lower() or len(contract) > 100

skills = render_template(
 "agent/skills_section.md",
 skills_summary="- **rbp-agent**: always-on RNA–RBP skill",
)
assert "rbp-agent" in skills

policy = render_template("agent/platform_policy.md", system="linux", strip=True)
print(policy[:160])
```

Edit templates carefully — they shape every chat turn’s system prompt.

## Dependencies / env

- Jinja2 via `nanobot.utils.prompt_templates`.
- No Python package `__init__.py` here; treated as template data.

## See also

[`../README.md`](../README.md) · [`../../agent/README.md`](../../agent/README.md) · [`../../utils/README.md`](../../utils/README.md)
