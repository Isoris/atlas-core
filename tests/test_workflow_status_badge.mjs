// tests/test_workflow_status_badge.mjs
// Smoke tests for the snapshot collector + classifier in
// core/workflow_status_badge.js. DOM rendering is not tested here (no
// jsdom dependency); the chip's user-visible bits are exercised in-browser.
// Run: node tests/test_workflow_status_badge.mjs

import { _collectSnapshot } from '../core/workflow_status_badge.js';

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
// Fixtures
// ---------------------------------------------------------------------
const workflowsByAtlas = {
  'cross-species': {
    workflows: [
      { workflow_id: 'bp_atlas_pipeline', label: 'BP_ATLAS pipeline',
        default_knob_hash: 'a3b7c9d2',
        status_file: 'data/breakpoints/results_bpatlas/_status.json' },
      { workflow_id: 'gene_order_consolidation', label: 'Gene order',
        default_knob_hash: 'auto',
        status_file: 'data/breakpoints/_status_gene_order.json' },
    ],
  },
  'evolution': {
    workflows: [
      { workflow_id: 'run_polarisation', label: 'Polarisation',
        default_knob_hash: 'beef',
        status_file: 'data/evolution_polarisation/_status.json' },
    ],
  },
};

// Per-URL canned responses. Maps URL → either a status payload or 404.
const FAKE_STATUS = {
  // bp_atlas: fresh (knob_hash matches)
  'atlases/cross-species/data/breakpoints/results_bpatlas/_status.json':
    { workflow_id: 'bp_atlas_pipeline', runner_id: 'laptop',
      knob_hash: 'a3b7c9d2', stages_completed: ['BP1','BP2','BP3'],
      stages_failed: [], finished_at: new Date(Date.now() - 3600 * 1000).toISOString() },
  // gene_order: failed
  'atlases/cross-species/data/breakpoints/_status_gene_order.json':
    { workflow_id: 'gene_order_consolidation', runner_id: 'laptop',
      knob_hash: 'whatever', stages_completed: ['GO1'], stages_failed: ['GO3'],
      finished_at: new Date(Date.now() - 7200 * 1000).toISOString() },
  // evolution polarisation: stale (knob_hash differs)
  'atlases/evolution/data/evolution_polarisation/_status.json':
    { workflow_id: 'run_polarisation', runner_id: 'slurm',
      knob_hash: 'old_hash', stages_failed: [],
      finished_at: new Date(Date.now() - 86400 * 1000).toISOString() },
};

async function mockFetch(url) {
  if (url in FAKE_STATUS) {
    return { ok: true, status: 200, text: async () => '', json: async () => FAKE_STATUS[url] };
  }
  return { ok: false, status: 404, text: async () => '', json: async () => ({}) };
}

// Stub registry + manifests.
const registry = {
  getWorkflows(atlas_id) { return workflowsByAtlas[atlas_id] || null; },
};

// ---------------------------------------------------------------------
console.log('\n=== empty manifests → empty snapshot ===');
{
  const snap = await _collectSnapshot(registry, new Map(), mockFetch);
  eq(snap, { total: 0, fresh: 0, stale: 0, failed: 0, never: 0, rows: [] }, 'no atlases → 0 rows');
}

// ---------------------------------------------------------------------
console.log('\n=== atlases without workflows → 0 rows ===');
{
  const manifests = new Map([
    ['inversion', {}],
    ['diversity', {}],
  ]);
  const snap = await _collectSnapshot(registry, manifests, mockFetch);
  ok(snap.total === 0,                                 'atlases without workflows registry contribute nothing');
  ok(snap.rows.length === 0,                           'no rows emitted');
}

// ---------------------------------------------------------------------
console.log('\n=== fresh / stale / failed mix ===');
{
  const manifests = new Map([
    ['cross-species', {}],
    ['evolution',     {}],
  ]);
  const snap = await _collectSnapshot(registry, manifests, mockFetch);
  ok(snap.total === 3,                                 `total = 3 workflows (got ${snap.total})`);
  ok(snap.fresh === 1,                                 `fresh = 1 (got ${snap.fresh})`);
  ok(snap.failed === 1,                                `failed = 1 (got ${snap.failed})`);
  ok(snap.stale === 1,                                 `stale = 1 (got ${snap.stale})`);
  ok(snap.never === 0,                                 `never = 0 (got ${snap.never})`);
  // Spot-check classifications
  const bp   = snap.rows.find(r => r.wf_id === 'bp_atlas_pipeline');
  const geno = snap.rows.find(r => r.wf_id === 'gene_order_consolidation');
  const pol  = snap.rows.find(r => r.wf_id === 'run_polarisation');
  ok(bp   && bp.kind   === 'fresh',                    'bp_atlas_pipeline → fresh (knob_hash matches)');
  ok(geno && geno.kind === 'failed',                   'gene_order_consolidation → failed (stages_failed non-empty)');
  ok(pol  && pol.kind  === 'stale',                    'run_polarisation → stale (knob_hash differs)');
  ok(bp   && bp.status && bp.status.runner_id === 'laptop', 'status object preserved');
}

// ---------------------------------------------------------------------
console.log('\n=== status_file 404 → never-ran ===');
{
  // Wire a workflow whose status_file isn't in FAKE_STATUS.
  const ghostReg = {
    getWorkflows(atlas_id) {
      if (atlas_id === 'ghost') {
        return { workflows: [{ workflow_id: 'never_ran_wf', label: 'Ghost',
                                default_knob_hash: 'x',
                                status_file: 'nowhere/_status.json' }] };
      }
      return null;
    },
  };
  const manifests = new Map([['ghost', {}]]);
  const snap = await _collectSnapshot(ghostReg, manifests, mockFetch);
  ok(snap.total === 1,                                 'ghost atlas contributes 1 workflow');
  ok(snap.never === 1,                                 '404 status → never classification');
  ok(snap.fresh + snap.stale + snap.failed === 0,      'no other class triggers');
  ok(snap.rows[0].status === null,                     'status null on 404');
}

// ---------------------------------------------------------------------
console.log('\n=== "auto" knob_hash never flags stale ===');
{
  // gene_order_consolidation has default_knob_hash:'auto' AND stages_failed=['GO3'].
  // We already know it lands as 'failed' (failed wins over stale/fresh check ordering).
  // Synthesize a clean "auto" workflow to verify the staleness rule alone.
  const reg = {
    getWorkflows() {
      return { workflows: [{
        workflow_id: 'auto_wf', label: 'auto knob',
        default_knob_hash: 'auto',
        status_file: 'atlas-root/_status.json',
      }] };
    },
  };
  const manifests = new Map([['x', {}]]);
  const url = 'atlases/x/atlas-root/_status.json';
  const localFetch = async (u) => {
    if (u === url) {
      return { ok: true, status: 200, text: async () => '',
               json: async () => ({ knob_hash: 'doesntmatter', stages_failed: [],
                                    finished_at: new Date().toISOString(), runner_id: 'local' }) };
    }
    return { ok: false, status: 404, text: async () => '', json: async () => ({}) };
  };
  const snap = await _collectSnapshot(reg, manifests, localFetch);
  ok(snap.fresh === 1,                                 "'auto' default_knob_hash classifies fresh (not stale)");
}

// ---------------------------------------------------------------------
console.log(`\n${_pass} passed, ${_fail} failed.`);
if (_fail > 0) process.exit(1);
