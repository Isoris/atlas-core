// atlases/core/pages/catalogue.js
// =============================================================================
// Catalogue page — modules and analyses browser.
//
// Round-1 migration from toolkit_registries/relatedness/page/catalogue.html.
// Same logic; the differences from the original:
//   - Inline <script> body wrapped in a module with mount()/unmount().
//   - All element lookups scoped to the page root.
//   - Tab and filter listeners are registered in mount() and detached in
//     unmount() so navigating away does not leave stale handlers.
//   - Registry-data fetches go through REGISTRY_ROOT + '01_registry/...'.
//   - Hover popovers come from the shared previews module.
// =============================================================================

import { ensurePreviewsInstalled } from './previews.js';

const REGISTRY_ROOT = 'toolkit_registries/relatedness/';

// ===== TSV loader ===================================================== //

function parseTSV(text) {
  const lines = text.split(/\r?\n/).filter(l => l.length > 0);
  if (lines.length === 0) return [];
  const header = lines[0].split('\t');
  return lines.slice(1).map(line => {
    const cols = line.split('\t');
    const row = {};
    header.forEach((h, j) => row[h] = cols[j] !== undefined ? cols[j] : '');
    return row;
  });
}

async function fetchTsv(rel, optional = false) {
  try {
    const resp = await fetch(rel, { cache: 'no-store' });
    if (!resp.ok) throw new Error(`${rel} → HTTP ${resp.status}`);
    return parseTSV(await resp.text());
  } catch (e) {
    if (optional) return [];
    throw e;
  }
}

let DB = { modules: [], modes: [], moduleBy: {} };

async function loadAll() {
  DB.modules = await fetchTsv(`${REGISTRY_ROOT}01_registry/module_registry.tsv`, true);
  DB.modes   = await fetchTsv(`${REGISTRY_ROOT}01_registry/analysis_modes.tsv`);
  DB.moduleBy = Object.fromEntries(DB.modules.map(m => [m.module_name, m]));
}

// ===== Wiring helpers ================================================== //

function modesUsingModule(moduleName) {
  return DB.modes.filter(m => m.module_name === moduleName);
}

const REQ_TO_PRODUCES = {
  ngsrelate_result: 'relatedness_res',
  pedigree_result:  'pedigree_result',
  mendelian_result: 'mendelian_result',
  relatedness_res:  'relatedness_res',
};

function downstreamOfModule(moduleName) {
  const produced = new Set();
  for (const m of modesUsingModule(moduleName)) {
    if (m.produces) produced.add(m.produces);
  }
  if (produced.size === 0) return [];
  const out = [];
  for (const mode of DB.modes) {
    const required = (mode.required_dimensions || '').split(',').map(s => s.trim());
    for (const dim of required) {
      const tag = REQ_TO_PRODUCES[dim];
      if (tag && produced.has(tag)) {
        if (mode.module_name && mode.module_name !== moduleName) {
          out.push({ module: mode.module_name, via_mode: `${mode.analysis_type}/${mode.mode}`, via_dim: dim });
        }
      }
    }
  }
  const seen = new Set();
  return out.filter(o => seen.has(o.module) ? false : (seen.add(o.module), true));
}

function upstreamOfModule(moduleName) {
  const myModes = modesUsingModule(moduleName);
  const requiredTags = new Set();
  for (const m of myModes) {
    for (const dim of (m.required_dimensions || '').split(',').map(s => s.trim())) {
      const tag = REQ_TO_PRODUCES[dim];
      if (tag) requiredTags.add(tag);
    }
  }
  if (requiredTags.size === 0) return [];
  const out = [];
  for (const mode of DB.modes) {
    if (requiredTags.has(mode.produces) && mode.module_name && mode.module_name !== moduleName) {
      out.push({ module: mode.module_name, via_mode: `${mode.analysis_type}/${mode.mode}`, via_tag: mode.produces });
    }
  }
  const seen = new Set();
  return out.filter(o => seen.has(o.module) ? false : (seen.add(o.module), true));
}

function moduleStatusClass(m) {
  if (!m) return 'mod-conceptual';
  if (m.installed !== 'true') return 'mod-not-installed';
  if (m.last_run_status === 'failed') return 'mod-failed';
  if (m.stale === 'true') return 'mod-stale';
  if (m.ready === 'true') return 'mod-ready';
  return 'mod-available';
}

function moduleStatusLabel(m) {
  if (!m) return 'conceptual';
  if (m.installed !== 'true') return 'not installed';
  if (m.last_run_status === 'failed') return 'last run failed';
  if (m.stale === 'true') return 'stale';
  if (m.ready === 'true') return 'ready';
  return 'available';
}

// ===== Render — modules tab ============================================ //

function renderModuleCard(m) {
  const cls    = moduleStatusClass(m);
  const label  = moduleStatusLabel(m);
  const modes  = modesUsingModule(m.module_name);
  const ups    = upstreamOfModule(m.module_name);
  const downs  = downstreamOfModule(m.module_name);

  const modesList = modes.length
    ? modes.map(mo => `<span class="chip">${mo.analysis_type}/${mo.mode}</span>`).join('')
    : '<span style="color:var(--muted)">(no analysis_modes row references this module yet)</span>';

  const modCode = (name) => `<code data-preview-table="module_registry" data-preview-id="${name}">${name}</code>`;
  const lineage = (ups.length || downs.length) ? `<div class="lineage">
    ${ups.map(u => `<span>${modCode(u.module)} <span class="arrow">→</span></span>`).join('')}
    <code style="font-weight:600" data-preview-table="module_registry" data-preview-id="${m.module_name}">${m.module_name}</code>
    ${downs.map(d => `<span><span class="arrow">→</span> ${modCode(d.module)}</span>`).join('')}
  </div>` : '';

  return `
    <div class="card ${cls}">
      <div class="head">
        <span class="name" data-preview-table="module_registry" data-preview-id="${m.module_name}">${m.module_name}</span>
        <span class="meta">v${m.version} · family=${m.family} · biomod_status=${m.biomod_status || '?'}</span>
        <span class="pill">${label}</span>
      </div>
      ${lineage}
      <dl>
        <dt>used by</dt><dd>${modesList}</dd>
        <dt>produces</dt><dd>${[...new Set(modes.map(mo => mo.produces).filter(Boolean))].map(p => `<span class="chip">${p}</span>`).join('') || '—'}</dd>
        <dt>parent</dt><dd>${m.parent || '—'}</dd>
        <dt>derivatives</dt><dd>${m.derivatives ? m.derivatives.split(',').map(d => `<span class="chip">${d}</span>`).join('') : '—'}</dd>
        <dt>last run</dt><dd>${m.last_run_id
            ? `${m.last_run_status} · QC ${m.last_run_qc || '?'} · ${m.last_run_seconds || '?'}s · n_samples=${m.n_samples || '?'} · <code>${m.last_run_id.slice(0,8)}…</code>`
            : '—'}</dd>
        <dt>conda env</dt><dd>${m.conda_env_path || '—'}</dd>
      </dl>
    </div>`;
}

function renderModules(root, filter) {
  const out = root.querySelector('#modules');
  if (DB.modules.length === 0) {
    out.innerHTML = `<div class="empty">No modules in <code>module_registry.tsv</code> yet.<br>
      Run <code>python3 scripts/sync_biomod_status.py --from-json 01_registry/biomod_status.example.json</code>
      to populate the example.</div>`;
    return;
  }
  const q = (filter || '').toLowerCase();
  const ms = DB.modules.filter(m => !q || (m.module_name + ' ' + m.family + ' ' + m.biomod_status).toLowerCase().includes(q));
  if (ms.length === 0) { out.innerHTML = '<div class="empty">No modules match the filter.</div>'; return; }
  out.innerHTML = ms.map(renderModuleCard).join('');
}

// ===== Render — analyses tab =========================================== //

function renderAnalysisCard(mode) {
  const m = DB.moduleBy[mode.module_name];
  const cls = moduleStatusClass(m);
  const label = moduleStatusLabel(m);

  const upstream = (mode.required_dimensions || '').split(',')
    .map(s => s.trim())
    .filter(s => REQ_TO_PRODUCES[s])
    .map(s => `<span class="chip">${s}</span>`).join('');

  return `
    <div class="card ${cls}">
      <div class="head">
        <span class="name">${mode.analysis_type}/${mode.mode}</span>
        <span class="meta">${mode.label || ''}</span>
        <span class="pill">${label}</span>
      </div>
      <dl>
        <dt>module</dt><dd>${mode.module_name ? `<code>${mode.module_name}</code>` + (m ? ` v${m.version}` : '') : '—'}</dd>
        <dt>requires</dt><dd>${(mode.required_dimensions || '').split(',').map(s => `<span class="chip">${s.trim()}</span>`).join('') || '—'}</dd>
        <dt>upstream tags</dt><dd>${upstream || '—'}</dd>
        <dt>produces</dt><dd><span class="chip">${mode.produces || '—'}</span></dd>
        <dt>interval policy</dt><dd>${mode.interval_policy || '—'}</dd>
        <dt>site policy</dt><dd>${mode.site_policy || '—'}</dd>
        <dt>group policy</dt><dd>${mode.group_policy || '—'}</dd>
        <dt>value policy</dt><dd>${mode.value_policy || '—'}</dd>
      </dl>
    </div>`;
}

function renderAnalyses(root, filter) {
  const out = root.querySelector('#analyses');
  const q = (filter || '').toLowerCase();
  const ms = DB.modes.filter(m => !q || (`${m.analysis_type}/${m.mode} ${m.label} ${m.module_name}`).toLowerCase().includes(q));
  if (ms.length === 0) { out.innerHTML = '<div class="empty">No analyses match the filter.</div>'; return; }
  out.innerHTML = ms.map(renderAnalysisCard).join('');
}

// ===== Tab + filter wiring ============================================= //

let CURRENT = 'modules';

function applyFilter(root) {
  const f = root.querySelector('#filter').value.trim();
  renderModules(root, f);
  renderAnalyses(root, f);
  const visible = root.querySelector('#' + CURRENT);
  const total = CURRENT === 'modules' ? DB.modules.length : DB.modes.length;
  const shown = visible.querySelectorAll('.card').length;
  root.querySelector('#stat').textContent = `${shown} / ${total} shown`;
}

// ===== Lifecycle ======================================================= //

let _tabsHandler = null;
let _filterHandler = null;
let _tabsEl = null;
let _filterEl = null;

export async function mount(root, _atlasState, _registry) {
  ensurePreviewsInstalled(REGISTRY_ROOT);
  DB = { modules: [], modes: [], moduleBy: {} };
  CURRENT = 'modules';
  try {
    await loadAll();
    window.DB = {
      module_registry: { rows: DB.modules, by: DB.moduleBy },
      analysis_modes:  { rows: DB.modes },
      modules:  DB.modules, modes: DB.modes, moduleBy: DB.moduleBy,
    };
    root.querySelector('#count-modules').textContent  = `(${DB.modules.length})`;
    root.querySelector('#count-analyses').textContent = `(${DB.modes.length})`;
    applyFilter(root);
    root.querySelector('#footer').innerHTML =
      `<strong>Modules</strong> loaded from <code>${REGISTRY_ROOT}01_registry/module_registry.tsv</code> (mirror of <code>biomod status --json</code>) · ` +
      `<strong>Analyses</strong> loaded from <code>${REGISTRY_ROOT}01_registry/analysis_modes.tsv</code> · ` +
      'Wiring derived from <code>analysis_modes.required_dimensions</code> ↔ <code>analysis_modes.produces</code> (e.g. <code>ngsrelate</code> produces <code>relatedness_res</code>, which <code>ngspedigree</code> requires as <code>ngsrelate_result</code>).';

    _tabsEl = root.querySelector('.tabs');
    _tabsHandler = (e) => {
      const t = e.target.closest('.tab');
      if (!t) return;
      CURRENT = t.dataset.tab;
      for (const x of root.querySelectorAll('.tab'))  x.classList.toggle('active', x.dataset.tab === CURRENT);
      for (const x of root.querySelectorAll('.view')) x.style.display = (x.id === CURRENT) ? '' : 'none';
      applyFilter(root);
    };
    _tabsEl.addEventListener('click', _tabsHandler);

    _filterEl = root.querySelector('#filter');
    _filterHandler = () => applyFilter(root);
    _filterEl.addEventListener('input', _filterHandler);
  } catch (e) {
    root.insertAdjacentHTML('beforeend',
      `<div class="error">Failed to load registry: ${e.message}.<br>Ensure the assembled workspace contains <code>${REGISTRY_ROOT}01_registry/</code>.</div>`);
  }
}

export async function unmount(_root) {
  if (_tabsEl && _tabsHandler) _tabsEl.removeEventListener('click', _tabsHandler);
  if (_filterEl && _filterHandler) _filterEl.removeEventListener('input', _filterHandler);
  _tabsEl = null; _filterEl = null;
  _tabsHandler = null; _filterHandler = null;
}
