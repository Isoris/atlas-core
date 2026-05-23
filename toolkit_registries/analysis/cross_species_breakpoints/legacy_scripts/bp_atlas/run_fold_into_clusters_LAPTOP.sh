#!/usr/bin/env bash
# run_fold_into_clusters_LAPTOP.sh
# ----------------------------------------------------------------------------
# Run AFTER run_bp_atlas_LAPTOP.sh finishes. Folds the BP_ATLAS sequence layer
# back into the headline cluster table, exactly as section 8 of the handoff
# describes:
#
#   per-PAF STEP_CS01_extract_breakpoints.py   (one cs JSON per Pass-A PAF)
#       -> csbp_dir_to_breakpoints.py          (fold all JSONs into one table)
#       -> cluster_breakpoints.py --source ... (re-cluster with the new source)
#
# This is the "supported from both directions" sequence evidence tier joining
# the gene-order catalog. It is a CONFIRMATION layer: it reproduces the Clarias
# breakpoints (LG27, LG23) with reciprocity + tiers; it does NOT change the
# headline. Cohort boundary: COMPARATIVE/ASSEMBLY only — coordinates, never
# hatchery claims.
#
# Usage (from MODULE_BPATLAS_crossspecies/scripts/):
#   bash run_fold_into_clusters_LAPTOP.sh \
#       [--existing-clusters /path/to/prior/breakpoint_clusters.tsv sources...]
#
# Env overrides:
#   MIN_MAPQ   (default 1 — wfmash mapq is 1-5; NEVER use 40 here)
#   MIN_BLOCK  (default 50000)
#   TOL_KB     (default 500 — matches the locked tolerance-cluster default)
# ----------------------------------------------------------------------------
set -uo pipefail

MODULE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$MODULE_DIR/.." && pwd)"
RESULTS_DIR="${ROOT_DIR}/results_bpatlas"
PAF_DIR_A="${RESULTS_DIR}/02_paf_passA"
CSJSON_DIR="${RESULTS_DIR}/04_cs_json"
FOLD_DIR="${RESULTS_DIR}/04_fold"
mkdir -p "$CSJSON_DIR" "$FOLD_DIR"

MIN_MAPQ="${MIN_MAPQ:-1}"          # wfmash mapq is 1-5; do NOT raise to 40
MIN_BLOCK="${MIN_BLOCK:-50000}"
TOL_KB="${TOL_KB:-500}"

echo "=== Fold BP_ATLAS sequence layer into clusters $(date) ==="
echo "PAF source: $PAF_DIR_A   min-mapq=$MIN_MAPQ min-block=$MIN_BLOCK tol-kb=$TOL_KB"

# --- Step A: per-PAF STEP_CS01 (skip empty deep-outgroup PAFs) ---
echo ""; echo "--- Step A: STEP_CS01 per Pass-A PAF ---"
n_done=0; n_skip=0
for paf in "$PAF_DIR_A"/*.paf; do
  [[ -e "$paf" ]] || { echo "  no PAFs found in $PAF_DIR_A — run run_bp_atlas_LAPTOP.sh first"; exit 1; }
  if [[ ! -s "$paf" ]]; then n_skip=$((n_skip+1)); continue; fi   # empty = deep skip
  pid="$(basename "$paf" .paf)"
  out="$CSJSON_DIR/${pid}.json"
  [[ -s "$out" ]] && { echo "  [$pid] cs json exists, skip"; n_done=$((n_done+1)); continue; }
  python3 "$MODULE_DIR/STEP_CS01_extract_breakpoints.py" \
      --paf "$paf" --min-mapq "$MIN_MAPQ" --min-block-bp "$MIN_BLOCK" \
      --out "$out" > "$CSJSON_DIR/${pid}.cs.log" 2>&1 \
    && { echo "  [$pid] ok"; n_done=$((n_done+1)); } \
    || echo "    WARN STEP_CS01 rc=$? for $pid (see ${pid}.cs.log)"
done
echo "  STEP_CS01: $n_done json, $n_skip empty/deep PAFs skipped"

# --- Step B: fold all cs JSONs into one long breakpoints table ---
echo ""; echo "--- Step B: csbp_dir_to_breakpoints ---"
FOLDED="$FOLD_DIR/bpatlas_seq_breakpoints.tsv"
python3 "$MODULE_DIR/csbp_dir_to_breakpoints.py" \
    --json-dir "$CSJSON_DIR" --out "$FOLDED" 2>&1 | tail -8 || {
  echo "  csbp fold produced no usable rows — check STEP_CS01 JSON schema"; exit 1; }

# --- Step C: re-cluster, adding the BP_ATLAS sequence source ---
# By default this builds a fresh cluster table from JUST the BP_ATLAS sequence
# layer. To merge with the prior gene-order/wfmash sources, pass them as extra
# --source args after the script name (NAME:PATH[:FAMILY]); they are forwarded
# verbatim to cluster_breakpoints.py.
echo ""; echo "--- Step C: cluster_breakpoints (re-cluster) ---"
# cluster_breakpoints.py lives in the OUTER comparative scripts/ dir, not here.
CLUSTER_PY="$(cd "$ROOT_DIR/.." && pwd)/scripts/cluster_breakpoints.py"
if [[ ! -f "$CLUSTER_PY" ]]; then
  # fall back to a sibling copy if the bundle layout differs
  CLUSTER_PY="$(find "$ROOT_DIR/.." -maxdepth 3 -name cluster_breakpoints.py 2>/dev/null | head -1)"
fi
[[ -f "$CLUSTER_PY" ]] || { echo "  cluster_breakpoints.py not found — fold table is at $FOLDED"; exit 0; }

CLUST_OUT="$FOLD_DIR/breakpoint_clusters_with_bpatlas.tsv"
EXTRA_SOURCES=()
# pass-through any extra --source the user appended
while [[ $# -gt 0 ]]; do EXTRA_SOURCES+=("$1"); shift; done

python3 "$CLUSTER_PY" \
    --source "bpatlas_seq:${FOLDED}:wfmash" \
    "${EXTRA_SOURCES[@]}" \
    --tol-kb "$TOL_KB" --split-wfmash \
    --out "$CLUST_OUT" 2>&1 | tail -8

echo ""; echo "=== fold done $(date) ==="
echo "  cs JSONs        : $CSJSON_DIR/"
echo "  folded seq table: $FOLDED"
echo "  re-clustered    : $CLUST_OUT"
echo "  reciprocity tier: $RESULTS_DIR/03_breakpoints/reciprocity/reciprocity_table.tsv"
echo ""
echo "Cohort boundary: this is COMPARATIVE/ASSEMBLY evidence (coordinates)."
echo "Hatchery haploblock join + styled S-tables are SEPARATE next chats."
