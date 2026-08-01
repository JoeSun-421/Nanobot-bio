# nanobot/templates/agent/

注入 Nanobot agent 循环的 Jinja2 Markdown 提示词。

[English](README.md) · [中文]

## 用途

由 `nanobot.utils.prompt_templates.render_template` 渲染的活跃提示词片段。调用方传入相对于 `nanobot/templates/` 的路径（如 `agent/identity.md`）。共享 include 在 `_snippets/`，通过 `{% include 'agent/_snippets/....md' %}` 引入。

被 `nanobot.agent.context`、`memory`、`runner`、`subagent`、cron 与 evaluator 使用。

## 布局

| 文件 | 角色 |
|------|------|
| `identity.md` | 核心身份 / 偏 RBP 的框架文案 |
| `tool_contract.md` | 工具使用契约 |
| `skills_section.md` | Skills 块（`{{ skills_summary }}`） |
| `platform_policy.md` | 平台策略片段 |
| `dream.md` · `consolidator_archive.md` | 记忆整理提示词 |
| `evaluator.md` | Evaluator 系统/用户部分 |
| `subagent_system.md` · `subagent_announce.md` | 子代理提示词 |
| `cron_reminder.md` · `max_iterations_message.md` | Cron / 迭代消息 |
| `_snippets/` | 共享 include（如 `untrusted_content.md`） |

## 入口

```python
from nanobot.utils.prompt_templates import render_template

render_template("agent/identity.md")
render_template("agent/skills_section.md", skills_summary="...")
render_template("agent/platform_policy.md", system="linux")
```

## 代码示例

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

修改模板需谨慎——它们塑造每一轮 chat 的 system prompt。

## 依赖 / 环境

- 通过 `nanobot.utils.prompt_templates` 使用 Jinja2。
- 此处无 Python `__init__.py`；作为模板数据对待。

## 相关文档

[`../README.zh.md`](../README.zh.md) · [`../../agent/README.zh.md`](../../agent/README.zh.md) · [`../../utils/README.zh.md`](../../utils/README.zh.md)
