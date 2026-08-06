# scripts/data/

delivery 操作库的幂等重建辅助脚本。

[English](README.md) · [中文]

## 功能

- 从原始蛋白/结构/benchmark 源重建 `agent_db/`（registry、embedding bank、foldseek、mmseqs、可选 peaks）
- 幂等：输出比输入新则跳过；`--force` 强制重建
- 不改 delivery 应用源码——调用 delivery `agent/database/build/` 下的构建脚本

## 实现方法

| 文件 | 作用 |
|------|------|
| `bootstrap_data.sh` | 编排：embedding bank → foldseek DB → mmseqs seq DB → `rbp_registry.json` → peaks DB（可选） |

仓库根 / delivery 根由 `$SCRIPT_DIR/../..` 与 `BIO_ROOT` / `DELIVERY_ROOT` 解析。步骤说明见 delivery `agent/database/SOURCES.md`。

前置条件：

- conda：`protein_embed`（foldseek / ESM）、`rna`（mmseqs）
- 原始 bundle `RB`、benchmark 结果、head index 目录可读
- peaks 步需要 `PROCESSED_ROOT`（默认 `$RB/../processed_260417`）或 `--skip-peaks`

## 怎么使用

```bash
bash scripts/data/bootstrap_data.sh \
 --rb /path/to/rbp_proteins_260417 \
 --benchmarks /path/to/results/benchmark_cluster \
 --head-index-dir /path/to/head_index_dir \
 --out /path/to/agent_db

# 可选：
# --force
# --skip-peaks
# --skip-embeddings
```

运行时通过 `AGENT_DB` / delivery env 指向重建库（见 [`INSTALL.md`](../../INSTALL.md)）。

## 设计思路

- 操作库重建是运维职责，不是 chat 逻辑——放在 `scripts/data/`。
- 幂等便于大机器反复跑。
- peaks 可跳过；融合权重在消融 promote 前保持 `0`（[`config/README.zh.md`](../../config/README.zh.md)）。

## 相关文档

[`../README.zh.md`](../README.zh.md) · [`INSTALL.md`](../../INSTALL.md) · [`../../app/backends/delivery/README.zh.md`](../../app/backends/delivery/README.zh.md)
