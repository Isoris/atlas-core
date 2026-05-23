// atlases/core/pages/registries.js
// =============================================================================
// Registries page — chains and compatibility browser + brick-edit sidebar.
//
// Round-1 migration from toolkit_registries/relatedness/page/index.html.
// Same logic; per-page helpers were unchanged. The differences:
//   - Inline <script> body wrapped in a module with mount()/unmount().
//   - All element lookups scoped to the page root (`root.querySelector`).
//   - The two delegated `document.addEventListener` handlers (brick click,
//     Enter/Space activation, Escape-to-close) are kept as document-level
//     listeners — but their references are stored so unmount() detaches them.
//   - Registry-data fetches go through REGISTRY_ROOT + '01_registry/...'.
//   - Hover popovers come from the shared previews module.
// =============================================================================

import { ensurePreviewsInstalled } from './previews.js';

const REGISTRY_ROOT = 'toolkit_registries/relatedness/';

// ===== TSV loader ======================================================= //

function parseTSV(text) {
  const lines = text.split(/\r?\n/).filter(l => l.length > 0);
  if (lines.length === 0) return [];
  const header = lines[0].split('\t');
  const rows = [];
  for (let i = 1; i < lines.length; i++) {
    const cols = lines[i].split('\t');
    const row = {};
    header.forEach((h, j) => row[h] = cols[j] !== undefined ? cols[j] : '');
    rows.push(row);
  }
  return rows;
}

async function fetchTsv(rel) {
  const resp = await fetch(rel, { cache: 'no-store' });
  if (!resp.ok) throw new Error(`${rel} → HTTP ${resp.status}`);
  return parseTSV(await resp.text());
}

const TSVS = [
  ['sample_sets',      `${REGISTRY_ROOT}01_registry/sample_sets.tsv`,      'sample_set_id'],
  ['group_sets',       `${REGISTRY_ROOT}01_registry/group_sets.tsv`,       'group_set_id'],
  ['interval_sets',    `${REGISTRY_ROOT}01_registry/interval_sets.tsv`,    'interval_set_id'],
  ['site_sets',        `${REGISTRY_ROOT}01_registry/site_sets.tsv`,        'site_set_id'],
  ['input_values',     `${REGISTRY_ROOT}01_registry/input_values.tsv`,     'value_id'],
  ['analysis_results', `${REGISTRY_ROOT}01_registry/analysis_results.tsv`, 'result_id'],
  ['analysis_modes',   `${REGISTRY_ROOT}01_registry/analysis_modes.tsv`,   null],
  ['module_registry',  `${REGISTRY_ROOT}01_registry/module_registry.tsv`,  'module_name'],
];

let DB = {};

async function loadAll(root) {
  for (const [name, path, key] of TSVS) {
    let rows;
    try {
      rows = await fetchTsv(path);
    } catch (e) {
      if (name === 'module_registry') {
        rows = [];
      } else {
        const c = root.querySelector('#chains');
        c.innerHTML = `<div class="error">Could not load ${path} — ${e.message}.<br>
          Ensure the assembled workspace contains <code>${REGISTRY_ROOT}01_registry/</code>.</div>`;
        throw e;
      }
    }
    if (key) {
      const m = {}; for (const r of rows) if (r[key]) m[r[key]] = r;
      DB[name] = { rows, by: m };
    } else {
      DB[name] = { rows };
    }
  }
}

// ===== Compatibility logic ============================================= //

function produceTagOf(analysisType) {
  const modes = (DB.analysis_modes && DB.analysis_modes.rows) || [];
  for (const m of modes) {
    if (m.analysis_type === analysisType) return m.produces;
  }
  return '';
}

function consumersOf(producedTag) {
  if (!producedTag) return [];
  const out = [];
  const modes = (DB.analysis_modes && DB.analysis_modes.rows) || [];
  for (const m of modes) {
    const req = (m.required_dimensions || '').split(',').map(s => s.trim());
    if (req.includes(producedTag.replace('_res', '_result'))
        || req.includes(producedTag)
        || (producedTag === 'relatedness_res' && req.includes('ngsrelate_result'))
        || (producedTag === 'pedigree_result'  && req.includes('pedigree_result'))) {
      out.push(`${m.analysis_type}/${m.mode}`);
    }
  }
  return [...new Set(out)];
}

function buildChains() {
  const results = (DB.analysis_results && DB.analysis_results.rows) || [];
  const downstream = {};
  for (const r of results) {
    if (r.input_result_id) {
      (downstream[r.input_result_id] = downstream[r.input_result_id] || []).push(r.result_id);
    }
  }

  const heads = results.filter(r => !r.input_result_id);

  const chains = [];
  function walk(rid, path) {
    path = [...path, rid];
    const kids = downstream[rid] || [];
    if (kids.length === 0) { chains.push(path); return; }
    for (const k of kids) walk(k, path);
  }
  for (const h of heads) walk(h.result_id, []);

  const longerCovers = new Set();
  for (const c of chains) {
    if (c.length > 1) for (const id of c) longerCovers.add(id);
  }
  return chains.filter(c => c.length > 1 || !longerCovers.has(c[0]));
}

function contractStatus(r) {
  const checks = [
    ['sample_set_id',   'sample_sets'],
    ['group_set_id',    'group_sets'],
    ['interval_set_id', 'interval_sets'],
    ['site_set_id',     'site_sets'],
    ['input_value_id',  'input_values'],
    ['input_result_id', 'analysis_results'],
  ];
  for (const [col, table] of checks) {
    const v = r[col];
    if (v && !DB[table].by[v]) return { ok: false, why: `unknown ${col}: ${v}` };
  }
  return { ok: true };
}

function moduleStatusForAnalysisType(analysisType) {
  if (!analysisType) return null;
  const modeRow = (DB.analysis_modes && DB.analysis_modes.rows || [])
    .find(m => m.analysis_type === analysisType && m.module_name);
  if (!modeRow) return null;
  const moduleRow = (DB.module_registry && DB.module_registry.by || {})[modeRow.module_name];
  return { module_name: modeRow.module_name, row: moduleRow || null };
}

function moduleBadge(analysisType) {
  const m = moduleStatusForAnalysisType(analysisType);
  if (!m) return '';
  if (!m.row) {
    return `<span class="badge mod-conceptual" title="${m.module_name} not in module_registry.tsv">mod: ${m.module_name} (conceptual)</span>`;
  }
  const r = m.row;
  if (r.installed !== 'true') return '<span class="badge mod-not-installed">mod: not installed</span>';
  if (r.last_run_status === 'failed') return `<span class="badge mod-failed">mod: ${r.module_name} ${r.version} — last run failed</span>`;
  if (r.stale === 'true') return `<span class="badge mod-stale">mod: ${r.module_name} stale</span>`;
  if (r.ready === 'true') return `<span class="badge mod-ready">mod: ${r.module_name} ${r.version} ✓</span>`;
  return `<span class="badge mod-available">mod: ${r.module_name} ${r.version}</span>`;
}

function readyForFor(r) {
  const out = [];
  const myProduces = produceTagOf(r.analysis_type);
  if (!myProduces) return out;
  const consumers = consumersOf(myProduces);
  for (const consumerKey of consumers) {
    const [consumerType] = consumerKey.split('/');
    const wired = (DB.analysis_results.rows || []).some(other =>
      other.analysis_type === consumerType && other.input_result_id === r.result_id
    );
    if (wired) continue;
    out.push(consumerKey);
  }
  return out;
}

// ===== Rendering ====================================================== //

function classFor(analysisType) {
  if (analysisType === 'ngsrelate' || analysisType === 'ngspedigree' || analysisType === 'mendelian') {
    return analysisType;
  }
  return 'other';
}

function stepCard(r) {
  const cls = classFor(r.analysis_type);
  const cs = contractStatus(r);
  const readyFor = readyForFor(r);

  const upstream = r.input_result_id ? '<span class="badge compat-in">upstream ✓</span>' : '';
  const ready    = readyFor.map(c => `<span class="badge ready-for">ready for ${c}</span>`).join('');
  const failBadge = !cs.ok ? `<span class="badge contract-fail">${cs.why}</span>` : '';

  const pv = (tbl, id) => id ? `<span data-preview-table="${tbl}" data-preview-id="${id}">${id}</span>` : '—';
  return `
    <div class="step ${cls}" data-brick-rid="${r.result_id}" tabindex="0" role="button" aria-label="Edit ${r.analysis_type} brick">
      <div class="ana">${r.analysis_type}</div>
      <div class="rid" data-preview-table="analysis_results" data-preview-id="${r.result_id}">${r.result_id}</div>
      <div class="meta">
        <div><span class="k">samples</span> ${pv('sample_sets',  r.sample_set_id)}</div>
        <div><span class="k">interval</span> ${pv('interval_sets',r.interval_set_id)}</div>
        <div><span class="k">sites</span> ${pv('site_sets',    r.site_set_id)}</div>
        <div><span class="k">value</span> ${pv('input_values', r.input_value_id)}</div>
        ${r.input_result_id ? `<div><span class="k">input_result</span> ${pv('analysis_results', r.input_result_id)}</div>` : ''}
      </div>
      <div>${upstream}${ready}${failBadge}${moduleBadge(r.analysis_type)}</div>
    </div>`;
}

function arrow() { return '<div class="arrow">→</div>'; }

function renderChains(root, filtered) {
  const chains = buildChains();
  const visible = chains.filter(c => c.some(rid => filtered.has(rid)));

  const el = root.querySelector('#chains');
  if (visible.length === 0) {
    el.innerHTML = '<div class="empty">No chains match the current filters.</div>';
    return;
  }

  let html = '';
  for (const ridList of visible) {
    const results = ridList.map(rid => DB.analysis_results.by[rid]);
    const head = results[0];
    const chainKind = results.map(r => r.analysis_type).join(' → ');
    const allOk = results.every(r => contractStatus(r).ok);

    html += `<div class="chain">
      <div class="chain-meta">
        <div class="heading">${chainKind}</div>
        <div class="row"><code>${ridList.length}</code> step(s)</div>
        <div class="row">samples: <code>${head.sample_set_id}</code></div>
        <div class="row">interval: <code>${head.interval_set_id}</code></div>
        <div class="row">contract: ${allOk
          ? '<span style="color:var(--ok)">✓ OK end-to-end</span>'
          : '<span style="color:var(--fail)">✗ at least one step has unresolved FK</span>'}</div>
      </div>
      <div class="chain-steps">`;
    for (let i = 0; i < results.length; i++) {
      html += stepCard(results[i]);
      if (i < results.length - 1) html += arrow();
    }
    html += '</div></div>';
  }
  el.innerHTML = html;
}

function renderTable(root, filtered) {
  const rows = (DB.analysis_results.rows || []).filter(r => filtered.has(r.result_id));
  const out = root.querySelector('#all-results');
  if (rows.length === 0) {
    out.innerHTML = '<div class="empty">No results match the current filters.</div>';
    return;
  }
  let html = `<table>
    <thead><tr>
      <th>result_id</th><th>type</th><th>samples</th><th>interval</th><th>sites</th>
      <th>value / upstream</th><th>method</th><th>compatibility</th>
    </tr></thead><tbody>`;
  for (const r of rows) {
    const cs = contractStatus(r);
    const readyFor = readyForFor(r);
    const compat = [];
    if (r.input_result_id) compat.push('<span class="badge compat-in">upstream ✓</span>');
    for (const k of readyFor) compat.push(`<span class="badge ready-for">ready for ${k}</span>`);
    if (compat.length === 0 && !readyFor.length) compat.push('<span class="badge orphan">no downstream wired yet</span>');
    if (!cs.ok) compat.push(`<span class="badge contract-fail">${cs.why}</span>`);
    const mb = moduleBadge(r.analysis_type);
    if (mb) compat.push(mb);
    const cellPV = (tbl, id) => id ? `<td class="code" data-preview-table="${tbl}" data-preview-id="${id}">${id}</td>` : '<td class="code"></td>';
    const valueOrUpstream = r.input_value_id
      ? cellPV('input_values', r.input_value_id)
      : (r.input_result_id ? cellPV('analysis_results', r.input_result_id) : '<td class="code"></td>');
    html += `<tr>
      ${cellPV('analysis_results', r.result_id)}
      <td>${r.analysis_type}</td>
      ${cellPV('sample_sets',   r.sample_set_id)}
      ${cellPV('interval_sets', r.interval_set_id)}
      ${cellPV('site_sets',     r.site_set_id)}
      ${valueOrUpstream}
      <td>${r.method_id || ''}</td>
      <td>${compat.join(' ')}</td>
    </tr>`;
  }
  html += '</tbody></table>';
  out.innerHTML = html;
}

function applyFilters(root) {
  const fs = root.querySelector('#filter-sample').value;
  const fi = root.querySelector('#filter-interval').value;
  const all = (DB.analysis_results.rows || []);
  const filtered = new Set(
    all.filter(r => (!fs || r.sample_set_id === fs) && (!fi || r.interval_set_id === fi))
       .map(r => r.result_id)
  );
  renderChains(root, filtered);
  renderTable(root, filtered);
  root.querySelector('#counts').textContent =
    `${filtered.size} / ${all.length} result(s)  •  `
    + `${(DB.sample_sets.rows || []).length} sample set(s)  •  `
    + `${(DB.interval_sets.rows || []).length} interval set(s)  •  `
    + `${(DB.input_values.rows || []).length} input value(s)`;
}

function populateFilters(root) {
  const all = (DB.analysis_results.rows || []);
  const samples   = [...new Set(all.map(r => r.sample_set_id).filter(Boolean))].sort();
  const intervals = [...new Set(all.map(r => r.interval_set_id).filter(Boolean))].sort();
  const fs = root.querySelector('#filter-sample');
  const fi = root.querySelector('#filter-interval');
  for (const s of samples) {
    const o = document.createElement('option'); o.value = o.textContent = s;
    fs.appendChild(o);
  }
  for (const v of intervals) {
    const o = document.createElement('option'); o.value = o.textContent = v;
    fi.appendChild(o);
  }
}

// ===== Brick-edit sidebar ============================================= //

let CURRENT_BRICK = null;

function _txt(s) { return (s === undefined || s === null) ? '' : String(s); }

function renderContractDL(root, r) {
  const mod = moduleStatusForAnalysisType(r.analysis_type);
  const moduleRow = mod && mod.row;
  const fields = [
    ['analysis_type', r.analysis_type],
    ['sample_set',    r.sample_set_id],
    ['group_set',     r.group_set_id],
    ['interval_set',  r.interval_set_id],
    ['site_set',      r.site_set_id],
    ['input_value',   r.input_value_id],
    ['input_result',  r.input_result_id],
    ['method_id',     r.method_id],
    ['params_id',     r.params_id],
    ['path',          r.path],
    ['hash',          r.hash],
    ['status',        r.status],
    ['created_at',    r.created_at],
    ['notes',         r.notes],
  ];
  const moduleLine = moduleRow
    ? `${moduleRow.module_name} ${moduleRow.version} · ${moduleRow.family}`
    : (mod ? `${mod.module_name} (not in module_registry)` : '(no module wired)');
  const parts = [`<dt>module</dt><dd class="plain">${_txt(moduleLine)}</dd>`];
  for (const [k, v] of fields) {
    if (!v) continue;
    parts.push(`<dt>${k}</dt><dd>${_txt(v)}</dd>`);
  }
  root.querySelector('#sb-contract').innerHTML = parts.join('');
  return moduleRow;
}

function openBrick(root, rid) {
  const r = DB.analysis_results.by[rid];
  if (!r) return;
  CURRENT_BRICK = r;

  root.querySelectorAll('.step.selected').forEach(el => el.classList.remove('selected'));
  root.querySelectorAll(`.step[data-brick-rid="${rid}"]`).forEach(el => el.classList.add('selected'));

  const cls = classFor(r.analysis_type);
  const sb = root.querySelector('#sidebar');
  sb.classList.remove('ngsrelate', 'ngspedigree', 'mendelian', 'popstats', 'other');
  sb.classList.add(cls);

  const ana = root.querySelector('#sb-ana');
  ana.textContent = r.analysis_type;
  ana.style.background = ({
    ngsrelate:   'var(--chain-ngsrelate)',
    ngspedigree: 'var(--chain-ngspedigree)',
    mendelian:   'var(--chain-mendelian)',
    popstats:    '#b7791f',
    other:       'var(--muted)',
  })[cls];

  root.querySelector('#sb-rid').textContent = r.result_id;

  const moduleRow = renderContractDL(root, r);
  const mod = moduleStatusForAnalysisType(r.analysis_type);
  const modLabel = mod
    ? (moduleRow ? `module: ${moduleRow.module_name} ${moduleRow.version}` : `module: ${mod.module_name} (conceptual)`)
    : 'module: (none wired)';
  root.querySelector('#sb-module').textContent = modLabel;

  const parentName = moduleRow ? moduleRow.module_name : (mod ? mod.module_name : r.analysis_type);
  root.querySelector('#sb-new-name').value = `${parentName}_derived`;
  root.querySelector('#sb-new-version').value = '0.1.0';
  root.querySelector('#sb-params').value = '{}';
  root.querySelector('#sb-reason').value = '';
  const hint = root.querySelector('#sb-params-hint');
  hint.classList.remove('invalid');
  hint.textContent = "Only the overrides — biomod merges these on top of the parent's params.";
  root.querySelector('#sb-save').disabled = true;

  root.querySelector('#sidebar-backdrop').classList.add('open');
  sb.classList.add('open');
  sb.setAttribute('aria-hidden', 'false');
}

function closeBrick(root) {
  const sb = root.querySelector('#sidebar');
  sb.classList.remove('open');
  sb.setAttribute('aria-hidden', 'true');
  root.querySelector('#sidebar-backdrop').classList.remove('open');
  root.querySelectorAll('.step.selected').forEach(el => el.classList.remove('selected'));
  CURRENT_BRICK = null;
}

function buildDerivativeRecipe(root) {
  if (!CURRENT_BRICK) return null;
  const name = root.querySelector('#sb-new-name').value.trim();
  const version = root.querySelector('#sb-new-version').value.trim() || '0.1.0';
  const reason = root.querySelector('#sb-reason').value.trim();
  const paramsRaw = root.querySelector('#sb-params').value.trim() || '{}';

  let params;
  try { params = JSON.parse(paramsRaw); }
  catch (e) { return { error: `parameter overrides not valid JSON: ${e.message}` }; }
  if (typeof params !== 'object' || Array.isArray(params) || params === null) {
    return { error: 'parameter overrides must be a JSON object.' };
  }

  const mod = moduleStatusForAnalysisType(CURRENT_BRICK.analysis_type);
  const moduleRow = mod && mod.row;
  const parentName = moduleRow ? moduleRow.module_name : (mod ? mod.module_name : CURRENT_BRICK.analysis_type);
  const parentVersion = moduleRow ? moduleRow.version : null;
  const family = moduleRow ? moduleRow.family : 'unknown';

  const recipe = {
    schema_version: 0,
    name,
    version,
    family,
    description: `Derivative of ${parentName} created from ${CURRENT_BRICK.result_id}.`,
    parent: parentVersion ? `${parentName}@${parentVersion}` : parentName,
    parent_overrides: { parameters: params, reason },
    _provenance: {
      derived_from_result: CURRENT_BRICK.result_id,
      derived_from_analysis_type: CURRENT_BRICK.analysis_type,
      derived_at: new Date().toISOString(),
    },
  };
  return { recipe };
}

function validateForm(root) {
  const name = root.querySelector('#sb-new-name').value.trim();
  const reason = root.querySelector('#sb-reason').value.trim();
  const paramsRaw = root.querySelector('#sb-params').value.trim() || '{}';
  const hint = root.querySelector('#sb-params-hint');
  let paramsOk = true;
  try {
    const v = JSON.parse(paramsRaw);
    if (typeof v !== 'object' || Array.isArray(v) || v === null) paramsOk = false;
  } catch (_e) { paramsOk = false; }
  if (paramsOk) {
    hint.classList.remove('invalid');
    hint.textContent = "Only the overrides — biomod merges these on top of the parent's params.";
  } else {
    hint.classList.add('invalid');
    hint.textContent = 'Not valid JSON object — fix this before saving.';
  }
  root.querySelector('#sb-save').disabled = !(name && reason && paramsOk);
}

function saveDerivative(root) {
  const res = buildDerivativeRecipe(root);
  if (!res || res.error) { alert(res ? res.error : 'no brick selected'); return; }
  const blob = new Blob([JSON.stringify(res.recipe, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `${res.recipe.name}.recipe.json`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

function copyDerivative(root) {
  const res = buildDerivativeRecipe(root);
  if (!res || res.error) { alert(res ? res.error : 'no brick selected'); return; }
  const text = JSON.stringify(res.recipe, null, 2);
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(text).then(
      () => {
        const b = root.querySelector('#sb-copy');
        const t = b.textContent;
        b.textContent = 'Copied ✓';
        setTimeout(() => { b.textContent = t; }, 1200);
      },
      () => alert('Copy failed — your browser blocked clipboard access. Use Save instead.')
    );
  } else {
    alert('Clipboard not available. Use Save instead.');
  }
}

// ===== Lifecycle ======================================================= //

let _docClickHandler = null;
let _docKeyHandler = null;
let _filterHandlers = [];
let _sidebarHandlers = [];

export async function mount(root, _atlasState, _registry) {
  ensurePreviewsInstalled(REGISTRY_ROOT);
  DB = {};
  CURRENT_BRICK = null;

  await loadAll(root);
  window.DB = DB;
  populateFilters(root);
  applyFilters(root);

  root.querySelector('#footer').innerHTML =
    `Loaded from <code>${REGISTRY_ROOT}01_registry/*.tsv</code> · `
    + 'analysis_modes drives compatibility: a result of analysis_type X is "ready for" '
    + 'analysis_type Y when Y\'s mode requires X\'s <code>produces</code> as upstream input.';

  // Filter inputs (page-scoped).
  for (const id of ['#filter-sample', '#filter-interval']) {
    const el = root.querySelector(id);
    const h = () => applyFilters(root);
    el.addEventListener('input', h);
    _filterHandlers.push([el, 'input', h]);
  }

  // Sidebar buttons.
  const wire = (id, ev, fn) => {
    const el = root.querySelector(id);
    el.addEventListener(ev, fn);
    _sidebarHandlers.push([el, ev, fn]);
  };
  wire('#sb-close',          'click', () => closeBrick(root));
  wire('#sidebar-backdrop',  'click', () => closeBrick(root));
  wire('#sb-save',           'click', () => saveDerivative(root));
  wire('#sb-copy',           'click', () => copyDerivative(root));
  for (const id of ['#sb-new-name', '#sb-reason', '#sb-params']) {
    const el = root.querySelector(id);
    const h = () => validateForm(root);
    el.addEventListener('input', h);
    _sidebarHandlers.push([el, 'input', h]);
  }

  // Document-level listeners (delegated brick click + keyboard).
  // Stored so unmount() detaches them — otherwise stale handlers would
  // accumulate every time the user navigates away and back.
  _docClickHandler = (e) => {
    const brick = e.target.closest('.step[data-brick-rid]');
    if (!brick) return;
    if (!root.contains(brick)) return;  // ignore clicks from sibling atlases (defensive)
    openBrick(root, brick.getAttribute('data-brick-rid'));
  };
  _docKeyHandler = (e) => {
    if (e.key === 'Escape' && root.querySelector('#sidebar').classList.contains('open')) {
      closeBrick(root);
      return;
    }
    if (e.key !== 'Enter' && e.key !== ' ') return;
    const el = document.activeElement;
    if (el && el.classList && el.classList.contains('step') && el.dataset.brickRid && root.contains(el)) {
      e.preventDefault();
      openBrick(root, el.dataset.brickRid);
    }
  };
  document.addEventListener('click', _docClickHandler);
  document.addEventListener('keydown', _docKeyHandler);
}

export async function unmount(_root) {
  for (const [el, ev, h] of _filterHandlers) el.removeEventListener(ev, h);
  for (const [el, ev, h] of _sidebarHandlers) el.removeEventListener(ev, h);
  _filterHandlers = [];
  _sidebarHandlers = [];
  if (_docClickHandler) document.removeEventListener('click', _docClickHandler);
  if (_docKeyHandler)   document.removeEventListener('keydown', _docKeyHandler);
  _docClickHandler = null;
  _docKeyHandler = null;
  CURRENT_BRICK = null;
}
