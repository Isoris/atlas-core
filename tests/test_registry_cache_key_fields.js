// Smoke test for Registry._buildCacheKey when fields varies.
// Verifies that different field subsets produce different cache keys
// (so a 5-column read isn't served from a 23-column cache entry),
// and that field order doesn't matter.
//
// Run from repo root:
//   node atlas-core/tests/test_registry_cache_key_fields.js

import { Registry } from '../core/registry_core.js';

function eq(a, b, msg) {
  if (a !== b) {
    console.error(`FAIL: ${msg}`);
    console.error(`  expected: ${b}`);
    console.error(`  got:      ${a}`);
    process.exit(1);
  } else {
    console.log(`  ok: ${msg}`);
  }
}

function neq(a, b, msg) {
  if (a === b) {
    console.error(`FAIL: ${msg}`);
    console.error(`  both values are: ${a}`);
    process.exit(1);
  } else {
    console.log(`  ok: ${msg} (${a} !== ${b})`);
  }
}

// Minimal AtlasState stand-in (registry only reads templateFill state).
const fakeState = {
  shared: {},
  inv: {},
  emit() {},
  subscribe() { return () => {}; },
};

const registry = new Registry({ atlasState: fakeState });

// Register a synthetic atlas with one tsv layer that supports fields.
// Note: register_atlas expects the configs to mirror the on-disk
// {layers: {...}} wrapping (configs.layers.layers).
registry.register_atlas('test', {
  layers: {
    layers: {
      rel: {
        tier: 'warm',
        source: 'file',
        path: 'data/relatedness/{run_id}/relatedness.tsv',
        format: 'tsv',
        fields: null
      }
    }
  }
});

console.log('cache-key derivation — fields are part of the key:');
{
  const entry = registry._lookup('rel').entry;

  const k1 = registry._buildCacheKey('rel', entry, { run_id: 'A' });
  const k2 = registry._buildCacheKey('rel', entry,
    { run_id: 'A', fields: ['a', 'b', 'theta'] });
  const k3 = registry._buildCacheKey('rel', entry,
    { run_id: 'A', fields: ['a', 'b', 'theta', 'IBS0'] });

  console.log(`    k1 (no fields):    ${k1}`);
  console.log(`    k2 (3 fields):     ${k2}`);
  console.log(`    k3 (4 fields):     ${k3}`);

  neq(k1, k2, 'no-fields and 3-fields use different cache keys');
  neq(k2, k3, '3-fields and 4-fields use different cache keys');
}

console.log('cache-key derivation — fields order is normalised:');
{
  const entry = registry._lookup('rel').entry;
  const k_ab = registry._buildCacheKey('rel', entry,
    { run_id: 'A', fields: ['a', 'b'] });
  const k_ba = registry._buildCacheKey('rel', entry,
    { run_id: 'A', fields: ['b', 'a'] });
  eq(k_ab, k_ba, "['a','b'] and ['b','a'] hit the same cache entry");
}

console.log('cache-key derivation — entry.fields default vs args.fields override:');
{
  // Re-register with a layer-level default
  registry.register_atlas('test2', {
    layers: {
      layers: {
        rel2: {
          tier: 'warm',
          source: 'file',
          path: 'data/r2.tsv',
          format: 'tsv',
          fields: ['a', 'b', 'theta']
        }
      }
    }
  });
  const entry = registry._lookup('rel2').entry;

  const k_default = registry._buildCacheKey('rel2', entry, {});
  const k_override = registry._buildCacheKey('rel2', entry,
    { fields: ['a', 'b', 'theta', 'IBS0'] });
  const k_explicit_same = registry._buildCacheKey('rel2', entry,
    { fields: ['a', 'b', 'theta'] });

  console.log(`    k_default:        ${k_default}`);
  console.log(`    k_override:       ${k_override}`);
  console.log(`    k_explicit_same:  ${k_explicit_same}`);

  neq(k_default, k_override, 'override produces a different cache key');
  eq(k_default, k_explicit_same,
    'explicit args.fields matching layer default produces the same key');
}

console.log('cache-key derivation — empty args.fields falls back to layer default:');
{
  // _resolveFields treats args.fields=[] as "no per-call override"
  // and falls back to entry.fields. Same cache key as default.
  registry.register_atlas('test3', {
    layers: {
      layers: {
        rel3: {
          tier: 'warm',
          source: 'file',
          path: 'data/r3.tsv',
          format: 'tsv',
          fields: ['a', 'b']
        }
      }
    }
  });
  const entry = registry._lookup('rel3').entry;
  const k_default = registry._buildCacheKey('rel3', entry, {});
  const k_empty   = registry._buildCacheKey('rel3', entry, { fields: [] });
  eq(k_default, k_empty, 'empty args.fields treated as "no override"');
}

console.log('\nAll cache-key tests passed.');
