#!/usr/bin/env bash
# One non-LLM certification path; never reads or prints provider API keys.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$ROOT"

PY="${PYTHON:-$ROOT/.venv/bin/python}"
[[ -x "$PY" ]] || { echo "missing agent Python: $PY" >&2; exit 2; }

NETWORK=0
RUN_TRANSFER=0
RUN_RELEASE=0
TARGET="${CERTIFY_TARGET:-PTBP1}"
MAX_SEQS="${CERTIFY_MAX_SEQS:-4}"
for arg in "$@"; do
  case "$arg" in
    --network) NETWORK=1 ;;
    --transfer) RUN_TRANSFER=1 ;;
    --release-metrics) RUN_RELEASE=1 ;;
    --full) NETWORK=1; RUN_TRANSFER=1; RUN_RELEASE=1 ;;
    -h|--help)
      echo "usage: bash scripts/cert/certify.sh [--network] [--release-metrics] [--transfer] [--full]"
      exit 0
      ;;
    *) echo "unknown option: $arg" >&2; exit 2 ;;
  esac
done

"$PY" "$SCRIPT_DIR/environment_manifest.py"
"$PY" -m app doctor
"$PY" -m rbp_eval.accept.own_head

SMOKE_ARGS=()
if (( NETWORK )); then
  SMOKE_ARGS+=(--network)
fi
"$PY" "$SCRIPT_DIR/smoke_delivery_tools.py" "${SMOKE_ARGS[@]}"

if (( RUN_RELEASE )); then
  "$PY" -m rbp_eval.accept.release_metrics \
    --device cuda --out artifacts/reports/json/release_metrics.json
fi

if (( RUN_TRANSFER )); then
  "$PY" -m rbp_eval.accept.transfer_calibration \
    --regime both --rbp "$TARGET" --max-seqs "$MAX_SEQS" --device cuda \
    --out artifacts/reports/json/transfer_calibration.json
fi

"$PY" -m pytest -q
echo "certification complete: artifacts/reports/{json,md,csv}/"
