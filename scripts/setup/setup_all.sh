#!/usr/bin/env bash
# =============================================================================
# nanobot-bio — sole environment setup entry (Linux / SSH)
# =============================================================================
# Smart default: pick AF3 stack from nvidia-smi compute capability
#   - CC 12.* (Blackwell, e.g. RTX 5090) → out-of-tree af3_blackwell + jax≥0.10
#   - Other (Ampere/Ada/Hopper, …) → delivery classic conda env `af3` (jax 0.4.x)
#
# First-time (science conda + agent + optional AF3 hardening):
#   bash scripts/setup/setup_all.sh
#
# Explicit machine entrypoints (thin wrappers; prefer by GPU):
#   bash scripts/setup/setup_all_ampere_or_older.sh   # classic af3 (A100/H100/4090…)
#   bash scripts/setup/setup_all_blackwell.sh         # force Blackwell isolated stack
#
# Day-to-day (standard venv; CLI loads .env automatically):
#   source $BIO_ROOT/nanobot-bio/.venv/bin/activate
#   rbp-agent doctor && rbp-agent chat
#
# Options:
#   --skip-conda     agent venv only (no RhoBind/ESM/AF3)
#   --skip-smoke     skip doctor smoke check
#   --skip-af3       skip AF3 hardening (default on; 10-minute budget)
#   --af3-stack=auto|classic|blackwell
#                    AF3 stack selection (or env AF3_STACK; default auto)
#   AF3_BUDGET_SEC=600  AF3 hardening timeout (then deferred)
#
# After delivery setup_envs, import/probe-verifies rhobind (torch+transformers),
# protein_embed (transformers), rna (mmseqs), af3 (python) and heals hollow envs.
# Does not modify rhobind_agent_delivery sources; read-only use of setup_envs / tools.
# =============================================================================
set -euo pipefail

WITH_CONDA=1
SKIP_SMOKE=0
SKIP_AF3=0
# auto = probe GPU CC; classic = delivery `af3`; blackwell = isolated stack
AF3_STACK="${AF3_STACK:-auto}"
for arg in "$@"; do
  case "$arg" in
    --with-conda) WITH_CONDA=1 ;;
    --skip-conda) WITH_CONDA=0 ;;
    --skip-smoke) SKIP_SMOKE=1 ;;
    --skip-af3) SKIP_AF3=1 ;;
    --af3-stack=*) AF3_STACK="${arg#*=}" ;;
    -h|--help) sed -n '1,40p' "$0"; exit 0 ;;
  esac
done
case "$AF3_STACK" in
  auto|classic|blackwell) ;;
  *)
    echo "ERROR: AF3_STACK / --af3-stack must be auto|classic|blackwell (got: $AF3_STACK)" >&2
    exit 1
    ;;
esac
export AF3_STACK

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
BIO_ROOT="$(cd "${BIO_ROOT:-$AGENT_ROOT/..}" && pwd)"
DELIVERY_ROOT="${DELIVERY_ROOT:-$BIO_ROOT/rhobind_agent_delivery}"
NANOBOT_SRC="${NANOBOT_SRC:-$AGENT_ROOT/nanobot}"
export BIO_ROOT NANOBOT_SRC DELIVERY_ROOT
export NANOBOT_BIO_ROOT="$AGENT_ROOT"
export NANOBOT_WORKSPACE="$AGENT_ROOT/workspace"

# ---------------------------------------------------------------------------
# Inline: ensure in-repo slim nanobot runtime (no sibling clone)
# ---------------------------------------------------------------------------
_ensure_nanobot() {
  NANOBOT_SRC="${NANOBOT_SRC:-$AGENT_ROOT/nanobot}"
  case "$NANOBOT_SRC" in
    *"nanobot-bio/nanobot"|*"nanobot-bio/nanobot/"|"$AGENT_ROOT/nanobot")
      ;;
    *)
      echo "[ensure_nanobot] overriding NANOBOT_SRC=$NANOBOT_SRC → $AGENT_ROOT/nanobot (slim vendor)" >&2
      NANOBOT_SRC="$AGENT_ROOT/nanobot"
      ;;
  esac
  if [[ ! -f "$NANOBOT_SRC/__init__.py" && ! -f "$NANOBOT_SRC/nanobot.py" ]]; then
    echo "ERROR: in-repo nanobot missing at $NANOBOT_SRC" >&2
    echo "  Expected slim vendor tree under nanobot-bio/nanobot/ (Proposal §6.2)." >&2
    return 1
  fi
  if [[ ! -d "$NANOBOT_SRC/agent/tools/rbp" ]]; then
    echo "ERROR: missing agent/tools/rbp under $NANOBOT_SRC" >&2
    return 1
  fi
  if [[ -d "$NANOBOT_SRC/channels" || -d "$NANOBOT_SRC/webui" ]]; then
    echo "WARN: personal-assistant surface still present under $NANOBOT_SRC (expected stripped)" >&2
  fi
  echo "[ensure_nanobot] OK (in-repo): $NANOBOT_SRC"
  export NANOBOT_SRC
  return 0
}

# ---------------------------------------------------------------------------
# Inline: AF3 harden (writes AF3 status outside the git workspace; delivery read-only)
# Default: ${XDG_CACHE_HOME:-$HOME/.cache}/nanobot-bio/af3_status  (override: AF3_STATUS_FILE)
# ---------------------------------------------------------------------------
_af3_status_default() {
  echo "${AF3_STATUS_FILE:-${XDG_CACHE_HOME:-$HOME/.cache}/nanobot-bio/af3_status}"
}

_setup_af3() {
  local AF3_DIR="${AF3_DIR:-$DELIVERY_ROOT/agent/third_party/alphafold3}"
  local YML="$AF3_DIR/af3_env.yml"
  local PIP_INDEX="${PIP_INDEX_URL:-https://pypi.tuna.tsinghua.edu.cn/simple}"
  local PIP_HOST="${PIP_TRUSTED_HOST:-pypi.tuna.tsinghua.edu.cn}"
  local AF3_BUDGET_SEC="${AF3_BUDGET_SEC:-600}"
  local STATUS_FILE
  STATUS_FILE="$(_af3_status_default)"
  mkdir -p "$(dirname "$STATUS_FILE")"
  local _START
  _START=$(date +%s)

  _budget_left() {
    local now elapsed
    now=$(date +%s)
    elapsed=$((now - _START))
    echo $((AF3_BUDGET_SEC - elapsed))
  }
  _stop_if_over() {
    local left
    left="$(_budget_left)"
    if (( left <= 0 )); then
      echo "[af3] BUDGET ${AF3_BUDGET_SEC}s exceeded — stop; resume tomorrow." >&2
      _write_status deferred "budget_exceeded"
      return 1
    fi
    return 0
  }
  _write_status() {
    local state="$1" note="${2:-}"
    # A transient recheck failure (for example GPU OOM while another model is
    # active) must not erase an already certified real AF3 inference.
    if [[ "$state" != "ok" && -f "$STATUS_FILE" ]] \
      && grep -q '^state=ok$' "$STATUS_FILE" 2>/dev/null; then
      {
        echo "ts=$(date -Iseconds 2>/dev/null || date)"
        echo "state=$state"
        echo "note=$note"
      } > "${STATUS_FILE}.last_failure"
      echo "[af3] preserved certified OK; wrote ${STATUS_FILE}.last_failure"
      return
    fi
    {
      echo "state=$state"
      echo "ts=$(date -Iseconds 2>/dev/null || date)"
      echo "note=$note"
      echo "af3_python=${AF3_PYTHON:-}"
      echo "budget_sec=$AF3_BUDGET_SEC"
    } > "$STATUS_FILE"
    echo "[af3] wrote $STATUS_FILE ($state)"
  }

  echo "[af3] budget=${AF3_BUDGET_SEC}s  DELIVERY_ROOT=$DELIVERY_ROOT (read-only)"
  echo "[af3] AF3_STACK=${AF3_STACK:-auto}"
  # Delivery's pinned JAX cannot execute on Blackwell (compute capability 12).
  # Keep its official env untouched and use the isolated agent-side stack.
  # AF3_STACK: auto → blackwell on CC 12.*; classic / blackwell force-override probe.
  local GPU_CC
  GPU_CC="$(nvidia-smi --query-gpu=compute_cap --format=csv,noheader 2>/dev/null | awk 'NR==1{print; exit}' || true)"
  local use_blackwell=0
  case "${AF3_STACK:-auto}" in
    blackwell) use_blackwell=1 ;;
    classic) use_blackwell=0 ;;
    auto)
      if [[ "$GPU_CC" == 12.* ]]; then
        use_blackwell=1
      fi
      ;;
  esac
    if (( use_blackwell )); then
    # Portable discovery relative to BIO_ROOT / home /opt.
    local BW_ROOT="" BW_ENV="" _r _base _parent
    _parent="$(cd "$BIO_ROOT/.." 2>/dev/null && pwd || true)"
    for _r in \
      "${AF3_BLACKWELL_ROOT:-}" \
      "${AF3_ROOT:-}" \
      "$BIO_ROOT/af3_blackwell" \
      "${_parent}/af3_blackwell" \
      "${HOME}/af3_blackwell" \
      "/opt/af3_blackwell"
    do
      [[ -n "$_r" && -f "${_r%/}/alphafold3/run_alphafold.py" ]] || continue
      BW_ROOT="${_r%/}"
      break
    done
    if [[ -n "${AF3_BLACKWELL_ENV:-}" && -x "${AF3_BLACKWELL_ENV%/}/bin/python" ]]; then
      BW_ENV="${AF3_BLACKWELL_ENV%/}"
    elif [[ -n "${ENV_PREFIX:-}" && -x "${ENV_PREFIX%/}/bin/python" ]]; then
      BW_ENV="${ENV_PREFIX%/}"
    else
      if command -v conda >/dev/null 2>&1; then
        _base="$(conda info --base 2>/dev/null || true)"
        [[ -n "$_base" && -x "${_base%/}/envs/af3_blackwell/bin/python" ]] \
          && BW_ENV="${_base%/}/envs/af3_blackwell"
      fi
      if [[ -z "$BW_ENV" ]]; then
        for _base in \
          "${CONDA_PREFIX:-}" \
          "${MAMBA_ROOT_PREFIX:-}" \
          "${HOME}/miniconda3" \
          "${HOME}/miniforge3" \
          "${HOME}/mambaforge" \
          "${HOME}/anaconda3" \
          "${_parent}/conda" \
          "$BIO_ROOT/conda"
        do
          [[ -n "$_base" && -x "${_base%/}/envs/af3_blackwell/bin/python" ]] || continue
          BW_ENV="${_base%/}/envs/af3_blackwell"
          break
        done
      fi
    fi
    # Defaults for a fresh install when nothing exists yet.
    BW_ROOT="${BW_ROOT:-${AF3_BLACKWELL_ROOT:-${_parent:-$BIO_ROOT}/af3_blackwell}}"
    if [[ -z "$BW_ENV" ]]; then
      if command -v conda >/dev/null 2>&1; then
        _base="$(conda info --base 2>/dev/null || true)"
        BW_ENV="${AF3_BLACKWELL_ENV:-${_base:+${_base%/}/envs/af3_blackwell}}"
      fi
      BW_ENV="${BW_ENV:-${HOME}/miniconda3/envs/af3_blackwell}"
    fi
    if [[ "$GPU_CC" == 12.* ]]; then
      echo "[af3] Blackwell CC $GPU_CC detected; preserving delivery af3 env"
    else
      echo "[af3] AF3_STACK=blackwell forced (GPU CC=${GPU_CC:-unknown}); preserving delivery af3 env"
    fi
    echo "[af3] discovered BW_ROOT=$BW_ROOT BW_ENV=$BW_ENV"
    if [[ ! -x "$BW_ENV/bin/python" || ! -f "$BW_ROOT/alphafold3/run_alphafold.py" ]]; then
      echo "[af3] installing isolated Blackwell stack via scripts/setup/setup_af3_blackwell.sh"
      AF3_ROOT="$BW_ROOT" ENV_PREFIX="$BW_ENV" AF3_BLACKWELL_ROOT="$BW_ROOT" \
        timeout "$(_budget_left)" bash "$SCRIPT_DIR/setup_af3_blackwell.sh" \
        || { _write_status deferred "blackwell_setup_timeout_or_fail"; return 0; }
      # Re-read after install (script may resolve a slightly different prefix).
      BW_ROOT="${AF3_BLACKWELL_ROOT:-$BW_ROOT}"
      [[ -x "$BW_ENV/bin/python" ]] || BW_ENV="$(dirname "$(dirname "$BW_ENV")")/af3_blackwell"
    fi
    AF3_DIR="$BW_ROOT/alphafold3"
    AF3_PYTHON="$BW_ENV/bin/python"
    AF3_PARAMS="${AF3_PARAMS:-$DELIVERY_ROOT/af3_assets/alphafold_param}"
    AF3_CACHE="${AF3_CACHE:-$BW_ROOT/alphafold_cache}"
    export AF3_DIR AF3_PYTHON AF3_PARAMS AF3_CACHE AF3_BLACKWELL_ROOT="$BW_ROOT"
    mkdir -p "$AF3_CACHE"
    echo "[af3] real Blackwell inference smoke ..."
    set +e
    timeout "$(_budget_left)" "$AF3_PYTHON" \
      "$DELIVERY_ROOT/agent/tools/structure/structure_predict_af3.py" --json \
      "{\"sequence\":\"MQIFVKTLTGKTITLEVEPSDTIENVKAKIQDKEGIPPDQQRLIFAGKQLEDGRTLSDYNIQKESTLHLVLRLRGG\",\"name\":\"ubq_blackwell_setup\",\"out_dir\":\"$AGENT_ROOT/artifacts/diag/af3_ubq_blackwell_setup\"}" \
      > /tmp/af3_blackwell_setup.out 2> /tmp/af3_blackwell_setup.err
    local bw_ec=$?
    set -e
    if grep -q '"ok": true' /tmp/af3_blackwell_setup.out 2>/dev/null; then
      _write_status ok "real_blackwell_inference_passed; compute_cap=$GPU_CC"
    else
      _write_status deferred "blackwell_inference_failed_ec=$bw_ec"
      echo "[af3] inspect /tmp/af3_blackwell_setup.err" >&2
    fi
    echo "[af3] Blackwell stack: AF3_PYTHON=$AF3_PYTHON"
    return 0
  fi
  if [[ ! -f "$YML" ]]; then
    echo "ERROR: missing $YML" >&2
    _write_status missing "no_af3_env_yml"
    return 1
  fi
  command -v conda >/dev/null || { echo "ERROR: conda required" >&2; return 1; }

  _stop_if_over || return 0
  if ! conda env list 2>/dev/null | awk '{print $1}' | grep -qx af3; then
    echo "[af3] creating env via delivery setup_af3.sh ..."
    # shellcheck disable=SC1091
    source "$DELIVERY_ROOT/agent/setup.sh"
    timeout "$(_budget_left)" bash "$DELIVERY_ROOT/agent/setup_af3.sh" \
      || { _write_status deferred "setup_af3_timeout_or_fail"; return 0; }
  fi

  local AF3_PY
  AF3_PY="$(conda run -n af3 which python 2>/dev/null || true)"
  if [[ -z "$AF3_PY" || ! -x "$AF3_PY" ]]; then
    _write_status missing "no_af3_python"
    return 1
  fi
  export AF3_PYTHON="$AF3_PY"
  echo "[af3] AF3_PYTHON=$AF3_PYTHON"

  _stop_if_over || return 0
  echo "[af3] ensure jax/triton pins from af3_env.yml ..."
  local PINS=()
  mapfile -t PINS < <(python - <<PY
from pathlib import Path
pins, in_pip = [], False
for line in Path(r"$YML").read_text().splitlines():
    s = line.strip()
    if s.startswith("- pip:"):
        in_pip = True
        continue
    if in_pip:
        if s.startswith("- ") and "==" in s:
            pins.append(s[2:].strip())
        elif s and not s.startswith("-") and not s.startswith("#"):
            break
want = [p for p in pins if p.split("==")[0] in (
    "jax", "jaxlib", "triton", "jax-cuda12-pjrt", "jax-cuda12-plugin",
)]
for p in want:
    print(p)
PY
)
  if ((${#PINS[@]})); then
    timeout "$(_budget_left)" "$AF3_PY" -m pip install --no-deps \
      -i "$PIP_INDEX" --trusted-host "$PIP_HOST" "${PINS[@]}" -q \
      || true
  fi

  _stop_if_over || return 0
  echo "[af3] bump nvidia-cuda-nvcc-cu12 (≥12.8) for new GPUs ..."
  timeout "$(_budget_left)" "$AF3_PY" -m pip install -U 'nvidia-cuda-nvcc-cu12>=12.8' \
    -i "$PIP_INDEX" --trusted-host "$PIP_HOST" -q \
    || echo "[af3] WARN: nvcc bump skipped"

  _stop_if_over || return 0
  echo "[af3] import verify ..."
  if ! "$AF3_PY" - <<'PY'
import jax, triton
import alphafold3  # noqa: F401
print("jax", jax.__version__, "triton", triton.__version__, "devices", jax.devices())
# AF3 historically pinned jax 0.4.*; accept 0.4+ (0.5/0.6 stacks are deferred-capable).
_jv = tuple(int(x) for x in jax.__version__.split(".")[:2])
assert _jv >= (0, 4), jax.__version__
print("import OK")
PY
  then
    # Imports failed: prefer deferred (AFDB path still valid) over broken hard-stop.
    _write_status deferred "import_failed_use_afdb"
    return 0
  fi

  _stop_if_over || return 0
  if [[ "${AF3_SKIP_SMOKE:-0}" == "1" ]]; then
    _write_status import_ok "smoke_skipped"
  else
    echo "[af3] short inference smoke (remaining $(_budget_left)s) ..."
    export AF3_DIR AF3_PARAMS="${AF3_PARAMS:-$DELIVERY_ROOT/af3_assets/alphafold_param}"
    export AF3_CACHE="${AF3_CACHE:-/tmp/af3_cache}"
    mkdir -p "$AF3_CACHE"
    set +e
    timeout "$(_budget_left)" "$AF3_PY" \
      "$DELIVERY_ROOT/agent/tools/structure/structure_predict_af3.py" --json \
      '{"sequence":"MQIFVKTLTGKTITLEVEPSDTIENVKAKIQDKEGIPPDQQRLIFAGKQLEDGRTLSDYNIQKESTLHLVLRLRGG","name":"ubq"}' \
      > /tmp/af3_budget_smoke.out 2> /tmp/af3_budget_smoke.err
    local ec=$?
    set -e
    if grep -q '"ok": true' /tmp/af3_budget_smoke.out 2>/dev/null; then
      _write_status ok "smoke_passed"
    else
      local note="smoke_failed_ec=${ec}; Blackwell/Triton often needs newer jax — defer"
      echo "[af3] inference smoke failed (imports OK). $note"
      echo "[af3] Agent can still use AFDB via structure_fetch / struct_similarity."
      _write_status deferred "$note"
    fi
  fi

  local ENVF="$AGENT_ROOT/.env"
  if [[ -f "$ENVF" ]]; then
    if grep -q '^AF3_PYTHON=' "$ENVF"; then
      sed -i "s|^AF3_PYTHON=.*|AF3_PYTHON=$AF3_PYTHON|" "$ENVF"
    else
      echo "AF3_PYTHON=$AF3_PYTHON" >> "$ENVF"
    fi
  fi
  echo "[af3] done (elapsed $(( $(date +%s) - _START ))s)"
  return 0
}

# ---------------------------------------------------------------------------
# Import-level science env verify + heal (name existence ≠ packages ready).
# Delivery setup_envs.sh skips pip when the env name already exists, so a
# hollow `conda create -n rhobind` would otherwise stay broken forever.
# ---------------------------------------------------------------------------
_conda_env_exists() {
  conda env list 2>/dev/null | awk '{print $1}' | grep -qx "$1"
}

_verify_science_envs() {
  local fail=0
  local req="${RHOBIND_RELEASE}/requirements.txt"
  local yml_pe="${DELIVERY_ROOT}/agent/envs/protein_embed.yml"
  local yml_rna="${DELIVERY_ROOT}/agent/envs/rna.yml"
  local _env

  echo "[2a/6] verify science envs (import/probe; heal hollow envs) ..."

  for _env in protein_embed rna rhobind af3; do
    if _conda_env_exists "$_env"; then
      echo "  [ok name] conda env $_env"
    else
      echo "  [FAIL] conda env $_env missing" >&2
      fail=1
    fi
  done
  if [[ "$fail" == "1" ]]; then
    echo "ERROR: full science stack incomplete. Re-run setup_envs or fix conda." >&2
    return 1
  fi

  # --- rhobind: torch + transformers (RhoBind predict) ---
  # Prefer data-disk tmp/cache: root overlay is often ~30G and fills on CUDA wheels.
  local _data_root="${BIO_ROOT:-${TMPDIR:-/tmp}}"
  # Prefer BIO_ROOT (sibling layout) for pip tmp/cache so root overlay is not filled.
  local _data_tmp="${_data_root}/tmp"
  local _pip_cache="${_data_root}/pip-cache"
  local _wheel_cpu="${_data_root}/wheels/torch-2.13.0+cpu-cp312-cp312-manylinux_2_28_x86_64.whl"
  mkdir -p "$_data_tmp" "$_pip_cache" "$(dirname "$_wheel_cpu")"
  export TMPDIR="$_data_tmp" TMP="$_data_tmp" PIP_CACHE_DIR="$_pip_cache"

  if conda run -n rhobind python -c "import torch, transformers" >/dev/null 2>&1; then
    echo "  [ok] rhobind: torch + transformers"
  else
    echo "  [heal] rhobind: missing torch/transformers — install to data-disk tmp/cache ..."
    echo "  note: plain 'pip install -r requirements.txt' pulls CUDA torch (~GB) onto / and often hits ENOSPC"
    local _healed=0
    # 1) Local CPU wheel if present (fast, small enough for smoke / CPU predict)
    if [[ -f "$_wheel_cpu" ]]; then
      echo "  [heal] trying local CPU wheel: $_wheel_cpu"
      if conda run -n rhobind env TMPDIR="$_data_tmp" PIP_CACHE_DIR="$_pip_cache" \
          pip install "$_wheel_cpu" \
          && conda run -n rhobind env TMPDIR="$_data_tmp" PIP_CACHE_DIR="$_pip_cache" \
          pip install 'transformers>=4.44,<5.6' tokenizers 'numpy>=1.26' 'scikit-learn>=1.3' 'einops>=0.7' \
            -i "${PIP_INDEX_URL:-https://pypi.tuna.tsinghua.edu.cn/simple}" \
            --trusted-host "${PIP_TRUSTED_HOST:-pypi.tuna.tsinghua.edu.cn}"
      then
        _healed=1
      fi
    fi
    # 2) PyTorch CPU index (no CUDA megapack)
    if [[ "$_healed" != "1" ]]; then
      echo "  [heal] trying torch CPU index + transformers (tuna) ..."
      if conda run -n rhobind env TMPDIR="$_data_tmp" PIP_CACHE_DIR="$_pip_cache" \
          pip install torch --index-url https://download.pytorch.org/whl/cpu \
        && conda run -n rhobind env TMPDIR="$_data_tmp" PIP_CACHE_DIR="$_pip_cache" \
          pip install 'transformers>=4.44,<5.6' tokenizers 'numpy>=1.26' 'scikit-learn>=1.3' 'einops>=0.7' \
            -i "${PIP_INDEX_URL:-https://pypi.tuna.tsinghua.edu.cn/simple}" \
            --trusted-host "${PIP_TRUSTED_HOST:-pypi.tuna.tsinghua.edu.cn}"
      then
        _healed=1
      fi
    fi
    # 3) Full release requirements (CUDA) only if enough free space on /
    if [[ "$_healed" != "1" && -f "$req" ]]; then
      local _avail_kb
      _avail_kb="$(df -Pk / | awk 'NR==2{print $4}')"
      if [[ "${_avail_kb:-0}" -gt 8000000 ]]; then
        echo "  [heal] fallback: pip install -r requirements.txt (CUDA; needs ≥8GiB free on /) ..."
        conda run -n rhobind env TMPDIR="$_data_tmp" PIP_CACHE_DIR="$_pip_cache" \
          pip install -r "$req" \
          -i "${PIP_INDEX_URL:-https://pypi.tuna.tsinghua.edu.cn/simple}" \
          --trusted-host "${PIP_TRUSTED_HOST:-pypi.tuna.tsinghua.edu.cn}" \
          && _healed=1 || true
      else
        echo "  [heal] skip CUDA requirements.txt: only ~$((_avail_kb/1024))MiB free on / (need ≥8GiB)" >&2
      fi
    fi
    if conda run -n rhobind python -c "import torch, transformers" >/dev/null 2>&1; then
      echo "  [healed] rhobind: torch + transformers"
    else
      echo "  [FAIL] rhobind still cannot import torch + transformers after heal" >&2
      echo "  hint: free space on / OR:" >&2
      echo "    wget -c -O $_wheel_cpu 'https://download.pytorch.org/whl/cpu/torch-2.13.0%2Bcpu-cp312-cp312-manylinux_2_28_x86_64.whl'" >&2
      echo "    conda run -n rhobind pip install $_wheel_cpu && conda run -n rhobind pip install transformers einops ..." >&2
      return 1
    fi
  fi
  conda run -n rhobind python -c \
    "import transformers, torch; print('  rhobind OK transformers', transformers.__version__, 'torch', torch.__version__, 'cuda', torch.cuda.is_available())"

  # --- protein_embed: transformers (ESM path) ---
  if conda run -n protein_embed python -c "import transformers" >/dev/null 2>&1; then
    echo "  [ok] protein_embed: transformers"
  else
    echo "  [heal] protein_embed: missing transformers — conda env update from yml ..."
    if [[ ! -f "$yml_pe" ]]; then
      echo "  [FAIL] protein_embed yml not found: $yml_pe" >&2
      return 1
    fi
    if ! conda env update -n protein_embed -f "$yml_pe"; then
      echo "  [FAIL] protein_embed conda env update" >&2
      return 1
    fi
    if conda run -n protein_embed python -c "import transformers" >/dev/null 2>&1; then
      echo "  [healed] protein_embed: transformers"
    else
      echo "  [FAIL] protein_embed still cannot import transformers after heal" >&2
      return 1
    fi
  fi
  conda run -n protein_embed python -c \
    "import transformers; print('  protein_embed (ESM) OK transformers', transformers.__version__)"

  # --- rna: mmseqs on PATH inside env ---
  # Use bash -c (not -lc): login shells reset PATH and drop conda env/bin.
  if conda run -n rna bash -c 'command -v mmseqs >/dev/null 2>&1'; then
    echo "  [ok] rna: mmseqs"
  else
    echo "  [heal] rna: mmseqs missing — conda env update from yml ..."
    if [[ ! -f "$yml_rna" ]]; then
      echo "  [FAIL] rna yml not found: $yml_rna" >&2
      return 1
    fi
    if ! conda env update -n rna -f "$yml_rna"; then
      echo "  [FAIL] rna conda env update" >&2
      return 1
    fi
    if conda run -n rna bash -c 'command -v mmseqs >/dev/null 2>&1'; then
      echo "  [healed] rna: mmseqs"
    else
      echo "  [FAIL] rna still has no mmseqs after heal" >&2
      return 1
    fi
  fi

  # --- af3: usable interpreter (AF3_PYTHON or conda env af3) ---
  if [[ -x "${AF3_PYTHON:-}" && "${AF3_PYTHON}" != "/bin/false" ]]; then
    echo "  [ok] af3: python=$AF3_PYTHON"
  else
    local _af3py
    _af3py="$(conda run -n af3 which python 2>/dev/null || true)"
    if [[ -n "$_af3py" && -x "$_af3py" ]]; then
      export AF3_PYTHON="$_af3py"
      echo "  [ok] af3: python=$AF3_PYTHON"
    else
      echo "  [FAIL] af3 env has no usable python" >&2
      return 1
    fi
  fi

  return 0
}

# =============================================================================
_ensure_nanobot
NANOBOT_SRC="${NANOBOT_SRC}"
export NANOBOT_SRC

echo "=============================================="
echo " nanobot-bio setup (Linux / slim in-repo nanobot)"
echo "=============================================="
echo "  BIO_ROOT      = $BIO_ROOT"
echo "  AGENT_ROOT    = $AGENT_ROOT"
echo "  DELIVERY_ROOT = $DELIVERY_ROOT"
echo "  NANOBOT_SRC   = $NANOBOT_SRC"
echo "  AF3_STACK     = $AF3_STACK"
echo "  OS            = $(uname -s)"
echo

if [[ "$(uname -s)" != "Linux" ]]; then
  echo "WARNING: uname=$(uname -s). Official setup target is Linux SSH server." >&2
fi

if [[ ! -d "$DELIVERY_ROOT/agent" ]]; then
  echo "ERROR: delivery missing: $DELIVERY_ROOT" >&2
  exit 1
fi

echo "[1/6] apply delivery env (no AF3 conda probe)"
_bundle="$DELIVERY_ROOT"
export BUNDLE_ROOT="$_bundle"
export AGENT_DB="${AGENT_DB:-$_bundle/agent_db}"
export RBP_PROTEINS="${RBP_PROTEINS:-$_bundle/reference}"
export RHOBIND_RELEASE="${RHOBIND_RELEASE:-$_bundle/release/rhobind_release_v1}"
export USALIGN="${USALIGN:-$AGENT_DB/bin/USalign}"
export PEAKS_DB="${PEAKS_DB:-$AGENT_DB/peaks_db/peaks}"
export TRANSFER_DIR="${TRANSFER_DIR:-$AGENT_DB/transfer}"
export AFDB_DIR="${AFDB_DIR:-$RBP_PROTEINS/structures/afdb}"
export EMB_BANK="${EMB_BANK:-$AGENT_DB/embedding_bank}"
export FOLDSEEK_DB="${FOLDSEEK_DB:-$AGENT_DB/foldseek_db/refs}"
export SEQ_DB="${SEQ_DB:-$AGENT_DB/seq_db/refs}"
export RBP_REGISTRY="${RBP_REGISTRY:-$AGENT_DB/registry/rbp_registry.json}"
export AF3_DIR="${AF3_DIR:-$_bundle/agent/third_party/alphafold3}"
export AF3_PARAMS="${AF3_PARAMS:-$_bundle/af3_assets/alphafold_param}"
export AF3_CACHE="${AF3_CACHE:-/tmp/af3_cache}"
export AF3_PYTHON="${AF3_PYTHON:-/bin/false}"
echo "  AGENT_DB=$AGENT_DB"
echo "  RHOBIND_RELEASE=$RHOBIND_RELEASE"

if [[ "$WITH_CONDA" == "1" ]]; then
  echo "[2/6] delivery setup_envs.sh (protein_embed=ESM / rna / rhobind / af3) ..."
  if command -v conda >/dev/null 2>&1; then
    bash "$DELIVERY_ROOT/agent/setup_envs.sh"
    _verify_science_envs || exit 1
    if [[ "$SKIP_AF3" != "1" ]]; then
      echo "[2b/6] AF3 harden (budget ${AF3_BUDGET_SEC:-600}s; deferred ≠ setup fail) ..."
      AF3_BUDGET_SEC="${AF3_BUDGET_SEC:-600}" _setup_af3 \
        || echo "  WARN: AF3 harden exited non-zero (science stack still usable via AFDB)" >&2
      _af3_st="$(_af3_status_default)"
      if [[ ! -f "$_af3_st" && -f "$AGENT_ROOT/.af3_status" ]]; then
        _af3_st="$AGENT_ROOT/.af3_status"  # legacy in-repo path (read-only fallback)
      fi
      if [[ -f "$_af3_st" ]]; then
        echo "  AF3 status ($_af3_st): $(tr '\n' ' ' < "$_af3_st")"
      fi
    else
      echo "[2b/6] skip AF3 harden (--skip-af3)"
    fi
  else
    echo "ERROR: conda not found — cannot build full science stack." >&2
    echo "  Install conda, or re-run with --skip-conda (agent-only, no RhoBind/ESM/AF3)." >&2
    exit 1
  fi
else
  echo "[2/6] skip delivery conda (--skip-conda: agent venv only, no science envs)"
fi

echo "[3/6] Resolving Python >= 3.13 for nanobot ..."
pick_python() {
  local c
  for c in python3.13 python3.14 python3 python; do
    if command -v "$c" >/dev/null 2>&1; then
      if "$c" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 13) else 1)' 2>/dev/null; then
        echo "$c"
        return 0
      fi
    fi
  done
  return 1
}

PYTHON_BIN=""
if PYTHON_BIN="$(pick_python)"; then
  echo "  using $($PYTHON_BIN -V)"
else
  echo "  trying conda env rbp_nanobot (python 3.13) ..."
  if ! command -v conda >/dev/null 2>&1; then
    echo "ERROR: need Python>=3.13 or conda" >&2
    exit 1
  fi
  # shellcheck disable=SC1091
  eval "$(conda shell.bash hook)"
  if ! conda env list | awk '{print $1}' | grep -qx 'rbp_nanobot'; then
    conda create -y -n rbp_nanobot python=3.13
  fi
  conda activate rbp_nanobot
  PYTHON_BIN=python
  echo "  using conda rbp_nanobot: $($PYTHON_BIN -V)"
fi

echo "[4/6] venv + pip + nanobot ..."
if [[ ! -d "$AGENT_ROOT/.venv" ]]; then
  "$PYTHON_BIN" -m venv "$AGENT_ROOT/.venv"
fi
# shellcheck disable=SC1091
source "$AGENT_ROOT/.venv/bin/activate"
python -m pip install -U pip setuptools wheel
if [[ ! -f "$AGENT_ROOT/requirements.lock" ]]; then
  echo "ERROR: missing $AGENT_ROOT/requirements.lock (sole App pip pin file)" >&2
  exit 1
fi
echo "  pip install -r requirements.lock (pinned runtime)"
python -m pip install -r "$AGENT_ROOT/requirements.lock"

echo "  install nanobot-bio (includes in-repo slim nanobot) ..."
# Drop legacy PyPI nanobot-ai / sibling .pth that would shadow in-repo package
python -m pip uninstall -y nanobot-ai nanobot 2>/dev/null || true
_SITE="$(python -c 'import site; print(site.getsitepackages()[0])')"
rm -f "$_SITE"/_nanobot_src.pth \
  "$_SITE"/__editable__.nanobot-*.pth \
  "$_SITE"/__editable___nanobot_*_finder.py 2>/dev/null || true
# A physical site-packages/nanobot/ dir (no __init__.py, stray agent/+skills/ from
# an old install) shadows the editable in-repo package as a namespace package — drop it.
if [[ -d "$_SITE/nanobot" && ! -L "$_SITE/nanobot" && ! -f "$_SITE/nanobot/__init__.py" ]]; then
  echo "  removing stray namespace dir $_SITE/nanobot"
  rm -rf "$_SITE/nanobot" 2>/dev/null || true
fi
# Corrupt half-installed torch leftovers (~orch, ~unctorch, …) spam pip warnings.
rm -rf "$_SITE"/~orch* "$_SITE"/~unctorch* "$_SITE"/~orchgen* 2>/dev/null || true
export NANOBOT_SRC="$AGENT_ROOT/nanobot"
export NANOBOT_BIO_ROOT="$AGENT_ROOT"
export NANOBOT_WORKSPACE="$AGENT_ROOT/workspace"
python -m pip install -e "${AGENT_ROOT}[dev]"
# Verify from $AGENT_ROOT with PYTHONSAFEPATH so a sibling bio_agent/nanobot on the
# launch-dir CWD can never shadow the in-repo slim package (root cause of the
# "AssertionError: .../bio_agent/nanobot/__init__.py" when setup is run from BIO_ROOT).
( cd "$AGENT_ROOT" && PYTHONSAFEPATH=1 python -c "
import nanobot
from nanobot.agent.tools.core.base import Tool
p = (nanobot.__file__ or '').replace('\\\\', '/')
print('  nanobot OK', p)
assert 'nanobot-bio' in p, p
" )
python -m app.sync_overlay
( cd "$AGENT_ROOT" && PYTHONSAFEPATH=1 python -c "from nanobot.agent.tools.rbp.predict import PredictInteractionTool; print('  nanobot.agent.tools.rbp OK', PredictInteractionTool)" )

echo "[5/6] .env + workspace skill ..."
# AF3_PYTHON must be a conda AF3 interpreter (classic `af3` or `af3_blackwell`).
# Never accept the agent .venv python — that is the exact misconfig we are fixing.
_AF3_PY="${AF3_PYTHON:-/bin/false}"
_af3_py_ok=0
if [[ -x "$_AF3_PY" && "$_AF3_PY" != *"/.venv/"* ]]; then
  # classic: .../envs/af3/bin/python (path contains /af3/); blackwell: .../af3_blackwell/...
  if [[ "$_AF3_PY" == *"af3_blackwell"* && "${AF3_STACK:-auto}" != "classic" ]]; then
    _af3_py_ok=1
  elif [[ "$_AF3_PY" == *"/af3/"* && "$_AF3_PY" != *"af3_blackwell"* && "${AF3_STACK:-auto}" != "blackwell" ]]; then
    _af3_py_ok=1
  fi
fi
if [[ "$_af3_py_ok" != "1" ]]; then
  _AF3_PY="/bin/false"
  # Candidate order follows AF3_STACK so classic machines do not pick a
  # blackwell interpreter (and vice versa).
  _af3_cands=()
  _gpu_cc="$(nvidia-smi --query-gpu=compute_cap --format=csv,noheader 2>/dev/null | awk 'NR==1{print; exit}' || true)"
  case "${AF3_STACK:-auto}" in
    blackwell) _prefer_bw=1 ;;
    classic) _prefer_bw=0 ;;
    auto) [[ "$_gpu_cc" == 12.* ]] && _prefer_bw=1 || _prefer_bw=0 ;;
  esac
  _conda_base="$(conda info --base 2>/dev/null || true)"
  if [[ -n "${CONDA_ENVS_PATH:-}" ]]; then
    IFS=':' read -r -a _cep_dirs <<< "$CONDA_ENVS_PATH"
  else
    _cep_dirs=()
  fi
  if [[ "$_prefer_bw" == "1" ]]; then
    for _d in "${_cep_dirs[@]}"; do
      [[ -n "$_d" ]] && _af3_cands+=("${_d%/}/af3_blackwell/bin/python")
    done
    [[ -n "$_conda_base" ]] && _af3_cands+=("${_conda_base%/}/envs/af3_blackwell/bin/python")
    _af3_cands+=(
      "$HOME/miniconda3/envs/af3_blackwell/bin/python"
      "$HOME/miniforge3/envs/af3_blackwell/bin/python"
    )
  fi
  for _d in "${_cep_dirs[@]}"; do
    [[ -n "$_d" ]] && _af3_cands+=("${_d%/}/af3/bin/python")
  done
  [[ -n "$_conda_base" ]] && _af3_cands+=("${_conda_base%/}/envs/af3/bin/python")
  _af3_cands+=(
    "$HOME/miniconda3/envs/af3/bin/python"
    "$HOME/miniforge3/envs/af3/bin/python"
    "$HOME/mambaforge/envs/af3/bin/python"
    "$HOME/anaconda3/envs/af3/bin/python"
  )
  for _c in "${_af3_cands[@]}"; do
    [[ -x "$_c" ]] && _AF3_PY="$_c" && break
  done
  if [[ "$_AF3_PY" == "/bin/false" ]] && command -v conda >/dev/null 2>&1; then
    _env_order=(af3)
    [[ "$_prefer_bw" == "1" ]] && _env_order=(af3_blackwell af3)
    for _env in "${_env_order[@]}"; do
      if conda env list 2>/dev/null | awk '{print $1}' | grep -qx "$_env"; then
        _cand="$(conda run -n "$_env" which python 2>/dev/null || true)"
        if [[ -x "$_cand" ]]; then
          _AF3_PY="$_cand"
          break
        fi
      fi
    done
  fi
fi
export AF3_PYTHON="${_AF3_PY:-/bin/false}"

cat > "$AGENT_ROOT/.env" <<EOF
# Generated by setup_all.sh on Linux server
BIO_ROOT=$BIO_ROOT
DELIVERY_ROOT=$DELIVERY_ROOT
NANOBOT_SRC=$NANOBOT_SRC
NANOBOT_BIO_ROOT=$AGENT_ROOT
NANOBOT_WORKSPACE=$AGENT_ROOT/workspace
AGENT_DB=${AGENT_DB:-$DELIVERY_ROOT/agent_db}
RBP_REGISTRY=${RBP_REGISTRY:-$DELIVERY_ROOT/agent_db/registry/rbp_registry.json}
RHOBIND_RELEASE=${RHOBIND_RELEASE:-$DELIVERY_ROOT/release/rhobind_release_v1}
RBP_PROTEINS=${RBP_PROTEINS:-$DELIVERY_ROOT/reference}
AFDB_DIR=${AFDB_DIR:-$DELIVERY_ROOT/reference/structures/afdb}
TRANSFER_DIR=${TRANSFER_DIR:-$DELIVERY_ROOT/agent_db/transfer}
EMB_BANK=${EMB_BANK:-$DELIVERY_ROOT/agent_db/embedding_bank}
FOLDSEEK_DB=${FOLDSEEK_DB:-$DELIVERY_ROOT/agent_db/foldseek_db/refs}
SEQ_DB=${SEQ_DB:-$DELIVERY_ROOT/agent_db/seq_db/refs}
PEAKS_DB=${PEAKS_DB:-$DELIVERY_ROOT/agent_db/peaks_db/peaks}
USALIGN=${USALIGN:-$DELIVERY_ROOT/agent_db/bin/USalign}
AF3_DIR=${AF3_DIR:-$DELIVERY_ROOT/agent/third_party/alphafold3}
AF3_PARAMS=${AF3_PARAMS:-$DELIVERY_ROOT/af3_assets/alphafold_param}
AF3_PYTHON=${AF3_PYTHON:-/bin/false}
RHOBIND_DEVICE=${RHOBIND_DEVICE:-auto}
RBP_BACKEND=delivery
EOF

chmod +x "$SCRIPT_DIR/setup_all.sh" 2>/dev/null || true

mkdir -p "$AGENT_ROOT/workspace/skills/rbp-agent" \
  "$AGENT_ROOT/workspace/memory"
PYTHONPATH="$AGENT_ROOT${PYTHONPATH:+:$PYTHONPATH}" python3 -c "
from app.core.paths import ensure_artifact_dirs, migrate_flat_artifacts
ensure_artifact_dirs()
migrate_flat_artifacts()
print('[setup] artifacts dirs OK')
" || mkdir -p \
  "$AGENT_ROOT/artifacts/traces" \
  "$AGENT_ROOT/artifacts/sessions" \
  "$AGENT_ROOT/artifacts/reports/json" \
  "$AGENT_ROOT/artifacts/reports/md" \
  "$AGENT_ROOT/artifacts/reports/csv" \
  "$AGENT_ROOT/artifacts/memory" \
  "$AGENT_ROOT/artifacts/cache" \
  "$AGENT_ROOT/artifacts/logs" \
  "$AGENT_ROOT/artifacts/diag"
# Always sync SoT plugin overlay → runtime + workspace
echo "[sync] plugin overlay → NANOBOT_SRC + workspace ..."
export PYTHONPATH="$BIO_ROOT:$AGENT_ROOT${PYTHONPATH:+:$PYTHONPATH}"
python -m app.sync_overlay || {
  echo "WARN: sync_overlay failed (NANOBOT_SRC may be incomplete); doctor will retry" >&2
}
# Ensure workspace skill marker stays present after sync
cat > "$AGENT_ROOT/workspace/skills/rbp-agent/DO_NOT_EDIT.md" <<'EOF'
# Generated by sync — do not hand-edit

Edit the SoT (source-of-truth) instead:

  nanobot/skills/rbp-agent/SKILL.md

Then run: `python -m app.sync_overlay` or `rbp-agent doctor`.
EOF

if [[ "$SKIP_SMOKE" != "1" ]]; then
  echo "[6/6] Smoke + verify ..."
  python -m app doctor
  python -m app nanobot-smoke || true
else
  echo "[6/6] skip smoke"
fi

_STAMP="$AGENT_ROOT/.setup_complete"
{
  echo "setup_all_ts=$(date -Iseconds 2>/dev/null || date)"
  echo "with_conda=$WITH_CONDA"
  echo "nanobot_src=$NANOBOT_SRC"
  echo "af3_python=$AF3_PYTHON"
  echo "python=$(command -v python 2>/dev/null || true)"
} > "$_STAMP"
echo "  wrote $_STAMP"

echo
echo " setup_all.sh done — full advanced env configured once."
echo " Every later SSH session:"
echo "   source $AGENT_ROOT/scripts/setup/activate_env.sh"
echo "   # or: source $AGENT_ROOT/.venv/bin/activate"
echo "   rbp-agent doctor && rbp-agent chat"
echo " Re-run full setup after pulls / new GPU host:"
echo "   bash $AGENT_ROOT/scripts/setup/setup_all.sh"
echo " Agent-only (no conda science): bash $AGENT_ROOT/scripts/setup/setup_all.sh --skip-conda"
