# rbp_eval/evolve/

离线自进化：验证批跑、旋钮重调、候选配置与门禁 promote。

[English](README.md) · [中文]

## 用途

运行离线自进化环：从 LOO 风格验证批重调 fusion / abstain / label / `tau_drop`，写入 `config/evolved.candidate.yaml`，仅在嵌套划分 + transfer 校准门禁通过后 promote 到 `config/evolved.yaml`。交互 chat **不会**调用此路径——运营使用 `nanobot-bio evolve` / `promote-evolved` 或 `python -m rbp_eval.evolve.*`。

策略文档：[`../../docs/product/SELF_EVOLUTION.md`](../../docs/product/SELF_EVOLUTION.md)。

## 布局

| 模块 | 角色 |
|------|------|
| `runner.py` | LOO 验证批 + 可选 `--evolve` |
| `orchestrator.py` | `run_self_evolution`、`EvolutionReport` |
| `retune.py` | 权重 / 阈值 / abstain / `tau_drop` 重调 |
| `proposals.py` | 工具归因 + toolkit 扩展提案 |
| `proxy_cache.py` | 提升高频 target→proxy 映射（`artifacts/cache/proxy_map.json`） |
| `../loo/expand_matrix.py` | 一键扩展 agent 侧 LOO 矩阵副本（不改 delivery） |
| `../loo/matrix_ab_eval.py` | delivery vs 扩展矩阵 A/B（`delta_auprc`） |
| `promote.py` | 门禁并将候选 promote 为 `evolved.yaml` |
| `evolve_eval.py` | 在 LOO medoids 上的轻量嵌套 train/test |
| `run_eval.py` | Agent run_eval + 模态消融 |
| `transfer_promotion.py` | 对比 baseline vs candidate transfer 报告 |
| `__init__.py` | 包标记 |

## 入口

```bash
# LOO 矩阵副本 + 自演进 + A/B（不改 delivery）
nanobot-bio expand-loo-matrix --cohort K562 --max-seqs 64
export RBP_LOO_TRANSFER_DIR="$(pwd)/rbp_eval/data/transfer"
export TRANSFER_DIR="$RBP_LOO_TRANSFER_DIR"
nanobot-bio evolve --transfer-dir "$RBP_LOO_TRANSFER_DIR"
nanobot-bio loo-matrix-ab

nanobot-bio evolve-eval
nanobot-bio run-eval
nanobot-bio promote-evolved [--seed]
python -m rbp_eval.evolve.runner --evolve
python -m rbp_eval.evolve.evolve_eval
python -m rbp_eval.evolve.run_eval
```

```python
from rbp_eval.evolve.orchestrator import run_self_evolution
from rbp_eval.evolve.promote import promote_evolved_config
from rbp_eval.evolve.proxy_cache import load_proxy_cache, lookup_proxies
```

## 代码示例

**批验证并写入候选（CLI）**

```bash
python -m rbp_eval.evolve.runner --top-k 5 --out artifacts/reports/json/val_batch.json
python -m rbp_eval.evolve.runner --evolve --top-k 5

# 嵌套划分轻量评估 → evolve_eval_decision.json
python -m rbp_eval.evolve.evolve_eval --seed 42 --n-test 5
```

**门禁齐全后的程序化 promote**

```python
from rbp_eval.evolve.promote import promote_evolved_config, CANDIDATE_CONFIG

# 需要 artifacts/reports/ 下：eval_loo_report.json、
# evaluation_plan_report.json、evolve_eval_decision.json（PROMOTE）、
# 且 transfer_calibration.json 与候选 sha256 一致。
path = promote_evolved_config(seed=True, require_reports=True)
print("promoted:", path, "from", CANDIDATE_CONFIG)
```

**代理缓存查询**

```python
from rbp_eval.evolve.proxy_cache import load_proxy_cache, lookup_proxies

cache = load_proxy_cache()
hits = lookup_proxies(alias="PTBP1")  # 仅关键字参数；内部加载 cache
print("entries", len(cache.get("entries") or {}), "lookup", hits)
```

## 依赖 / 环境

- 真实重调 / promote 需要 delivery release + 科学 conda（`DELIVERY_ROOT`、`rhobind`）。
- `config/evolved.candidate.yaml` 被 gitignore；可用 `--seed` / example 种子引导。
- Promote 拒绝仅 retrieval 的合成 evolve 报告，并要求嵌套划分 `delta_auprc>0`（`n>=10`）。
- 认证环：[`../../scripts/cert/README.zh.md`](../../scripts/cert/README.zh.md)（`smoke_evolve_loop.sh`）。

## 相关文档

[`../README.zh.md`](../README.zh.md) · [`../accept/README.zh.md`](../accept/README.zh.md) · [`../loo/README.zh.md`](../loo/README.zh.md) · [`../../config/README.zh.md`](../../config/README.zh.md) · [`../../docs/product/SELF_EVOLUTION.md`](../../docs/product/SELF_EVOLUTION.md)
