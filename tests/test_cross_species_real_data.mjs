// tests/test_cross_species_real_data.mjs
// End-to-end validation of the registry trilogy against REAL atlas data:
//   - core/cohorts.registry.json
//   - atlases/cross-species/registries/data/layers.registry.json
//   - atlases/cross-species/registries/data/workflows.registry.json
// Run: node tests/test_cross_species_real_data.mjs
//
// This is the proof the SPECs work against actual data, not just
// hand-crafted fixtures. Any drift between the real file and the schema
// surfaces here and either points to a real bug to fix or a schema gap
// to widen.

import { readFileSync, existsSync } from 'node:fs';
import { resolve as pathResolve } from 'node:path';

import { validateCohortsRegistry } from '../core/cohorts_registry.js';
import { validateWorkflowsRegistry } from '../core/workflows_registry.js';
import { validateTreeLayer } from '../core/tree_layer_registry.js';

let _pass = 0, _fail = 0;
function ok(cond, msg) {
  if (cond) { _pass++; console.log(`  ✓ ${msg}`); }
  else { _fail++; console.error(`  ✗ ${msg}`); }
}

// Resolve paths from the atlas-core repo root (one level up from tests/).
const CORE_ROOT = pathResolve(import.meta.url.replace(/^file:\/\//, ''), '../../');
const CROSS_SPECIES_ROOT = pathResolve(CORE_ROOT, '../cross-species-atlas');

const FILES = {
  cohorts:   pathResolve(CORE_ROOT, 'core/cohorts.registry.json'),
  atlases:   pathResolve(CORE_ROOT, 'atlases/_index.json'),
  layers:    pathResolve(CROSS_SPECIES_ROOT, 'atlases/cross-species/registries/data/layers.registry.json'),
  workflows: pathResolve(CROSS_SPECIES_ROOT, 'atlases/cross-species/registries/data/workflows.registry.json'),
};

function loadJson(path) {
  if (!existsSync(path)) {
    console.log(`  ⊘  ${path} not found — skipping tests that need it`);
    return null;
  }
  return JSON.parse(readFileSync(path, 'utf-8'));
}

// ---------------------------------------------------------------------
console.log('\n=== file presence ===');
const cohortsReg   = loadJson(FILES.cohorts);
const atlasesIdx   = loadJson(FILES.atlases);
const layersReg    = loadJson(FILES.layers);
const workflowsReg = loadJson(FILES.workflows);
ok(cohortsReg,   `cohorts.registry.json loaded (${cohortsReg && cohortsReg.cohorts.length} cohorts)`);
ok(layersReg,    `cross-species layers.registry.json loaded (${layersReg && layersReg.layers.length} layers)`);
ok(workflowsReg, `cross-species workflows.registry.json loaded (${workflowsReg && workflowsReg.workflows.length} workflows)`);
if (atlasesIdx) console.log(`  ⓘ atlases/_index.json present (${atlasesIdx.atlases.length} atlases)`);
else            console.log(`  ⓘ atlases/_index.json absent — atlas_id installed-check will skip`);

if (!cohortsReg || !layersReg || !workflowsReg) {
  console.log('\nMissing one or more required real files; bailing out.');
  process.exit(_fail > 0 ? 1 : 0);
}

// ---------------------------------------------------------------------
console.log('\n=== cohorts.registry.json validates ===');
const cohortsErrs = validateCohortsRegistry(cohortsReg, atlasesIdx);
ok(cohortsErrs.length === 0, `cohorts validates clean (${cohortsErrs.length} errors)`);
if (cohortsErrs.length) cohortsErrs.forEach(e => console.error(`    - ${e}`));

// ---------------------------------------------------------------------
console.log('\n=== cross-species tree-layers validate against schema + xref ===');
const treeEntries = layersReg.layers.filter(l => l && l.kind === 'tree');
ok(treeEntries.length > 0, `at least one tree-layer present (${treeEntries.length} found)`);
for (const entry of treeEntries) {
  const errs = validateTreeLayer(entry, {
    cohortsRegistry:  cohortsReg,
    workflowsRegistry: workflowsReg,
  });
  ok(errs.length === 0, `tree-layer '${entry.layer_id}' validates clean (${errs.length} errors)`);
  if (errs.length) errs.forEach(e => console.error(`    - ${e}`));
}

// ---------------------------------------------------------------------
console.log('\n=== cross-species workflows.registry validates against schema + xref ===');
// layersIndex built from layers.registry.json so produces/consumes cross-check works.
const layersIndex = { layers: layersReg.layers
  .filter(l => l && typeof l.layer_id === 'string')
  .map(l => ({ layer_id: l.layer_id })) };
const wfErrs = validateWorkflowsRegistry(workflowsReg, {
  cohortsRegistry: cohortsReg,
  layersIndex,
  atlasesIndex: atlasesIdx,
});
ok(wfErrs.length === 0, `workflows validates clean (${wfErrs.length} errors)`);
if (wfErrs.length) wfErrs.forEach(e => console.error(`    - ${e}`));

// ---------------------------------------------------------------------
console.log('\n=== sanity: produced layers all reference workflow_ids that exist ===');
const knownWfIds = new Set(workflowsReg.workflows.map(w => w.workflow_id));
let unknownProducers = 0;
for (const l of layersReg.layers) {
  if (l && l.produced_by != null && !knownWfIds.has(l.produced_by)) {
    console.error(`    - layer '${l.layer_id}' produced_by='${l.produced_by}' is not in workflows.registry`);
    unknownProducers++;
  }
}
ok(unknownProducers === 0, `every layer's produced_by points to a real workflow (${unknownProducers} mismatches)`);

// ---------------------------------------------------------------------
console.log('\n=== sanity: every workflow stage produces a layer that exists in layers.registry ===');
const knownLayerIds = new Set(layersIndex.layers.map(l => l.layer_id));
let unknownProduces = 0;
for (const wf of workflowsReg.workflows) {
  for (const stg of wf.stages || []) {
    for (const lid of stg.produces || []) {
      if (!knownLayerIds.has(lid)) {
        console.error(`    - workflow '${wf.workflow_id}' stage '${stg.stage_id}' produces unknown layer '${lid}'`);
        unknownProduces++;
      }
    }
  }
}
ok(unknownProduces === 0, `every produces[] entry exists as a layer (${unknownProduces} mismatches)`);

// ---------------------------------------------------------------------
console.log('\n=== sanity: cohort_ids in workflows + tree-layers all exist ===');
const knownCohortIds = new Set(cohortsReg.cohorts.map(c => c.cohort_id));
let unknownCohorts = 0;
for (const wf of workflowsReg.workflows) {
  if (wf.cohort_id && !knownCohortIds.has(wf.cohort_id)) {
    console.error(`    - workflow '${wf.workflow_id}' references unknown cohort '${wf.cohort_id}'`);
    unknownCohorts++;
  }
}
for (const entry of treeEntries) {
  if (entry.cohort_id && !knownCohortIds.has(entry.cohort_id)) {
    console.error(`    - tree-layer '${entry.layer_id}' references unknown cohort '${entry.cohort_id}'`);
    unknownCohorts++;
  }
}
ok(unknownCohorts === 0, `every cohort_id reference resolves (${unknownCohorts} mismatches)`);

// ---------------------------------------------------------------------
console.log(`\n${_pass} passed, ${_fail} failed.`);
if (_fail > 0) process.exit(1);
