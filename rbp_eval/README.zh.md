# rbp_eval/

离线科学评估、LOO、融合打分、验收与自演化。

[English](README.md) · [中文]

## 用途

本包是 nanobot-bio 的离线科学实验室：测量 own-head / LOO 上限、融合多视图命中、校准 transfer，并跑写入 `config/evolved.candidate.yaml` 的门禁自演化。它刻意**不在 chat 热路径上**——交互 UX 留在 `app/` + `nanobot/`。物理路径 = import 路径（无 facade）；使用 `python -m rbp_eval.<subpkg>.<module>`。

Chat 绑定产品流：[`docs/product/BINDING_PREDICTION_FLOW.zh.md`](../docs/product/BINDING_PREDICTION_FLOW.zh.md)。演化政策：[`docs/product/SELF_EVOLUTION.md`](../docs/product/SELF_EVOLUTION.md)。

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

## 入口

```bash
python -m rbp_eval
nanobot-bio run-eval|heavy-loo|evolve|promote-evolved|eval-plan|own-head
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

[`../README.zh.md`](../README.zh.md) · [`../config/README.zh.md`](../config/README.zh.md) · [`../docs/product/BINDING_PREDICTION_FLOW.zh.md`](../docs/product/BINDING_PREDICTION_FLOW.zh.md) · [`ARCHITECTURE.md`](../ARCHITECTURE.md) · [`../scripts/cert/README.zh.md`](../scripts/cert/README.zh.md)
