# rbp_eval/

离线科学评估、LOO、融合打分、验收与自演化。

[English](README.md) · [中文]

## 功能

- Leave-one-out / 隐藏自身 head 评估与 recovered AUPRC 类指标
- Transfer 相似度 / 权重所用的命中融合打分
- 验收模块：own-head、transfer 校准、release 指标、LLM 触点、gap closure
- 自演化写入 `config/evolved.candidate.yaml`，经门禁 `promote`
- 物理路径 = import 路径（无顶层 facade）

## 实现方法

| 子包 | 角色 |
|------|------|
| `scoring/` | 命中融合（`fuse_hits.py`）、head index、指标 |
| `loo/` | `loo_eval.py`（轻量 LOO）、`heavy_loo.py`（hide-own-head） |
| `accept/` | `own_head`、`transfer_calibration`、`release_metrics`、`accept_llm`、`gap_closure` |
| `evolve/` | `run_eval`、`orchestrator`、`promote`、`runner`、`retune`、`proxy_cache` 等 |
| `runtime/` | 评估运行时辅助 |
| `rna/` | RNA 轴相关 |
| `plans/` | evaluation plan / 指标报告 |

报告默认写入 `artifacts/reports/{json,md,csv}/`（经 `app.core.paths`）。

与配置的关系（[`ARCHITECTURE.md`](../ARCHITECTURE.md) §5）：

- 默认：`config/defaults.yaml`
- 候选：`config/evolved.candidate.yaml`（gitignore）
- 已提升：`config/evolved.yaml`（`evolved: true` 时 deep-merge）

## 怎么使用

```bash
python -m rbp_eval                          # 常用模块帮助
python -m rbp_eval.loo.loo_eval --out artifacts/reports/json/eval_loo_report.json
python -m rbp_eval.accept.own_head
python -m rbp_eval.accept.transfer_calibration --regime both …
python -m rbp_eval.evolve.runner [--evolve]
bash scripts/cert/smoke_evolve_loop.sh      # evolve 干跑冒烟

# CLI 包装：
nanobot-bio run-eval
nanobot-bio heavy-loo
nanobot-bio evolve|evolve-eval|promote-evolved
```

真实打分需要 `DELIVERY_ROOT` + 科学 conda。公开 CI 常跳过重科学——本地用 [`scripts/cert/`](../scripts/cert/README.zh.md)。

## 设计思路

- 离线调参**离开 chat 热路径**，交互 UX 保持精简。
- promote 必须过 gate + nested-split 证据（`delta_auprc > 0` 或 HOLD）——禁止手改后声称已演化（[`AGENTS.md`](../AGENTS.md)）。
- 融合权重（如 peaks 消融通过前 `rna_peak_homology: 0`）对实测诚实。
- 勿用 LLM 编造分数冒充 own-head / LOO 指标。

## 相关文档

[`../README.zh.md`](../README.zh.md) · [`../config/README.zh.md`](../config/README.zh.md) · [`ARCHITECTURE.md`](../ARCHITECTURE.md) · [`../scripts/cert/README.zh.md`](../scripts/cert/README.zh.md)
