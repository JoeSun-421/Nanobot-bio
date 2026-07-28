#!/usr/bin/env bash
# Install a Blackwell-capable AlphaFold3 stack OUTSIDE delivery (no delivery edits).
# RTX 5090 / CC 12 needs AF3 ≥3.0.x + jax ≥0.10 — delivery's pinned jax 0.4.34 cannot run.
#
# Usage:
#   bash scripts/setup_af3_blackwell.sh
# Then point nanobot-bio/.env:
#   AF3_DIR=/root/autodl-tmp/af3_blackwell/alphafold3
#   AF3_PYTHON=/root/autodl-tmp/conda/envs/af3_blackwell/bin/python
#   AF3_PARAMS=$DELIVERY_ROOT/af3_assets/alphafold_param   # reuse delivery weights
#   AF3_CACHE=/root/autodl-tmp/af3_blackwell/alphafold_cache
set -euo pipefail

AF3_ROOT="${AF3_ROOT:-/root/autodl-tmp/af3_blackwell}"
ENV_PREFIX="${ENV_PREFIX:-/root/autodl-tmp/conda/envs/af3_blackwell}"
DELIVERY_ROOT="${DELIVERY_ROOT:-/root/autodl-tmp/bio_agent/rhobind_agent_delivery}"
PIP_INDEX_URL="${PIP_INDEX_URL:-https://pypi.tuna.tsinghua.edu.cn/simple}"
export PIP_INDEX_URL CONDA_PKGS_DIRS="${CONDA_PKGS_DIRS:-/root/autodl-tmp/conda/pkgs}"

mkdir -p "$AF3_ROOT" "$(dirname "$ENV_PREFIX")" "$CONDA_PKGS_DIRS"

if [[ ! -f "$AF3_ROOT/alphafold3/run_alphafold.py" ]]; then
  echo "[1/4] clone google-deepmind/alphafold3 → $AF3_ROOT/alphafold3"
  git clone --depth 1 https://github.com/google-deepmind/alphafold3.git "$AF3_ROOT/alphafold3"
else
  echo "[1/4] AF3 tree present: $AF3_ROOT/alphafold3"
fi

if [[ ! -x "$ENV_PREFIX/bin/python" ]]; then
  echo "[2/4] conda create $ENV_PREFIX (python 3.12)"
  conda create -y -p "$ENV_PREFIX" python=3.12 pip cmake ninja
else
  echo "[2/4] env exists: $ENV_PREFIX"
fi

echo "[3/4] pip install -e alphafold3 (jax cuda12) + build_data"
"$ENV_PREFIX/bin/python" -m pip install -U pip setuptools wheel
( cd "$AF3_ROOT/alphafold3" && "$ENV_PREFIX/bin/python" -m pip install -e . )
"$ENV_PREFIX/bin/build_data" || true

echo "[4/4] short inference smoke"
export AF3_DIR="$AF3_ROOT/alphafold3"
export AF3_PYTHON="$ENV_PREFIX/bin/python"
export AF3_PARAMS="${AF3_PARAMS:-$DELIVERY_ROOT/af3_assets/alphafold_param}"
export AF3_CACHE="$AF3_ROOT/alphafold_cache"
export XLA_FLAGS="--xla_gpu_enable_triton_gemm=false"
mkdir -p "$AF3_CACHE"
"$AF3_PYTHON" "$DELIVERY_ROOT/agent/tools/structure/structure_predict_af3.py" --json \
  '{"sequence":"MQIFVKTLTGKTITLEVEPSDTIENVKAKIQDKEGIPPDQQRLIFAGKQLEDGRTLSDYNIQKESTLHLVLRLRGG","name":"ubq_smoke"}' \
  | tee /tmp/af3_blackwell_smoke.json
grep -q '"ok": true' /tmp/af3_blackwell_smoke.json
echo "OK — update nanobot-bio/.env AF3_* to point here, set .af3_status state=ok"
