#!/usr/bin/env bash
# Scan tracked files for obvious committed secrets. Fail on hit.
# Usage: bash scripts/check_secrets.sh
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT"

# Only tracked files (respects .gitignore / index)
mapfile -t FILES < <(git ls-files -z 2>/dev/null | tr '\0' '\n' | grep -vE '^(requirements\.lock|.*\.lock)$' || true)
if ((${#FILES[@]} == 0)); then
  # Not a git checkout — scan common source roots
  mapfile -t FILES < <(find app rbp_eval nanobot tests scripts config docs \
    -type f \( -name '*.py' -o -name '*.md' -o -name '*.yaml' -o -name '*.yml' -o -name '*.sh' -o -name '*.toml' -o -name '*.txt' -o -name '*.example' \) 2>/dev/null | head -5000)
fi

PATTERNS=(
  'BEGIN (RSA |OPENSSH |EC )?PRIVATE KEY'
  'sk-[A-Za-z0-9]{20,}'
  'api[_-]?key[[:space:]]*=[[:space:]]*['\''\"]?[A-Za-z0-9_\-]{20,}'
  'OPENAI_API_KEY[[:space:]]*=[[:space:]]*['\''\"]?[A-Za-z0-9_\-]{16,}'
  'DEEPSEEK_API_KEY[[:space:]]*=[[:space:]]*['\''\"]?[A-Za-z0-9_\-]{16,}'
)

hits=0
for f in "${FILES[@]}"; do
  [[ -f "$f" ]] || continue
  case "$f" in
    *.png|*.jpg|*.jpeg|*.gif|*.webp|*.pyc|*.so|*.bin) continue ;;
    artifacts/*|workspace/.nanobot/*|*.egg-info/*) continue ;;
  esac
  for pat in "${PATTERNS[@]}"; do
    if grep -nIE "$pat" -- "$f" 2>/dev/null | grep -vE 'example|EXAMPLE|placeholder|your.api|FIXME|check_secrets' >/dev/null; then
      echo "SECRET_PATTERN hit in $f (/$pat/)" >&2
      grep -nIE "$pat" -- "$f" 2>/dev/null | head -3 >&2 || true
      hits=$((hits + 1))
    fi
  done
done

if ((hits > 0)); then
  echo "check_secrets: FAIL ($hits file hits). Rotate keys; do not commit .env / ~/.nanobot/config.json" >&2
  exit 1
fi

# Reminder: ~/.nanobot/config.json holds the live LLM key (outside the repo).
# We do not read it; just nudge if it is missing the 0600 perm or is world-readable.
CFG="${NANOBOT_CONFIG:-$HOME/.nanobot/config.json}"
if [[ -f "$CFG" ]]; then
  perm=$(stat -c '%a' "$CFG" 2>/dev/null || stat -f '%Lp' "$CFG" 2>/dev/null || echo "???")
  if [[ "$perm" != "600" && "$perm" != "400" ]]; then
    echo "check_secrets: WARN  $CFG perms=$perm (recommend chmod 600). Not a tracked-file failure." >&2
  fi
  # Guard against accidental `git add -f ~/.nanobot/config.json` inside any repo
  if git -C "$HOME" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    if git -C "$HOME" ls-files --error-unmatch "$CFG" >/dev/null 2>&1; then
      echo "check_secrets: FAIL  $CFG is TRACKED by a git repo at $HOME — untrack + rotate key." >&2
      exit 1
    fi
  fi
fi

echo "check_secrets: OK (${#FILES[@]} files scanned)"
exit 0
