# rbp_eval/loo/

Leave-one-out：轻量 LOO、heavy hide-own-head、矩阵扩充与 A/B。

[English](README.md) · [中文]

## 用途

衡量隐藏 catalogue head 后的迁移表现。Agent 侧矩阵扩充**不改** delivery SoT；自演进请 `export RBP_LOO_TRANSFER_DIR=...`。

## 模块



## 通用布局（Linux）

```bash
export BIO_ROOT="${BIO_ROOT:-$HOME/bio_agent}"
cd "$BIO_ROOT/nanobot-bio"
source scripts/nbio.sh
```

| 模块 | 角色 |
|------|------|
| `loo_eval.py` | 轻量 LOO / CSV 解析 |
| `heavy_loo.py` | Heavy LOO + `test_fasta_for`（支持 `RBP_TEST_DATA_ROOT`） |
| `batch_score_held.py` | 单进程 encode 一次 × 全 heads |
| `expand_matrix.py` | 扩充 agent 侧 LOO 矩阵 |
| `matrix_ab_eval.py` | delivery vs 扩展矩阵 A/B |

用法见 [`../../docs/guides/LOO_EXPAND.zh.md`](../../docs/guides/LOO_EXPAND.zh.md)。
