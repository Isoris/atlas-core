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
// 2026-05-26: was returning false (→ page aborts) when reg was missing.
// Now still collects whatever globals are exposed so failed-only boots
// still render a useful "what's wrong" view instead of a blank panel.
function _collect() {
  const reg = window.__atlasRegistry || null;
  _state.registry = reg;
  _state.allLayers = [];
  if (reg) {
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
  }
  // True if we have *anything* to render — either a registry or a
  // manifests map (which exists even when every registration failed).
  return !!(reg || (window.__atlasManifests instanceof Map && window.__atlasManifests.size > 0));
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
// 2026-05-26: was iterating reg._atlases (registered only). Atlases
// whose register_atlas() threw were silently dropped from the dashboard
// — Quentin: "its missing many atlases". Now enumerates the FULL
// discovered set (window.__atlasManifests) so failed atlases render
// with ⚠ + reason instead of vanishing. Adds workflows / files /
// scope_pickers counts (previously only pages/layers/ops were shown).
function _renderSummary() {
  const slot = document.getElementById('shSummaryGrid');
  if (!slot) return;

  // Canonical atlas list = every atlas discovered at boot, regardless
  // of whether registration succeeded. Fall back to the registry's
  // keys if __atlasManifests isn't exposed (older bundles).
  const manifests = (typeof window !== 'undefined' && window.__atlasManifests instanceof Map)
    ? window.__atlasManifests : null;
  const failedList = (typeof window !== 'undefined' && Array.isArray(window.__atlasFailedAtlases))
    ? window.__atlasFailedAtlases : [];
  const failedByAtlas = new Map(failedList.map(f => [f.atlas_id, f.error]));

  const reg = _state.registry;
  let atlasIds = [];
  if (manifests) {
    atlasIds = Array.from(manifests.keys());
    for (const fId of failedByAtlas.keys()) {
      if (!atlasIds.includes(fId)) atlasIds.push(fId);
    }
  } else if (reg) {
    atlasIds = Array.from(reg._atlases.keys());
  }
  atlasIds.sort();

  if (atlasIds.length === 0) {
    slot.innerHTML = '<span class="sh-hint">No atlases discovered at boot.</span>';
    return;
  }

  // ── Top-line summary strip (counts across atlases) ─────────────
  const nLoaded = manifests ? manifests.size : (reg ? reg._atlases.size : 0);
  const nFailed = failedByAtlas.size;
  const nRegistered = reg ? reg._atlases.size : 0;
  const summaryStrip = `
    <div class="sh-card-strip"
         style="grid-column: 1 / -1; padding: 8px 12px;
                background: var(--panel-2, #181d27);
                border: 1px solid var(--rule, #2a3242); border-radius: 3px;
                margin-bottom: 8px;
                display: flex; gap: 14px; flex-wrap: wrap; font-size: 11px;">
      <span><b>${atlasIds.length}</b> total</span>
      <span style="color: var(--good, #4ade80);"><b>${nRegistered}</b> registered</span>
      ${nFailed > 0
        ? `<span style="color: var(--bad, #ef4444);"><b>${nFailed}</b> failed</span>`
        : ''}
      ${manifests && nLoaded !== nRegistered
        ? `<span style="color: var(--ink-dim);"><b>${nLoaded - nRegistered}</b> discovered but unregistered</span>`
        : ''}
    </div>
  `;

  const cardsHtml = atlasIds.map(aid => {
    const manifest = manifests ? manifests.get(aid) : null;
    const conf = reg ? reg._atlases.get(aid) : null;
    const failedReason = failedByAtlas.get(aid) || null;

    // Per-atlas counts. Use registry confs when registered; fall back to
    // manifest declarations when only-discovered. Both can be 0 / missing.
    const nLayers = conf
      ? Object.keys(conf.layers || {}).filter(k => !k.startsWith('_')).length : 0;
    const nOps    = conf
      ? Object.keys(conf.operations || {}).filter(k => !k.startsWith('_')).length : 0;
    const nFiles  = conf
      ? Object.keys(conf.files || {}).filter(k => !k.startsWith('_')).length : 0;
    const nPages  = conf
      ? Object.keys(conf.pages || {}).filter(k => !k.startsWith('_')).length
      : (manifest && Array.isArray(manifest.pages) ? manifest.pages.length : 0);
    const nWorkflows = (conf && conf.workflows && Array.isArray(conf.workflows.workflows))
      ? conf.workflows.workflows.length : 0;
    const nPickers = (manifest && Array.isArray(manifest.scope_pickers))
      ? manifest.scope_pickers.length : 0;

    // Card state — drives the border color + status pill.
    let stateKind, stateLabel, stateColor;
    if (failedReason) {
      stateKind = 'failed';
      stateLabel = '⚠ failed to register';
      stateColor = 'var(--bad, #ef4444)';
    } else if (!conf) {
      stateKind = 'unregistered';
      stateLabel = '· not registered';
      stateColor = 'var(--ink-dim, #8895a8)';
    } else if (nLayers === 0 && nOps === 0 && nPages === 0) {
      stateKind = 'empty';
      stateLabel = '· empty (no layers / ops / pages)';
      stateColor = 'var(--accent, #f5a524)';
    } else {
      stateKind = 'registered';
      stateLabel = '✓ registered';
      stateColor = 'var(--good, #4ade80)';
    }

    // Ready bar — only meaningful when the atlas registered AND has layers.
    const layersOfAtlas = _state.allLayers.filter(L => L.atlas_id === aid);
    const nReady = layersOfAtlas.filter(L =>
      L.statusKind === 'ready' || L.statusKind === 'session_state').length;
    const pct = nLayers > 0 ? Math.round(100 * nReady / nLayers) : 0;
    const readyBar = (stateKind === 'registered' && nLayers > 0) ? `
      <div class="sh-card-ready">
        <div class="sh-bar"><div class="sh-bar-fill" style="width:${pct}%"></div></div>
        <div class="sh-bar-label">${nReady}/${nLayers} ready (${pct}%)</div>
      </div>` : '';

    const reasonHtml = failedReason ? `
      <div style="margin-top: 6px; padding: 6px 8px; background: rgba(239,68,68,0.10);
                  border-left: 2px solid var(--bad, #ef4444); border-radius: 2px;
                  font-size: 10.5px; word-break: break-word;">
        ${_esc(failedReason)}
      </div>` : '';

    return `
      <div class="sh-card" data-state="${stateKind}" style="border-left: 3px solid ${stateColor};">
        <div class="sh-card-title">
          ${_esc(aid)}
          <span style="float: right; font-size: 9.5px; font-weight: 400; color: ${stateColor};">
            ${_esc(stateLabel)}
          </span>
        </div>
        <div class="sh-card-stats">
          <span class="sh-stat"><b>${nPages}</b> pages</span>
          <span class="sh-stat"><b>${nLayers}</b> layers</span>
          <span class="sh-stat"><b>${nOps}</b> ops</span>
          ${nFiles > 0    ? `<span class="sh-stat"><b>${nFiles}</b> files</span>`     : ''}
          ${nWorkflows > 0? `<span class="sh-stat"><b>${nWorkflows}</b> workflows</span>` : ''}
          ${nPickers > 0  ? `<span class="sh-stat"><b>${nPickers}</b> pickers</span>`  : ''}
        </div>
        ${readyBar}
        ${reasonHtml}
      </div>
    `;
  }).join('');

  slot.innerHTML = summaryStrip + cardsHtml;
}

// ----- layer table ------------------------------------------------------
// 2026-05-26: dropdown now includes every discovered atlas (from
// __atlasManifests + failed list), not just those that contributed
// layers. Atlases with 0 layers get a "·" marker so the user can tell
// at a glance which selections will show an empty table.
function _populateLayerFilter() {
  const sel = document.getElementById('shLayerAtlasFilter');
  if (!sel) return;

  const manifests = (typeof window !== 'undefined' && window.__atlasManifests instanceof Map)
    ? window.__atlasManifests : null;
  const failedList = (typeof window !== 'undefined' && Array.isArray(window.__atlasFailedAtlases))
    ? window.__atlasFailedAtlases : [];

  const withLayers = new Set(_state.allLayers.map(L => L.atlas_id));
  const all = new Set([...withLayers]);
  if (manifests) for (const aid of manifests.keys()) all.add(aid);
  for (const f of failedList) all.add(f.atlas_id);

  const atlases = Array.from(all).sort();

  // Preserve the "all" option, replace the rest.
  const allOpt = Array.from(sel.options).find(o => o.value === '');
  sel.innerHTML = '';
  if (allOpt) sel.appendChild(allOpt);
  else {
    const o = document.createElement('option');
    o.value = ''; o.textContent = 'all atlases';
    sel.appendChild(o);
  }
  for (const aid of atlases) {
    const opt = document.createElement('option');
    opt.value = aid;
    opt.textContent = withLayers.has(aid) ? aid : `${aid} · 0 layers`;
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
    if (grid) grid.innerHTML = '<span class="sh-hint">Atlas has not finished booting yet — no registry and no manifests exposed.</span>';
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
