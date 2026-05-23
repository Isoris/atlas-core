# CS pipeline vs BP_ATLAS — why they complement (for the next chat)

Both detect the SAME cross-species breakpoints by the SAME core idea (walk
wfmash PAF blocks on the query chrom, flag target-change or strand-flip).
They differ in SCOPE, SENSITIVITY, and AGGREGATION — deliberately.

## CS pipeline (STEP_CS01_extract_breakpoints.py) — CONSERVATIVE CORE
- Runs on ONE PAF (Cgar query vs Cmac target).
- One-directional (Gar-anchored only).
- min-block 50kb; linear block walk; cluster within 50kb.
- Emits the cleanest macro-events + TE-density flanking annotation
  (Spalax-style repeat-mechanism argument) + 226-cohort candidate overlap hook.
- Output: cs_breakpoints_v1.json (3 events: LG27@12.52 inv, LG27@16.50 inv,
  LG28@15.58 fission/fusion).
- ROLE: high-precision headline; the TE-mechanism + candidate-overlap angles.

## BP_ATLAS (STEP_BP1..BP6) — COMPREHENSIVE, POPULATION-AWARE, RECIPROCAL
- Runs on ALL pairs (built for multi-haplotype Cgar/Cmac; here adapted to
  cross-species focal+tiered).
- TWO-PASS wfmash: Pass A (-s 100k, sensitive ~100kb inversions) +
  Pass B (-s 500k, backbone check to reject repeat-driven false zones).
- BP2 detection more permissive: separates INVERSION / INTERCHROM /
  INVERTED_TRANSLOC / NONCOLLINEAR.
- BP3 clusters across pairs into zones with CONFIDENCE TIERS (high/med/low).
- BP3c RECIPROCITY: anchors BOTH Cgar and Cmac; a zone is strongest when the
  same event appears from both reference frames ("supported from both
  directions"). CS cannot do this (one-directional).
- BP4 population overlap (226 hatchery cohort) -> NEXT CHAT (cohort boundary).
- BP5 ribbons/dotplots/montages (figures) -> FIGURE CHAT.
- BP6 joint A-E classification (manuscript table).
- ROLE: full atlas with provenance; recall + reciprocal validation + tiers.

## How they agree (verified in chat bdecd0af)
  CS cs_bp_0001 (LG27 12.52) == BP_ATLAS BP_zone_000013 (LG27 12.40) high conf
  CS cs_bp_0002 (LG27 16.50) == BP_ATLAS BP_zone_000015 (LG27 16.50)
  CS LG28 fission/fusion 15.58 ~ this session's LG28 cluster 16.78-16.95
    (SAME event, ~1Mb spread = resolution diff between sparse gene-order and wfmash)

## This session's cross-method result (gene-order + wfmash sequence)
  Cross-method validated (independent families agree <=500kb):
    LG27 @ 12.4 Mb, LG27 @ 16.5 Mb (bounded inversion, both edges), LG23 @ 4.0 Mb
  LG28: gene-order recurrent across species; not sequence-corroborated at p90.

## Method/divergence split (locked by the BUSCO timetree)
  wfmash sequence: only works <=~Clariidae (p90). Mid-Siluriformes marginal at p80.
  Deep outgroups (P_lineatus ~85My, T_rosablanca ~100My): gene-order ONLY.
  -> cross-species manifest marks the two deep species tier-C (target-only).

## COHORT DISCIPLINE (unchanged)
  Comparative cohort here (18 genomes). Hatchery 226-cohort join is BP4 and a
  SEPARATE chat. Coordinates hand across, never claims.

## LAPTOP vs LANTA (run paths)
- LAPTOP: run_bp_atlas_LAPTOP.sh -> STEP_BP1 (conda activation made conditional/
  non-fatal) -> BP2 -> BP3 (both anchors) -> BP3c reciprocity. Sequential, one
  pair at a time, resumable. STOPS at zones+reciprocity. This is the laptop path.
- LANTA: SLURM_run_bp_atlas_PARALLEL.sh + #SBATCH headers (kept for reference).
  Edit manifest fasta_path to /project/... LANTA paths if running there.
- STEP_BP1b miniprot PROTEOME still points at /scratch/... — only relevant if the
  miniprot stage is enabled (laptop runner does NOT call it).
