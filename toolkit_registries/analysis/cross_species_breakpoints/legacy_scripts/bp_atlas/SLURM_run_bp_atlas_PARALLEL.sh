#!/usr/bin/env bash
#SBATCH -p compute
#SBATCH -A lt200308
#SBATCH -N 1
#SBATCH --cpus-per-task=80
#SBATCH --mem=200GB
#SBATCH -t 12:00:00
#SBATCH -J bp_atlas
#SBATCH -o logs/bp_atlas.%j.out
#SBATCH -e logs/bp_atlas.%j.err
# =============================================================================
# SLURM_run_bp_atlas_PARALLEL.sh
#
# One sbatch, no SLURM arrays. Backgrounds N_PARALLEL wfmash pairs at a
# time on the same 80-cpu node, waits, starts the next batch.
#
# Submit from MODULE_BPATLAS/ (SLURM_SUBMIT_DIR resolves there):
#   cd /scratch/lt200308-agbsci/Quentin_project_KEEP_2026-02-04/MODULE_BPATLAS
#   mkdir -p logs   # required: #SBATCH -o logs/... is relative to submit dir
#   sbatch SLURM_run_bp_atlas_PARALLEL.sh
#
# Config:
#   All user-tunable knobs live in 00_bpatlas_config.sh next to this
#   script. Edit there, not here.
#
# Wall time estimate (5-hap cohort, 16 pairs):
#   16 pairs / 4 parallel = 4 batches x ~25-40 min/batch ~= 2-3 h stage 1
#   miniprot (optional, off by default unless PROTEOME set) ~30 min
#   BP2 + BP3 + BP3c + BP5_prep + BP6 ~= 5-10 min
#   Total ~3-4 h on a fresh run. 12 h wall budget is the safety margin.
#
# Resume: every pair's PAFs are checked before running; existing PAFs
# are skipped. Re-running this script after a partial run continues
# from where it left off in ~10 seconds for the validation pass.
# =============================================================================
set -euo pipefail

# =============================================================================
# Locate this script + load config
# =============================================================================
# SLURM_SUBMIT_DIR is the directory you ran `sbatch` from. We require that
# this script be submitted from MODULE_BPATLAS/, so MODULE_DIR is unambiguous
# whether running under sbatch or interactively.
SCRIPT_DIR="${SLURM_SUBMIT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
MODULE_DIR="${SCRIPT_DIR}"
ROOT_DIR="$(cd "${MODULE_DIR}/.." && pwd)"
RESULTS_DIR="${ROOT_DIR}/results_bpatlas"
LOGS_DIR="${ROOT_DIR}/logs"

# Sanity check the layout before doing anything destructive
[[ -f "${MODULE_DIR}/STEP_BP1_pairwise_wfmash.sh" ]] || {
    echo "[ERROR] MODULE_DIR does not look right (no STEP_BP1 found): ${MODULE_DIR}" >&2
    echo "        Submit this script from inside MODULE_BPATLAS/." >&2
    exit 1
}

CONFIG="${MODULE_DIR}/00_bpatlas_config.sh"
[[ -f "${CONFIG}" ]] || { echo "[ERROR] Missing config: ${CONFIG}" >&2; exit 1; }

# Export everything sourced from config so child scripts (STEP_BP1 reads
# MANIFEST from env, STEP_BP1b reads PROTEOME from env, etc.) inherit them.
export MODULE_DIR ROOT_DIR RESULTS_DIR LOGS_DIR
set -a
# shellcheck disable=SC1090
source "${CONFIG}"
set +a

# =============================================================================
# Activate environment
# =============================================================================
# shellcheck disable=SC1090
source ~/.bashrc
mamba activate "${CONDA_ENV}"

# =============================================================================
# Prep absolute output dirs
# =============================================================================
mkdir -p "${LOGS_DIR}" "${RESULTS_DIR}"

# A few subprocesses (rare) write to cwd. Park cwd at ROOT_DIR so any such
# stray output lands in a sane place rather than $HOME or the submit dir.
cd "${ROOT_DIR}"

echo "==========================================================="
echo "Job:         ${SLURM_JOB_ID:-interactive}  on $(hostname)"
echo "CPUs:        ${SLURM_CPUS_PER_TASK:-80} (${N_PARALLEL} parallel × ${CPUS_PER_TASK} each)"
echo "Date:        $(date)"
echo "MODULE_DIR:  ${MODULE_DIR}"
echo "ROOT_DIR:    ${ROOT_DIR}"
echo "RESULTS_DIR: ${RESULTS_DIR}"
echo "LOGS_DIR:    ${LOGS_DIR}"
echo "CONFIG:      ${CONFIG}"
echo "CONDA_ENV:   ${CONDA_ENV}"
echo "ANCHOR:      ${ANCHOR}"
echo "POP_TSV:     ${POP_TSV:-<unset>}"
echo "PROTEOME:    ${PROTEOME:-<unset>}"
echo "HIC_LOOKUP:  ${HIC_LOOKUP:-<unset>}"
echo "RUN_MINIPROT:${RUN_MINIPROT}    STAGE_END: ${STAGE_END}"
echo "==========================================================="

# =============================================================================
# STAGE 1: wfmash, N_PARALLEL pairs at a time
# =============================================================================
echo ""
echo "=== Stage 1: wfmash two-pass — $(date +%H:%M:%S) ==="

PAIRS_TSV="${RESULTS_DIR}/01_pairs/pairs.tsv"

# Build pairs.tsv. STEP_BP1 internally cd's to ROOT_DIR (its own logic) and
# writes ${RESULTS_DIR}/01_pairs/pairs.tsv.
bash "${MODULE_DIR}/STEP_BP1_pairwise_wfmash.sh" --build-pairs-only

[[ -f "${PAIRS_TSV}" ]] || {
    echo "[ERROR] STEP_BP1 --build-pairs-only did not produce ${PAIRS_TSV}" >&2
    exit 1
}

NPAIRS=$(awk -F'\t' 'NR>1 {n++} END {print n+0}' "${PAIRS_TSV}")
(( NPAIRS > 0 )) || { echo "[ERROR] 0 pairs in ${PAIRS_TSV}" >&2; exit 1; }
echo "  ${NPAIRS} pairs total, ${N_PARALLEL} at a time × ${CPUS_PER_TASK} cpus each"

run_one_pair() {
    local idx="$1"
    local pid
    pid=$(awk -F'\t' -v i="${idx}" 'NR>1 && $1==i {print $2}' "${PAIRS_TSV}")
    if [[ -z "${pid}" ]]; then
        echo "  [${idx}] ERROR: no row with pair_idx=${idx} in ${PAIRS_TSV}" >&2
        return 1
    fi

    local out_a="${RESULTS_DIR}/02_paf_passA/${pid}.paf"
    local out_b="${RESULTS_DIR}/02_paf_passB/${pid}.paf"

    # Resume: skip if both PAFs already non-empty
    if [[ -s "${out_a}" && -s "${out_b}" ]]; then
        echo "  [${idx}] ${pid} — already done, skip"
        return 0
    fi

    echo "  [${idx}] ${pid} — START $(date +%H:%M:%S)"

    local rc=0
    SLURM_ARRAY_TASK_ID="${idx}" \
    SLURM_CPUS_PER_TASK="${CPUS_PER_TASK}" \
        bash "${MODULE_DIR}/STEP_BP1_pairwise_wfmash.sh" \
        >  "${LOGS_DIR}/bp_wfmash_pair${idx}.out" \
        2> "${LOGS_DIR}/bp_wfmash_pair${idx}.err" \
        || rc=$?

    echo "  [${idx}] ${pid} — DONE  $(date +%H:%M:%S) (rc=${rc})"
    return "${rc}"
}

# Batch loop: 0, N_PARALLEL, 2*N_PARALLEL, ...
for batch_start in $(seq 0 "${N_PARALLEL}" $((NPAIRS-1))); do
    echo ""
    echo "--- batch starting at pair ${batch_start} --- $(date +%H:%M:%S)"

    bg_pids=()
    for k in $(seq 0 $((N_PARALLEL-1))); do
        idx=$((batch_start + k))
        (( idx >= NPAIRS )) && break
        run_one_pair "${idx}" &
        bg_pids+=($!)
    done

    for p in "${bg_pids[@]}"; do
        wait "${p}" || echo "  WARN: a pair in this batch returned non-zero"
    done
done

# Verify all PAFs landed
MISSING=0
while IFS=$'\t' read -r pidx pid _rest; do
    [[ "${pidx}" == "pair_idx" ]] && continue
    [[ -s "${RESULTS_DIR}/02_paf_passA/${pid}.paf" ]] \
        || { echo "  MISSING Pass A: ${pid}.paf"; MISSING=$((MISSING+1)); }
    [[ -s "${RESULTS_DIR}/02_paf_passB/${pid}.paf" ]] \
        || { echo "  MISSING Pass B: ${pid}.paf"; MISSING=$((MISSING+1)); }
done < "${PAIRS_TSV}"

if (( MISSING > 0 )); then
    echo "[ERROR] ${MISSING} wfmash outputs missing — check ${LOGS_DIR}/bp_wfmash_pair*.err"
    echo "        Re-running this script will resume from where it left off."
    exit 2
fi
touch "${RESULTS_DIR}/01_pairs/.done"
echo ""
echo "  Stage 1 complete: $(date +%H:%M:%S)"

# =============================================================================
# STAGE 1b: miniprot, N_PARALLEL haplotypes at a time
# =============================================================================
if [[ "${RUN_MINIPROT}" == "1" && -n "${PROTEOME}" && -f "${PROTEOME}" ]]; then
    echo ""
    echo "=== Stage 1b: miniprot — $(date +%H:%M:%S) ==="

    JOBS_TSV="${RESULTS_DIR}/01b_miniprot_jobs/jobs.tsv"

    bash "${MODULE_DIR}/STEP_BP1b_miniprot_anchors.sh" --build-jobs-only

    [[ -f "${JOBS_TSV}" ]] || {
        echo "[ERROR] STEP_BP1b --build-jobs-only did not produce ${JOBS_TSV}" >&2
        exit 1
    }

    NHAPS=$(awk -F'\t' 'NR>1 {n++} END {print n+0}' "${JOBS_TSV}")
    echo "  ${NHAPS} haplotypes, ${N_PARALLEL} at a time × ${CPUS_PER_TASK} cpus each"

    run_one_hap() {
        local idx="$1"
        local hid
        hid=$(awk -F'\t' -v i="${idx}" 'NR>1 && $1==i {print $2}' "${JOBS_TSV}")
        if [[ -z "${hid}" ]]; then
            echo "  [${idx}] ERROR: no row with job_idx=${idx} in ${JOBS_TSV}" >&2
            return 1
        fi

        local out_paf="${RESULTS_DIR}/02b_miniprot_anchors/${hid}.paf"
        if [[ -s "${out_paf}" ]]; then
            echo "  [${idx}] ${hid} — already done, skip"
            return 0
        fi

        echo "  [${idx}] ${hid} — START $(date +%H:%M:%S)"
        local rc=0
        SLURM_ARRAY_TASK_ID="${idx}" \
        SLURM_CPUS_PER_TASK="${CPUS_PER_TASK}" \
            bash "${MODULE_DIR}/STEP_BP1b_miniprot_anchors.sh" \
            >  "${LOGS_DIR}/bp_miniprot_${idx}.out" \
            2> "${LOGS_DIR}/bp_miniprot_${idx}.err" \
            || rc=$?
        echo "  [${idx}] ${hid} — DONE  $(date +%H:%M:%S) (rc=${rc})"
        return "${rc}"
    }

    for batch_start in $(seq 0 "${N_PARALLEL}" $((NHAPS-1))); do
        bg_pids=()
        for k in $(seq 0 $((N_PARALLEL-1))); do
            idx=$((batch_start + k))
            (( idx >= NHAPS )) && break
            run_one_hap "${idx}" &
            bg_pids+=($!)
        done
        for p in "${bg_pids[@]}"; do wait "${p}" || true; done
    done
    touch "${RESULTS_DIR}/01b_miniprot_jobs/.done"
    echo "  Stage 1b complete: $(date +%H:%M:%S)"
else
    echo ""
    echo "=== Stage 1b: SKIPPED (PROTEOME not set/missing, or RUN_MINIPROT=0) ==="
fi

# =============================================================================
# STAGE 2 + 3: BP2 + BP3 (fast python steps, run via the main orchestrator)
# =============================================================================
echo ""
echo "=== Stage 2 + 3: BP2 + BP3 — $(date +%H:%M:%S) ==="

ARGS=(
    --anchor "${ANCHOR}"
    --stage-start 2
    --stage-end   "${STAGE_END}"
    --skip-slurm-wait
)
[[ -n "${POP_TSV}"    ]] && ARGS+=( --pop        "${POP_TSV}" )
[[ -n "${PROTEOME}"   ]] && ARGS+=( --proteome   "${PROTEOME}" )
[[ -n "${HIC_LOOKUP}" ]] && ARGS+=( --hic-lookup "${HIC_LOOKUP}" )

bash "${MODULE_DIR}/run_bp_atlas.sh" "${ARGS[@]}"

echo ""
echo "==========================================================="
echo "Done: $(date)"
echo "==========================================================="
