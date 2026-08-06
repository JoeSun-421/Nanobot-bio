# workspace/

Nanobot 工作区根：同步的 skill 与（符号链接的）session/memory 视图。

[English](README.md) · [中文]

## 功能

- Nanobot 期望的运行时工作区（`NANOBOT_WORKSPACE`）
- `skills/` 下的同步 skill 副本（见 [`skills/README.zh.md`](skills/README.zh.md)）


## 通用布局（Linux）

```bash
export BIO_ROOT="${BIO_ROOT:-$HOME/bio_agent}"
# 检出目录常见为 Nanobot-bio（GitHub）；小写 nanobot-bio 亦可。
cd "${NANOBOT_BIO_ROOT:-$BIO_ROOT/Nanobot-bio}"
source scripts/nbio.sh
```

- `sessions` → `../artifacts/sessions`、`memory` → `../artifacts/memory`（避免双写）
- `AGENTS.md` 中的工作区级短提示

## 实现方法

| 路径 | 说明 |
|------|------|
| `skills/rbp-agent/` | 由 `python -m app.sync_overlay` 从 SoT 同步；勿当长期编辑源 |
| `sessions` → `../artifacts/sessions` | 会话转录符号链接 |
| `memory` → `../artifacts/memory` | PA 长期记忆符号链接（科学提示中排除） |
| `AGENTS.md` | 工作区级短提示（阶段 0 own-head 等） |

规范存储与辅助：`app.core.paths.ensure_artifact_dirs()`。细节见 [`ARCHITECTURE.md`](../ARCHITECTURE.md) §2（细节见 ARCHITECTURE §2）。

环境变量：

- `NANOBOT_WORKSPACE` 默认 `$NANOBOT_BIO_ROOT/workspace`
- 会话/记忆字节仍落在 `artifacts/`

`.gitignore` 忽略 `workspace/memory/*`、`workspace/.nanobot/` 等。

## 怎么使用

```bash
export NANOBOT_WORKSPACE=$PWD/workspace # 通常由 setup / 默认设置
python -m app.sync_overlay
nanobot-bio chat
```

请编辑 SoT：`nanobot/skills/rbp-agent/SKILL.md`，再 sync——不要把工作区副本当成唯一源。

## 设计思路

- Nanobot 历史上需要 workspace 目录；`artifacts/` 仍是**规范**存储，大文件/敏感输出集中 gitignore。
- 符号链接避免 session/memory 双份拷贝。
- Overlay 同步让运行副本与仓内 SoT 对齐，且不引入第三套 tools 树。

## 相关文档

[`skills/README.zh.md`](skills/README.zh.md) · [`../artifacts/README.zh.md`](../artifacts/README.zh.md) · [`../nanobot/README.zh.md`](../nanobot/README.zh.md) · [`ARCHITECTURE.md`](../ARCHITECTURE.md)
