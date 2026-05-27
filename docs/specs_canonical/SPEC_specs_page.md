# SPEC — atlas-core SPECs page (`core/specs`)

**Status**: shipped 2026-05-21. Per-helper smoke test green; mount path
exercised in-browser at `#/core/specs` after `bash atlas-core/build/assemble.sh`.

**Implemented in:**
- [`atlases/core/pages/specs.html`](../atlases/core/pages/specs.html)
- [`atlases/core/pages/specs.js`](../atlases/core/pages/specs.js)
- [`atlases/core/pages/test_specs.js`](../atlases/core/pages/test_specs.js)
- Manifest entry: [`atlases/core/manifest.json`](../atlases/core/manifest.json) page #6
- Styles in [`atlases/core/css/core_pages.css`](../atlases/core/css/core_pages.css) §8
- Build-time indexer: [`build/index_specs.py`](../build/index_specs.py),
  invoked per atlas by [`build/assemble.sh`](../build/assemble.sh) steps 2b + 3

---

## 1. Goal

A single place to **see what's shipped and what's still pending** across
every atlas. Each atlas keeps SPECs in two top-level folders at its repo
root (`specs_done/` and `specs_todo/`), plus an optional `SPECS.md`
table-of-contents. This page surfaces all of them, grouped by atlas,
with a click-to-read markdown viewer.

Mounted at `#/core/specs` (6th page of the `core` atlas, after Inventory).

## 2. Surface

```
┌─────────────────────────────────────────────────────────────────┐
│ SPECs — done and to-do, per atlas                               │
├─────────────────────────────────────────────────────────────────┤
│ [core][diversity][genome][inversion][meiosis][population][rel.] │  ← one tab per atlas
│                                              [All][Done][To-do] │  ← filter mode (right)
├──────────────────────────┬──────────────────────────────────────┤
│ [filter SPEC…         ]  │  atlases/inversion/specs/done/...    │ ← det-h: path
│                          │                                      │
│  OVERVIEW                │  # SPEC — ...                        │
│   SPECS.md               │                                      │
│  [DONE] (28)             │  Rendered markdown body              │
│   SPEC — adapter ...     │                                      │
│   SPEC — band track ...  │                                      │
│   ...                    │                                      │
│  [TO-DO] (6)             │                                      │
│   SPEC — copy origin ... │                                      │
│   ...                    │                                      │
└──────────────────────────┴──────────────────────────────────────┘
```

Left: search filter + grouped tree (Overview / Done / To-do sections).
Right: rendered markdown body of the selected SPEC.

## 3. Data flow

Lazy-loaded on first tab activation, cached in module-level `CACHE`.

### 3.1 Atlas list

`atlases/_index.json` (written by `assemble.sh`) → list of atlas ids in
display order. Each id becomes one tab. First tab (`core`) is selected
by default.

### 3.2 Per-atlas index

`atlases/<aid>/specs/specs_index.json` per atlas:

```json
{
  "atlas_id":       "inversion",
  "has_aggregate":  true,
  "aggregate_path": "atlases/inversion/specs/SPECS.md",
  "done": [{ "file": "SPEC_x.md", "title": "SPEC — x", "path": "atlases/inversion/specs/done/SPEC_x.md" }],
  "todo": [...]
}
```

Each entry's `path` is workspace-relative — the SPECs page fetches it
directly via `fetch(entry.path)`.

Fail-soft: a missing `specs_index.json` for an atlas (e.g. an atlas that
hasn't been assembled yet, or one whose source repo never had
`specs_done/`) yields an inline empty-state with remediation:

> No `specs_index.json` for **<aid>**.
> Run `bash atlas-core/build/assemble.sh` to generate it.

### 3.3 SPEC body

Raw markdown fetched on click via `loadMarkdown(path)`, then rendered
client-side by `renderMarkdown()` (see §5). Cached per path.

## 4. Build-time indexer

[`build/index_specs.py`](../build/index_specs.py) — pure CPython, no deps.
Called from `assemble.sh` once per atlas:

```bash
python3 "$SCRIPT_DIR/index_specs.py" <aid> <src_repo_root> "$WORKSPACE/atlases/<aid>/specs"
```

Per atlas, it:

1. Copies `<src>/specs_done/*.md` → `<out>/done/` (status: done)
2. Copies `<src>/specs_todo/*.md` → `<out>/todo/` (status: todo)
3. Copies `<src>/SPECS.md` → `<out>/SPECS.md` (aggregate, optional)
4. **Also** picks up `<src>/docs/SPEC_*.md` as done-specs — atlas-core
   itself keeps SPECs flat under `docs/`, not in `specs_done/`. Name
   collisions with step 1 are skipped (specs_done/ wins).
5. Extracts each file's first `# heading` line as the row title (falls
   back to filename stem).
6. Writes `<out>/specs_index.json` with the entry list.

The indexer never aborts the assemble: missing source folders just yield
empty `done` / `todo` arrays in the index.

## 5. Markdown renderer

`renderMarkdown(md)` in [`specs.js`](../atlases/core/pages/specs.js) — a
deliberately small subset, enough for SPEC files:

| construct          | output                                      |
|--------------------|---------------------------------------------|
| `# … ###### h`     | `<h1>…<h6 class="spc-md-h spc-md-h{1..6}">`  |
| paragraph (blank-line separated) | `<p class="spc-md-p">…</p>`    |
| ` ``` lang ` fence | `<pre class="spc-md-pre"><code class="lang-…">…` |
| backtick code      | `<code class="spc-md-icode">…</code>`        |
| `- item` / `* item`| `<ul class="spc-md-ul"><li>…</li></ul>`      |
| `1. item`          | `<ol class="spc-md-ol"><li>…</li></ol>`      |
| `[txt](url)`       | `<a href="url" target="_blank" rel="noopener noreferrer">txt</a>` |
| `**x**` / `__x__`  | `<strong>x</strong>`                         |
| `*x*` / `_x_`      | `<em>x</em>`                                 |
| `> quoted`         | `<blockquote class="spc-md-bq">…`            |
| `---` / `***` / `___` (≥3) | `<hr class="spc-md-hr">`              |
| GFM table          | `<table class="spc-md-tbl">`                 |

HTML-in-source is always escaped — both in inline code and in
paragraph text. The escape step runs AFTER pulling inline-code spans
out (so their content survives raw, then is escaped by `esc(body)` inside
the placeholder).

**Not supported**: setext headings (`===` / `---` underlines), reference
links, image syntax `![alt](url)`, nested lists, footnotes, task lists.
SPEC files in this codebase don't use them — extend if a real use case
appears.

## 6. View modes

Right-side button group `[All | Done | To-do]` — toggles which sections
the left tree renders. `All` is the default. The filter input is
independent and combines with the mode (filter matches both file + title;
counts show `matched / total` when filter is active).

## 7. Public surface

Two exports for testing:

```js
export function esc(s)              // HTML-escape (mirrors inventory.esc)
export function renderMarkdown(md)  // → HTML string
```

[`test_specs.js`](../atlases/core/pages/test_specs.js) covers them with
**60+ assertions** including:
- All heading levels H1–H6 (and that H7 is NOT generated)
- CRLF line endings (matters for Windows-edited SPEC files)
- HTML-in-source escaping (inline + paragraph + code blocks)
- Inline code preserves HTML chars (escaped, not interpreted)
- Bold / italic combinations
- GFM table with inline code in a cell
- Bullet (`-` and `*`) and numbered list
- Mixed structures (heading directly followed by paragraph)
- Empty input → empty output
- Star-bullet vs HR disambiguation (`* a` is a bullet; `***` is an HR)

The mount path (DOM-coupled) is exercised in-browser only — same
convention as `test_inventory.js`.

## 8. Why client-side markdown rendering

Three alternatives considered, all rejected:

1. **Pre-render to HTML at build time** (Python markdown → HTML files).
   Adds a dependency (`markdown` / `mistletoe`) to the assemble pipeline
   AND doubles disk usage in the workspace. Atlas-workspace is meant to
   stay self-contained and shellable.
2. **Server-side endpoint** that reads + renders on request. Couples the
   SPECs page to a running `atlas_server.py` — undesirable, since the
   inventory page already failsoft when the server isn't running, and
   the SPECs page should follow the same pattern.
3. **Embed full markdown library client-side** (`marked.min.js` etc.).
   ~50 KB just for markdown when our SPECs use a small subset; also
   conflicts with the no-third-party-deps-in-the-shell convention.

The bespoke renderer is ~150 lines, has zero deps, and covers the SPEC
markdown vocabulary actually used in this codebase. New constructs can
be added when a real SPEC needs them.

## 9. Open work

- **No deep-linking** to a specific SPEC — the URL only carries
  `#/core/specs`, not the active tab or selected file. Adding
  `?aid=inversion&spec=SPEC_x.md` would let team mates share a direct
  link, but the current usage pattern (open the page, scan, click) hasn't
  required it.
- **No outdated-SPEC warnings** — if a SPEC under specs_done/ references
  a file that no longer exists, this page renders it as-is. The
  inversion-atlas audit-sweeps (3 rounds in May 2026) catch staleness
  by reading + amending the SPEC text; a future enhancement could
  highlight `[broken](../path/to/missing.js)` links on render.
- **No image rendering** — SPECs that paste image links currently render
  the link text, not the image. Most SPECs are diagram-free; if this
  changes, add `![alt](url)` → `<img src="url" alt="alt">` to `_inline()`.
