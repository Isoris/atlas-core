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
                        j(REG + "analysis_modes.jsonl")]);
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

  function renderAtlasSummaryCard(panel, atlases, modules, modes) {
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
        <table style="width:100%;border-collapse:collapse;font-size:12px">
          <thead><tr>
            <th style="text-align:left;padding:3px 8px;color:#6c727f;font-weight:500">atlas</th>
            <th style="text-align:right;padding:3px 8px;color:#6c727f;font-weight:500">modules</th>
            <th style="text-align:right;padding:3px 8px;color:#6c727f;font-weight:500">modes</th>
          </tr></thead>
          <tbody>${rows}</tbody>
        </table>
      </div>`;
  }

  // ---- diff & spawn ---- //

  function diffAndSpawn(panels, rules, atlases, modules, modes) {
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

    // Spawn diff
    for (const [pid, _prio] of desired) {
      if (CURRENT_PANELS.has(pid)) continue;
      const panel = panels.find(p => p.panel_id === pid);
      if (!panel) continue;
      const slot = pickSlot(panel);
      if (!slot) continue;
      const html =
        panel.panel_id === "atlas_summary_card"
          ? renderAtlasSummaryCard(panel, atlases, modules, modes)
          : `<div class="conductor-panel" data-panel-id="${pid}"
                  style="background:#fff;border:1px dashed #d8dce3;border-radius:6px;padding:12px 14px;margin-bottom:12px">
               <strong>${panel.label || pid}</strong>
               <div style="margin-top:6px;color:#6c727f;font-size:11.5px;font-style:italic">
                 conductor: no renderer registered for kind "${panel.kind || "?"}" (TODO)
               </div>
             </div>`;
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
    const [panels, rules, atlases, modules, modes] = await load();
    diffAndSpawn(panels, rules, atlases, modules, modes);
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
