#!/usr/bin/env bash
# nanobot-bio — single portable entry for Linux
#   activate / status / doctor / setup / chat / start (all-in-one)
#
# Daily:
#   source scripts/nbio.sh
#   source scripts/nbio.sh activate
#   ./scripts/nbio.sh doctor
#   ./scripts/nbio.sh chat
#   ./scripts/nbio.sh start              # one-shot: probe paths + AF3 heal + chat
#   ./scripts/nbio.sh start --dry-run    # print auto-adapt result only; no chat
#
# First-time / repair (explicit; does NOT run on activate):
#   ./scripts/nbio.sh setup
#   ./scripts/nbio.sh setup --skip-conda
#
# Detect-only (no venv activate required for status when python available):
#   ./scripts/nbio.sh status
#
# Safe by design: activate never pip-installs CUDA/torch. Fix hollow envs via `setup`.

_NBIO_SELF="${BASH_SOURCE[0]:-$0}"
_NBIO_DIR="$(cd "$(dirname "$_NBIO_SELF")" && pwd)"
_AGENT_ROOT="$(cd "$_NBIO_DIR/.." && pwd)"
_BIO_ROOT="$(cd "${BIO_ROOT:-$_AGENT_ROOT/..}" && pwd)"
_DELIVERY_ROOT="${DELIVERY_ROOT:-$_BIO_ROOT/rhobind_agent_delivery}"
_NANOBOT_SRC_DEFAULT="$_AGENT_ROOT/nanobot"
_SETUP_ALL="$_AGENT_ROOT/scripts/setup/setup_all.sh"

_nbio_sourced=0
if [[ "${BASH_SOURCE[0]:-}" != "${0:-}" ]]; then
  _nbio_sourced=1
else
  set -euo pipefail
fi

_nbio_die() {
  echo "[nbio] ERROR: $*" >&2
  if [[ "$_nbio_sourced" == "1" ]]; then
    return 2
  fi
  exit 2
}

_nbio_omp_sane() {
  case "${1:-}" in
    ''|0|*[!0-9]*) return 1 ;;
    *) return 0 ;;
  esac
}

_nbio_gpu_cc() {
  nvidia-smi --query-gpu=compute_cap --format=csv,noheader 2>/dev/null \
    | awk 'NR==1{gsub(/ /,""); print; exit}' || true
}

# Prefer blackwell stack? 0=yes. Honors AF3_STACK=auto|classic|blackwell.
_nbio_prefer_blackwell() {
  local stack="${AF3_STACK:-auto}"
  local cc
  cc="$(_nbio_gpu_cc)"
  case "$stack" in
    blackwell) return 0 ;;
    classic) return 1 ;;
    *)
      [[ "$cc" == 12.* ]] && return 0
      return 1
      ;;
  esac
}

# Candidate roots for af3_blackwell (portable Linux layouts only).
_nbio_blackwell_root_candidates() {
  local parent agent_parent
  parent="$(cd "$_BIO_ROOT/.." 2>/dev/null && pwd || true)"
  agent_parent="$(cd "$_AGENT_ROOT/.." 2>/dev/null && pwd || true)"
  [[ -n "${AF3_BLACKWELL_ROOT:-}" ]] && printf '%s\n' "${AF3_BLACKWELL_ROOT}"
  [[ -n "${AF3_ROOT:-}" ]] && printf '%s\n' "${AF3_ROOT}"
  # If AF3_DIR already points at …/af3_blackwell/alphafold3, include its parent.
  if [[ -n "${AF3_DIR:-}" && "${AF3_DIR}" == *"af3_blackwell"* ]]; then
    printf '%s\n' "$(cd "$(dirname "${AF3_DIR}")" 2>/dev/null && pwd || true)"
  fi
  printf '%s\n' \
    "$_BIO_ROOT/af3_blackwell" \
    "${agent_parent}/af3_blackwell" \
    "${parent}/af3_blackwell" \
    "${HOME}/af3_blackwell" \
    "/opt/af3_blackwell"
}

_nbio_find_blackwell_root() {
  local r
  local -A seen=()
  while IFS= read -r r; do
    [[ -n "$r" ]] || continue
    r="${r%/}"
    [[ -n "${seen[$r]:-}" ]] && continue
    seen[$r]=1
    if [[ -f "${r}/alphafold3/run_alphafold.py" ]]; then
      printf '%s\n' "$r"
      return 0
    fi
  done < <(_nbio_blackwell_root_candidates)
  return 1
}

# Candidate python binaries for a named conda env (portable Linux layouts).
_nbio_af3_python_candidates() {
  local name="$1"
  local _d _base _py parent
  parent="$(cd "$_BIO_ROOT/.." 2>/dev/null && pwd || true)"
  # Explicit ENV_PREFIX when it is this env.
  if [[ -n "${ENV_PREFIX:-}" ]]; then
    case "${ENV_PREFIX}" in
      */"${name}"|*/"${name}/") printf '%s\n' "${ENV_PREFIX%/}/bin/python" ;;
    esac
  fi
  if [[ -n "${AF3_BLACKWELL_ENV:-}" && "$name" == "af3_blackwell" ]]; then
    printf '%s\n' "${AF3_BLACKWELL_ENV%/}/bin/python"
  fi
  if [[ -n "${CONDA_ENVS_PATH:-}" ]]; then
    IFS=':' read -r -a _dirs <<< "$CONDA_ENVS_PATH"
    for _d in "${_dirs[@]}"; do
      [[ -n "$_d" ]] || continue
      printf '%s\n' "${_d%/}/${name}/bin/python"
    done
  fi
  if [[ -n "${CONDA_ENVS_DIRS:-}" ]]; then
    IFS=':' read -r -a _dirs <<< "$CONDA_ENVS_DIRS"
    for _d in "${_dirs[@]}"; do
      [[ -n "$_d" ]] || continue
      printf '%s\n' "${_d%/}/${name}/bin/python"
    done
  fi
  if command -v conda >/dev/null 2>&1; then
    _base="$(conda info --base 2>/dev/null || true)"
    if [[ -n "$_base" ]]; then
      printf '%s\n' "${_base%/}/envs/${name}/bin/python"
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
    # CONDA_PREFIX may be an env itself → sibling envs live next door.
    if [[ "$(basename "${_base%/}")" == "$name" ]]; then
      printf '%s\n' "${_base%/}/bin/python"
    fi
    printf '%s\n' "${_base%/}/envs/${name}/bin/python"
    if [[ "$(basename "${_base%/}")" != "envs" ]]; then
      printf '%s\n' "$(dirname "${_base%/}")/envs/${name}/bin/python"
    fi
  done
}

_nbio_find_af3_python_named() {
  # $1 = env name: af3_blackwell | af3
  local name="$1"
  local _py
  local -A seen=()
  while IFS= read -r _py; do
    [[ -n "$_py" ]] || continue
    [[ -n "${seen[$_py]:-}" ]] && continue
    seen[$_py]=1
    if [[ -x "$_py" ]]; then
      printf '%s\n' "$_py"
      return 0
    fi
  done < <(_nbio_af3_python_candidates "$name")
  if command -v conda >/dev/null 2>&1; then
    if conda env list 2>/dev/null | awk '{print $1}' | grep -qx "$name"; then
      _py="$(conda run -n "$name" which python 2>/dev/null || true)"
      if [[ -n "$_py" && -x "$_py" ]]; then
        printf '%s\n' "$_py"
        return 0
      fi
    fi
  fi
  return 1
}

# Print discovery candidates for this host (used by start --dry-run).
_nbio_print_path_discovery() {
  local r _py st
  echo "[nbio] === path discovery (this host; AutoDL is optional last resort) ==="
  echo "[nbio] BIO_ROOT (script)=$_BIO_ROOT"
  echo "[nbio] AGENT_ROOT=$_AGENT_ROOT"
  echo "[nbio] DELIVERY_ROOT (default)=$_DELIVERY_ROOT"
  echo "[nbio] af3_blackwell root candidates:"
  local -A seen_r=()
  while IFS= read -r r; do
    [[ -n "$r" ]] || continue
    r="${r%/}"
    [[ -n "${seen_r[$r]:-}" ]] && continue
    seen_r[$r]=1
    if [[ -f "${r}/alphafold3/run_alphafold.py" ]]; then
      st="OK"
    else
      st="miss"
    fi
    printf '[nbio]   %-6s %s\n' "$st" "$r"
  done < <(_nbio_blackwell_root_candidates)
  echo "[nbio] af3_blackwell python candidates:"
  local -A seen_p=()
  while IFS= read -r _py; do
    [[ -n "$_py" ]] || continue
    [[ -n "${seen_p[$_py]:-}" ]] && continue
    seen_p[$_py]=1
    if [[ -x "$_py" ]]; then
      st="OK"
    else
      st="miss"
    fi
    printf '[nbio]   %-6s %s\n' "$st" "$_py"
  done < <(_nbio_af3_python_candidates af3_blackwell)
  r="$(_nbio_find_blackwell_root 2>/dev/null || true)"
  _py="$(_nbio_find_af3_python_named af3_blackwell 2>/dev/null || true)"
  echo "[nbio] selected AF3_BLACKWELL_ROOT=${r:-missing}"
  echo "[nbio] selected af3_blackwell python=${_py:-missing}"
}

# After sourcing .env: prefer script-relative roots when .env paths are missing
# on this machine (do not treat a trial-host absolute path as authoritative).
_nbio_reconcile_roots() {
  export NANOBOT_BIO_ROOT="$_AGENT_ROOT"
  if [[ -z "${BIO_ROOT:-}" || ! -d "${BIO_ROOT}" ]]; then
    export BIO_ROOT="$_BIO_ROOT"
  elif [[ ! -d "${BIO_ROOT}/rhobind_agent_delivery" && ! -d "${BIO_ROOT}/nanobot-bio" \
        && "${BIO_ROOT}" != "$_BIO_ROOT" ]]; then
    echo "[nbio] WARN: .env BIO_ROOT=${BIO_ROOT} is invalid on this host → using $_BIO_ROOT" >&2
    export BIO_ROOT="$_BIO_ROOT"
  fi
  _BIO_ROOT="$BIO_ROOT"
  local _del_default="$_BIO_ROOT/rhobind_agent_delivery"
  if [[ -z "${DELIVERY_ROOT:-}" || ! -d "${DELIVERY_ROOT}" ]]; then
    if [[ -d "$_del_default" ]]; then
      export DELIVERY_ROOT="$_del_default"
    else
      export DELIVERY_ROOT="${DELIVERY_ROOT:-$_del_default}"
    fi
  fi
  _DELIVERY_ROOT="$DELIVERY_ROOT"
  export NANOBOT_WORKSPACE="${NANOBOT_WORKSPACE:-$_AGENT_ROOT/workspace}"
}

# Portable AF3 interpreter discovery (checkout-relative + standard conda layouts).
_nbio_discover_af3_python() {
  if [[ -n "${AF3_PYTHON:-}" && "${AF3_PYTHON}" != "/bin/false" && -x "${AF3_PYTHON}" ]]; then
    # Keep an explicit valid interpreter unless prefer_bw says we must switch.
    if _nbio_prefer_blackwell; then
      if [[ "${AF3_PYTHON}" == *"af3_blackwell"* ]]; then
        return 0
      fi
    else
      return 0
    fi
  fi
  local _py
  if _nbio_prefer_blackwell; then
    if _py="$(_nbio_find_af3_python_named af3_blackwell)"; then
      export AF3_PYTHON="$_py"
      return 0
    fi
  fi
  if _py="$(_nbio_find_af3_python_named af3)"; then
    export AF3_PYTHON="$_py"
    return 0
  fi
  if ! _nbio_prefer_blackwell; then
    if _py="$(_nbio_find_af3_python_named af3_blackwell)"; then
      export AF3_PYTHON="$_py"
      return 0
    fi
  fi
  export AF3_PYTHON="${AF3_PYTHON:-/bin/false}"
}

# Resolve + export coherent AF3_* for this host. Call AFTER sourcing .env.
_nbio_apply_af3_env() {
  local cc prefer_bw=0
  local bw_root="" bw_py="" classic_dir params
  cc="$(_nbio_gpu_cc)"
  if _nbio_prefer_blackwell; then
    prefer_bw=1
  fi

  # Never AF3_FORCE_CLASSIC on Blackwell (CC 12.*).
  if [[ "$cc" == 12.* ]]; then
    case "${AF3_FORCE_CLASSIC:-}" in
      1|true|yes|TRUE|YES)
        echo "[nbio] WARN: ignoring AF3_FORCE_CLASSIC (compute_cap=$cc requires blackwell)" >&2
        ;;
    esac
    unset AF3_FORCE_CLASSIC || true
  fi

  params="${AF3_PARAMS:-$_DELIVERY_ROOT/af3_assets/alphafold_param}"
  classic_dir="$_DELIVERY_ROOT/agent/third_party/alphafold3"

  if [[ "$prefer_bw" == "1" ]]; then
    bw_root="$(_nbio_find_blackwell_root 2>/dev/null || true)"
    bw_py="$(_nbio_find_af3_python_named af3_blackwell 2>/dev/null || true)"
    if [[ -n "$bw_root" && -n "$bw_py" && -x "$bw_py" ]]; then
      export AF3_BLACKWELL_ROOT="$bw_root"
      export AF3_DIR="$bw_root/alphafold3"
      export AF3_PYTHON="$bw_py"
      export AF3_CACHE="$bw_root/alphafold_cache"
      export AF3_PARAMS="$params"
      mkdir -p "$AF3_CACHE" 2>/dev/null || true
      return 0
    fi
    echo "[nbio] WARN: prefer blackwell on this host, but stack incomplete (root=${bw_root:-missing} py=${bw_py:-missing})" >&2
    echo "[nbio]        fix: ./scripts/nbio.sh setup  or  bash scripts/setup/setup_all_blackwell.sh" >&2
  fi

  # Classic (or blackwell incomplete fallback): delivery tree + af3 conda.
  if [[ -f "$classic_dir/run_alphafold.py" ]]; then
    if [[ "$prefer_bw" != "1" ]] || [[ "${AF3_DIR:-}" != *"af3_blackwell"* ]]; then
      export AF3_DIR="$classic_dir"
    fi
  fi
  _nbio_discover_af3_python
  export AF3_PARAMS="$params"
  if [[ -z "${AF3_CACHE:-}" && -n "${AF3_DIR:-}" ]]; then
    export AF3_CACHE="$(cd "$(dirname "$AF3_DIR")" 2>/dev/null && pwd)/alphafold_cache"
  fi
}

_nbio_af3_env_needs_heal() {
  # Return 0 when .env AF3_* disagrees with resolved blackwell/classic targets.
  local envf="$_AGENT_ROOT/.env"
  [[ -f "$envf" ]] || return 1
  local cur_dir cur_py prefer_bw=0
  cur_dir="$(grep -E '^AF3_DIR=' "$envf" 2>/dev/null | head -1 | cut -d= -f2- || true)"
  cur_py="$(grep -E '^AF3_PYTHON=' "$envf" 2>/dev/null | head -1 | cut -d= -f2- || true)"
  if _nbio_prefer_blackwell; then
    prefer_bw=1
  fi
  if [[ "$prefer_bw" == "1" ]]; then
    local bw_root bw_py
    bw_root="$(_nbio_find_blackwell_root 2>/dev/null || true)"
    bw_py="$(_nbio_find_af3_python_named af3_blackwell 2>/dev/null || true)"
    [[ -n "$bw_root" && -n "$bw_py" ]] || return 1
    [[ "$cur_dir" == *"af3_blackwell"* ]] || return 0
    [[ "$cur_py" == *"af3_blackwell"* ]] || return 0
    [[ "$cur_dir" == "$bw_root/alphafold3" ]] || return 0
    if grep -qE '^AF3_FORCE_CLASSIC=(1|true|yes)' "$envf" 2>/dev/null; then
      return 0
    fi
    return 1
  fi
  # classic preferred: blackwell python + classic dir is also a mismatch to heal softly
  if [[ "$cur_py" == *"af3_blackwell"* && "$cur_dir" == *"third_party/alphafold3"* ]]; then
    return 0
  fi
  return 1
}

_nbio_envf_upsert() {
  local envf="$1" key="$2" val="$3"
  local tmp
  if [[ ! -f "$envf" ]]; then
    printf '%s=%s\n' "$key" "$val" > "$envf"
    return 0
  fi
  tmp="$(mktemp)"
  awk -v k="$key" -v v="$val" '
    BEGIN { done = 0 }
    index($0, k "=") == 1 {
      print k "=" v
      done = 1
      next
    }
    { print }
    END { if (!done) print k "=" v }
  ' "$envf" > "$tmp"
  mv "$tmp" "$envf"
}

_nbio_envf_delete_key() {
  local envf="$1" key="$2"
  local tmp
  [[ -f "$envf" ]] || return 0
  tmp="$(mktemp)"
  awk -v k="$key" 'index($0, k "=") != 1 { print }' "$envf" > "$tmp"
  mv "$tmp" "$envf"
}

# True when .env layout roots are missing on this host or NANOBOT_BIO_ROOT ≠ checkout.
_nbio_layout_env_needs_heal() {
  local envf="$_AGENT_ROOT/.env"
  [[ -f "$envf" ]] || return 1
  local key cur
  for key in BIO_ROOT DELIVERY_ROOT NANOBOT_BIO_ROOT; do
    cur="$(grep -E "^${key}=" "$envf" 2>/dev/null | head -1 | cut -d= -f2- || true)"
    [[ -n "$cur" ]] || continue
    if [[ ! -d "$cur" ]]; then
      return 0
    fi
  done
  cur="$(grep -E '^NANOBOT_BIO_ROOT=' "$envf" 2>/dev/null | head -1 | cut -d= -f2- || true)"
  if [[ -n "$cur" && "$cur" != "$_AGENT_ROOT" ]]; then
    return 0
  fi
  cur="$(grep -E '^BIO_ROOT=' "$envf" 2>/dev/null | head -1 | cut -d= -f2- || true)"
  # Stale trial absolute path: exists elsewhere but is not parent of this checkout.
  if [[ -n "$cur" && "$cur" != "$_BIO_ROOT" && "$_AGENT_ROOT" == "$_BIO_ROOT"/* ]]; then
    return 0
  fi
  return 1
}

# Heal BIO_ROOT / NANOBOT_* / DELIVERY_ROOT in .env to this checkout.
_nbio_heal_layout_env() {
  local mode="${1:-auto}"
  local envf="$_AGENT_ROOT/.env"
  local bak ans
  if [[ "$mode" == "no" ]]; then
    return 0
  fi
  [[ -f "$envf" ]] || return 0
  if [[ "$mode" != "force" ]] && ! _nbio_layout_env_needs_heal; then
    return 0
  fi
  echo "[nbio] .env layout paths disagree with this checkout (will reconcile from script location)"
  echo "[nbio]   → BIO_ROOT=$_BIO_ROOT"
  echo "[nbio]   → NANOBOT_BIO_ROOT=$_AGENT_ROOT"
  echo "[nbio]   → DELIVERY_ROOT=${_DELIVERY_ROOT}"
  if [[ "$mode" == "ask" ]]; then
    if [[ ! -t 0 ]]; then
      echo "[nbio] non-interactive tty: skipping layout heal (use --heal)" >&2
      return 0
    fi
    read -r -p "[nbio] write .env layout paths and backup? [Y/n] " ans || ans=n
    case "${ans:-Y}" in
      n|N|no|NO) echo "[nbio] skipped layout heal"; return 0 ;;
    esac
  fi
  bak="${envf}.bak.nbio.$(date +%Y%m%d_%H%M%S)"
  cp -a "$envf" "$bak"
  echo "[nbio] backed up → $bak"
  _nbio_envf_upsert "$envf" "BIO_ROOT" "$_BIO_ROOT"
  _nbio_envf_upsert "$envf" "NANOBOT_BIO_ROOT" "$_AGENT_ROOT"
  _nbio_envf_upsert "$envf" "NANOBOT_SRC" "$_AGENT_ROOT/nanobot"
  _nbio_envf_upsert "$envf" "NANOBOT_WORKSPACE" "$_AGENT_ROOT/workspace"
  if [[ -d "$_DELIVERY_ROOT" ]]; then
    _nbio_envf_upsert "$envf" "DELIVERY_ROOT" "$_DELIVERY_ROOT"
  fi
  echo "[nbio] healed .env layout paths (this host)"
  return 0
}

# Heal mismatched AF3_* in .env (surgical; keeps API keys). Backup first.
# $1 = auto|ask|no|force  (force = rewrite even if heuristic says aligned)
_nbio_heal_af3_env() {
  local mode="${1:-auto}"
  local envf="$_AGENT_ROOT/.env"
  local bw_root bw_py bak ans params

  if [[ "$mode" == "no" ]]; then
    return 0
  fi
  if [[ ! -f "$envf" ]]; then
    echo "[nbio] no .env; skipping heal (run ./scripts/nbio.sh setup or create one manually)" >&2
    return 0
  fi
  if [[ "$mode" != "force" ]] && ! _nbio_af3_env_needs_heal; then
    return 0
  fi
  if ! _nbio_prefer_blackwell; then
    echo "[nbio] .env AF3 paths look wrong, but this host does not prefer blackwell; not writing .env" >&2
    echo "[nbio]        (session still exports corrected AF3_*; do not force --heal on classic GPUs)" >&2
    return 0
  fi

  bw_root="$(_nbio_find_blackwell_root 2>/dev/null || true)"
  bw_py="$(_nbio_find_af3_python_named af3_blackwell 2>/dev/null || true)"
  if [[ -z "$bw_root" || -z "$bw_py" ]]; then
    echo "[nbio] WARN: cannot heal — blackwell stack not found (scanned local candidates, not AutoDL-only)" >&2
    return 1
  fi

  echo "[nbio] .env AF3 mismatch detected (will write host-discovered paths):"
  echo "[nbio]   current AF3_DIR=$(grep -E '^AF3_DIR=' "$envf" 2>/dev/null | head -1 | cut -d= -f2- || echo unset)"
  echo "[nbio]   current AF3_PYTHON=$(grep -E '^AF3_PYTHON=' "$envf" 2>/dev/null | head -1 | cut -d= -f2- || echo unset)"
  echo "[nbio]   will set AF3_DIR=$bw_root/alphafold3"
  echo "[nbio]   will set AF3_PYTHON=$bw_py"

  if [[ "$mode" == "ask" ]]; then
    if [[ ! -t 0 ]]; then
      echo "[nbio] non-interactive tty: skipping heal (use --heal)" >&2
      return 0
    fi
    read -r -p "[nbio] write .env and backup? [Y/n] " ans || ans=n
    case "${ans:-Y}" in
      n|N|no|NO) echo "[nbio] skipped heal"; return 0 ;;
    esac
  fi

  bak="${envf}.bak.nbio.$(date +%Y%m%d_%H%M%S)"
  cp -a "$envf" "$bak"
  echo "[nbio] backed up → $bak"

  params="${AF3_PARAMS:-$_DELIVERY_ROOT/af3_assets/alphafold_param}"
  _nbio_envf_upsert "$envf" "AF3_BLACKWELL_ROOT" "$bw_root"
  _nbio_envf_upsert "$envf" "AF3_DIR" "$bw_root/alphafold3"
  _nbio_envf_upsert "$envf" "AF3_PYTHON" "$bw_py"
  _nbio_envf_upsert "$envf" "AF3_CACHE" "$bw_root/alphafold_cache"
  _nbio_envf_upsert "$envf" "AF3_PARAMS" "$params"
  _nbio_envf_delete_key "$envf" "AF3_FORCE_CLASSIC"
  echo "[nbio] healed .env AF3_* (blackwell @ host paths)"
  return 0
}

_nbio_print_af3_status() {
  local cc stack="classic" bw_root="" bw_py=""
  cc="$(_nbio_gpu_cc)"
  [[ -z "$cc" ]] && cc="unknown"
  if _nbio_prefer_blackwell; then
    stack="blackwell"
  fi
  bw_root="$(_nbio_find_blackwell_root 2>/dev/null || true)"
  bw_py="$(_nbio_find_af3_python_named af3_blackwell 2>/dev/null || true)"
  printf '%-28s %-6s %s\n' "GPU compute_cap" "INFO" "$cc"
  printf '%-28s %-6s %s\n' "AF3 stack (prefer)" "INFO" "${AF3_STACK:-auto} → $stack"
  printf '%-28s %-6s %s\n' "AF3_BLACKWELL_ROOT" "INFO" "${AF3_BLACKWELL_ROOT:-${bw_root:-missing}}"
  printf '%-28s %-6s %s\n' "AF3_DIR" "INFO" "${AF3_DIR:-unset}"
  printf '%-28s %-6s %s\n' "AF3_PYTHON" "INFO" "${AF3_PYTHON:-${bw_py:-unset}}"
  printf '%-28s %-6s %s\n' "AF3_CACHE" "INFO" "${AF3_CACHE:-unset}"
  printf '%-28s %-6s %s\n' "AF3_PARAMS" "INFO" "${AF3_PARAMS:-$_DELIVERY_ROOT/af3_assets/alphafold_param}"
  printf '%-28s %-6s %s\n' "AF3_FORCE_CLASSIC" "INFO" "${AF3_FORCE_CLASSIC:-unset}"
  if [[ "$stack" == "blackwell" ]]; then
    if [[ "${AF3_DIR:-}" == *"af3_blackwell"* && "${AF3_PYTHON:-}" == *"af3_blackwell"* ]]; then
      printf '%-28s %-6s %s\n' "AF3 coherence" "OK" "DIR+PYTHON both blackwell"
    else
      printf '%-28s %-6s %s\n' "AF3 coherence" "WARN" "DIR/PYTHON not aligned to blackwell (start can heal)"
    fi
  fi
}

_nbio_activate() {
  local _heavy="${ACTIVATE_HEAVY:-0}"
  local _verify="${ACTIVATE_VERIFY:-0}"

  if [[ ! -f "$_AGENT_ROOT/.setup_complete" ]]; then
    echo "[nbio] WARN: full setup not finished (missing $_AGENT_ROOT/.setup_complete)" >&2
    echo "[nbio]        First time:  $_AGENT_ROOT/scripts/nbio.sh setup" >&2
  fi

  if [[ -f "$_DELIVERY_ROOT/agent/setup.sh" ]]; then
    # shellcheck disable=SC1091
    source "$_DELIVERY_ROOT/agent/setup.sh"
  elif [[ ! -d "$_DELIVERY_ROOT" ]]; then
    echo "[nbio] WARN: delivery pack missing: $_DELIVERY_ROOT" >&2
    echo "[nbio]        Place rhobind_agent_delivery next to this repo, or set DELIVERY_ROOT" >&2
  fi

  if [[ ! -f "$_AGENT_ROOT/.venv/bin/activate" ]]; then
    _nbio_die "missing $_AGENT_ROOT/.venv — run: $_AGENT_ROOT/scripts/nbio.sh setup"
    return $?
  fi
  # shellcheck disable=SC1091
  source "$_AGENT_ROOT/.venv/bin/activate"

  if ! _nbio_omp_sane "${OMP_NUM_THREADS:-}"; then
    export OMP_NUM_THREADS=4
  fi
  _nbio_omp_sane "${MKL_NUM_THREADS:-}" || export MKL_NUM_THREADS="$OMP_NUM_THREADS"
  _nbio_omp_sane "${OPENBLAS_NUM_THREADS:-}" || export OPENBLAS_NUM_THREADS="$OMP_NUM_THREADS"

  export HF_HOME="${HF_HOME:-${XDG_CACHE_HOME:-$HOME/.cache}/huggingface}"
  export HUGGINGFACE_HUB_CACHE="${HUGGINGFACE_HUB_CACHE:-$HF_HOME/hub}"
  export TRANSFORMERS_CACHE="${TRANSFORMERS_CACHE:-$HF_HOME/transformers}"
  export HF_ENDPOINT="${HF_ENDPOINT:-https://hf-mirror.com}"
  mkdir -p "$HF_HOME/hub" "$TRANSFORMERS_CACHE" 2>/dev/null || true

  # Load .env first, then reconcile roots + AF3 for THIS host (not trial absolutes).
  if [[ -f "$_AGENT_ROOT/.env" ]]; then
    set -a
    # shellcheck disable=SC1091
    source "$_AGENT_ROOT/.env"
    set +a
  fi
  _nbio_reconcile_roots
  _nbio_apply_af3_env

  local _src="${NANOBOT_SRC:-$_NANOBOT_SRC_DEFAULT}"
  if [[ ! -f "$_src/nanobot.py" && ! -f "$_src/__init__.py" ]]; then
    _src="$_NANOBOT_SRC_DEFAULT"
  fi
  export NANOBOT_SRC="$_src"
  export PYTHONPATH="${_AGENT_ROOT}:${_BIO_ROOT}${PYTHONPATH:+:$PYTHONPATH}"

  if [[ "$_heavy" == "1" ]]; then
    pip install -e "$_AGENT_ROOT" -q 2>/dev/null \
      || echo "[nbio] WARN: pip install -e nanobot-bio failed" >&2
    python -m app.sync_overlay \
      || echo "[nbio] WARN: sync_overlay failed" >&2
    _verify=1
  fi

  echo "[nbio] BIO_ROOT=$BIO_ROOT DELIVERY_ROOT=$DELIVERY_ROOT"
  echo "[nbio] NANOBOT_SRC=$NANOBOT_SRC"
  echo "[nbio] AF3_DIR=$AF3_DIR"
  echo "[nbio] AF3_PYTHON=$AF3_PYTHON"
  echo "[nbio] $(python -V 2>/dev/null) $(command -v python 2>/dev/null)"

  if [[ "$_verify" == "1" ]]; then
    (
      cd "$_AGENT_ROOT"
      python - <<'PY'
import nanobot
from nanobot.agent.tools.core.base import Tool  # noqa: F401
p = (nanobot.__file__ or "").replace("\\", "/")
print("[nbio] nanobot OK", p)
if "nanobot-bio" not in p and "Nanobot-bio" not in p and not p.endswith("/nanobot/__init__.py"):
    raise SystemExit("[nbio] ERROR: expected in-repo nanobot package")
PY
    ) || echo "[nbio] WARN: nanobot import failed" >&2
  fi

  if command -v nanobot-bio >/dev/null 2>&1; then
    echo "[nbio] nanobot-bio=$(command -v nanobot-bio)"
  elif command -v rbp-agent >/dev/null 2>&1; then
    echo "[nbio] rbp-agent=$(command -v rbp-agent)"
  else
    echo "[nbio] tip: ACTIVATE_HEAVY=1 source scripts/nbio.sh  # or: pip install -e \$NANOBOT_BIO_ROOT"
  fi
}

_nbio_status() {
  # Lightweight detect table (no science probes). Works without activate when possible.
  local venv_ok=FAIL delivery_ok=FAIL setup_ok=FAIL cli=FAIL
  local detail_venv="missing .venv" detail_del="missing" detail_setup="no .setup_complete" detail_cli="not on PATH"

  [[ -f "$_AGENT_ROOT/.venv/bin/activate" ]] && { venv_ok=OK; detail_venv="$_AGENT_ROOT/.venv"; }
  if [[ -d "$_DELIVERY_ROOT" ]]; then
    delivery_ok=OK
    detail_del="$_DELIVERY_ROOT"
  else
    detail_del="set DELIVERY_ROOT or place sibling rhobind_agent_delivery"
  fi
  [[ -f "$_AGENT_ROOT/.setup_complete" ]] && { setup_ok=OK; detail_setup="present"; }
  if [[ -x "$_AGENT_ROOT/.venv/bin/nanobot-bio" ]]; then
    cli=OK
    detail_cli="$_AGENT_ROOT/.venv/bin/nanobot-bio"
  elif command -v nanobot-bio >/dev/null 2>&1; then
    cli=OK
    detail_cli="$(command -v nanobot-bio)"
  fi

  # Preview AF3 resolution without requiring venv (session-only; does not heal).
  local _saved_dir="${AF3_DIR:-}" _saved_py="${AF3_PYTHON:-}" _saved_cache="${AF3_CACHE:-}"
  local _saved_bw="${AF3_BLACKWELL_ROOT:-}" _saved_force="${AF3_FORCE_CLASSIC:-}"
  if [[ -f "$_AGENT_ROOT/.env" ]]; then
    set -a
    # shellcheck disable=SC1091
    source "$_AGENT_ROOT/.env"
    set +a
  fi
  _nbio_reconcile_roots
  _nbio_apply_af3_env

  printf '%s\n' "=== nbio status ==="
  printf '%-28s %-6s %s\n' "Feature" "Status" "Detail"
  printf '%-28s %-6s %s\n' "----------------------------" "------" "------"
  printf '%-28s %-6s %s\n' "Agent venv" "$venv_ok" "$detail_venv"
  printf '%-28s %-6s %s\n' "Delivery pack" "$delivery_ok" "$detail_del"
  printf '%-28s %-6s %s\n' "Setup marker" "$setup_ok" "$detail_setup"
  printf '%-28s %-6s %s\n' "CLI (nanobot-bio)" "$cli" "$detail_cli"
  printf '%-28s %-6s %s\n' "BIO_ROOT" "INFO" "$_BIO_ROOT"
  printf '%-28s %-6s %s\n' "NANOBOT_BIO_ROOT" "INFO" "$_AGENT_ROOT"
  _nbio_print_af3_status
  if _nbio_af3_env_needs_heal; then
    printf '%-28s %-6s %s\n' ".env AF3 heal" "WARN" "run: ./scripts/nbio.sh start --dry-run or start --heal"
  else
    printf '%-28s %-6s %s\n' ".env AF3 heal" "OK" "aligned or N/A"
  fi

  # Restore caller env if we only previewed.
  if [[ "$_nbio_sourced" == "1" ]]; then
    [[ -n "$_saved_dir" ]] && export AF3_DIR="$_saved_dir" || true
    [[ -n "$_saved_py" ]] && export AF3_PYTHON="$_saved_py" || true
    [[ -n "$_saved_cache" ]] && export AF3_CACHE="$_saved_cache" || true
    [[ -n "$_saved_bw" ]] && export AF3_BLACKWELL_ROOT="$_saved_bw" || true
    if [[ -n "$_saved_force" ]]; then
      export AF3_FORCE_CLASSIC="$_saved_force"
    fi
  fi

  if [[ "$venv_ok" != "OK" || "$delivery_ok" != "OK" ]]; then
    echo "fix: $_AGENT_ROOT/scripts/nbio.sh setup"
    return 1
  fi
  return 0
}

_nbio_doctor() {
  if [[ ! -f "$_AGENT_ROOT/.venv/bin/activate" ]]; then
    _nbio_die "missing .venv — run: $_AGENT_ROOT/scripts/nbio.sh setup"
    return $?
  fi
  # shellcheck disable=SC1091
  source "$_AGENT_ROOT/.venv/bin/activate"
  if [[ -f "$_AGENT_ROOT/.env" ]]; then
    set -a
    # shellcheck disable=SC1091
    source "$_AGENT_ROOT/.env"
    set +a
  fi
  _nbio_reconcile_roots
  _nbio_apply_af3_env
  if [[ -f "$_DELIVERY_ROOT/agent/setup.sh" ]]; then
    # shellcheck disable=SC1091
    source "$_DELIVERY_ROOT/agent/setup.sh"
    _nbio_reconcile_roots
    _nbio_apply_af3_env
  fi
  cd "$_AGENT_ROOT"
  if command -v nanobot-bio >/dev/null 2>&1; then
    exec nanobot-bio doctor "$@"
  fi
  exec python -m app doctor "$@"
}

_nbio_setup() {
  if [[ ! -x "$_SETUP_ALL" && ! -f "$_SETUP_ALL" ]]; then
    _nbio_die "setup_all.sh not found: $_SETUP_ALL"
    return $?
  fi
  bash "$_SETUP_ALL" "$@"
}

_nbio_chat() {
  _nbio_activate || return $?
  cd "$_AGENT_ROOT"
  if command -v nanobot-bio >/dev/null 2>&1; then
    exec nanobot-bio chat "$@"
  fi
  exec python -m app chat "$@"
}

# One-shot launcher: discover → heal AF3 → status → optional doctor → chat.
# Flags: --dry-run --heal --no-heal --ask --doctor --no-doctor --status-only
# Remaining args (after --) pass through to nanobot-bio chat.
_nbio_start() {
  local heal_mode="auto"
  local dry_run=0 status_only=0 run_doctor=0
  local -a chat_args=()
  local arg

  while [[ $# -gt 0 ]]; do
    arg="$1"
    case "$arg" in
      --dry-run) dry_run=1; shift ;;
      --status-only) status_only=1; shift ;;
      --heal) heal_mode="force"; shift ;;
      --no-heal) heal_mode="no"; shift ;;
      --ask) heal_mode="ask"; shift ;;
      --doctor) run_doctor=1; shift ;;
      --no-doctor) run_doctor=0; shift ;;
      -h|--help)
        cat <<EOF
Usage: ./scripts/nbio.sh start|up [options] [-- chat-args...]

  One-shot: discover BIO_ROOT / delivery / .venv, fix AF3_* for GPU, then start chat.

Options:
  --dry-run       print auto-adapt results (may heal); do not start chat
  --status-only   same as --dry-run
  --heal          force-write .env AF3_* (backup .env.bak.nbio.* first)
  --no-heal       leave .env unchanged (still export correct AF3_* for this session)
  --ask           confirm interactively before heal
  --doctor        run nanobot-bio doctor before chat
  --no-doctor     default; skip doctor
  --              pass remaining args through to nanobot-bio chat

Defaults: auto-heal on CC12 when blackwell stack exists (with backup); never keep AF3_FORCE_CLASSIC on CC12.
EOF
        return 0
        ;;
      --)
        shift
        chat_args+=("$@")
        break
        ;;
      *)
        chat_args+=("$1")
        shift
        ;;
    esac
  done

  echo "[nbio] === start: auto-adapt env (host path discovery) ==="
  echo "[nbio] AGENT_ROOT=$_AGENT_ROOT"
  echo "[nbio] BIO_ROOT=$_BIO_ROOT"
  echo "[nbio] DELIVERY_ROOT=$_DELIVERY_ROOT"
  echo "[nbio] NANOBOT_BIO_ROOT=$_AGENT_ROOT"

  # Preview resolution for messaging (before heal).
  if [[ -f "$_AGENT_ROOT/.env" ]]; then
    set -a
    # shellcheck disable=SC1091
    source "$_AGENT_ROOT/.env"
    set +a
  fi
  _nbio_reconcile_roots
  _nbio_print_path_discovery
  _nbio_apply_af3_env
  _nbio_print_af3_status

  if [[ "$heal_mode" == "no" ]]; then
    echo "[nbio] --no-heal: leaving .env unchanged (session still uses corrected paths above)"
  else
    if [[ "$heal_mode" == "force" ]] || _nbio_layout_env_needs_heal; then
      _nbio_heal_layout_env "$heal_mode"
      _nbio_reconcile_roots
    fi
    if [[ "$heal_mode" == "force" ]]; then
      _nbio_heal_af3_env "force"
    elif _nbio_af3_env_needs_heal; then
      _nbio_heal_af3_env "$heal_mode"
    else
      echo "[nbio] .env AF3_* already matches host discovery; heal not needed"
    fi
  fi

  # Re-apply after possible heal.
  if [[ -f "$_AGENT_ROOT/.env" ]]; then
    set -a
    # shellcheck disable=SC1091
    source "$_AGENT_ROOT/.env"
    set +a
  fi
  _nbio_reconcile_roots
  _nbio_apply_af3_env

  if [[ "$dry_run" == "1" || "$status_only" == "1" ]]; then
    echo "[nbio] === dry-run / status-only (not starting chat) ==="
    _nbio_status || true
    echo "[nbio] session would use (host discovery):"
    echo "[nbio]   BIO_ROOT=$BIO_ROOT"
    echo "[nbio]   DELIVERY_ROOT=$DELIVERY_ROOT"
    echo "[nbio]   AF3_DIR=$AF3_DIR"
    echo "[nbio]   AF3_PYTHON=$AF3_PYTHON"
    echo "[nbio]   AF3_CACHE=${AF3_CACHE:-}"
    echo "[nbio]   AF3_BLACKWELL_ROOT=${AF3_BLACKWELL_ROOT:-}"
    return 0
  fi

  _nbio_activate || return $?

  if [[ "$run_doctor" == "1" ]]; then
    echo "[nbio] running doctor ..."
    if command -v nanobot-bio >/dev/null 2>&1; then
      nanobot-bio doctor || echo "[nbio] WARN: doctor exited non-zero" >&2
    else
      python -m app doctor || echo "[nbio] WARN: doctor exited non-zero" >&2
    fi
  fi

  cd "$_AGENT_ROOT"
  echo "[nbio] launching chat ..."
  if [[ "$_nbio_sourced" == "1" ]]; then
    if command -v nanobot-bio >/dev/null 2>&1; then
      nanobot-bio chat "${chat_args[@]}"
      return $?
    fi
    python -m app chat "${chat_args[@]}"
    return $?
  fi
  if command -v nanobot-bio >/dev/null 2>&1; then
    exec nanobot-bio chat "${chat_args[@]}"
  fi
  exec python -m app chat "${chat_args[@]}"
}

_nbio_usage() {
  cat <<EOF
Usage:
  source scripts/nbio.sh [activate]     Activate agent .venv + export paths (daily)
  ./scripts/nbio.sh status              Detect layout / venv / delivery / AF3 (table)
  ./scripts/nbio.sh doctor [--verbose]  Capability table (nanobot-bio doctor)
  ./scripts/nbio.sh setup [args...]     First-time / repair → setup_all.sh
  ./scripts/nbio.sh chat [args...]      Activate then nanobot-bio chat
  ./scripts/nbio.sh start|up [opts]     one-shot: AF3 fix(+heal) → status → chat
                                     opts: --dry-run --heal --no-heal --ask --doctor

Environment overrides: BIO_ROOT, DELIVERY_ROOT, AF3_PYTHON, AF3_BLACKWELL_ROOT,
  AF3_STACK=auto|classic|blackwell, CONDA_ENVS_PATH,
  ACTIVATE_HEAVY=1, ACTIVATE_VERIFY=1
EOF
}

_nbio_main() {
  local cmd="${1:-}"
  if [[ -z "$cmd" ]]; then
    if [[ "$_nbio_sourced" == "1" ]]; then
      _nbio_activate
      return $?
    fi
    _nbio_usage
    exit 0
  fi
  shift || true
  case "$cmd" in
    activate|env)
      _nbio_activate "$@"
      ;;
    status)
      _nbio_status "$@"
      ;;
    doctor)
      _nbio_doctor "$@"
      ;;
    setup)
      _nbio_setup "$@"
      ;;
    chat)
      if [[ "$_nbio_sourced" == "1" ]]; then
        _nbio_activate || return $?
        nanobot-bio chat "$@"
        return $?
      fi
      _nbio_chat "$@"
      ;;
    start|up)
      _nbio_start "$@"
      ;;
    -h|--help|help)
      _nbio_usage
      ;;
    *)
      echo "[nbio] unknown command: $cmd" >&2
      _nbio_usage >&2
      if [[ "$_nbio_sourced" == "1" ]]; then
        return 2
      fi
      exit 2
      ;;
  esac
}

# When sourced with no args → activate. When sourced with args → dispatch.
# When executed → dispatch (default: help).
if [[ "$_nbio_sourced" == "1" ]]; then
  # Do not enable `set -e` in the caller's shell.
  _nbio_main "$@"
  return $? 2>/dev/null || exit $?
else
  _nbio_main "$@"
fi
