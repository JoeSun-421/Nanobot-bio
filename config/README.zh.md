# config/

检索 / 融合 / 运行行为的 YAML 默认与演化旋钮。

[English](README.md) · [中文]

## 功能

- 产品默认超参（`schema_version`、轴开关、融合权重、弃权/标签阈值、integrate / predict / structure / llm 块）
- 可选已 promote 的演化叠层，以及被 gitignore 的候选文件
- 受 `tests/test_proposal_compliance.py` 对照提案矩阵约束

## 实现方法

| 文件 | 角色 | 版本控制 |
|------|------|----------|
| `defaults.yaml` | **主默认**：`backend`、`cohort`、`top_k`/`n_cand`、`axes.*`、`fusion_weights.*`、`tau_drop`、`models:` 等 | 跟踪 |
| `evolved.yaml` | 已 promote 的演化配置（若存在） | 可跟踪 |
| `evolved.candidate.yaml` | 演化候选（promote 前） | **gitignore** |
| `evolved.candidate.yaml.example` | 候选示例 | 跟踪 |

运行时读取：`app.core.runtime_config`（启用时 deep-merge `evolved.yaml`）。写入方：`rbp_eval.evolve.*`（`promote.py` 等）。Skill / CLI 不得静默替换 Table 默认值。

`defaults.yaml` 中的示例字段：

- `axes.use_af3` / `rna_blastn` / `structure` …
- `fusion_weights.rna_peak_homology` 默认 `0`，直至 peaks 消融通过 promote
- `tau_drop: 0.30`、`n_cand: 5`、`integrate.max_vote_donors: 2`

## 怎么使用

改默认须有评估证据并更新测试（[`AGENTS.md`](../AGENTS.md)）：

```bash
# 演化产出候选后：
nanobot-bio promote-evolved          # 有门禁；或 python -m rbp_eval.evolve.promote
pytest tests/test_proposal_compliance.py
```

不要把含密钥的 `*.local.json` 放进本目录（gitignore 已挡一部分）。

## 设计思路

- 用可评审的单一 YAML SoT 承载产品旋钮，避免魔法数散落在 skill 文案里。
- candidate 本地/ignore，避免实验 promote 产物被强行提交。
- 不可用轴的诚实性与 `app/core/capability_matrix.py` 一起约束，而不是编造融合权重。

## 相关文档

[`../README.zh.md`](../README.zh.md) · [`../rbp_eval/README.zh.md`](../rbp_eval/README.zh.md) · [`ARCHITECTURE.md`](../ARCHITECTURE.md) §5
