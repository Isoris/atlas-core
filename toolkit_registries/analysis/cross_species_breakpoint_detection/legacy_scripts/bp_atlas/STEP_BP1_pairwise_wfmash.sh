#!/usr/bin/env bash
#SBATCH --job-name=bpatlas_wfmash
#SBATCH --account=lt200308
#SBATCH --partition=compute
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=32
#SBATCH --mem=128G
#SBATCH --time=06:00:00
#SBATCH --output=logs/bpatlas_wfmash_%A_%a.out
#SBATCH --error=logs/bpatlas_wfmash_%A_%a.err
# ============================================================================
# STEP_BP1_pairwise_wfmash.sh
#
# Two-pass wfmash alignment for every (query, target) haplotype pair.
# minimap2 is intentionally NOT used here — base-level alignments are
# wasted at the resolution the inversion atlas works at, and minimap2
# produces noisy multi-mapping in repeat-rich regions of the catfish
# genome where wfmash's mashmap3 minmer filtering is more robust.
#
# Two passes per pair:
#
#   Pass A  -s 100k -n 1 -m       sensitive — catches ~100 kb inversions.
#                                  This is the input to STEP_BP2 breakpoint
#                                  detection.
#
#   Pass B  -s 500k -n 1 -m       backbone — coarser synteny chain.
#                                  Used by STEP_BP3 to flag Pass-A zones
#                                  that don't sit on a real backbone (likely
#                                  repeat-driven false positives).
#
# Both passes use --approx-mapping (-m): no WFA base alignment. Reasons:
#   1. Quentin's zone clustering already tolerates ±50–500 kb, so base
#      precision is wasted.
#   2. WFA is quadratic in differences; cross-species pairs at -s 100k
#      with full alignment would take 4–8 h/pair × 25 pairs.
#   3. Strand orientation comes from the mashmap chain itself, not from
#      base-level CIGAR — orientation switches are visible in approx mode.
#
# QC-tier rule (unchanged):
#   tier-C haplotypes (broken assemblies) NEVER appear as the QUERY of a
#   pair. They appear only as TARGETS so phantom breakpoints from
#   fragmentation cannot define new events.
#
# Usage:
#   bash MODULE_BPATLAS/STEP_BP1_pairwise_wfmash.sh --build-pairs-only
#   sbatch --array=0-$((NPAIRS-1)) MODULE_BPATLAS/STEP_BP1_pairwise_wfmash.sh
# ============================================================================
set -euo pipefail

MODULE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$MODULE_DIR/.." && pwd)"
cd "$ROOT_DIR"

MANIFEST="${MANIFEST:-$MODULE_DIR/haplotype_manifest.tsv}"
PAIRS_DIR="results_bpatlas/01_pairs"
PAF_DIR_A="results_bpatlas/02_paf_passA"  # sensitive (-s 100k)
PAF_DIR_B="results_bpatlas/02_paf_passB"  # backbone  (-s 500k)
mkdir -p logs "$PAIRS_DIR" "$PAF_DIR_A" "$PAF_DIR_B"

# Pass parameters — change here, not in the SLURM body
PASS_A_SEG=100000           # 100 kb segments — medium inversion sensitive
PASS_B_SEG=500000           # 500 kb backbone
PASS_A_MAP_PCT=85           # within/cross-species ANI floor (A pairs are ≥95% identical)
PASS_B_MAP_PCT=85
WFMASH_THREADS="${SLURM_CPUS_PER_TASK:-32}"

# ----------------------------------------------------------------------------
# CROSS-SPECIES DIVERGENCE TIERS (added for the 18-genome run).
# Per-pair %identity floor, chosen by the MORE diverged of the two species so
# wfmash uses a threshold the pair can actually clear. Tier by genus/family
# from the BUSCO timetree:
#   same genus Clarias (~15-20 MYA)            -> p90
#   within Clariidae+near (Cranoglanis ~40My)  -> p85
#   other Siluroidei (~55-65 MYA)              -> p80
#   deep outgroup (Plotosus ~85, Tricho ~100)  -> SKIP (handled by tier-C, never query)
# Species code from manifest column 2 (species). Unknown -> p80 (safe mid).
declare -A SPTIER=(
  [Cgar]=0 [Cmac]=0 [Cfus]=0 [Capus]=0      # genus-level: same-genus pairs get p90
  [Cbou]=1                                   # Cranoglanididae ~40My
  [Ifur]=2 [Ipun]=2 [Amel]=2 [Hwyc]=2 [Tful]=2 [Tvac]=2 [Smer]=2 [Sari]=2 [Phyp]=2 [Ngra]=2
  [Plin]=3 [Tros]=3                          # deep outgroups
)
pair_identity() {
  # args: qsp tsp  -> echo the -p floor for this pair
  # The floor is set by the MORE diverged of the two species' tiers. Same-genus
  # Clarias pairs are already both tier 0, so their max is 0 -> p90; no special
  # case is needed.
  local a="${1}" b="${2}"
  local ta="${SPTIER[$a]:-2}" tb="${SPTIER[$b]:-2}"
  local t=$(( ta > tb ? ta : tb ))          # use the MORE diverged tier
  case "$t" in
    0) echo 90 ;;
    1) echo 85 ;;
    2) echo 80 ;;
    *) echo 0  ;;   # deep -> caller skips
  esac
}

# ----------------------------------------------------------------------------
# Build pairs.tsv (unchanged from minimap2 version)
# ----------------------------------------------------------------------------
build_pairs() {
    local out="$PAIRS_DIR/pairs.tsv"
    echo -e "pair_idx\tpair_id\tquery_id\tquery_species\tquery_qc\tquery_fa\ttarget_id\ttarget_species\ttarget_qc\ttarget_fa\tpair_kind" > "$out"

    local ids=() species=() qc=() fa=()
    while IFS=$'\t' read -r hid sp src tier path notes; do
        [[ "$hid" =~ ^#.*$ ]] && continue
        [[ -z "$hid" ]] && continue
        # Skip the TSV header row. Identified by content rather than line
        # number so the parser is robust to leading blank/comment lines.
        # Earlier run 5743651 ingested "haplotype_id" (the column name)
        # as a 6th haplotype and produced 9 phantom pairs that failed rc=2.
        [[ "$hid" == "haplotype_id" ]] && continue
        ids+=("$hid"); species+=("$sp"); qc+=("$tier"); fa+=("$path")
    done < "$MANIFEST"

    local n=${#ids[@]}
    local idx=0
    for ((i=0; i<n; i++)); do
        for ((j=0; j<n; j++)); do
            (( i == j )) && continue
            [[ "${qc[i]}" == "C" ]] && continue

            local kind
            if [[ "${species[i]}" == "${species[j]}" ]]; then
                kind="within_${species[i]}"
            else
                kind="cross_${species[i]}_vs_${species[j]}"
            fi

            local pair_id="${ids[i]}__vs__${ids[j]}"
            printf "%d\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n" \
                "$idx" "$pair_id" \
                "${ids[i]}" "${species[i]}" "${qc[i]}" "${fa[i]}" \
                "${ids[j]}" "${species[j]}" "${qc[j]}" "${fa[j]}" \
                "$kind" >> "$out"
            idx=$((idx + 1))
        done
    done
    echo "[STEP_BP1] Wrote $idx pairs -> $out" >&2
    echo "$idx"
}

if [[ "${1:-}" == "--build-pairs-only" ]]; then
    NPAIRS=$(build_pairs)
    echo "[STEP_BP1] $NPAIRS pairs to align."
    echo "[STEP_BP1] Submit with: sbatch --array=0-$((NPAIRS-1)) $0"
    exit 0
fi

# ----------------------------------------------------------------------------
# SLURM array task — pick our pair, run BOTH passes
# ----------------------------------------------------------------------------
PAIRS_FILE="$PAIRS_DIR/pairs.tsv"
[[ -f "$PAIRS_FILE" ]] || { echo "ERROR: $PAIRS_FILE missing — run with --build-pairs-only first"; exit 1; }

ARRAY_IDX="${SLURM_ARRAY_TASK_ID:?This script must be run as a SLURM array}"

ROW=$(awk -F'\t' -v idx="$ARRAY_IDX" 'NR>1 && $1==idx' "$PAIRS_FILE")
[[ -n "$ROW" ]] || { echo "ERROR: no pair with idx=$ARRAY_IDX"; exit 1; }

read -r _ PAIR_ID QID QSP QQC QFA TID TSP TQC TFA KIND <<< "$(echo "$ROW" | tr '\t' ' ')"

# Cross-species: pick the identity floor for THIS pair by divergence tier.
PASS_P=$(pair_identity "$QSP" "$TSP")
if [[ "$PASS_P" == "0" ]]; then
  echo "[STEP_BP1] SKIP $PAIR_ID: deep-outgroup pair ($QSP vs $TSP) — wfmash cannot align; gene-order only."
  # Write empty PAFs + meta so the resume/verify logic is satisfied.
  : > "${PAF_DIR_A}/${PAIR_ID}.paf"; : > "${PAF_DIR_B}/${PAIR_ID}.paf"
  printf "pair_id\tquery_id\tquery_species\tquery_qc\ttarget_id\ttarget_species\ttarget_qc\tpair_kind\tn_records_A\tn_records_B\n%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t0\t0\n" \
    "$PAIR_ID" "$QID" "$QSP" "$QQC" "$TID" "$TSP" "$TQC" "$KIND" \
    | tee "${PAF_DIR_A}/${PAIR_ID}.meta.tsv" > "${PAF_DIR_B}/${PAIR_ID}.meta.tsv"
  exit 0
fi
echo "[STEP_BP1] divergence tier -> -p ${PASS_P} for $QSP vs $TSP"

echo "==========================================================="
echo "[STEP_BP1] pair $ARRAY_IDX: $PAIR_ID"
echo "  query : $QID ($QSP, qc=$QQC) -> $QFA"
echo "  target: $TID ($TSP, qc=$TQC) -> $TFA"
echo "  kind  : $KIND"
echo "==========================================================="

# LANTA used: module load Miniconda3 + source activate assembly.
# Laptop-safe: only attempt if the tools aren't already on PATH. Never fatal.
if ! command -v wfmash >/dev/null 2>&1; then
    module load Miniconda3 2>/dev/null || true
    source activate assembly 2>/dev/null || conda activate assembly 2>/dev/null || true
fi

[[ -f "$QFA" ]] || { echo "ERROR: query FASTA missing: $QFA"; exit 2; }
[[ -f "$TFA" ]] || { echo "ERROR: target FASTA missing: $TFA"; exit 2; }

# wfmash needs bgzip + samtools fai indexes on its inputs; build if missing.
prepare_index() {
    local fa="$1"
    if [[ "$fa" == *.gz ]]; then
        # Must be bgzip, not gzip
        if ! file "$fa" 2>/dev/null | grep -q "BGZF"; then
            echo "[STEP_BP1] WARNING: $fa is gzip not bgzip — wfmash needs bgzip"
            echo "  to fix: zcat $fa | bgzip > ${fa%.gz}.bgz; mv ${fa%.gz}.bgz $fa"
            return 1
        fi
        [[ -f "${fa}.gzi" ]] || samtools faidx "$fa"
        [[ -f "${fa}.fai" ]] || samtools faidx "$fa"
    else
        [[ -f "${fa}.fai" ]] || samtools faidx "$fa"
    fi
}
prepare_index "$QFA" || exit 3
prepare_index "$TFA" || exit 3

# ----------------------------------------------------------------------------
# Pass A — sensitive: -s 100k, mashmap one-to-one, approx mode
# ----------------------------------------------------------------------------
OUT_A="${PAF_DIR_A}/${PAIR_ID}.paf"
LOG_A="${PAF_DIR_A}/${PAIR_ID}.log"

echo ""
echo "[STEP_BP1] Pass A (sensitive, -s ${PASS_A_SEG}, approx)"
time wfmash \
    -t "$WFMASH_THREADS" \
    -s "$PASS_A_SEG" \
    -p "$PASS_P" \
    -n 1 \
    -m \
    "$TFA" "$QFA" \
    > "$OUT_A" 2> "$LOG_A"

NREC_A=$(wc -l < "$OUT_A")
echo "[STEP_BP1] Pass A: $NREC_A records -> $OUT_A"

# ----------------------------------------------------------------------------
# Pass B — backbone: -s 500k, mashmap one-to-one, approx mode
# ----------------------------------------------------------------------------
OUT_B="${PAF_DIR_B}/${PAIR_ID}.paf"
LOG_B="${PAF_DIR_B}/${PAIR_ID}.log"

echo ""
echo "[STEP_BP1] Pass B (backbone, -s ${PASS_B_SEG}, approx)"
time wfmash \
    -t "$WFMASH_THREADS" \
    -s "$PASS_B_SEG" \
    -p "$PASS_P" \
    -n 1 \
    -m \
    "$TFA" "$QFA" \
    > "$OUT_B" 2> "$LOG_B"

NREC_B=$(wc -l < "$OUT_B")
echo "[STEP_BP1] Pass B: $NREC_B records -> $OUT_B"

# ----------------------------------------------------------------------------
# Per-pair metadata sidecar — schema must match what STEP_BP2 reads.
# Both passes share the same meta; STEP_BP2 picks Pass A as primary.
# ----------------------------------------------------------------------------
META_PAYLOAD=$(printf "pair_id\tquery_id\tquery_species\tquery_qc\ttarget_id\ttarget_species\ttarget_qc\tpair_kind\tn_records_A\tn_records_B\n%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%d\t%d\n" \
    "$PAIR_ID" "$QID" "$QSP" "$QQC" "$TID" "$TSP" "$TQC" "$KIND" "$NREC_A" "$NREC_B")
echo "$META_PAYLOAD" > "${PAF_DIR_A}/${PAIR_ID}.meta.tsv"
echo "$META_PAYLOAD" > "${PAF_DIR_B}/${PAIR_ID}.meta.tsv"

# Quick sanity warnings
if (( NREC_A < 50 )); then
    echo "[STEP_BP1] WARNING: very few Pass A records for $PAIR_ID — check FASTA indexing or ANI floor" >&2
fi
if (( NREC_B < 20 )); then
    echo "[STEP_BP1] WARNING: very few Pass B records for $PAIR_ID — backbone will be sparse" >&2
fi

echo ""
echo "[STEP_BP1] Done."
