// Smoke test for core/worker_json_parse.js (2026-05-26 worker-offload
// of heavy JSON parses for layers tagged `worker_parse: true`).
//
// Node has no Worker global, so this test exercises the main-thread
// fallback path. The contract:
//   - parseJsonInWorker(text) returns a Promise<any>
//   - resolves to the parsed object when text is valid JSON
//   - rejects when text is invalid
//   - terminateJsonWorker() is a no-op when no worker spun up; safe to
//     call from teardown
//
// Run from repo root:
//   node atlas-core/tests/test_worker_json_parse.js

import { parseJsonInWorker, terminateJsonWorker } from '../core/worker_json_parse.js';

let pass = 0, fail = 0;
function check(label, cond, extra) {
  if (cond) { pass++; console.log('  ✓', label); }
  else      { fail++; console.log('  ✗', label, extra ? ' — ' + extra : ''); }
}
function group(name) { console.log('\n--- ' + name + ' ---'); }

// ---------------------------------------------------------------------------
group('happy path — valid JSON parses correctly');
{
  const text = JSON.stringify({ chrom: 'C_gar_LG01', n_windows: 12, samples: ['a', 'b', 'c'] });
  const r = await parseJsonInWorker(text);
  check('result.chrom = C_gar_LG01',     r && r.chrom === 'C_gar_LG01');
  check('result.n_windows = 12',         r && r.n_windows === 12);
  check('result.samples length = 3',     r && Array.isArray(r.samples) && r.samples.length === 3);
}

// ---------------------------------------------------------------------------
group('arrays + nested objects round-trip');
{
  const payload = {
    windows: [
      { start_bp: 0,     end_bp: 1000, center_bp: 500  },
      { start_bp: 1000,  end_bp: 2000, center_bp: 1500 },
    ],
    tracks: { _z_lambda1: [0.1, 0.2, 0.3], _z_lambda2: [0.0, 0.1, 0.0] },
    samples: ['s1', 's2', 's3'],
  };
  const r = await parseJsonInWorker(JSON.stringify(payload));
  check('windows[0].end_bp preserved',         r.windows[0].end_bp === 1000);
  check('tracks._z_lambda1 array preserved',   Array.isArray(r.tracks._z_lambda1)
                                              && r.tracks._z_lambda1[1] === 0.2);
  check('samples length = 3',                  r.samples.length === 3);
}

// ---------------------------------------------------------------------------
group('invalid JSON rejects with a useful message');
{
  let caught = null;
  try { await parseJsonInWorker('{not valid'); }
  catch (e) { caught = e; }
  check('promise rejected',          caught instanceof Error);
  check('error message non-empty',   caught && typeof caught.message === 'string' && caught.message.length > 0);
}

// ---------------------------------------------------------------------------
group('non-string input rejects (worker path) or throws sync (fallback)');
{
  // In the fallback path (Node, no Worker) JSON.parse(undefined) throws
  // synchronously inside the .resolve() try block, surfacing as a rejected
  // promise. Either way the caller gets a rejection.
  let caught = null;
  try { await parseJsonInWorker(undefined); }
  catch (e) { caught = e; }
  check('undefined input → promise rejects', caught instanceof Error);
}

// ---------------------------------------------------------------------------
group('terminateJsonWorker is safe when no worker spun up');
{
  let threw = false;
  try { terminateJsonWorker(); } catch (_) { threw = true; }
  check('terminate() is a no-op without an active worker', !threw);
  // Subsequent parse still works (helper re-attempts spin-up).
  const r = await parseJsonInWorker('{"ok":true}');
  check('parse still works after terminate', r && r.ok === true);
}

// ---------------------------------------------------------------------------
group('concurrent parses resolve independently');
{
  const a = parseJsonInWorker(JSON.stringify({ tag: 'a', n: 1 }));
  const b = parseJsonInWorker(JSON.stringify({ tag: 'b', n: 2 }));
  const c = parseJsonInWorker(JSON.stringify({ tag: 'c', n: 3 }));
  const [ra, rb, rc] = await Promise.all([a, b, c]);
  check('result a.tag = "a"', ra.tag === 'a');
  check('result b.tag = "b"', rb.tag === 'b');
  check('result c.tag = "c"', rc.tag === 'c');
}

// ---------------------------------------------------------------------------
console.log('\n=================');
console.log(`pass: ${pass}   fail: ${fail}`);
console.log('=================');
process.exit(fail === 0 ? 0 : 1);
