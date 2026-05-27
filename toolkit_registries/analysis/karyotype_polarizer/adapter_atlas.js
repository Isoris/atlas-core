// analysis/karyotype_polarizer/adapter_atlas.js

import { compute } from "./compute.js";

export const meta = {
  analysis_id:        "karyotype_polarizer",
  analysis_version:   "v0",
  atlas_id:           "inversion_atlas",
  schema_version:     "adapter_atlas_v1",
  label:              "Karyotype polarizer",
  description:        "Polarises unpolarized_karyotype_calls so 0/1/2 carries direction (0 = reference-like, 2 = derived/inverted-like). Decision tree: reference_match (ref_dosage) / outgroup_vote / majority_allele / force_unchanged. Heterozygotes (class 1) are symmetric and never flip; NA propagates.",
  input_layer_types:  ["unpolarized_karyotype_calls", "reference_genome_layer"],
  produces:           ["polarized_karyotype_calls"],
  engine:             "atlas_js",
  schema_in:          "./schema_in.json",
  schema_out:         "./schema_out.json",
  example_input:      "./example_input.json",
  example_output:     "./example_output.json",
  trigger_policy:     "manual",
  status:             "experimental",
};

export async function run(inputs, params, _ctx) {
  return compute(inputs, params);
}

export function preview(output_layers, _panel_id) {
  const rows = (output_layers && output_layers.polarized_karyotype_calls) || [];
  return { kind: "table", rows: rows.slice(0, 12) };
}

export function explain() {
  return "Assigns direction to unpolarized_karyotype_calls using a polarity_source ∈ {reference_match, outgroup_vote, majority_allele, force_unchanged}. A 'flip' swaps 0 ↔ 2 across all calls for a given candidate; class 1 (heterozygote) is symmetric. Output polarized_karyotype_calls is the canonical karyotype layer for downstream mendelian + popstats + inversion_pair_incompatibility.";
}
