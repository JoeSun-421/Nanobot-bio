#!/usr/bin/env bash
# Compatibility wrapper — prefer: source scripts/nbio.sh
# Usage (must be sourced):
#   source scripts/setup/activate_env.sh
#   ACTIVATE_HEAVY=1 source scripts/setup/activate_env.sh
_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "$_SCRIPT_DIR/../nbio" activate
