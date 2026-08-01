# app/dev/

仅含工程成熟度门禁（C5 边界）。快速检查，**不能替代** `rbp_eval.accept.*` 下的科学验收。

[English](README.md) · [中文]

## 用途

本包回答：「产品树对 CI / 协作者是否接线正确？」它跑 ruff / pytest / SoT 布局 / MVP 结构验收。科学分数（own-head AUPRC、transfer 校准、promote 证据）属于 [`rbp_eval/`](../../rbp_eval/README.zh.md) 以及 `accept-*` / `promote-evolved` CLI——不要在这里加科学打分路径。

## 布局

| 模块 | 角色 |
|------|------|
| `gate.py` | `run_gate()` — ruff + pytest + layout（+ 可选轻量评估断言） |
| `layout.py` | 断言仓内 `nanobot/` SoT 布局；禁止 PA 表面回流 |
| `mvp.py` | Agent-Owner MVP A–F 级（工程结构，部分级别可能调用 `Nanobot.run`） |
| `compliance.py` | Delivery 路径 / SoT 合规自检 |

## 入口

```bash
nanobot-bio gate
nanobot-bio layout
nanobot-bio mvp
nanobot-bio compliance
# 等价：
python -m app gate
python -m app.dev.layout
bash scripts/ci/ci_gate.sh
```

```python
from app.dev.gate import run_gate
from app.dev.layout import main as layout_main

raise SystemExit(run_gate(light_eval=False))
```

## 代码示例

**以编程方式跑工程门禁**

```python
from app.dev.gate import run_gate, delivery_loo_ready

# CI 风格完整门禁（ruff + pytest + layout）
rc = run_gate()
assert rc == 0

# 可选：delivery LOO 就绪时才断言报告形状
if delivery_loo_ready():
    from app.dev.gate import assert_loo_report
    assert_loo_report()
```

**布局断言（SoT）**

```bash
# 缺少必要 RBP tools 或 PA 表面回流时失败
python -m app.dev.layout
# 或：
nanobot-bio layout
```

## 依赖 / 环境

- `gate` / `layout` 需要项目 `.venv` / editable install（ruff + pytest）。
- `mvp` 在调用 `Nanobot.run` 的级别上需要 LLM 凭证。
- 默认不要求科学 conda；仅在已有 delivery LOO 产物时可选轻量评估断言。

## 相关文档

[`../README.zh.md`](../README.zh.md) · [`../cli/README.zh.md`](../cli/README.zh.md) · [`../../scripts/ci/README.zh.md`](../../scripts/ci/README.zh.md) · [`../../AGENTS.md`](../../AGENTS.md)
