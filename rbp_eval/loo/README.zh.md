# rbp_eval/loo/

Leave-one-out 评估：轻量 policy LOO 与重型 hide-own-head。

[English](README.md) · [中文]

## 用途

量化 catalogue head 留出时 transfer 策略的恢复能力。`loo_eval.py` 是较轻的报告路径（policy vs own-head 的 AUPRC 类摘要）。`heavy_loo.py` 跑更强认证用的昂贵 hide-own-head 协议。报告写入 `artifacts/reports/`。

## 布局

| 模块 | 角色 |
|------|------|
| `loo_eval.py` | 轻量 LOO 报告 CLI |
| `heavy_loo.py` | 重型 hide-own-head CLI |
| `__init__.py` | 包标记 |

## 入口

```bash
python -m rbp_eval.loo.loo_eval --out artifacts/reports/json/eval_loo_report.json
python -m rbp_eval.loo.heavy_loo --help
nanobot-bio run-eval
nanobot-bio heavy-loo
```

## 代码示例

```bash
python -m rbp_eval.loo.loo_eval \
  --out artifacts/reports/json/eval_loo_report.json

nanobot-bio heavy-loo --help
```

```python
from rbp_eval.loo.loo_eval import load_loo_summary, resolve_loo_csvs

print(resolve_loo_csvs)
print(load_loo_summary)
```

## 依赖 / 环境

- 有意义的数字需要 delivery LOO 产物 / 科学环境。
- `app.dev.gate.delivery_loo_ready()` 检测 CI 何时可跑轻量断言。

## 相关文档

[`../README.zh.md`](../README.zh.md) · [`../scoring/README.zh.md`](../scoring/README.zh.md) · [`../../scripts/cert/README.zh.md`](../../scripts/cert/README.zh.md)
