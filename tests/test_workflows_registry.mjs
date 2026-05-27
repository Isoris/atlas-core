// tests/test_workflows_registry.mjs
// Smoke tests for core/workflows_registry.js.
// Run: node tests/test_workflows_registry.mjs
//
// No global workflows.registry.json exists in atlas-core itself — workflows
// live per-atlas. These tests use a synthetic in-memory registry that
// mirrors the SPEC_workflows_v1 §3 worked example (BP_ATLAS) so the
// validator + lookup helpers can be exercised offline.

import {
  loadWorkflowsRegistry,
  validateWorkflowsRegistry,
  getWorkflow,
  listWorkflows,
  getWorkflowsByConsumes,
  getWorkflowsByProduces,
  getStatusForWorkflow,
  isWorkflowOutputStale,
} from '../core/workflows_registry.js';

let _pass = 0, _fail = 0;
function ok(cond, msg) {
  if (cond) { _pass++; console.log(`  ✓ ${msg}`); }
  else { _fail++; console.error(`  ✗ ${msg}`); }
}
function eq(a, b, msg) {
  const same = JSON.stringify(a) === JSON.stringify(b);
  if (same) { _pass++; console.log(`  ✓ ${msg}`); }
  else { _fail++; console.error(`  ✗ ${msg}\n    expected: ${JSON.stringify(b)}\n    got:      ${JSON.stringify(a)}`); }
}

// ---------------------------------------------------------------------
// Synthetic registry — mirrors SPEC §3 BP_ATLAS worked example + a
// second small workflow to test multi-workflow cases.
// ---------------------------------------------------------------------
const synthetic = {
  atlas_id: 'cross-species',
  version:  '1.0',
  workflows: [
    {
      workflow_id: 'bp_atlas_pipeline',
      label: 'BP_ATLAS — cross-species breakpoints',
      version: '1.0',
      knob_schema_ref: 'engines/producers/bp_atlas/config/knobs.schema.json',
      default_knob_hash: 'a3b7c9d2',
      cohort_id: 'f1_hybrid_cga_cma',
      reference_id: 'fClaHyb_Gar_LG',
      stages: [
        { stage_id: 'BP1', script: 'engines/producers/bp_atlas/scripts/STEP_BP1_pairwise_wfmash.sh',
          produces: ['bp_atlas_passA_paf_v1', 'bp_atlas_passB_paf_v1'],
          consumes: ['haplotype_manifest_v1'],
          estimated_runtime_min: 4320, estimated_ram_gb: 5 },
        { stage_id: 'BP2', script: 'engines/producers/bp_atlas/scripts/STEP_BP2_call_breakpoints.py',
          produces: ['bp_atlas_events_v1'],
          consumes: ['bp_atlas_passA_paf_v1'],
          estimated_runtime_min: 30 },
        { stage_id: 'BP3', script: 'engines/producers/bp_atlas/scripts/STEP_BP3_cluster_zones.py',
          produces: ['bp_atlas_zones_v1'],
          consumes: ['bp_atlas_events_v1', 'bp_atlas_passB_paf_v1'],
          estimated_runtime_min: 10 },
        { stage_id: 'BP3c', script: 'engines/producers/bp_atlas/scripts/STEP_BP3c_reciprocity.py',
          produces: ['bp_atlas_reciprocity_v1'],
          consumes: ['bp_atlas_zones_v1'],
          estimated_runtime_min: 5 },
        { stage_id: 'BP5', script: 'engines/producers/bp_atlas/scripts/STEP_BP5_prep_atlas_data.py',
          produces: ['bp_atlas_arcs_v1', 'atlas_data_v1'],
          consumes: ['bp_atlas_zones_v1'],
          estimated_runtime_min: 5 },
        { stage_id: 'BP6', script: 'engines/producers/bp_atlas/scripts/STEP_BP6_joint_classify.py',
          produces: ['joint_candidates_v1'],
          consumes: ['bp_atlas_zones_v1', 'bp_atlas_reciprocity_v1'],
          estimated_runtime_min: 5 },
      ],
      runners: [
        { runner_id: 'laptop', script: 'engines/producers/bp_atlas/runners/run_bp_atlas_LAPTOP.sh',
          preset: 'focal_only_2cpu_skiplargetargets' },
        { runner_id: 'slurm', script: 'engines/producers/bp_atlas/runners/SLURM_run_bp_atlas_PARALLEL.sh',
          preset: 'all_pairs_80cpu_200gb' },
      ],
      post_run_chain: [
        { step: 'fold_into_clusters',
          script: 'engines/producers/bp_atlas/runners/run_fold_into_clusters_LAPTOP.sh' },
      ],
      outputs_root: 'data/breakpoints/results_bpatlas/',
      status_file:  'data/breakpoints/results_bpatlas/_status.json',
    },
    {
      workflow_id: 'gene_order_consolidation',
      label: 'Gene-order synteny consolidation (18 species)',
      cohort_id: 'cross_species_18sp_compendium',
      stages: [
        { stage_id: 'GO1', script: 'engines/producers/gene_order/STEP_collect_orthologs.py',
          produces: ['synteny_18sp_v1'] },
      ],
      runners: [
        { runner_id: 'laptop', script: 'engines/producers/gene_order/run_LAPTOP.sh' },
      ],
      outputs_root: 'data/gene_order/',
      status_file:  'data/gene_order/_status.json',
    },
  ],
};

// Cross-validation inputs.
const cohortsRegistry = {
  cohorts: [
    { cohort_id: 'f1_hybrid_cga_cma' },
    { cohort_id: 'cross_species_18sp_compendium' },
    { cohort_id: 'cgar_hatchery_226' },
  ],
};
const layersIndex = {
  layers: [
    'haplotype_manifest_v1', 'bp_atlas_passA_paf_v1', 'bp_atlas_passB_paf_v1',
    'bp_atlas_events_v1', 'bp_atlas_zones_v1', 'bp_atlas_reciprocity_v1',
    'bp_atlas_arcs_v1', 'atlas_data_v1', 'joint_candidates_v1', 'synteny_18sp_v1',
  ].map(layer_id => ({ layer_id })),
};
const atlasesIndex = { atlases: ['cross-species', 'genome', 'inversion', 'diversity'] };

// ---------------------------------------------------------------------
console.log('\n=== validate (clean registry) ===');
const errs = validateWorkflowsRegistry(synthetic, { cohortsRegistry, layersIndex, atlasesIndex });
eq(errs, [], 'clean validation returns no errors');

// ---------------------------------------------------------------------
// Per-rule break tests. The validator `continue`s after a bad
// workflow_id slug (so it can index the remaining workflows safely),
// which means a single registry can't exercise every rule at once.
// Each break is in its own clone so the targeted rule definitely fires.
// ---------------------------------------------------------------------
function breakOne(mutator) {
  const r = JSON.parse(JSON.stringify(synthetic));
  mutator(r);
  return validateWorkflowsRegistry(r, { cohortsRegistry, layersIndex, atlasesIndex });
}

console.log('\n=== validate — per-rule break tests ===');
const e_slug = breakOne(r => { r.workflows[0].workflow_id = 'BAD-ID'; });
ok(e_slug.some(e => e.includes('BAD-ID')), 'flags bad workflow_id slug');

const e_dup = breakOne(r => { r.workflows[1].workflow_id = r.workflows[0].workflow_id; });
ok(e_dup.some(e => e.includes('duplicate workflow_id')), 'flags duplicate workflow_id');

const e_cohort = breakOne(r => { r.workflows[0].cohort_id = 'nonexistent_cohort'; });
ok(e_cohort.some(e => e.includes('nonexistent_cohort')), 'flags unknown cohort_id');

const e_layer = breakOne(r => { r.workflows[1].stages[0].produces = ['no_such_layer_v1']; });
ok(e_layer.some(e => e.includes('no_such_layer_v1')), 'flags unknown produces layer_id');

// BP3 (index 2) consumes joint_candidates_v1 which BP6 (index 5) produces — earlier-consumes-later.
const e_dag = breakOne(r => { r.workflows[0].stages[2].consumes = ['joint_candidates_v1']; });
ok(e_dag.some(e => e.includes('ordering violates DAG')), 'flags DAG ordering violation');

const e_runner = breakOne(r => {
  r.workflows[0].runners[1].runner_id = r.workflows[0].runners[0].runner_id;
});
ok(e_runner.some(e => e.includes('duplicate runner_id')), 'flags duplicate runner_id');

// ---------------------------------------------------------------------
console.log('\n=== validate (cycle in produces ↔ consumes) ===');
const cycled = JSON.parse(JSON.stringify(synthetic));
// BP3 produces bp_atlas_zones_v1; add bp_atlas_zones_v1 to its own consumes.
cycled.workflows[0].stages[2].consumes = (cycled.workflows[0].stages[2].consumes || []).concat(['bp_atlas_zones_v1']);
const cycleErrs = validateWorkflowsRegistry(cycled, { cohortsRegistry, layersIndex, atlasesIndex });
ok(cycleErrs.some(e => e.includes('consumes its own output')),  'flags self-cycle');

// ---------------------------------------------------------------------
console.log('\n=== validate (duplicate producer for same layer_id) ===');
const dup = JSON.parse(JSON.stringify(synthetic));
dup.workflows[0].stages[5].produces = ['bp_atlas_zones_v1'];   // BP6 now also produces zones (was BP3)
const dupErrs = validateWorkflowsRegistry(dup, { cohortsRegistry, layersIndex, atlasesIndex });
ok(dupErrs.some(e => e.includes('produced by both')),  'flags duplicate producer for same layer_id');

// ---------------------------------------------------------------------
console.log('\n=== validate (without cross-ref inputs — schema-only) ===');
// When cohortsRegistry/layersIndex absent, those checks are skipped.
const noXref = validateWorkflowsRegistry(synthetic, {});
eq(noXref, [], 'schema-only validation passes (no cross-ref errors)');

// ---------------------------------------------------------------------
console.log('\n=== validate (missing atlas_id from installed) ===');
const notInstalled = JSON.parse(JSON.stringify(synthetic));
notInstalled.atlas_id = 'never-installed';
const niErrs = validateWorkflowsRegistry(notInstalled, { cohortsRegistry, layersIndex, atlasesIndex });
ok(niErrs.some(e => e.includes('not in atlases/_index.json')),  'flags un-installed atlas_id');

// ---------------------------------------------------------------------
console.log('\n=== validate (junk payload) ===');
ok(validateWorkflowsRegistry(null).length === 1, 'null payload → 1 error');
ok(validateWorkflowsRegistry({}).length >= 1,    'empty object → ≥1 error');

// ---------------------------------------------------------------------
console.log('\n=== lookup helpers ===');
const bp = getWorkflow(synthetic, 'bp_atlas_pipeline');
ok(bp && bp.label.startsWith('BP_ATLAS'), 'getWorkflow resolves bp_atlas_pipeline');
ok(getWorkflow(synthetic, 'nope') === null, 'getWorkflow returns null for unknown');
eq(listWorkflows(synthetic).length, 2, 'listWorkflows returns 2');

const consumesZones = getWorkflowsByConsumes(synthetic, 'bp_atlas_zones_v1');
eq(consumesZones.map(w => w.workflow_id), ['bp_atlas_pipeline'], 'getWorkflowsByConsumes finds bp_atlas');
const producesZones = getWorkflowsByProduces(synthetic, 'bp_atlas_zones_v1');
eq(producesZones.map(w => w.workflow_id), ['bp_atlas_pipeline'], 'getWorkflowsByProduces finds bp_atlas');
eq(getWorkflowsByProduces(synthetic, 'synteny_18sp_v1').map(w => w.workflow_id),
   ['gene_order_consolidation'],                                  'getWorkflowsByProduces finds gene_order');
eq(getWorkflowsByConsumes(synthetic, 'no_such_layer'), [],         'getWorkflowsByConsumes returns [] for unknown');

// ---------------------------------------------------------------------
console.log('\n=== getStatusForWorkflow (mocked fetch) ===');
const mockStatus = {
  workflow_id: 'bp_atlas_pipeline',
  runner_id: 'laptop',
  knob_hash: 'a3b7c9d2',
  stages_completed: ['BP1','BP2','BP3','BP3c','BP5','BP6'],
  stages_failed: [],
};
// Mock fetch: 200 for the bp_atlas status_file, 404 for gene_order's.
async function statusFetch(url) {
  if (url.endsWith('results_bpatlas/_status.json')) {
    return { ok: true, status: 200, json: async () => mockStatus };
  }
  return { ok: false, status: 404, json: async () => ({}) };
}
const bpStatus = await getStatusForWorkflow('', bp, { fetch: statusFetch });
ok(bpStatus && bpStatus.knob_hash === 'a3b7c9d2', 'getStatusForWorkflow returns mocked status');
const noStatus = await getStatusForWorkflow('', synthetic.workflows[1], { fetch: statusFetch });
ok(noStatus === null, 'getStatusForWorkflow returns null on 404');

// ---------------------------------------------------------------------
console.log('\n=== isWorkflowOutputStale ===');
ok(!isWorkflowOutputStale(bp, bpStatus), 'fresh: knob_hash matches → not stale');
const staleStatus = Object.assign({}, mockStatus, { knob_hash: 'differenthash' });
ok( isWorkflowOutputStale(bp, staleStatus), 'stale: knob_hash differs → stale');
const autoBp = Object.assign({}, bp, { default_knob_hash: 'auto' });
ok(!isWorkflowOutputStale(autoBp, staleStatus), "'auto' default knob_hash never flags stale");
ok(!isWorkflowOutputStale(bp, null),  'null status → not stale');
ok(!isWorkflowOutputStale(null, bpStatus),  'null workflow → not stale');

// ---------------------------------------------------------------------
console.log(`\n${_pass} passed, ${_fail} failed.`);
if (_fail > 0) process.exit(1);
