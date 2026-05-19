// atlas-colors.js — reads atlases.jsonl + products.jsonl, then applies
// per-atlas color stripes to any product card the page renders.
//
// Pattern: each product card on pages 8/9/10 is a DOM element that
// contains the product_id somewhere in its text. We re-scan the page on
// every render and decorate cards whose product_id resolves to an atlas
// with a left border in the atlas's color.
//
// No new schema. No mutation. Pure visual.

(function () {
  const COLOR = {}; // product_id → hex color (from atlases.primary_products + atlas.color)

  async function loadAtlasColors() {
    async function jsonl(p) {
      try {
        const r = await fetch(p, { cache: "no-store" });
        if (!r.ok) return [];
        return (await r.text()).split("\n").map(l => l.trim()).filter(Boolean).map(JSON.parse);
      } catch { return []; }
    }
    const base = "../01_registry/";
    const [atlases, products] = await Promise.all([
      jsonl(base + "atlases.jsonl"),
      jsonl(base + "products.jsonl"),
    ]);
    // build atlas_id → color
    const aCol = Object.fromEntries(atlases.map(a => [a.atlas_id, a.color || "#6c727f"]));
    // explicit primary_products
    for (const a of atlases) {
      for (const pid of (a.primary_products || [])) COLOR[pid] = aCol[a.atlas_id] || "#6c727f";
    }
    // implicit: any product with atlas: <id> gets the atlas color
    for (const p of products) {
      if (p.product_id && p.atlas && aCol[p.atlas]) COLOR[p.product_id] = aCol[p.atlas];
    }
  }

  function decorate() {
    if (!Object.keys(COLOR).length) return;
    // selectors to scan — cards that might carry a product_id in their text
    const candidates = document.querySelectorAll(
      ".product, .pcard, .panel, .row-item, .est-row, .step, .node"
    );
    for (const el of candidates) {
      // skip already-decorated
      if (el.dataset.atlasColored) continue;
      // pull a likely product_id from the .id child or full text
      const idChild = el.querySelector(".id, .pid, .qid");
      const text = (idChild ? idChild.textContent : el.textContent) || "";
      // try every known product_id; longest-match first to avoid prefix collisions
      let matched = null;
      for (const pid of Object.keys(COLOR).sort((a, b) => b.length - a.length)) {
        if (text.includes(pid)) { matched = pid; break; }
      }
      if (!matched) continue;
      el.style.borderLeft = `4px solid ${COLOR[matched]}`;
      el.style.paddingLeft = (parseInt(getComputedStyle(el).paddingLeft, 10) || 9) + 2 + "px";
      el.dataset.atlasColored = "1";
      el.title = (el.title ? el.title + " · " : "") + "atlas-colored for " + matched;
    }
  }

  // Re-scan after any render. We poll a few times in the first second
  // (cheap) and then on mutation.
  async function init() {
    await loadAtlasColors();
    decorate();
    let n = 0;
    const t = setInterval(() => { decorate(); if (++n > 6) clearInterval(t); }, 250);
    // MutationObserver picks up later re-renders (clicks, filter changes)
    const mo = new MutationObserver(() => decorate());
    mo.observe(document.body, { childList: true, subtree: true });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
