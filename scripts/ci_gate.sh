#!/usr/bin/env bash
# Phase-1 engineering gate (pytest / ruff / layout / optional light eval).
# Usage:
#   bash scripts/ci_gate.sh
#   bash scripts/ci_gate.sh --skip-eval
#   bash scripts/ci_gate.sh --no-cov
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$AGENT_ROOT"
# shellcheck disable=SC1091
[[ -f .venv/bin/activate ]] && source .venv/bin/activate
export PYTHONPATH="${AGENT_ROOT}${PYTHONPATH:+:$PYTHONPATH}"
exec python -m app gate "$@"
