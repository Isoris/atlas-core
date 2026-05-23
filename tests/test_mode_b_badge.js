// Smoke test for core/mode_b_badge.js — probeModeB() behaviour.
// Locks in the 2026-05-20 changes:
//   - layer-disabled short-circuit (skips registry.resolve when entry is
//     flagged disabled: true)
//   - graceful fallback when registry lacks the new getLayerEntry method
//   - existing reason codes still surface as expected
//
// Run from repo root:
//   node atlas-core/tests/test_mode_b_badge.js

import { probeModeB } from '../core/mode_b_badge.js';

let pass = 0, fail = 0;
function check(label, cond, extra) {
  if (cond) { pass++; console.log('  ✓', label); }
  else      { fail++; console.log('  ✗', label, extra ? ' — ' + extra : ''); }
}
function group(name) { console.log('\n--- ' + name + ' ---'); }

// ---------------------------------------------------------------------------
group('registry-not-injected reason');
{
  let r = await probeModeB(null, 'foo', {}, {});
  check('null registry → reason=registry-not-injected',
        r.ok === false && r.reason === 'registry-not-injected');
  r = await probeModeB({}, 'foo', {}, {});
  check('registry without resolve → reason=registry-not-injected',
        r.ok === false && r.reason === 'registry-not-injected');
}

// ---------------------------------------------------------------------------
group('disabled layer short-circuit');
{
  let resolveCalled = 0;
  const reg = {
    getLayerEntry: (key) => key === 'per_sample_stats'
      ? { disabled: true, _disabled_reason: 'Pipeline X has not shipped yet.' }
      : null,
    resolve: () => { resolveCalled++; return Promise.reject(new Error('HTTP 404')); },
  };
  const r = await probeModeB(reg, 'per_sample_stats', {}, {});
  check('disabled layer → ok=false',          r.ok === false);
  check('disabled layer → reason=layer-disabled',
        r.reason === 'layer-disabled');
  check('disabled layer → carries disabled_reason',
        r.disabled_reason && r.disabled_reason.includes('Pipeline X'));
  check('disabled layer → registry.resolve NOT called',
        resolveCalled === 0,
        `resolve was called ${resolveCalled} times`);
}

// ---------------------------------------------------------------------------
group('enabled layer that resolves to array (happy path)');
{
  let resolveCalled = 0;
  const reg = {
    getLayerEntry: () => ({ disabled: false }),
    resolve: () => { resolveCalled++; return Promise.resolve([
      { sample_id: 'CGA_001', F_ROH: 0.05 },
      { sample_id: 'CGA_002', F_ROH: 0.07 },
    ]); },
  };
  const r = await probeModeB(reg, 'per_sample_stats', {}, {});
  check('enabled → resolve called',          resolveCalled === 1);
  check('enabled → ok=true',                 r.ok === true);
  check('enabled → n=2',                     r.n === 2);
  check('enabled → rows length 2',           Array.isArray(r.rows) && r.rows.length === 2);
  check('enabled → sample_keys includes F_ROH',
        Array.isArray(r.sample_keys) && r.sample_keys.includes('F_ROH'));
}

// ---------------------------------------------------------------------------
group('enabled layer that resolves to non-array (stub-payload)');
{
  const reg = {
    getLayerEntry: () => ({ disabled: false }),
    resolve: () => Promise.resolve({ cohort_summary: { n: 0 } }),
  };
  const r = await probeModeB(reg, 'per_sample_stats', {}, {});
  check('stub object → ok=false',            r.ok === false);
  check('stub object → reason=stub-payload', r.reason === 'stub-payload');
  check('stub object → payload preserved',   r.payload && r.payload.cohort_summary);
}

// ---------------------------------------------------------------------------
group('enabled layer that resolves to null (empty-result)');
{
  const reg = {
    getLayerEntry: () => ({ disabled: false }),
    resolve: () => Promise.resolve(null),
  };
  const r = await probeModeB(reg, 'per_sample_stats', {}, {});
  check('null payload → ok=false',           r.ok === false);
  check('null payload → reason=empty-result',r.reason === 'empty-result');
}

// ---------------------------------------------------------------------------
group('enabled layer where resolve throws');
{
  const reg = {
    getLayerEntry: () => ({ disabled: false }),
    resolve: () => Promise.reject(new Error('HTTP 500 server died')),
  };
  const r = await probeModeB(reg, 'per_sample_stats', {}, {});
  check('throw → ok=false',                  r.ok === false);
  check('throw → reason=resolve-threw',      r.reason === 'resolve-threw');
  check('throw → carries error message',
        r.error && r.error.includes('HTTP 500'));
}

// ---------------------------------------------------------------------------
group('legacy registry (no getLayerEntry method)');
// Verifies graceful fallback — older registry implementations that haven't
// been upgraded should still work. The probe just skips the disabled check
// and goes straight to resolve.
{
  let resolveCalled = 0;
  const reg = {
    // NO getLayerEntry here
    resolve: () => { resolveCalled++; return Promise.resolve([{ x: 1 }]); },
  };
  const r = await probeModeB(reg, 'foo', {}, {});
  check('legacy registry → resolve called',  resolveCalled === 1);
  check('legacy registry → ok=true',         r.ok === true);
}

// ---------------------------------------------------------------------------
group('opts.extractRows projects rows out of object payload');
{
  const reg = {
    getLayerEntry: () => ({ disabled: false }),
    resolve: () => Promise.resolve({ windows: [{ z: 1 }, { z: 2 }, { z: 3 }] }),
  };
  const r = await probeModeB(reg, 'scrubber_main', {}, {
    extractRows: (p) => p && p.windows,
  });
  check('extractRows → ok=true',             r.ok === true);
  check('extractRows → n=3',                 r.n === 3);
  check('extractRows → payload kept whole',  r.payload && r.payload.windows.length === 3);
}

// ---------------------------------------------------------------------------
console.log('\n=================');
console.log(`pass: ${pass}   fail: ${fail}`);
console.log('=================');
process.exit(fail > 0 ? 1 : 0);
