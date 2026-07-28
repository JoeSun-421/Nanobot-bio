#!/usr/bin/env bash
# App-side mmseqs shim: delivery rna_blastn / protein_seq_similarity omit --threads.
# On this host, default (all-core) search segfaults with:
#   World Size: 208 dbSize: 130
# Inject --threads from MMSEQS_THREADS / OMP_NUM_THREADS (default 4).
set -euo pipefail
REAL="${MMSEQS_REAL:-mmseqs}"
THREADS="${MMSEQS_THREADS:-${OMP_NUM_THREADS:-4}}"
case "${THREADS}" in
  ''|*[!0-9]*|0) THREADS=4 ;;
esac
if [[ "${1:-}" == "search" ]]; then
  has_threads=0
  for a in "$@"; do
    if [[ "$a" == "--threads" ]]; then
      has_threads=1
      break
    fi
  done
  if [[ "$has_threads" -eq 0 ]]; then
    exec "$REAL" "$@" --threads "$THREADS"
  fi
fi
exec "$REAL" "$@"
