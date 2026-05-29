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
# Every results_<atlas>/ tree below mirrors a master_config.yaml `root`.
# The per-slot file patterns each atlas reads are documented in
# docs/DATA_LAYOUT.md — consult that to know WHICH files go in each slot.
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
RESULTS_CS="$MNT/results_cross_species"
RESULTS_EVO="$MNT/results_evolution"
RESULTS_PS="$MNT/results_popstats"
RESULTS_PODS="$MNT/results_pods"
RESULTS_LOADS="$MNT/results_loads"
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
# GHSL + z-blocks emit their atlas JSONs under a higher-numbered dir
# (09/10_atlas_json) than the theta-pi path (04). master_config points the
# precomp_zblocks / precomp_ghsl roots at those; create them so the
# /api/precomp_index depth-2 scan finds the per-chrom subfolders.
mkdir -p \
  "$RESULTS_INV/local_PCA_MDS_z/09_atlas_json" \
  "$RESULTS_INV/local_PCA_MDS_GHSL/10_atlas_json"

echo "==> results_diversity/ ($RESULTS_DIV)"
# Folder names mirror the producer repo at
# /mnt/c/Users/quent/Desktop/catfish-diversity-analysis/Modules/.
# When the producer adds a module, add the matching slot here.
mkdir -p \
  "$RESULTS_DIV/01_saf_per_sample" \
  "$RESULTS_DIV/02_heterozygosity/02_sfs" \
  "$RESULTS_DIV/02_heterozygosity/04_summary" \
  "$RESULTS_DIV/02_heterozygosity/05_single_heterozygosity_boxplot" \
  "$RESULTS_DIV/02_heterozygosity/05_ancestry_heterozygosity/tables" \
  "$RESULTS_DIV/03_theta_pi" \
  "$RESULTS_DIV/04_roh/per_sample" \
  "$RESULTS_DIV/04_roh/per_chrom" \
  "$RESULTS_DIV/05_aggregated"

echo "==> results_population/ ($RESULTS_POP)"
# NB: the population ATLAS reads carved data/*.json committed in its repo,
# not these dirs directly (Model B). These slots are producer staging for
# the carve step + any server-side operation that reads raw outputs.
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
  "$RESULTS_GEN/04_synteny/oxford" \
  "$RESULTS_GEN/04_synteny/orthologs/pairs" \
  "$RESULTS_GEN/05_conservation"

echo "==> results_cross_species/ ($RESULTS_CS)"
# Producer: catfish-synteny-toolkit / MODULE_SYNTENY_ATLAS. Slots 04-08
# were added 2026-05-29 with their master_config roots (cross_species_te,
# _mashmap, _breakpoint_genes, _phylogeny, _inventory). {focal_genome} /
# {pair} / {anchor} expand at runtime — those subdirs are created by the
# producer, not here.
mkdir -p \
  "$RESULTS_CS/00_manifests" \
  "$RESULTS_CS/01_bp_atlas/passA" \
  "$RESULTS_CS/01_bp_atlas/passB" \
  "$RESULTS_CS/01_bp_atlas/pairs" \
  "$RESULTS_CS/01_bp_atlas/reciprocity" \
  "$RESULTS_CS/02_consolidated/sweep" \
  "$RESULTS_CS/03_gene_order/oxford" \
  "$RESULTS_CS/03_gene_order/geneanchor" \
  "$RESULTS_CS/04_te/breakpoint_te_cross" \
  "$RESULTS_CS/04_te/centromeres" \
  "$RESULTS_CS/05_mashmap/pair" \
  "$RESULTS_CS/06_breakpoint_genes" \
  "$RESULTS_CS/07_phylogeny" \
  "$RESULTS_CS/08_inventory"

echo "==> results_evolution/ ($RESULTS_EVO)"
# Per-candidate JSON producers (one {candidate_id}.json per inversion).
mkdir -p \
  "$RESULTS_EVO/01_age_busco_4d" \
  "$RESULTS_EVO/02_polarisation/synteny_vote" \
  "$RESULTS_EVO/02_polarisation/msa_stacked" \
  "$RESULTS_EVO/03_haplotype_networks" \
  "$RESULTS_EVO/04_archaeology" \
  "$RESULTS_EVO/05_orientation_diversity"

echo "==> results_popstats/ ($RESULTS_PS)"
mkdir -p \
  "$RESULTS_PS/01_groupwise" \
  "$RESULTS_PS/02_ancestry_painting/per_window" \
  "$RESULTS_PS/02_ancestry_painting/per_fish"

echo "==> results_pods/ ($RESULTS_PODS)"
# Server-computed null distributions; the server writes <cache_key>-named
# files into these three slots.
mkdir -p \
  "$RESULTS_PODS/simulations" \
  "$RESULTS_PODS/outlier_calls" \
  "$RESULTS_PODS/calibration"

echo "==> results_loads/ ($RESULTS_LOADS)"
# Flat root — two cohort-level TSVs (load_per_individual.tsv,
# load_per_inversion.tsv). Phase-0 stub; empty until the load pipeline ships.
mkdir -p \
  "$RESULTS_LOADS"

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
# heterozygosity-atlas session outputs (heterozygosity_session root). Lives
# under atlas-cache so in-browser derivations don't pollute the producer tree.
mkdir -p \
  "$CACHE/heterozygosity/sessions"

echo
echo "==> done."
echo "    next:  put your raw outputs into the slots above (move/symlink/mount —"
echo "           your call; see atlas-core/docs/DATA_LAYOUT.md for which files"
echo "           go where), then:"
echo "             bash atlas-core/build/assemble.sh"
echo "             cd ../atlas-workspace && bash start.sh"
