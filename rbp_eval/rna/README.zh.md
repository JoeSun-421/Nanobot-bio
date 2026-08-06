# rbp_eval/rna/

RNA 轴融合门禁辅助（与 delivery 对齐的 HOLD）。

[English](README.md) · [中文]

> 包地图与 `$BIO_ROOT` 布局见仓库根 [`README.zh.md`](../../README.zh.md)。激活：`cd "${NANOBOT_BIO_ROOT:-$BIO_ROOT/Nanobot-bio}" && source scripts/nbio.sh`。

## 用途

记录并输出离线评估 / promote 使用的 RNA 融合门禁。Delivery 注册表中**没有 RNA-FM 轴**；产品 RNA 轴是 `rna_blastn` / peaks 同源，融合中的 `rna_*` 权重在 peaks 就绪前保持 0。`run_rna_fm_gate` 始终返回 `decision: HOLD`、`allow_fusion: False`、`fusion_weight: 0.0`，并调用 `app.core.fusion_rna_policy.write_gate`（当前为 no-op——就绪性仅在运行时判断）。

## 布局

| 模块 | 角色 |
|------|------|
| `rna_fm_gate.py` | `run_rna_fm_gate`，CLI `python -m rbp_eval.rna.rna_fm_gate` |
| `__init__.py` | 包标记 |

## 入口

```bash
python -m rbp_eval.rna.rna_fm_gate
python -m rbp_eval.rna.rna_fm_gate --weight 0.30
```

```python
from rbp_eval.rna.rna_fm_gate import run_rna_fm_gate
from app.core.fusion_rna_policy import apply_fusion_rna_policy, DEFAULT_REAL_WEIGHT
```

## 代码示例

```bash
python -m rbp_eval.rna.rna_fm_gate
# 打印 JSON：schema rna_fm_eval_gate.v1，decision HOLD，fusion_weight 0.0
```

```python
from rbp_eval.rna.rna_fm_gate import run_rna_fm_gate
from app.core.fusion_rna_policy import apply_fusion_rna_policy

gate = run_rna_fm_gate()
assert gate["decision"] == "HOLD"
assert gate["allow_fusion"] is False
assert float(gate["fusion_weight"]) == 0.0

# 运行时融合权重：peaks DB 未就绪时将 rna_peak_homology 置 0
w = apply_fusion_rna_policy({"esmc_cosine": 0.4, "rna_peak_homology": 0.3})
print(w.get("rna_peak_homology"), "rna_embed" in w) # 通常为 0.0, False
```

## 依赖 / 环境

- 门禁 CLI 不需要 GPU。
- 实时融合权重清零会查询 `app.core.capability_matrix.rna_blastn_status`。
- Peaks DB / `rna_blastn` 就绪与此历史 RNA-FM 门禁名称彼此独立。

## 相关文档

[`../README.zh.md`](../README.zh.md) · [`../scoring/README.zh.md`](../scoring/README.zh.md) · [`../../app/core/README.zh.md`](../../app/core/README.zh.md) · [rbp-agent SKILL.md](../../nanobot/skills/rbp-agent/SKILL.md)
