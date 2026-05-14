// analysis/iv_candidate_promoter/adapter_atlas.js
//
// Atlas/APLR-aware bridge for the iv_candidate_promoter analysis.
// Per ADAPTER_CONTRACT.md §2.

import { compute } from "./compute.js";

export const meta = {
  // identity
  analysis_id:        "iv_candidate_promoter",
  analysis_version:   "v1",
  atlas_id:           "inversion_atlas",
  schema_version:     "adapter_atlas_v1",

  // human-facing
  label:              "Inversion candidate promoter",
  description:        "Promotes window-band signals into candidate intervals with chain evidence. Inputs: window_band_calls, l3_contingency, dosage_summary. Outputs: candidate_registry, chain_evidence.",

  // contract
  input_layer_types:  ["window_band_calls", "l3_contingency", "dosage_summary"],
  produces:           ["candidate_registry", "chain_evidence"],

  // runtime
  engine:             "atlas_js",
  schema_in:          "./schema_in.json",
  schema_out:         "./schema_out.json",
  example_input:      "./example_input.json",
  example_output:     "./example_output.json",
  trigger_policy:     "manual",
  status:             "active",
};

export async function run(inputs, params, _context) {
  // No registry imports — the librarian already resolved the inputs.
  return compute(inputs, params);
}

export function preview(output_layers, panel_id) {
  // Tiny default preview: the first 5 rows of the produced candidate_registry
  // as a JSON list.  Pages with a richer renderer will override.
  if (panel_id === "candidate_overview_panel" || panel_id === "candidate_review_panel") {
    const rows = (output_layers.candidate_registry || []).slice(0, 5);
    return { kind: "table", rows };
  }
  return null;
}

export function explain() {
  return "Merges window-band hits into candidate intervals; cross-checks with L3 and dosage layers to assign a confidence class. Output is the canonical candidate_registry that downstream karyotype-calling consumes.";
}
