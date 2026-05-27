// tests/test_cohorts_registry.mjs
// Smoke tests for core/cohorts_registry.js + core/cross_atlas_imports.js.
// Run: node tests/test_cohorts_registry.mjs
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve as resolvePath } from 'node:path';

import {
  loadCohortsRegistry,
  validateCohortsRegistry,
  getCohort,
  listCohorts,
  getCohortsForAtlas,
  findHandoff,
  listHandoffs,
} from '../core/cohorts_registry.js';

import {
  read,
  setStrictMode,
  isStrictMode,
  CohortMismatchError,
  LayerNotFoundError,
} from '../core/cross_atlas_imports.js';

const HERE = dirname(fileURLToPath(import.meta.url));
const CORE_ROOT = resolvePath(HERE, '..');

// Node fetch shim that reads from disk.
async function diskFetch(url) {
  const path = url.startsWith('http')
    ? new URL(url).pathname
    : resolvePath(CORE_ROOT, url.replace(/^\/?/, ''));
  try {
    const text = readFileSync(path, 'utf-8');
    return { ok: true, status: 200, json: async () => JSON.parse(text) };
  } catch (e) {
    return { ok: false, status: 404, json: async () => ({}) };
  }
}

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
console.log('\n=== loadCohortsRegistry + shape ===');
const registry = await loadCohortsRegistry('', { fetch: diskFetch });
ok(typeof registry === 'object', 'registry parses');
ok(registry.version === '1.0',   `version is 1.0 (got ${registry.version})`);
ok(Array.isArray(registry.cohorts) && registry.cohorts.length === 3, '3 cohorts present');
ok(Array.isArray(registry.cross_reference_handoffs) && registry.cross_reference_handoffs.length === 1, '1 handoff present');

console.log('\n=== validateCohortsRegistry (clean) ===');
const atlasesIndex = { atlases: ['core','cross-species','diversity','evolution','genome','inversion','meiosis','popstats','population','relatedness'] };
const errs = validateCohortsRegistry(registry, atlasesIndex);
eq(errs, [], 'clean validation returns no errors');

console.log('\n=== validateCohortsRegistry (broken) ===');
const broken = JSON.parse(JSON.stringify(registry));
broken.cohorts[0].cohort_id = 'BAD-ID';   // not lowercase
broken.cohorts[1].cohort_id = broken.cohorts[2].cohort_id;   // duplicate
broken.cross_reference_handoffs[0].from_cohort = 'nonexistent';
broken.cross_reference_handoffs[0].via_layer_pattern = '[unclosed';
const brokeErrs = validateCohortsRegistry(broken, atlasesIndex);
ok(brokeErrs.length >= 3, `broken registry yields ≥3 errors (got ${brokeErrs.length}): ${brokeErrs.join(' | ')}`);

console.log('\n=== getCohort / listCohorts / getCohortsForAtlas ===');
const cgar = getCohort(registry, 'cgar_hatchery_226');
ok(cgar && cgar.n_samples_approx === 226, 'getCohort resolves cgar_hatchery_226');
ok(getCohort(registry, 'nonexistent') === null, 'getCohort returns null for unknown');
eq(listCohorts(registry).length, 3, 'listCohorts returns 3');
const invCohorts = getCohortsForAtlas(registry, 'inversion');
ok(invCohorts.length === 1 && invCohorts[0].cohort_id === 'cgar_hatchery_226', 'inversion atlas has cgar_hatchery_226');
const csCohorts = getCohortsForAtlas(registry, 'cross-species');
ok(csCohorts.length === 1 && csCohorts[0].cohort_id === 'f1_hybrid_cga_cma', 'cross-species atlas has f1_hybrid');
eq(getCohortsForAtlas(registry, 'unknown-atlas'), [], 'unknown atlas returns []');

console.log('\n=== findHandoff ===');
const hf = findHandoff(registry, 'f1_hybrid_cga_cma', 'cgar_hatchery_226', 'cross-species.breakpoints_consolidated_v1');
ok(hf && hf.handoff_id === 'bp_atlas_to_hatchery_join', 'BP_ATLAS handoff matches');
const hf2 = findHandoff(registry, 'f1_hybrid_cga_cma', 'cgar_hatchery_226', 'cross-species.bp_atlas_reciprocity_v2');
ok(hf2 && hf2.handoff_id === 'bp_atlas_to_hatchery_join', 'pattern matches reciprocity_v2');
const noHf = findHandoff(registry, 'f1_hybrid_cga_cma', 'cgar_hatchery_226', 'cross-species.unrelated_v1');
ok(noHf === null, 'unrelated layer returns null');
const reversed = findHandoff(registry, 'cgar_hatchery_226', 'f1_hybrid_cga_cma', 'inversion.candidates_v1');
ok(reversed === null, 'reversed direction returns null');

console.log('\n=== listHandoffs ===');
eq(listHandoffs(registry).length, 1, 'listHandoffs returns 1');
eq(listHandoffs(registry, { from_cohort: 'f1_hybrid_cga_cma' }).length, 1, 'filter from_cohort');
eq(listHandoffs(registry, { handoff_kind: 'reference_join' }).length, 0, 'filter handoff_kind no match');

console.log('\n=== cross_atlas_imports.read (same-cohort pass) ===');
const fakeRegistry = {
  resolve: async (lid) => ({ rows: [{ id: 1 }], _layer: lid }),
  _atlases: new Map([
    ['inversion', { layers: { 'candidates_v1': { cohort_id: 'cgar_hatchery_226' } } }],
    ['cross-species', { layers: { 'breakpoints_consolidated_v1': { cohort_id: 'f1_hybrid_cga_cma' } } }],
    ['evolution', { layers: { 'rate_v1': {} } }],   // no cohort_id declared
  ]),
};
const r1 = await read({
  consumer_atlas_id: 'inversion',
  layer_ref:         'inversion.candidates_v1',
  registry:          fakeRegistry,
  cohorts_registry:  registry,
});
ok(r1.data && Array.isArray(r1.data.rows), 'same-cohort read returns data');
eq(r1.meta.cohort_status, 'same_cohort', 'meta.cohort_status === same_cohort');
ok(r1.meta.handoff_used === null, 'no handoff for same-cohort');

console.log('\n=== cross_atlas_imports.read (handoff pass) ===');
const r2 = await read({
  consumer_atlas_id: 'inversion',
  layer_ref:         'cross-species.breakpoints_consolidated_v1',
  registry:          fakeRegistry,
  cohorts_registry:  registry,
});
eq(r2.meta.cohort_status, 'handoff', 'cross-cohort via known handoff');
eq(r2.meta.handoff_used, 'bp_atlas_to_hatchery_join', 'handoff_used set');

console.log('\n=== cross_atlas_imports.read (mismatch — permissive mode warns instead of throws) ===');
// 2026-05-26: module default flipped to strict (Phase 0b). Explicitly flip
// back to permissive here so this section keeps testing the permissive code
// path. The "strict mode throws" section below toggles back to strict.
setStrictMode(false);
ok(isStrictMode() === false, 'permissive mode active after explicit setStrictMode(false)');
const oldWarn = console.warn;
let warnedOnce = false;
console.warn = (...args) => { warnedOnce = true; };
const fakeRegistry2 = {
  resolve: async (lid) => ({ rows: [], _layer: lid }),
  _atlases: new Map([
    ['evolution', { layers: { 'rate_v1': { cohort_id: 'f1_hybrid_cga_cma' } } }],
    ['inversion', { layers: { 'whatever_v1': { cohort_id: 'cgar_hatchery_226' } } }],
  ]),
};
const r3 = await read({
  consumer_atlas_id: 'inversion',
  layer_ref:         'evolution.rate_v1',
  registry:          fakeRegistry2,
  cohorts_registry:  registry,
});
console.warn = oldWarn;
eq(r3.meta.cohort_status, 'mismatch_allowed', 'permissive mode passes with mismatch_allowed');
ok(warnedOnce, 'console.warn fired in permissive mode');

console.log('\n=== cross_atlas_imports.read (mismatch — strict mode throws) ===');
setStrictMode(true);
ok(isStrictMode() === true, 'isStrictMode reflects setStrictMode');
let caught = null;
try {
  await read({
    consumer_atlas_id: 'inversion',
    layer_ref:         'evolution.rate_v1',
    registry:          fakeRegistry2,
    cohorts_registry:  registry,
  });
} catch (e) { caught = e; }
ok(caught instanceof CohortMismatchError, 'strict mode throws CohortMismatchError');
ok(caught && caught.message.includes('cohorts.registry.json'), 'error message hints at registry edit');
ok(caught && caught.detail && caught.detail.producer_cohort_id === 'f1_hybrid_cga_cma', 'error carries detail block');
// Leave strict mode on at module exit — matches the new Phase 0b default.

console.log('\n=== cross_atlas_imports.read (producer with no cohort_id) ===');
const r4 = await read({
  consumer_atlas_id: 'inversion',
  layer_ref:         'evolution.rate_v1',   // cohort_id explicitly absent for this layer
  registry:          { resolve: async () => ({ ok: true }), _atlases: new Map([['evolution', { layers: { 'rate_v1': {} } }]]) },
  cohorts_registry:  registry,
});
eq(r4.meta.cohort_status, 'producer_unknown_cohort', 'unknown cohort → producer_unknown_cohort');
ok(r4.meta.producer_cohort_id === null, 'producer_cohort_id surfaces as null');

console.log(`\n${_fail === 0 ? 'ALL OK' : 'FAIL'}: ${_pass} passed, ${_fail} failed`);
process.exit(_fail === 0 ? 0 : 1);
