#!/usr/bin/env bash
# =============================================================================
# bootstrap_data.sh — idempotent rebuild of the delivery operational database
# =============================================================================
# Replays the build steps documented in
#   rhobind_agent_delivery/agent/database/SOURCES.md
# so a collaborator can reconstruct agent_db/ from the raw source bundle
# (rbp_proteins_260417) without touching delivery source code.
#
# Idempotent: each step is skipped if its output already exists and is newer
# than its inputs (override with --force).
#
# Prereqs (on the build host):
#   - conda envs: protein_embed (foldseek/ESM), rna (mmseqs)
#   - Raw source bundle RB (rbp_proteins_260417) reachable
#   - benchmark_cluster results dir reachable
#
# Usage:
#   bash scripts/bootstrap_data.sh \
#     --rb /path/to/rbp_proteins_260417 \
#     --benchmarks /path/to/results/benchmark_cluster \
#     --head-index-dir /path/to/head_index_dir \
#     --out /path/to/agent_db
#
#   --force   rebuild even if outputs look fresh
#   --skip-peaks      skip the rna_blastn peaks DB (needs processed_260417)
#   --skip-embeddings skip embedding bank (needs per-residue pkl set)
# =============================================================================
set -euo pipefail

FORCE=0
SKIP_PEAKS=0
SKIP_EMBED=0
RB=""
BENCHMARKS=""
HEAD_INDEX_DIR=""
OUT=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --rb) RB="$2"; shift 2 ;;
    --benchmarks) BENCHMARKS="$2"; shift 2 ;;
    --head-index-dir) HEAD_INDEX_DIR="$2"; shift 2 ;;
    --out) OUT="$2"; shift 2 ;;
    --force) FORCE=1; shift ;;
    --skip-peaks) SKIP_PEAKS=1; shift ;;
    --skip-embeddings) SKIP_EMBED=1; shift ;;
    -h|--help) sed -n '1,30p' "$0"; exit 0 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

for v in RB BENCHMARKS HEAD_INDEX_DIR OUT; do
  if [[ -z "${!v:-}" ]]; then
    echo "ERROR: --$(echo "$v" | tr 'A-Z' 'a-z' | tr '_' '-') is required" >&2
    exit 2
  fi
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BIO_ROOT="$(cd "${BIO_ROOT:-$AGENT_ROOT/..}" && pwd)"
DELIVERY_ROOT="${DELIVERY_ROOT:-$BIO_ROOT/rhobind_agent_delivery}"
BUILD_DIR="$DELIVERY_ROOT/agent/database/build"

echo "=============================================="
echo " bootstrap_data.sh"
echo "=============================================="
echo "  RB            = $RB"
echo "  BENCHMARKS    = $BENCHMARKS"
echo "  HEAD_INDEX    = $HEAD_INDEX_DIR"
echo "  OUT           = $OUT"
echo "  DELIVERY_ROOT = $DELIVERY_ROOT"
echo "  FORCE         = $FORCE"
echo

for d in "$RB" "$BENCHMARKS" "$HEAD_INDEX_DIR" "$BUILD_DIR"; do
  [[ -d "$d" ]] || { echo "ERROR: missing dir: $d" >&2; exit 1; }
done

mkdir -p "$OUT"/{embedding_bank,foldseek_db,seq_db,registry,peaks_db,transfer,bin}

# ---------------------------------------------------------------------------
# Helper: run a step only if its marker is missing or stale
# ---------------------------------------------------------------------------
fresh() { # fresh <marker> <input1> [input2 ...]
  local marker="$1"; shift
  [[ -f "$marker" ]] || return 1
  [[ "$FORCE" == "1" ]] && return 1
  local inp
  for inp in "$@"; do
    [[ -e "$inp" ]] || continue
    if [[ "$inp" -nt "$marker" ]]; then return 1; fi
  done
  return 0
}

# ---------------------------------------------------------------------------
# 1. Embedding bank (mean-pool per-residue pkl -> npz + ids.json)
# ---------------------------------------------------------------------------
EMBED_MARKER="$OUT/embedding_bank/ids.json"
if [[ "$SKIP_EMBED" == "1" ]]; then
  echo "[1/5] skip embeddings (--skip-embeddings)"
elif fresh "$EMBED_MARKER" "$RB/embeddings"; then
  echo "[1/5] embeddings fresh — skip ($EMBED_MARKER)"
else
  echo "[1/5] build_embedding_bank.py"
  conda run -n protein_embed python "$BUILD_DIR/build_embedding_bank.py" \
    --src "$RB/embeddings" --out "$OUT/embedding_bank"
fi

# ---------------------------------------------------------------------------
# 2. Foldseek structure DB from AFDB models
# ---------------------------------------------------------------------------
FOLDSEEK_MARKER="$OUT/foldseek_db/refs.idx"
if fresh "$FOLDSEEK_MARKER" "$RB/structures/afdb"; then
  echo "[2/5] foldseek DB fresh — skip ($FOLDSEEK_MARKER)"
else
  echo "[2/5] foldseek createdb"
  conda run -n protein_embed foldseek createdb \
    "$RB/structures/afdb" "$OUT/foldseek_db/refs"
fi

# ---------------------------------------------------------------------------
# 3. mmseqs sequence DB from UniProt canonical seqs
# ---------------------------------------------------------------------------
SEQ_MARKER="$OUT/seq_db/refs.idx"
if fresh "$SEQ_MARKER" "$RB/sequences/all_rbps.fasta"; then
  echo "[3/5] mmseqs DB fresh — skip ($SEQ_MARKER)"
else
  echo "[3/5] mmseqs createdb"
  conda run -n rna mmseqs createdb \
    "$RB/sequences/all_rbps.fasta" "$OUT/seq_db/refs"
fi

# ---------------------------------------------------------------------------
# 4. Master registry (rbp_registry.json)
# ---------------------------------------------------------------------------
REG_MARKER="$OUT/registry/rbp_registry.json"
if fresh "$REG_MARKER" "$RB" "$BENCHMARKS" "$HEAD_INDEX_DIR" "$EMBED_MARKER"; then
  echo "[4/5] registry fresh — skip ($REG_MARKER)"
else
  echo "[4/5] build_registry.py"
  conda run -n rna python "$BUILD_DIR/build_registry.py" \
    --rb "$RB" \
    --benchmarks "$BENCHMARKS" \
    --head-index-dir "$HEAD_INDEX_DIR" \
    --bank-ids "$OUT/embedding_bank/ids.json" \
    --out "$REG_MARKER"
fi

# ---------------------------------------------------------------------------
# 5. Peaks DB for rna_blastn (needs processed_260417 train fastas)
# ---------------------------------------------------------------------------
PEAKS_MARKER="$OUT/peaks_db/peaks.idx"
if [[ "$SKIP_PEAKS" == "1" ]]; then
  echo "[5/5] skip peaks DB (--skip-peaks)"
elif fresh "$PEAKS_MARKER"; then
  echo "[5/5] peaks DB fresh — skip ($PEAKS_MARKER)"
else
  PROCESSED="${PROCESSED_ROOT:-$RB/../processed_260417}"
  if [[ ! -d "$PROCESSED" ]]; then
    echo "[5/5] skip peaks DB (no processed_260417 at $PROCESSED; set PROCESSED_ROOT)"
  else
    echo "[5/5] build_peaks_db.py"
    conda run -n rna python "$BUILD_DIR/build_peaks_db.py" \
      --data_root "$PROCESSED" --out "$OUT/peaks_db"
  fi
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo
echo "=============================================="
echo " bootstrap_data.sh done"
echo "=============================================="
echo "  registry:   $OUT/registry/rbp_registry.json"
echo "  embeddings:$OUT/embedding_bank/"
echo "  foldseek:   $OUT/foldseek_db/"
echo "  mmseqs:     $OUT/seq_db/"
echo "  peaks:      $OUT/peaks_db/  (optional)"
echo
echo "  Point AGENT_DB=$OUT and RBP_REGISTRY=$OUT/registry/rbp_registry.json"
echo "  at this dir (see INSTALL.md env table)."
