// atlases/core/pages/specs.js
// =============================================================================
// SPECs page — per-atlas done + to-do SPEC inventory with markdown reader.
//
// Data flow:
//   atlases/_index.json          → list of atlas ids
//   atlases/<aid>/specs/specs_index.json
//                                → { atlas_id, has_aggregate, aggregate_path,
//                                    done: [{file, title, path}],
//                                    todo: [...] }
//   atlases/<aid>/specs/done/<file>.md   → SPEC markdown (raw)
//   atlases/<aid>/specs/todo/<file>.md   → SPEC markdown (raw)
//
// Indexer that produces specs_index.json: build/index_specs.py (called
// per atlas by build/assemble.sh).
//
// Fail-soft everywhere: a missing specs_index.json for an atlas yields
// an empty-state badge instead of breaking the page. Missing markdown
// at click time renders an inline error instead of throwing.
// =============================================================================

// In-memory cache.
const CACHE = {
  atlases:    null,   // [string] — id list (in display order)
  indices:    {},     // {aid: {ok, data|error}}
  markdown:   {},     // {path: {ok, body|error}}
};

let CURRENT_AID  = null;
let CURRENT_MODE = 'all';  // 'all' | 'done' | 'todo'
let _wired = [];

function wire(el, evt, fn) {
  if (!el) return;
  el.addEventListener(evt, fn);
  _wired.push(() => el.removeEventListener(evt, fn));
}

export function esc(s) {
  return String(s ?? '')
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

async function fetchJson(path) {
  const resp = await fetch(path, { cache: 'no-store' });
  if (!resp.ok) throw new Error(`${path} → HTTP ${resp.status}`);
  return resp.json();
}

async function fetchText(path) {
  const resp = await fetch(path, { cache: 'no-store' });
  if (!resp.ok) throw new Error(`${path} → HTTP ${resp.status}`);
  return resp.text();
}

// ===== Atlas discovery =================================================== //

async function loadAtlases() {
  if (CACHE.atlases) return CACHE.atlases;
  try {
    const idx = await fetchJson('atlases/_index.json');
    CACHE.atlases = idx.atlases || [];
  } catch {
    CACHE.atlases = [];
  }
  return CACHE.atlases;
}

async function loadIndex(aid) {
  if (CACHE.indices[aid]) return CACHE.indices[aid];
  try {
    const data = await fetchJson(`atlases/${aid}/specs/specs_index.json`);
    CACHE.indices[aid] = { ok: true, data };
  } catch (e) {
    CACHE.indices[aid] = { ok: false, error: e.message };
  }
  return CACHE.indices[aid];
}

async function loadMarkdown(path) {
  if (CACHE.markdown[path]) return CACHE.markdown[path];
  try {
    CACHE.markdown[path] = { ok: true, body: await fetchText(path) };
  } catch (e) {
    CACHE.markdown[path] = { ok: false, error: e.message };
  }
  return CACHE.markdown[path];
}

// ===== Minimal markdown renderer ========================================= //
// Enough for SPEC pages: headings, paragraphs, fenced code, inline code,
// bullet + numbered lists, links, simple emphasis, GFM tables, and HRs.
// Not a full CommonMark parser; SPEC files tend to use a small subset.

function _inline(s) {
  // 1. Pull fenced inline code OUT first (so its content isn't re-processed).
  const tokens = [];
  let i = 0;
  let out = s.replace(/`([^`\n]+)`/g, (_, body) => {
    const t = `\x00${i++}\x00`;
    tokens.push(`<code class="spc-md-icode">${esc(body)}</code>`);
    return t;
  });
  // 2. Escape everything that remains.
  out = esc(out);
  // 3. Restore code tokens.
  out = out.replace(/\x00(\d+)\x00/g, (_, idx) => tokens[Number(idx)]);
  // 4. Links: [text](url) — text/url already escaped at step 2.
  out = out.replace(/\[([^\]]+)\]\(([^)\s]+)\)/g,
    (_, txt, url) => `<a href="${url}" target="_blank" rel="noopener noreferrer">${txt}</a>`);
  // 5. Bold then italic. We use **…** / *…* and __…__ / _…_.
  out = out.replace(/\*\*([^*\n]+)\*\*/g, '<strong>$1</strong>');
  out = out.replace(/__([^_\n]+)__/g, '<strong>$1</strong>');
  out = out.replace(/(^|[^*])\*([^*\n]+)\*/g, '$1<em>$2</em>');
  out = out.replace(/(^|[^_])_([^_\n]+)_/g,    '$1<em>$2</em>');
  return out;
}

function _renderTable(lines) {
  // Caller has already verified lines is at least: header | separator | row...
  const split = (l) => l.replace(/^\||\|$/g, '').split('|').map(c => c.trim());
  const headers = split(lines[0]);
  const rows    = lines.slice(2).map(split);
  let html = '<table class="spc-md-tbl"><thead><tr>';
  for (const h of headers) html += `<th>${_inline(h)}</th>`;
  html += '</tr></thead><tbody>';
  for (const r of rows) {
    html += '<tr>';
    for (let i = 0; i < headers.length; i++) html += `<td>${_inline(r[i] || '')}</td>`;
    html += '</tr>';
  }
  return html + '</tbody></table>';
}

export function renderMarkdown(md) {
  // Normalise line endings; trim trailing whitespace per line.
  const lines = md.replace(/\r\n?/g, '\n').split('\n').map(l => l.replace(/\s+$/, ''));
  const out = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];

    // Fenced code block ```lang
    const fence = /^```([\w-]*)\s*$/.exec(line);
    if (fence) {
      const lang = fence[1];
      const buf = [];
      i++;
      while (i < lines.length && !/^```\s*$/.test(lines[i])) {
        buf.push(lines[i]); i++;
      }
      i++;  // skip closing fence (or EOF)
      const cls = lang ? ` class="lang-${esc(lang)}"` : '';
      out.push(`<pre class="spc-md-pre"><code${cls}>${esc(buf.join('\n'))}</code></pre>`);
      continue;
    }

    // GFM table: header row, separator row of dashes, then rows.
    if (/\|/.test(line) && i + 1 < lines.length &&
        /^\|?\s*:?-{2,}/.test(lines[i + 1])) {
      const tbl = [line, lines[i + 1]];
      let j = i + 2;
      while (j < lines.length && /\|/.test(lines[j]) && lines[j].trim()) {
        tbl.push(lines[j]); j++;
      }
      out.push(_renderTable(tbl));
      i = j;
      continue;
    }

    // Heading
    const h = /^(#{1,6})\s+(.+)$/.exec(line);
    if (h) {
      const lvl = h[1].length;
      out.push(`<h${lvl} class="spc-md-h spc-md-h${lvl}">${_inline(h[2])}</h${lvl}>`);
      i++; continue;
    }

    // Horizontal rule
    if (/^-{3,}\s*$|^\*{3,}\s*$|^_{3,}\s*$/.test(line)) {
      out.push('<hr class="spc-md-hr">');
      i++; continue;
    }

    // Bullet list (- or *)
    if (/^\s*[-*]\s+/.test(line)) {
      const items = [];
      while (i < lines.length && /^\s*[-*]\s+/.test(lines[i])) {
        items.push(lines[i].replace(/^\s*[-*]\s+/, ''));
        i++;
      }
      out.push('<ul class="spc-md-ul">' + items.map(t => `<li>${_inline(t)}</li>`).join('') + '</ul>');
      continue;
    }

    // Numbered list
    if (/^\s*\d+\.\s+/.test(line)) {
      const items = [];
      while (i < lines.length && /^\s*\d+\.\s+/.test(lines[i])) {
        items.push(lines[i].replace(/^\s*\d+\.\s+/, ''));
        i++;
      }
      out.push('<ol class="spc-md-ol">' + items.map(t => `<li>${_inline(t)}</li>`).join('') + '</ol>');
      continue;
    }

    // Blank line: paragraph separator
    if (!line.trim()) { i++; continue; }

    // Blockquote
    if (/^>\s?/.test(line)) {
      const buf = [];
      while (i < lines.length && /^>\s?/.test(lines[i])) {
        buf.push(lines[i].replace(/^>\s?/, '')); i++;
      }
      out.push(`<blockquote class="spc-md-bq">${_inline(buf.join(' '))}</blockquote>`);
      continue;
    }

    // Paragraph — slurp consecutive non-blank, non-special lines.
    const para = [line];
    i++;
    while (i < lines.length && lines[i].trim() &&
           !/^(#|```|>\s|-{3,}|\*{3,}|_{3,}|\s*[-*]\s+|\s*\d+\.\s+)/.test(lines[i]) &&
           !(/\|/.test(lines[i]) && i + 1 < lines.length && /^\|?\s*:?-{2,}/.test(lines[i + 1]))) {
      para.push(lines[i]); i++;
    }
    out.push(`<p class="spc-md-p">${_inline(para.join(' '))}</p>`);
  }
  return out.join('\n');
}

// ===== Left tree ========================================================= //

function renderTree(root, filter) {
  const tree = root.querySelector('#spc-tree');
  if (!CURRENT_AID) {
    tree.innerHTML = '<div class="spc-empty">No atlas selected.</div>';
    return;
  }
  const slot = CACHE.indices[CURRENT_AID];
  if (!slot) {
    tree.innerHTML = '<div class="spc-empty">loading…</div>';
    return;
  }
  if (!slot.ok) {
    tree.innerHTML =
      `<div class="spc-empty spc-warn">No specs_index.json for <code>${esc(CURRENT_AID)}</code>.<br>` +
      `Run <code>bash atlas-core/build/assemble.sh</code> to generate it.<br>` +
      `<span class="spc-empty-detail">${esc(slot.error)}</span></div>`;
    return;
  }
  const data = slot.data;
  const f = (filter || '').trim().toLowerCase();
  const match = (e) => !f || (e.file + ' ' + e.title).toLowerCase().includes(f);

  const sections = [];
  if (CURRENT_MODE === 'all' || CURRENT_MODE === 'done') {
    const done = data.done.filter(match);
    sections.push({ label: 'Done', kind: 'done', entries: done, total: data.done.length });
  }
  if (CURRENT_MODE === 'all' || CURRENT_MODE === 'todo') {
    const todo = data.todo.filter(match);
    sections.push({ label: 'To-do', kind: 'todo', entries: todo, total: data.todo.length });
  }

  const parts = [];

  if (data.has_aggregate) {
    parts.push(
      `<div class="spc-group"><div class="spc-group-h">Overview</div>` +
      `<div class="spc-row" data-kind="aggregate" data-path="${esc(data.aggregate_path)}" tabindex="0">` +
        `<div class="spc-row-1">SPECS.md</div>` +
        `<div class="spc-row-2">atlas-wide aggregate / table of contents</div>` +
      `</div></div>`);
  }

  for (const s of sections) {
    const badgeCls = s.kind === 'done' ? 'spc-badge-done' : 'spc-badge-todo';
    parts.push(
      `<div class="spc-group"><div class="spc-group-h">` +
        `<span class="spc-badge ${badgeCls}">${esc(s.label)}</span>` +
        ` <span class="spc-n">(${s.entries.length}${s.entries.length !== s.total ? ` / ${s.total}` : ''})</span>` +
      `</div>`);
    if (s.entries.length === 0) {
      parts.push(`<div class="spc-empty spc-empty-sm">${f ? 'no matches' : 'empty'}</div>`);
    } else {
      for (const e of s.entries) {
        parts.push(
          `<div class="spc-row" data-kind="${esc(s.kind)}" data-path="${esc(e.path)}" tabindex="0">` +
            `<div class="spc-row-1">${esc(e.title)}</div>` +
            `<div class="spc-row-2">${esc(e.file)}</div>` +
          `</div>`);
      }
    }
    parts.push('</div>');
  }

  tree.innerHTML = parts.join('') || '<div class="spc-empty">No matches.</div>';
}

// ===== Right detail ====================================================== //

async function showSpecDetail(root, path) {
  const detail = root.querySelector('#spc-detail');
  detail.innerHTML = `<div class="spc-det-h">${esc(path)}</div><div class="spc-empty">loading…</div>`;
  const slot = await loadMarkdown(path);
  if (!slot.ok) {
    detail.innerHTML =
      `<div class="spc-det-h">${esc(path)}</div>` +
      `<div class="spc-empty spc-warn">fetch failed — ${esc(slot.error)}</div>`;
    return;
  }
  const html = renderMarkdown(slot.body);
  detail.innerHTML =
    `<div class="spc-det-h">${esc(path)}</div>` +
    `<div class="spc-md-body">${html}</div>`;
  detail.scrollTop = 0;
}

// ===== Tab activation ==================================================== //

async function buildTabs(root) {
  const atlases = await loadAtlases();
  const tabsHost = root.querySelector('#spc-tabs');
  // Prepend buttons before the existing mode-toggle on the right.
  const modeEl = tabsHost.querySelector('.spc-mode');
  // Clear any previous (re-mounting after route nav)
  for (const old of [...tabsHost.querySelectorAll('.spc-tab')]) old.remove();
  for (const aid of atlases) {
    const b = document.createElement('button');
    b.className = 'spc-tab';
    b.type = 'button';
    b.dataset.aid = aid;
    b.textContent = aid;
    tabsHost.insertBefore(b, modeEl);
  }
  // Default selection: first atlas (which is `core` after assemble).
  CURRENT_AID = atlases[0] || null;
  for (const t of tabsHost.querySelectorAll('.spc-tab')) {
    t.classList.toggle('active', t.dataset.aid === CURRENT_AID);
  }
}

async function activateAtlas(root, aid) {
  CURRENT_AID = aid;
  for (const t of root.querySelectorAll('.spc-tab')) {
    t.classList.toggle('active', t.dataset.aid === aid);
  }
  root.querySelector('#spc-tree').innerHTML = '<div class="spc-empty">loading…</div>';
  root.querySelector('#spc-detail').innerHTML =
    '<div class="spc-empty">Select a SPEC on the left.</div>';
  await loadIndex(aid);
  const filterEl = root.querySelector('#spc-filter');
  renderTree(root, filterEl?.value || '');
}

// ===== mount / unmount =================================================== //

export async function mount(root, _ctx = {}) {
  await buildTabs(root);

  wire(root.querySelector('#spc-tabs'), 'click', (e) => {
    const modeBtn = e.target.closest('.spc-mode-btn');
    if (modeBtn) {
      CURRENT_MODE = modeBtn.dataset.mode;
      for (const b of root.querySelectorAll('.spc-mode-btn')) {
        b.classList.toggle('active', b.dataset.mode === CURRENT_MODE);
      }
      renderTree(root, root.querySelector('#spc-filter')?.value || '');
      return;
    }
    const t = e.target.closest('.spc-tab');
    if (!t || !root.contains(t)) return;
    activateAtlas(root, t.dataset.aid);
  });

  wire(root.querySelector('#spc-filter'), 'input', () => {
    renderTree(root, root.querySelector('#spc-filter').value);
  });

  wire(root.querySelector('#spc-tree'), 'click', (e) => {
    const row = e.target.closest('.spc-row');
    if (!row || !root.contains(row)) return;
    showSpecDetail(root, row.dataset.path);
  });

  if (CURRENT_AID) await activateAtlas(root, CURRENT_AID);
  else {
    root.querySelector('#spc-tree').innerHTML =
      '<div class="spc-empty spc-warn">No atlases registered in atlases/_index.json.</div>';
  }
}

export async function unmount(_root) {
  for (const off of _wired) off();
  _wired = [];
  CURRENT_AID = null;
}
