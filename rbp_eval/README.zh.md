# rbp_eval/

离线科学评估、LOO、融合打分、验收与自演化。

[English](README.md) · [中文]

## 用途

本包是 nanobot-bio 的离线科学实验室：测量 own-head / LOO 上限、融合多视图命中、校准 transfer，并跑写入 `config/evolved.candidate.yaml` 的门禁自演化。它刻意**不在 chat 热路径上**——交互 UX 留在 `app/` + `nanobot/`。物理路径 = import 路径（无 facade）；使用 `python -m rbp_eval.<subpkg>.<module>`。

Chat 绑定产品流：[rbp-agent SKILL.md](../nanobot/skills/rbp-agent/SKILL.md)。演化政策：[`evolve/README.zh.md`](evolve/README.zh.md)。

## 布局

| 子包 | 角色 |
|------|------|
| [`scoring/`](scoring/README.zh.md) | 命中融合（`fuse_hits.py`）、head index、指标 |
| [`loo/`](loo/README.zh.md) | 轻量 LOO + 重型 hide-own-head |
| [`accept/`](accept/README.zh.md) | own-head、transfer 校准、release 指标、LLM 验收、gap closure |
| [`evolve/`](evolve/README.zh.md) | runner、orchestrator、promote、retune、proxy cache |
| [`runtime/`](runtime/README.zh.md) | 评估 hooks / trace schema |
| [`rna/`](rna/README.zh.md) | RNA 轴门禁辅助 |
| [`plans/`](plans/README.zh.md) | Evaluation plan / faithfulness 报告 |

报告默认写入 `artifacts/reports/{json,md,csv}/`（经 `app.core.paths`）。

配置（[`ARCHITECTURE.md`](../ARCHITECTURE.md) §5）：

- 默认：`config/defaults.yaml`
- 候选：`config/evolved.candidate.yaml`（gitignore）
- 已提升：`config/evolved.yaml`（`evolved: true` 时 deep-merge）

## 自演进（摘要）

政策与五步：[自演进 (evolve)](evolve/README.zh.md)。 
矩阵扩充：[LOO 扩充](loo/README.zh.md)。

```bash
export BIO_ROOT="${BIO_ROOT:-$HOME/bio_agent}"
cd "${NANOBOT_BIO_ROOT:-$BIO_ROOT/Nanobot-bio}" && source scripts/nbio.sh
export RHOBIND_RELEASE="${RHOBIND_RELEASE:-$DELIVERY_ROOT/release/rhobind_release_v1}"
export RBP_TEST_DATA_ROOT="${RBP_TEST_DATA_ROOT:-$BIO_ROOT/rhobind_testdata_v2/rhobind_testdata_v2/test_data}"
nanobot-bio expand-loo-matrix --cohort K562 --max-seqs 256 --skip-existing-helds
export RBP_LOO_TRANSFER_DIR="$(pwd)/rbp_eval/data/transfer"
nanobot-bio evolve --transfer-dir "$RBP_LOO_TRANSFER_DIR" --medoids --max-seqs 64 \
 --collect-agent-traces --require-traces
nanobot-bio run-eval --medoids --transfer-dir "$RBP_LOO_TRANSFER_DIR" \
 --policy config/evolved.candidate.yaml --max-seqs 64
nanobot-bio review-toolkit-proposals --list
nanobot-bio promote-evolved
```



## 入口

```bash
python -m rbp_eval
nanobot-bio run-eval|heavy-loo|evolve|promote-evolved|review-toolkit-proposals|eval-plan|own-head
```



## 代码示例

```bash
python -m rbp_eval.loo.loo_eval --out artifacts/reports/json/eval_loo_report.json
python -m rbp_eval.accept.own_head
python -m rbp_eval.accept.transfer_calibration --regime both
python -m rbp_eval.evolve.runner --evolve
python -m rbp_eval.plans.evaluation_plan --with-seq
bash scripts/cert/smoke_evolve_loop.sh
```

```python
from rbp_eval.scoring.fuse_hits import fuse_rbp_hits, aggregate_p_hat

donors = fuse_rbp_hits([
 [{"alias": "PTBP1", "metric": "esm_cosine", "score": 0.82}],
 [{"alias": "PTBP1", "metric": "foldseek", "score": 0.71}],
], top_k=5)
print(donors[0]["alias"], donors[0].get("score"))
```



## 依赖 / 环境

- 真实打分需要 `DELIVERY_ROOT` + 科学 conda。
- 公开 CI 常跳过重科学——本地用 [`scripts/cert/`](../scripts/cert/README.zh.md)。
- promote 必须过 gate + nested-split 证据（[`AGENTS.md`](../AGENTS.md)）。

## 设计思路

- 离线调参离开 chat 热路径。
- 勿用 LLM 编造分数冒充 own-head / LOO 指标。
- 融合权重对实测消融诚实（如 peaks 提升前 `rna_peak_homology: 0`）。

## 相关文档

[`../README.zh.md`](../README.zh.md) · [`../config/README.zh.md`](../config/README.zh.md) · [rbp-agent SKILL.md](../nanobot/skills/rbp-agent/SKILL.md) · [自演进 (evolve)](evolve/README.zh.md) · [`ARCHITECTURE.md`](../ARCHITECTURE.md) · [`../scripts/cert/README.zh.md`](../scripts/cert/README.zh.md)