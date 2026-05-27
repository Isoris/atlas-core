# SPEC — atlas-core Inventory page (`core/inventory`)

**Status**: shipped 2026-05-20. 62-assertion smoke test green; wired into the
umbrella as suite "atlas-core inventory page (pure helpers)".

**Implemented in:**
- [`atlases/core/pages/inventory.html`](../atlases/core/pages/inventory.html)
- [`atlases/core/pages/inventory.js`](../atlases/core/pages/inventory.js)
- [`atlases/core/pages/test_inventory.js`](../atlases/core/pages/test_inventory.js)
- Manifest entry: [`atlases/core/manifest.json`](../atlases/core/manifest.json) page #5
- Styles in [`atlases/core/css/core_pages.css`](../atlases/core/css/core_pages.css) §7

---

## 1. Goal

A single place to inspect **everything loaded right now** across all
atlases — the live action-pipeline envelopes, each atlas's manifest
pages, each atlas's 5 registry files, plus the toolkit_registries TSV +
JSONL + JSON catalogues — without opening a file manager or a
text editor. Click any row, see its content.

Mounted at `#/core/inventory` (5th page of the `core` atlas, after
Conversation / Action / Registries / Catalogue).

## 2. Surface

```
┌─────────────────────────────────────────────────────────────────┐
│ Inventory — what's loaded                                       │
├─────────────────────────────────────────────────────────────────┤
│ [Envelopes][Atlas pages][Atlas registries][Toolkit TSVs]  [S][J]│  ← tab strip + Simple/JSON toggle
├──────────────────────────┬──────────────────────────────────────┤
│ [filter…              ]  │                                      │
│                          │  Detail panel (click a row →)        │
│  GROUP HEADING           │                                      │
│   row 1                  │   - Simple: dl grid                  │
│   row 2                  │   - JSON: <pre> raw                  │
│   row 3                  │                                      │
│  GROUP HEADING           │                                      │
│   ...                    │                                      │
└──────────────────────────┴──────────────────────────────────────┘
```

Left: search filter + grouped tree. Right: detail panel with current row's
content. Mode toggle re-renders the active detail in place.

## 3. Four sources

Lazy-loaded on first tab activation, cached in module-level `CACHE`.

### 3.1 Envelopes (`GET /api/layers`)

Live envelopes from the action pipeline. Each row: `layer_id` (primary),
`dataset_id + created_at` (secondary). Grouped by `layer_type`. Click → `GET
/api/layers/{layer_id}` for the full envelope; rendered as a key-value grid
(Simple) or raw JSON (JSON).

Fail-soft: when the server is offline or `/api/layers` returns non-2xx, the
tree shows: "Action-pipeline server not reachable — &lt;message&gt;. Start
`atlas_server.py --workspace-root &lt;workspace&gt;` to populate this tab."

### 3.2 Atlas pages

For each atlas in `atlases/_index.json` → fetch
`atlases/<id>/manifest.json` → list its `pages[]` array. Each row: page
label / id (primary), id + stage (secondary). Grouped by atlas.
Click → renders the page entry's manifest record.

### 3.3 Atlas registries

For each atlas, fetch the 5 JSON files declared in
`manifest.registries` (`layers`, `files`, `operations`, `pages`, `slots`).
Each row: registry name + entry count (counted via
`countRegistryEntries()`). Click → renders the full registry JSON.

Each missing registry surfaces as `<span class="inv-warn">missing — HTTP
404</span>` inline; the rest of the atlas's registries still display.

### 3.4 Toolkit (`toolkit_registries/relatedness/01_registry/`)

Three subsections rendered in a single tab:

- **Records (JSONL)** — 10 catalogues with one JSON record per line. Per-record `<details>` cards with `{primary_id} {label}` in the summary. Files: `atlases`, `products`, `questions`, `estimands`, `pages`, `panels`, `layer_registry`, `sample_attributes`, `hook_registry`, `analysis_registry`.
- **Files (JSON)** — single-object JSON files: `connection_map`.
- **Tables (TSV)** — 8 TSVs read by the Registries + Catalogue pages: `sample_sets`, `group_sets`, `interval_sets`, `site_sets`, `input_values`, `analysis_results`, `analysis_modes`, `module_registry`.

Malformed JSONL lines surface as red error cards (`{ _error, _line, _raw }`)
instead of aborting the whole file.

## 4. View modes

A two-button toggle in the right side of the tab strip — `[ Simple | JSON ]`.
Default = Simple. Persisted in `localStorage` under
`atlas.inventory.viewMode`.

### 4.1 Simple

[`renderSimpleObject(v)`](../atlases/core/pages/inventory.js) — recursive,
unbounded depth:
- Objects → `<dl class="inv-simple">` two-column grid (key in monospace
  muted, value in body font).
- Arrays of primitives → `<ul>` bullet list.
- Arrays of objects → indexed cards (`[0]`, `[1]`, …) each with its own grid.
- Nested objects → indented panel using `var(--panel-2)` (theme-aware).
- Primitives:
  - boolean `true / false` → "yes" / "no" (color-coded via
    `--ok`, `--muted`)
  - number → `var(--accent)` with `font-variant-numeric: tabular-nums`
  - empty string / null / undefined / `[]` / `{}` → italicised "(empty …)"

All keys and values HTML-escaped.

### 4.2 JSON

Raw `JSON.stringify(obj, null, 2)` in a `<pre class="inv-json">` block.
Useful for copy-paste and for debugging shape mismatches.

### 4.3 Switching

`renderDetail(fn, ...args)` stores `_lastDetail = { fn, args }` so the toggle
handler can re-invoke the renderer without re-clicking the row. The renderers
themselves branch on `VIEW_MODE` internally.

## 5. Public surface

Five named exports for testing (none used by the page mount path):

```js
export function parseTSV(text)         // → {header: string[], rows: object[]}
export function parseJSONL(text)       // → object[] (malformed → {_error, _line, _raw})
export function esc(s)                 // HTML-escape
export function countRegistryEntries(name, data)  // → "N entries" | "(empty)"
export function renderSimpleObject(v)  // → HTML string
```

[`test_inventory.js`](../atlases/core/pages/test_inventory.js) covers all five with **62 assertions** including:
- CRLF line endings (matters for Windows-edited registry files)
- Malformed-JSONL recovery
- HTML escaping on keys + values
- Array-of-primitives vs array-of-objects code paths
- Underscore + `$schema` keys excluded from entry counts

## 6. Why not just open the files

This page replaces several text-editor flows:

| previously                        | now                                        |
|-----------------------------------|--------------------------------------------|
| `code atlases/<id>/manifest.json` | `#/core/inventory` → Atlas pages tab        |
| `code toolkit_registries/.../atlases.jsonl` | → Toolkit TSVs tab → Records (JSONL) |
| `cat atlas-workspace/registry/layers.registry.json` | → Envelopes tab (with server running) |
| Comparing 5 per-atlas registries  | → Atlas registries tab (grouped by atlas)   |

The Simple-mode renderer means you don't have to mentally parse JSON syntax
on every inspection — the "this object has these fields with these values"
question is answered visually.

## 7. Open work

- **No envelope filter UI** — currently the filter input does a `JSON.stringify(row).toLowerCase().includes(filter)` whole-record substring match. Per-field filtering (`layer_type:fst_windows`) would be cleaner but isn't blocking.
- **No download / export** — clicking an envelope shows the JSON in-page but doesn't expose a "Download as JSON" button. Copy-from-pre works in JSON mode.
- **No keyboard navigation** — rows are `tabindex="0"` so they receive focus, but `↑/↓` to next-row doesn't move keyboard focus today. Click + Enter / Space activates correctly.
