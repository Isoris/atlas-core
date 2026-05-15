// analysis/inversion_pair_incompatibility/adapter_atlas.js
//
// Manuscript stress-test target: scoring joint karyotype distortion for
// a pair of inversions on different chromosomes (the LG01 × LG28 case).

import { compute } from "./compute.js";

export const meta = {
  analysis_id:        "inversion_pair_incompatibility",
  analysis_version:   "v0",
  atlas_id:           "inversion_atlas",
  schema_version:     "adapter_atlas_v1",
  label:              "Inversion pair incompatibility test",
  description:        "Scores observed-vs-expected joint karyotype counts for a pair of inversions on different chromosomes (the manuscript LG01 × LG28 target). Emits distortion_summary + pair_meta (chi-square, df, cells_below_min).",
  input_layer_types:  ["inversion_candidates", "karyotype_calls"],
  produces:           ["distortion_summary"],
  engine:             "atlas_js",
  schema_in:          "./schema_in.json",
  schema_out:         "./schema_out.json",
  example_input:      "./example_input.json",
  example_output:     "./example_output.json",
  trigger_policy:     "manual",
  status:             "experimental",
};

export async function run(inputs, params, _context) {
  return compute(inputs, params);
}

export function preview(output_layers, panel_id) {
  // For a panel rendering distortion_summary, show the 3×3 cell table.
  const rows = output_layers.distortion_summary || [];
  return { kind: "table", rows: rows.slice(0, 9) };
}

export function explain() {
  return "Scores joint karyotype distortion for a pair of inversions on different chromosomes. Output feeds the inversion_pair_incompatibility_LG01_LG28 question; expected counts assume independent transmission, chi-square is over the 3×3 karyotype joint table.";
}
