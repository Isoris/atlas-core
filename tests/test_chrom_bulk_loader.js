// Smoke test for core/chrom_bulk_loader.js — SPEC
// multichrom_load_orchestrator Slice 2 (bulk JSON loader).
//
// Covers:
//   - _resolveChrom picks payload.chrom over filename, and falls through
//     to the filename pattern when payload is silent
//   - loadChromJsons writes to the registry + populates chromSummary
//   - non-JSON files skipped with reason 'not_json'
//   - parse-error files skipped with reason 'parse_error'
//   - unknown-chrom files skipped with reason 'chrom_unknown'
//   - onProgress fires for every file
//
// Run from repo root:
//   node atlas-core/tests/test_chrom_bulk_loader.js

import { loadChromJsons, _resolveChrom } from '../core/chrom_bulk_loader.js';
import { AtlasState } from '../core/atlas_state.js';

let pass = 0, fail = 0;
function check(label, cond, extra) {
  if (cond) { pass++; console.log('  ✓', label); }
  else      { fail++; console.log('  ✗', label, extra ? ' — ' + extra : ''); }
}
function group(name) { console.log('\n--- ' + name + ' ---'); }

// Minimal File stub — node has no native File. We need .name, .text(),
// and .type — that's all loadChromJsons reaches for.
function mkFile(name, content, type = 'application/json') {
  return {
    name, type,
    text: () => Promise.resolve(content),
  };
}

// Minimal Registry stub — captures set() calls.
function mkRegistry() {
  const writes = [];
  return {
    writes,
    set(key, value, args) { writes.push({ key, args, value }); },
  };
}

// ---------------------------------------------------------------------------
group('_resolveChrom — priority order');
{
  check('payload.chrom wins',
        _resolveChrom({ chrom: 'C_gar_LG07' }, 'random.json') === 'C_gar_LG07');
  check('payload.chromosome wins when .chrom absent',
        _resolveChrom({ chromosome: 'C_gar_LG05' }, 'random.json') === 'C_gar_LG05');
  check('filename C_<species>_LG\\d+ pattern',
        _resolveChrom(null, 'precomp_C_gar_LG28.json') === 'C_gar_LG28');
  check('filename bare LG\\d+ pattern',
        _resolveChrom(null, 'something_LG01_extra.json') === 'LG01');
  check('no payload + no match → null',
        _resolveChrom(null, 'random.json') === null);
}

// ---------------------------------------------------------------------------
group('loadChromJsons — happy path (3 files)');
{
  const state = new AtlasState({});
  const reg = mkRegistry();
  const files = [
    mkFile('C_gar_LG01.json', JSON.stringify({
      chrom: 'C_gar_LG01',
      windows: [{ end_bp: 1000 }, { end_bp: 2000 }],
      samples: ['s1', 's2'],
    })),
    mkFile('C_gar_LG02.json', JSON.stringify({
      chrom: 'C_gar_LG02',
      windows: [{ end_bp: 500 }],
      samples: ['s1'],
    })),
    mkFile('LG28.json', JSON.stringify({
      // no chrom field — should fall through to filename
      windows: [{ end_bp: 3000 }],
      samples: ['s1', 's2', 's3'],
    })),
  ];
  const progressLog = [];
  const result = await loadChromJsons({
    files, registry: reg, atlasState: state,
    onProgress: (p) => progressLog.push(p),
  });
  check('loaded count = 3',  result.loaded === 3);
  check('skipped is empty',  result.skipped.length === 0);
  check('total = 3',         result.total === 3);
  check('registry.set called 3×', reg.writes.length === 3);
  check('first write chrom = C_gar_LG01',
        reg.writes[0].args && reg.writes[0].args.chrom === 'C_gar_LG01');
  check('third write chrom = LG28 (from filename)',
        reg.writes[2].args && reg.writes[2].args.chrom === 'LG28');
  check('chromSummaries populated for LG01',
        state.shared.chromSummaries['C_gar_LG01']
        && state.shared.chromSummaries['C_gar_LG01'].n_windows === 2);
  check('chromSummaries populated for LG28',
        state.shared.chromSummaries['LG28']
        && state.shared.chromSummaries['LG28'].n_samples === 3);
  check('onProgress fired 3×', progressLog.length === 3);
  check('every progress event has loaded count',
        progressLog.every(p => Number.isFinite(p.loaded)));
}

// ---------------------------------------------------------------------------
group('loadChromJsons — error paths');
{
  const state = new AtlasState({});
  const reg = mkRegistry();
  const files = [
    mkFile('readme.txt', 'not JSON', 'text/plain'),                  // not_json
    mkFile('broken.json', '{not valid json'),                        // parse_error
    mkFile('mystery.json', JSON.stringify({ samples: ['x'] })),      // chrom_unknown
    mkFile('C_gar_LG09.json', JSON.stringify({
      chrom: 'C_gar_LG09', windows: [], samples: [],
    })),                                                              // loaded
  ];
  const result = await loadChromJsons({
    files, registry: reg, atlasState: state,
  });
  check('loaded = 1',                 result.loaded === 1);
  check('skipped = 3',                result.skipped.length === 3);
  check('not_json surfaced',
        result.skipped.some(s => s.reason === 'not_json'));
  check('parse_error surfaced',
        result.skipped.some(s => s.reason === 'parse_error'));
  check('chrom_unknown surfaced',
        result.skipped.some(s => s.reason === 'chrom_unknown'));
  check('only the valid file was written',
        reg.writes.length === 1 && reg.writes[0].args.chrom === 'C_gar_LG09');
}

// ---------------------------------------------------------------------------
group('loadChromJsons — empty input');
{
  const r1 = await loadChromJsons({ files: [], registry: mkRegistry(), atlasState: new AtlasState({}) });
  check('empty files → loaded=0, total=0', r1.loaded === 0 && r1.total === 0);
  const r2 = await loadChromJsons({ files: null, registry: mkRegistry(), atlasState: new AtlasState({}) });
  check('null files → loaded=0, total=0', r2.loaded === 0 && r2.total === 0);
}

// ---------------------------------------------------------------------------
console.log('\n=================');
console.log(`pass: ${pass}   fail: ${fail}`);
console.log('=================');
process.exit(fail === 0 ? 0 : 1);
