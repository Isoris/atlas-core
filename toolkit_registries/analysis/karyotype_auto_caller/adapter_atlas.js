// analysis/karyotype_auto_caller/adapter_atlas.js
// STUB ADAPTER — meta only; compute is a placeholder until the real
// classifier lands. The registry entry exists so APLR can plan around it.

export const meta = {
  analysis_id:        "karyotype_auto_caller",
  analysis_version:   "v0",
  atlas_id:           "inversion_atlas",
  schema_version:     "adapter_atlas_v1",
  label:              "Karyotype auto caller",
  description:        "Calls per-sample karyotype (0/1/2) for each candidate from dosage + window-band signals + the candidate_registry.",
  input_layer_types:  ["candidate_registry", "chain_evidence", "dosage_summary", "window_band_calls"],
  produces:           ["unpolarized_karyotype_calls"],
  engine:             "atlas_js",
  schema_in:          "./schema_in.json",
  schema_out:         "./schema_out.json",
  example_input:      "./example_input.json",
  example_output:     "./example_output.json",
  trigger_policy:     "manual",
  status:             "stub",
};

export async function run(_inputs, _params, _ctx) {
  throw new Error("karyotype_auto_caller: stub adapter; real compute lands later");
}

export function explain() {
  return "Classifies each (sample, candidate) into karyotype 0 / 1 / 2 from dosage + chain evidence. Output feeds karyotype_polarizer and the karyotype_panel.";
}
