# rbp_eval/plans/

提案评估计划（轻量 / 重量）与 faithfulness 表格。

[English](README.md) · [中文]

## 用途

实现 Proposal Evaluation Plan：隐藏 own head → 检索 donor → 用 delivery transfer CSV 计算策略级 AUPRC/AUROC（轻量）；在 RhoBind 可用时可选跑重量级实例指标。同时写出定性 faithfulness 评分 CSV，以及启发式验收分层标签（`own_head`、`in_panel_transfer`、`dark_protein`、`cross_kingdom`）。默认输出在 `artifacts/reports/{json,md,csv}/`。

## 布局

| 模块 | 角色 |
|------|------|
| `evaluation_plan.py` | 轻/重计划、分层、faithfulness 表、CLI |
| `__init__.py` | 包标记 |

## 入口

```bash
nanobot-bio eval-plan [--with-seq]
python -m rbp_eval.plans.evaluation_plan
python -m rbp_eval.plans.evaluation_plan --with-seq
python -m rbp_eval.plans.evaluation_plan --heavy   # 需要 ≥8 GiB + rhobind
```

```python
from rbp_eval.plans.evaluation_plan import (
    assign_strata,
    run_light_evaluation_plan,
    write_faithfulness_sheet,
)
```

## 代码示例

**CLI（轻量，约 2 GiB 安全）**

```bash
python -m rbp_eval.plans.evaluation_plan \
  --out artifacts/reports/json/evaluation_plan_report.json \
  --md artifacts/reports/md/evaluation_plan_report.md \
  --qual artifacts/reports/csv/faithfulness_rating_sheet.csv
```

**分层辅助**

```python
from rbp_eval.plans.evaluation_plan import assign_strata, strata_bucket_schema

tags = assign_strata(in_panel=True, mode="transfer", dark=False)
print(tags)  # 例如含 in_panel_transfer / own_head 启发式
print(list(strata_bucket_schema().keys())[:4])
```

轻量计划仍需 delivery LOO / transfer 矩阵资源（与 `rbp_eval.loo` 相同）；除非 `--heavy`，否则**不会**重跑 RhoBind。

## 依赖 / 环境

- 轻量：delivery CSV transfer 矩阵 + domain（可选 `--with-seq` ESM）视图。
- 重量：`rhobind` conda、带标签 FASTA 子采样、足够内存的 GPU/CPU。
- 报告被 `nanobot-bio gate` / `promote-evolved` 消费（`evaluation_plan_report.json`）。

## 相关文档

[`../README.zh.md`](../README.zh.md) · [`../loo/README.zh.md`](../loo/README.zh.md) · [`../scoring/README.zh.md`](../scoring/README.zh.md) · [`../../app/dev/README.zh.md`](../../app/dev/README.zh.md)
