#!/usr/bin/env bash
# =============================================================================
# setup_all_ampere_or_older.sh — classic AF3 stack (non-Blackwell) full install entry
# =============================================================================
#
# Target GPUs (delivery pins jax 0.4.x / CUDA12-capable inference cards), e.g.:
#   - Ampere: A100, A10, RTX 3090, etc. (CC 8.0 / 8.6)
#   - Ada: RTX 4090, etc. (CC 8.9)
#   - Hopper: H100, etc. (CC 9.0; still classic `af3`, per docs matrix)
#   - In short: common datacenter / consumer NVIDIA GPUs that are **not CC 12.***
#
# Not for:
#   - RTX 5090 / Blackwell (CC 12) → use setup_all_blackwell.sh
#
# What this script does:
#   Thin wrapper: calls setup_all.sh with AF3_STACK=classic forced
#   → harden path uses delivery conda env `af3` + vendored third_party/alphafold3
#   → does **not** install / switch to the out-of-tree af3_blackwell isolated stack
#
# Usage:
#   bash scripts/setup/setup_all_ampere_or_older.sh
#   bash scripts/setup/setup_all_ampere_or_older.sh --skip-smoke
#   # remaining args are forwarded to setup_all.sh (--skip-conda / --skip-af3, etc.)
#
# Unsure of GPU class: run bash scripts/setup/setup_all.sh (auto detects via nvidia-smi CC)
# AF3 isolated stack only (5090): bash scripts/setup/setup_af3_blackwell.sh
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "[setup_all_ampere_or_older] AF3_STACK=classic → delivery conda env af3"
echo "[setup_all_ampere_or_older] for: A100 / H100 / 4090 and other non-CC12 GPUs"
exec bash "$SCRIPT_DIR/setup_all.sh" --af3-stack=classic "$@"
