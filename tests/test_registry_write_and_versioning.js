// tests/test_registry_write_and_versioning.js
// =====================================================================
// Tests for the registry v2 additions in this session:
//   - Registry.write() public method (writable: true contract)
//   - persist hook on operation source (fire-and-forget after resolve)
//   - version_id requirement on per-candidate file layers (no fallback)
//   - content-addressed cache paths (op_id + stableHashHex(args))
//   - stableHashHex / stableStringify determinism
//
// Run with: node tests/test_registry_write_and_versioning.js
// All assertions print "  ok: ..." on pass, the script exits 1 on first
// failure (uncaught throw).
// =====================================================================

import { Registry, stableHashHex, stableStringify, templateFill }
  from '../core/registry_core.js';

let assertions = 0;
function ok(cond, msg) {
  if (!cond) {
    console.error('FAIL:', msg);
    process.exit(1);
  }
  console.log('  ok:', msg);
  assertions++;
}

function throws(fn, pattern, msg) {
  try {
    const r = fn();
    if (r && typeof r.then === 'function') {
      // promise — caller should use throwsAsync
      throw new Error('throws() received a Promise; use throwsAsync');
    }
    console.error('FAIL:', msg, '— did not throw');
    process.exit(1);
  } catch (e) {
    if (e.message === 'throws() received a Promise; use throwsAsync') {
      throw e;
    }
    if (pattern && !pattern.test(e.message)) {
      console.error('FAIL:', msg, '— wrong error:', e.message);
      process.exit(1);
    }
    console.log('  ok:', msg);
    assertions++;
  }
}

async function throwsAsync(fn, pattern, msg) {
  try {
    await fn();
    console.error('FAIL:', msg, '— did not throw');
    process.exit(1);
  } catch (e) {
    if (pattern && !pattern.test(e.message)) {
      console.error('FAIL:', msg, '— wrong error:', e.message);
      process.exit(1);
    }
    console.log('  ok:', msg);
    assertions++;
  }
}

// ====================================================================
// Group 1 — stableHashHex / stableStringify determinism
// ====================================================================
console.log('\nstableStringify — determinism:');
{
  const a = { x: 1, y: { b: 2, a: 3 } };
  const b = { y: { a: 3, b: 2 }, x: 1 };
  ok(stableStringify(a) === stableStringify(b),
     'objects with same content but different key order serialise identically');

  ok(stableStringify({ a: [3, 1, 2] }) === '{"a":[3,1,2]}',
     'arrays preserve positional order (semantic; not sorted)');

  ok(stableStringify(null) === 'null',  'null serialises to "null"');
  ok(stableStringify(42)   === '42',    'numbers stringify');
  ok(stableStringify("hi") === '"hi"',  'strings get quotes');
}

console.log('\nstableHashHex — determinism + collision avoidance:');
{
  const h1 = stableHashHex({ chrom: 'LG28', win: 50000 });
  const h2 = stableHashHex({ win: 50000, chrom: 'LG28' });
  ok(h1 === h2, 'same content, different key order → same hash');
  ok(/^[0-9a-f]{8}$/.test(h1), 'hash is 8 hex chars');

  const h3 = stableHashHex({ chrom: 'LG28', win: 50001 });
  ok(h1 !== h3, 'different value → different hash');

  const h4 = stableHashHex({ chrom: 'LG12', win: 50000 });
  ok(h1 !== h4, 'different chrom → different hash');
}

// ====================================================================
// Group 2 — Registry.write contract (without a real server)
// ====================================================================
console.log('\nRegistry.write — pre-flight checks (no HTTP):');
{
  const reg = new Registry({ atlasState: { shared: {} } });
  // Register a fake atlas with a writable file layer and a non-writable one
  reg.register_atlas('test', {
    layers: { layers: {
      candidate_lineage: {
        tier: 'warm',
        source: 'file',
        path: 'data/candidates/{candidate_id}/lineage.json',
        writable: true
      },
      candidate_boundaries: {
        tier: 'warm',
        source: 'file',
        path: 'data/candidates/{candidate_id}/{version_id}/boundaries_refined.json',
        writable: true
      },
      readonly_layer: {
        tier: 'warm',
        source: 'file',
        path: 'data/some/path.json'
        // writable not set
      },
      operation_layer: {
        tier: 'cold',
        source: 'operation',
        operation: 'fake_op',
        writable: true   // even if marked, source!=file should reject
      }
    } }
  });

  await throwsAsync(
    () => reg.write('does_not_exist', { x: 1 }, { foo: 1 }),
    /unknown layer/,
    'unknown layer key throws');

  await throwsAsync(
    () => reg.write('readonly_layer', {}, { foo: 1 }),
    /not writable/,
    'layer without writable: true throws "not writable"');

  await throwsAsync(
    () => reg.write('operation_layer', { x: 1 }, { foo: 1 }),
    /Only source='file'/,
    'operation-source layer rejected even with writable: true');

  await throwsAsync(
    () => reg.write('candidate_lineage', { candidate_id: 'foo' }, null),
    /payload is required/,
    'null payload rejected');

  await throwsAsync(
    () => reg.write('candidate_boundaries', { candidate_id: 'foo' }, { boundaries: [] }),
    /version_id/,
    'per-candidate per-version layer requires version_id (no fallback)');

  // Lineage is per-candidate but NOT per-version — should not require version_id
  // (will fail on the HTTP call instead, since no server is running)
  let lineageHttpFailed = false;
  try {
    await reg.write('candidate_lineage', { candidate_id: 'cid_test' }, { hello: 1 });
  } catch (e) {
    lineageHttpFailed = /fetch|ECONNREFUSED|Failed to fetch|Registry\.write/i.test(e.message);
  }
  ok(lineageHttpFailed,
     'lineage write passes pre-flight (no version_id required), fails only on HTTP');
}

// ====================================================================
// Group 3 — version_id requirement on resolve() for per-candidate layers
// ====================================================================
console.log('\nRegistry.resolve — version_id requirement on per-candidate layers:');
{
  const reg = new Registry({ atlasState: { shared: {} } });
  reg.register_atlas('test', {
    layers: { layers: {
      // Per-candidate per-version: requires version_id
      candidate_boundaries: {
        tier: 'warm',
        source: 'file',
        path: 'data/candidates/{candidate_id}/{version_id}/boundaries_refined.json'
      },
      // Per-candidate but NOT per-version (lineage): does not require version_id
      candidate_lineage: {
        tier: 'warm',
        source: 'file',
        path: 'data/candidates/{candidate_id}/lineage.json'
      },
      // Hot-tier sync path test: same template
      candidate_hot: {
        tier: 'hot',
        source: 'file',
        path: 'data/candidates/{candidate_id}/{version_id}/hot.json'
      }
    } }
  });

  await throwsAsync(
    () => reg.resolve('candidate_boundaries', { candidate_id: 'cid_x' }),
    /version_id/,
    'resolve() throws clear version_id error before fetch');

  // Hot tier short-circuit returns sync; verify it also throws on miss
  // (the missing-version error path runs inside _fetchAndCache).
  await throwsAsync(
    () => Promise.resolve(reg.resolve('candidate_hot', { candidate_id: 'cid_x' })),
    /version_id/,
    'hot-tier resolve also throws on missing version_id');

  // candidate_lineage path has only {candidate_id}, no {version_id} → no
  // version_id check should fire. It will still fail on the actual fetch
  // because no file exists, but that's a different error.
  let lineageErr = '';
  try {
    await reg.resolve('candidate_lineage', { candidate_id: 'cid_x' });
  } catch (e) { lineageErr = e.message; }
  ok(!/version_id/.test(lineageErr),
     'lineage resolve does NOT throw version_id error (only one slot in path)');
}

// ====================================================================
// Group 4 — _buildPersistPath structure
// ====================================================================
console.log('\nRegistry persist path — content_addressed layout:');
{
  const reg = new Registry({ atlasState: { shared: {} } });
  reg.register_atlas('test', {
    layers: { layers: {
      fst_dxy: {
        tier: 'cold',
        source: 'operation',
        operation: 'popstats_groupwise',
        persist: true
      }
    } }
  });
  const layer = reg._layerIndex.get('fst_dxy').entry;
  const p1 = reg._buildPersistPath('fst_dxy', layer, { chrom: 'LG28', start: 1000, end: 2000 });
  ok(p1.startsWith('_cache/server_results/popstats_groupwise/'),
     'content-addressed path uses op_id from layer entry');
  ok(p1.endsWith('.json'),
     'content-addressed path ends in .json');
  const p2 = reg._buildPersistPath('fst_dxy', layer, { start: 1000, end: 2000, chrom: 'LG28' });
  ok(p1 === p2,
     'same args (different order) → same persist path');

  const p3 = reg._buildPersistPath('fst_dxy', layer, { chrom: 'LG12', start: 1000, end: 2000 });
  ok(p1 !== p3,
     'different chrom → different persist path');
}

console.log('\nRegistry persist path — path_template layout (opt-in):');
{
  const reg = new Registry({ atlasState: { shared: {} } });
  reg.register_atlas('test', {
    layers: { layers: {
      custom_persist: {
        tier: 'cold',
        source: 'operation',
        operation: 'foo',
        persist: true,
        cache_layout: 'path_template',
        path: 'data/precomp/{chrom}/foo.json'
      }
    } }
  });
  const layer = reg._layerIndex.get('custom_persist').entry;
  const p = reg._buildPersistPath('custom_persist', layer, { chrom: 'LG28' });
  ok(p === 'data/precomp/LG28/foo.json',
     'path_template layout fills the layer.path with templateFill');
}

// ====================================================================
// Done
// ====================================================================
console.log(`\nAll write/versioning/persist tests passed (${assertions} assertions).`);
