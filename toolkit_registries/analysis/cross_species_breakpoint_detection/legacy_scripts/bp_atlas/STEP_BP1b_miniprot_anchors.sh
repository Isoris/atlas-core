#!/usr/bin/env bash
#SBATCH --job-name=bpatlas_miniprot
#SBATCH --account=lt200308
#SBATCH --partition=compute
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=16
#SBATCH --mem=48G
#SBATCH --time=02:00:00
#SBATCH --output=logs/bpatlas_miniprot_%A_%a.out
#SBATCH --error=logs/bpatlas_miniprot_%A_%a.err
# ============================================================================
# STEP_BP1b_miniprot_anchors.sh
#
# Runs miniprot once per haplotype, aligning a polished reference proteome
# (default: fClaHyb_Gar.proteins.faa, ~30k proteins) against the haplotype's
# genome FASTA. One PAF per haplotype.
#
# This is the gene-anchor track for the atlas — independent of the wfmash
# breakpoint detection. The miniprot anchors give *dense* protein-resolution
# dotplots (denser than wfmash 100k segments by 1–2 orders of magnitude),
# which is exactly the visual confirmation the *T. cristinae* paper does
# in its Fig 1B-style synteny dots.
#
# Why one PAF per haplotype instead of per pair:
#   - The reference proteome is the SAME for all haplotypes.
#   - To compare "haplotype X vs haplotype Y", we just intersect their
#     two PAFs on protein_id — so N runs, not N(N-1) runs. 6 haplotypes
#     in this module = 6 miniprot runs, not 25.
#
# Reuses STEP_Jc1_miniprot_wholegenome.sh's --outs=0.5 lenient threshold
# (the toolkit's existing convention).
#
# Usage:
#   bash STEP_BP1b_miniprot_anchors.sh --build-jobs-only
#   sbatch --array=0-$((NHAPS-1)) STEP_BP1b_miniprot_anchors.sh
#
# Required env / args:
#   PROTEOME      path to .faa, defaults to fClaHyb_Gar.proteins.faa
# ============================================================================
set -euo pipefail

MODULE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$MODULE_DIR/.." && pwd)"
cd "$ROOT_DIR"

MANIFEST="${MANIFEST:-$MODULE_DIR/haplotype_manifest.tsv}"
PROTEOME="${PROTEOME:-/scratch/lt200308-agbsci/Quentin_project_KEEP_2026-02-04/proteomes/fClaHyb_Gar.proteins.faa}"
JOBS_DIR="results_bpatlas/01b_miniprot_jobs"
ANCHORS_DIR="results_bpatlas/02b_miniprot_anchors"
mkdir -p logs "$JOBS_DIR" "$ANCHORS_DIR"

MINIPROT_THREADS="${SLURM_CPUS_PER_TASK:-16}"
MIN_IDENTITY=0.5      # toolkit convention from MODULE_CONSERVATION
OUTS_FRAC=0.5         # match STEP_Jc1's lenient threshold

build_jobs() {
    local out="$JOBS_DIR/jobs.tsv"
    echo -e "job_idx\thaplotype_id\tspecies\tqc_tier\tfasta_path" > "$out"
    local idx=0
    while IFS=$'\t' read -r hid sp src tier path notes; do
        [[ "$hid" =~ ^#.*$ ]] && continue
        [[ -z "$hid" ]] && continue
        # Skip the TSV header row (see STEP_BP1 for rationale).
        [[ "$hid" == "haplotype_id" ]] && continue
        printf "%d\t%s\t%s\t%s\t%s\n" "$idx" "$hid" "$sp" "$tier" "$path" >> "$out"
        idx=$((idx + 1))
    done < "$MANIFEST"
    echo "[STEP_BP1b] Wrote $idx haplotype jobs -> $out" >&2
    echo "$idx"
}

if [[ "${1:-}" == "--build-jobs-only" ]]; then
    NHAPS=$(build_jobs)
    echo "[STEP_BP1b] $NHAPS haplotypes to anchor."
    echo "[STEP_BP1b] Submit with: sbatch --array=0-$((NHAPS-1)) $0"
    exit 0
fi

JOBS_FILE="$JOBS_DIR/jobs.tsv"
[[ -f "$JOBS_FILE" ]] || { echo "ERROR: $JOBS_FILE missing — run with --build-jobs-only first"; exit 1; }

ARRAY_IDX="${SLURM_ARRAY_TASK_ID:?This script must be run as a SLURM array}"

ROW=$(awk -F'\t' -v idx="$ARRAY_IDX" 'NR>1 && $1==idx' "$JOBS_FILE")
[[ -n "$ROW" ]] || { echo "ERROR: no job with idx=$ARRAY_IDX"; exit 1; }
read -r _ HID SP QC FA <<< "$(echo "$ROW" | tr '\t' ' ')"

OUT_PAF="${ANCHORS_DIR}/${HID}.paf"
OUT_LOG="${ANCHORS_DIR}/${HID}.log"

echo "==========================================================="
echo "[STEP_BP1b] miniprot $HID ($SP, qc=$QC)"
echo "  proteome: $PROTEOME"
echo "  target:   $FA"
echo "  output:   $OUT_PAF"
echo "==========================================================="

module load Miniconda3 || true
source activate assembly

[[ -f "$FA" ]] || { echo "ERROR: target FASTA missing: $FA"; exit 2; }
[[ -f "$PROTEOME" ]] || { echo "ERROR: proteome missing: $PROTEOME"; exit 2; }

# miniprot:
#   --outs F  output alignments with score >= F * top score per protein
#             (lenient = 0.5 = collect mode; refining done downstream)
#   -t        threads
#   PAF mode is default with --aln=no (we don't need CIGAR; gene anchors
#   are point-like for the dotplot). For the atlas track we want the
#   genomic span though, so leave --aln on.
time miniprot \
    -t "$MINIPROT_THREADS" \
    --outs "$OUTS_FRAC" \
    "$FA" "$PROTEOME" \
    > "$OUT_PAF" \
    2> "$OUT_LOG"

NREC=$(wc -l < "$OUT_PAF")
echo "[STEP_BP1b] $HID: $NREC PAF records"

if (( NREC < 5000 )); then
    echo "[STEP_BP1b] WARNING: only $NREC anchors for $HID — assembly fragmented or proteome wrong?" >&2
fi

# Sidecar metadata
{
    echo -e "haplotype_id\tspecies\tqc_tier\tfasta_path\tproteome\tn_records"
    echo -e "${HID}\t${SP}\t${QC}\t${FA}\t${PROTEOME}\t${NREC}"
} > "${ANCHORS_DIR}/${HID}.meta.tsv"

echo "[STEP_BP1b] Done."
