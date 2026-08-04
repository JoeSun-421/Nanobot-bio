# rbp_eval/evolve/

Offline self-evolution: scored \(D_{\mathrm{val}}\), five-step loop, candidate config, gated promote.

[English] · [中文](README.zh.md)

Policy: [`../../docs/product/SELF_EVOLUTION.md`](../../docs/product/SELF_EVOLUTION.md)  
Matrix expand: [`../../docs/guides/LOO_EXPAND.md`](../../docs/guides/LOO_EXPAND.md)

## Environment

```bash
export BIO_ROOT="${BIO_ROOT:-$HOME/bio_agent}"
cd "$BIO_ROOT/nanobot-bio" && source scripts/nbio.sh
export RHOBIND_RELEASE="${RHOBIND_RELEASE:-$DELIVERY_ROOT/release/rhobind_release_v1}"
export RBP_TEST_DATA_ROOT="${RBP_TEST_DATA_ROOT:-$BIO_ROOT/rhobind_testdata_v2/rhobind_testdata_v2/test_data}"
```

## Five steps ↔ modules ↔ CLI

| # | Step | Module | CLI |
|---|------|--------|-----|
| 1 | Trace | `runtime/nanobot_hooks.py`, `runner.collect_agent_traces` | `evolve [--collect-agent-traces] [--require-traces]` → `artifacts/traces/` |
| 2 | Attribution | `proposals.tool_attribution` | candidate `tools.soft_disabled` (runtime skip / `disabled_by_evolution`) |
| 3 | CE retune | `retune_fusion_on_dval_ce` (+ label thresholds); LOO-AUPRC auxiliary | `evolved.candidate.yaml` (`tuned_weights`, `logit_scale`) |
| 4 | Toolkit review | `propose_toolkit_expansions`, `toolkit_review.py` | `review-toolkit-proposals` (human only; never installs) |
| 5 | Cache / Stage-1 | `proxy_cache.promote_from_traces` | `proxy_map.json`; hit → `stage1_bypassed` hard bypass |

## End-to-end

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

Default path is **scored** (real \(p_{\mathrm{hat}}\)). Toolkit proposals are never auto-installed. Off the chat hot path.

## Artifacts

| Path | Role |
|------|------|
| `artifacts/traces/*.jsonl` | `rbp_trace/v1` |
| `artifacts/cache/proxy_map.json` | proxy cache |
| `config/evolved.candidate.yaml` | CE weights + `logit_scale` + `soft_disabled` |
| `artifacts/reports/json/toolkit_proposals.json` | human-review proposals |
| `artifacts/reports/json/toolkit_proposals_decisions.json` | accept/reject audit |
