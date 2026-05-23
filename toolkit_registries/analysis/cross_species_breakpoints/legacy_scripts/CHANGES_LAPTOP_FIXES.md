# BP_ATLAS LAPTOP FIXES — 2026-05-23
Context: make the cross-species BP_ATLAS run correctly + safely on a 5GB-RAM,
2-3 CPU laptop. All changes are in MODULE_BPATLAS_crossspecies/scripts/.
Cohort boundary unchanged: COMPARATIVE/ASSEMBLY only — coordinates, never
hatchery claims.

================================================================================
CRITICAL CORRECTNESS BUG (would have silently wasted the entire run)
================================================================================
STEP_BP2_call_breakpoints.py defaulted to --min-mapq 5, and the laptop runner
did not override it. STEP_BP1 feeds wfmash --approx-mapping PAFs whose MAPQ is
1-5 (NOT 40 like minimap2). With the default of 5, BP2 filtered out ~every
block -> 0 breakpoints, with NO error. This is the same failure diagnosed in
chat 1b4d8e12 for the cs caller.

PROVEN with a synthetic low-MAPQ PAF carrying an obvious inversion:
  --min-mapq 5  -> 0 events   (bug)
  --min-mapq 1  -> all inversion breakpoints recovered   (fix)

Fixes:
  - run_bp_atlas_LAPTOP.sh: BP2 call now passes --min-mapq 1 explicitly.
  - STEP_BP2_call_breakpoints.py: default --min-mapq changed 5 -> 1; help text
    and docstrings corrected from "minimap2" to "wfmash" (the actual aligner).

================================================================================
RAM SAFETY (5GB ceiling)
================================================================================
Key fact: wfmash peak RAM is driven by the TARGET genome it indexes, NOT by
thread count. So lowering CPUs barely helps memory; excluding big targets does.

  - CPUS default 4 -> 2 (leaves a core for the OS; minimal RAM effect).
  - NEW SKIP_TARGETS gate (the real RAM lever). Drops pairs whose TARGET genome
    is too big to index under 5GB. Default: Ngra (2.4GB), Plin (1.35GB),
    Capus (1.2GB). Run those targets on LANTA (SLURM path). They are a
    confirmation tier only — excluding them does NOT change the LG27/LG23
    headline.
  - SKIP_QUERIES kept but default emptied: in focal-only mode it does not lower
    RAM (the query is always Cgar/Cmac), so the old Ngra-as-query default was
    a no-op for memory. The genuine guard is now SKIP_TARGETS.

================================================================================
LAPTOP THROUGHPUT
================================================================================
  - NEW FOCAL_ONLY gate (default 1): keep only pairs whose QUERY is Cgar/Cmac
    (~30 pairs instead of ~240). The handoff's "FASTER ALTERNATIVE"; hours not
    days; loses nothing for a Clarias-focused manuscript. Set FOCAL_ONLY=0 for
    the full all-vs-all grind.
  - Pair subsetting rewrites pairs.tsv in place (full list stashed as
    pairs.full.tsv); pair_idx values stay aligned with STEP_BP1's array lookup.

================================================================================
RESUME FIX
================================================================================
Deep-outgroup pairs write EMPTY PAFs by design (wfmash cannot align them). The
old resume test `[[ -s A && -s B ]]` (non-empty) treated those as "not done"
and re-ran them every resume. Now a pair also counts as done when its
.meta.tsv sidecar records a skip (n_records_A == 0 && n_records_B == 0).
VERIFIED: on re-run all pairs skip, deep-outgroup pairs report
"deep-outgroup skip (already recorded)".

================================================================================
PASS B BACKBONE WIRED IN
================================================================================
run_bp_atlas_LAPTOP.sh now passes --passB-paf-dir to STEP_BP3, so each zone
gets a real backbone_support flag (yes/partial/no) instead of always "n/a".
This activates the two-pass repeat-artifact guard the design exists for.
VERIFIED: backbone_support column populates (e.g. "yes").

================================================================================
CLEANUP
================================================================================
  - STEP_BP1_pairwise_wfmash.sh: removed a dead no-op `case " $a $b "` block in
    pair_identity (the same-genus p90 case is already handled by the max-tier
    logic). Tier selection unit-tested for all genus/family/deep cases.

================================================================================
NEW: POST-RUN FOLD CHAINER
================================================================================
run_fold_into_clusters_LAPTOP.sh — run AFTER run_bp_atlas_LAPTOP.sh. Chains
handoff section 8 in one command:
  per-PAF STEP_CS01 (skips empty deep PAFs, --min-mapq 1)
    -> csbp_dir_to_breakpoints.py (fold all cs JSONs)
    -> cluster_breakpoints.py --source bpatlas_seq:...:wfmash --split-wfmash
Pass extra prior --source args through to merge with the gene-order catalog.

================================================================================
HOW TO RUN (laptop)
================================================================================
1. Edit MANIFEST paths (haplotype_manifest_CROSSSPECIES.tsv) to local genomes.
2. Verify paths (catches silent pair-1 failure):
     cut -f5 haplotype_manifest_CROSSSPECIES.tsv | tail -n +2 | \
       while read f; do [ -f "$f" ] && echo "OK $f" || echo "MISSING $f"; done
3. cd MODULE_BPATLAS_crossspecies/scripts
4. bash run_bp_atlas_LAPTOP.sh          # focal-only, 2 CPU, big targets -> LANTA
   (override e.g.: CPUS=3 SKIP_TARGETS="" FOCAL_ONLY=0 bash run_bp_atlas_LAPTOP.sh)
5. After it finishes:
     bash run_fold_into_clusters_LAPTOP.sh
6. Headline evidence:
     results_bpatlas/03_breakpoints/reciprocity/reciprocity_table.tsv

================================================================================
KNOWN GAPS (not blockers for the laptop path)
================================================================================
  - SLURM_run_bp_atlas_PARALLEL.sh references run_bp_atlas.sh, which is NOT in
    this bundle. The LAPTOP runner is self-contained and does not need it; only
    the cluster (SLURM) Stage-2/3 path would break. Stub or supply that script
    before using the SLURM driver.
  - csbp_dir_to_breakpoints.py was not validated against the real STEP_CS01
    JSON on /mnt/e (unreadable here). The handoff records STEP_CS01 as
    verified against cs_breakpoints_v1.json; if the fold emits 0 rows, check
    that STEP_CS01's JSON keys (gar_chr / gar_pos_mb / event_type_refined)
    match what csbp_dir_to_breakpoints.py reads.

Tested this session: full chain BP1 -> BP2 -> BP3 (both anchors) -> BP3c on a
synthetic 4-genome cohort with a stubbed wfmash emitting realistic MAPQ 1-5
approx PAFs. All stages pass; min-mapq fix, skip/resume, SKIP_TARGETS, and
Pass B backbone all verified.
