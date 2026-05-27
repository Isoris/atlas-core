// Smoke test for core/chrom_summary.js — SPEC_multichrom_load_orchestrator
// Slice 1 helpers.
//
// Locks in:
//   - buildChromSummary returns the canonical shape for a populated payload
//   - buildChromSummary is null-tolerant (missing fields → safe zeros)
//   - cross-atlas payload shapes (no envelopes, no candidates) → all-zeros
//     for those fields but still returns the rest
//   - setChromSummary / getChromSummary round-trip through AtlasState
//   - listChromSummaries orders by LG-natural order
//   - 'shared.chromSummaries.changed' event fires with the right payload
//
// Run from repo root:
//   node atlas-core/tests/test_chrom_summary.js

import {
  buildChromSummary, setChromSummary, getChromSummary, listChromSummaries,
} from '../core/chrom_summary.js';
import { AtlasState } from '../core/atlas_state.js';

let pass = 0, fail = 0;
function check(label, cond, extra) {
  if (cond) { pass++; console.log('  ✓', label); }
  else      { fail++; console.log('  ✗', label, extra ? ' — ' + extra : ''); }
}
function group(name) { console.log('\n--- ' + name + ' ---'); }

// ---------------------------------------------------------------------------
group('buildChromSummary — full inversion-shape payload');
{
  const data = {
    chrom: 'C_gar_LG01',
    windows: [
      { center_bp: 50_000,  end_bp: 100_000  },
      { center_bp: 150_000, end_bp: 200_000  },
      { center_bp: 250_000, end_bp: 300_000  },
    ],
    samples: ['s1', 's2', 's3', 's4'],
    envelopes: [{}, {}, {}, {}, {}],
    candidate_tracks: [{}, {}],
    dosage_chunks: { url_template: '/api/x' },
    cusum_theta: [],   // empty array — should NOT show up in layers_present
    _provenance: { data_version: 'v3.2', content_sha256: 'abc' },
  };
  const s = buildChromSummary(data);

  check('chrom = C_gar_LG01',          s.chrom === 'C_gar_LG01');
  check('n_windows = 3',               s.n_windows === 3);
  check('n_samples = 4',               s.n_samples === 4);
  check('chrom_length_bp = 300000',    s.chrom_length_bp === 300_000);
  check('n_l2_envelopes = 5',          s.n_l2_envelopes === 5);
  check('n_candidates = 2',            s.n_candidates === 2);
  check('layers_present sorted',
        Array.isArray(s.layers_present)
        && s.layers_present.includes('dosage_chunks')
        && s.layers_present.includes('envelopes')
        && s.layers_present.includes('candidate_tracks')
        && s.layers_present.includes('samples')
        && s.layers_present.includes('windows'));
  check('empty cusum_theta excluded from layers_present',
        !s.layers_present.includes('cusum_theta'));
  check('_provenance excluded from layers_present',
        !s.layers_present.includes('_provenance'));
  check('data_version surfaced',       s.data_version === 'v3.2');
  check('has_lineage_cache defaults false',  s.has_lineage_cache === false);
  check('has_inheritance_cache defaults false', s.has_inheritance_cache === false);
  check('built_at_ms is a recent timestamp',
        Number.isFinite(s.built_at_ms) && s.built_at_ms > 1_700_000_000_000);
}

// ---------------------------------------------------------------------------
group('buildChromSummary — null + missing data');
{
  const s1 = buildChromSummary(null);
  check('null payload → empty chrom',    s1.chrom === '');
  check('null payload → 0 windows',      s1.n_windows === 0);
  check('null payload → 0 samples',      s1.n_samples === 0);
  check('null payload → 0 envelopes',    s1.n_l2_envelopes === 0);
  check('null payload → 0 candidates',   s1.n_candidates === 0);
  check('null payload → empty layers_present',
        Array.isArray(s1.layers_present) && s1.layers_present.length === 0);
  check('null payload → null data_version', s1.data_version === null);

  const s2 = buildChromSummary({});
  check('{} payload → empty chrom',      s2.chrom === '');
  check('{} payload → 0 windows',        s2.n_windows === 0);
}

// ---------------------------------------------------------------------------
group('buildChromSummary — cross-atlas payload (no inversion blocks)');
{
  // A diversity-atlas-style payload: has windows + samples, no envelopes,
  // no candidates. Should still surface a meaningful summary.
  const data = {
    chrom: 'C_gar_LG07',
    windows: [{ center_bp: 1000, end_bp: 2000 }],
    samples: ['s1'],
    theta_pi_local_pca: [{}, {}, {}],
    n_windows: 1,
    n_samples: 1,
  };
  const s = buildChromSummary(data);
  check('cross-atlas → chrom',                  s.chrom === 'C_gar_LG07');
  check('cross-atlas → n_l2_envelopes = 0',     s.n_l2_envelopes === 0);
  check('cross-atlas → n_candidates = 0',       s.n_candidates === 0);
  check('cross-atlas → theta_pi_local_pca in layers_present',
        s.layers_present.includes('theta_pi_local_pca'));
}

// ---------------------------------------------------------------------------
group('buildChromSummary — chrom override + cache hints');
{
  const data = { windows: [], samples: [] };   // no chrom field
  const s = buildChromSummary(data, {
    chrom: 'C_gar_LG28',
    has_lineage_cache: true,
    has_inheritance_cache: true,
  });
  check('opts.chrom overrides missing field',  s.chrom === 'C_gar_LG28');
  check('opts.has_lineage_cache plumbed',      s.has_lineage_cache === true);
  check('opts.has_inheritance_cache plumbed',  s.has_inheritance_cache === true);
}

// ---------------------------------------------------------------------------
group('AtlasState round-trip via setChromSummary');
{
  const state = new AtlasState({ serverBaseUrl: 'http://localhost:5000' });
  let lastEvent = null;
  state.subscribe('shared.chromSummaries.changed', (ev) => { lastEvent = ev; });

  const summary = buildChromSummary({
    chrom: 'C_gar_LG05', windows: [{ end_bp: 100 }], samples: ['x'],
  });
  state.setChromSummary('C_gar_LG05', summary);

  check('event fired with chrom',          lastEvent && lastEvent.chrom === 'C_gar_LG05');
  check('event carries summary ref',        lastEvent && lastEvent.summary === summary);
  check('getChromSummary returns it back', getChromSummary(state, 'C_gar_LG05') === summary);
  check('getChromSummary unknown → null',  getChromSummary(state, 'C_gar_LG99') === null);

  state.setChromSummary('', summary);  // empty key — should no-op
  check('empty-key setter is a no-op',     Object.keys(state.shared.chromSummaries).length === 1);
}

// ---------------------------------------------------------------------------
group('listChromSummaries — LG-natural order');
{
  const state = new AtlasState({});
  for (const chrom of ['C_gar_LG10', 'C_gar_LG02', 'C_gar_LG01', 'C_gar_LG28']) {
    state.setChromSummary(chrom, buildChromSummary({ chrom }));
  }
  const ordered = listChromSummaries(state);
  check('list length = 4',     ordered.length === 4);
  check('ordered[0] = LG01',   ordered[0] && ordered[0].chrom === 'C_gar_LG01');
  check('ordered[1] = LG02',   ordered[1] && ordered[1].chrom === 'C_gar_LG02');
  check('ordered[2] = LG10',   ordered[2] && ordered[2].chrom === 'C_gar_LG10');
  check('ordered[3] = LG28',   ordered[3] && ordered[3].chrom === 'C_gar_LG28');

  // Non-LG chrom names land after LG entries, lex-sorted.
  state.setChromSummary('mito',  buildChromSummary({ chrom: 'mito' }));
  state.setChromSummary('scaff0', buildChromSummary({ chrom: 'scaff0' }));
  const ordered2 = listChromSummaries(state);
  check('non-LG chroms land after LG entries',
        ordered2[ordered2.length - 1].chrom === 'scaff0'
        && ordered2[ordered2.length - 2].chrom === 'mito');
}

// ---------------------------------------------------------------------------
group('null-tolerance — listChromSummaries / getChromSummary');
{
  check('list on missing state → []',     Array.isArray(listChromSummaries(null)) && listChromSummaries(null).length === 0);
  check('list on empty state → []',       Array.isArray(listChromSummaries({})) && listChromSummaries({}).length === 0);
  check('get on missing state → null',    getChromSummary(null, 'LG01') === null);
  check('get on state w/o slot → null',   getChromSummary({ shared: {} }, 'LG01') === null);
}

// ---------------------------------------------------------------------------
group('AtlasState localStorage persistence round-trip');
{
  // Node test harness — stub localStorage if absent.
  if (typeof globalThis.localStorage === 'undefined') {
    const _store = new Map();
    globalThis.localStorage = {
      getItem: (k) => _store.has(k) ? _store.get(k) : null,
      setItem: (k, v) => _store.set(k, String(v)),
      removeItem: (k) => _store.delete(k),
      clear: () => _store.clear(),
    };
  }
  localStorage.clear();

  // Session A: populate + save.
  const sessionA = new AtlasState({});
  sessionA.setActiveChrom('C_gar_LG07');
  for (const chrom of ['C_gar_LG01', 'C_gar_LG07', 'C_gar_LG28']) {
    sessionA.setChromSummary(chrom, buildChromSummary({
      chrom, windows: [{ end_bp: 1000 }], samples: ['s1', 's2'],
    }));
  }
  sessionA.savePersisted();

  const persisted = JSON.parse(localStorage.getItem('atlas_state_v1'));
  check('persisted payload carries chromSummaries',
        persisted.shared && persisted.shared.chromSummaries
        && Object.keys(persisted.shared.chromSummaries).length === 3);
  check('persisted activeChrom preserved',
        persisted.shared.activeChrom === 'C_gar_LG07');

  // Session B: fresh state, restore from disk.
  const sessionB = new AtlasState({});
  sessionB.loadPersisted();
  check('sessionB restored chromSummaries map',
        sessionB.shared.chromSummaries
        && Object.keys(sessionB.shared.chromSummaries).length === 3);
  check('sessionB restored individual summary',
        sessionB.shared.chromSummaries['C_gar_LG07']
        && sessionB.shared.chromSummaries['C_gar_LG07'].chrom === 'C_gar_LG07');
  check('listChromSummaries reads restored entries',
        listChromSummaries(sessionB).length === 3);

  // Empty cache shouldn't pollute the payload.
  const sessionC = new AtlasState({});
  sessionC.setActiveChrom('C_gar_LG02');
  sessionC.savePersisted();
  const persistedC = JSON.parse(localStorage.getItem('atlas_state_v1'));
  check('empty chromSummaries map is not persisted',
        !persistedC.shared.chromSummaries);

  localStorage.clear();
}

// ---------------------------------------------------------------------------
console.log('\n=================');
console.log(`pass: ${pass}   fail: ${fail}`);
console.log('=================');
process.exit(fail === 0 ? 0 : 1);
