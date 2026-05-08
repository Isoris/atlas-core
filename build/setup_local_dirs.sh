#!/usr/bin/env bash
# atlas-core/build/setup_local_dirs.sh
# =====================================================================
# Lay down the directory layout the atlas proposes on /mnt/e/.
#
# The atlas owns the SHAPE of the tree (which paths exist, what each
# slot is for). The atlas does NOT own where your raw data lives or
# how it gets into those slots — that's a one-time external decision:
# move files in, symlink them in, mount a network share into them, up
# to you. Re-run this script as often as you want; it only ever
# creates folders.
#
# Run from WSL:
#     bash atlas-core/build/setup_local_dirs.sh
#
# Idempotent (mkdir -p only).
# =====================================================================

set -euo pipefail

MNT=/mnt/e
SHARED="$MNT/_shared"
RESULTS_INV="$MNT/results_inversions"
RESULTS_DIV="$MNT/results_diversity"
RESULTS_POP="$MNT/results_population"
RESULTS_GEN="$MNT/results_genome"
CACHE="$MNT/atlas-cache"

echo "==> _shared/ ($SHARED)"
# Cohort-wide inputs the whole atlas reads (samples.ind, chrom_sizes.tsv,
# callable_regions, reference fasta, etc.). Used by inversions, diversity,
# AND population — top-level so no result tree owns it.
mkdir -p \
  "$SHARED" \
  "$SHARED/reference"

echo "==> results_inversions/ ($RESULTS_INV)"
# 03_theta_pi_pestPG holds the win10000.step2000 slice consumed by the
# theta-pi local-PCA path (STEP_TR_A/B). The full 4-scale pestPG bundle
# lives in results_diversity/03_theta_pi — we only duplicate the slice
# the inversion path actually reads.
mkdir -p \
  "$RESULTS_INV/01_beagle" \
  "$RESULTS_INV/02_dosage_sites" \
  "$RESULTS_INV/03_theta_pi_pestPG" \
  "$RESULTS_INV/04_clair3_phased_GHSL"

for path in local_PCA_MDS_z local_PCA_MDS_theta_pi local_PCA_MDS_GHSL; do
  mkdir -p \
    "$RESULTS_INV/$path/01_local_pca" \
    "$RESULTS_INV/$path/02_mds" \
    "$RESULTS_INV/$path/03_per_chrom" \
    "$RESULTS_INV/$path/04_atlas_json"
  for nn in 01 02 03 04 05 06 07 08 09 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24 25 26 27 28; do
    mkdir -p "$RESULTS_INV/$path/03_per_chrom/C_gar_LG$nn"
  done
done

echo "==> results_diversity/ ($RESULTS_DIV)"
# Folder names mirror the producer repo at
# /mnt/c/Users/quent/Desktop/catfish-diversity-analysis/Modules/.
# When the producer adds a module, add the matching slot here.
mkdir -p \
  "$RESULTS_DIV/01_saf_per_sample" \
  "$RESULTS_DIV/02_heterozygosity" \
  "$RESULTS_DIV/03_theta_pi" \
  "$RESULTS_DIV/04_roh" \
  "$RESULTS_DIV/05_aggregated"

echo "==> results_population/ ($RESULTS_POP)"
mkdir -p \
  "$RESULTS_POP/01_natora_pruned" \
  "$RESULTS_POP/02_ngsrelate" \
  "$RESULTS_POP/03_ngsadmix" \
  "$RESULTS_POP/04_pcangsd" \
  "$RESULTS_POP/05_evaladmix" \
  "$RESULTS_POP/06_FPW"

echo "==> results_genome/ ($RESULTS_GEN)"
mkdir -p \
  "$RESULTS_GEN/01_assembly" \
  "$RESULTS_GEN/02_annotation" \
  "$RESULTS_GEN/03_TE_density" \
  "$RESULTS_GEN/04_synteny"

echo "==> atlas-cache/ ($CACHE)"
# Server caches (filled by atlas_server.py + the registry persist hook)
mkdir -p \
  "$CACHE/popstats_engine_cache" \
  "$CACHE/popstats_server_cache" \
  "$CACHE/server_results" \
  "$CACHE/empty_bams" \
  "$CACHE/empty_ancestry_cache"
# Writable evidence roots referenced from master_config.yaml
mkdir -p \
  "$CACHE/candidates" \
  "$CACHE/arrangement_calls" \
  "$CACHE/comparative" \
  "$CACHE/review/inversion/sessions" \
  "$CACHE/working_dir"

echo
echo "==> done."
echo "    next:  put your raw outputs into the slots above (move/symlink/mount —"
echo "           your call), then:"
echo "             bash atlas-core/build/assemble.sh"
echo "             cd ../atlas-workspace && bash start.sh"
