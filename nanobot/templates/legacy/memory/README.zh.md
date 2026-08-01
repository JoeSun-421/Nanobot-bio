# nanobot/templates/legacy/memory/

遗留长期记忆种子（`MEMORY.md`）。

[English](README.md) · [中文]

## 用途

未使用的 `templates/legacy/` 树中历史 `memory/MEMORY.md` 模板。运行时记忆 I/O 由 `nanobot.agent.memory` 针对**工作区** `memory/MEMORY.md` 完成（由工作区辅助创建/同步），不要把本目录当模块导入。

## 布局

| 文件 | 角色 |
|------|------|
| `MEMORY.md` | 占位分区：User Information、Preferences、Project Context |
| `__init__.py` | 空包标记 |

## 入口

优先使用工作区同步 / memory API：

```python
from nanobot.utils.helpers import sync_workspace_templates
from pathlib import Path

sync_workspace_templates(Path("workspace"), silent=True)
# → 在捆绑种子存在时可能创建 workspace/memory/MEMORY.md
```

## 代码示例

```python
from pathlib import Path

seed = Path("nanobot/templates/legacy/memory/MEMORY.md")
print(seed.read_text(encoding="utf-8").splitlines()[0])
# "# Long-term Memory"
```

## 依赖 / 环境

- 仅 Markdown；无需运行时导入。
- 负责*编辑*记忆的 dream / consolidator 提示词在 [`../../agent/`](../../agent/README.zh.md)（`dream.md`）。

## 相关文档

[`../README.zh.md`](../README.zh.md) · [`../../README.zh.md`](../../README.zh.md) · [`../../../agent/README.zh.md`](../../../agent/README.zh.md)
