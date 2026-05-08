// tests/test_registry_master_config.js
//
// End-to-end test for the master_config path through Registry:
//   1. Build a synthetic master_config with two roots (one flat, one
//      species_scoped).
//   2. Build a synthetic atlas with two file layers — one using the
//      legacy `path:` form, one using the new `root:` + `path_under_root:`
//      form.
//   3. Stub the LayerRouter so we capture the path that would be
//      fetched, without doing real HTTP.
//   4. Resolve each layer; verify the expected path is computed.
//
// USAGE: from an assembled atlas-core+inversion workspace,
//   WORKSPACE=/path/to/workspace node tests/test_registry_master_config.js

const WS = process.env.WORKSPACE || '/home/claude/workspace/atlas-workspace';

const { Registry } = await import(`${WS}/core/registry_core.js`);
const { AtlasState } = await import(`${WS}/core/atlas_state.js`);

let pass = 0, fail = 0;
function ok(name, cond, detail = '') {
  if (cond) { console.log(`  ✓ ${name}`); pass++; }
  else      { console.log(`  ✗ ${name}  ${detail}`); fail++; }
}
function eq(name, got, want) {
  const same = JSON.stringify(got) === JSON.stringify(want);
  ok(name, same, same ? '' : `\n      got:  ${JSON.stringify(got)}\n      want: ${JSON.stringify(want)}`);
}

// ---------- Helpers: build a Registry with a stub fetcher ----------

function buildRegistry({ masterConfig = null, layers = {} } = {}) {
  const state = new AtlasState({ serverBaseUrl: 'http://localhost:0' });
  const registry = new Registry({
    atlasState: state,
    serverBaseUrl: 'http://localhost:0',
    masterConfig,
  });

  // Replace the layer router with a stub that just records what was asked
  const calls = [];
  registry.router = {
    fetchFile: async (path, format /* , fields */) => {
      calls.push({ path, format });
      return { __stub: true, path, format };
    },
  };

  registry.register_atlas('synthetic', {
    layers: { layers },
    operations: { operations: {} },
    files: { files: {} },
    pages: { pages: {} },
    slots: { slots: {} },
  });

  return { registry, state, calls };
}

// ============= 1. Legacy `path:` form (atlas-relative fallback) =============

{
  const { registry, calls } = buildRegistry({
    masterConfig: null,
    layers: {
      legacy_layer: {
        tier: 'cold',
        source: 'file',
        path: 'data/precomp/{chrom}.json',
      },
    },
  });

  await registry.resolve('legacy_layer', { chrom: 'LG28' });
  eq('legacy `path:` form: prepends atlases/<atlas_id>/',
    calls[0].path,
    'atlases/synthetic/data/precomp/LG28.json'
  );
}

// ============= 2. Legacy form: absolute path leaves as-is =============

{
  const { registry, calls } = buildRegistry({
    masterConfig: null,
    layers: {
      abs_layer: {
        tier: 'cold',
        source: 'file',
        path: '/mnt/big/precomp.json',
      },
    },
  });

  await registry.resolve('abs_layer', {});
  eq('legacy `path:` form: absolute path left untouched',
    calls[0].path,
    '/mnt/big/precomp.json'
  );
}

// ============= 3. New `root:` form, flat root =============

{
  const masterConfig = {
    atlas: { workspace_root: '.' },
    roots: {
      cohort_relatedness: {
        path: '/data/cohorts/main/relatedness',
        role: 'samples',
      },
    },
  };
  const { registry, calls } = buildRegistry({
    masterConfig,
    layers: {
      relatedness_layer: {
        tier: 'cold',
        source: 'file',
        root: 'cohort_relatedness',
        path_under_root: 'ngsrelate/{run_id}/relatedness.tsv',
        format: 'tsv',
      },
    },
  });

  await registry.resolve('relatedness_layer', { run_id: '2026_04_30' });
  eq('new `root:` form: flat root joined with path_under_root',
    calls[0].path,
    '/data/cohorts/main/relatedness/ngsrelate/2026_04_30/relatedness.tsv'
  );
  eq('new form: format flows through', calls[0].format, 'tsv');
}

// ============= 4. New `root:` form, species_scoped root =============

{
  const masterConfig = {
    atlas: { workspace_root: '.' },
    species: [{ id: 'gariepinus', config: 'species/gariepinus.yaml', active: true }],
    roots: {
      precomp: {
        path: './data/{species_id}/precomp',
        species_scoped: true,
        role: 'intervals',
      },
    },
  };
  const { registry, calls, state } = buildRegistry({
    masterConfig,
    layers: {
      scrubber_main: {
        tier: 'hot',
        source: 'file',
        root: 'precomp',
        path_under_root: '{chrom}.json',
      },
    },
  });
  state.shared.activeSpecies = 'gariepinus';

  await registry.resolve('scrubber_main', { chrom: 'LG28' });
  eq('new form: species_scoped root templates {species_id} from active species',
    calls[0].path,
    'data/gariepinus/precomp/LG28.json'
  );

  // Switch active species
  state.shared.activeSpecies = 'macrocephalus';
  registry.invalidate('scrubber_main', { chrom: 'LG28' });
  await registry.resolve('scrubber_main', { chrom: 'LG28' });
  eq('new form: species switch reroutes to other species path',
    calls[1].path,
    'data/macrocephalus/precomp/LG28.json'
  );

  // args.species_id wins over state.shared.activeSpecies
  registry.invalidate('scrubber_main', { chrom: 'LG28', species_id: 'bighead' });
  await registry.resolve('scrubber_main', { chrom: 'LG28', species_id: 'bighead' });
  eq('new form: args.species_id overrides active species',
    calls[2].path,
    'data/bighead/precomp/LG28.json'
  );
}

// ============= 5. Error: `root:` without master_config =============

{
  const { registry } = buildRegistry({
    masterConfig: null,
    layers: {
      orphan: {
        tier: 'cold',
        source: 'file',
        root: 'precomp',
        path_under_root: '{chrom}.json',
      },
    },
  });

  let caught = null;
  try { await registry.resolve('orphan', { chrom: 'LG28' }); }
  catch (e) { caught = e; }
  ok('new form: layer with root: but no master_config throws helpful error',
    caught !== null && /no master_config is loaded/.test(caught.message)
  );
}

// ============= 6. Error: `root:` referencing unknown root =============

{
  const masterConfig = {
    atlas: { workspace_root: '.' },
    roots: { precomp: { path: '/data/precomp' } },
  };
  const { registry } = buildRegistry({
    masterConfig,
    layers: {
      bogus: {
        tier: 'cold',
        source: 'file',
        root: 'nonexistent_root',
        path_under_root: 'x.json',
      },
    },
  });

  let caught = null;
  try { await registry.resolve('bogus', {}); }
  catch (e) { caught = e; }
  ok('new form: unknown root throws with hint about known roots',
    caught !== null
    && /unknown root 'nonexistent_root'/.test(caught.message)
    && /Known roots: precomp/.test(caught.message)
  );
}

// ============= 7. species_scoped root, no species resolved =============

{
  const masterConfig = {
    atlas: { workspace_root: '.' },
    // no species declared, no active species
    roots: {
      precomp: {
        path: './data/{species_id}/precomp',
        species_scoped: true,
      },
    },
  };
  const { registry } = buildRegistry({
    masterConfig,
    layers: {
      scrubber_main: {
        tier: 'hot',
        source: 'file',
        root: 'precomp',
        path_under_root: '{chrom}.json',
      },
    },
  });

  let caught = null;
  try { await registry.resolve('scrubber_main', { chrom: 'LG28' }); }
  catch (e) { caught = e; }
  ok('new form: species_scoped root with no species resolved → clear error',
    caught !== null && /no species_id resolved/.test(caught.message)
  );
}

// ============= 8. path_under_root absent → use root path directly =============

{
  const masterConfig = {
    atlas: { workspace_root: '.' },
    roots: { manifest_root: { path: '/data/manifest' } },
  };
  const { registry, calls } = buildRegistry({
    masterConfig,
    layers: {
      manifest_layer: {
        tier: 'cold',
        source: 'file',
        root: 'manifest_root',
        // no path_under_root — fetch the root itself (e.g. an index file convention)
      },
    },
  });

  await registry.resolve('manifest_layer', {});
  eq('new form: no path_under_root → root path itself',
    calls[0].path,
    '/data/manifest'
  );
}

// ---------- Summary ----------

console.log(`\npass: ${pass}\nfail: ${fail}`);
if (fail > 0) process.exit(1);
