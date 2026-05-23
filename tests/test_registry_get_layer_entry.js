// Smoke test for Registry.getLayerEntry() — the 2026-05-20 public peek API.
// Lets callers inspect a layer's entry (flags like disabled, tier, fields)
// without firing a resolve. Used by core/mode_b_badge.js to short-circuit
// probes on disabled layers (see test_mode_b_badge.js).
//
// Run from repo root:
//   node atlas-core/tests/test_registry_get_layer_entry.js

import { Registry } from '../core/registry_core.js';

let pass = 0, fail = 0;
function check(label, cond, extra) {
  if (cond) { pass++; console.log('  ✓', label); }
  else      { fail++; console.log('  ✗', label, extra ? ' — ' + extra : ''); }
}
function group(name) { console.log('\n--- ' + name + ' ---'); }

const fakeState = {
  shared: {}, atlas: {},
  emit() {}, subscribe() { return () => {}; },
};
const registry = new Registry({ atlasState: fakeState });

registry.register_atlas('test', {
  layers: {
    layers: {
      enabled_layer: {
        tier: 'warm',
        source: 'file',
        path: 'data/enabled.json',
      },
      disabled_layer: {
        tier: 'warm',
        source: 'file',
        path: 'data/disabled.json',
        disabled: true,
        _disabled_reason: 'Pipeline X has not shipped yet.',
      },
    },
  },
});

// -----------------------------------------------------------------------------
group('public getLayerEntry returns the entry');
{
  const e = registry.getLayerEntry('enabled_layer');
  check('enabled_layer entry returned',     e !== null && typeof e === 'object');
  check('enabled_layer entry has tier',     e && e.tier === 'warm');
  check('enabled_layer entry has source',   e && e.source === 'file');
  check('enabled_layer entry NOT disabled', !e || e.disabled !== true);
}

// -----------------------------------------------------------------------------
group('disabled flag surfaces');
{
  const e = registry.getLayerEntry('disabled_layer');
  check('disabled_layer entry returned',    e !== null && typeof e === 'object');
  check('disabled_layer.disabled === true', e && e.disabled === true);
  check('disabled_layer carries _disabled_reason',
        e && typeof e._disabled_reason === 'string'
        && e._disabled_reason.includes('Pipeline X'));
}

// -----------------------------------------------------------------------------
group('unknown key returns null');
{
  check('unknown key → null',               registry.getLayerEntry('nope') === null);
  check('empty string → null',              registry.getLayerEntry('') === null);
}

// -----------------------------------------------------------------------------
group('namespaced key resolution (atlas:key)');
{
  // _lookup splits on ':' and uses the bare key after the colon
  const e = registry.getLayerEntry('test:enabled_layer');
  check('namespaced enabled_layer resolves',
        e !== null && e.source === 'file' && e.path === 'data/enabled.json');
}

// -----------------------------------------------------------------------------
console.log('\n=================');
console.log(`pass: ${pass}   fail: ${fail}`);
console.log('=================');
process.exit(fail > 0 ? 1 : 0);
