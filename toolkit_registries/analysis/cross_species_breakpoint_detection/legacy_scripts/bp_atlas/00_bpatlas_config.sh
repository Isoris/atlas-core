# ============================================================================
# 00_bpatlas_config.sh — central config for MODULE_BPATLAS
#
# Sourced by SLURM_run_bp_atlas_PARALLEL.sh (and any other driver in this
# module) via:
#       set -a
#       source "${CONFIG}"
#       set +a
# so every variable below is automatically exported into the environment of
# child scripts (STEP_BP1, STEP_BP1b, run_bp_atlas.sh). This is intentional:
# STEP_BP1 picks up MANIFEST from env, STEP_BP1b picks up PROTEOME from env.
#
# Edit values here, not in the SLURM script.
# ============================================================================

# ---- absolute layout ------------------------------------------------------
# MODULE_DIR  : directory containing this config and all STEP_BP*.{sh,py,R}
# ROOT_DIR    : parent of MODULE_DIR — outputs land in $ROOT_DIR/results_bpatlas
# RESULTS_DIR : absolute results root
# LOGS_DIR    : absolute logs root
#
# These are set from SLURM_SUBMIT_DIR by the SLURM script BEFORE sourcing
# this file, so we just reference them here for documentation; don't
# reassign them.
MODULE_DIR="${MODULE_DIR:?MODULE_DIR must be set by the caller before sourcing this config}"
ROOT_DIR="${ROOT_DIR:?ROOT_DIR must be set by the caller before sourcing this config}"
RESULTS_DIR="${RESULTS_DIR:-${ROOT_DIR}/results_bpatlas}"
LOGS_DIR="${LOGS_DIR:-${ROOT_DIR}/logs}"

# ---- conda / mamba environment -------------------------------------------
CONDA_ENV="${CONDA_ENV:-assembly}"

# ---- parallelism ---------------------------------------------------------
# N_PARALLEL × CPUS_PER_TASK should be ≤ the cpus-per-task in the SBATCH
# header of the SLURM driver. Current driver requests 80 cpus.
N_PARALLEL="${N_PARALLEL:-4}"
CPUS_PER_TASK="${CPUS_PER_TASK:-16}"

# ---- pipeline parameters -------------------------------------------------
# Anchor species for STEP_BP3 zone re-anchoring. "Cgar,Cmac" runs the
# clustering twice, once with each species as the anchor frame.
ANCHOR="${ANCHOR:-Cgar,Cmac}"

# Population candidate catalogue from inversion-popgen-toolkit phase_8.
# Empty string = skip STEP_BP4 overlap join.
POP_TSV="${POP_TSV:-}"

# Polished reference proteome for miniprot anchor track (STEP_BP1b).
# Lives under ${MODULE_DIR}/00_input/proteomes/. Empty string = skip
# Stage 1b entirely (current state: the proteomes/ dir exists but is
# empty, so Stage 1b is intentionally off until you drop a .faa in).
# To enable: place the proteome at
#   ${MODULE_DIR}/00_input/proteomes/fClaHyb_Gar.proteins.faa
# and uncomment the second line below.
PROTEOME="${PROTEOME:-}"
# PROTEOME="${PROTEOME:-${MODULE_DIR}/00_input/proteomes/fClaHyb_Gar.proteins.faa}"

# Pre-existing Hi-C evidence lookup TSV (chrom, start, end, evidence_note).
# Empty = no hic_evidence column in STEP_BP4 output.
HIC_LOOKUP="${HIC_LOOKUP:-}"

# Haplotype manifest used by STEP_BP1 and STEP_BP1b. If unset, both scripts
# default to "${MODULE_DIR}/haplotype_manifest.tsv".
MANIFEST="${MANIFEST:-${MODULE_DIR}/haplotype_manifest.tsv}"

# ---- stage gating --------------------------------------------------------
# Run STEP_BP1b miniprot stage? (0 = skip even if PROTEOME is set)
RUN_MINIPROT="${RUN_MINIPROT:-1}"

# How far through the pipeline to run via run_bp_atlas.sh after Stage 1.
# 3 = stop after STEP_BP3 (zone catalogue); 4 = also run STEP_BP4
# population overlap; 5 = also run STEP_BP5 figures + atlas_data.json +
# ribbon montages; 6 = also run STEP_BP6 joint A-E classification (the
# manuscript table).
STAGE_END="${STAGE_END:-6}"

# Comma-separated stages to skip entirely. Useful to bypass the legacy
# Stage 5/5b figure scripts (whose F3 zone-landscape panel currently
# crashes on a data.table::fread schema mismatch with the newer BP3
# output). The new ribbon montages at Stage 3e are the headline figures
# and run regardless of this setting. To re-enable Stage 5, export
# SKIP_STAGES="" before submitting the SLURM job.
SKIP_STAGES="${SKIP_STAGES:-5,5b}"

# ---- Stage 6 inputs (joint A-E classification) ----------------------------
# Optional. Empty defaults => STEP_BP6 runs in STUB MODE and every BP zone
# becomes Class C/E. Fill these in once the popgen/Mendelian/popstats
# tables are ready. Schemas are documented at the top of
# STEP_BP6_joint_classify.py.
POPGEN_TSV="${POPGEN_TSV:-}"
MENDELIAN_TSV="${MENDELIAN_TSV:-}"
POPSTATS_TSV="${POPSTATS_TSV:-}"
