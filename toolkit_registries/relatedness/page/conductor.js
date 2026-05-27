// conductor.js — DYNAMIC_PANELS_SPEC §13 vertical slice.
//
// One rule + one panel + the diff/spawn/hydrate loop, proving the spec's
// runtime contract. Larger panel inventory + multi-graph gating + the
// event bus are deferred to follow-up PRs.
//
// What it does on every page load:
//   1. Load 01_registry/{panels,spawn_rules}.jsonl
//   2. Identify the current page_id from its document title (`Atlas-core — page N`
//      tag, or fallback to <body data-page>)
//   3. Evaluate every spawn_rule against the current page + scope
//   4. For each spawn directive: find the panel row, find a target slot
//      (<div data-slot="…">), render the panel's `kind` into it
//   5. Idempotent: re-running diff does not double-render
//
// Panels with kind: "card" and data_source.kind: "registry" are rendered
// inline; other kinds (table / chart / chain / …) log a TODO and skip
// (covered when the next panels arrive).

(function () {
  if (window.__atlasConductorInstalled) return;
  window.__atlasConductorInstalled = true;

  const REG = "../01_registry/";
  const CURRENT_PANELS = new Map();   // panel_id → DOM element

  function pageIdFromDoc() {
    const tag = document.querySelector(".topnav .tag");
    if (tag) {
      const m = tag.textContent.match(/page\s+(\d+)/i);
      if (m) {
        const n = +m[1];
        const map = { 1: "conversation", 2: "action", 3: "registries",
                      4: "catalogue", 5: "layers", 6: "candidate_review",
                      7: "graph_builder", 8: "readiness", 9: "layer_connector",
                      10: "workspace_health", 11: "queue", 12: "manuscript",
                      13: "adapters" };
        return map[n] || "";
      }
    }
    const b = document.body && document.body.dataset.page;
    return b || "";
  }

  async function load() {
    const j = (url) => (typeof window.atlasFetchJsonl === "function")
      ? window.atlasFetchJsonl(url)
      : fetch(url, { cache: "default" }).then(r => r.ok ? r.text() : "")
          .then(t => (t || "").split("\n").map(l => l.trim()).filter(Boolean).map(JSON.parse));
    return Promise.all([j(REG + "panels.jsonl"), j(REG + "spawn_rules.jsonl"),
                        j(REG + "atlases.jsonl"), j(REG + "module_registry.jsonl"),
                        j(REG + "analysis_modes.jsonl"), j(REG + "analysis_registry.jsonl"),
                        j(REG + "cohorts.jsonl"), j(REG + "manuscript_chunks.jsonl"),
                        j(REG + "references.jsonl")]);
  }

  function pickSlot(panel) {
    const aff = panel.slot_affinity || ["main"];
    for (const s of aff) {
      const el = document.querySelector(`[data-slot="${s}"]`);
      if (el && el.children.length < (+(el.dataset.maxPanels || 8))) return el;
    }
    return null;
  }

  function atlasBadge(atlasId, atlases) {
    const a = atlases.find(x => x.atlas_id === atlasId);
    if (!a) return "";
    const bg = a.color || "#6c727f";
    return `<span style="display:inline-block;padding:1px 6px;border-radius:3px;font-size:10.5px;font-weight:600;color:white;background:${bg}">${a.icon || ""} ${a.label || atlasId}</span>`;
  }

  // ---- Card shell (shared chrome) ---- //
  function cardShell(panel, bodyHtml) {
    return `
      <div class="conductor-panel" data-panel-id="${panel.panel_id}"
           style="background:#fff;border:1px solid #d8dce3;border-radius:6px;
                  padding:12px 14px;margin-bottom:12px;min-width:${panel.fluidity.min_width_px.comfortable}px">
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;
                    padding-bottom:8px;border-bottom:1px solid #d8dce3">
          <strong style="font-size:13px">${panel.label}</strong>
          <span style="margin-left:auto;font-size:10px;color:#6c727f;text-transform:uppercase;letter-spacing:0.04em">conductor-spawned</span>
          ${panel.dismissable !== false
            ? `<button data-act="dismiss" title="Dismiss"
                       style="cursor:pointer;border:1px solid #d8dce3;background:transparent;color:#6c727f;
                              border-radius:3px;width:18px;height:18px;line-height:14px;font-size:13px;padding:0">✕</button>`
            : ""}
        </div>
        ${bodyHtml}
      </div>`;
  }

  // ---- Renderers ---- //

  function renderAtlasSummaryCard(panel, ctx) {
    const { atlases, modules, modes } = ctx;
    const modBy = {}, modeBy = {};
    for (const m of modules)  (modBy[m.atlas]  = modBy[m.atlas]  || []).push(m);
    for (const m of modes) {
      const mod = modules.find(x => x.module_name === m.module_name);
      const a = mod && mod.atlas;
      if (a) (modeBy[a] = modeBy[a] || []).push(m);
    }
    const rows = atlases
      .filter(a => a.atlas_id !== "atlas_core" && a.status !== "deprecated")
      .map(a => {
        const m = (modBy[a.atlas_id] || []).length;
        const md = (modeBy[a.atlas_id] || []).length;
        return `<tr>
          <td style="padding:3px 8px">${atlasBadge(a.atlas_id, atlases)}</td>
          <td style="padding:3px 8px;text-align:right;font-family:ui-monospace,Menlo,monospace">${m}</td>
          <td style="padding:3px 8px;text-align:right;font-family:ui-monospace,Menlo,monospace">${md}</td>
        </tr>`;
      }).join("");
    return cardShell(panel, `
      <table style="width:100%;border-collapse:collapse;font-size:12px">
        <thead><tr>
          <th style="text-align:left;padding:3px 8px;color:#6c727f;font-weight:500">atlas</th>
          <th style="text-align:right;padding:3px 8px;color:#6c727f;font-weight:500">modules</th>
          <th style="text-align:right;padding:3px 8px;color:#6c727f;font-weight:500">modes</th>
        </tr></thead>
        <tbody>${rows}</tbody>
      </table>`);
  }

  function renderCohortSummaryCard(panel, ctx) {
    const { cohorts, atlases } = ctx;
    const byId = Object.fromEntries(cohorts.map(c => [c.cohort_id, c]));
    // Hierarchy: render roots first, then children indented one level
    const roots = cohorts.filter(c => !c.parent_cohort);
    const children = (rid) => cohorts.filter(c => c.parent_cohort === rid);
    const ownerBadges = (ows) => (ows || []).map(o => atlasBadge(o, atlases)).join(" ");
    const row = (c, depth) => `<tr>
      <td style="padding:3px 8px;font-family:ui-monospace,Menlo,monospace;font-size:11.5px">
        ${"&nbsp;".repeat(depth * 4)}${depth > 0 ? "└─ " : ""}<code style="font-weight:600">${c.cohort_id}</code>
      </td>
      <td style="padding:3px 8px;text-align:right;font-family:ui-monospace,Menlo,monospace">${c.n_samples}</td>
      <td style="padding:3px 8px;font-size:11px">${ownerBadges(c.owner_atlases)}</td>
    </tr>`;
    const rows = roots.flatMap(r => [row(r, 0), ...children(r.cohort_id).map(c => row(c, 1))]).join("");
    return cardShell(panel, `
      <table style="width:100%;border-collapse:collapse;font-size:12px">
        <thead><tr>
          <th style="text-align:left;padding:3px 8px;color:#6c727f;font-weight:500">cohort</th>
          <th style="text-align:right;padding:3px 8px;color:#6c727f;font-weight:500">n</th>
          <th style="text-align:left;padding:3px 8px;color:#6c727f;font-weight:500">owners</th>
        </tr></thead>
        <tbody>${rows}</tbody>
      </table>`);
  }

  function renderAdapterCompletenessCard(panel, ctx) {
    const { registry } = ctx;
    // Filter to analysis_registry rows that have a definition_path under analysis/
    const adap = registry.filter(r => (r.definition_path || "").startsWith("analysis/")
                                    || (r.default_runner || "").startsWith("analysis."));
    // The conductor doesn't probe the filesystem; we report the registered surface
    // and tag each as "shipped" vs "pending" by inspecting status.
    const rows = adap.map(r => {
      const tag = r.status === "experimental" || r.status === "active" ? "ok" : "warn";
      const color = tag === "ok" ? "#2f855a" : "#b7791f";
      return `<tr>
        <td style="padding:3px 8px;font-family:ui-monospace,Menlo,monospace;font-size:11.5px"><code>${r.analysis_id}</code></td>
        <td style="padding:3px 8px;font-size:11px;color:#6c727f">${r.engine || "?"}</td>
        <td style="padding:3px 8px"><span style="background:${color};color:#fff;padding:1px 7px;border-radius:3px;font-size:10px;font-weight:600;text-transform:uppercase">${r.status || "?"}</span></td>
      </tr>`;
    }).join("");
    const total = adap.length;
    return cardShell(panel, `
      <div style="font-size:11.5px;color:#6c727f;margin-bottom:6px">
        ${total} registered adapter${total === 1 ? "" : "s"} · open page 13 for the 6/6 file-shipping detail
      </div>
      <table style="width:100%;border-collapse:collapse;font-size:12px">
        <thead><tr>
          <th style="text-align:left;padding:3px 8px;color:#6c727f;font-weight:500">adapter</th>
          <th style="text-align:left;padding:3px 8px;color:#6c727f;font-weight:500">engine</th>
          <th style="text-align:left;padding:3px 8px;color:#6c727f;font-weight:500">status</th>
        </tr></thead>
        <tbody>${rows}</tbody>
      </table>`);
  }

  function renderManuscriptChunksSummaryCard(panel, ctx) {
    const { chunks, refs, atlases } = ctx;
    // Per-(atlas, section) counts
    const grid = {};
    for (const c of chunks) {
      const a = c.atlas, s = c.section;
      grid[a] = grid[a] || { methods: 0, results: 0, discussion: 0 };
      grid[a][s] = (grid[a][s] || 0) + 1;
    }
    const atlasOrder = atlases.map(x => x.atlas_id).filter(a => grid[a]);
    const rows = atlasOrder.map(aid => {
      const g = grid[aid];
      return `<tr>
        <td style="padding:3px 8px">${atlasBadge(aid, atlases)}</td>
        <td style="padding:3px 8px;text-align:right;font-family:ui-monospace,Menlo,monospace">${g.methods || 0}</td>
        <td style="padding:3px 8px;text-align:right;font-family:ui-monospace,Menlo,monospace">${g.results || 0}</td>
        <td style="padding:3px 8px;text-align:right;font-family:ui-monospace,Menlo,monospace">${g.discussion || 0}</td>
      </tr>`;
    }).join("");
    // Orphan ref count (refs not cited by any chunk)
    const cited = new Set();
    for (const c of chunks) {
      for (const r of (c.references || [])) cited.add(r);
      const re = /\[@([A-Za-z][A-Za-z0-9_]*)\]/g; let m;
      while ((m = re.exec(c.template || "")) !== null) cited.add(m[1]);
    }
    const orphans = (refs || []).filter(r => !cited.has(r.ref_id)).length;
    return cardShell(panel, `
      <div style="font-size:11.5px;color:#6c727f;margin-bottom:6px">
        ${chunks.length} chunks · ${refs.length} references · <strong style="color:${orphans ? '#b7791f' : '#2f855a'}">${orphans}</strong> orphan ref${orphans === 1 ? "" : "s"}
      </div>
      <table style="width:100%;border-collapse:collapse;font-size:12px">
        <thead><tr>
          <th style="text-align:left;padding:3px 8px;color:#6c727f;font-weight:500">atlas</th>
          <th style="text-align:right;padding:3px 8px;color:#6c727f;font-weight:500">methods</th>
          <th style="text-align:right;padding:3px 8px;color:#6c727f;font-weight:500">results</th>
          <th style="text-align:right;padding:3px 8px;color:#6c727f;font-weight:500">discussion</th>
        </tr></thead>
        <tbody>${rows}</tbody>
      </table>`);
  }

  async function renderPlansSummaryCard(panel, _ctx) {
    // Reads 02_queue/plans/index.json directly; falls back to the example
    // seed if no live index exists. Not run through atlasFetchJsonl because
    // the file is JSON, not JSONL.
    async function getJson(url) {
      try { const r = await fetch(url, { cache: "default" }); return r.ok ? r.json() : null; }
      catch { return null; }
    }
    const idx = (await getJson("../02_queue/plans/index.json"))
             || (await getJson("../02_queue/plans/index.example.json"));
    if (!idx) {
      return cardShell(panel, `
        <div style="font-size:12px;color:var(--muted);font-style:italic;padding:6px 0">
          No plan index. Run <code>python3 -m toolkit_registries.relatedness.lib.plan_generator</code> to populate.
        </div>`);
    }
    const entries = idx.entries || [];
    let ready = 0, oneStep = 0, blocked = 0;
    for (const e of entries) {
      const b = e.n_blocked || 0;
      if (b === 0) ready++;
      else if (b === 1) oneStep++;
      else blocked++;
    }
    const stat = (n, lbl, color) =>
      `<div style="flex:1;padding:8px 10px;background:${color}18;border-radius:4px;text-align:center">
         <div style="font-size:18px;font-weight:600;color:${color}">${n}</div>
         <div style="font-size:10.5px;color:#6c727f;text-transform:uppercase;letter-spacing:0.04em">${lbl}</div>
       </div>`;
    return cardShell(panel, `
      <div style="font-size:11.5px;color:var(--muted);margin-bottom:8px">
        ${entries.length} plan${entries.length === 1 ? "" : "s"} indexed · source: <code style="font-size:11px">02_queue/plans/</code>
      </div>
      <div style="display:flex;gap:6px">
        ${stat(ready,   "ready",     "#2f855a")}
        ${stat(oneStep, "one step",  "#2b6cb0")}
        ${stat(blocked, "blocked",   "#c53030")}
      </div>
      <div style="margin-top:8px;font-size:11.5px">
        <a href="plans.html" style="color:#2b6cb0;text-decoration:none">→ review on page 14</a>
      </div>`);
  }

  async function renderBridgeSummaryCard(panel, ctx) {
    // Reads external_databases.jsonl (in ctx via atlasFetchJsonl) and the
    // runtime 02_queue/bridge_log.jsonl (newline JSONL of {ts, db_id,
    // endpoint_id, url, ok, elapsed_ms}).
    async function getLog(url) {
      try {
        const r = await fetch(url, { cache: "no-store" });
        if (!r.ok) return null;
        const rows = (await r.text()).split("\n").filter(Boolean).map(l => {
          try { return JSON.parse(l); } catch { return null; }
        }).filter(Boolean);
        return rows.length ? rows : null;
      } catch { return null; }
    }
    const dbs = await window.atlasFetchJsonl("../01_registry/external_databases.jsonl");
    let log = await getLog("../02_queue/bridge_log.jsonl");
    let isExample = false;
    if (!log) {
      log = await getLog("../02_queue/bridge_log.example.jsonl") || [];
      isExample = log.length > 0;
    }
    // Per-db roll-ups
    const perDb = {};
    for (const db of dbs) {
      perDb[db.db_id] = { db, n: 0, ok: 0, fail: 0, last: null, median_ms: null, samples: [] };
    }
    for (const e of log) {
      const r = perDb[e.db_id];
      if (!r) continue;
      r.n += 1;
      if (e.ok) r.ok += 1; else r.fail += 1;
      if (!r.last || e.ts > r.last.ts) r.last = e;
      if (typeof e.elapsed_ms === "number") r.samples.push(e.elapsed_ms);
    }
    for (const k of Object.keys(perDb)) {
      const s = perDb[k].samples.slice().sort((a, b) => a - b);
      perDb[k].median_ms = s.length ? s[Math.floor(s.length / 2)] : null;
    }
    const rows = Object.values(perDb).map(r => {
      const db = r.db;
      const ts = r.last ? r.last.ts.slice(0, 19).replace("T", " ") : "—";
      const statusPill = r.n === 0
        ? `<span style="font-size:10px;color:#a0aec0;font-style:italic">no calls yet</span>`
        : r.last && r.last.ok
          ? `<span style="background:#2f855a;color:white;padding:1px 6px;border-radius:3px;font-size:10px;font-weight:600;text-transform:uppercase">ok</span>`
          : `<span style="background:#c53030;color:white;padding:1px 6px;border-radius:3px;font-size:10px;font-weight:600;text-transform:uppercase">fail</span>`;
      const med = r.median_ms != null ? `${r.median_ms} ms` : "—";
      return `<tr>
        <td style="padding:3px 8px"><code style="font-weight:600">${db.db_id}</code></td>
        <td style="padding:3px 8px;text-align:right;font-family:ui-monospace,Menlo,monospace">${r.n}</td>
        <td style="padding:3px 8px;text-align:right;font-family:ui-monospace,Menlo,monospace">${med}</td>
        <td style="padding:3px 8px">${statusPill}</td>
        <td style="padding:3px 8px;font-size:10.5px;color:#6c727f;font-family:ui-monospace,Menlo,monospace">${ts}</td>
      </tr>`;
    }).join("");
    const totalCalls = log.length;
    const totalOk    = log.filter(e => e.ok).length;
    return cardShell(panel, `
      <div style="font-size:11.5px;color:var(--muted);margin-bottom:8px">
        ${dbs.length} external DBs registered · ${totalCalls} call${totalCalls === 1 ? "" : "s"} logged
        ${totalCalls > 0 ? ` · ${totalOk}/${totalCalls} ok` : ""}
        · log: <code style="font-size:11px">02_queue/bridge_log${isExample ? ".example" : ""}.jsonl</code>
        ${isExample ? ` · <span style="background:#d69e2e;color:white;padding:1px 5px;border-radius:3px;font-size:10px;font-weight:600;text-transform:uppercase">example</span>` : ""}
      </div>
      <table style="width:100%;border-collapse:collapse;font-size:12px">
        <thead><tr>
          <th style="text-align:left;padding:3px 8px;color:#6c727f;font-weight:500">db</th>
          <th style="text-align:right;padding:3px 8px;color:#6c727f;font-weight:500">calls</th>
          <th style="text-align:right;padding:3px 8px;color:#6c727f;font-weight:500">median</th>
          <th style="text-align:left;padding:3px 8px;color:#6c727f;font-weight:500">last</th>
          <th style="text-align:left;padding:3px 8px;color:#6c727f;font-weight:500">when</th>
        </tr></thead>
        <tbody>${rows}</tbody>
      </table>`);
  }

  async function renderAddonsSummaryCard(panel, _ctx) {
    const addons = await window.atlasFetchJsonl("../01_registry/addons.jsonl");
    if (!addons.length) {
      return cardShell(panel, `
        <div style="font-size:12px;color:var(--muted);font-style:italic;padding:6px 0">
          addons.jsonl is empty.
        </div>`);
    }
    const KINDS = ["panel", "page", "page_extension", "analysis", "bridge", "validator"];
    const perKind = {};
    for (const k of KINDS) perKind[k] = { n: 0, active: 0, experimental: 0, deprecated: 0, ids: [] };
    const unknownKind = { n: 0, ids: [] };
    for (const a of addons) {
      const k = a.kind;
      const tgt = perKind[k] || unknownKind;
      tgt.n += 1;
      tgt.ids.push(a.addon_id);
      if (k in perKind) {
        const s = a.status;
        if (s === "active") tgt.active += 1;
        else if (s === "experimental") tgt.experimental += 1;
        else if (s === "deprecated") tgt.deprecated += 1;
      }
    }
    const rows = KINDS.map(k => {
      const r = perKind[k];
      if (!r.n) return "";
      const statusBlock = [
        r.active        ? `<span style="background:#2f855a;color:white;padding:1px 5px;border-radius:3px;font-size:10px;font-weight:600">${r.active} active</span>` : "",
        r.experimental  ? `<span style="background:#d69e2e;color:white;padding:1px 5px;border-radius:3px;font-size:10px;font-weight:600">${r.experimental} exp</span>`    : "",
        r.deprecated    ? `<span style="background:#6c727f;color:white;padding:1px 5px;border-radius:3px;font-size:10px;font-weight:600">${r.deprecated} dep</span>`      : "",
      ].filter(Boolean).join(" ");
      return `<tr>
        <td style="padding:3px 8px"><code style="font-weight:600">${k}</code></td>
        <td style="padding:3px 8px;text-align:right;font-family:ui-monospace,Menlo,monospace">${r.n}</td>
        <td style="padding:3px 8px">${statusBlock}</td>
      </tr>`;
    }).filter(Boolean).join("");
    return cardShell(panel, `
      <div style="font-size:11.5px;color:var(--muted);margin-bottom:8px">
        ${addons.length} addon${addons.length === 1 ? "" : "s"} registered across ${Object.values(perKind).filter(r => r.n).length} kind${Object.values(perKind).filter(r => r.n).length === 1 ? "" : "s"}
        · per ADDON_SPEC §10
      </div>
      <table style="width:100%;border-collapse:collapse;font-size:12px">
        <thead><tr>
          <th style="text-align:left;padding:3px 8px;color:#6c727f;font-weight:500">kind</th>
          <th style="text-align:right;padding:3px 8px;color:#6c727f;font-weight:500">n</th>
          <th style="text-align:left;padding:3px 8px;color:#6c727f;font-weight:500">status</th>
        </tr></thead>
        <tbody>${rows}</tbody>
      </table>`);
  }

  // Renderer dispatch by panel_id (each registered panel has its own renderer)
  const RENDERERS = {
    atlas_summary_card:              renderAtlasSummaryCard,
    cohort_summary_card:             renderCohortSummaryCard,
    adapter_completeness_card:       renderAdapterCompletenessCard,
    manuscript_chunks_summary_card:  renderManuscriptChunksSummaryCard,
    plans_summary_card:              renderPlansSummaryCard,
    addons_summary_card:             renderAddonsSummaryCard,
    bridge_summary_card:             renderBridgeSummaryCard,
  };

  // ---- diff & spawn ---- //

  async function diffAndSpawn(panels, rules, ctx) {
    const pageId = pageIdFromDoc();
    const desired = new Map();   // panel_id → priority
    for (const r of rules) {
      const when = r.when || {};
      const pages = when.page || [];
      if (pages.length && !pages.includes(pageId)) continue;
      for (const s of (r.then && r.then.spawn) || []) {
        const cur = desired.get(s.panel_id);
        if (!cur || s.priority > cur) desired.set(s.panel_id, s.priority);
      }
    }
    // honor user dismissals (atlas_panel_dismissals_v1 — §8 of the spec)
    const dismissals = JSON.parse(localStorage.getItem("atlas_panel_dismissals_v1") || "{}");
    const scopeKey = pageId;   // simple v0; full scope-aware key lands later
    for (const pid of Object.keys(dismissals[scopeKey] || {})) desired.delete(pid);

    // Spawn diff (ordered by priority — higher first into each slot)
    const desiredList = [...desired].sort((a, b) => b[1] - a[1]);
    for (const [pid, _prio] of desiredList) {
      if (CURRENT_PANELS.has(pid)) continue;
      const panel = panels.find(p => p.panel_id === pid);
      if (!panel) continue;
      const slot = pickSlot(panel);
      if (!slot) continue;
      const renderer = RENDERERS[pid];
      const rendered = renderer
        ? renderer(panel, ctx)
        : `<div class="conductor-panel" data-panel-id="${pid}"
                style="background:#fff;border:1px dashed #d8dce3;border-radius:6px;padding:12px 14px;margin-bottom:12px">
             <strong>${panel.label || pid}</strong>
             <div style="margin-top:6px;color:#6c727f;font-size:11.5px;font-style:italic">
               conductor: no renderer registered for kind "${panel.kind || "?"}" (TODO)
             </div>
           </div>`;
      const html = (rendered && typeof rendered.then === "function") ? await rendered : rendered;
      const tmp = document.createElement("div");
      tmp.innerHTML = html;
      const el = tmp.firstElementChild;
      slot.appendChild(el);
      CURRENT_PANELS.set(pid, el);
      el.querySelector('[data-act="dismiss"]')?.addEventListener("click", () => {
        const d = JSON.parse(localStorage.getItem("atlas_panel_dismissals_v1") || "{}");
        d[scopeKey] = d[scopeKey] || {};
        d[scopeKey][pid] = true;
        localStorage.setItem("atlas_panel_dismissals_v1", JSON.stringify(d));
        el.remove();
        CURRENT_PANELS.delete(pid);
      });
    }
    // Dismiss diff
    for (const [pid, el] of CURRENT_PANELS) {
      if (!desired.has(pid)) { el.remove(); CURRENT_PANELS.delete(pid); }
    }
  }

  async function tick() {
    const [panels, rules, atlases, modules, modes, registry, cohorts, chunks, refs] = await load();
    await diffAndSpawn(panels, rules, { atlases, modules, modes, registry, cohorts, chunks, refs });
  }

  // Trigger on load + on scope change + on cache refresh
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", tick);
  } else {
    tick();
  }
  document.addEventListener("scope-changed", tick);
  window.addEventListener("atlas-cache-fresh", tick);
})();
