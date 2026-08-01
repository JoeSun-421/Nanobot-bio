# nanobot/templates/legacy/

旧版 Nanobot 工作区布局遗留的未使用模板。

[English](README.md) · [中文]

## 用途

包文档字符串写明：*“Unused template residue.”* 保留历史 `HEARTBEAT.md` 与嵌套 `memory/` 种子，**不是**活跃提示词路径。当前 Jinja 提示词在 [`../agent/`](../agent/README.zh.md)；工作区引导文件在 [`../`](../README.zh.md)（`AGENTS.md` / `SOUL.md` / `USER.md`）。

不要在此新增产品提示词。

## 布局

| 路径 | 角色 |
|------|------|
| `HEARTBEAT.md` | 遗留 heartbeat cron 清单种子 |
| [`memory/`](memory/README.zh.md) | 遗留 `MEMORY.md` 种子 |
| `__init__.py` | 标记残留包 |

## 入口

产品代码无入口。请改用：

```python
from nanobot.utils.prompt_templates import render_template

render_template("agent/identity.md")  # 活跃路径
```

## 代码示例

```python
from importlib.resources import files

legacy = files("nanobot") / "templates" / "legacy" / "HEARTBEAT.md"
try:
    text = legacy.read_text(encoding="utf-8")
    print("legacy HEARTBEAT lines:", len(text.splitlines()))
except Exception as exc:
    print("not packaged or unreadable:", type(exc).__name__)
```

## 依赖 / 环境

- RBP chat / eval 不需要。
- 除非迁移仍引用 HEARTBEAT 的旧工作区，否则可忽略。

## 相关文档

[`../README.zh.md`](../README.zh.md) · [`../agent/README.zh.md`](../agent/README.zh.md) · [`memory/README.zh.md`](memory/README.zh.md)
