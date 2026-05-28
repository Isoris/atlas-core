// analysis/cross_species_breakpoint_detection/compute.js
//
// SUBPROCESS bridge — the real work lives in ./legacy_scripts/.
//
// The contract: compute() returns a recipe that an external runner picks up
// and executes. We do NOT spawn here (the registry must stay pure
// JSON-in/out; runners live above).
//
// Input shape (also pinned in schema_in.json):
//   {
//     sources: [                          // one per method × pair / table
//       { name, family, path },           // family ∈ {gene_order, sequence}
//       ...
//     ],
//     params: { wfmash_p, wfmash_s, min_mapq, min_block_bp,
//               cluster_radius_bp, flank_bp, tol_kb, edge_merge_kb,
//               divergence_tiers, pass_a_segment_kb, pass_b_segment_kb }
//   }
//
// Output shape (pinned in schema_out.json):
//   {
//     breakpoint_clusters:                  [...],   // headline table
//     cross_method_validated_breakpoints:   [...],   // tier 1
//     recurrent_breakpoints:                [...],   // tier 2
//     reciprocity_table:                    [...],   // BP3c
//     pairwise_summary:                     [...],   // pair × edge
//     recipe: {                             // subprocess plan
//       gene_order_steps: [ { script, args }, ... ],
//       sequence_steps:   [ { script, args }, ... ],
//       fold_step:        { script, args },
//       reciprocity_step: { script, args }
//     }
//   }

export function compute(inputs, params = {}) {
  const p = {
    wfmash_p:           90,
    wfmash_s:           50000,
    pass_a_segment_kb:  100,
    pass_b_segment_kb:  500,
    min_mapq:           1,
    min_block_bp:       50000,
    cluster_radius_bp:  50000,
    flank_bp:           100000,
    tol_kb:             500,
    edge_merge_kb:      200,
    ...params,
  };

  const sources = (inputs && inputs.sources) || [];
  const geneOrderSources = sources.filter(s => s.family === "gene_order");
  const sequenceSources  = sources.filter(s => s.family === "sequence");

  const gene_order_steps = [];
  for (const s of geneOrderSources) {
    if (s.kind === "wide_orthologs") {
      gene_order_steps.push({
        script: "legacy_scripts/gene_order/wide_orthologs_to_breakpoints.py",
        args: ["--in", s.path, "--out", `out/synteny_${s.name}_breakpoints.tsv`,
               "--edge-merge-kb", String(p.edge_merge_kb)],
      });
    } else if (s.kind === "csbp_json_dir") {
      gene_order_steps.push({
        script: "legacy_scripts/gene_order/csbp_dir_to_breakpoints.py",
        args: ["--dir", s.path, "--out", `out/csbp_${s.name}.tsv`],
      });
    } else if (s.kind === "rideogram") {
      gene_order_steps.push({
        script: "legacy_scripts/gene_order/rideogram_to_breakpoints.py",
        args: ["--in", s.path, "--out", `out/rideogram_${s.name}.tsv`],
      });
    }
  }

  const sequence_steps = [];
  for (const s of sequenceSources) {
    if (s.kind === "paf") {
      sequence_steps.push({
        script: "legacy_scripts/gene_order/STEP_CS01_extract_breakpoints.py",
        args: ["--paf", s.path, "--out", `out/cs_${s.name}.json`,
               "--min-mapq", String(p.min_mapq),
               "--min-block-bp", String(p.min_block_bp),
               "--cluster-radius-bp", String(p.cluster_radius_bp),
               "--flank-bp", String(p.flank_bp)],
      });
    } else if (s.kind === "bp_atlas_manifest") {
      sequence_steps.push({
        script: "legacy_scripts/bp_atlas/run_bp_atlas_LAPTOP.sh",
        args: [s.path],
        env: {
          PASS_A_SEGMENT: String(p.pass_a_segment_kb * 1000),
          PASS_B_SEGMENT: String(p.pass_b_segment_kb * 1000),
          MIN_MAPQ:       String(p.min_mapq),
        },
      });
    }
  }

  const reciprocity_step = {
    script: "legacy_scripts/bp_atlas/STEP_BP3c_reciprocity.py",
    args: ["--anchor-a", "out/anchor_Cgar", "--anchor-b", "out/anchor_Cmac",
           "--out", "out/reciprocity_table.tsv",
           "--cluster-radius-bp", String(p.cluster_radius_bp)],
  };

  const fold_args = ["--tol-kb", String(p.tol_kb),
                     "--out", "out/breakpoint_clusters.tsv"];
  for (const s of sources) {
    const tsv = s.family === "sequence" && s.kind !== "paf"
              ? `out/${s.name}_breakpoints.tsv`
              : s.family === "gene_order"
                ? `out/${s.name === "synteny18" || s.name === "synteny5"
                       ? `synteny_${s.name}_breakpoints` : s.name}.tsv`
                : `out/cs_${s.name}.tsv`;
    fold_args.push("--source", `${s.name}:${tsv}:${s.family}`);
  }
  const fold_step = {
    script: "legacy_scripts/gene_order/cluster_breakpoints.py",
    args: fold_args,
  };

  return {
    breakpoint_clusters:                [],
    cross_method_validated_breakpoints: [],
    recurrent_breakpoints:              [],
    reciprocity_table:                  [],
    pairwise_summary:                   [],
    recipe: {
      gene_order_steps,
      sequence_steps,
      reciprocity_step,
      fold_step,
    },
  };
}
