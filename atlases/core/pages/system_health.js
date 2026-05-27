// atlases/core/pages/system_health.js
// =============================================================================
// System health dashboard. Three tabs:
//   1. Per-atlas summary cards (page/layer/op counts, % ready)
//   2. Layer status table (all layers across all atlases, sortable + filterable)
//   3. Cross-atlas dependency graph (producer -> consumer edges from
//      cohorts.registry.json)
//
// Data sources (all read at mount, no live polling):
//   - window.__atlasRegistry — the singleton Registry, exposed by index.html
//                              at boot. Has _atlases Map, _layerIndex, _operationIndex.
//   - GET ./cohorts.registry.json — atlas-core's master producer/consumer index.
//
// The page is self-contained (no shared module deps beyond the registry singleton).
// =============================================================================

// ----- helpers ----------------------------------------------------------
function _esc(s) {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function _statusKind(entry) {
  if (!entry || typeof entry !== 'object') return 'other';
  const s = entry._status || '';
  if (s === 'not_implemented') return 'not_implemented';
  if (s === 'not_loaded')      return 'not_loaded';
  if (s === 'session_state')   return 'session_state';
  if (s.startsWith('available_')) return 'ready';
  if (s === '' || s === 'ready' || entry.path || entry.path_under_root) return 'ready';
  return 'other';
}

function _statusClass(kind) {
  return {
    ready:           'sh-pill-ready',
    not_loaded:      'sh-pill-pending',
    not_implemented: 'sh-pill-pending',
    session_state:   'sh-pill-ready',
    other:           'sh-pill-other',
  }[kind] || 'sh-pill-other';
}

// ----- page-local state -------------------------------------------------
const _state = {
  registry: null,
  cohorts: null,
  allLayers: [],     // { atlas_id, layer_id, entry, statusKind }
  layerFilter: { atlas: '', status: '', q: '' },
  graphSortDir: -1,  // -1 = desc by used_by count
};

// ----- data collection --------------------------------------------------
function _collect() {
  const reg = window.__atlasRegistry;
  if (!reg) return false;
  _state.registry = reg;
  _state.allLayers = [];
  // reg._atlases is a Map<atlas_id, { layers, operations, files, pages, slots }>
  for (const [atlas_id, conf] of reg._atlases.entries()) {
    const layers = conf.layers || {};
    for (const [layer_id, entry] of Object.entries(layers)) {
      if (layer_id.startsWith('_')) continue;
      _state.allLayers.push({
        atlas_id,
        layer_id,
        entry,
        statusKind: _statusKind(entry),
      });
    }
  }
  return true;
}

async function _loadCohorts() {
  try {
    const resp = await fetch('./cohorts.registry.json');
    if (!resp.ok) throw new Error('HTTP ' + resp.status);
    _state.cohorts = await resp.json();
  } catch (e) {
    _state.cohorts = null;
    console.warn('system_health: cohorts.registry.json load failed:', e);
  }
}

// ----- summary cards ----------------------------------------------------
function _renderSummary() {
  const slot = document.getElementById('shSummaryGrid');
  if (!slot) return;
  const reg = _state.registry;
  if (!reg) {
    slot.innerHTML = '<span class="sh-hint">window.__atlasRegistry not present.</span>';
    return;
  }

  const atlases = Array.from(reg._atlases.keys()).sort();
  const html = atlases.map(aid => {
    const conf = reg._atlases.get(aid);
    const nLayers = Object.keys(conf.layers || {}).filter(k => !k.startsWith('_')).length;
    const nOps    = Object.keys(conf.operations || {}).filter(k => !k.startsWith('_')).length;
    const nPages  = Object.keys(conf.pages || {}).filter(k => !k.startsWith('_')).length;

    // % ready
    const layersOfAtlas = _state.allLayers.filter(L => L.atlas_id === aid);
    const nReady = layersOfAtlas.filter(L => L.statusKind === 'ready' || L.statusKind === 'session_state').length;
    const pct = nLayers > 0 ? Math.round(100 * nReady / nLayers) : 0;

    return `
      <div class="sh-card">
        <div class="sh-card-title">${_esc(aid)}</div>
        <div class="sh-card-stats">
          <span class="sh-stat"><b>${nPages}</b> pages</span>
          <span class="sh-stat"><b>${nLayers}</b> layers</span>
          <span class="sh-stat"><b>${nOps}</b> ops</span>
        </div>
        <div class="sh-card-ready">
          <div class="sh-bar"><div class="sh-bar-fill" style="width:${pct}%"></div></div>
          <div class="sh-bar-label">${nReady}/${nLayers} ready (${pct}%)</div>
        </div>
      </div>
    `;
  }).join('');
  slot.innerHTML = html || '<span class="sh-hint">No atlases registered.</span>';
}

// ----- layer table ------------------------------------------------------
function _populateLayerFilter() {
  const sel = document.getElementById('shLayerAtlasFilter');
  if (!sel) return;
  const atlases = Array.from(new Set(_state.allLayers.map(L => L.atlas_id))).sort();
  // Preserve "all"
  const had = new Set(Array.from(sel.options).map(o => o.value));
  for (const aid of atlases) {
    if (had.has(aid)) continue;
    const opt = document.createElement('option');
    opt.value = aid;
    opt.textContent = aid;
    sel.appendChild(opt);
  }
}

function _filteredLayers() {
  const { atlas, status, q } = _state.layerFilter;
  const ql = q.toLowerCase();
  return _state.allLayers.filter(L => {
    if (atlas && L.atlas_id !== atlas) return false;
    if (status && L.statusKind !== status) return false;
    if (ql && !L.layer_id.toLowerCase().includes(ql)) return false;
    return true;
  });
}

function _renderLayers() {
  const slot = document.getElementById('shLayerTableSlot');
  const countSlot = document.getElementById('shLayerCount');
  if (!slot) return;

  const rows = _filteredLayers();
  if (countSlot) {
    countSlot.textContent = `${rows.length} of ${_state.allLayers.length}`;
  }
  if (!rows.length) {
    slot.innerHTML = '<span class="sh-hint">no layers match.</span>';
    return;
  }

  // Sort: atlas_id then layer_id
  rows.sort((a, b) => {
    if (a.atlas_id !== b.atlas_id) return a.atlas_id.localeCompare(b.atlas_id);
    return a.layer_id.localeCompare(b.layer_id);
  });

  let html = '<table class="sh-table"><thead><tr>' +
    '<th>atlas</th><th>layer_id</th><th>tier</th><th>source</th><th>status</th><th>path</th>' +
    '</tr></thead><tbody>';
  for (const L of rows) {
    const e = L.entry || {};
    const tier   = e.tier || e.cache_tier || '';
    const source = e.source || '';
    const path   = e.path || e.path_under_root || (e.root ? `<root:${e.root}>` : '');
    html += '<tr>' +
      `<td><code>${_esc(L.atlas_id)}</code></td>` +
      `<td><code>${_esc(L.layer_id)}</code></td>` +
      `<td>${_esc(tier)}</td>` +
      `<td>${_esc(source)}</td>` +
      `<td><span class="sh-pill ${_statusClass(L.statusKind)}">${_esc(L.statusKind)}</span></td>` +
      `<td class="sh-dim">${_esc(path)}</td>` +
      '</tr>';
  }
  html += '</tbody></table>';
  slot.innerHTML = html;
}

// ----- cross-atlas graph ------------------------------------------------
function _renderGraph() {
  const slot = document.getElementById('shGraphTableSlot');
  if (!slot) return;
  const cohorts = _state.cohorts;
  if (!cohorts) {
    slot.innerHTML = '<span class="sh-hint">cohorts.registry.json unavailable.</span>';
    return;
  }
  const producers = cohorts.producers || {};
  const rows = Object.entries(producers)
    .filter(([, m]) => m && typeof m === 'object')
    .map(([k, m]) => ({
      key: k,
      atlas_id: m.atlas_id || '',
      used_by: Array.isArray(m.used_by) ? m.used_by : [],
    }));
  // Sort by used_by count desc, then key
  rows.sort((a, b) => (b.used_by.length - a.used_by.length) * _state.graphSortDir || a.key.localeCompare(b.key));

  let html = '<table class="sh-table"><thead><tr>' +
    '<th data-sort-graph="key">layer</th><th data-sort-graph="atlas">owner</th>' +
    '<th data-sort-graph="count">consumers</th><th>used_by</th>' +
    '</tr></thead><tbody>';
  for (const r of rows) {
    const consumers = r.used_by.length === 0
      ? '<span class="sh-dim">(unused)</span>'
      : r.used_by.map(c => `<span class="sh-chip">${_esc(c)}</span>`).join(' ');
    html += '<tr>' +
      `<td><code>${_esc(r.key)}</code></td>` +
      `<td><code>${_esc(r.atlas_id)}</code></td>` +
      `<td class="sh-num">${r.used_by.length}</td>` +
      `<td>${consumers}</td>` +
      '</tr>';
  }
  html += '</tbody></table>';
  slot.innerHTML = html;
}

// ----- tab switching ----------------------------------------------------
function _setTab(name) {
  document.querySelectorAll('.sh-tab').forEach(t => {
    t.classList.toggle('active', t.dataset.tab === name);
  });
  document.querySelectorAll('.sh-tab-panel').forEach(p => {
    p.classList.remove('sh-tab-panel-active');
  });
  const target = document.getElementById('shTab' + name[0].toUpperCase() + name.slice(1));
  if (target) target.classList.add('sh-tab-panel-active');
}

function _wire() {
  document.querySelectorAll('.sh-tab').forEach(t => {
    t.addEventListener('click', () => _setTab(t.dataset.tab));
  });
  const af = document.getElementById('shLayerAtlasFilter');
  const sf = document.getElementById('shLayerStatusFilter');
  const sb = document.getElementById('shLayerSearch');
  if (af) af.addEventListener('change', e => { _state.layerFilter.atlas  = e.target.value; _renderLayers(); });
  if (sf) sf.addEventListener('change', e => { _state.layerFilter.status = e.target.value; _renderLayers(); });
  if (sb) sb.addEventListener('input',  e => { _state.layerFilter.q      = e.target.value; _renderLayers(); });
}

// ----- lifecycle --------------------------------------------------------
export async function mount(root, atlasState, registry) {
  _wire();
  const ok = _collect();
  if (!ok) {
    const grid = document.getElementById('shSummaryGrid');
    if (grid) grid.innerHTML = '<span class="sh-hint">window.__atlasRegistry not present. Atlas has not finished booting yet.</span>';
    return;
  }
  await _loadCohorts();
  _renderSummary();
  _populateLayerFilter();
  _renderLayers();
  _renderGraph();
}

export async function unmount(root) {
  // no-op — page is read-only and idempotent
}
