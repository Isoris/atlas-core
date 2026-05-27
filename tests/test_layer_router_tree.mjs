// tests/test_layer_router_tree.mjs
// Smoke tests for LayerRouter.readTreePath — the tree-layer extension
// that consumes core/tree_layer_registry.js's typed-path resolution.
// Run: node tests/test_layer_router_tree.mjs

import { LayerRouter } from '../core/layer_router.js';

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
// Tree-layer (small subset of the SPEC §3 BP_ATLAS worked example).
// ---------------------------------------------------------------------
const bpTree = {
  layer_id: 'bp_atlas_results_v1',
  kind: 'tree',
  label: 'BP_ATLAS — results',
  root: 'data/breakpoints/results_bpatlas/',
  tree: {
    '02_paf_passA': {
      kind: 'dir',
      children_pattern: '*.paf',
      leaf_kind: 'paf',
    },
    '03_breakpoints': {
      kind: 'dir',
      children: {
        reciprocity: {
          kind: 'dir',
          children: { 'reciprocity_table.tsv': { kind: 'leaf', leaf_kind: 'tsv' } },
        },
      },
    },
    '05_atlas_data': {
      kind: 'dir',
      children: {
        'atlas_data.json':     { kind: 'leaf', leaf_kind: 'json' },
        'atlas_paf_arcs.jsonl': { kind: 'leaf', leaf_kind: 'jsonl' },
      },
    },
    '07_unsupported': {
      kind: 'dir',
      children: { 'genome.fasta': { kind: 'leaf', leaf_kind: 'fasta' } },
    },
    '08_binary': {
      kind: 'dir',
      children: { 'index.bin': { kind: 'leaf', leaf_kind: 'bin' } },
    },
  },
};

// ---------------------------------------------------------------------
// Mock fetch — serves tiny content per URL so we can verify the router
// picked the right format + abs path.
// ---------------------------------------------------------------------
const FAKE_FILES = {
  'data/breakpoints/results_bpatlas/03_breakpoints/reciprocity/reciprocity_table.tsv':
    'pair\trecip_frac\nA-B\t0.92\nC-D\t0.71\n',
  'data/breakpoints/results_bpatlas/05_atlas_data/atlas_data.json':
    JSON.stringify({ version: 1, n_zones: 28 }),
  'data/breakpoints/results_bpatlas/05_atlas_data/atlas_paf_arcs.jsonl':
    '{"a":1}\n{"a":2}\n{"a":3}\n',
  'data/breakpoints/results_bpatlas/02_paf_passA/Cgar_h1_vs_Cmac_h1.paf':
    'q1\t100\t0\t100\t+\tt1\t200\t50\t150\t98\t100\t60\tNM:i:2\n',
  'data/breakpoints/results_bpatlas/08_binary/index.bin':
    null,   // binary stub — see _fetchBinary below
};
const _BIN_BYTES = new Uint8Array([0xde, 0xad, 0xbe, 0xef]);

let _callLog = [];
globalThis.fetch = async (url) => {
  _callLog.push(url);
  // Strip leading / and the optional /file/ prefix (real atlas-server
  // mounts sandboxed reads under /file/<path>; the FAKE_FILES keys are
  // sans-prefix so the urlPrefix-option test works).
  let path = url.replace(/^\/+/, '');
  if (path.startsWith('file/')) path = path.slice(5);
  if (!(path in FAKE_FILES)) {
    return { ok: false, status: 404, text: async () => '', json: async () => ({}),
             arrayBuffer: async () => new ArrayBuffer(0) };
  }
  const content = FAKE_FILES[path];
  return {
    ok: true,
    status: 200,
    text:        async () => content == null ? '' : String(content),
    json:        async () => JSON.parse(content),
    arrayBuffer: async () => _BIN_BYTES.buffer,
  };
};

const router = new LayerRouter();

// ---------------------------------------------------------------------
console.log('\n=== readTreePath — TSV leaf (3-level path) ===');
const tsv = await router.readTreePath(bpTree, '03_breakpoints.reciprocity.reciprocity_table.tsv');
ok(Array.isArray(tsv) && tsv.length === 2,                                  'TSV parses into 2 rows');
eq(tsv[0],     { pair: 'A-B', recip_frac: 0.92 },                            'first row parsed + numeric coerced');
eq(tsv[1].pair, 'C-D',                                                       'second row pair col');
ok(_callLog.some(u => u.endsWith('reciprocity/reciprocity_table.tsv')),     'fetched the right URL');

// ---------------------------------------------------------------------
console.log('\n=== readTreePath — JSON leaf ===');
const j = await router.readTreePath(bpTree, '05_atlas_data.atlas_data.json');
eq(j, { version: 1, n_zones: 28 },                                           'JSON leaf parsed');

// ---------------------------------------------------------------------
console.log('\n=== readTreePath — JSONL leaf (returns raw text per SPEC §5) ===');
const jl = await router.readTreePath(bpTree, '05_atlas_data.atlas_paf_arcs.jsonl');
ok(typeof jl === 'string' && jl.includes('{"a":2}'),
   'JSONL leaf returns raw text (caller does line-by-line JSON.parse)');

// ---------------------------------------------------------------------
console.log('\n=== readTreePath — PAF leaf via pattern-dir (headerless TSV) ===');
const paf = await router.readTreePath(bpTree, '02_paf_passA.Cgar_h1_vs_Cmac_h1.paf');
ok(Array.isArray(paf) && paf.length === 1,                                  'PAF pattern-match parses 1 row');
// Headerless: PAF columns surface as col_0..col_12; caller maps to spec names
ok(paf[0].col_0 === 'q1' && paf[0].col_5 === 't1',
   'PAF cols synthesized as col_N (caller maps to PAF spec names)');
ok(paf[0].col_1 === 100 && paf[0].col_10 === 100,                          'numeric cols coerced');
ok(_callLog.some(u => u.endsWith('02_paf_passA/Cgar_h1_vs_Cmac_h1.paf')),   'fetched correct PAF abs path');

// ---------------------------------------------------------------------
console.log('\n=== readTreePath — binary leaf ===');
const bin = await router.readTreePath(bpTree, '08_binary.index.bin');
ok(bin instanceof ArrayBuffer && new Uint8Array(bin).length === 4,           'binary leaf returns ArrayBuffer');

// ---------------------------------------------------------------------
console.log('\n=== readTreePath — metadata (no I/O for null/empty path) ===');
_callLog = [];
const meta = await router.readTreePath(bpTree, '');
ok(meta.kind === 'metadata' && meta.node === bpTree.tree,                   'empty path → metadata, no fetch');
ok(_callLog.length === 0,                                                    'no fetch happened for metadata');

// ---------------------------------------------------------------------
console.log('\n=== readTreePath — subtree returns dir/subtree without I/O ===');
_callLog = [];
const sub = await router.readTreePath(bpTree, '03_breakpoints.reciprocity');
ok(sub.kind === 'dir' && sub.absPath.endsWith('reciprocity'),                'sub-path to dir returns dir metadata');
ok(_callLog.length === 0,                                                    'no fetch for dir resolution');

// ---------------------------------------------------------------------
console.log('\n=== readTreePath — pattern-dir without child segment returns dir ===');
_callLog = [];
const patDir = await router.readTreePath(bpTree, '02_paf_passA');
ok(patDir.kind === 'dir' && patDir.children_pattern === '*.paf',
   'pattern-dir without child segment returns dir + pattern metadata');
ok(_callLog.length === 0,                                                    'no fetch for pattern-dir metadata');

// ---------------------------------------------------------------------
console.log('\n=== readTreePath — unsupported leaf_kind throws v1-clear error ===');
let threw = null;
try { await router.readTreePath(bpTree, '07_unsupported.genome.fasta'); }
catch (e) { threw = e; }
ok(threw && /not supported in v1/.test(threw.message),                       'fasta throws v1 not-supported error');
ok(threw && /SPEC §12/.test(threw.message),                                  'error message references SPEC §12');

// ---------------------------------------------------------------------
console.log('\n=== readTreePath — urlPrefix option (atlas-server /file/ mount) ===');
_callLog = [];
await router.readTreePath(bpTree, '05_atlas_data.atlas_data.json',
                          { urlPrefix: '/file' });
ok(_callLog[_callLog.length - 1].startsWith('/file/data/breakpoints/'),     'urlPrefix prepended to abs path');

// ---------------------------------------------------------------------
console.log('\n=== readTreePath — TSV fields allowlist forwarded ===');
_callLog = [];
const subset = await router.readTreePath(bpTree,
  '03_breakpoints.reciprocity.reciprocity_table.tsv',
  { fields: ['pair'] });
ok(subset.length === 2 && !('recip_frac' in subset[0]),
   'fields allowlist drops non-listed columns');
ok('pair' in subset[0],                                                      'allowed column kept');

// ---------------------------------------------------------------------
console.log(`\n${_pass} passed, ${_fail} failed.`);
if (_fail > 0) process.exit(1);
