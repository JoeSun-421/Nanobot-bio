#!/usr/bin/env bash
# =============================================================================
# setup_all_blackwell.sh — Blackwell / CC12 full install entry
# =============================================================================
#
# Target GPUs:
#   - NVIDIA Blackwell, compute capability **12.x**
#   - Typical: GeForce RTX 5090 / 5090 D (and other CC 12 cards)
#
# Why a separate entrypoint:
#   delivery classic conda env `af3` pins jax 0.4.34 and **cannot run on CC 12**.
#   This path forces the out-of-tree isolated stack (newer upstream AF3 + jax >=0.10)
#   and does not overwrite the official `af3` env.
#
# What this script does:
#   Thin wrapper: calls setup_all.sh with AF3_STACK=blackwell forced
#   → if isolated stack is missing, setup_all invokes scripts/setup/setup_af3_blackwell.sh
#   → .env AF3_DIR / AF3_PYTHON point at af3_blackwell (weights still use delivery AF3_PARAMS)
#
# Usage:
#   bash scripts/setup/setup_all_blackwell.sh
#   bash scripts/setup/setup_all_blackwell.sh --skip-smoke
#   # remaining args are forwarded to setup_all.sh
#
# Rebuild AF3 isolated stack only (leave agent venv / other conda alone):
#   bash scripts/setup/setup_af3_blackwell.sh
#
# Non-5090 hosts: use setup_all_ampere_or_older.sh, or auto setup_all.sh
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "[setup_all_blackwell] AF3_STACK=blackwell → out-of-tree af3_blackwell isolated stack"
echo "[setup_all_blackwell] for: RTX 5090 and other CC 12 GPUs (does not change delivery af3 env)"
exec bash "$SCRIPT_DIR/setup_all.sh" --af3-stack=blackwell "$@"
