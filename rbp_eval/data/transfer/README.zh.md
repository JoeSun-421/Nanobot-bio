# Agent 侧 LOO 转移矩阵（实验副本）

<p><a href="README.md">English</a> · <b>中文</b></p>

本目录存放 nanobot-bio 自演进 / A–B 实验用的 **扩充 LOO 转移矩阵副本**。

- **科学 SoT** 仍在 `rhobind_agent_delivery`（勿从这里改写 SoT）。
- 填充：`nanobot-bio expand-loo-matrix`
- 优先使用本副本：

```bash
export BIO_ROOT="${BIO_ROOT:-$HOME/bio_agent}"
cd "$BIO_ROOT/nanobot-bio"
source scripts/nbio.sh
export RBP_LOO_TRANSFER_DIR="$(pwd)/rbp_eval/data/transfer"
# 可选：也指向 delivery 工具查找
export TRANSFER_DIR="$RBP_LOO_TRANSFER_DIR"
export RBP_TEST_DATA_ROOT="${RBP_TEST_DATA_ROOT:-$BIO_ROOT/rhobind_testdata_v2/rhobind_testdata_v2/test_data}"
```

## Held 选择（不限于 seed ~10）

`expand-loo-matrix` 会规划 **cohort catalogue 中凡有**
`release/.../test_data/{k562|hepg2}/<ALIAS>/test.fasta`（带 POS/NEG 标签）的 RBP。
种子 `loo_summary.csv`（~10 held）只是起始 CSV，**不限制**可打分 held 集合。

```bash
nanobot-bio expand-loo-matrix --cohort K562 --list-helds
RHOBIND_DEVICE=cuda nanobot-bio expand-loo-matrix --cohort K562 --max-seqs 256 --device cuda
nanobot-bio expand-loo-matrix --cohort K562 --skip-existing-helds
```

若 `n_held_planned` 很小，通常是 **数据缺口**：需在 release/testdata 树下补齐更多带标签的 `test.fasta`。

大 CSV 已 gitignore；`manifest.json` 记录 cohort / 断点续跑状态。

详见：[docs/guides/LOO_EXPAND.zh.md](../../../docs/guides/LOO_EXPAND.zh.md)、[rbp_eval/README.zh.md](../../README.zh.md)。
