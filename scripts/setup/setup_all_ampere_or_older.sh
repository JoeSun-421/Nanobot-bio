#!/usr/bin/env bash
# =============================================================================
# setup_all_ampere_or_older.sh — 经典 AF3 栈（非 Blackwell）全量安装入口
# =============================================================================
#
# 适用 GPU（delivery 钉死的 jax 0.4.x / CUDA12 可跑推理的卡），例如：
#   - Ampere：A100、A10、RTX 3090 等（CC 8.0 / 8.6）
#   - Ada：RTX 4090 等（CC 8.9）
#   - Hopper：H100 等（CC 9.0；仍走经典 `af3`，与 docs 矩阵一致）
#   - 总之：**非 CC 12.*** 的常见数据中心 / 消费级 NVIDIA GPU
#
# 不适用于：
#   - RTX 5090 / Blackwell（CC 12）→ 请用 setup_all_blackwell.sh
#
# 本脚本做什么：
#   薄包装：调用 setup_all.sh，并强制 AF3_STACK=classic
#   → harden 路径使用 delivery 的 conda env `af3` + vendored third_party/alphafold3
#   → **不会**安装 / 切换到仓外 af3_blackwell 隔离栈
#
# 用法：
#   bash scripts/setup/setup_all_ampere_or_older.sh
#   bash scripts/setup/setup_all_ampere_or_older.sh --skip-smoke
#   # 其余参数原样转给 setup_all.sh（--skip-conda / --skip-af3 等）
#
# 不确定机型时：直接 bash scripts/setup/setup_all.sh（auto 按 nvidia-smi CC 探测）
# 仅补装 AF3 隔离栈（5090）：bash scripts/setup/setup_af3_blackwell.sh
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "[setup_all_ampere_or_older] AF3_STACK=classic → delivery conda env af3"
echo "[setup_all_ampere_or_older] 适用：A100 / H100 / 4090 等非 CC12 GPU"
exec bash "$SCRIPT_DIR/setup_all.sh" --af3-stack=classic "$@"
