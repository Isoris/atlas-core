// tests/test_tree_layer_registry.mjs
// Smoke tests for core/tree_layer_registry.js.
// Run: node tests/test_tree_layer_registry.mjs
//
// Tree-layers live inside per-atlas layers.registry.json entries.
// These tests exercise the validator + the typed-path resolver against
// the SPEC_tree_layers_v1 §3 worked example (BP_ATLAS results tree).

import {
  validateTreeLayer,
  resolveTreePath,
  walkTreePaths,
  InvalidTreePathError,
} from '../core/tree_layer_registry.js';

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
// Synthetic tree-layer — mirrors SPEC §3 BP_ATLAS worked example.
// ---------------------------------------------------------------------
const bpTree = {
  layer_id: 'bp_atlas_results_v1',
  kind: 'tree',
  label: 'BP_ATLAS — full results tree',
  version: 1,
  cohort_id: 'f1_hybrid_cga_cma',
  reference_id: 'fClaHyb_Gar_LG',
  produced_by: 'bp_atlas_pipeline',
  root: 'data/breakpoints/results_bpatlas/',
  tree: {
    '02_paf_passA': {
      kind: 'dir',
      children_pattern: '*.paf',
      leaf_kind: 'paf',
      label: 'Pass A wfmash PAFs (per pair)',
    },
    '02_paf_passB': {
      kind: 'dir',
      children_pattern: '*.paf',
      leaf_kind: 'paf',
      label: 'Pass B wfmash PAFs (per pair)',
    },
    '03_breakpoints': {
      kind: 'dir',
      children: {
        anchor_Cgar: { kind: 'dir', children: { 'breakpoint_zones.tsv': { kind: 'leaf', leaf_kind: 'tsv' } } },
        anchor_Cmac: { kind: 'dir', children: { 'breakpoint_zones.tsv': { kind: 'leaf', leaf_kind: 'tsv' } } },
        reciprocity: { kind: 'dir', children: { 'reciprocity_table.tsv': { kind: 'leaf', leaf_kind: 'tsv' } } },
        'breakpoints_raw.tsv': { kind: 'leaf', leaf_kind: 'tsv' },
      },
    },
    '05_atlas_data': {
      kind: 'dir',
      children: {
        'atlas_data.json':     { kind: 'leaf', leaf_kind: 'json' },
        'atlas_paf_arcs.json': { kind: 'leaf', leaf_kind: 'json' },
      },
    },
    '06_joint': {
      kind: 'dir',
      children: { 'joint_candidates.tsv': { kind: 'leaf', leaf_kind: 'tsv' } },
    },
  },
};

// Cross-validation inputs.
const cohortsRegistry  = { cohorts: [{ cohort_id: 'f1_hybrid_cga_cma' }, { cohort_id: 'cross_species_18sp_compendium' }] };
const workflowsRegistry = { workflows: [{ workflow_id: 'bp_atlas_pipeline' }, { workflow_id: 'gene_order_consolidation' }] };

// ---------------------------------------------------------------------
console.log('\n=== validate (clean tree-layer) ===');
const errs = validateTreeLayer(bpTree, { cohortsRegistry, workflowsRegistry });
eq(errs, [], 'clean validation returns no errors');

// ---------------------------------------------------------------------
// Per-rule break tests.
function breakOne(mutator) {
  const r = JSON.parse(JSON.stringify(bpTree));
  mutator(r);
  return validateTreeLayer(r, { cohortsRegistry, workflowsRegistry });
}

console.log('\n=== validate — per-rule break tests ===');
const e_kind = breakOne(r => { r.kind = 'scalar'; });
ok(e_kind.some(e => e.includes("kind must be 'tree'")),       'flags wrong kind');

const e_slug = breakOne(r => { r.layer_id = 'BAD-ID'; });
ok(e_slug.some(e => e.includes('BAD-ID')),                   'flags bad layer_id slug');

const e_cohort = breakOne(r => { r.cohort_id = 'nonexistent_cohort'; });
ok(e_cohort.some(e => e.includes('nonexistent_cohort')),     'flags unknown cohort_id');

const e_wf = breakOne(r => { r.produced_by = 'nope_workflow'; });
ok(e_wf.some(e => e.includes('nope_workflow')),              'flags unknown produced_by workflow_id');

const e_leaf = breakOne(r => { r.tree['05_atlas_data'].children['atlas_data.json'].leaf_kind = 'parquet'; });
ok(e_leaf.some(e => e.includes('unknown leaf_kind')),        'flags unknown leaf_kind');

const e_both = breakOne(r => {
  r.tree['02_paf_passA'].children = { 'pinned.paf': { kind: 'leaf', leaf_kind: 'paf' } };
});
ok(e_both.some(e => e.includes('BOTH children and children_pattern')),
                                                              'flags dir with both children + pattern');

const e_neither = breakOne(r => {
  r.tree['neither'] = { kind: 'dir', label: 'empty' };
});
ok(e_neither.some(e => e.includes('neither children nor children_pattern')),
                                                              'flags dir with neither');

const e_empty = breakOne(r => {
  r.tree['06_joint'].children = {};
});
ok(e_empty.some(e => e.includes('empty children')),          'flags dir with empty children');

const e_ref = breakOne(r => {
  r.tree['nested'] = { kind: 'tree_ref', ref_layer: 'other_v1' };
});
ok(e_ref.some(e => e.includes("not allowed in tree_layer v1")), 'flags tree_ref (SPEC §4 open question)');

const e_unknown = breakOne(r => {
  r.tree['weird'] = { kind: 'pipe', leaf_kind: 'tsv' };
});
ok(e_unknown.some(e => e.includes('unknown kind')),          'flags unknown node kind');

const e_junk = validateTreeLayer(null);
eq(e_junk, ['tree-layer: payload is not an object'],         'null payload → 1 error');

// ---------------------------------------------------------------------
console.log('\n=== resolveTreePath — explicit children ===');
// Explicit-children leaf
const r1 = resolveTreePath(bpTree, '03_breakpoints.reciprocity.reciprocity_table.tsv');
eq({ kind: r1.kind, absPath: r1.absPath, leaf_kind: r1.leaf_kind },
   { kind: 'leaf',
     absPath: 'data/breakpoints/results_bpatlas/03_breakpoints/reciprocity/reciprocity_table.tsv',
     leaf_kind: 'tsv' },
   'resolves explicit leaf path');

// Leaf nested directly under a dir's `children` (no .children indirection on this path)
const r2 = resolveTreePath(bpTree, '05_atlas_data.atlas_data.json');
eq({ kind: r2.kind, absPath: r2.absPath, leaf_kind: r2.leaf_kind },
   { kind: 'leaf',
     absPath: 'data/breakpoints/results_bpatlas/05_atlas_data/atlas_data.json',
     leaf_kind: 'json' },
   'resolves nested .json leaf');

// Leaf directly under a top-level dir's children (no sub-dir)
const r3 = resolveTreePath(bpTree, '06_joint.joint_candidates.tsv');
eq({ kind: r3.kind, absPath: r3.absPath, leaf_kind: r3.leaf_kind },
   { kind: 'leaf',
     absPath: 'data/breakpoints/results_bpatlas/06_joint/joint_candidates.tsv',
     leaf_kind: 'tsv' },
   'resolves single-level leaf');

// Dot-in-name child (breakpoints_raw.tsv) — the resolver uses dot-segmentation
// so this name appears as TWO segments. SPEC §6 doesn't address dots in
// child names; current behaviour is to require children to be addressable
// segment-by-segment. The test documents the behaviour rather than the
// intended UX.
const r4 = resolveTreePath(bpTree, '03_breakpoints.breakpoints_raw.tsv');
eq({ kind: r4.kind, absPath: r4.absPath, leaf_kind: r4.leaf_kind },
   { kind: 'leaf',
     absPath: 'data/breakpoints/results_bpatlas/03_breakpoints/breakpoints_raw.tsv',
     leaf_kind: 'tsv' },
   'resolves dot-in-name leaf (treated as multi-segment)');

// ---------------------------------------------------------------------
console.log('\n=== resolveTreePath — pattern dirs ===');
// Pattern dir without child segment → returns dir metadata
const r5 = resolveTreePath(bpTree, '02_paf_passA');
ok(r5.kind === 'dir' && r5.children_pattern === '*.paf' && r5.leaf_kind === 'paf',
   'pattern dir without child segment returns dir + pattern metadata');

// Pattern dir + child filename → returns pattern_match with absPath
const r6 = resolveTreePath(bpTree, '02_paf_passA.Cgar_h1_vs_Cmac_h1.paf');
eq({ kind: r6.kind, leaf_kind: r6.leaf_kind, absPath: r6.absPath },
   { kind: 'pattern_match', leaf_kind: 'paf',
     absPath: 'data/breakpoints/results_bpatlas/02_paf_passA/Cgar_h1_vs_Cmac_h1.paf' },
   'pattern dir + child returns pattern_match');

// Real-world filenames contain dots; the resolver joins remaining segments
// into the filename rather than rejecting them. Verifies the SPEC §6 example
// '02_paf_passA.Cgar_h1_vs_Cmac_h1.paf' isn't a special case.
const r6_long = resolveTreePath(bpTree, '02_paf_passA.subdir_v2.something.paf');
eq({ kind: r6_long.kind, leaf_kind: r6_long.leaf_kind, absPath: r6_long.absPath },
   { kind: 'pattern_match', leaf_kind: 'paf',
     absPath: 'data/breakpoints/results_bpatlas/02_paf_passA/subdir_v2.something.paf' },
   'pattern dir joins multi-segment remainders into one filename');

// ---------------------------------------------------------------------
console.log('\n=== resolveTreePath — metadata + invalid paths ===');
const meta = resolveTreePath(bpTree, '');
eq(meta.kind, 'metadata',                                    'empty treePath returns metadata');
const metaNull = resolveTreePath(bpTree, null);
eq(metaNull.kind, 'metadata',                                'null treePath returns metadata');

let threw2 = null;
try { resolveTreePath(bpTree, '03_breakpoints.nope'); }
catch (e) { threw2 = e; }
ok(threw2 instanceof InvalidTreePathError,                   'unknown segment throws InvalidTreePathError');

let threw3 = null;
try { resolveTreePath(bpTree, '06_joint.joint_candidates.tsv.extra'); }
catch (e) { threw3 = e; }
ok(threw3 instanceof InvalidTreePathError,                   'descending past a leaf throws InvalidTreePathError');

let threw4 = null;
try { resolveTreePath({}, 'anything'); }
catch (e) { threw4 = e; }
ok(threw4 instanceof InvalidTreePathError,                   'non-tree layerEntry throws');

// Sub-tree return (landing on a dir's children object via a known segment chain).
const subtree = resolveTreePath(bpTree, '03_breakpoints.reciprocity');
eq(subtree.kind, 'dir',                                       'resolving to an explicit-children dir returns dir');

// ---------------------------------------------------------------------
console.log('\n=== walkTreePaths ===');
const paths = walkTreePaths(bpTree);
const pathStrs = paths.map(p => p.path).sort();
// Expected leaves + pattern dirs:
//   02_paf_passA  (pattern)
//   02_paf_passB  (pattern)
//   03_breakpoints.anchor_Cgar.breakpoint_zones.tsv  (leaf)
//   03_breakpoints.anchor_Cmac.breakpoint_zones.tsv  (leaf)
//   03_breakpoints.reciprocity.reciprocity_table.tsv (leaf)
//   03_breakpoints.breakpoints_raw.tsv               (leaf)
//   05_atlas_data.atlas_data.json                    (leaf)
//   05_atlas_data.atlas_paf_arcs.json                (leaf)
//   06_joint.joint_candidates.tsv                    (leaf)
ok(pathStrs.length === 9,                                    `walkTreePaths yields 9 entries (got ${pathStrs.length})`);
ok(pathStrs.includes('02_paf_passA'),                        'walk includes 02_paf_passA pattern-dir');
ok(pathStrs.includes('06_joint.joint_candidates.tsv'),       'walk includes 06_joint leaf');

// ---------------------------------------------------------------------
console.log('\n=== validate (without cross-ref inputs — schema-only) ===');
const noXref = validateTreeLayer(bpTree, {});
eq(noXref, [], 'schema-only validation passes');

// ---------------------------------------------------------------------
console.log(`\n${_pass} passed, ${_fail} failed.`);
if (_fail > 0) process.exit(1);
