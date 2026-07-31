# artifacts/

会话、报告、缓存与诊断的规范运行产物根目录。

[English](README.md) · [中文]

## 功能

- 所有运行产物的单一 gitignore 树（`app.core.paths`）
- 会话、PA 记忆、评估/认证报告、轨迹、缓存、日志、诊断
- 由 `workspace/sessions` 与 `workspace/memory` 符号链接，兼容 Nanobot

## 实现方法

| 子目录 | 用途 |
|--------|------|
| `sessions/` | 按本地开始日期组织的会话转录 |
| `memory/` | PA 长期记忆（`MEMORY.md` 等）；科学提示中排除 |
| `reports/json/` · `reports/md/` · `reports/csv/` | 评估 / certify / smoke / manifest 报告 |
| `traces/` | 运行与 eval 轨迹（如 jsonl） |
| `cache/` | 结构 / literature / `proxy_map.json`（proxy ≠ PA 记忆；不改 RhoBind 分） |
| `logs/` | 日志 |
| `diag/` | 诊断输出（如 AF3 setup smoke） |

由 `ensure_artifact_dirs()` / setup 创建。路径辅助：`ARTIFACTS`、`REPORTS_*`、`SESSIONS`、`report_path()` 等。

### Gitignore

见 [`.gitignore`](../.gitignore)：

```
artifacts/**
!artifacts/README.md
!artifacts/README.zh.md
```

纳入版本控制的只有这些 README；`artifacts/` 下其余内容保持本地。

### 谁在写这里？

- Agent chat / session manager
- `rbp_eval` 与 `scripts/cert/*`
- `environment_manifest.py`、`smoke_delivery_tools.py`
- setup / AF3 诊断

## 怎么使用

setup / `doctor` 后一般无需手建目录。需要时显式指定报告路径：

```bash
python -m rbp_eval.loo.loo_eval --out artifacts/reports/json/eval_loo_report.json
bash scripts/cert/certify.sh
```

评估回合优先 `ephemeral=True` 或清理对应会话文件——只改 `MEMORY.md` 不会重置 chat 复用（[`ARCHITECTURE.md`](../ARCHITECTURE.md) §2）。

## 设计思路

- 单一规范根，避免密钥、大缓存与个人会话散落进 git 树。
- 报告按 `json`/`md`/`csv` 分目录，便于机器与人各取所需。
- Proxy 缓存只是检索捷径，**不是**科学分数来源。

## 相关文档

[`../README.zh.md`](../README.zh.md) · [`../workspace/README.zh.md`](../workspace/README.zh.md) · [`ARCHITECTURE.md`](../ARCHITECTURE.md) · `app/core/paths.py`
