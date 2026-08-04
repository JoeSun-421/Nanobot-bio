# nanobot/utils/

共享框架工具函数（路径、helpers、artifacts、日志桥等）。

[English](README.md) · [中文]

> 包地图与 `$BIO_ROOT` 布局见仓库根 [`README.zh.md`](../../README.zh.md)。激活：`cd "$BIO_ROOT/nanobot-bio" && source scripts/nbio.sh`。

## 用途

供 Nanobot 各模块使用的小工具。nanobot-bio 产品侧 artifact **规范根目录**由 `app.core.paths` 拥有；本包仍提供框架级辅助（`ensure_dir`、`abbreviate_path`、gitstore、进度事件等）。

## 布局

| 模块 | 角色 |
|------|------|
| `helpers.py` | 通用辅助（`ensure_dir` 等） |
| `path.py` | 路径缩写 / 工具 |
| `artifacts.py` | Artifact 辅助 |
| `runtime.py` / `llm_runtime.py` | 运行时辅助 |
| `gitstore.py` | Git 存储辅助 |
| `progress_events.py` / `file_edit_events.py` | 事件辅助 |
| `document.py` / `media_decode.py` / `tool_hints.py` / … | 杂项 |

## 入口

```python
from nanobot.utils import ensure_dir, abbreviate_path
```

## 代码示例

```python
from pathlib import Path
from nanobot.utils import ensure_dir, abbreviate_path

p = ensure_dir(Path("artifacts/logs"))
print(abbreviate_path(p))
```

```python
from app.core.paths import ensure_artifact_dirs
ensure_artifact_dirs()
```

## 依赖 / 环境

- 多数辅助仅框架依赖。
- 勿与 `app.core.paths`（产品 artifact 权威）混淆。

## 相关文档

[`../README.zh.md`](../README.zh.md) · [`../../app/core/README.zh.md`](../../app/core/README.zh.md) · [`../../artifacts/README.zh.md`](../../artifacts/README.zh.md)
