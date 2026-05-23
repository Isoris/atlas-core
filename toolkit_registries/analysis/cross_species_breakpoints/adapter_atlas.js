// analysis/cross_species_breakpoints/adapter_atlas.js
//
// Cross-species comparative breakpoint detection. Two independent method
// families fold into one consolidated catalog with a cross_method flag:
//
//   gene_order : BUSCO single-copy orthologs walked across the phylogeny
//                (synteny18 / synteny5 / genejson). Works the full tree.
//   sequence   : wfmash whole-genome alignment, divergence-tiered identity
//                (p90 Clarias / p85 Cranoglanis / p80 mid / skip deep).
//                BP_ATLAS adds BP3c BOTH-anchor reciprocity validation.
//
// A breakpoint is "cross-method validated" iff TWO INDEPENDENT method
// FAMILIES agree within --tol-kb of each other. wfmash-vs-wfmash on two
// different pairs is recurrent, NOT cross-method.
//
// The actual pipelines live in ./legacy_scripts/ (the user's hand-tuned
// shell + Python + R chain). This adapter is a SUBPROCESS bridge: it
// records the recipe, declares inputs / outputs, and points runners at the
// right wrapper script. It deliberately does NOT reimplement the pipeline
// inside compute.js — that would be a rewrite, and would drift from the
// scripts the user is actively running on LANTA / laptop.

import { compute } from "./compute.js";

export const meta = {
  analysis_id:        "cross_species_breakpoint_detection",
  analysis_version:   "v0",
  atlas_id:           "cross_species_atlas",
  schema_version:     "adapter_atlas_v1",
  label:              "Cross-species breakpoint detection",
  description:        "Comparative breakpoint catalog across 18 catfish species. Two independent method families (gene-order via BUSCO; sequence via wfmash) feed cluster_breakpoints.py with a cross_method flag set only when families agree. BP_ATLAS adds BP3c reciprocity. Headline: LG27 bounded inversion (12.43 Mb + 16.50 Mb both edges cross-method validated); LG23 @ 4.04 Mb cross-method; LG28 @ 15-19 Mb recurrent gene-order-only.",
  input_layer_types:  ["wfmash_paf", "busco_ortholog_table"],
  produces: [
    "breakpoint_clusters",
    "cross_method_validated_breakpoints",
    "recurrent_breakpoints",
    "reciprocity_table",
    "pairwise_summary",
  ],
  engine:             "subprocess",
  schema_in:          "./schema_in.json",
  schema_out:         "./schema_out.json",
  example_input:      "./example_input.json",
  example_output:     "./example_output.json",
  legacy_scripts_dir: "./legacy_scripts",
  default_params: {
    // wfmash sequence alignment (proven Gar-vs-Mac params)
    wfmash_p: 90,
    wfmash_s: 50000,
    // BP_ATLAS two-pass
    pass_a_segment_kb: 100,
    pass_b_segment_kb: 500,
    // STEP_BP2 / STEP_CS01 breakpoint caller
    min_mapq: 1,            // wfmash MAPQ is 1-5, NOT 40 like minimap2
    min_block_bp: 50000,
    cluster_radius_bp: 50000,
    flank_bp: 100000,
    // cluster_breakpoints.py tolerance
    tol_kb: 500,
    edge_merge_kb: 200,
    // divergence tiers (MYA -> wfmash -p threshold)
    divergence_tiers: {
      clariidae: 90,
      cranoglanis: 85,
      siluroidei: 80,
      deep_outgroup: null,  // skip wfmash; gene-order only
    },
  },
  trigger_policy:     "manual",
  status:             "experimental",
  notes:              "The pipeline runs on the comparative cohort (18 genomes + hybrid subgenomes); it produces COORDINATES that the hatchery LG01 x LG28 work consumes, never CLAIMS about hatchery samples.",
};

export async function run(inputs, params, _context) {
  return compute(inputs, params);
}

export function preview(output_layers, _panel_id) {
  // Show the cross-method validated cluster table first; it's the headline.
  const cm = output_layers.cross_method_validated_breakpoints || [];
  if (cm.length) return { kind: "table", rows: cm.slice(0, 20) };
  const cl = output_layers.breakpoint_clusters || [];
  return { kind: "table", rows: cl.slice(0, 20) };
}

export function explain() {
  return [
    "Calls breakpoints from two independent method families and folds them",
    "into one tolerance cluster table. Sequence (wfmash) only aligns inside",
    "Clariidae / Cranoglanis at p90 / p85; gene-order (BUSCO walk) covers the",
    "full catfish phylogeny. cross_method = TRUE only when an INDEPENDENT",
    "family agrees within --tol-kb. BP_ATLAS adds BOTH-anchor reciprocity.",
    "Manuscript-level headline: LG27 bounded inversion (12.43 + 16.50 Mb).",
  ].join(" ");
}
