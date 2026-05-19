// search.js — universal search across the registry.
//
// Floating 🔎 button (next to the doc.js button). Click → modal. Type →
// live filter across products / questions / layers / atlases / estimands /
// hooks / analyses. Click a result → navigate to the right page with
// ?focus=<id>. The destination page reads the URL param via
// readFocusParam() (defined here) and pre-selects / scrolls to the item.
//
// Cmd/Ctrl+K opens the modal from anywhere.
//
// No external deps. Single file. Drop-in script.

(function () {
  // -------- routing table: which page handles which id-kind --------
  // The destination URL is hash-style so we don't depend on a server.
  const ROUTE = {
    product:  "readiness.html",
    question: "readiness.html",
    estimand: "readiness.html",
    layer:    "layers.html",
    hook:     "candidate_review.html",   // when it's a candidate_review_hook
    analysis: "catalogue.html",
    atlas:    "workspace_health.html",
  };

  // -------- expose helper for destination pages --------
  window.readFocusParam = function () {
    try {
      const u = new URL(location.href);
      const id = u.searchParams.get("focus");
      const kind = u.searchParams.get("kind") || "";
      return id ? { id, kind } : null;
    } catch { return null; }
  };

  // -------- DB loader --------
  const DB = { ready: false };
  async function loadDB() {
    async function jsonl(p) {
      try {
        const r = await fetch(p, { cache: "no-store" });
        if (!r.ok) return [];
        return r.text().then(t => t.split("\n").map(l => l.trim()).filter(Boolean).map(JSON.parse));
      } catch { return []; }
    }
    const base = "../01_registry/";
    const [products, questions, layers, analyses, hooks, atlases, estimands] = await Promise.all([
      jsonl(base + "products.jsonl"),
      jsonl(base + "questions.jsonl"),
      jsonl(base + "layer_registry.jsonl"),
      jsonl(base + "analysis_registry.jsonl"),
      jsonl(base + "hook_registry.jsonl"),
      jsonl(base + "atlases.jsonl"),
      jsonl(base + "estimands.jsonl"),
    ]);
    DB.items = [];
    for (const r of products)  DB.items.push({ id: r.product_id, kind: "product",  label: r.label || "", subtitle: r.atlas || "biological_object", atlas: r.atlas });
    for (const r of questions) DB.items.push({ id: r.question_id, kind: "question", label: r.label || "", subtitle: (r.tags || []).join(", ") || "question" });
    for (const r of layers)    DB.items.push({ id: r.layer_id,    kind: "layer",    label: r.label || "", subtitle: r.source_kind || "layer" });
    for (const r of analyses)  DB.items.push({ id: r.analysis_id, kind: "analysis", label: r.label || "", subtitle: r.engine || "analysis" });
    for (const r of hooks)     DB.items.push({ id: r.hook_id,     kind: "hook",     label: r.label || "", subtitle: r.page_id || "hook" });
    for (const r of atlases)   DB.items.push({ id: r.atlas_id,    kind: "atlas",    label: r.label || "", subtitle: r.description || "atlas" });
    for (const r of estimands) DB.items.push({ id: r.estimand_id, kind: "estimand", label: r.label || "", subtitle: r.question_id || "estimand" });
    DB.ready = true;
  }

  // -------- inject UI --------
  const css = document.createElement("style");
  css.textContent = `
    .srchbtn {
      position: fixed; bottom: 16px; right: 168px; z-index: 80;
      background: #2d6cb6; color: white; border: none; border-radius: 24px;
      padding: 9px 14px; font: 600 12.5px/1 -apple-system, BlinkMacSystemFont, sans-serif;
      cursor: pointer; box-shadow: 0 3px 12px rgba(0,0,0,0.15);
      letter-spacing: 0.02em;
    }
    .srchbtn:hover { background: #225a96; }
    .srchbtn .kbd {
      display: inline-block; background: rgba(255,255,255,0.18); padding: 1px 5px;
      border-radius: 3px; font-size: 10px; margin-left: 6px;
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    }
    .srchback {
      position: fixed; inset: 0; background: rgba(0,0,0,0.4);
      opacity: 0; pointer-events: none; transition: opacity .14s ease;
      z-index: 90; display: flex; align-items: flex-start; justify-content: center;
      padding-top: 80px;
    }
    .srchback.open { opacity: 1; pointer-events: auto; }
    .srchmodal {
      width: 580px; max-width: 92%; max-height: 70vh; overflow: hidden;
      background: white; border-radius: 8px; box-shadow: 0 12px 36px rgba(0,0,0,0.3);
      display: flex; flex-direction: column;
    }
    .srchinput {
      width: 100%; padding: 14px 18px; border: none; outline: none;
      font: 16px/1.2 -apple-system, BlinkMacSystemFont, sans-serif;
      border-bottom: 1px solid #d8dce3; box-sizing: border-box;
    }
    .srchlist { overflow-y: auto; padding: 4px 0; }
    .srchrow {
      padding: 8px 18px; display: flex; align-items: center; gap: 10px;
      cursor: pointer; font-size: 13px;
    }
    .srchrow:hover, .srchrow.kbd-active { background: #eef4fc; }
    .srchrow .kind {
      display: inline-block; padding: 1px 7px; border-radius: 3px;
      background: #eef0f4; color: #6c727f; font-size: 10px; font-weight: 700;
      text-transform: uppercase; letter-spacing: 0.04em; min-width: 60px; text-align: center;
    }
    .srchrow .kind.product  { background: #e9eef7; color: #2d6cb6; }
    .srchrow .kind.question { background: #fdecd2; color: #b87a14; }
    .srchrow .kind.atlas    { background: #def0e0; color: #2f855a; }
    .srchrow .kind.estimand { background: #efe6f5; color: #6b3aa6; }
    .srchrow .id {
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      font-weight: 600; flex: 0 1 auto; min-width: 0;
    }
    .srchrow .sub { color: #6c727f; font-size: 11.5px; margin-left: auto; max-width: 200px;
                    overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .srchempty { padding: 18px; color: #6c727f; font-style: italic; font-size: 13px; }
    .srchhelp { padding: 8px 18px; border-top: 1px solid #d8dce3; font-size: 11px; color: #6c727f; background: #f7f8fa; }
    .srchhelp .kbd { background: white; border: 1px solid #d8dce3; padding: 1px 5px; border-radius: 3px;
                     font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 10.5px; margin: 0 2px; }
  `;
  document.head.appendChild(css);

  const btn = document.createElement("button");
  btn.className = "srchbtn";
  btn.type = "button";
  btn.innerHTML = `🔎 Search <span class="kbd">⌘K</span>`;
  btn.title = "Search the registry (Cmd/Ctrl+K)";
  document.body.appendChild(btn);

  const back = document.createElement("div");
  back.className = "srchback";
  back.innerHTML = `
    <div class="srchmodal">
      <input class="srchinput" id="__srch_input" placeholder="search products / questions / layers / atlases / estimands…" autocomplete="off">
      <div class="srchlist" id="__srch_list"></div>
      <div class="srchhelp">
        <span class="kbd">↑↓</span> navigate ·
        <span class="kbd">Enter</span> open ·
        <span class="kbd">Esc</span> close
      </div>
    </div>
  `;
  document.body.appendChild(back);

  let cursor = 0, filtered = [];
  const input = back.querySelector("#__srch_input");
  const list  = back.querySelector("#__srch_list");

  function open() {
    back.classList.add("open");
    input.value = ""; input.focus();
    cursor = 0; render("");
  }
  function close() { back.classList.remove("open"); }

  function render(q) {
    if (!DB.ready) {
      list.innerHTML = '<div class="srchempty">loading registry…</div>';
      return;
    }
    q = (q || "").toLowerCase().trim();
    filtered = DB.items.filter(it =>
      !q ||
      it.id.toLowerCase().includes(q) ||
      it.label.toLowerCase().includes(q) ||
      (it.subtitle || "").toLowerCase().includes(q)
    );
    // ranking: id-prefix > id-contains > label-contains
    if (q) {
      filtered.sort((a, b) => {
        const ai = a.id.toLowerCase(), bi = b.id.toLowerCase();
        const ap = ai.startsWith(q) ? 0 : ai.includes(q) ? 1 : 2;
        const bp = bi.startsWith(q) ? 0 : bi.includes(q) ? 1 : 2;
        return ap - bp || ai.localeCompare(bi);
      });
    } else {
      filtered.sort((a, b) => a.id.localeCompare(b.id));
    }
    filtered = filtered.slice(0, 50);
    if (!filtered.length) { list.innerHTML = '<div class="srchempty">no matches</div>'; return; }
    list.innerHTML = filtered.map((it, i) => `
      <div class="srchrow ${i === cursor ? "kbd-active" : ""}" data-i="${i}">
        <span class="kind ${it.kind}">${it.kind}</span>
        <span class="id">${it.id}</span>
        <span class="sub">${it.label || it.subtitle || ""}</span>
      </div>
    `).join("");
    for (const r of list.querySelectorAll(".srchrow")) {
      r.addEventListener("click", () => selectAt(+r.dataset.i));
      r.addEventListener("mousemove", () => { cursor = +r.dataset.i; updateActive(); });
    }
  }
  function updateActive() {
    for (const r of list.querySelectorAll(".srchrow")) r.classList.toggle("kbd-active", +r.dataset.i === cursor);
  }
  function selectAt(i) {
    const it = filtered[i];
    if (!it) return;
    const page = ROUTE[it.kind] || "readiness.html";
    const url = new URL(page, location.href);
    url.searchParams.set("focus", it.id);
    url.searchParams.set("kind", it.kind);
    location.href = url.toString();
  }

  input.addEventListener("input", e => { cursor = 0; render(e.target.value); });
  input.addEventListener("keydown", e => {
    if (e.key === "Escape") { close(); e.preventDefault(); return; }
    if (e.key === "Enter")  { selectAt(cursor); e.preventDefault(); return; }
    if (e.key === "ArrowDown") { cursor = Math.min(cursor + 1, filtered.length - 1); updateActive(); e.preventDefault(); return; }
    if (e.key === "ArrowUp")   { cursor = Math.max(cursor - 1, 0);                   updateActive(); e.preventDefault(); return; }
  });
  btn.addEventListener("click", open);
  back.addEventListener("click", e => { if (e.target === back) close(); });
  document.addEventListener("keydown", e => {
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") { open(); e.preventDefault(); }
  });

  // -------- highlight pulse helper (used by destination pages) --------
  // Pages can call window.flashFocus(elementOrSelector) to highlight an item.
  window.flashFocus = function (el) {
    if (typeof el === "string") el = document.querySelector(el);
    if (!el) return;
    el.scrollIntoView({ behavior: "smooth", block: "center" });
    const orig = el.style.boxShadow;
    el.style.transition = "box-shadow .25s ease";
    el.style.boxShadow = "0 0 0 3px rgba(45,108,182,0.6)";
    setTimeout(() => { el.style.boxShadow = orig; }, 1500);
  };

  loadDB();
})();
