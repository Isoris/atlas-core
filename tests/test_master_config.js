// tests/test_master_config.js
//
// Unit tests for atlas-core/core/master_config.js — loader, YAML parser,
// substitution, validation, root resolution.
//
// USAGE: from an assembled atlas-core+inversion workspace,
//   WORKSPACE=/path/to/workspace node tests/test_master_config.js
// Defaults to /home/claude/workspace/atlas-workspace if WORKSPACE is unset.

const WS = process.env.WORKSPACE || '/home/claude/workspace/atlas-workspace';

const { parseYamlSubset, resolveSubstitutions, validateMasterConfig, resolveRootPath } =
  await import(`${WS}/core/master_config.js`);

let pass = 0, fail = 0;
function ok(name, cond, detail = '') {
  if (cond) { console.log(`  ✓ ${name}`); pass++; }
  else      { console.log(`  ✗ ${name}  ${detail}`); fail++; }
}
function eq(name, got, want) {
  const same = JSON.stringify(got) === JSON.stringify(want);
  ok(name, same, same ? '' : `\n      got:  ${JSON.stringify(got)}\n      want: ${JSON.stringify(want)}`);
}

// ---------- parseYamlSubset ----------

eq('empty input → {}', parseYamlSubset(''), {});

eq('comments-only input → {}', parseYamlSubset('# hello\n# world\n'), {});

eq('flat key: value pairs',
  parseYamlSubset('a: 1\nb: 2\nc: hello'),
  { a: 1, b: 2, c: 'hello' }
);

eq('null and boolean literals',
  parseYamlSubset('a: null\nb: ~\nc:\nd: true\ne: false'),
  { a: null, b: null, c: null, d: true, e: false }
);

eq('quoted strings preserve special chars',
  parseYamlSubset('a: "hello world"\nb: \'with: colon\''),
  { a: 'hello world', b: 'with: colon' }
);

eq('nested mapping (indent 2)',
  parseYamlSubset('atlas:\n  workspace_root: "."\n  active_atlas: inversion\n'),
  { atlas: { workspace_root: '.', active_atlas: 'inversion' } }
);

eq('two-level nested mapping',
  parseYamlSubset(`roots:
  precomp:
    path: "./data/precomp"
    role: intervals
`),
  { roots: { precomp: { path: './data/precomp', role: 'intervals' } } }
);

eq('inline sequence of scalars',
  parseYamlSubset(`names:
  - alice
  - bob
  - charlie
`),
  { names: ['alice', 'bob', 'charlie'] }
);

eq('sequence of mappings',
  parseYamlSubset(`species:
  - id: gariepinus
    config: species/gariepinus.config.yaml
    active: true
  - id: macrocephalus
    config: species/macrocephalus.config.yaml
    active: false
`),
  {
    species: [
      { id: 'gariepinus',    config: 'species/gariepinus.config.yaml',    active: true },
      { id: 'macrocephalus', config: 'species/macrocephalus.config.yaml', active: false },
    ]
  }
);

eq('comment after value is stripped',
  parseYamlSubset('a: 1  # this is a comment\nb: 2'),
  { a: 1, b: 2 }
);

eq('hash inside quoted string preserved',
  parseYamlSubset('a: "value # with hash"\nb: 2'),
  { a: 'value # with hash', b: 2 }
);

eq('numeric scalars (int / float / negative)',
  parseYamlSubset('a: 42\nb: -7\nc: 3.14\nd: -0.5\ne: 1e6'),
  { a: 42, b: -7, c: 3.14, d: -0.5, e: 1e6 }
);

// ---------- resolveSubstitutions ----------

eq('substitution: ${roots.X.path}',
  resolveSubstitutions({
    roots: { cache: { path: '/mnt/e/cache' } },
    server: { popstats_cache: { path: '${roots.cache.path}/popstats' } },
  }),
  {
    roots: { cache: { path: '/mnt/e/cache' } },
    server: { popstats_cache: { path: '/mnt/e/cache/popstats' } },
  }
);

eq('substitution: leaves non-substitution strings alone',
  resolveSubstitutions({ a: 'hello', b: 42, c: { d: 'world' } }),
  { a: 'hello', b: 42, c: { d: 'world' } }
);

ok('substitution: cycle is detected',
  (() => {
    try {
      resolveSubstitutions({
        a: { x: '${b.y}' },
        b: { y: '${a.x}' },
      });
      return false;
    } catch (e) {
      return /cycle detected/.test(e.message);
    }
  })()
);

ok('substitution: unresolved reference throws',
  (() => {
    try {
      resolveSubstitutions({ a: '${nope.nada}' });
      return false;
    } catch (e) {
      return /refers to nothing/.test(e.message);
    }
  })()
);

// ---------- validateMasterConfig ----------

ok('validation: minimal valid config passes',
  (() => {
    try {
      validateMasterConfig({
        atlas: { workspace_root: '.' },
        roots: { precomp: { path: './data/precomp' } },
      });
      return true;
    } catch { return false; }
  })()
);

ok('validation: missing roots throws',
  (() => {
    try { validateMasterConfig({ atlas: { workspace_root: '.' } }); return false; }
    catch (e) { return /missing required 'roots'/.test(e.message); }
  })()
);

ok('validation: missing atlas throws',
  (() => {
    try { validateMasterConfig({ roots: { x: { path: '/x' } } }); return false; }
    catch (e) { return /missing required 'atlas'/.test(e.message); }
  })()
);

ok('validation: invalid role rejected',
  (() => {
    try {
      validateMasterConfig({
        atlas: { workspace_root: '.' },
        roots: { x: { path: '/x', role: 'bogus' } },
      });
      return false;
    } catch (e) { return /invalid role/.test(e.message); }
  })()
);

ok('validation: root missing path throws',
  (() => {
    try {
      validateMasterConfig({
        atlas: { workspace_root: '.' },
        roots: { precomp: { role: 'intervals' } },
      });
      return false;
    } catch (e) { return /missing 'path'/.test(e.message); }
  })()
);

// ---------- resolveRootPath ----------

const cfgFlat = {
  atlas: { workspace_root: '.' },
  roots: { precomp: { path: './data/precomp' } },
};

eq('resolveRootPath: flat root, ./ stripped',
  resolveRootPath(cfgFlat, 'precomp'),
  'data/precomp'
);

ok('resolveRootPath: unknown root throws with helpful message',
  (() => {
    try { resolveRootPath(cfgFlat, 'nonexistent'); return false; }
    catch (e) { return /unknown root 'nonexistent'/.test(e.message) && /Known roots: precomp/.test(e.message); }
  })()
);

ok('resolveRootPath: no master_config throws',
  (() => {
    try { resolveRootPath(null, 'precomp'); return false; }
    catch (e) { return /no master_config is loaded/.test(e.message); }
  })()
);

const cfgScoped = {
  atlas: { workspace_root: '.' },
  species: [{ id: 'gariepinus', config: 'species/gariepinus.yaml', active: true }],
  roots: {
    precomp: { path: './data/{species_id}/precomp', species_scoped: true, role: 'intervals' },
    cache:   { path: '/mnt/e/cache' },
  },
};

eq('resolveRootPath: species_scoped uses active species',
  resolveRootPath(cfgScoped, 'precomp'),
  'data/gariepinus/precomp'
);

eq('resolveRootPath: species_scoped uses args override',
  resolveRootPath(cfgScoped, 'precomp', { species_id: 'macrocephalus' }),
  'data/macrocephalus/precomp'
);

eq('resolveRootPath: species_scoped uses state.shared.activeSpecies',
  resolveRootPath(cfgScoped, 'precomp', {}, { shared: { activeSpecies: 'bighead' } }),
  'data/bighead/precomp'
);

eq('resolveRootPath: non-scoped root ignores species',
  resolveRootPath(cfgScoped, 'cache', { species_id: 'gariepinus' }),
  '/mnt/e/cache'
);

// ---------- Round-trip: actual master_config.example.yaml ----------

const fs = await import('node:fs/promises');
const yamlText = await fs.readFile(`${WS}/master_config.example.yaml`, 'utf8');
let parsed;
try {
  parsed = parseYamlSubset(yamlText);
  ok('parses real master_config.example.yaml without throwing', true);
} catch (e) {
  ok('parses real master_config.example.yaml without throwing', false, e.message);
  parsed = null;
}

if (parsed) {
  ok('parsed config has atlas section',  parsed.atlas && typeof parsed.atlas === 'object');
  ok('parsed config has roots section',  parsed.roots && typeof parsed.roots === 'object');
  ok('parsed config has species array',  Array.isArray(parsed.species));
  ok('parsed roots has precomp entry',   parsed.roots && parsed.roots.precomp);
  ok('parsed roots.precomp has path',    parsed.roots && parsed.roots.precomp && typeof parsed.roots.precomp.path === 'string');
  ok('parsed roots.precomp has species_scoped: true',
    parsed.roots && parsed.roots.precomp && parsed.roots.precomp.species_scoped === true);
  ok('parsed roots.cache has writable: true',
    parsed.roots && parsed.roots.cache && parsed.roots.cache.writable === true);
  ok('parsed roots.cache has ephemeral: true',
    parsed.roots && parsed.roots.cache && parsed.roots.cache.ephemeral === true);

  // Substitution should resolve ${roots.cache.path} inside server.popstats_cache.path
  const resolved = resolveSubstitutions(parsed);
  ok('substitution resolves ${roots.cache.path} inside server config',
    resolved.server && resolved.server.popstats_cache && resolved.server.popstats_cache.path
    && resolved.server.popstats_cache.path.startsWith('/mnt/e/inversion-atlas-cache/popstats_engine_cache'));

  // Final validation
  try {
    validateMasterConfig(resolved, 'master_config.example.yaml');
    ok('parsed example yaml passes validation', true);
  } catch (e) {
    ok('parsed example yaml passes validation', false, e.message);
  }
}

// ---------- Summary ----------

console.log(`\npass: ${pass}\nfail: ${fail}`);
if (fail > 0) process.exit(1);
