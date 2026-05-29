# COMPARATIVE CROSS-SPECIES BREAKPOINT — COMPLETE HANDOFF
Date: 2026-05-23 | Author context: Quentin Andres, PhD comp genomics, Kasetsart Univ
Manuscript: MS_Inversions_North_african_catfish (Nature Comms tier)

================================================================================
0. COHORT DISCIPLINE (READ FIRST — never violate)
================================================================================
THREE catfish cohorts, NEVER conflate:
  (1) F1 hybrid (C. gariepinus x C. macrocephalus) — genome ASSEMBLY paper ONLY.
  (2) 226-sample pure C. gariepinus hatchery on LANTA — MS_Inversions; K=broodline.
  (3) Pure C. macrocephalus wild — FUTURE paper.
ALL work in this handoff = COMPARATIVE/ASSEMBLY cohort (18 genomes + hybrid
subgenomes). NOT hatchery. The hatchery haploblock join is a SEPARATE next chat;
this side hands COORDINATES across, never CLAIMS.

================================================================================
1. THE RESEARCH ARC
================================================================================
Goal: find breakpoints -> cross with atlas -> consolidate large inversions ->
study PODs inside -> finish. This chat completed the COMPARATIVE side
(find + consolidate, two methods). POD (hatchery, step 4) + styled supplementary
tables are deferred to later chats.

================================================================================
2. WHAT WE DID THIS SESSION (chronological)
================================================================================
- Built gene-order breakpoint extraction from macrosyntR wide ortholog tables
  (all 18 species), both focal frames (Gar + Mac), tolerance-swept 500kb->1kb.
- Built tolerance-CLUSTER consolidation (not fixed bins) with method-family
  independence: gene_order (synteny18/synteny5/genejson) vs sequence (wfmash).
  cross_method flag = TRUE only when independent families agree <=tol.
- Fixed wfmash table reader (query_chrom/query_pos cols, LG-aware chrom norm,
  NONCOLLINEAR drop). Fixed family labeling so wfmash-vs-wfmash != cross-method.
- Decoded cs_breakpoints_v1.json structure; found the REAL detector
  (STEP_CS01_extract_breakpoints.py) and used it instead of a reverse-engineered
  adapter.
- Established the METHOD/DIVERGENCE SPLIT via the BUSCO timetree:
  wfmash (sequence) only aligns <=~Clariidae at p90; gene-order for full phylogeny.
- Carried the full real BP_ATLAS (STEP_BP1..BP6 + config + SLURM) into the bundle,
  built a cross-species 18-genome manifest, patched STEP_BP1 for per-pair
  divergence-tiered identity, built a laptop-sequential runner.

================================================================================
3. HEADLINE RESULTS (honest, two-tier)
================================================================================
TIER 1 — CROSS-METHOD validated (gene_order AND wfmash sequence agree, survived
         tolerance sweep to kb):
  * LG27 @ 12.43 Mb (span 123 kb) — genejson + wfmash. Inversion edge.
  * LG27 @ 16.50 Mb (span 1 kb)   — genejson + wfmash. STRONGEST result.
    => LG27 is a BOUNDED INVERSION (both edges cross-method corroborated).
       PRIME result + PRIME POD target for the hatchery chat.
  * LG23 @ 4.04 Mb (span 200 kb)  — synteny5 + wfmash.

TIER 2 — recurrent / single-method (real but ONE method):
  * LG28 @ 15-19 Mb — gene-order recurrent (synteny18+synteny5+genejson agree),
    NOT sequence-corroborated at p90. Report as karyotype-level fusion.
    NOTE: CS called LG28 fission/fusion @ 15.58; wfmash interchrom @ 16.78-16.95;
    gene-order 15-18.5. SAME event, ~1Mb spread = resolution diff. Not separate.
  * LG3, LG4 — wfmash cross + within-Cgar (same method, two comparisons) =
    recurrent-rearrangement candidates, NOT cross-method.

GENE-ORDER MULTI-SPECIES CATALOG (stability-validated):
  Gar frame: 16 edges with >=3 species support, STABLE 500kb->1kb (real).
  Mac frame: 27-28 edges with >=3 species support, STABLE.

================================================================================
4. METHODS (for the manuscript methods paragraph)
================================================================================
"Breakpoints between the focal genomes and close relatives (Clariidae) were
corroborated by whole-genome sequence alignment (wfmash, >=90% identity);
across the broader catfish phylogeny, where sequence divergence precludes
whole-genome alignment, breakpoints were detected from single-copy ortholog
gene order (BUSCO)."

Method independence (anti-overclaim): synteny18/synteny5/genejson are ALL
gene-order from the same BUSCO ortholog data = ONE correlated family. wfmash =
sequence = independent. "Many species agree" = recurrent (one method), NOT
multi-method. cross_method requires gene_order AND sequence.

CS vs BP_ATLAS (both detect same breakpoints, different scope):
  CS (STEP_CS01): one PAF, Gar-anchored, conservative core + TE-flank + candidate
    overlap. High precision.
  BP_ATLAS (STEP_BP1..6): all pairs, two-pass (Pass A -s100k sensitive, Pass B
    -s500k backbone check), confidence tiers, BOTH-anchor reciprocity (BP3c).
    High recall + reciprocal validation. They AGREE on LG27 (verified chat bdecd0af).

================================================================================
5. PARAMETERS (proven / locked)
================================================================================
wfmash (Quentin's working Gar-vs-Mac run, from 01_wfmash/wfmash.log):
  -X -p 90 -s 50000  | kmer 19, window 256, block-min 250000, chain-gap-max 100000
  query=Gar target=Mac (wfmash: FIRST arg target, SECOND query)
cs caller (STEP_CS01): --min-mapq 1 --min-block-bp 50000 --cluster-radius-bp 50000
  --flank-bp 100000   (min-mapq 1 because wfmash mapq is 1-5, NOT 40 like minimap2)
BP_ATLAS two-pass: Pass A -s 100000, Pass B -s 500000, both -n 1 -m (approx).
  Original PASS_A/B_MAP_PCT=85; PATCHED to per-pair divergence tier (p90/85/80/skip).
Divergence tiers (from BUSCO timetree, MYA to focal Clarias):
  same-genus Clarias ~15-20My -> p90 ; Cranoglanis ~40My -> p85 ;
  other Siluroidei ~55-65My -> p80 ; Plotosus ~85My, Trichomycterus ~100My -> SKIP.
Tolerance clustering: --tol-kb 500 default; swept 500->1, cross-method count
  STABLE (6->...->2-3) proving real not binning artifact.
Gene-order edge-merge: --edge-merge-kb 200 default; swept, >=3-species count STABLE.
Constants: LG28 prototype 15.115-18.005 Mb; karyotype 60/106/60;
  Fst_Hom1_Hom2=0.308; PAD=3; NPC=6.

================================================================================
6. KEY DATA PATHS (on Quentin's machine; Claude cannot read /mnt/e or /mnt/c)
================================================================================
GENOMES (all 18, named to match ortholog table, NO DOWNLOAD NEEDED):
  /mnt/e/catfish_bundle_no_genomes_no_EDTA/
    catfish_phylogenomics_v1.0/phylogeny/results_tree_busco_catfish/
    -> A_melas.fa C_apus.fa(1.2G) C_bouderius.fa C_fuscus.fa C_gariepinus.fa
       C_macrocephalus.fa fClaHyb_Gar.fa fClaHyb_Mac.fa H_wyckioides.fa
       I_furcatus.fa I_punctatus.fa N_graeffei.fa(2.4G,biggest) P_hypophthalmus.fa
       P_lineatus.fa(1.35G) S_aristotelis.fa S_meridionalis.fa T_fulvidraco.fa
       T_rosablanca.fa T_vachellii.fa
    Also per-species *_single_copybuscos.faa here (headers have NO coords).
HYBRID FOCAL GENOMES (hybrid frame, _LG suffix):
  /mnt/e/01-catfish_assembly_manuscript_CGA/cross_species_breakpoints/00_fastas/
    fClaHyb_Gar_LG.fa (980M) fClaHyb_Mac_LG.fa (910M) + .fai
EXISTING wfmash (Gar-vs-Mac): .../cross_species_breakpoints/01_wfmash/gar_vs_mac.paf
  + wfmash.log
EXISTING cs JSON: .../cross_species_breakpoints/02_breakpoints/cs_breakpoints_v1.json
  (schema v2; 3 called breakpoints + 42 synteny_blocks; LG15/27/28)
wfmash BPATLAS raw (275 breakends): /mnt/e/results_genome/results_bpatlas/
  03_breakpoints/breakpoints_raw.tsv (cols query_chrom query_pos event_class
  [NONCOLLINEAR/INVERSION/INTERCHROM] pair_kind [within_Cgar/cross])
  *** BP_ATLAS ALREADY RAN on the 5-haplotype Cgar/Cmac cohort (Cgar_h1,
      Cmac_h1/h2/h3, Cgar_DE_primary). COMPLETE outputs at results_bpatlas/:
        02_paf_passA/ + 02_paf_passB/   all pair PAFs (two-pass), with .meta.tsv
        03_breakpoints/breakpoints_raw.tsv   (the wfmash source we used)
        03_breakpoints/anchor_Cgar/ + anchor_Cmac/   per-anchor zone tables
        03_breakpoints/reciprocity/   <-- BP3c reciprocity (use this! both-anchor
                                          validated zones for the Clarias pairs)
        05_atlas_data/atlas_data.json + atlas_paf_arcs.json   (figure inputs)
        06_joint/joint_candidates.tsv   (BP6 A-E classification)
      So the within-Cgar/Cmac BP_ATLAS is DONE. The optional cross-species run
      only EXTENDS it to the 18 other species (the days-long laptop grind).
      NEXT CHAT: pull results_bpatlas/03_breakpoints/reciprocity/ for the
      "supported from both directions" evidence tier on LG27 etc.
ORTHOLOG TABLES (from macrosyntR .RData): /mnt/c/Users/quent/Desktop/MS_CGA/
  orthologs_18sp.tsv (983 orth x 18sp), orthologs_5sp.tsv (2003 x 5sp)
  source .RData: /mnt/c/Users/quent/Desktop/MS_CGA/.RData
    objects: my_orthologs_with_18_sp, my_orthologs_with_5_sp, my_orthologs_with_9_sp
    species map: sp11=fClaHyb_Gar, sp8=fClaHyb_Mac, sp10=C_gariepinus, sp3=H_wyckioides
RIdeogram synteny: /mnt/c/Users/quent/Desktop/MS_CGA/macrosyntR_6/*.txt
WORKDIR Quentin ran from: /mnt/c/Users/quent/Desktop/MS_CGA (scripts copied in,
  results/ created locally there)

================================================================================
7. RESULTS PRODUCED THIS SESSION (in Quentin's results/)
================================================================================
results/synteny_18sp_breakpoints.tsv     16 edges >=3sp (18-species gene-order)
  (NOTE: also a typo dup synteny_18sp_breakpoint.tsv [no s] + cluster_breakpoints.py.old
   exist locally from early runs — IGNORE both, use the canonical names.)
results/synteny_5sp_breakpoints.tsv      9 edges >=3sp (denser, 5sp)
results/csbp_json_breakpoints.tsv        3 (LG27 12.52 inv, LG15 3.22 inv, LG28 16.95 ff)
results/breakpoint_clusters.tsv          CONSOLIDATED; cross_method flag; THE headline table
results/consolidated_large_inversions.tsv  POD handoff (coordinates only)
results/pairwise_summary_fClaHyb_Gar.tsv   Gar-vs-each: edge + n_species + species_list
results/pairwise_summary_fClaHyb_Mac.tsv   Mac-vs-each
results/pairwise_long_*.tsv                per (edge x species) detail
results/sweep/summary_*_{500..1}kb.tsv     tolerance sweep (STABILITY proof)
results/evidence_matrix.tsv                (older fixed-bin; SUPERSEDED by clusters)

================================================================================
8. NEXT STEPS
================================================================================
OPTIONAL — BP_ATLAS sequence layer (NEXT CHAT MANAGES THIS; not a blocker):
  STATUS: scripts laptop-safe + manifest VERIFIED (17/17 genome paths resolve).
  This is a CONFIRMATION layer. It reproduces the Clarias breakpoints already
  found (LG27, LG23) with reciprocity + confidence tiers; does NOT change the
  headline. The comparative chapter's data is COMPLETE without it.

  Laptop path (works now; STEP_BP1 conda-activation made conditional/non-fatal):
    cd /mnt/e/COMPARATIVE_BREAKPOINTS_MASTER_<date>/MODULE_BPATLAS_crossspecies/scripts
    bash run_bp_atlas_LAPTOP.sh
    -> legacy all-vs-all (~240 pairs, DAYS sequential, watchable, resumable) with
       per-pair divergence-tiered -p (p90 Clarias / p85 Cranoglanis / p80 mid /
       skip deep). Stops at zones + BP3c reciprocity (BP4 pop-overlap and BP5
       figures intentionally NOT run here).
    CAUTIONS: (1) N_graeffei 2.4GB may OOM a 4GB laptop — resume skips done pairs,
      so let the rest finish and do N_graeffei separately/on LANTA. (2) mid-tier
      pairs (p80, ~60My) will be SPARSE — BP3 tiers them low-confidence correctly.
    FASTER ALTERNATIVE: focal-only (~30 pairs) — gate STEP_BP1 build_pairs to
      Gar/Mac-as-query only. Loses nothing for a Clarias-focused manuscript.

  LANTA path (if moved to cluster): edit manifest fasta_path -> /project/... paths;
    sbatch SLURM_run_bp_atlas_PARALLEL.sh (80cpu/200GB, two-pass parallel).

  AFTER the run: per-PAF STEP_CS01_extract_breakpoints.py -> csbp_dir_to_breakpoints.py
    folds all JSONs into one table -> add as --source to cluster_breakpoints.py ->
    re-cluster. The reciprocity_table.tsv (BP3c) is the "supported from both
    directions" evidence tier for the manuscript.

  VERIFY PATHS before any run (catches silent pair-1 failure):
    cut -f5 haplotype_manifest_CROSSSPECIES.tsv | tail -n +2 | \
      while read f; do [ -f "$f" ] && echo "OK $f" || echo "MISSING $f"; done
    (Confirmed 17/17 OK on 2026-05-23.)

NEXT CHAT A (hatchery haploblock bounding):
  Intersect Gar-frame breakpoint catalog (breakpoint_clusters.tsv +
  pairwise_summary_fClaHyb_Gar.tsv) with 226-cohort haploblocks. COORDINATES
  ONLY, cohort boundary strict. Scaffold ready: SYNTENY_INVERSION_JOIN/.
  BP_ATLAS STEP_BP4_overlap_population.py is the population-overlap tool for this.

NEXT CHAT B (styled supplementary tables + figures):
  Build S-series docx (landscape, method-column shading, anti-overclaim captions)
  from breakpoint_clusters.tsv + pairwise summaries. Two-tier framing (Tier1
  cross-method vs Tier2 recurrent). BP_ATLAS STEP_BP5* R scripts = atlas figures
  (ribbons, dotplots, montages). docx skill: /mnt/skills/public/docx/SKILL.md.

================================================================================
9. THINGS FOUND BY SEARCHING OTHER CHATS (provenance)
================================================================================
- wfmash exact params: chat "Catfish chromosome cross-species analysis" (1b4d8e12)
  + the wfmash.log paste this session.
- cs_breakpoints 0-breakpoints diagnosis (mapq>=40 too strict for wfmash mapq 1-5):
  chat 1b4d8e12.
- CS vs BP_ATLAS "found the same breakpoints, different scope": chat
  "Debugging MODULE_BPATLAS script errors" (bdecd0af) — LG27 12.4 & 16.5 match.
- catfish-synteny-toolkit design (wfmash over MCScanX, collect-then-refine,
  four tiers, T.rosablanca protein-anchor-only): chat 81aa35e4.
- BUSCO timetree (100->0 MYA, divergence tiers): uploaded image this session.

================================================================================
10. NAMING CONVENTIONS (locked)
================================================================================
HWE_FIS ; arrangement_FST_like / FAT_arrangement ; POD_candidate_variant ;
"POD-compatible" (NEVER "POD found"). GitHub: Isoris;
github.com/Isoris/inversion-popgen-toolkit. GitHub Desktop only (no git CLI).
