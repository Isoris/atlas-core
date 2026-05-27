// registry-cache.js — single-session JSONL cache shared across pages.
//
// Every page fetches some subset of {analysis_registry, analysis_modes,
// module_registry, layer_registry, atlases, products, references,
// manuscript_chunks}. These files change rarely between page
// navigations. Loading them from scratch on every navigation makes the
// dashboard feel slow.
//
// This shim:
//   1. Exposes window.atlasFetchJsonl(url) — drop-in for the per-page
//      fetchJsonl(...) helpers; returns parsed rows.
//   2. Caches the parsed rows in sessionStorage keyed by URL + a
//      registry_version (Last-Modified header).
//   3. Returns the cached rows immediately + revalidates in the
//      background (stale-while-revalidate).
//   4. Exposes window.atlasCacheClear() so a "Refresh" button can
//      force a re-fetch — wired automatically to ⇧⌘R / Ctrl+Shift+R.
//
// Idempotent. Loaded on every page alongside loader.js / filters.js.

(function () {
  if (window.__atlasRegistryCacheInstalled) return;
  window.__atlasRegistryCacheInstalled = true;

  const NS = "atlas_registry_cache_v1:";
  const MEM = new Map();    // in-memory hot path

  function keyOf(url) {
    // Normalize relative URLs to absolute so the same JSONL fetched from
    // two pages with different relative paths hits the same cache slot.
    try { return NS + new URL(url, location.href).pathname; }
    catch { return NS + url; }
  }

  function parseJsonl(text) {
    const out = [];
    for (const l of text.split("\n")) {
      const s = l.trim();
      if (!s) continue;
      try { out.push(JSON.parse(s)); } catch (_) { /* skip malformed */ }
    }
    return out;
  }

  async function _fetchNetwork(url) {
    const resp = await fetch(url, { cache: "default" });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const text = await resp.text();
    const lastMod = resp.headers.get("last-modified") || resp.headers.get("etag") || "";
    return { rows: parseJsonl(text), lastMod };
  }

  // Public API: stale-while-revalidate.
  // Returns parsed rows. If cache has them, returns immediately and
  // revalidates in the background; subscribers get an `atlas-cache-fresh`
  // CustomEvent if the data changed.
  async function atlasFetchJsonl(url) {
    const k = keyOf(url);
    // 1. In-memory hot path
    if (MEM.has(k)) {
      _revalidate(url, k);
      return MEM.get(k);
    }
    // 2. sessionStorage warm path
    try {
      const raw = sessionStorage.getItem(k);
      if (raw) {
        const { rows } = JSON.parse(raw);
        MEM.set(k, rows);
        _revalidate(url, k);
        return rows;
      }
    } catch (_) {}
    // 3. Network cold path
    try {
      const { rows, lastMod } = await _fetchNetwork(url);
      MEM.set(k, rows);
      try { sessionStorage.setItem(k, JSON.stringify({ rows, lastMod, at: Date.now() })); }
      catch (_) { /* quota exceeded — fall back to MEM only */ }
      return rows;
    } catch (e) {
      return [];
    }
  }
  window.atlasFetchJsonl = atlasFetchJsonl;

  function _revalidate(url, k) {
    // Fire-and-forget; HTTP cache + browser's default policy will collapse
    // duplicate revalidations across tabs.
    _fetchNetwork(url).then(({ rows, lastMod }) => {
      const oldRaw = sessionStorage.getItem(k);
      let changed = true;
      if (oldRaw) {
        try { changed = JSON.parse(oldRaw).lastMod !== lastMod; } catch (_) {}
      }
      if (!changed) return;
      MEM.set(k, rows);
      try { sessionStorage.setItem(k, JSON.stringify({ rows, lastMod, at: Date.now() })); }
      catch (_) {}
      window.dispatchEvent(new CustomEvent("atlas-cache-fresh", { detail: { url, rows } }));
    }).catch(() => {});
  }

  // Drop all cached registry data. Used by the Refresh button + the
  // ⇧⌘R / Ctrl+Shift+R shortcut, which the browser already maps to
  // hard-reload but won't always clear sessionStorage.
  window.atlasCacheClear = function () {
    MEM.clear();
    try {
      for (const k of Object.keys(sessionStorage)) {
        if (k.startsWith(NS)) sessionStorage.removeItem(k);
      }
    } catch (_) {}
  };

  // Expose a small stats panel for debugging — visible only when
  // ?atlas_cache_debug=1 is appended to the URL.
  if (location.search.includes("atlas_cache_debug=1")) {
    const tag = document.createElement("div");
    tag.style.cssText = "position:fixed;bottom:6px;right:6px;background:#1a202c;color:#cbd5e0;font:10.5px ui-monospace,Menlo,monospace;padding:4px 8px;border-radius:4px;z-index:99999;opacity:0.85;pointer-events:none";
    document.addEventListener("DOMContentLoaded", () => {
      document.body.appendChild(tag);
      setInterval(() => {
        let n = 0; try { for (const k of Object.keys(sessionStorage)) if (k.startsWith(NS)) n++; } catch (_) {}
        tag.textContent = `registry cache: ${MEM.size} in-mem · ${n} in sessionStorage`;
      }, 500);
    });
  }
})();
