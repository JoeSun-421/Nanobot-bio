# app/bootstrap/

SoT 定位、workspace skill 同步、RBP 工具安装辅助。

**不** import `app.agent`，避免 registry ↔ agent 循环。

[English](README.md) · [中文]

## 模块

| 模块 | 角色 |
|------|------|
| `sot.py` | `sot_root` / `skill_md` / `tools_rbp` |
| `sync_overlay.py` | 链到 `workspace/skills/rbp-agent` |
| `rbp_bootstrap.py` | `install_rbp_tools_into_nanobot` |

唯一根级兼容入口：`python -m app.sync_overlay`（薄 re-export）。新代码请 `from app.bootstrap import …`。

## 用法

```bash
export BIO_ROOT="${BIO_ROOT:-$HOME/bio_agent}"
cd "${NANOBOT_BIO_ROOT:-$BIO_ROOT/Nanobot-bio}"
source scripts/nbio.sh

# 编辑 nanobot/skills/rbp-agent 或 nanobot/agent/tools/rbp 之后：
python -m app.sync_overlay
nanobot-bio doctor
```

## 参见

[`../README.zh.md`](../README.zh.md) · [`../../nanobot/skills/rbp-agent/README.zh.md`](../../nanobot/skills/rbp-agent/README.zh.md) · [`../../workspace/skills/README.zh.md`](../../workspace/skills/README.zh.md)
