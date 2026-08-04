# app/bootstrap/

SoT 定位、workspace skill 同步、RBP 工具安装辅助。

**不** import `app.agent`，避免 registry ↔ agent 循环。

| 模块 | 角色 |
|------|------|
| `sot.py` | `sot_root` / `skill_md` / `tools_rbp` |
| `sync_overlay.py` | 链到 `workspace/skills/rbp-agent` |
| `rbp_bootstrap.py` | `install_rbp_tools_into_nanobot` |

唯一根级兼容入口：`python -m app.sync_overlay`（薄 re-export）。新代码请 `from app.bootstrap import …`。
