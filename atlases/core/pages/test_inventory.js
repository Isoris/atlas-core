// Smoke tests for the inventory page's pure helpers.
//
// Exercises the four parser / escaper / counter helpers that drive the
// Inventory page's rendering. The page itself is DOM-coupled (mount()
// expects an HTMLElement root + querySelector tree) so a full-mount test
// would require jsdom or a heavier fake-DOM than the sibling page tests
// use. Instead — matching the established convention in
// atlases/relatedness/pages/hub/test_network_data_source.js — we test the
// pure helpers the page exposes, and trust the integration to the
// in-browser smoke at #/core/inventory.
//
// Run from the atlas-core root:
//   node atlases/core/pages/test_inventory.js
//
// Covers:
//   - parseTSV   — header-only, simple rows, missing trailing cells,
//                  trailing newline, single-column, blank lines skipped
//   - parseJSONL — empty input, valid records, malformed line surfaces
//                  as { _error, _line, _raw }, blank lines skipped
//   - esc        — HTML entity escaping for &, <, >, ", '; null / undefined
//                  yield empty string
//   - countRegistryEntries — picks the right dict from pages-shaped /
//                  layers-shaped registries; underscore keys + $schema
//                  excluded; pluralisation correct

import {
  parseTSV,
  parseJSONL,
  esc,
  countRegistryEntries,
} from './inventory.js';

let _failed = 0;
let _passed = 0;

function eq(a, b, msg) {
  if (JSON.stringify(a) !== JSON.stringify(b)) {
    console.error(`FAIL: ${msg}\n  expected: ${JSON.stringify(b)}\n  got:      ${JSON.stringify(a)}`);
    _failed++;
    return;
  }
  _passed++;
  console.log(`  ok: ${msg}`);
}

// ====== parseTSV ========================================================

console.log('parseTSV:');
{
  const r = parseTSV('');
  eq(r, { header: [], rows: [] }, 'empty input → empty header + rows');
}
{
  const r = parseTSV('a\tb\tc\n1\t2\t3\n4\t5\t6');
  eq(r.header, ['a', 'b', 'c'], 'header parsed');
  eq(r.rows.length, 2, 'two data rows');
  eq(r.rows[0], { a: '1', b: '2', c: '3' }, 'first row as dict');
  eq(r.rows[1], { a: '4', b: '5', c: '6' }, 'second row as dict');
}
{
  // Trailing newline does NOT produce a phantom row.
  const r = parseTSV('a\tb\n1\t2\n');
  eq(r.rows.length, 1, 'trailing newline does not add empty row');
}
{
  // Row with missing trailing cell — fewer columns than header.
  const r = parseTSV('a\tb\tc\n1\t2');
  eq(r.rows[0], { a: '1', b: '2', c: '' }, 'missing trailing cell → empty string');
}
{
  // Single-column TSV.
  const r = parseTSV('id\nfoo\nbar');
  eq(r.header, ['id'], 'single-column header');
  eq(r.rows, [{ id: 'foo' }, { id: 'bar' }], 'single-column rows');
}
{
  // Blank lines between rows are dropped.
  const r = parseTSV('a\tb\n1\t2\n\n3\t4');
  eq(r.rows.length, 2, 'blank line between rows is skipped');
}
{
  // CRLF line endings (Windows-edited registry files).
  const r = parseTSV('a\tb\r\n1\t2\r\n3\t4\r\n');
  eq(r.rows, [{ a: '1', b: '2' }, { a: '3', b: '4' }], 'CRLF line endings handled');
}

// ====== parseJSONL ======================================================

console.log('\nparseJSONL:');
{
  eq(parseJSONL(''), [], 'empty input → empty array');
}
{
  const rows = parseJSONL('{"id":"a"}\n{"id":"b"}\n{"id":"c"}');
  eq(rows.length, 3, 'three records parsed');
  eq(rows[0], { id: 'a' }, 'first record');
  eq(rows[2], { id: 'c' }, 'third record');
}
{
  // Trailing newline + blank lines + valid records.
  const rows = parseJSONL('{"x":1}\n\n{"x":2}\n');
  eq(rows.length, 2, 'blank lines skipped');
}
{
  // Malformed line → _error record, NOT a thrown exception.
  const rows = parseJSONL('{"x":1}\nNOT JSON\n{"x":2}');
  eq(rows.length, 3, 'malformed line still produces a record');
  if (rows[1]._error && rows[1]._line === 2 && rows[1]._raw === 'NOT JSON') {
    console.log('  ok: malformed line surfaces as { _error, _line, _raw }');
    _passed++;
  } else {
    console.error(`FAIL: expected error record at index 1, got: ${JSON.stringify(rows[1])}`);
    _failed++;
  }
  eq(rows[0], { x: 1 }, 'valid records before malformed line unaffected');
  eq(rows[2], { x: 2 }, 'valid records after malformed line unaffected');
}
{
  // Leading whitespace on a line — JSON.parse handles it; we trim before
  // empty check so this should still parse correctly.
  const rows = parseJSONL('   {"a":1}   ');
  eq(rows, [{ a: 1 }], 'whitespace around record is tolerated');
}

// ====== esc =============================================================

console.log('\nesc:');
{
  eq(esc('hello'), 'hello', 'plain text unchanged');
  eq(esc('<script>alert(1)</script>'), '&lt;script&gt;alert(1)&lt;/script&gt;', 'tags escaped');
  eq(esc('a & b'), 'a &amp; b', 'ampersand escaped');
  eq(esc('"quoted"'), '&quot;quoted&quot;', 'double-quote escaped');
  eq(esc("it's"), 'it&#39;s', 'single-quote escaped');
  eq(esc(null), '', 'null → empty string');
  eq(esc(undefined), '', 'undefined → empty string');
  eq(esc(0), '0', 'number 0 → "0" (not empty)');
  eq(esc(false), 'false', 'boolean false → "false"');
}

// ====== countRegistryEntries ===========================================

console.log('\ncountRegistryEntries:');
{
  // pages-shaped registry — picks the .pages dict.
  const data = { _doc: 'x', $schema: 'y', pages: { p1: {}, p2: {}, p3: {} } };
  eq(countRegistryEntries('pages', data), '3 entries', 'pages dict counted (3)');
}
{
  // layers-shaped registry — picks .layers when no .pages.
  const data = { layers: { crossover_track: {}, nco_gc_track: {} } };
  eq(countRegistryEntries('layers', data), '2 entries', 'layers dict counted (2)');
}
{
  // Singular form for 1 entry.
  const data = { pages: { only_one: {} } };
  eq(countRegistryEntries('pages', data), '1 entry', 'pluralisation: 1 entry (singular)');
}
{
  // Underscore + $schema keys excluded from count.
  const data = { pages: { _doc: 'x', $schema: 'y', _meta: 'z', real_page: {} } };
  eq(countRegistryEntries('pages', data), '1 entry', '_-prefix and $schema keys excluded');
}
{
  // Falls through to data itself when no expected dict key matches.
  const data = { a: {}, b: {}, c: {} };
  eq(countRegistryEntries('weird', data), '3 entries', 'fallback to root dict counted');
}
{
  // Empty / nullish data.
  eq(countRegistryEntries('x', null), '(empty)', 'null data → "(empty)"');
  eq(countRegistryEntries('x', undefined), '(empty)', 'undefined data → "(empty)"');
  eq(countRegistryEntries('x', 'not an object'), '(empty)', 'string data → "(empty)"');
}

// ====== summary =========================================================

console.log();
if (_failed > 0) {
  console.error(`FAILED: ${_failed} of ${_passed + _failed} assertions failed`);
  process.exit(1);
}
console.log(`ALL OK (${_passed} assertions)`);
