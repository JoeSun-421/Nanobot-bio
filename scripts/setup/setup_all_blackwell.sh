#!/usr/bin/env bash
# =============================================================================
# setup_all_blackwell.sh — Blackwell / CC12 全量安装入口
# =============================================================================
#
# 适用 GPU：
#   - NVIDIA Blackwell，compute capability **12.x**
#   - 典型：GeForce RTX 5090 / 5090 D（以及其它 CC 12 卡）
#
# 为什么需要单独入口：
#   delivery 的经典 conda env `af3` 钉死 jax 0.4.34，**无法在 CC 12 上执行**。
#   本路径强制走仓外隔离栈（较新上游 AF3 + jax ≥0.10），且不覆盖官方 `af3` env。
#
# 本脚本做什么：
#   薄包装：调用 setup_all.sh，并强制 AF3_STACK=blackwell
#   → 若隔离栈缺失，setup_all 会调用 scripts/setup/setup_af3_blackwell.sh
#   → .env 中的 AF3_DIR / AF3_PYTHON 指向 af3_blackwell（权重仍用 delivery AF3_PARAMS）
#
# 用法：
#   bash scripts/setup/setup_all_blackwell.sh
#   bash scripts/setup/setup_all_blackwell.sh --skip-smoke
#   # 其余参数原样转给 setup_all.sh
#
# 仅重装 AF3 隔离栈（不动 agent venv / 其它 conda）：
#   bash scripts/setup/setup_af3_blackwell.sh
#
# 非 5090 机型：请用 setup_all_ampere_or_older.sh，或 auto 的 setup_all.sh
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "[setup_all_blackwell] AF3_STACK=blackwell → 仓外 af3_blackwell 隔离栈"
echo "[setup_all_blackwell] 适用：RTX 5090 等 CC 12 GPU（不改 delivery 的 af3 env）"
exec bash "$SCRIPT_DIR/setup_all.sh" --af3-stack=blackwell "$@"
