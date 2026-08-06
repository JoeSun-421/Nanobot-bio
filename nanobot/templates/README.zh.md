# nanobot/templates/

捆绑的工作区引导文件与 Jinja2 agent 提示词模板。

[English](README.md) · [中文]

## 用途

两类职责：

1. **工作区种子** — 根目录 `AGENTS.md`、`SOUL.md`、`USER.md`，由 `nanobot.utils.helpers.sync_workspace_templates` 复制到新工作区（只创建缺失文件，不覆盖用户修改）。
2. **提示词模板** — `agent/` 下 Markdown，经 `nanobot.utils.prompt_templates.render_template` 渲染（Jinja2，`autoescape=False`）。名称形如 `agent/identity.md`。

`legacy/` 为未使用残留（旧 HEARTBEAT / memory 种子）；活跃提示词请用 `agent/`。

## 布局

| 路径 | 角色 |
|------|------|
| `AGENTS.md` · `SOUL.md` · `USER.md` | 工作区引导种子 |
| [`agent/`](agent/README.zh.md) | 活跃 Jinja 提示词 + `_snippets/` |
| [`legacy/`](legacy/README.zh.md) | 未使用模板残留 |
| `__init__.py` | 包标记 |

## 入口

```python
from nanobot.utils.prompt_templates import render_template
from nanobot.utils.helpers import sync_workspace_templates, load_bundled_template
```

## 代码示例

**渲染 agent 提示词模板**

```python
from nanobot.utils.prompt_templates import render_template

# 名称相对于 nanobot/templates/
text = render_template(
 "agent/skills_section.md",
 skills_summary="- **rbp-agent**: RNA–RBP binding workflow",
)
print(text[:200])

identity = render_template("agent/identity.md")
print("identity chars:", len(identity))
```

**引导工作区（仅缺失文件）**

```python
from pathlib import Path
from nanobot.utils.helpers import sync_workspace_templates, load_bundled_template

ws = Path("/tmp/nanobot-ws-demo")
ws.mkdir(parents=True, exist_ok=True)
added = sync_workspace_templates(ws, silent=True)
print("added:", added)
print("bundled SOUL exists:", bool(load_bundled_template("SOUL.md")))
```

## 依赖 / 环境

- `render_template` 需要 Jinja2。
- 打包需包含 `nanobot/templates/**`。
- 产品 RBP skill 内容在 [`../skills/`](../skills/README.zh.md)，不在此处。

## 相关文档

[`../README.zh.md`](../README.zh.md) · [`agent/README.zh.md`](agent/README.zh.md) · [`../utils/README.zh.md`](../utils/README.zh.md) · [`../../workspace/README.zh.md`](../../workspace/README.zh.md)
