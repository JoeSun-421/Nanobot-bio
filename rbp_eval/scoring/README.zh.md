# rbp_eval/scoring/

用于 transfer 排序的命中融合、head-index 辅助与离线指标。

[English](README.md) · [中文]

## 用途

实现离线评估中为 donor RBP 排序与聚合 transfer 概率时的多视图融合（概念上与产品工具镜像）。`fuse_rbp_hits` 合并各模态命中列表；`aggregate_p_hat` 将 donor head 概率 + 相似度转为报告用 transfer 分数。Chat 时 transfer 聚合权威仍是 delivery `similarity_weighted_vote`。

## 布局



## 通用布局（Linux）

```bash
export BIO_ROOT="${BIO_ROOT:-$HOME/bio_agent}"
# 检出目录常见为 Nanobot-bio（GitHub）；小写 nanobot-bio 亦可。
cd "${NANOBOT_BIO_ROOT:-$BIO_ROOT/Nanobot-bio}"
source scripts/nbio.sh
```

| 模块 | 角色 |
|------|------|
| `fuse_hits.py` | `fuse_rbp_hits`、`fuse_proxy_candidates`、`aggregate_p_hat`、`label_from_p_hat` |
| `head_index.py` | Head / catalogue 索引辅助 |
| `metrics.py` | 离线指标辅助 |
| `__init__.py` | 包标记 |

## 入口

```python
from rbp_eval.scoring.fuse_hits import (
 fuse_rbp_hits,
 aggregate_p_hat,
 fuse_proxy_candidates,
 DEFAULT_WEIGHTS,
)
```

## 代码示例

```python
from rbp_eval.scoring.fuse_hits import fuse_rbp_hits, label_from_p_hat

hits = fuse_rbp_hits(
 [
 [{"alias": "HNRNPA1", "metric": "esm_cosine", "score": 0.9}],
 [{"alias": "HNRNPA1", "metric": "domain_jaccard", "score": 0.6}],
 ],
 top_k=5,
)
print(hits[0]["alias"], hits[0].get("vote_similarity"), hits[0].get("score"))
```

```bash
python -m rbp_eval.loo.loo_eval --out artifacts/reports/json/eval_loo_report.json
```

## 依赖 / 环境

- 可能查询 `app.core.capability_matrix.rna_blastn_status`，在 peaks DB 缺失时将 `rna_peak_homology` 置 0。
- 权重常来自 `app.core.runtime_config.fusion_weights()`。

## 相关文档

[`../README.zh.md`](../README.zh.md) · [`../loo/README.zh.md`](../loo/README.zh.md) · [`../../config/README.zh.md`](../../config/README.zh.md) · [rbp-agent SKILL.md](../../nanobot/skills/rbp-agent/SKILL.md)
