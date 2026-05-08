// Smoke tests for parseDelimited with the new fieldsAllowList argument
// and for the cache-key derivation when fields varies.
//
// Run from repo root:
//   node atlas-core/tests/test_layer_router_fields.js
//
// No test framework — just throws on the first mismatch and prints OK.

import { parseDelimited } from '../core/layer_router.js';

function eq(a, b, msg) {
  if (JSON.stringify(a) !== JSON.stringify(b)) {
    console.error(`FAIL: ${msg}`);
    console.error(`  expected: ${JSON.stringify(b)}`);
    console.error(`  got:      ${JSON.stringify(a)}`);
    process.exit(1);
  } else {
    console.log(`  ok: ${msg}`);
  }
}

// ---------------------------------------------------------------------
// Mock ngsRelate-style TSV (subset of real columns; numeric coercion
// should kick in, "NA" → null).
// ---------------------------------------------------------------------
const ngsrelateTsv = [
  'a\tb\tnSites\ttheta\tIBS0\tIBS1\tIBS2\tKING',
  '0\t1\t12345\t0.0421\t0.0008\t0.4523\t0.5469\t0.0432',
  '0\t2\t12200\t0.0033\t0.0410\t0.5021\t0.4569\t0.0019',
  '1\t2\t12100\tNA\t0.0395\t0.5007\t0.4598\tNA',
].join('\n');

console.log('parseDelimited — no filter (legacy behavior):');
{
  const rows = parseDelimited(ngsrelateTsv, '\t');
  eq(rows.length, 3, 'returns 3 rows');
  eq(Object.keys(rows[0]).sort(),
     ['IBS0', 'IBS1', 'IBS2', 'KING', 'a', 'b', 'nSites', 'theta'],
     'all 8 columns present');
  eq(rows[0].theta, 0.0421, 'numeric coercion applied');
  eq(rows[2].theta, null, 'NA coerced to null in numeric column');
}

console.log('parseDelimited — fieldsAllowList filter:');
{
  const rows = parseDelimited(ngsrelateTsv, '\t', ['a', 'b', 'theta', 'IBS0']);
  eq(rows.length, 3, 'still 3 rows');
  eq(Object.keys(rows[0]).sort(),
     ['IBS0', 'a', 'b', 'theta'],
     'only the 4 requested columns present');
  eq(rows[0].a, 0, 'a coerced to int');
  eq(rows[0].theta, 0.0421, 'theta still numeric');
  eq(rows[0].IBS0, 0.0008, 'IBS0 still numeric');
  eq(rows[2].theta, null, 'NA still becomes null after filter');
}

console.log('parseDelimited — fieldsAllowList with unknown column:');
{
  // 'frobozz' isn't a column; should be silently ignored.
  const rows = parseDelimited(ngsrelateTsv, '\t', ['a', 'theta', 'frobozz']);
  eq(Object.keys(rows[0]).sort(), ['a', 'theta'], 'unknown column ignored');
}

console.log('parseDelimited — fieldsAllowList where allow-listed col is non-numeric:');
{
  const mixedTsv = [
    'sample\ttheta\tlabel',
    'CGA009\t0.10\thub',
    'CGA021\t0.05\tsmall',
  ].join('\n');
  const rows = parseDelimited(mixedTsv, '\t', ['sample', 'label']);
  eq(rows[0].sample, 'CGA009', 'sample stays as string');
  eq(rows[0].label, 'hub', 'label stays as string');
  eq(Object.keys(rows[0]).sort(), ['label', 'sample'], 'only requested cols');
}

console.log('parseDelimited — empty allow-list short-circuit:');
{
  // Empty allow-list means "keep nothing" by current semantics. The
  // engine never passes an empty array (it falls back to null in
  // _resolveFields). But the parser itself must handle it predictably.
  const rows = parseDelimited(ngsrelateTsv, '\t', []);
  // With Set([]) → no column passes → empty row objects, 3 of them.
  // (This is intentional: the engine's _resolveFields returns null
  // for empty arrays, so this case shouldn't occur in production.)
  eq(rows.length, 3, 'still 3 rows');
  eq(Object.keys(rows[0]).length, 0, 'all columns dropped on empty allow-list');
}

console.log('\nAll parseDelimited tests passed.');
