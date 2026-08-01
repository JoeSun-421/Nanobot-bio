# rbp_eval/accept/

科学验收：own-head 金标、transfer 校准、release 指标、LLM accept、缺口闭合。

[English](README.md) · [中文]

## 用途

承载 nanobot-bio 的**科学**验收路径。工程门禁（`gate` / `compliance` / `layout` / `mvp`）留在 `app/dev`。此处包含：delivery own-head（无 LLM）、Phase-2 transfer 校准、不可变 release 指标复现、LLM 产品路径验收，以及 gap-closure 证据报告。CLI 别名：`nanobot-bio own-head` / `accept-golden` / `accept-llm` / `gap-closure`。

## 布局

| 模块 | 角色 |
|------|------|
| `own_head.py` | 理想环境：`resolve_rbp(PTBP1)` → `rhobind_predict` 对照金标 |
| `transfer_calibration.py` | Live / records transfer 校准（`transfer_calibration.v1`） |
| `release_metrics.py` | 复现 delivery `expected_metrics.csv`（不改 delivery） |
| `accept_llm.py` | 严格 `nanobot_llm` 产品路径 + LLM 触点证据 |
| `gap_closure.py` | Unseen trace 形态、faithfulness schema、own-head 金标检查 |
| `__init__.py` | 包标记 |

## 入口

```bash
nanobot-bio own-head
nanobot-bio accept-golden          # own-head 别名
nanobot-bio accept-llm
nanobot-bio gap-closure
python -m rbp_eval.accept.own_head
python -m rbp_eval.accept.transfer_calibration --regime both
python -m rbp_eval.accept.release_metrics --cohort K562
python -m rbp_eval.accept.gap_closure
```

```python
from rbp_eval.accept.accept_llm import run_accept_llm
from rbp_eval.accept.gap_closure import build_gap_closure_report
from rbp_eval.accept.transfer_calibration import build_calibration_report
```

## 代码示例

**Own-head 金标（delivery，无 LLM）**

```bash
# 需要 rhobind conda + GPU/CPU；退出码 0 ≈ 金标概率，3 = 科学被阻塞
python -m rbp_eval.accept.own_head
nanobot-bio own-head
```

**Transfer 校准（regime both）**

```bash
python -m rbp_eval.accept.transfer_calibration \
  --regime both --cohort K562 --top-k 5 --out artifacts/reports/json/transfer_calibration.json
```

```python
from rbp_eval.accept.gap_closure import check_unseen_trace_shape, build_gap_closure_report

shape = check_unseen_trace_shape(
    [
        "resolve_rbp",
        "fuse_similarity_views",
        "confidence_abstain",
        "predict_interaction",
        "similarity_weighted_vote",
    ],
    predict_targets=["DONOR1"],
)
print(shape.get("ok"), shape.get("errors"))

report = build_gap_closure_report(live_own_head=False)
print(report.get("ok"), list(report.keys()))
# CLI 等价：python -m rbp_eval.accept.gap_closure --no-live
```

**LLM 验收（产品路径）**

```python
from rbp_eval.accept.accept_llm import run_accept_llm

# 需配置 LLM provider；prefer_nanobot_llm，禁止 fallback
out = run_accept_llm(run_catalogue=True, run_unseen=True, strict=True)
print(out.get("ok"), out.get("mode"), list((out.get("touchpoints") or {}).keys())[:4])
```

## 依赖 / 环境

- Own-head / release 指标 / live 校准：`DELIVERY_ROOT`、`rhobind` conda、足够内存/GPU。
- `accept_llm`：Nanobot + LLM API（见 `~/.nanobot/config.json` / providers）；会清理 `artifacts/sessions/` 下 `accept-llm_*` 会话。
- Transfer promote 门禁要求 schema `transfer_calibration.v1`，且 `score_source=real_rhobind`、`synthetic=false`。

## 相关文档

[`../README.zh.md`](../README.zh.md) · [`../evolve/README.zh.md`](../evolve/README.zh.md) · [`../../app/dev/README.zh.md`](../../app/dev/README.zh.md) · [`../../app/backends/delivery/README.zh.md`](../../app/backends/delivery/README.zh.md) · [`../../docs/product/BINDING_PREDICTION_FLOW.zh.md`](../../docs/product/BINDING_PREDICTION_FLOW.zh.md)
