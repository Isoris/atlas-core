// core/layer_api.js
// =====================================================================
// Action-pipeline layer helpers. Wraps the four endpoints that
// atlas-core/server/atlas_server.py exposes per PIPELINE_FLOW.md:
//
//   POST /api/actions            — submit a manifest, run dispatcher,
//                                  return produced layer_ids
//   GET  /api/actions/{id}       — latest action log entry
//   GET  /api/layers             — list/filter envelope index
//   GET  /api/layers/{layer_id}  — fetch one envelope (full JSON)
//
// Pages use these to consume action-pipeline outputs by content (layer
// envelope) instead of by filename. The legacy file-based resolve()
// stays usable for layers declared in <atlas>/registries/data/
// layers.registry.json; the two paths coexist on purpose.
//
// Page usage:
//
//   import { resolveLatestLayer, submitAction } from '../core/atlas_api.js';
//
//   // Get the most recent fst_windows envelope for this cohort
//   const env = await resolveLatestLayer('fst_windows', {
//     dataset_id: 'main_226_hatchery',
//     stage:      'normalized',
//   });
//   render(env.payload.windows, env.payload.summary);
//
//   // Submit a new compute action
//   const res = await submitAction({
//     action_id:  'act_' + Date.now() + '_' + Math.random().toString(36).slice(2,5),
//     type:       'run_popstats',
//     dataset_id: 'main_226_hatchery',
//     runner:     'run_popstats',
//     target:     { chrom: 'C_gar_LG28', groups: {...} },
//     params:     { stat: 'fst' },
//     expected_outputs: [{ layer_type:'fst_windows', schema_version:'fst_windows_v1' }],
//   }, { atlas: 'inversion' });
//   // res.produced_layers is an array of layer_ids ready to fetch.
//
// All helpers use relative URLs by default (same-origin fetch). For
// file:// origin pages talking to a remote server, call
// configureLayerApi({ baseUrl: 'http://127.0.0.1:8000' }) once at boot.
// =====================================================================

let _baseUrl = '';   // empty → same-origin relative fetches

export function configureLayerApi({ baseUrl } = {}) {
  if (typeof baseUrl === 'string') {
    _baseUrl = baseUrl.replace(/\/+$/, '');
  }
}

export function getLayerApiBaseUrl() { return _baseUrl; }

function _url(path) { return _baseUrl + path; }

async function _fetchJson(path, init) {
  const resp = await fetch(_url(path), init);
  if (!resp.ok) {
    let body = '';
    try { body = (await resp.text()).slice(0, 400); } catch (_) {}
    throw new Error(
      `layer_api: ${(init && init.method) || 'GET'} ${path} → ` +
      `HTTP ${resp.status}${body ? ' — ' + body : ''}`
    );
  }
  return resp.json();
}

// ---------------------------------------------------------------------
// GET /api/layers — filter the envelope index.
// ---------------------------------------------------------------------
//
// filters:
//   layer_type, dataset_id, stage, status: exact-match string filters
//   limit:                                 integer (server clamps to tail)
//
// Returns: { layers: [...index_entries], n, total }
// Each entry has { layer_id, layer_type, schema_version, stage,
//                  dataset_id, status, created_at, path }
// (path is workspace-relative; pages typically don't read it directly
// — getLayer(layer_id) is the supported way.)
// ---------------------------------------------------------------------
export async function listLayers(filters = {}) {
  const q = new URLSearchParams();
  for (const k of ['layer_type', 'dataset_id', 'stage', 'status']) {
    const v = filters[k];
    if (v !== undefined && v !== null && v !== '') q.set(k, String(v));
  }
  if (filters.limit !== undefined && filters.limit !== null) {
    q.set('limit', String(Number(filters.limit) | 0));
  }
  const qs = q.toString();
  return _fetchJson('/api/layers' + (qs ? '?' + qs : ''));
}

// ---------------------------------------------------------------------
// GET /api/layers/{layer_id} — fetch one full envelope.
// ---------------------------------------------------------------------
export async function getLayer(layer_id) {
  if (!layer_id) throw new Error('layer_api.getLayer: layer_id required');
  return _fetchJson('/api/layers/' + encodeURIComponent(layer_id));
}

// ---------------------------------------------------------------------
// Convenience: most-recent envelope of `layer_type` matching the
// optional dataset_id / stage / status filters. Returns null when no
// match exists (NOT an error — pages should branch on null).
// ---------------------------------------------------------------------
export async function resolveLatestLayer(layer_type, opts = {}) {
  if (!layer_type) throw new Error('layer_api.resolveLatestLayer: layer_type required');
  const list = await listLayers({ ...opts, layer_type });
  const rows = (list && list.layers) || [];
  if (rows.length === 0) return null;
  // The server returns most-recent-last. Take the tail.
  return getLayer(rows[rows.length - 1].layer_id);
}

// ---------------------------------------------------------------------
// Fetch ALL envelopes matching the filter (one fetch per envelope).
// Use with care — chatty for large indexes. Prefer listLayers() when
// you only need the index rows, or limit/dataset_id/stage filters when
// you need the full envelopes.
// ---------------------------------------------------------------------
export async function getLayersOfType(layer_type, opts = {}) {
  const list = await listLayers({ ...opts, layer_type });
  const rows = (list && list.layers) || [];
  return Promise.all(rows.map((r) => getLayer(r.layer_id)));
}

// ---------------------------------------------------------------------
// GET /api/actions/{action_id} — latest log entry (status, produced_layers, …).
// ---------------------------------------------------------------------
export async function getActionLog(action_id) {
  if (!action_id) throw new Error('layer_api.getActionLog: action_id required');
  return _fetchJson('/api/actions/' + encodeURIComponent(action_id));
}

// ---------------------------------------------------------------------
// POST /api/actions — submit a manifest. Atlas resolution precedence
// inside the server is: ?atlas=… > manifest.atlas_id > master_config.
// Pass { atlas } here to set the query-param (most explicit).
//
// Returns the server's JSON: { ok, action_id, atlas_id, produced_layers }.
// Throws on non-2xx — the action log will still have an 'error' entry
// for forensics.
// ---------------------------------------------------------------------
export async function submitAction(manifest, opts = {}) {
  if (!manifest || typeof manifest !== 'object') {
    throw new Error('layer_api.submitAction: manifest object required');
  }
  const q = opts.atlas ? '?atlas=' + encodeURIComponent(opts.atlas) : '';
  return _fetchJson('/api/actions' + q, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(manifest),
  });
}

// ---------------------------------------------------------------------
// Convenience: action_id generator matching the schema regex
//   ^act_[A-Za-z0-9_]+$
// — timestamp_ms + 3-char suffix is the convention the action manifest
// schema documents.
// ---------------------------------------------------------------------
export function newActionId() {
  const ms = Date.now();
  const tail = Math.random().toString(36).slice(2, 5).padEnd(3, '0');
  return 'act_' + ms + '_' + tail;
}
