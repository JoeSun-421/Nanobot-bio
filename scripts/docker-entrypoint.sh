#!/usr/bin/env bash
# docker-entrypoint.sh — self-check then exec the user command.
#
# Behaviour:
#   1. If DELIVERY_ROOT is mounted and present, apply delivery env.
#   2. Run `nanobot-bio doctor` as a smoke self-check (non-fatal on failure).
#   3. exec "$@" (default: nanobot-bio chat).
#
# Override the self-check: SKIP_DOCTOR=1 docker run ...
set -euo pipefail

NANOBOT_BIO_ROOT="${NANOBOT_BIO_ROOT:-/bio/nanobot-bio}"
export NANOBOT_BIO_ROOT
export NANOBOT_WORKSPACE="${NANOBOT_WORKSPACE:-$NANOBOT_BIO_ROOT/workspace}"
export NANOBOT_CONFIG="${NANOBOT_CONFIG:-/root/.nanobot/config.json}"

# Apply delivery env if the bundle is mounted (best-effort)
if [ -d "${DELIVERY_ROOT:-/delivery}/agent" ]; then
  export DELIVERY_ROOT="${DELIVERY_ROOT:-/delivery}"
  # app.backends.delivery.env.apply_delivery_env sets the standard paths
  "$NANOBOT_BIO_ROOT/.venv/bin/python" - <<'PY' || true
import os
from app.backends.delivery.env import apply_delivery_env
applied = apply_delivery_env()
for k, v in applied.items():
    os.environ.setdefault(k, v)
print("[entrypoint] delivery env applied:", os.environ.get("DELIVERY_ROOT"))
PY
fi

# Self-check (non-fatal). Skip with SKIP_DOCTOR=1.
if [ "${SKIP_DOCTOR:-0}" != "1" ]; then
  echo "[entrypoint] nanobot-bio doctor (self-check) ..."
  set +e
  "$NANOBOT_BIO_ROOT/.venv/bin/python" -m app doctor
  rc=$?
  set -e
  if [ "$rc" -ne 0 ]; then
    echo "[entrypoint] WARN: doctor exited $rc — continuing (mount DELIVERY_ROOT / config to fix)" >&2
  fi
fi

# Re-sync overlay at runtime in case the mounted nanobot runtime drifted
"$NANOBOT_BIO_ROOT/.venv/bin/python" -m app.sync_overlay >/dev/null 2>&1 || true

echo "[entrypoint] exec: $*"
exec "$@"
