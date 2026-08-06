# rbp_eval/evolve/

离线自进化：scored \(D_{\mathrm{val}}\)、五步环、候选配置与门禁 promote。

[English](README.md) · [中文]

政策：本包（下方五步环）· [`ARCHITECTURE.zh.md`](../../ARCHITECTURE.zh.md) eval/promote  
矩阵：[LOO 扩充](../loo/README.zh.md)

## 环境

```bash
export BIO_ROOT="${BIO_ROOT:-$HOME/bio_agent}"
cd "${NANOBOT_BIO_ROOT:-$BIO_ROOT/Nanobot-bio}" && source scripts/nbio.sh
export RHOBIND_RELEASE="${RHOBIND_RELEASE:-$DELIVERY_ROOT/release/rhobind_release_v1}"
export RBP_TEST_DATA_ROOT="${RBP_TEST_DATA_ROOT:-$BIO_ROOT/rhobind_testdata_v2/rhobind_testdata_v2/test_data}"
```

## 五步 ↔ 模块 ↔ CLI

| # | 步骤 | 模块 | CLI |
|---|------|------|-----|
| 1 | Trace | `runtime/nanobot_hooks.py`、`runner.collect_agent_traces` | `evolve [--collect-agent-traces] [--require-traces]` → `artifacts/traces/` |
| 2 | Attribution | `proposals.tool_attribution` | candidate `tools.soft_disabled`（runtime 跳过 / `disabled_by_evolution`） |
| 3 | CE retune | `retune_fusion_on_dval_ce`（+ 标签阈值）；LOO-AUPRC 为辅 | `evolved.candidate.yaml`（`tuned_weights`、`logit_scale`） |
| 4 | Toolkit 人审 | `propose_toolkit_expansions`、`toolkit_review.py` | `review-toolkit-proposals`（仅人审；永不安装） |
| 5 | Cache / Stage1 | `proxy_cache.promote_from_traces` | `proxy_map.json`；hit → `stage1_bypassed` 硬旁路 |

## 端到端

```bash
nanobot-bio expand-loo-matrix --cohort K562 --max-seqs 256 --skip-existing-helds
export RBP_LOO_TRANSFER_DIR="$(pwd)/rbp_eval/data/transfer"

nanobot-bio evolve --transfer-dir "$RBP_LOO_TRANSFER_DIR" --medoids --max-seqs 64 \
 --collect-agent-traces --require-traces
nanobot-bio run-eval --medoids --transfer-dir "$RBP_LOO_TRANSFER_DIR" \
 --policy config/evolved.candidate.yaml --max-seqs 64
nanobot-bio review-toolkit-proposals --list
nanobot-bio promote-evolved
```

默认 scored（真实 \(p_{\mathrm{hat}}\)）；`--retrieval-only` 不可 promote。toolkit **永不**自动安装。不在 chat 热路径。

## 产物

| 路径 | 角色 |
|------|------|
| `artifacts/traces/*.jsonl` | `rbp_trace/v1` |
| `artifacts/cache/proxy_map.json` | proxy 缓存 |
| `config/evolved.candidate.yaml` | CE 权重 + `logit_scale` + `soft_disabled` |
| `artifacts/reports/json/toolkit_proposals.json` | 待人审提案 |
| `artifacts/reports/json/toolkit_proposals_decisions.json` | accept/reject 审计 |
