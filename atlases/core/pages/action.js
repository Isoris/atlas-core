// atlases/core/pages/action.js
// =============================================================================
// Action page — readiness & routing dashboard.
//
// Round-1 migration from toolkit_registries/relatedness/page/action.html.
// All logic preserved verbatim; the differences from the original are:
//   - The inline <script> body is wrapped in a module with mount()/unmount().
//   - Element lookups are scoped to the page root (`root.querySelector`)
//     instead of `document.getElementById`, so two simultaneous instances
//     would not collide. (The router only mounts one page at a time, but
//     this is the safer pattern.)
//   - The form's <onsubmit="resolveAndRender()"> attribute is replaced by an
//     addEventListener('submit', …) in mount(); the handler's reference is
//     kept so unmount() can detach it cleanly.
//   - Registry data is fetched from `${REGISTRY_ROOT}01_registry/...` so the
//     workspace-rooted path resolves under the assembled workspace.
//   - Hover popovers are installed once via the shared previews module.
// =============================================================================

import { ensurePreviewsInstalled } from './previews.js';

const REGISTRY_ROOT = 'toolkit_registries/relatedness/';

// ===== TSV loader (same as page 3) ===================================== //

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

async function loadAll() {
  for (const [name, path, key] of TSVS) {
    let rows;
    try {
      rows = await fetchTsv(path);
    } catch (e) {
      // module_registry.tsv is optional — degrade gracefully when biomod
      // isn't synced yet. Everything else is required.
      if (name === 'module_registry') {
        rows = [];
      } else {
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

// ===== Policy resolvers (port from resolve.py) ========================== //

function _interval(tag, args) {
  const rows = DB.interval_sets.rows;
  if (tag === 'genome_all') {
    const cs = rows.filter(r => r.interval_type === 'genome');
    return cs.length === 1
      ? { id: cs[0].interval_set_id, why: 'interval_type=genome' }
      : { cands: cs.map(c => c.interval_set_id), why: 'interval_type=genome (need exactly 1)' };
  }
  if (tag === 'chromosome_full') {
    if (!args.chromosome) return { why: 'need --chromosome' };
    const cs = rows.filter(r => r.interval_type === 'chromosome'
                                && (r.interval_set_id || '').includes(args.chromosome));
    return cs.length === 1
      ? { id: cs[0].interval_set_id, why: `interval_type=chromosome containing '${args.chromosome}'` }
      : { cands: cs.map(c => c.interval_set_id), why: `interval_type=chromosome matching '${args.chromosome}'` };
  }
  if (tag === 'candidate_interval') {
    if (!args.candidate_id) return { why: 'need --candidate-id' };
    const cs = rows.filter(r => r.interval_type === 'candidate'
                                && (r.interval_set_id || '').includes(args.candidate_id));
    return cs.length === 1
      ? { id: cs[0].interval_set_id, why: `interval_type=candidate matching '${args.candidate_id}'` }
      : { cands: cs.map(c => c.interval_set_id), why: 'no unique candidate match' };
  }
  return { why: `unknown interval_policy '${tag}'` };
}

function _site(tag, intervalId) {
  const rows = DB.site_sets.rows;
  if (tag === 'thin500_global') {
    const cs = rows.filter(r => r.site_set_id.includes('thin500') && r.site_set_id.includes('global'));
    return cs.length === 1
      ? { id: cs[0].site_set_id, why: 'site_set name contains thin500+global' }
      : { cands: cs.map(c => c.site_set_id), why: 'thin500+global (need exactly 1)' };
  }
  if (tag === 'thin500_per_chr') {
    const cs = rows.filter(r => r.site_set_id.includes('thin500') && r.interval_set_id === intervalId);
    return cs.length === 1
      ? { id: cs[0].site_set_id, why: `thin500 site_set with interval_set_id=${intervalId}` }
      : { cands: cs.map(c => c.site_set_id), why: `thin500 + interval=${intervalId}` };
  }
  if (tag === 'candidate_sites') {
    const cs = rows.filter(r => r.interval_set_id === intervalId && r.operation === 'intersect');
    return cs.length === 1
      ? { id: cs[0].site_set_id, why: `site_set on interval=${intervalId}, operation=intersect` }
      : { cands: cs.map(c => c.site_set_id), why: `intersect on ${intervalId}` };
  }
  return { why: `unknown site_policy '${tag}'` };
}

function _group(tag, sampleId) {
  const rows = DB.group_sets.rows;
  const relevant = rows.filter(r => r.sample_set_id === sampleId);
  if (tag === 'family_population') {
    const cs = relevant.filter(r => (r.group_columns || '').includes('family')
                                  && (r.group_columns || '').includes('population'));
    return cs.length === 1
      ? { id: cs[0].group_set_id, why: 'family+population in group_columns' }
      : { cands: cs.map(c => c.group_set_id), why: 'family+population (need exactly 1)' };
  }
  if (tag === 'family_karyotype') {
    const cs = relevant.filter(r => (r.group_columns || '').includes('family')
                                  && (r.group_columns || '').includes('karyotype'));
    if (cs.length === 1) return { id: cs[0].group_set_id, why: 'family+karyotype' };
    if (cs.length > 1)  return { cands: cs.map(c => c.group_set_id), why: 'family+karyotype (need exactly 1)' };
    return { why: 'no group_set with family+karyotype columns; --group-set explicitly', cands: [] };
  }
  if (tag === 'optional_groups') return { id: '', why: 'groups optional' };
  return { why: `unknown group_policy '${tag}'` };
}

function _value(tag, sampleId, siteId, intervalId) {
  if (tag === 'none') return { id: '', why: 'this analysis consumes an upstream result, not a value file' };
  if (tag === 'beagle_matching') {
    const cs = DB.input_values.rows.filter(r =>
      (r.value_type || '').startsWith('BEAGLE')
      && r.sample_set_id === sampleId
      && r.site_set_id === siteId
      && (!intervalId || r.interval_set_id === intervalId)
    );
    return cs.length === 1
      ? { id: cs[0].value_id, why: `BEAGLE matching (${sampleId}, ${siteId}, ${intervalId})` }
      : { cands: cs.map(c => c.value_id), why: `BEAGLE matching (${sampleId}, ${siteId}, ${intervalId})` };
  }
  return { why: `unknown value_policy '${tag}'` };
}

// ===== Mode chain walking ============================================== //

function findMode(analysis, mode) {
  return DB.analysis_modes.rows.find(m => m.analysis_type === analysis && m.mode === mode);
}

const REQ_TO_PRODUCES = {
  ngsrelate_result: 'relatedness_res',
  pedigree_result:  'pedigree_result',
  mendelian_result: 'mendelian_result',
  relatedness_res:  'relatedness_res',
};

function walkChain(targetAnalysis, targetMode) {
  const chain = []; const seen = new Set();
  function walk(a, mo) {
    const k = a + '/' + mo;
    if (seen.has(k)) return;
    seen.add(k);
    const m = findMode(a, mo);
    if (!m) return;
    const req = (m.required_dimensions || '').split(',').map(s => s.trim());
    for (const dim of req) {
      const producesTag = REQ_TO_PRODUCES[dim];
      if (!producesTag) continue;
      const candidate = DB.analysis_modes.rows.find(mm => mm.produces === producesTag);
      if (candidate) walk(candidate.analysis_type, candidate.mode);
    }
    chain.push(m);
  }
  walk(targetAnalysis, targetMode);
  return chain;
}

// ===== Resolve one step's contract ===================================== //

function resolveStep(mode, args, inherited) {
  const log = [];
  const contract = {
    analysis_type: mode.analysis_type,
    mode:          mode.mode,
    produces:      mode.produces,
  };
  const missing = [];
  const ambiguous = [];

  const required = (mode.required_dimensions || '').split(',').map(s => s.trim()).filter(Boolean);
  const have = {
    sample_set:        args.sample_set,
    chromosome:        args.chromosome,
    candidate_id:      args.candidate_id,
    ngsrelate_result:  inherited.ngsrelate_result,
    pedigree_result:   inherited.pedigree_result,
  };
  for (const dim of required) {
    if (!have[dim] && !inherited['_inherited_' + dim]) {
      missing.push(`required dimension '${dim}' not provided`);
    }
  }

  const sampleId = args.sample_set || inherited.sample_set_id || '';
  contract.sample_set_id = sampleId;
  if (inherited.input_result_id) contract.input_result_id = inherited.input_result_id;

  const ip = mode.interval_policy || '';
  if (ip === 'same_as_input' && inherited.interval_set_id) {
    contract.interval_set_id = inherited.interval_set_id;
    log.push(`interval (inherited): ${contract.interval_set_id}`);
  } else if (ip) {
    const r = _interval(ip, args);
    log.push(`interval_policy='${ip}': ${r.why} → ${r.id || '(none)'}`);
    if (r.id !== undefined) contract.interval_set_id = r.id;
    else if ((r.cands || []).length) ambiguous.push(`interval: ${r.why} — ${(r.cands || []).join(', ')}`);
    else missing.push(`interval: ${r.why}`);
  }

  const sp = mode.site_policy || '';
  if (sp === 'same_as_input' && inherited.site_set_id) {
    contract.site_set_id = inherited.site_set_id;
    log.push(`site (inherited): ${contract.site_set_id}`);
  } else if (sp) {
    const r = _site(sp, contract.interval_set_id || '');
    log.push(`site_policy='${sp}': ${r.why} → ${r.id || '(none)'}`);
    if (r.id !== undefined) contract.site_set_id = r.id;
    else if ((r.cands || []).length) ambiguous.push(`site: ${r.why} — ${(r.cands || []).join(', ')}`);
    else missing.push(`site: ${r.why}`);
  }

  const gp = mode.group_policy || '';
  if (gp === 'same_as_input' && inherited.group_set_id) {
    contract.group_set_id = inherited.group_set_id;
    log.push(`group (inherited): ${contract.group_set_id}`);
  } else if (gp) {
    const r = _group(gp, sampleId);
    log.push(`group_policy='${gp}': ${r.why} → ${r.id !== undefined ? r.id : '(none)'}`);
    if (r.id !== undefined) contract.group_set_id = r.id;
    else if ((r.cands || []).length) ambiguous.push(`group: ${r.why} — ${(r.cands || []).join(', ')}`);
    else missing.push(`group: ${r.why}`);
  }

  const vp = mode.value_policy || '';
  if (vp) {
    const r = _value(vp, sampleId, contract.site_set_id || '', contract.interval_set_id || '');
    log.push(`value_policy='${vp}': ${r.why} → ${r.id || '(none)'}`);
    if (r.id !== undefined) contract.input_value_id = r.id;
    else if ((r.cands || []).length) ambiguous.push(`value: ${r.why} — ${(r.cands || []).join(', ')}`);
    else missing.push(`value: ${r.why}`);
  }

  return { contract, missing, ambiguous, log };
}

// ===== Result-lookup ==================================================== //

function findMatchingResult(contract) {
  return DB.analysis_results.rows.find(r =>
    r.analysis_type === contract.analysis_type
    && r.sample_set_id === (contract.sample_set_id || '')
    && r.interval_set_id === (contract.interval_set_id || '')
    && r.site_set_id === (contract.site_set_id || '')
    && (
      (r.input_value_id || '') === (contract.input_value_id || '')
      || (r.input_result_id && r.input_result_id === contract.input_result_id)
    )
  );
}

// ===== Status ========================================================== //

function statusFor(stepResolution) {
  const { contract, missing, ambiguous } = stepResolution;
  const hit = findMatchingResult(contract);
  if (hit) return { state: 'RESULT_READY', existing: hit };
  if (missing.length) return { state: 'MISSING', missing, ambiguous };
  if (ambiguous.length) return { state: 'BLOCKED', ambiguous };
  return { state: 'RUN_READY' };
}

// ===== Render ========================================================== //

function pill(state) { return `<span class="pill ${state}">${state.toLowerCase()}</span>`; }

function moduleStatus(mode) {
  const name = (mode.module_name || '').trim();
  if (!name) return { state: 'MOD_CONCEPTUAL', label: '(no module_name set)', row: null };
  const row = DB.module_registry.by[name];
  if (!row) return { state: 'MOD_CONCEPTUAL', label: name + ' (not in module_registry)', row: null };
  if (row.installed !== 'true') return { state: 'MOD_NOT_INSTALLED', label: `${name} ${row.version || ''}`, row };
  if (row.last_run_status === 'failed') return { state: 'MOD_FAILED', label: `${name} ${row.version || ''} — last run failed`, row };
  if (row.stale === 'true') return { state: 'MOD_STALE', label: `${name} — stale: ${row.stale_reason || 'inputs changed'}`, row };
  if (row.ready === 'true') return { state: 'MOD_READY', label: `${name} ${row.version || ''} — last QC: ${row.last_run_qc || '?'}`, row };
  return { state: 'MOD_AVAILABLE', label: `${name} ${row.version || ''}`, row };
}

function recoBlock(step) {
  const { state, existing, missing, ambiguous } = step.status;
  const c = step.resolution.contract;

  if (state === 'RESULT_READY') {
    return `<div class="step-rec">
      <h4>Recommended action — REUSE</h4>
      Use existing layer: <code>${existing.result_id}</code><br>
      <code>path: ${existing.path}</code>
    </div>`;
  }
  if (state === 'RUN_READY') {
    const cmd = `python3 register_result.py \\
  --result-id        <new_id> \\
  --analysis-type    ${c.analysis_type} \\
  --path             04_results/${c.analysis_type}/<filename> \\
  --sample-set-id    ${c.sample_set_id || ''} \\
  ${c.group_set_id ? '--group-set-id     ' + c.group_set_id + ' \\\n  ' : ''}--interval-set-id  ${c.interval_set_id || ''} \\
  ${c.site_set_id ? '--site-set-id      ' + c.site_set_id + ' \\\n  ' : ''}${c.input_value_id ? '--input-value-id   ' + c.input_value_id + ' \\\n  ' : ''}${c.input_result_id ? '--input-result-id  ' + c.input_result_id + ' \\\n  ' : ''}--method-id        ${c.analysis_type}_v?`;
    return `<div class="step-rec">
      <h4>Recommended action — RUN</h4>
      All inputs resolved. Run the tool, then register the output:
      <pre>${cmd.replace(/&/g, '&amp;').replace(/</g, '&lt;')}</pre>
    </div>`;
  }
  if (state === 'MISSING') {
    return `<div class="step-rec">
      <h4>Recommended action — RESOLVE MISSING</h4>
      <ul>${missing.map(m => `<li>${m}</li>`).join('')}</ul>
    </div>`;
  }
  if (state === 'BLOCKED') {
    return `<div class="step-rec">
      <h4>Recommended action — DISAMBIGUATE</h4>
      Pick one explicitly:
      <ul>${(ambiguous || []).map(m => `<li>${m}</li>`).join('')}</ul>
    </div>`;
  }
  return '';
}

function renderSteps(root, chain, args) {
  const steps = [];
  let inherited = {};
  for (let i = 0; i < chain.length; i++) {
    const m = chain[i];
    const resolution = resolveStep(m, args, inherited);
    const status = statusFor(resolution);
    steps.push({ mode: m, resolution, status });

    const c = resolution.contract;
    inherited = {
      sample_set_id:    c.sample_set_id   || inherited.sample_set_id,
      group_set_id:     c.group_set_id    || inherited.group_set_id,
      interval_set_id:  c.interval_set_id || inherited.interval_set_id,
      site_set_id:      c.site_set_id     || inherited.site_set_id,
      ngsrelate_result: m.produces === 'relatedness_res' ? (status.existing ? status.existing.result_id : '<future>' + m.analysis_type + '_id') : inherited.ngsrelate_result,
      pedigree_result:  m.produces === 'pedigree_result'  ? (status.existing ? status.existing.result_id : '<future>' + m.analysis_type + '_id') : inherited.pedigree_result,
      input_result_id:  status.existing ? status.existing.result_id : inherited.input_result_id,
    };
  }

  let html = '';
  steps.forEach((s, i) => {
    const c = s.resolution.contract;
    const ex = s.status.existing;
    const mod = moduleStatus(s.mode);
    html += `<div class="step-card ${s.status.state}">
      <div class="step-head">
        <span class="step-num">step ${i + 1} of ${steps.length}</span>
        <span class="step-ana">${s.mode.analysis_type}<span class="mode">/${s.mode.mode}</span></span>
        ${pill(s.status.state)}
        ${pill(mod.state)}
        <span style="color:var(--muted);font-size:11.5px">${mod.label}</span>
        ${ex ? `<span style="color:var(--muted);font-size:12px">→ <code>${ex.result_id}</code></span>` : ''}
      </div>
      <dl class="step-body">
        <dt>sample_set</dt><dd>${c.sample_set_id    ? `<span data-preview-table="sample_sets"      data-preview-id="${c.sample_set_id}">${c.sample_set_id}</span>`     : '—'}</dd>
        <dt>group_set</dt><dd>${c.group_set_id     ? `<span data-preview-table="group_sets"       data-preview-id="${c.group_set_id}">${c.group_set_id}</span>`     : '—'}</dd>
        <dt>interval_set</dt><dd>${c.interval_set_id ? `<span data-preview-table="interval_sets"    data-preview-id="${c.interval_set_id}">${c.interval_set_id}</span>` : '—'}</dd>
        <dt>site_set</dt><dd>${c.site_set_id       ? `<span data-preview-table="site_sets"        data-preview-id="${c.site_set_id}">${c.site_set_id}</span>`       : '—'}</dd>
        <dt>input_value</dt><dd>${c.input_value_id ? `<span data-preview-table="input_values"     data-preview-id="${c.input_value_id}">${c.input_value_id}</span>` : '—'}</dd>
        ${c.input_result_id ? `<dt>input_result</dt><dd><span data-preview-table="analysis_results" data-preview-id="${c.input_result_id}">${c.input_result_id}</span></dd>` : ''}
        <dt>produces</dt><dd>${c.produces}</dd>
        <dt>module</dt><dd>${s.mode.module_name ? `<span data-preview-table="module_registry" data-preview-id="${s.mode.module_name}">${s.mode.module_name}</span>` : '—'}${mod.row && mod.row.version ? '  @ ' + mod.row.version : ''}${mod.row && mod.row.last_run_id ? `  · last_run=<code>${mod.row.last_run_id.slice(0,8)}…</code>` : ''}</dd>
      </dl>
      ${recoBlock(s)}
    </div>`;
  });

  const counts = {};
  for (const s of steps) counts[s.status.state] = (counts[s.status.state] || 0) + 1;
  const summary = Object.entries(counts)
    .sort()
    .map(([k, n]) => `<span class="item"><strong>${n}</strong> step(s) ${pill(k)}</span>`)
    .join('');
  const summaryEl = root.querySelector('#summary');
  summaryEl.innerHTML = summary;
  summaryEl.style.display = 'flex';

  root.querySelector('#steps').innerHTML = html || '<div class="empty">No steps to resolve.</div>';
}

// ===== Form wiring ===================================================== //

function populateForm(root) {
  const fa = root.querySelector('#f-analysis');
  const fm = root.querySelector('#f-mode');
  const fs = root.querySelector('#f-sample');

  const analyses = [...new Set(DB.analysis_modes.rows.map(r => r.analysis_type))];
  for (const a of analyses) {
    const o = document.createElement('option');
    o.value = o.textContent = a;
    fa.appendChild(o);
  }
  fa.addEventListener('change', () => populateModes(root));
  populateModes(root);

  for (const s of DB.sample_sets.rows) {
    const o = document.createElement('option');
    o.value = s.sample_set_id; o.textContent = `${s.sample_set_id} (${s.n_samples})`;
    fs.appendChild(o);
  }

  // Sensible defaults: target = mendelian/per_candidate, sample = first.
  if (analyses.includes('mendelian')) fa.value = 'mendelian';
  populateModes(root);
  const perCandOpt = [...fm.options].find(o => o.value === 'per_candidate');
  if (perCandOpt) fm.value = 'per_candidate';
  root.querySelector('#f-chrom').value = 'C_gar_LG12';
  root.querySelector('#f-candidate').value = 'LG12_INV_001';
}

function populateModes(root) {
  const a = root.querySelector('#f-analysis').value;
  const fm = root.querySelector('#f-mode');
  fm.innerHTML = '';
  for (const m of DB.analysis_modes.rows.filter(r => r.analysis_type === a)) {
    const o = document.createElement('option');
    o.value = m.mode; o.textContent = `${m.mode} — ${m.label || ''}`;
    fm.appendChild(o);
  }
}

function resolveAndRender(root) {
  const args = {
    analysis:     root.querySelector('#f-analysis').value,
    mode:         root.querySelector('#f-mode').value,
    sample_set:   root.querySelector('#f-sample').value,
    chromosome:   root.querySelector('#f-chrom').value.trim(),
    candidate_id: root.querySelector('#f-candidate').value.trim(),
  };
  const chain = walkChain(args.analysis, args.mode);
  renderSteps(root, chain, args);
}

// ===== Lifecycle ======================================================= //

let _formHandler = null;
let _formEl = null;

export async function mount(root, _atlasState, _registry) {
  ensurePreviewsInstalled(REGISTRY_ROOT);
  DB = {};
  try {
    await loadAll();
    window.DB = DB;
    populateForm(root);
    resolveAndRender(root);
    root.querySelector('#footer').innerHTML =
      `Loaded from <code>${REGISTRY_ROOT}01_registry/*.tsv</code> · ` +
      `Status logic: <code>RESULT_READY</code> if a result row matches the resolved contract; ` +
      `<code>RUN_READY</code> if all inputs exist and policies resolve uniquely; ` +
      `<code>MISSING</code> if a required dimension is unfilled; ` +
      `<code>BLOCKED</code> if a policy has multiple candidates and needs human disambiguation. ` +
      `<strong>This page does not run anything</strong> — it tells you what to reuse, what's run-ready, and what's blocked.`;

    _formEl = root.querySelector('[data-core-form]');
    _formHandler = (ev) => { ev.preventDefault(); resolveAndRender(root); };
    _formEl.addEventListener('submit', _formHandler);
  } catch (e) {
    const banner = document.createElement('div');
    banner.className = 'error';
    banner.innerHTML = `Failed to load registry TSVs: ${e.message}.<br>` +
      `Ensure the assembled workspace contains <code>${REGISTRY_ROOT}01_registry/*.tsv</code>.`;
    const form = root.querySelector('[data-core-form]');
    if (form) form.parentNode.insertBefore(banner, form);
  }
}

export async function unmount(_root) {
  if (_formEl && _formHandler) _formEl.removeEventListener('submit', _formHandler);
  _formEl = null;
  _formHandler = null;
}
