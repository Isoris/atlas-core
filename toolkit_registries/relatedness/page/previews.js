// previews.js — hover preview popover for registry-id cells.
//
// Usage:
//   1. Include this file (after the page's main script that populates window.DB):
//        <script src="previews.js"></script>
//
//   2. On any cell that renders a registry id, add data-preview attributes:
//        <code data-preview-table="sample_sets" data-preview-id="samples_226_v1">
//          samples_226_v1
//        </code>
//      Supported `data-preview-table` values:
//        sample_sets, group_sets, interval_sets, site_sets, input_values,
//        analysis_results, analysis_modes, module_registry
//
//   3. Hover any tagged cell → popover shows:
//        - the registry row fields
//        - a peek at the underlying file (first ~10 rows of TSV)
//
// File-fetch policy:
//   - Plain .tsv / .res / .pedigree.tsv / .mendelian.tsv: full preview
//   - .tsv.gz / .beagle.gz: tries DecompressionStream (modern browsers);
//     falls back to "compressed — N rows, see <path>" message
//
// Stdlib JS, no deps, no build.

(function () {
  if (window.__atlasPreviewsInstalled) return;
  window.__atlasPreviewsInstalled = true;

  // ---------- styles --------------------------------------------------- //
  const css = document.createElement("style");
  css.textContent = `
    #atlas-preview {
      position: fixed; z-index: 9999;
      max-width: 540px; min-width: 280px;
      background: #1a202c; color: #e2e8f0;
      border: 1px solid #2d3748; border-radius: 6px;
      box-shadow: 0 8px 24px rgba(0,0,0,0.18);
      padding: 10px 12px;
      font: 11.5px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      pointer-events: none;
      display: none;
    }
    #atlas-preview .hdr {
      font-weight: 600; font-size: 12px; color: #fff; margin-bottom: 4px;
      display: flex; gap: 6px; align-items: baseline;
    }
    #atlas-preview .hdr .tag {
      font-size: 10px; padding: 1px 6px; border-radius: 3px;
      background: #4a5568; color: white; text-transform: uppercase; letter-spacing: 0.04em;
    }
    #atlas-preview dl {
      display: grid; grid-template-columns: max-content 1fr;
      gap: 1px 10px; margin: 6px 0 0;
    }
    #atlas-preview dt { color: #a0aec0; }
    #atlas-preview dd { margin: 0; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 11px; word-break: break-all; }
    #atlas-preview .file-section { margin-top: 8px; border-top: 1px solid #2d3748; padding-top: 6px; }
    #atlas-preview .file-path { color: #a0aec0; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 10.5px; margin-bottom: 4px; }
    #atlas-preview table { border-collapse: collapse; font-size: 10.5px; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; width: 100%; }
    #atlas-preview th { text-align: left; padding: 2px 6px 2px 0; color: #cbd5e0; font-weight: 600; border-bottom: 1px solid #2d3748; }
    #atlas-preview td { padding: 1px 6px 1px 0; color: #e2e8f0; }
    #atlas-preview .muted { color: #718096; font-style: italic; }
    #atlas-preview .err { color: #fc8181; }
  `;
  document.head.appendChild(css);

  // ---------- overlay -------------------------------------------------- //
  const popover = document.createElement("div");
  popover.id = "atlas-preview";
  document.body.appendChild(popover);

  let currentKey = null;
  let lastPath = "";
  let pathCache = new Map();   // url → preview HTML

  // ---------- table key helpers --------------------------------------- //
  const TABLE_PK = {
    sample_sets:      "sample_set_id",
    group_sets:       "group_set_id",
    interval_sets:    "interval_set_id",
    site_sets:        "site_set_id",
    input_values:     "value_id",
    analysis_results: "result_id",
    analysis_modes:   null,            // composite key
    module_registry:  "module_name",
  };

  function findRow(table, id) {
    const db = window.DB && window.DB[table];
    if (!db) return null;
    if (db.by) return db.by[id];
    if (db.rows) {
      const pk = TABLE_PK[table];
      if (!pk) return null;
      return db.rows.find(r => r[pk] === id) || null;
    }
    return null;
  }

  // ---------- file preview ------------------------------------------- //
  function escapeHtml(s) {
    return String(s ?? "").replace(/[&<>]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;"}[c]));
  }

  async function fetchText(url) {
    const resp = await fetch(url, { cache: "force-cache" });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    return resp.text();
  }

  async function fetchGzipText(url) {
    const resp = await fetch(url, { cache: "force-cache" });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    if (typeof DecompressionStream === "undefined") {
      throw new Error("DecompressionStream unsupported in this browser");
    }
    const ds = new DecompressionStream("gzip");
    const stream = resp.body.pipeThrough(ds);
    const text = await new Response(stream).text();
    return text;
  }

  function renderPreviewTable(text, maxRows) {
    const lines = text.split(/\r?\n/).filter(l => l.length > 0);
    if (lines.length === 0) return '<div class="muted">(empty file)</div>';
    const head = lines[0].split("\t");
    const rows = lines.slice(1, 1 + (maxRows || 8)).map(l => l.split("\t"));
    let html = "<table><thead><tr>";
    for (const h of head) html += `<th>${escapeHtml(h)}</th>`;
    html += "</tr></thead><tbody>";
    for (const r of rows) {
      html += "<tr>";
      for (let i = 0; i < head.length; i++) html += `<td>${escapeHtml(r[i] ?? "")}</td>`;
      html += "</tr>";
    }
    html += "</tbody></table>";
    if (lines.length - 1 > rows.length) {
      html += `<div class="muted">… ${lines.length - 1 - rows.length} more row(s)</div>`;
    }
    return html;
  }

  async function previewFile(path) {
    // path is registry-relative (e.g. "02_sets/samples/broodstock226.samples.tsv").
    // The page is served from /page/, so go up one level.
    const url = "../" + path;
    if (pathCache.has(url)) return pathCache.get(url);
    let html;
    try {
      if (url.endsWith(".gz")) {
        const text = await fetchGzipText(url);
        html = renderPreviewTable(text, 8);
      } else {
        const text = await fetchText(url);
        html = renderPreviewTable(text, 8);
      }
    } catch (e) {
      html = `<div class="err">preview unavailable: ${escapeHtml(e.message)}</div>`;
    }
    pathCache.set(url, html);
    return html;
  }

  // ---------- render --------------------------------------------------- //
  function renderRowDl(row, fields) {
    let dl = "<dl>";
    for (const f of fields) {
      if (row[f] !== undefined && row[f] !== "") {
        dl += `<dt>${f}</dt><dd>${escapeHtml(row[f])}</dd>`;
      }
    }
    dl += "</dl>";
    return dl;
  }

  const FIELDS_BY_TABLE = {
    sample_sets:      ["sample_set_id", "n_samples", "order_key", "path", "notes"],
    group_sets:       ["group_set_id", "sample_set_id", "group_columns", "path", "notes"],
    interval_sets:    ["interval_set_id", "coordinate_system", "interval_type", "n_intervals", "path", "notes"],
    site_sets:        ["site_set_id", "parent_site_set_id", "interval_set_id", "operation", "params_id", "n_sites", "path", "notes"],
    input_values:     ["value_id", "value_type", "sample_set_id", "site_set_id", "interval_set_id", "n_rows", "n_sample_columns", "path", "notes"],
    analysis_results: ["result_id", "analysis_type", "sample_set_id", "group_set_id", "interval_set_id", "site_set_id", "input_value_id", "input_result_id", "method_id", "path", "status", "notes"],
    analysis_modes:   ["analysis_type", "mode", "label", "required_dimensions", "interval_policy", "site_policy", "group_policy", "value_policy", "produces", "module_name", "notes"],
    module_registry:  ["module_name", "version", "family", "biomod_status", "installed", "ready", "stale", "last_run_status", "last_run_qc", "last_run_id", "conda_env_path"],
  };

  async function show(el, table, id) {
    const row = findRow(table, id);
    if (!row) {
      popover.innerHTML = `<div class="hdr"><span class="tag">${table}</span><span>${escapeHtml(id)}</span></div>
        <div class="err">row not found in window.DB.${table}</div>`;
      popover.style.display = "block";
      return;
    }
    const fields = FIELDS_BY_TABLE[table] || Object.keys(row);
    let html = `<div class="hdr"><span class="tag">${table}</span><span>${escapeHtml(id)}</span></div>`;
    html += renderRowDl(row, fields);

    if (row.path) {
      html += `<div class="file-section"><div class="file-path">${escapeHtml(row.path)}</div>`;
      html += `<div class="muted">loading preview…</div></div>`;
    }
    popover.innerHTML = html;
    popover.style.display = "block";

    if (row.path && lastPath !== row.path) {
      lastPath = row.path;
      const filePreviewHtml = await previewFile(row.path);
      if (currentKey === `${table}:${id}`) {
        // Replace the loading placeholder
        const sec = popover.querySelector(".file-section");
        if (sec) {
          sec.innerHTML = `<div class="file-path">${escapeHtml(row.path)}</div>` + filePreviewHtml;
        }
      }
    }
  }

  function position(ev) {
    const margin = 14;
    const w = popover.offsetWidth, h = popover.offsetHeight;
    let x = ev.clientX + margin;
    let y = ev.clientY + margin;
    if (x + w + margin > window.innerWidth)  x = ev.clientX - w - margin;
    if (y + h + margin > window.innerHeight) y = ev.clientY - h - margin;
    if (x < margin) x = margin;
    if (y < margin) y = margin;
    popover.style.left = x + "px";
    popover.style.top  = y + "px";
  }

  // ---------- event wiring -------------------------------------------- //
  document.addEventListener("mouseover", (ev) => {
    const el = ev.target.closest("[data-preview-id]");
    if (!el) return;
    const table = el.dataset.previewTable;
    const id    = el.dataset.previewId;
    if (!table || !id) return;
    const key = `${table}:${id}`;
    if (key === currentKey) return;
    currentKey = key;
    lastPath = "";
    show(el, table, id);
    position(ev);
  });
  document.addEventListener("mousemove", (ev) => {
    if (popover.style.display === "block") position(ev);
  });
  document.addEventListener("mouseout", (ev) => {
    const el = ev.target.closest("[data-preview-id]");
    if (!el) return;
    const to = ev.relatedTarget && ev.relatedTarget.closest("[data-preview-id]");
    if (to && to.dataset.previewId === el.dataset.previewId
          && to.dataset.previewTable === el.dataset.previewTable) {
      return;
    }
    currentKey = null;
    popover.style.display = "none";
  });

  // ---------- helper for page render functions ------------------------ //
  // Pages can call this to wrap an id in a span carrying the right attrs:
  //   previewSpan("sample_sets", "samples_226_v1") → '<code data-…>samples_226_v1</code>'
  window.previewSpan = function (table, id, opts) {
    opts = opts || {};
    if (!id) return "";
    const tag = opts.tag || "code";
    const cls = opts.cls ? ` class="${opts.cls}"` : "";
    return `<${tag}${cls} data-preview-table="${table}" data-preview-id="${id}">${id}</${tag}>`;
  };
})();
