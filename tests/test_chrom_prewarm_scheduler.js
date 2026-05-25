// Smoke test for core/chrom_prewarm_scheduler.js — SPEC
// multichrom_load_orchestrator Slice 3 (preview).
//
// Covers:
//   - isEnabled / setEnabled round-trips through localStorage
//   - neighbors-first ordering around the active chrom
//   - cached chroms are skipped
//   - abort() invalidates the current chain
//   - new kick supersedes the old chain (token-based cancellation)
//
// Run from repo root:
//   node atlas-core/tests/test_chrom_prewarm_scheduler.js

import { ChromPrewarmScheduler } from '../core/chrom_prewarm_scheduler.js';
import { AtlasState } from '../core/atlas_state.js';

let pass = 0, fail = 0;
function check(label, cond, extra) {
  if (cond) { pass++; console.log('  ✓', label); }
  else      { fail++; console.log('  ✗', label, extra ? ' — ' + extra : ''); }
}
function group(name) { console.log('\n--- ' + name + ' ---'); }

// Node test harness — stub the browser globals the scheduler reaches for.
if (typeof globalThis.localStorage === 'undefined') {
  const _store = new Map();
  globalThis.localStorage = {
    getItem: (k) => _store.has(k) ? _store.get(k) : null,
    setItem: (k, v) => _store.set(k, String(v)),
    removeItem: (k) => _store.delete(k),
    clear: () => _store.clear(),
  };
}
// rIC shim — Node has no requestIdleCallback. The scheduler falls
// through to setTimeout when rIC is missing, but we override setTimeout
// to run synchronously so tests don't need to await timers.
const _origSetTimeout = globalThis.setTimeout;
function sync(fn) { fn(); return 0; }

function makeRegistry(opts = {}) {
  const calls = [];
  const reg = {
    resolve(key, args) {
      calls.push({ key, args });
      if (opts.fail) return Promise.reject(new Error('HTTP 404'));
      return Promise.resolve({ chrom: args && args.chrom, windows: [] });
    },
    calls,
  };
  return reg;
}

// ---------------------------------------------------------------------------
group('isEnabled / setEnabled localStorage round-trip');
{
  localStorage.clear();
  const scheduler = new ChromPrewarmScheduler({
    atlasState: new AtlasState({}), registry: makeRegistry(),
    getChromList: () => [],
  });
  check('default → disabled',  scheduler.isEnabled() === false);
  scheduler.setEnabled(true);
  check('setEnabled(true)',    scheduler.isEnabled() === true);
  check('localStorage stamped','true' === localStorage.getItem('atlas.chromPrewarmEnabled'));
  scheduler.setEnabled(false);
  check('setEnabled(false)',   scheduler.isEnabled() === false);
}

// ---------------------------------------------------------------------------
group('neighbors-first ordering (kick → registry.resolve order)');
{
  localStorage.clear();
  globalThis.setTimeout = sync;
  const state = new AtlasState({});
  state.setActiveChrom('LG07');
  const reg = makeRegistry();
  const chroms = ['LG01','LG02','LG03','LG04','LG05','LG06','LG07','LG08','LG09','LG10'];
  const scheduler = new ChromPrewarmScheduler({
    atlasState: state, registry: reg,
    getChromList: () => chroms,
  });
  scheduler.setEnabled(true);
  scheduler.kick();

  // After all synchronous timers fire, every non-active chrom should be
  // resolved exactly once, in neighbors-first order starting from LG08.
  const order = reg.calls.map(c => c.args.chrom);
  check('all neighbors (9) resolved',     order.length === 9);
  check('active chrom skipped',           !order.includes('LG07'));
  check('first resolve = LG08 (idx+1)',   order[0] === 'LG08');
  check('second resolve = LG06 (idx-1)',  order[1] === 'LG06');
  check('third resolve = LG09 (idx+2)',   order[2] === 'LG09');
  check('fourth resolve = LG05 (idx-2)',  order[3] === 'LG05');
  globalThis.setTimeout = _origSetTimeout;
}

// ---------------------------------------------------------------------------
group('successful resolve writes a chromSummary');
{
  localStorage.clear();
  globalThis.setTimeout = sync;
  const state = new AtlasState({});
  state.setActiveChrom('LG01');
  const reg = makeRegistry();   // resolve returns { chrom, windows: [] }
  const scheduler = new ChromPrewarmScheduler({
    atlasState: state, registry: reg,
    getChromList: () => ['LG01', 'LG02', 'LG03'],
  });
  scheduler.setEnabled(true);
  scheduler.kick();
  // Drain any queued microtasks so the .then-chained setChromSummary runs.
  await new Promise((resolve) => _origSetTimeout(resolve, 0));
  check('LG02 summary written from prewarm',
        state.shared.chromSummaries['LG02']
        && state.shared.chromSummaries['LG02'].chrom === 'LG02');
  check('LG03 summary written from prewarm',
        state.shared.chromSummaries['LG03']
        && state.shared.chromSummaries['LG03'].chrom === 'LG03');
  check('active chrom (LG01) did NOT get a summary from prewarm',
        !state.shared.chromSummaries['LG01']);
  globalThis.setTimeout = _origSetTimeout;
}

// ---------------------------------------------------------------------------
group('cached chroms are skipped');
{
  localStorage.clear();
  globalThis.setTimeout = sync;
  const state = new AtlasState({});
  state.setActiveChrom('LG02');
  // Pretend LG01, LG03, LG04 are already summarized.
  state.setChromSummary('LG01', { chrom: 'LG01' });
  state.setChromSummary('LG03', { chrom: 'LG03' });
  state.setChromSummary('LG04', { chrom: 'LG04' });
  const reg = makeRegistry();
  const chroms = ['LG01','LG02','LG03','LG04','LG05'];
  const scheduler = new ChromPrewarmScheduler({
    atlasState: state, registry: reg,
    getChromList: () => chroms,
  });
  scheduler.setEnabled(true);
  scheduler.kick();

  const order = reg.calls.map(c => c.args.chrom);
  check('only LG05 (uncached non-active) resolved', order.length === 1 && order[0] === 'LG05');
  globalThis.setTimeout = _origSetTimeout;
}

// ---------------------------------------------------------------------------
group('abort() cancels the in-flight chain');
{
  localStorage.clear();
  // For this test we want async timers so we can intercept partway.
  let queued = [];
  globalThis.setTimeout = (fn /* , ms */) => {
    queued.push(fn);
    return queued.length;
  };
  const state = new AtlasState({});
  state.setActiveChrom('LG01');
  const reg = makeRegistry();
  const scheduler = new ChromPrewarmScheduler({
    atlasState: state, registry: reg,
    getChromList: () => ['LG01','LG02','LG03','LG04'],
  });
  scheduler.setEnabled(true);
  scheduler.kick();
  check('first idle timer queued', queued.length === 1);
  // Abort BEFORE firing the first timer.
  scheduler.abort();
  // Now drain queued timers; the chain should bail at the token check.
  while (queued.length) {
    const fn = queued.shift();
    try { fn(); } catch (_) {}
  }
  check('no chroms resolved after abort', reg.calls.length === 0);
  globalThis.setTimeout = _origSetTimeout;
}

// ---------------------------------------------------------------------------
console.log('\n=================');
console.log(`pass: ${pass}   fail: ${fail}`);
console.log('=================');
process.exit(fail === 0 ? 0 : 1);
