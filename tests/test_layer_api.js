// Smoke tests for core/layer_api.js — uses a hand-rolled fetch mock so
// it runs on stdlib Node with no servers / no deps.
//
// Run from repo root:
//   node atlas-core/tests/test_layer_api.js

import {
  configureLayerApi,
  getLayerApiBaseUrl,
  listLayers,
  getLayer,
  resolveLatestLayer,
  getLayersOfType,
  getActionLog,
  submitAction,
  newActionId,
} from '../core/layer_api.js';

// ---------------------------------------------------------------------
// Tiny fetch mock. Tests register a (predicate, response) pair; the
// mock walks the list and returns the first response whose predicate
// matches. The predicate receives (url, init).
// ---------------------------------------------------------------------
const _routes = [];
const _calls  = [];   // record every call for assertions

function _resetMock() {
  _routes.length = 0;
  _calls.length = 0;
}

function _route(predicate, respFn) { _routes.push({ predicate, respFn }); }

globalThis.fetch = async (url, init) => {
  _calls.push({ url, init });
  for (const r of _routes) {
    if (r.predicate(url, init)) {
      const built = await r.respFn(url, init);
      return _makeResponse(built);
    }
  }
  return _makeResponse({ status: 404, body: { error: 'no mock route', url } });
};

function _makeResponse({ status = 200, body = null, text = null } = {}) {
  const okStatus = status >= 200 && status < 300;
  const bodyText = text !== null
    ? text
    : (body === null ? '' : JSON.stringify(body));
  return {
    ok: okStatus,
    status,
    async json() { return body !== null ? body : JSON.parse(bodyText); },
    async text() { return bodyText; },
  };
}

function eq(a, b, msg) {
  if (JSON.stringify(a) !== JSON.stringify(b)) {
    console.error(`FAIL: ${msg}`);
    console.error(`  expected: ${JSON.stringify(b)}`);
    console.error(`  got:      ${JSON.stringify(a)}`);
    process.exit(1);
  }
  console.log(`  ok: ${msg}`);
}

async function rejects(fn, msgFragment, label) {
  try { await fn(); } catch (e) {
    if (!String(e.message).includes(msgFragment)) {
      console.error(`FAIL: ${label} — wrong error: ${e.message}`);
      process.exit(1);
    }
    console.log(`  ok: ${label}`);
    return;
  }
  console.error(`FAIL: ${label} — did not throw`);
  process.exit(1);
}

// ---------------------------------------------------------------------
// configureLayerApi
// ---------------------------------------------------------------------
console.log('configureLayerApi:');
{
  eq(getLayerApiBaseUrl(), '', 'default base url is empty');
  configureLayerApi({ baseUrl: 'http://example.test:8000/' });
  eq(getLayerApiBaseUrl(), 'http://example.test:8000', 'trailing slash stripped');
  configureLayerApi({ baseUrl: '' });
  eq(getLayerApiBaseUrl(), '', 'reset to empty');
}

// ---------------------------------------------------------------------
// listLayers — filters become query-string
// ---------------------------------------------------------------------
console.log('listLayers:');
{
  _resetMock();
  _route(
    (url) => url.startsWith('/api/layers') && !url.includes('/api/layers/'),
    () => ({ body: { layers: [], n: 0, total: 0 } }),
  );
  await listLayers({});
  eq(_calls[0].url, '/api/layers', 'no filters → bare path');

  _resetMock();
  _route(
    (url) => url.startsWith('/api/layers'),
    () => ({ body: { layers: [], n: 0, total: 0 } }),
  );
  await listLayers({
    layer_type: 'fst_windows',
    dataset_id: 'main_226_hatchery',
    stage:      'normalized',
    limit:      50,
  });
  const u = new URL('http://x' + _calls[0].url);
  eq(u.searchParams.get('layer_type'), 'fst_windows', 'layer_type param');
  eq(u.searchParams.get('dataset_id'), 'main_226_hatchery', 'dataset_id param');
  eq(u.searchParams.get('stage'),      'normalized', 'stage param');
  eq(u.searchParams.get('limit'),      '50', 'limit param');

  _resetMock();
  _route(() => true, () => ({ body: { layers: [], n: 0, total: 0 } }));
  await listLayers({ status: '', stage: undefined, layer_type: null });
  eq(_calls[0].url, '/api/layers', 'empty/null/undefined filters are dropped');
}

// ---------------------------------------------------------------------
// getLayer — required arg, success, error
// ---------------------------------------------------------------------
console.log('getLayer:');
{
  await rejects(() => getLayer(''), 'layer_id required', 'empty layer_id rejected');

  _resetMock();
  const fakeEnv = {
    layer_id: 'L_001', layer_type: 'fst_windows', schema_version: 'fst_windows_v1',
    stage: 'normalized', dataset_id: 'main_226_hatchery', status: 'active',
    created_at: '2026-05-14T00:00:00Z',
    payload: { windows: [], summary: { n_windows: 0 } },
  };
  _route((url) => url === '/api/layers/L_001', () => ({ body: fakeEnv }));
  const env = await getLayer('L_001');
  eq(env.layer_id, 'L_001', 'returned envelope shape');

  _resetMock();
  _route(() => true, () => ({ status: 404, text: 'not found: L_missing' }));
  await rejects(
    () => getLayer('L_missing'),
    'HTTP 404',
    'non-2xx surfaces as Error',
  );
}

// ---------------------------------------------------------------------
// resolveLatestLayer — picks tail of list, then fetches envelope
// ---------------------------------------------------------------------
console.log('resolveLatestLayer:');
{
  _resetMock();
  _route(
    (url) => url.startsWith('/api/layers?'),
    () => ({ body: { layers: [
      { layer_id: 'L_old',  layer_type: 'fst_windows', created_at: '2026-05-12T00:00:00Z' },
      { layer_id: 'L_new',  layer_type: 'fst_windows', created_at: '2026-05-13T00:00:00Z' },
    ], n: 2, total: 2 } }),
  );
  _route(
    (url) => url === '/api/layers/L_new',
    () => ({ body: { layer_id: 'L_new', stage: 'normalized', payload: { ok: true } } }),
  );
  const env = await resolveLatestLayer('fst_windows', { dataset_id: 'main_226_hatchery' });
  eq(env.layer_id, 'L_new', 'tail of list wins');
  eq(_calls.length, 2, 'one list + one envelope fetch');

  _resetMock();
  _route(() => true, () => ({ body: { layers: [], n: 0, total: 0 } }));
  const none = await resolveLatestLayer('fst_windows', { dataset_id: 'unknown' });
  eq(none, null, 'returns null when no match (not an error)');

  await rejects(
    () => resolveLatestLayer(''),
    'layer_type required',
    'empty layer_type rejected',
  );
}

// ---------------------------------------------------------------------
// getLayersOfType — one fetch per envelope
// ---------------------------------------------------------------------
console.log('getLayersOfType:');
{
  _resetMock();
  _route(
    (url) => url.startsWith('/api/layers?'),
    () => ({ body: { layers: [
      { layer_id: 'L_a' }, { layer_id: 'L_b' }, { layer_id: 'L_c' },
    ], n: 3, total: 3 } }),
  );
  _route(
    (url) => url.startsWith('/api/layers/L_'),
    (url) => ({ body: { layer_id: url.slice('/api/layers/'.length), payload: {} } }),
  );
  const envs = await getLayersOfType('fst_windows', { dataset_id: 'main_226_hatchery' });
  eq(envs.length, 3, 'all 3 envelopes returned');
  eq(envs.map((e) => e.layer_id), ['L_a', 'L_b', 'L_c'], 'order preserved');
}

// ---------------------------------------------------------------------
// submitAction — POST with JSON body, atlas query param
// ---------------------------------------------------------------------
console.log('submitAction:');
{
  await rejects(
    () => submitAction(null),
    'manifest object required',
    'null manifest rejected',
  );

  _resetMock();
  _route(
    (url, init) => url.startsWith('/api/actions') && init && init.method === 'POST',
    () => ({ body: {
      ok: true, action_id: 'act_123_abc',
      atlas_id: 'inversion', produced_layers: ['L_new'],
    } }),
  );
  const manifest = {
    action_id: 'act_123_abc', type: 'run_popstats',
    dataset_id: 'main_226_hatchery', runner: 'run_popstats',
    target: { chrom: 'C_gar_LG28', groups: { A: ['s1'], B: ['s2'] } },
    params: { stat: 'fst' },
    expected_outputs: [{ layer_type: 'fst_windows', schema_version: 'fst_windows_v1' }],
  };
  const res = await submitAction(manifest, { atlas: 'inversion' });
  eq(res.produced_layers, ['L_new'], 'produced_layers echoed');
  eq(_calls[0].url, '/api/actions?atlas=inversion', 'atlas query param appended');
  eq(_calls[0].init.method, 'POST', 'POST method');
  eq(_calls[0].init.headers['content-type'], 'application/json', 'json header');
  const sentBody = JSON.parse(_calls[0].init.body);
  eq(sentBody.action_id, 'act_123_abc', 'body forwards manifest');
}

// ---------------------------------------------------------------------
// getActionLog
// ---------------------------------------------------------------------
console.log('getActionLog:');
{
  await rejects(
    () => getActionLog(''),
    'action_id required',
    'empty action_id rejected',
  );

  _resetMock();
  _route(
    (url) => url === '/api/actions/act_123_abc',
    () => ({ body: {
      action_id: 'act_123_abc', status: 'success',
      produced_layers: ['L_new'], duration_ms: 321,
    } }),
  );
  const entry = await getActionLog('act_123_abc');
  eq(entry.status, 'success', 'status echoed');
}

// ---------------------------------------------------------------------
// newActionId — schema-conformant
// ---------------------------------------------------------------------
console.log('newActionId:');
{
  const id = newActionId();
  if (!/^act_[A-Za-z0-9_]+$/.test(id)) {
    console.error(`FAIL: newActionId did not match schema regex: ${id}`);
    process.exit(1);
  }
  console.log(`  ok: matches schema (${id})`);
  const a = newActionId(), b = newActionId();
  if (a === b) {
    console.error(`FAIL: newActionId collided: ${a}`);
    process.exit(1);
  }
  console.log('  ok: two calls produce distinct ids');
}

// ---------------------------------------------------------------------
// baseUrl prefixes every request
// ---------------------------------------------------------------------
console.log('baseUrl propagation:');
{
  configureLayerApi({ baseUrl: 'http://remote.test:8000' });
  _resetMock();
  _route(
    (url) => url === 'http://remote.test:8000/api/layers/L_x',
    () => ({ body: { layer_id: 'L_x' } }),
  );
  await getLayer('L_x');
  eq(_calls[0].url, 'http://remote.test:8000/api/layers/L_x', 'baseUrl prepended');
  configureLayerApi({ baseUrl: '' });
}

console.log('\nALL OK');
