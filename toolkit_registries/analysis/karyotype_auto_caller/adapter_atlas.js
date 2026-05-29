// analysis/karyotype_auto_caller/adapter_atlas.js

import { compute } from "./compute.js";

export const meta = {
  analysis_id:        "karyotype_auto_caller",
  analysis_version:   "v0",
  atlas_id:           "inversion_atlas",
  schema_version:     "adapter_atlas_v1",
  label:              "Karyotype auto caller",
  description:        "Calls per-sample karyotype (0/1/2) for each candidate from dosage + window-band signals + the candidate_registry. v0 uses fixed dosage_breaks + a (chain_score, band_fraction) confidence policy; a real production caller will replace bucket() with model-based clustering.",
  input_layer_types:  ["candidate_registry", "chain_evidence", "dosage_summary", "window_band_calls"],
  produces:           ["unpolarized_karyotype_calls"],
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
  const rows = (output_layers && output_layers.unpolarized_karyotype_calls) || [];
  return { kind: "table", rows: rows.slice(0, 12) };
}

export function explain() {
  return "Classifies each (sample, candidate) into karyotype 0 / 1 / 2 from dosage + chain_evidence + window_band_calls. The 0/1/2 axis is unpolarized — direction (reference vs derived) is assigned downstream by karyotype_polarizer. Confidence policy: high when both chain_score ≥ 0.80 and band_fraction ≥ 0.80; medium above the configured floors; samples below the floors are emitted as NA.";
}
