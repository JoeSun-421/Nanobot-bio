# nanobot/session/

会话持久化与回合续写辅助。

[English](README.md) · [中文]

> 包地图与 `$BIO_ROOT` 布局见仓库根 [`README.zh.md`](../../README.zh.md)。激活：`cd "$BIO_ROOT/nanobot-bio" && source scripts/nbio.sh`。

## 用途

拥有 `Session` / `SessionManager` 以存储对话状态。在 nanobot-bio 中，规范会话文件位于 `artifacts/sessions/`（workspace 有符号链接）——见 [`docs/guides/MEMORY_AND_SESSIONS.zh.md`](../../docs/guides/MEMORY_AND_SESSIONS.zh.md) 与 [`ARCHITECTURE.md`](../../ARCHITECTURE.md) §2。

## 布局

| 模块 | 角色 |
|------|------|
| `manager.py` | `Session`、`SessionManager` |
| `keys.py` | 会话 key 辅助 |
| `goal_state.py` | 目标状态跟踪 |
| `turn_continuation.py` | 多轮续写 |
| `webui_turns.py` | 遗留 WebUI 回合辅助 |

## 入口

```python
from nanobot.session import SessionManager, Session
```

## 代码示例

```python
from nanobot import Nanobot
from app.core.paths import SESSIONS, ensure_artifact_dirs

ensure_artifact_dirs()
print("canonical sessions dir:", SESSIONS)

bot = Nanobot.from_config(workspace="workspace", scientific_mode=True)
print(bot.sessions)
```

```bash
ls artifacts/sessions/
nanobot-bio chat
```

## 依赖 / 环境

- 磁盘路径为包内 `artifacts/sessions`（经 `app.core.paths`）。
- 临时回合（`ephemeral=True`）避免污染长寿命科学会话。

## 相关文档

[`../README.zh.md`](../README.zh.md) · [`../../artifacts/README.zh.md`](../../artifacts/README.zh.md) · [`../../docs/guides/MEMORY_AND_SESSIONS.zh.md`](../../docs/guides/MEMORY_AND_SESSIONS.zh.md)
