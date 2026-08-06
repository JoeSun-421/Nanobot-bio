#!/usr/bin/env bash
# =============================================================================
# setup_af3_blackwell.sh — isolated AF3 stack for Blackwell / CC12
#
# What it does:
#   Installs a newer upstream AlphaFold3 + CC12-capable jax (cuda12) outside
#   the delivery tree. RTX 5090 / compute capability 12 needs AF3 >=3.0.x +
#   jax >=0.10; delivery's pinned jax 0.4.34 cannot run inference on this GPU.
#
# When to run:
#   - Standalone install / reinstall of the Blackwell stack:
#       bash scripts/setup/setup_af3_blackwell.sh
#   - Usually not needed by hand: setup_all.sh auto-invokes this when GPU CC
#     is 12.* and the stack is missing
#   - Re-runs are idempotent by default: if af3_blackwell can already import
#     alphafold3 and jax/cuda works, skip the slow pip install -e / wheel
#     rebuild; skip build_data when the CCD pickle already exists
#   - Force reinstall: bash scripts/setup/setup_af3_blackwell.sh --force-reinstall
#                       (alias --rebuild)
#   - Smoke only: bash scripts/setup/setup_af3_blackwell.sh --smoke-only
#                 (skip clone/env/pip/build_data; run [4/4] only)
#
# What it does NOT do:
#   - Does not onboard LLM / nanobot agent (other setup_all steps)
#   - Does not download genetic search DBs / run the official data pipeline
#     (MSA still goes through ColabFold)
#   - Does not create or modify the classic conda env `af3` (delivery's
#     official stack stays untouched)
#
# Success outputs:
#   - AF3_DIR  -> $AF3_ROOT/alphafold3 (portable path discovery, not AutoDL-bound)
#   - conda    -> env prefix $ENV_PREFIX (conda info --base / ENV_PREFIX / common roots)
#   - smoke    -> /tmp/af3_blackwell_smoke.json (must contain "ok": true)
#   - status   -> this script only smokes; setup_all writes on success to
#                ~/.cache/nanobot-bio/af3_status (override with AF3_STATUS_FILE)
#
# Overrides: AF3_ROOT / AF3_BLACKWELL_ROOT, ENV_PREFIX / AF3_BLACKWELL_ENV, DELIVERY_ROOT
# Afterward: ./scripts/nbio.sh start --heal can write discovered local paths into .env.
# =============================================================================
set -euo pipefail

_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_AGENT_ROOT="$(cd "$_SCRIPT_DIR/../.." && pwd)"
_BIO_ROOT="$(cd "${BIO_ROOT:-$_AGENT_ROOT/..}" && pwd)"

_discover_af3_root() {
  local r parent
  parent="$(cd "$_BIO_ROOT/.." 2>/dev/null && pwd || true)"
  for r in \
    "${AF3_ROOT:-}" \
    "${AF3_BLACKWELL_ROOT:-}" \
    "$_BIO_ROOT/af3_blackwell" \
    "${parent}/af3_blackwell" \
    "${HOME}/af3_blackwell" \
    "/opt/af3_blackwell"
  do
    [[ -n "$r" ]] || continue
    if [[ -f "${r%/}/alphafold3/run_alphafold.py" ]]; then
      printf '%s\n' "${r%/}"
      return 0
    fi
  done
  # New install default: sibling of BIO_ROOT (portable).
  if [[ -n "${AF3_ROOT:-}" ]]; then
    printf '%s\n' "${AF3_ROOT%/}"
  elif [[ -n "${AF3_BLACKWELL_ROOT:-}" ]]; then
    printf '%s\n' "${AF3_BLACKWELL_ROOT%/}"
  else
    printf '%s\n' "${parent:-$_BIO_ROOT}/af3_blackwell"
  fi
}

_discover_env_prefix() {
  local name="af3_blackwell"
  local _base _py parent
  parent="$(cd "$_BIO_ROOT/.." 2>/dev/null && pwd || true)"
  if [[ -n "${ENV_PREFIX:-}" ]]; then
    printf '%s\n' "${ENV_PREFIX%/}"
    return 0
  fi
  if [[ -n "${AF3_BLACKWELL_ENV:-}" ]]; then
    printf '%s\n' "${AF3_BLACKWELL_ENV%/}"
    return 0
  fi
  if command -v conda >/dev/null 2>&1; then
    _base="$(conda info --base 2>/dev/null || true)"
    if [[ -n "$_base" && -x "${_base%/}/envs/${name}/bin/python" ]]; then
      printf '%s\n' "${_base%/}/envs/${name}"
      return 0
    fi
  fi
  for _base in \
    "${CONDA_PREFIX:-}" \
    "${MAMBA_ROOT_PREFIX:-}" \
    "${HOME}/miniconda3" \
    "${HOME}/miniforge3" \
    "${HOME}/mambaforge" \
    "${HOME}/anaconda3" \
    "${parent}/conda" \
    "$_BIO_ROOT/conda"
  do
    [[ -n "$_base" ]] || continue
    if [[ -x "${_base%/}/envs/${name}/bin/python" ]]; then
      printf '%s\n' "${_base%/}/envs/${name}"
      return 0
    fi
  done
  # Default create location under conda base (or home miniconda).
  if command -v conda >/dev/null 2>&1; then
    _base="$(conda info --base 2>/dev/null || true)"
    if [[ -n "$_base" ]]; then
      printf '%s\n' "${_base%/}/envs/${name}"
      return 0
    fi
  fi
  printf '%s\n' "${HOME}/miniconda3/envs/${name}"
}

AF3_ROOT="$(_discover_af3_root)"
ENV_PREFIX="$(_discover_env_prefix)"
DELIVERY_ROOT="${DELIVERY_ROOT:-$_BIO_ROOT/rhobind_agent_delivery}"
PIP_INDEX_URL="${PIP_INDEX_URL:-https://pypi.tuna.tsinghua.edu.cn/simple}"
# pkgs cache: prefer sibling-of-BIO conda pkgs, else conda base/pkgs or XDG cache.
if [[ -z "${CONDA_PKGS_DIRS:-}" ]]; then
  _pkgs_parent="$(cd "$_BIO_ROOT/.." 2>/dev/null && pwd || true)"
  if [[ -n "$_pkgs_parent" && -d "${_pkgs_parent}/conda/pkgs" ]]; then
    CONDA_PKGS_DIRS="${_pkgs_parent}/conda/pkgs"
  elif [[ -d "$_BIO_ROOT/conda/pkgs" ]]; then
    CONDA_PKGS_DIRS="$_BIO_ROOT/conda/pkgs"
  elif command -v conda >/dev/null 2>&1; then
    CONDA_PKGS_DIRS="$(conda info --base 2>/dev/null)/pkgs"
  else
    CONDA_PKGS_DIRS="${XDG_CACHE_HOME:-$HOME/.cache}/conda/pkgs"
  fi
fi
export PIP_INDEX_URL CONDA_PKGS_DIRS
export AF3_BLACKWELL_ROOT="$AF3_ROOT"
echo "[setup_af3_blackwell] AF3_ROOT=$AF3_ROOT"
echo "[setup_af3_blackwell] ENV_PREFIX=$ENV_PREFIX"
echo "[setup_af3_blackwell] DELIVERY_ROOT=$DELIVERY_ROOT"

FORCE_REINSTALL=0
SMOKE_ONLY=0
for arg in "$@"; do
  case "$arg" in
    --force-reinstall|--rebuild) FORCE_REINSTALL=1 ;;
    --smoke-only) SMOKE_ONLY=1 ;;
    -h|--help)
      cat <<'EOF'
Usage: setup_af3_blackwell.sh [--force-reinstall|--rebuild] [--smoke-only]

  (default)          Idempotent: skip pip -e if alphafold3+jax/cuda already OK;
                     skip build_data if ccd.pickle already present.
  --force-reinstall  Always run pip install -e (alias: --rebuild).
  --smoke-only       Skip clone/env/pip/build_data; only run [4/4] smoke.
EOF
      exit 0
      ;;
    *)
      echo "Unknown option: $arg (try --help)" >&2
      exit 2
      ;;
  esac
done

CCD_PICKLE="$AF3_ROOT/alphafold3/src/alphafold3/constants/converters/ccd.pickle"

af3_stack_ready() {
  # alphafold3 importable + jax sees at least one CUDA device
  [[ -x "$ENV_PREFIX/bin/python" ]] || return 1
  "$ENV_PREFIX/bin/python" - <<'PY' 2>/dev/null
import alphafold3  # noqa: F401
import jax
devs = jax.devices()
assert any(getattr(d, "platform", None) == "gpu" or "cuda" in str(d).lower() for d in devs), devs
print("ok")
PY
}

run_smoke() {
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
  echo "OK — update nanobot-bio/.env AF3_* to point here; AF3 status is written outside the repo (default ~/.cache/nanobot-bio/af3_status, override AF3_STATUS_FILE)"
}

if (( SMOKE_ONLY )); then
  echo "[smoke-only] skipping clone/env/pip/build_data"
  if [[ ! -x "$ENV_PREFIX/bin/python" || ! -f "$AF3_ROOT/alphafold3/run_alphafold.py" ]]; then
    echo "ERROR: --smoke-only requires existing env ($ENV_PREFIX) and AF3 tree" >&2
    exit 1
  fi
  run_smoke
  exit 0
fi

mkdir -p "$AF3_ROOT" "$(dirname "$ENV_PREFIX")" "$CONDA_PKGS_DIRS"

# [1/4] Clone upstream AF3 outside delivery (do not touch delivery/third_party)
if [[ ! -f "$AF3_ROOT/alphafold3/run_alphafold.py" ]]; then
  echo "[1/4] clone google-deepmind/alphafold3 → $AF3_ROOT/alphafold3"
  git clone --depth 1 https://github.com/google-deepmind/alphafold3.git "$AF3_ROOT/alphafold3"
else
  echo "[1/4] AF3 tree present: $AF3_ROOT/alphafold3"
fi

# [2/4] Isolated env af3_blackwell (do not overwrite classic af3)
if [[ ! -x "$ENV_PREFIX/bin/python" ]]; then
  echo "[2/4] conda create $ENV_PREFIX (python 3.12)"
  conda create -y -p "$ENV_PREFIX" python=3.12 pip cmake ninja
else
  echo "[2/4] env exists: $ENV_PREFIX"
fi

# [3/4] pip install -e (pull jax cuda12) + build_data (idempotent skip OK)
if (( FORCE_REINSTALL )); then
  echo "[3/4] --force-reinstall: pip install -e alphafold3 (jax cuda12)"
  "$ENV_PREFIX/bin/python" -m pip install -U pip setuptools wheel
  ( cd "$AF3_ROOT/alphafold3" && "$ENV_PREFIX/bin/python" -m pip install -e . )
elif af3_stack_ready; then
  echo "[3/4] alphafold3 + jax/cuda already OK in $ENV_PREFIX — skip pip install -e"
else
  echo "[3/4] pip install -e alphafold3 (jax cuda12) + build_data"
  "$ENV_PREFIX/bin/python" -m pip install -U pip setuptools wheel
  ( cd "$AF3_ROOT/alphafold3" && "$ENV_PREFIX/bin/python" -m pip install -e . )
fi

if [[ -f "$CCD_PICKLE" ]]; then
  echo "[3/4] CCD pickle present ($CCD_PICKLE) — skip build_data"
else
  echo "[3/4] CCD pickle missing — running build_data"
  "$ENV_PREFIX/bin/build_data" || true
fi

# [4/4] Short inference smoke (reuse delivery weights; MSA still via ColabFold)
run_smoke
