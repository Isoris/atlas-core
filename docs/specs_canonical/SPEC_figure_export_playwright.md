# SPEC_figure_export_playwright — reproducible publication export for genomic figures

Status: **handover spec (to be implemented in `inversion-atlas`)**. Not wired
in atlas-core.

> **Scope & honesty note.** This spec is for the *genomic* figures — the
> LG-scale inversion views: local-PCA panels, dosage/karyotype tracks, ribbon
> / synteny ribbons, and dense heatmaps. Those figures live in the
> `inversion-atlas` repository, **not** in atlas-core. atlas-core's own
> figures (the registry architecture graphs) are pure vector and are exported
> by `toolkit_registries/relatedness/lib/graph_figure_export.py` with no
> browser at all — see §7. This document cannot be run or committed from the
> atlas-core environment; it is a drop-in design to implement *there*.

---

## §1 Why not a screenshot

A browser screenshot and the browser's own PDF print use *different rendering
paths*, and a manual OS/Firefox screenshot adds a third. They diverge on:

- CSS transforms (rasterized at different effective resolutions),
- canvas backing-store resolution (depends on `devicePixelRatio`),
- font substitution when a webfont has not finished loading,
- clipped / `overflow:hidden` / off-screen elements (silently dropped),
- `position: sticky/fixed` elements (move or duplicate),
- SVG filters / drop-shadows (rendered differently per path),
- browser zoom (changes layout, not just scale).

For a thesis/journal figure none of this is acceptable: the figure must be
**deterministic** and **reproducible** from data. The contract is:

```
same data  ->  one drawing function  ->  fixed viewport  ->  white background
           ->  no UI chrome  ->  embedded/standard font  ->  vector where
           possible, high-res raster only where unavoidable
```

## §2 Classify each figure layer first

A genomic figure is usually *mixed*. Split it by layer and export each by the
right path — do **not** screenshot the whole mixed thing:

| Layer | Examples | Export path |
|-------|----------|-------------|
| Vector | axes, ticks, labels, ribbons, gene tracks, breakpoint marks, legend | **true SVG** (serialize the `<svg>`; §5) |
| Raster | dense per-sample heatmaps, LD matrices, read pile-ups | **high-res PNG** rendered at 2–4× *internally* (§6) |
| Composite | a panel that is SVG over a canvas raster | render both into one fixed export root, then snapshot (§4) |

The goal is that every line, label and axis is *vector* in the final figure,
and only genuinely pixel data (heatmaps) is raster.

## §3 Build a real export MODE, not an export button

Add a dedicated render path that strips the product down to one clean figure.
A query param is enough:

```
/atlas.html?figure=lg27&export=1
```

When `export=1`:

1. hide every UI element (panels, toolbars, scrollers, tooltips) — render
   only `#export-root`;
2. set a **fixed** figure size (e.g. 1800 × 1200), independent of window size;
3. force a white (or transparent, your choice) background;
4. render exactly **one** figure into `#export-root`, by the same drawing
   function used on screen — never a second "export-only" code path, or the
   figure will drift from what you validated;
5. when the figure is fully drawn (fonts loaded, canvas painted, async data
   resolved), set a render-complete flag the exporter can await:

```js
// after the figure's final draw call:
window.__figureReady = true;
```

A single `renderFigure({...})` entry point keeps screen and export identical:

```js
renderFigure({
  target:      "#export-root",
  figureId:    params.get("figure"),   // e.g. "lg27"
  width:       1800,
  height:      1200,
  mode:        "publication",          // white bg, embedded font, no UI
  showAxes:    true,
  showLegend:  true,
  showUI:      false,
  onComplete:  () => { window.__figureReady = true; },
});
```

## §4 The Playwright exporter (composite figures)

Deterministic because it controls the viewport, the device-scale-factor, and —
critically — **waits on `__figureReady` rather than a fixed timeout**. A
`waitForTimeout` is a race; a flag is reproducible.

```js
// export_figure.js   —   node export_figure.js lg27
const { chromium } = require("playwright");

(async () => {
  const figure = process.argv[2] || "lg27";
  const W = 1800, H = 1200, SCALE = 3;        // 3× for crisp raster layers

  const browser = await chromium.launch();
  const page = await browser.newPage({
    viewport: { width: W, height: H },
    deviceScaleFactor: SCALE,
  });

  await page.goto(
    `http://localhost:8766/atlas.html?figure=${figure}&export=1`,
    { waitUntil: "networkidle" }
  );

  // deterministic wait: the figure tells us when it is done
  await page.waitForFunction(() => window.__figureReady === true, { timeout: 30000 });
  await page.evaluate(() => document.fonts.ready);   // fonts settled

  const root = page.locator("#export-root");

  // (a) high-res raster snapshot of the composite (deviceScaleFactor applies)
  await root.screenshot({ path: `figure_${figure}.png` });

  // (b) vector-ish PDF of the page (good for vector-dominant figures)
  await page.pdf({
    path: `figure_${figure}.pdf`,
    width: `${W}px`,
    height: `${H}px`,
    printBackground: true,
    pageRanges: "1",
  });

  await browser.close();
})();
```

Notes:

- `deviceScaleFactor: 3` gives ~3× pixel density for raster layers — this is
  the right way to get DPI, **not** browser zoom (zoom changes layout).
- `page.pdf()` is Chromium-only and is best for vector-dominant figures; for
  a heatmap-dominant figure prefer the PNG at high scale.
- Pin a chromium version in `package.json` so the render path is frozen across
  machines (part of reproducibility).

## §5 Vector layers — export true SVG (best case)

For the axes/labels/ribbons/tracks SVG, do not rasterize at all — serialize it:

```js
function downloadSVG(svgEl, filename = "figure.svg") {
  let src = new XMLSerializer().serializeToString(svgEl);
  if (!/^<svg[^>]+xmlns=/.test(src)) {
    src = src.replace("<svg", '<svg xmlns="http://www.w3.org/2000/svg"');
  }
  const url = URL.createObjectURL(new Blob([src], { type: "image/svg+xml;charset=utf-8" }));
  const a = Object.assign(document.createElement("a"), { href: url, download: filename });
  a.click();
  URL.revokeObjectURL(url);
}
```

Then convert to PDF *after visual verification*:

```
cairosvg figure.svg -o figure.pdf
# or:  rsvg-convert -f pdf -o figure.pdf figure.svg
# or:  inkscape figure.svg --export-filename figure.pdf
```

Embed fonts (or convert text to outlines) at the SVG→PDF step so the figure is
self-contained on a print system that lacks your webfont.

## §6 Raster layers — high-res PNG (render at scale, not zoom)

Canvas cannot become true SVG without redrawing. For a heatmap, render the
canvas at an internal multiple of its display size, then export:

```js
function renderHeatmapAtScale(drawFn, wCss, hCss, scale = 3) {
  const c = document.createElement("canvas");
  c.width = wCss * scale; c.height = hCss * scale;
  const ctx = c.getContext("2d");
  ctx.scale(scale, scale);            // draw in CSS units, store at scale×
  drawFn(ctx, wCss, hCss);
  return c;
}
function downloadCanvasPNG(canvas, filename = "heatmap.png") {
  const a = Object.assign(document.createElement("a"),
    { href: canvas.toDataURL("image/png"), download: filename });
  a.click();
}
```

## §7 What atlas-core already does (reference, not to reimplement)

atlas-core's figures are the *registry architecture graphs* (layer /
atlas-dependency / chain / panel-coverage). They are pure node-edge vector, so
they need **no browser**: `graph_figure_export.py` reads
`01_registry/graphs/*_graph.json`, runs one deterministic layered layout, and
emits white-background SVG with an embedded-standard font. Output is
byte-identical across runs (no embedded timestamp), so the same registry state
always yields the same figure. Use that as the template for the *vector* parts
of the genomic figures: data → one drawing function → fixed size → SVG.

```
python3 -m toolkit_registries.relatedness.lib.graph_figure_export --all
python3 -m ...graph_figure_export --graph atlas_dependency --out fig.svg --pdf
```

## §8 Implementation checklist (inversion-atlas)

- [ ] `renderFigure({...})` single entry point; screen and export share it.
- [ ] `?export=1&figure=<id>` mode: hide UI, fixed size, white bg, one figure.
- [ ] `window.__figureReady` set on final draw; await it in Playwright.
- [ ] vector layers serialized via `downloadSVG`; raster layers via
      `renderHeatmapAtScale` + PNG at 3×.
- [ ] `export_figure.js` with pinned chromium, fixed viewport, deterministic
      wait (no `waitForTimeout`).
- [ ] SVG→PDF with embedded fonts; visually verify before converting.
- [ ] one figure id wired end-to-end (e.g. `lg27`) as the acceptance case.

---

_Handover spec. Implement in inversion-atlas; verify each figure by eye before
committing the converted PDF._
