// analysis/karyotype_polarizer/adapter_atlas.js
// STUB ADAPTER — meta only.

export const meta = {
  analysis_id:        "karyotype_polarizer",
  analysis_version:   "v0",
  atlas_id:           "inversion_atlas",
  schema_version:     "adapter_atlas_v1",
  label:              "Karyotype polarizer",
  description:        "Polarises unpolarized_karyotype_calls against a reference / ancestral comparison so 0/1/2 carries direction.",
  input_layer_types:  ["unpolarized_karyotype_calls", "reference_genome_layer"],
  produces:           ["polarized_karyotype_calls"],
  engine:             "atlas_js",
  schema_in:          "./schema_in.json",
  schema_out:         "./schema_out.json",
  example_input:      "./example_input.json",
  example_output:     "./example_output.json",
  trigger_policy:     "manual",
  status:             "stub",
};

export async function run(_inputs, _params, _ctx) {
  throw new Error("karyotype_polarizer: stub adapter; real compute lands later");
}

export function explain() {
  return "Uses a reference genome / ancestral signal to assign direction to unpolarized_karyotype_calls. Output polarized_karyotype_calls is the canonical karyotype layer for downstream mendelian + popstats analyses.";
}
