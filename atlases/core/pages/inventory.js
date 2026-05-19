// atlases/core/pages/inventory.js
// =============================================================================
// Inventory page — cross-atlas "what's loaded right now".
//
// Four sources, switched via the tab strip:
//   1. envelopes — GET /api/layers (action pipeline)
//   2. pages     — atlases/<id>/manifest.json `pages` array, per atlas
//   3. registries — atlases/<id>/registries/data/*.json, per atlas
//   4. toolkit   — toolkit_registries/relatedness/01_registry/*.tsv
//
// Each source loads lazily on first tab click and is then cached in memory.
// Clicking a left-tree row renders the underlying object in the right panel.
// All fetches are fail-soft: missing /api/layers or missing registry files
// surface an inline message rather than breaking the page.
// =============================================================================

import { listLayers, getLayer } from '../../../core/layer_api.js';

const TOOLKIT_ROOT = 'toolkit_registries/relatedness/';

// Same set the Catalogue + Registries pages already load — kept in sync here
// so the toolkit tab shows the same source of truth.
const TOOLKIT_TSVS = [
  ['sample_sets',      `${TOOLKIT_ROOT}01_registry/sample_sets.tsv`,      'sample_set_id'],
  ['group_sets',       `${TOOLKIT_ROOT}01_registry/group_sets.tsv`,       'group_set_id'],
  ['interval_sets',    `${TOOLKIT_ROOT}01_registry/interval_sets.tsv`,    'interval_set_id'],
  ['site_sets',        `${TOOLKIT_ROOT}01_registry/site_sets.tsv`,        'site_set_id'],
  ['input_values',     `${TOOLKIT_ROOT}01_registry/input_values.tsv`,     'value_id'],
  ['analysis_results', `${TOOLKIT_ROOT}01_registry/analysis_results.tsv`, 'result_id'],
  ['analysis_modes',   `${TOOLKIT_ROOT}01_registry/analysis_modes.tsv`,   null],
  ['module_registry',  `${TOOLKIT_ROOT}01_registry/module_registry.tsv`,  'module_name'],
];

// Richer JSONL catalogues that have no TSV mirror — the research-question
// content: atlas catalogue, products, questions, estimands, etc.
// Each entry: [name, path, key-field-for-row-title, label-field-for-row-title].
const TOOLKIT_JSONLS = [
  ['atlases',            `${TOOLKIT_ROOT}01_registry/atlases.jsonl`,            'atlas_id',     'label'],
  ['products',           `${TOOLKIT_ROOT}01_registry/products.jsonl`,           'product_id',   'label'],
  ['questions',          `${TOOLKIT_ROOT}01_registry/questions.jsonl`,          'question_id',  'label'],
  ['estimands',          `${TOOLKIT_ROOT}01_registry/estimands.jsonl`,          'estimand_id',  'label'],
  ['pages',              `${TOOLKIT_ROOT}01_registry/pages.jsonl`,              'page_id',      'label'],
  ['panels',             `${TOOLKIT_ROOT}01_registry/panels.jsonl`,             'panel_id',     'label'],
  ['layer_registry',     `${TOOLKIT_ROOT}01_registry/layer_registry.jsonl`,     'layer_id',     'label'],
  ['sample_attributes',  `${TOOLKIT_ROOT}01_registry/sample_attributes.jsonl`,  'attribute_id', 'label'],
  ['hook_registry',      `${TOOLKIT_ROOT}01_registry/hook_registry.jsonl`,      'hook_id',      'label'],
  ['analysis_registry',  `${TOOLKIT_ROOT}01_registry/analysis_registry.jsonl`,  'analysis_id',  'label'],
];

// Single-object JSON files (not JSONL, not TSV) worth surfacing.
const TOOLKIT_JSONS = [
  ['connection_map',  `${TOOLKIT_ROOT}01_registry/connection_map.json`,  'registry-graph map'],
];

// In-memory cache. Per-tab lazy load; populated on first activation.
const CACHE = {
  atlases: null,     // [{id, manifest}]
  envelopes: null,   // {ok: true, rows: [...]} | {ok: false, error: '...'}
  registries: null,  // {atlas_id: {regName: {ok, data|error}}}
  toolkit: null,     // {tsvName: {ok, rows|error}}
};

let CURRENT_TAB = 'envelopes';
let _wired = [];

function wire(el, evt, fn) {
  if (!el) return;
  el.addEventListener(evt, fn);
  _wired.push(() => el.removeEventListener(evt, fn));
}

function esc(s) {
  return String(s ?? '')
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

// ===== TSV loader (same shape as catalogue.js) =========================== //

function parseTSV(text) {
  const lines = text.split(/\r?\n/).filter(l => l.length > 0);
  if (lines.length === 0) return { header: [], rows: [] };
  const header = lines[0].split('\t');
  const rows = lines.slice(1).map(line => {
    const cols = line.split('\t');
    const row = {};
    header.forEach((h, j) => row[h] = cols[j] !== undefined ? cols[j] : '');
    return row;
  });
  return { header, rows };
}

async function fetchJson(path) {
  const resp = await fetch(path, { cache: 'no-store' });
  if (!resp.ok) throw new Error(`${path} → HTTP ${resp.status}`);
  return resp.json();
}

async function fetchTsv(path) {
  const resp = await fetch(path, { cache: 'no-store' });
  if (!resp.ok) throw new Error(`${path} → HTTP ${resp.status}`);
  return parseTSV(await resp.text());
}

// JSONL: one JSON object per line. Empty / whitespace lines skipped.
// Malformed lines surface as { _error, _line, _raw } so the renderer can
// flag them without aborting the whole file.
function parseJSONL(text) {
  const out = [];
  const lines = text.split(/\r?\n/);
  lines.forEach((raw, i) => {
    const line = raw.trim();
    if (!line) return;
    try { out.push(JSON.parse(line)); }
    catch (e) { out.push({ _error: e.message, _line: i + 1, _raw: raw }); }
  });
  return out;
}

async function fetchJsonl(path) {
  const resp = await fetch(path, { cache: 'no-store' });
  if (!resp.ok) throw new Error(`${path} → HTTP ${resp.status}`);
  return parseJSONL(await resp.text());
}

// ===== Atlas discovery =================================================== //

async function loadAtlases() {
  if (CACHE.atlases) return CACHE.atlases;
  const index = await fetchJson('atlases/_index.json');
  const ids = index.atlases || [];
  const out = [];
  for (const id of ids) {
    try {
      const manifest = await fetchJson(`atlases/${id}/manifest.json`);
      out.push({ id, manifest });
    } catch (e) {
      out.push({ id, manifest: null, error: e.message });
    }
  }
  CACHE.atlases = out;
  return out;
}

// ===== Source loaders ==================================================== //

async function loadEnvelopes() {
  if (CACHE.envelopes) return CACHE.envelopes;
  try {
    const result = await listLayers();
    CACHE.envelopes = { ok: true, rows: result.layers || result.rows || result || [] };
  } catch (e) {
    CACHE.envelopes = { ok: false, error: e.message };
  }
  return CACHE.envelopes;
}

async function loadAtlasRegistries() {
  if (CACHE.registries) return CACHE.registries;
  const atlases = await loadAtlases();
  const out = {};
  for (const { id, manifest } of atlases) {
    if (!manifest || !manifest.registries) { out[id] = {}; continue; }
    const perAtlas = {};
    for (const [name, path] of Object.entries(manifest.registries)) {
      try {
        perAtlas[name] = { ok: true, data: await fetchJson(path) };
      } catch (e) {
        perAtlas[name] = { ok: false, error: e.message };
      }
    }
    out[id] = perAtlas;
  }
  CACHE.registries = out;
  return out;
}

async function loadToolkitTsvs() {
  if (CACHE.toolkit) return CACHE.toolkit;
  const out = { tsv: {}, jsonl: {}, json: {} };
  for (const [name, path, key] of TOOLKIT_TSVS) {
    try {
      const parsed = await fetchTsv(path);
      out.tsv[name] = { kind: 'tsv', ok: true, header: parsed.header, rows: parsed.rows, key, path };
    } catch (e) {
      out.tsv[name] = { kind: 'tsv', ok: false, error: e.message, path };
    }
  }
  for (const [name, path, key, labelKey] of TOOLKIT_JSONLS) {
    try {
      const rows = await fetchJsonl(path);
      out.jsonl[name] = { kind: 'jsonl', ok: true, rows, key, labelKey, path };
    } catch (e) {
      out.jsonl[name] = { kind: 'jsonl', ok: false, error: e.message, path };
    }
  }
  for (const [name, path, desc] of TOOLKIT_JSONS) {
    try {
      const data = await fetchJson(path);
      out.json[name] = { kind: 'json', ok: true, data, desc, path };
    } catch (e) {
      out.json[name] = { kind: 'json', ok: false, error: e.message, desc, path };
    }
  }
  CACHE.toolkit = out;
  return out;
}

// ===== Rendering: left tree per tab ===================================== //

function renderEnvelopes(tree, detail, filter) {
  const c = CACHE.envelopes;
  if (!c) { tree.innerHTML = '<div class="inv-empty">loading…</div>'; return; }
  if (!c.ok) {
    tree.innerHTML =
      `<div class="inv-empty inv-warn">Action-pipeline server not reachable — ${esc(c.error)}.<br>` +
      'Start <code>atlas_server.py --workspace-root &lt;workspace&gt;</code> to populate this tab.</div>';
    return;
  }
  const rows = c.rows.filter(r => !filter ||
    JSON.stringify(r).toLowerCase().includes(filter));
  if (rows.length === 0) {
    tree.innerHTML = '<div class="inv-empty">No envelopes registered.</div>';
    return;
  }
  // Group by layer_type.
  const byType = {};
  for (const r of rows) {
    const t = r.layer_type || r.type || '(unknown)';
    (byType[t] ||= []).push(r);
  }
  const parts = [];
  for (const [type, list] of Object.entries(byType).sort()) {
    parts.push(`<div class="inv-group"><div class="inv-group-h">${esc(type)} <span class="inv-n">(${list.length})</span></div>`);
    for (const r of list) {
      const lid = r.layer_id || r.id || '(no id)';
      const ds  = r.dataset_id || '';
      parts.push(
        `<div class="inv-row" data-kind="envelope" data-layer-id="${esc(lid)}" tabindex="0">
           <div class="inv-row-1">${esc(lid)}</div>
           <div class="inv-row-2">${esc(ds)}${r.created_at ? ' · ' + esc(r.created_at) : ''}</div>
         </div>`);
    }
    parts.push('</div>');
  }
  tree.innerHTML = parts.join('');
}

function renderPagesTree(tree, _detail, filter) {
  const atlases = CACHE.atlases || [];
  const parts = [];
  for (const { id, manifest, error } of atlases) {
    if (!manifest) {
      parts.push(`<div class="inv-group"><div class="inv-group-h">${esc(id)} <span class="inv-warn">— ${esc(error || 'no manifest')}</span></div></div>`);
      continue;
    }
    const pages = (manifest.pages || []).filter(p => !filter ||
      (p.id + ' ' + (p.label || '') + ' ' + (p.tooltip || '')).toLowerCase().includes(filter));
    if (pages.length === 0 && filter) continue;
    parts.push(`<div class="inv-group"><div class="inv-group-h">${esc(id)} <span class="inv-n">(${pages.length})</span></div>`);
    for (const p of pages) {
      parts.push(
        `<div class="inv-row" data-kind="page" data-atlas-id="${esc(id)}" data-page-id="${esc(p.id)}" tabindex="0">
           <div class="inv-row-1">${esc(p.label || p.id)}</div>
           <div class="inv-row-2">${esc(p.id)}${p.stage ? ' · ' + esc(p.stage) : ''}</div>
         </div>`);
    }
    parts.push('</div>');
  }
  tree.innerHTML = parts.join('') || '<div class="inv-empty">No matches.</div>';
}

function renderRegistriesTree(tree, _detail, filter) {
  const regs = CACHE.registries || {};
  const parts = [];
  for (const [aid, perAtlas] of Object.entries(regs)) {
    const entries = Object.entries(perAtlas).filter(([n]) =>
      !filter || (aid + ' ' + n).toLowerCase().includes(filter));
    if (entries.length === 0) continue;
    parts.push(`<div class="inv-group"><div class="inv-group-h">${esc(aid)} <span class="inv-n">(${entries.length})</span></div>`);
    for (const [name, slot] of entries) {
      const sub = slot.ok
        ? countRegistryEntries(name, slot.data)
        : `<span class="inv-warn">missing — ${esc(slot.error)}</span>`;
      parts.push(
        `<div class="inv-row" data-kind="registry" data-atlas-id="${esc(aid)}" data-reg-name="${esc(name)}" tabindex="0">
           <div class="inv-row-1">${esc(name)}</div>
           <div class="inv-row-2">${sub}</div>
         </div>`);
    }
    parts.push('</div>');
  }
  tree.innerHTML = parts.join('') || '<div class="inv-empty">No matches.</div>';
}

function countRegistryEntries(name, data) {
  // Best-effort: most atlas registries have a top-level object like
  // { pages: { ... } } or { layers: { ... } }. Show entry count.
  if (!data || typeof data !== 'object') return '(empty)';
  const dict = data.pages || data.layers || data.files || data.operations
            || data.slots || data;
  if (dict && typeof dict === 'object') {
    const n = Object.keys(dict).filter(k => !k.startsWith('_') && k !== '$schema').length;
    return `${n} entr${n === 1 ? 'y' : 'ies'}`;
  }
  return '';
}

function renderToolkitTree(tree, _detail, filter) {
  const t = CACHE.toolkit || {};
  const parts = [];

  // Section: JSONL catalogues first (richer content — atlas/products/questions).
  const jsonlEntries = Object.entries(t.jsonl || {})
    .filter(([n]) => !filter || n.toLowerCase().includes(filter));
  if (jsonlEntries.length > 0) {
    parts.push('<div class="inv-group"><div class="inv-group-h">Records (JSONL)</div>');
    for (const [name, slot] of jsonlEntries) {
      const sub = slot.ok
        ? `${slot.rows.length} record${slot.rows.length === 1 ? '' : 's'}`
        : `<span class="inv-warn">missing — ${esc(slot.error)}</span>`;
      parts.push(
        `<div class="inv-row" data-kind="toolkit-jsonl" data-tsv-name="${esc(name)}" tabindex="0">
           <div class="inv-row-1">${esc(name)}</div>
           <div class="inv-row-2">${sub}</div>
         </div>`);
    }
    parts.push('</div>');
  }

  // Section: single-object JSON files (graphs / configs).
  const jsonEntries = Object.entries(t.json || {})
    .filter(([n]) => !filter || n.toLowerCase().includes(filter));
  if (jsonEntries.length > 0) {
    parts.push('<div class="inv-group"><div class="inv-group-h">Files (JSON)</div>');
    for (const [name, slot] of jsonEntries) {
      const sub = slot.ok
        ? esc(slot.desc || '')
        : `<span class="inv-warn">missing — ${esc(slot.error)}</span>`;
      parts.push(
        `<div class="inv-row" data-kind="toolkit-json" data-tsv-name="${esc(name)}" tabindex="0">
           <div class="inv-row-1">${esc(name)}</div>
           <div class="inv-row-2">${sub}</div>
         </div>`);
    }
    parts.push('</div>');
  }

  // Section: TSV tables (sets, modes, results).
  const tsvEntries = Object.entries(t.tsv || {})
    .filter(([n]) => !filter || n.toLowerCase().includes(filter));
  if (tsvEntries.length > 0) {
    parts.push('<div class="inv-group"><div class="inv-group-h">Tables (TSV)</div>');
    for (const [name, slot] of tsvEntries) {
      const sub = slot.ok
        ? `${slot.rows.length} row${slot.rows.length === 1 ? '' : 's'} · ${slot.header.length} col${slot.header.length === 1 ? '' : 's'}`
        : `<span class="inv-warn">missing — ${esc(slot.error)}</span>`;
      parts.push(
        `<div class="inv-row" data-kind="toolkit-tsv" data-tsv-name="${esc(name)}" tabindex="0">
           <div class="inv-row-1">${esc(name)}</div>
           <div class="inv-row-2">${sub}</div>
         </div>`);
    }
    parts.push('</div>');
  }

  tree.innerHTML = parts.join('') || '<div class="inv-empty">No matches.</div>';
}

// ===== Rendering: right detail panel ==================================== //

function renderJsonDetail(detail, title, obj) {
  const json = esc(JSON.stringify(obj, null, 2));
  detail.innerHTML =
    `<div class="inv-det-h">${esc(title)}</div>` +
    `<pre class="inv-json">${json}</pre>`;
}

async function showEnvelopeDetail(detail, layer_id) {
  detail.innerHTML = `<div class="inv-det-h">${esc(layer_id)}</div><div class="inv-empty">loading…</div>`;
  try {
    const env = await getLayer(layer_id);
    renderJsonDetail(detail, layer_id, env);
  } catch (e) {
    detail.innerHTML = `<div class="inv-det-h">${esc(layer_id)}</div><div class="inv-empty inv-warn">fetch failed — ${esc(e.message)}</div>`;
  }
}

function showPageDetail(detail, atlas_id, page_id) {
  const a = (CACHE.atlases || []).find(x => x.id === atlas_id);
  const p = a && (a.manifest.pages || []).find(x => x.id === page_id);
  if (!p) { detail.innerHTML = '<div class="inv-empty inv-warn">page entry not found</div>'; return; }
  renderJsonDetail(detail, `${atlas_id} / ${page_id}`, p);
}

function showRegistryDetail(detail, atlas_id, reg_name) {
  const slot = (CACHE.registries[atlas_id] || {})[reg_name];
  if (!slot) { detail.innerHTML = '<div class="inv-empty inv-warn">not loaded</div>'; return; }
  if (!slot.ok) { detail.innerHTML = `<div class="inv-empty inv-warn">missing — ${esc(slot.error)}</div>`; return; }
  renderJsonDetail(detail, `${atlas_id} / ${reg_name}.registry.json`, slot.data);
}

function showToolkitTsvDetail(detail, tsv_name) {
  const slot = (CACHE.toolkit?.tsv || {})[tsv_name];
  if (!slot) { detail.innerHTML = '<div class="inv-empty inv-warn">not loaded</div>'; return; }
  if (!slot.ok) { detail.innerHTML = `<div class="inv-empty inv-warn">missing — ${esc(slot.error)}</div>`; return; }
  const { header, rows, path } = slot;
  const head = header.map(h => `<th>${esc(h)}</th>`).join('');
  const body = rows.slice(0, 500).map(r =>
    '<tr>' + header.map(h => `<td>${esc(r[h])}</td>`).join('') + '</tr>').join('');
  const trunc = rows.length > 500 ? `<div class="inv-trunc">showing first 500 of ${rows.length} rows</div>` : '';
  detail.innerHTML =
    `<div class="inv-det-h">${esc(tsv_name)} <span class="inv-det-sub">${esc(path)}</span></div>` +
    `<div class="inv-tbl-wrap"><table class="inv-tbl"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>` +
    trunc;
}

function showToolkitJsonDetail(detail, name) {
  const slot = (CACHE.toolkit?.json || {})[name];
  if (!slot) { detail.innerHTML = '<div class="inv-empty inv-warn">not loaded</div>'; return; }
  if (!slot.ok) { detail.innerHTML = `<div class="inv-empty inv-warn">missing — ${esc(slot.error)}</div>`; return; }
  renderJsonDetail(detail, `${name} — ${slot.path}`, slot.data);
}

function showToolkitJsonlDetail(detail, name) {
  const slot = (CACHE.toolkit?.jsonl || {})[name];
  if (!slot) { detail.innerHTML = '<div class="inv-empty inv-warn">not loaded</div>'; return; }
  if (!slot.ok) { detail.innerHTML = `<div class="inv-empty inv-warn">missing — ${esc(slot.error)}</div>`; return; }
  const { rows, key, labelKey, path } = slot;
  const cards = rows.slice(0, 500).map((r, i) => {
    if (r._error) {
      return `<details class="inv-rec inv-rec-err"><summary>line ${esc(r._line)} — parse error: ${esc(r._error)}</summary><pre class="inv-json">${esc(r._raw)}</pre></details>`;
    }
    const id = r[key] || `(row ${i + 1})`;
    const lab = labelKey && r[labelKey] ? r[labelKey] : '';
    const sum = lab ? `${esc(id)} <span class="inv-rec-lab">${esc(lab)}</span>` : esc(id);
    return `<details class="inv-rec"><summary>${sum}</summary><pre class="inv-json">${esc(JSON.stringify(r, null, 2))}</pre></details>`;
  }).join('');
  const trunc = rows.length > 500 ? `<div class="inv-trunc">showing first 500 of ${rows.length} records</div>` : '';
  detail.innerHTML =
    `<div class="inv-det-h">${esc(name)} <span class="inv-det-sub">${esc(path)}</span></div>` +
    cards + trunc;
}

// ===== Tab activation =================================================== //

async function activateTab(root, tabId) {
  CURRENT_TAB = tabId;
  for (const b of root.querySelectorAll('.inv-tab')) {
    b.classList.toggle('active', b.dataset.tab === tabId);
  }
  const tree = root.querySelector('#inv-tree');
  const detail = root.querySelector('#inv-detail');
  detail.innerHTML = '<div class="inv-empty">Select a row on the left.</div>';
  tree.innerHTML = '<div class="inv-empty">loading…</div>';

  await loadAtlases();
  if (tabId === 'envelopes')      await loadEnvelopes();
  else if (tabId === 'registries') await loadAtlasRegistries();
  else if (tabId === 'toolkit')   await loadToolkitTsvs();

  applyFilter(root);
}

function applyFilter(root) {
  const tree = root.querySelector('#inv-tree');
  const detail = root.querySelector('#inv-detail');
  const filterEl = root.querySelector('#inv-filter');
  const filter = (filterEl?.value || '').trim().toLowerCase();
  if (CURRENT_TAB === 'envelopes')       renderEnvelopes(tree, detail, filter);
  else if (CURRENT_TAB === 'pages')      renderPagesTree(tree, detail, filter);
  else if (CURRENT_TAB === 'registries') renderRegistriesTree(tree, detail, filter);
  else if (CURRENT_TAB === 'toolkit')    renderToolkitTree(tree, detail, filter);
}

// ===== mount / unmount ================================================== //

export async function mount(root, _ctx = {}) {
  wire(root.querySelector('#inv-tabs'), 'click', (e) => {
    const t = e.target.closest('.inv-tab');
    if (!t || !root.contains(t)) return;
    activateTab(root, t.dataset.tab);
  });

  wire(root.querySelector('#inv-filter'), 'input', () => applyFilter(root));

  wire(root.querySelector('#inv-tree'), 'click', (e) => {
    const row = e.target.closest('.inv-row');
    if (!row || !root.contains(row)) return;
    const detail = root.querySelector('#inv-detail');
    const kind = row.dataset.kind;
    if (kind === 'envelope') showEnvelopeDetail(detail, row.dataset.layerId);
    else if (kind === 'page')     showPageDetail(detail, row.dataset.atlasId, row.dataset.pageId);
    else if (kind === 'registry')     showRegistryDetail(detail, row.dataset.atlasId, row.dataset.regName);
    else if (kind === 'toolkit-tsv')   showToolkitTsvDetail(detail, row.dataset.tsvName);
    else if (kind === 'toolkit-jsonl') showToolkitJsonlDetail(detail, row.dataset.tsvName);
    else if (kind === 'toolkit-json')  showToolkitJsonDetail(detail, row.dataset.tsvName);
  });

  // Initial load: envelopes (the most volatile source).
  await activateTab(root, 'envelopes');
}

export async function unmount(_root) {
  for (const off of _wired) off();
  _wired = [];
  CURRENT_TAB = 'envelopes';
}
