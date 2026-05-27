// tests/test_registry_integration.mjs
// Smoke tests for the registry trilogy wiring inside Registry.register_atlas:
//   1. workflows registry is validated + stored per-atlas, retrievable via getWorkflows().
//   2. Tree-layer entries in layers.registry get validated at register time.
//   3. setGlobalRegistries() forwards xref data to per-atlas validators.
//   4. Registry.readTreePath() dispatches to LayerRouter.readTreePath.
//   5. Existing (scalar-only) atlases keep booting unchanged.
// Run: node tests/test_registry_integration.mjs

import { Registry } from '../core/registry_core.js';

let _pass = 0, _fail = 0;
function ok(cond, msg) {
  if (cond) { _pass++; console.log(`  ✓ ${msg}`); }
  else { _fail++; console.error(`  ✗ ${msg}`); }
}

// Minimal atlasState double — register_atlas only touches state.emit.
const fakeState = { emit() {} };

// ---------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------
const cohortsRegistry = {
  cohorts: [
    { cohort_id: 'f1_hybrid_cga_cma' },
    { cohort_id: 'cross_species_18sp_compendium' },
  ],
};
const atlasesIndex = { atlases: ['cross-species', 'inversion', 'core'] };

const cleanLayersScalar = {
  layers: {
    scrubber_main: { layer_id: 'scrubber_main', source: 'file', path: 'data/foo.json',
                     format: 'json', cache_tier: 'warm' },
  },
};
const cleanLayersTree = {
  layers: {
    bp_atlas_results_v1: {
      layer_id: 'bp_atlas_results_v1', kind: 'tree', label: 'BP_ATLAS', root: 'data/results/',
      cohort_id: 'f1_hybrid_cga_cma',
      produced_by: 'bp_atlas_pipeline',
      tree: {
        results_table: { kind: 'leaf', leaf_kind: 'tsv' },
        per_pair: { kind: 'dir', children_pattern: '*.paf', leaf_kind: 'paf' },
      },
    },
  },
};
const cleanWorkflows = {
  atlas_id: 'cross-species',
  version: '1.0',
  workflows: [
    {
      workflow_id: 'bp_atlas_pipeline',
      label: 'BP_ATLAS pipeline',
      cohort_id: 'f1_hybrid_cga_cma',
      outputs_root: 'data/results/',
      status_file:  'data/results/_status.json',
      stages: [{
        stage_id: 'BP1', script: 'scripts/bp1.sh',
        produces: ['bp_atlas_results_v1'],
      }],
      runners: [{ runner_id: 'laptop', script: 'runners/laptop.sh' }],
    },
  ],
};

// ---------------------------------------------------------------------
console.log('\n=== 1. backward compat — scalar-only atlas registers as before ===');
{
  const r = new Registry({ atlasState: fakeState });
  // No workflows, no tree-layer, no global registries set — must succeed.
  r.register_atlas('inversion', { layers: cleanLayersScalar });
  const lookup = r._lookup('inversion.scrubber_main') || r._lookup('scrubber_main');
  ok(lookup && lookup.entry.layer_id === 'scrubber_main', 'scalar layer indexed');
  ok(r.getWorkflows('inversion') === null,                'getWorkflows() returns null when absent');
}

// ---------------------------------------------------------------------
console.log('\n=== 2. clean tree-layer + clean workflows — both register ===');
{
  const r = new Registry({ atlasState: fakeState });
  r.setGlobalRegistries({ cohortsRegistry, atlasesIndex });
  r.register_atlas('cross-species', {
    layers: cleanLayersTree,
    workflows: cleanWorkflows,
  });
  const lookup = r._lookup('cross-species.bp_atlas_results_v1') || r._lookup('bp_atlas_results_v1');
  ok(lookup && lookup.entry.kind === 'tree',          'tree-layer indexed (kind preserved)');
  const wf = r.getWorkflows('cross-species');
  ok(wf && wf.workflows.length === 1,                 'workflows registry stored on atlas');
  ok(wf.workflows[0].workflow_id === 'bp_atlas_pipeline', 'workflow_id round-trips');
}

// ---------------------------------------------------------------------
// Capture console.warn so we can verify the non-fatal validation logs
// without polluting the test output.
const _warns = [];
const _origWarn = console.warn;
function captureWarns() { _warns.length = 0; console.warn = (...a) => _warns.push(a.join(' ')); }
function releaseWarns() { console.warn = _origWarn; }

console.log('\n=== 3. broken tree-layer — register_atlas warns + still indexes (non-fatal) ===');
{
  const r = new Registry({ atlasState: fakeState });
  r.setGlobalRegistries({ cohortsRegistry, atlasesIndex });
  const badTree = JSON.parse(JSON.stringify(cleanLayersTree));
  badTree.layers.bp_atlas_results_v1.tree.results_table.leaf_kind = 'parquet';   // unknown
  captureWarns();
  let threw = null;
  try { r.register_atlas('cross-species', { layers: badTree }); }
  catch (e) { threw = e; }
  releaseWarns();
  ok(threw === null, 'broken tree-layer does NOT throw (boot continues)');
  ok(_warns.some(w => /tree-layer 'cross-species\.bp_atlas_results_v1'/.test(w)),
                                              'warn surfaces the layer key');
  ok(_warns.some(w => /unknown leaf_kind/.test(w)),
                                              'warn names the failing rule');
  // The layer is still indexed so registry.resolve() works (legacy/scalar path).
  const lookup = r._lookup('cross-species.bp_atlas_results_v1') || r._lookup('bp_atlas_results_v1');
  ok(lookup,                                  'broken tree-layer still indexed (resolve works)');
}

// ---------------------------------------------------------------------
console.log('\n=== 4. broken workflows — register_atlas warns + drops workflows (non-fatal) ===');
{
  const r = new Registry({ atlasState: fakeState });
  r.setGlobalRegistries({ cohortsRegistry, atlasesIndex });
  const badWf = JSON.parse(JSON.stringify(cleanWorkflows));
  badWf.workflows[0].cohort_id = 'never_registered_cohort';   // unknown cohort
  captureWarns();
  let threw = null;
  try { r.register_atlas('cross-species', { layers: cleanLayersTree, workflows: badWf }); }
  catch (e) { threw = e; }
  releaseWarns();
  ok(threw === null,                          'broken workflows does NOT throw');
  ok(_warns.some(w => /workflows\.registry\.json for 'cross-species'/.test(w)),
                                              'warn surfaces the atlas');
  ok(_warns.some(w => /never_registered_cohort/.test(w)),
                                              'warn names the bad cohort_id');
  ok(r.getWorkflows('cross-species') === null, 'workflows dropped after validation failure');
}

// ---------------------------------------------------------------------
console.log('\n=== 5. workflows validates produces layer against THIS atlas\'s layers.registry ===');
{
  const r = new Registry({ atlasState: fakeState });
  r.setGlobalRegistries({ cohortsRegistry, atlasesIndex });
  const wfWithUnknownLayer = JSON.parse(JSON.stringify(cleanWorkflows));
  wfWithUnknownLayer.workflows[0].stages[0].produces = ['some_layer_not_in_this_atlas'];
  captureWarns();
  let threw = null;
  try { r.register_atlas('cross-species', { layers: cleanLayersTree, workflows: wfWithUnknownLayer }); }
  catch (e) { threw = e; }
  releaseWarns();
  ok(threw === null,                          'unknown produces does NOT throw');
  ok(_warns.some(w => /produces unknown layer_id/.test(w)),
                                              'warn names the rule');
  ok(r.getWorkflows('cross-species') === null, 'workflows dropped');
}

// ---------------------------------------------------------------------
console.log('\n=== 6. xref skipped when global registries not set ===');
{
  const r = new Registry({ atlasState: fakeState });
  // Deliberately DON'T call setGlobalRegistries.
  // Validator falls back to schema-only — unknown cohort_id won't throw.
  const wfNoXref = JSON.parse(JSON.stringify(cleanWorkflows));
  wfNoXref.workflows[0].cohort_id = 'arbitrary_cohort_no_xref_check';
  r.register_atlas('cross-species', { layers: cleanLayersTree, workflows: wfNoXref });
  ok(r.getWorkflows('cross-species') != null, 'workflows registered without xref data');
}

// ---------------------------------------------------------------------
console.log('\n=== 7. readTreePath dispatches through LayerRouter ===');
{
  // Mock fetch so readTreePath can actually fetch the leaf.
  const FAKE = {
    'data/results/results_table': 'col\nA\nB\n',   // .tsv suffix dropped by tree-path resolver
  };
  globalThis.fetch = async (url) => {
    const path = url.replace(/^\/+/, '');
    if (!(path in FAKE)) return { ok: false, status: 404, text: async () => '', json: async () => ({}), arrayBuffer: async () => new ArrayBuffer(0) };
    return { ok: true, status: 200, text: async () => FAKE[path], json: async () => ({}), arrayBuffer: async () => new ArrayBuffer(0) };
  };

  const r = new Registry({ atlasState: fakeState });
  r.setGlobalRegistries({ cohortsRegistry, atlasesIndex });
  r.register_atlas('cross-species', { layers: cleanLayersTree, workflows: cleanWorkflows });

  // metadata read — no fetch
  const meta = await r.readTreePath('cross-species.bp_atlas_results_v1', '');
  ok(meta && meta.kind === 'metadata', 'metadata read returns metadata kind');

  // Unknown key
  const unknown = await r.readTreePath('cross-species.no_such_layer', '');
  ok(unknown === null, 'unknown layer returns null');

  // Scalar-layer readTreePath should throw a clear error.
  let threw = null;
  try { await r.readTreePath('inversion.scrubber_main', ''); }
  catch (e) { threw = e; }
  // (different atlas — won't find it; should warn + return null instead)
  ok(threw === null, "different-atlas key resolves through fallback (warn + null), doesn't throw");
}

// ---------------------------------------------------------------------
console.log(`\n${_pass} passed, ${_fail} failed.`);
if (_fail > 0) process.exit(1);
