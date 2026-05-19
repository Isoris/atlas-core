// scope.js — shared sticky scope ribbon + getScope() / setScope() helpers.
//
// One workspace-wide scope per browser. Persisted to localStorage. Renders
// a thin ribbon under the top nav showing the current candidate /
// sample_set / interval_set; clicking edits inline.
//
// Pages that already have their own scope picker (6 / 8 / 9 / 10) can opt
// in by calling window.setScope({...}) when their local picker changes,
// and reading window.getScope() on load to honour the persisted scope.
//
// Exposes:
//   window.getScope()                  → { sample_set, interval_set, candidate_id }
//   window.setScope(partial)            → merge & persist + dispatch 'scope-changed'
//   window.onScopeChange(fn)            → subscribe
// Listens to 'storage' for cross-tab sync.

(function () {
  const LS_KEY = "atlas_scope_v1";
  const DEFAULTS = { sample_set: "samples_226_v1", interval_set: "", candidate_id: "" };

  function read() {
    try { return { ...DEFAULTS, ...(JSON.parse(localStorage.getItem(LS_KEY) || "{}")) }; }
    catch { return { ...DEFAULTS }; }
  }
  function write(o) { localStorage.setItem(LS_KEY, JSON.stringify(o)); }

  let state = read();

  // ----- public API -----
  window.getScope = () => ({ ...state });
  window.setScope = (partial) => {
    const next = { ...state, ...(partial || {}) };
    if (JSON.stringify(next) === JSON.stringify(state)) return state;
    state = next;
    write(state);
    render();
    document.dispatchEvent(new CustomEvent("scope-changed", { detail: { ...state } }));
    return state;
  };
  window.onScopeChange = (fn) => document.addEventListener("scope-changed", e => fn(e.detail));

  // ----- UI -----
  const css = document.createElement("style");
  css.textContent = `
    .scoperibbon {
      display: flex; align-items: center; gap: 10px;
      padding: 6px 16px; background: #f0f4fa; border-bottom: 1px solid #d8dce3;
      font-size: 12px; color: #44505d;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
    }
    .scoperibbon .lbl {
      text-transform: uppercase; letter-spacing: 0.05em; font-size: 10.5px;
      color: #6c727f; font-weight: 700;
    }
    .scoperibbon .field {
      display: inline-flex; align-items: center; gap: 4px;
      padding: 2px 4px 2px 8px; border: 1px solid #d8dce3; border-radius: 4px;
      background: white;
    }
    .scoperibbon .field .name { color: #6c727f; font-size: 10.5px; }
    .scoperibbon .field input {
      border: none; outline: none; background: transparent;
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      font-size: 11.5px; font-weight: 600; color: #1a202c;
      min-width: 110px;
      padding: 1px 4px;
    }
    .scoperibbon .field input:focus { background: #fff8d9; }
    .scoperibbon .field .clear {
      border: none; background: transparent; cursor: pointer; padding: 0 6px;
      color: #c0c4cb; font-size: 14px; line-height: 1;
    }
    .scoperibbon .field .clear:hover { color: #b13030; }
    .scoperibbon .note { color: #6c727f; font-size: 11px; margin-left: auto; font-style: italic; }
    .scoperibbon .reset {
      border: 1px solid #d8dce3; background: white; padding: 2px 8px;
      border-radius: 3px; cursor: pointer; font-size: 11px; color: #6c727f;
    }
    .scoperibbon .reset:hover { color: #b13030; border-color: #b13030; }
  `;
  document.head.appendChild(css);

  function render() {
    let bar = document.getElementById("__scope_ribbon");
    if (!bar) {
      bar = document.createElement("div");
      bar.className = "scoperibbon";
      bar.id = "__scope_ribbon";
      // Insert right after the first <nav class="topnav"> if present, else at top.
      const nav = document.querySelector("nav.topnav");
      if (nav && nav.parentNode) nav.parentNode.insertBefore(bar, nav.nextSibling);
      else document.body.insertBefore(bar, document.body.firstChild);
    }
    bar.innerHTML = `
      <span class="lbl">scope</span>
      <span class="field"><span class="name">sample_set</span>
        <input type="text" data-k="sample_set" value="${state.sample_set || ""}" placeholder="e.g. samples_226_v1">
        <button class="clear" title="clear">×</button>
      </span>
      <span class="field"><span class="name">interval_set</span>
        <input type="text" data-k="interval_set" value="${state.interval_set || ""}" placeholder="(none)">
        <button class="clear" title="clear">×</button>
      </span>
      <span class="field"><span class="name">candidate</span>
        <input type="text" data-k="candidate_id" value="${state.candidate_id || ""}" placeholder="(none)">
        <button class="clear" title="clear">×</button>
      </span>
      <span class="note">persisted across pages · auto-saves on Enter / blur</span>
      <button class="reset" title="reset to defaults">reset</button>
    `;
    for (const inp of bar.querySelectorAll("input[data-k]")) {
      const commit = () => window.setScope({ [inp.dataset.k]: inp.value.trim() });
      inp.addEventListener("change", commit);
      inp.addEventListener("blur", commit);
      inp.addEventListener("keydown", e => { if (e.key === "Enter") { inp.blur(); } });
    }
    for (const x of bar.querySelectorAll(".clear")) {
      x.addEventListener("click", e => {
        const inp = x.previousElementSibling;
        inp.value = "";
        window.setScope({ [inp.dataset.k]: "" });
      });
    }
    bar.querySelector(".reset").addEventListener("click", () => {
      state = { ...DEFAULTS };
      write(state); render();
      document.dispatchEvent(new CustomEvent("scope-changed", { detail: { ...state } }));
    });
  }

  // Cross-tab: storage events
  window.addEventListener("storage", (e) => {
    if (e.key !== LS_KEY) return;
    state = read();
    render();
    document.dispatchEvent(new CustomEvent("scope-changed", { detail: { ...state } }));
  });

  // Init
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", render);
  } else {
    render();
  }
})();
