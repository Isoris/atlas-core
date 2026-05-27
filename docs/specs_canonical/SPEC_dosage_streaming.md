# SPEC — Streaming dosage heatmap viewer + extensions

**Companion to**: `AUDIT_dosage_heatmap.md`. Read the audit first —
this spec assumes you know what already exists.

**Status**: design pass. No code shipped this turn. Per Quentin's
explicit ask: "Do you agree to draft all of the all ideas for how
to overpower and annotate the dosage heatmap ?? Its audit + specs +
draft ideas for extended usage."

This document covers:

1. **Architecture choice**: atlas-internal streaming vs standalone
   viewer. Honest tradeoffs.
2. **Streaming protocol**: server contract, query API, response
   shape, downsampling modes.
3. **Storage backend**: how to lay the data on disk so queries
   stay fast.
4. **Atlas integration plan**: what to wire up, in what order.
5. **Annotation layers**: row recoloring schemes, gene-conversion
   tracks, crossover regions, family stratification, statistical
   overlays.
6. **Extensions and exploratory ideas** (Quentin's "discover stuff"
   list).
7. **Scope estimate** per piece (cheap / medium / heavy).
8. **Multi-turn carving** for what to ship and in what order.

---

## 1. Architecture choice

Two viable paths. They are NOT mutually exclusive — the standalone
viewer pasted-spec design is fine on its own merits — but they
serve different workflows.

### Option 1 — Atlas-internal streaming heatmap

The atlas adds a small local server (or uses a static-served
chunked store) and the live cursor strip + new region-query UI
talk to it directly. Existing renderer/cache/cursor strip stay
exactly as they are; what changes is the data source and the
query protocol.

**Pros**:
- Zero context switch — you see the heatmap inside the same atlas
  where you do all your other inversion work.
- The heatmap reuses the atlas's coordinate system, candidate
  registry, K-means labels, candidate selection, sample tracking,
  active-samples mask (AS1 just shipped), and inheritance groups.
- The cursor strip already redraws on `state.cur` change — you
  scrub through windows and the heatmap follows.
- One install, one URL, one workflow.

**Cons**:
- Server has to live somewhere. Either you run a local Python/Node
  process alongside the atlas HTML, or you precompute static
  chunks and serve them via `python -m http.server`. The pasted
  file's FastAPI design is fine; the question is whether you
  bundle that with the atlas or keep it separate.
- Atlas codebase grows. Already at 56k lines; adding query-mode UI,
  downsampling fallbacks, and annotation tracks adds another
  ~2-3k lines. Not blocking but not free.

### Option 2 — Standalone dosage viewer (per the pasted spec)

A separate `dosage_viewer/` directory with its own FastAPI server,
own HTML/JS, own downsampling logic. Independent of the atlas.

**Pros**:
- Clean separation of concerns. The viewer is generic — works for
  any cohort with `dosage.tsv` + `sites.tsv`, doesn't depend on the
  atlas's per-window precomputed PCA.
- Lower coupling to the atlas's idiosyncrasies.
- Easier to share with collaborators who don't run the atlas.
- The pasted spec is already complete and well-designed. You could
  build it as-is in a day or two.

**Cons**:
- Two viewers to maintain.
- Loses everything the atlas knows about candidates, K-means
  groupings, inheritance groups, families, etc — you'd have to
  reimplement that joining or import it via metadata files.
- Workflow friction: switching between the atlas and the viewer
  loses cursor position / context.

### Recommendation

**Build BOTH, in two phases.**

- **Phase 1 (recommended start)**: Implement the standalone viewer
  per the pasted spec. It's cheaper to build because the design is
  already complete. It gives you immediate value: you can look at
  raw dosage on any region of any chromosome, regardless of
  whether the atlas has a candidate there. It also forces the
  decisions about storage format, downsampling modes, and the
  region-query API in a clean environment without the atlas's
  legacy constraints.

- **Phase 2 (after Phase 1 is working)**: Make the atlas TALK TO
  the standalone viewer's server. The atlas's existing
  `_findCoveringChunk` / `_fetchAndCacheChunk` already use
  `fetch(url)`. Repointing those at the standalone server's
  `/api/region` endpoint is a small protocol-adapter change.
  The atlas keeps its renderer + cursor strip + cache + hover; it
  just doesn't need to know how the data got served. The atlas
  also gets the region-query UI as new toolbar entries that map
  to `/api/region` calls.

This way the standalone viewer carries the heavy lifting (storage,
indexing, downsampling), and the atlas carries the contextual
analysis (candidates, K-means, inheritance, active samples).
Neither has to do the other's job.

The rest of this spec assumes this split.

---

## 2. Streaming protocol

The contract between the standalone-viewer server and any client
(the standalone HTML, the atlas, future tools).

### 2.1 Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/manifest` | List chromosomes, sample names, total sites, server version. |
| GET | `/api/region` | Slice by genomic coordinates (the workhorse). |
| GET | `/api/candidate/<id>` | Convenience: slice a registered candidate region. |
| GET | `/api/breakpoint/<id>/<left|right>` | Convenience: slice ±window around a breakpoint. |
| GET | `/api/tile` | Genome- or chromosome-wide tiled overview. |
| GET | `/api/sites` | Site-only metadata for a region (no dosage). For overlays. |
| GET | `/api/samples` | Sample-only metadata (id, family, ancestry, F_ROH...). |

### 2.2 `/api/region` query parameters

```
chrom         required   string   e.g. "LG28"
start         required   int      bp
end           required   int      bp
max_sites     optional   int      default 1000, hard cap 5000
mode          optional   enum     raw | even | random | variance | hybrid | aggregate
                                  default: hybrid
seed          optional   int      for `random` and `hybrid` reproducibility
sample_order  optional   string   "input" | "k3:<cand_id>" | "family" | "ancestry" |
                                  "froh" | "het" | "hclust:<region>"
                                  default: "input"
sample_subset optional   string   comma-separated sample IDs OR "active:<atlas_session_id>"
                                  default: all
include       optional   string   comma-separated extras: "polarity,quality,gc_events"
                                  default: ""
binning       optional   string   only for mode=aggregate: "1kb" | "10kb" | "screen:N"
                                  default: "screen:200"
```

### 2.3 Response shape

```json
{
  "request": {
    "chrom": "LG28",
    "start": 10000000, "end": 12000000,
    "mode": "hybrid", "max_sites": 1000, "seed": null,
    "sample_order": "k3:INV_LG28_001",
    "sample_subset": null,
    "include": ["polarity"]
  },
  "stats": {
    "n_sites_total":   8421,
    "n_sites_returned": 1000,
    "n_samples_total":   226,
    "n_samples_returned": 226,
    "downsampled":      true,
    "missingness_dropped": 124,
    "elapsed_ms":       42
  },
  "warnings": [
    "hybrid mode: 30% top-variance markers included; not neutral for breakpoint detection"
  ],
  "samples": ["CGA001", "CGA002", ...],
  "site_ids":  ["LG28_001234", ...],
  "positions": [10001234, 10003781, ...],
  "matrix":    [[0,2,1,...], [...], ...],
  "include": {
    "polarity": [false, true, true, false, ...]
  }
}
```

Matrix layout: rows = sites, columns = samples (matches the
existing chunk_get(chunk, marker_idx, sample_idx) accessor).

NA values encoded as `-1` (matches existing convention).

Returned sites ALWAYS sorted by genomic position before serializing.

### 2.4 Downsampling modes — semantics

These are the spec's six modes, made precise:

**raw** — return ALL sites in `[start, end]`. If the count exceeds
`max_sites`, return HTTP 400 with `{ error: "raw mode requires
n_sites_in_region <= max_sites; got %d / %d", suggestion: "use
mode=hybrid" }`. Never silently downsamples — that's the whole
point of `raw`. `n_sites_returned == n_sites_total`.

**even** — pick `max_sites` sites with stride
`floor(n_sites_total / max_sites)` along the genomic-position-sorted
list. Preserves positional uniformity. Best for detecting local
tracts (gene-conversion patches), local ancestry switches,
breakpoint transitions. `n_sites_returned ~= max_sites`.

**random** — seeded reservoir-sample of `max_sites` sites from the
in-region set. Sort selected sites by position before returning.
Useful as an unbiased visual-only sample. Same seed → same set.

**variance** — rank in-region sites by per-site dosage variance
across the active sample subset, take top `max_sites`. Sort by
position. Strong band visualization. Biased toward informative-but-
confounded markers (family LD, repeats, paralogy, inversion-linked
markers) — return-with-warning.

**hybrid** — `0.7 * max_sites` even-spaced + `0.3 * max_sites`
top-variance, deduplicated, sorted by position. Default mode.
Best for exploration; warning notes it's not neutral.

**aggregate** — bin sites into `binning`-defined bins (`1kb`,
`10kb`, `screen:N` where N becomes the number of bins). Per bin
per sample, compute mean dosage of in-bin sites (NA-skipping). Bin
center serves as the "position." Used for chromosome-scale or
genome-scale overview. NOT for breakpoint detection — the
aggregation washes out per-site polarity.

Picking modes by purpose:
- Inversion bands → `variance` or `hybrid`
- Gene-conversion / local ancestry → `even` or `raw` if small
- Breakpoint detection → `even` or `raw`
- Chromosome scan → `aggregate`
- Quick check → `random`

### 2.5 `/api/tile` — chromosome-overview mode

```
GET /api/tile?chrom=LG28&zoom=2&width=500&height=226
```

Returns a `mode=aggregate` heatmap covering the entire chromosome
binned to fit `width` columns. `zoom=0` is the whole chromosome,
each higher level halves the bp range and doubles the columns at a
fixed display width (Google-Maps-style).

`tile=N` parameter (optional) specifies which segment of the
chromosome at this zoom level. Implementation: precompute zoom 0–4
at server startup or on first request; cache.

### 2.6 `/api/candidate/<id>`

Reads `candidate_regions.tsv` (or `state.candidates` exported from
the atlas) and resolves `<id>` to a `(chrom, start, end)` triple,
then proxies to `/api/region` with that triple plus any other
query params.

```
GET /api/candidate/INV_LG28_001?max_sites=1500&mode=variance
```

### 2.7 `/api/breakpoint/<id>/<side>`

Same as `/api/candidate` but uses `left_breakpoint ± window` or
`right_breakpoint ± window`. Default window 500 kb. Default mode
`even`.

```
GET /api/breakpoint/INV_LG28_001/left?window=500000&max_sites=1000
```

### 2.8 `/api/sites`

Returns ONLY the site metadata for a region — site IDs, positions,
optional per-site fields like `n_alt`, `missingness`,
`diagnostic_score`, `polarity`. No dosage values. Used by overlays
that need to know WHERE markers are without loading the heatmap.

```
GET /api/sites?chrom=LG28&start=10000000&end=12000000
```

### 2.9 `/api/samples`

Returns the sample-side metadata: ID, family_id, ancestry,
F_ROH summary, het, K8 ancestry vector. Used for the row-color
controls. Loaded once per session; cached client-side.

```
GET /api/samples
```

---

## 3. Storage backend

### 3.1 Choice rubric

The pasted spec lists Parquet, Zarr, HDF5, Arrow/Feather, NumPy.
Picking among them depends on:

- **Per-region slice latency**: how fast can the server answer a
  "give me sites in [start, end]" query?
- **Setup complexity**: how much code in the prep script?
- **Cohort-evolution friction**: when samples get added, how hard
  is it to extend?

Recommendation:

**Zarr or HDF5**. Both support efficient chunked reads of a
2D matrix and have mature Python bindings. Zarr is a bit more
modern (cloud-friendly, simpler chunks-as-files layout), HDF5 is
more portable to non-Python tools. Either is fine. Avoid Parquet
for this — it's column-oriented and our query is "give me a
contiguous range of rows (sites) for all samples (columns)" which
is exactly the row-wise slicing Parquet is bad at.

NumPy `.npy` per chromosome is the simplest possible — works
fine for a 226-sample cohort and a few hundred thousand sites.
Random-access slicing via `np.memmap` is fast enough. Use this
if the prep script needs to be dead simple.

### 3.2 On-disk layout (Zarr/HDF5 sketch)

```
output/dosage_store/
  manifest.json
  LG01/
    dosage.zarr/        # 2D array shape (n_sites, n_samples), int8 (-1..2)
    sites.parquet       # site_id, pos_bp, missingness, diagnostic_score, polarity
    sites.posbp_index.npy  # int64[n_sites] — position-sorted lookup index
  LG02/
    ...
  ...
  LG28/
    dosage.zarr/
    sites.parquet
    sites.posbp_index.npy
  samples.parquet       # cohort-wide: sample_id, family_id, ancestry, F_ROH, ...
```

`manifest.json` records: server version, schema version, chrom
list, n_sites per chrom, n_samples, default modes, etc.

### 3.3 Site-position index

Per-chromosome `posbp_index.npy` is sorted-bp positions, used for
binary search to resolve `[start, end]` → `[site_idx_lo,
site_idx_hi]`. This is the hot path on every region query.

### 3.4 Aggregate-mode precomputation

For `/api/tile`, precompute aggregated chunks at standard zoom
levels at server startup OR lazily on first request. Cache to
disk (`output/dosage_store/LG28/agg_zoom2.zarr`). This is what
makes whole-chromosome scrolling smooth.

---

## 4. Atlas integration plan

The atlas does NOT need a Python server of its own. Phase 2 is
a **protocol adapter**: replace the static-URL fetcher with a
server-aware fetcher that does query-time slicing.

### 4.1 New atlas state slot

```
state.dosageServer = {
  url: 'http://localhost:7000',     // configurable, persisted to localStorage
  mode: 'hybrid',                    // current downsampling mode
  max_sites: 500,                    // cap, replaces DOSAGE_HEATMAP_DEFAULTS.HARD_CAP
  sample_order_mode: 'k3',           // 'input' | 'k3' | 'family' | ...
  reachable: null,                   // null=unknown, true=ok, false=down
  manifest: null                     // cached /api/manifest result
}
```

Persisted to localStorage so reloading restores the user's
preferred server URL + mode.

### 4.2 Replace the chunk fetcher

`_fetchAndCacheChunk(chunkRef)` (line 13892) currently does
`fetch(chunkRef.url)`. Replace with a server-aware version that
constructs the URL from `state.dosageServer.url` + region +
current downsampling mode + sample-order mode. The cache key
should include the mode and max_sites parameters so different
queries don't clobber each other.

Cache key changes from:
```
${chrom}:${start_bp}:${end_bp}
```
to:
```
${chrom}:${start_bp}:${end_bp}:${mode}:${max_sites}:${sample_order}
```

### 4.3 New region-query UI

A new toolbar entry next to the cursor strip toggle:

```
[ ▦ live dosage ]  [ go to region: chrom [LG28 ▾] start [_______] end [_______] mode [hybrid ▾] ]
```

`mode` dropdown options: raw / even / random / variance / hybrid /
aggregate, with tooltips matching the spec.

Below that, a row of preset buttons:
```
[ ← scrub ]  [ this candidate ]  [ left bp ±500kb ]  [ right bp ±500kb ]  [ chromosome view ]
```

`scrub` = current cursor mode (default).
`this candidate` = state.candidate's [start, end] via /api/candidate.
`left bp ±500kb` / `right bp ±500kb` = via /api/breakpoint.
`chromosome view` = /api/tile, current chrom, zoom 0, replace
the strip with the wide aggregate view.

### 4.4 Sample-order picker

A dropdown in the cursor strip toolbar:
```
[ rows: input order ▾ ]
```
Options:
- input order — cohort default
- K=3 (this candidate) — current behavior with state.candidate active
- K=6 (this candidate)
- by family
- by ancestry (K8 dominant)
- by F_ROH (low → high)
- by het (low → high)
- hclust on dosage (this region) — server computes; expensive

Server computes order for the heavy ones (hclust, K-means re-run
on subset) and returns it as `samples: [...]` array in the response.

### 4.5 Active-samples integration (AS2 dependency)

When `state.activeSampleSet` (from AS1) is a subset, the atlas
threads `sample_subset` into the server query. The server filters
to the active set BEFORE downsampling, so variance / aggregate
modes reflect the active subset.

This is a clean handoff to AS2 — once AS2 reads `activeSampleSet`,
the dosage heatmap respects it automatically.

### 4.6 Server-down fallback

If `state.dosageServer.reachable === false`, the cursor strip
shows a clear message: "dosage server unreachable at <url>. Start
the server with `python 02_run_server.py`. The heatmap is
disabled." No silent failure.

---

## 5. Annotation layers (Quentin's "overpower the heatmap" list)

These are extensions to the renderer's per-sample-attribute
providers. The renderer ALREADY supports five left tracks and one
top track. Adding more tracks is mechanical — the work is mostly
deciding what's useful and wiring data sources.

### 5.1 Row recoloring modes (replaces or augments K3 left track)

Pick one at a time via a `rows colored by` dropdown:

| Mode | Color from | Source |
|------|------------|--------|
| K=3 (current) | candidate K-means label | already wired |
| K=6 | candidate K=6 sub-band | already wired |
| inheritance group | turns 115–122 inheritance matrix | NEW provider |
| family | family_id | already wired indirectly via family palette |
| K=8 ancestry (dominant) | NGSadmix Q max-component | NEW provider |
| F_ROH bin | low / mid / high | NEW provider |
| Het bin | low / mid / high | NEW provider |
| active vs inactive | AS1 active mask | NEW provider |
| custom manual group | manual groups | already wired in atlas |

Implementation cost: each new mode is a `function(si) → label` +
a `function(label) → '#hex'` and a dropdown entry. ~30 lines per
mode plus the dropdown. Cheap.

### 5.2 Top tracks (per-marker, above the matrix)

Stack vertically above the dosage matrix. Each ~10 px tall.

| Track | Color encoding | Source |
|-------|----------------|--------|
| polarity (current) | blue/red | already wired |
| diagnostic score | viridis | per-marker if present in chunk |
| variance | viridis | computed at render time |
| FST between K3 groups | viridis | computed at render time, expensive |
| recombination rate | viridis | external map; future |
| repeat density | grey | external annotation; future |
| gene density | grey | external GFF; future |

User-toggleable subset of these stacks.

### 5.3 Cell overlays — gene-conversion event tracks

This is the "is gene conversion enriched in some families" piece.

Concept: per-sample-per-window, the atlas's existing
`recombinant_class` flag (none / gene_conversion / double_crossover
/ mixed) is computed against an L2 envelope. To overlay this on
the heatmap, paint a small orange marker on each cell where the
sample at that position is flagged as gene_conversion. Crossover
regions get a red marker. None: nothing painted.

The renderer already uses cell-level fills. Adding a sparse
overlay layer (after the matrix paints) that fills 2-3 px markers
on the flagged cells is trivial. The data side: we need a
per-sample-per-window event track. The atlas has the per-candidate
classification but not per-window. Either:

- (a) extend the precomp to emit per-window recombinant_class, or
- (b) compute it lazily client-side from existing per-window K3
  labels + sample residuals when the user toggles the overlay.

Option (b) is feasible and runs in the atlas without R-side work.
Cost: ~150 lines for the overlay renderer + a `gene-conversion
events` toggle button.

### 5.4 Crossover region annotations

Different from gene-conversion events: crossover regions are the
intervals where a sample's haplotype switches band assignment.
Visualized as horizontal bars across the row spanning the switch
interval.

Data source: per-sample band-assignment changes between adjacent
L2 envelopes (or windows). Computable from existing K3 labels.

Visualization: thin horizontal bar at row level, color-coded by
direction (HOMO_1 → HET = light blue; HET → HOMO_2 = pink; etc).

Cost: ~200 lines + a toggle.

### 5.5 Sample-side strips on the right

Mirror the left tracks on the right with PER-SAMPLE summary
statistics SCOPED to the visible region:

- Region-mean dosage
- Region-variance dosage
- Within-region het rate
- Within-region recombinant_class fraction
- Within-region "active" status (AS1)

These are "is this sample interesting in this region" at-a-glance
indicators.

Cost: ~100 lines per strip + dropdown to pick which 1-2 to show.

### 5.6 Per-sample row click → detail panel

Clicking a sample row in the heatmap opens a detail panel
(sibling to the existing tooltip):

- Sample ID + family + ancestry + F_ROH
- Per-window K3/K6 labels (small inline trace)
- Gene-conversion events at this sample across all candidates
- Cross-candidate inheritance group memberships (turns 115-122)
- Active-sample status + reason (AS1)

Reuses existing data; no new data layer. Cost: ~250 lines.

---

## 6. Extensions and exploratory ideas

The "discover stuff" Quentin mentioned. Some are cheap, some are
research-grade.

### 6.1 Family-stratified gene-conversion enrichment

Per-candidate, per-family, count `gene_conversion` calls.
Test for enrichment via Fisher's exact test on the
`(family, has_gc_event)` 2×2 table, with FDR across families.

UI: a small "GC enrichment" panel under the heatmap when a
candidate is active. Sortable table: family_id, n_carriers,
n_gc_events, p, q, dominant_direction.

This is a real biological question. Cheap to compute (cohort-wide
counts + ~10 Fisher tests). Useful even if it returns "no
enrichment" — it characterizes the recombination landscape.

Cost: ~300 lines + a toggle. Medium.

### 6.2 GC-tract length distribution

Histogram of gene-conversion tract lengths across candidates and
across families. Compares to neutral expectation.

UI: a separate histogram panel. Useful for scaling the
"how big are GC tracts in this cohort" question.

Cost: ~150 lines. Cheap.

### 6.3 Recombination-rate inference from breakpoint distribution

For each candidate, plot the bp positions of inferred crossovers
within the inverted region across heterozygotes. Recombination
inside an inversion should be suppressed; if you see a hotspot,
that's a real signal (e.g., gene conversion within the inversion,
or a misclassified inversion).

Cost: ~250 lines. Medium.

### 6.4 Cross-candidate haplotype tracking

Pick a sample, follow its band assignment across all candidates on
this chromosome. Plot as a horizontal bar chart with one row per
candidate, colored by K3 band. Reveals haplotype block structure.

This is partly addressed by the inheritance matrix (turns 115-122)
but the per-sample horizontal view is a different visual.

Cost: ~200 lines. Cheap.

### 6.5 Differential heatmap: sample A vs sample B

Two samples picked, render `dosage_A - dosage_B` as a diverging
heatmap. Highlights where the two haplotypes differ. Useful for
"are these two trio members consistent with Mendelian inheritance"
or "is this F1 hybrid carrying the expected mix."

Cost: ~150 lines. Cheap.

### 6.6 Cohort-mean vs sample residual

For each cell, paint `dosage_sample - cohort_mean_dosage_at_this_marker`.
Two-color scale. Per-sample anomalies pop out.

Cost: ~100 lines. Cheap.

### 6.7 PCA biplot overlay

For a region, project samples by PCA on the in-region dosage
matrix, render an inset scatter alongside the heatmap. Markers
visualized as loading vectors. Real-time recomputation possible
since the region is small.

Cost: ~400 lines. Medium-heavy.

### 6.8 Save heatmap state as a "candidate snapshot"

Capture (region, downsampling mode, sample order, annotation
toggles) as a named snapshot the user can return to. Useful for
"this is my evidence figure for INV_LG28_001 in the manuscript."

Cost: ~200 lines. Cheap.

---

## 7. Scope estimate per piece

Cheap = 1 turn. Medium = 2-3 turns. Heavy = 4+ turns or
multi-component.

| Piece | Scope |
|-------|-------|
| Standalone viewer (whole pasted spec) | Heavy: 4-6 turns |
| Atlas adapter to standalone viewer | Medium: 2 turns |
| Region-query UI in atlas | Medium: 2 turns |
| Sample-order picker | Cheap: 1 turn |
| Each new row recoloring mode (§5.1) | Cheap: <1 turn each |
| Each new top track (§5.2) | Cheap: <1 turn each |
| Gene-conversion overlay (§5.3) | Medium: 1-2 turns |
| Crossover region annotation (§5.4) | Medium: 1-2 turns |
| Right-side per-sample strips (§5.5) | Cheap: 1 turn |
| Click-row detail panel (§5.6) | Medium: 2 turns |
| Family-stratified GC enrichment (§6.1) | Medium: 1-2 turns |
| GC tract length histograms (§6.2) | Cheap: 1 turn |
| Recombination-rate inference (§6.3) | Medium: 2 turns |
| Cross-candidate haplotype tracking (§6.4) | Cheap: 1 turn |
| Differential heatmap A-vs-B (§6.5) | Cheap: 1 turn |
| Residual heatmap (§6.6) | Cheap: 1 turn |
| PCA biplot overlay (§6.7) | Medium-heavy: 2-3 turns |
| Snapshot save (§6.8) | Cheap: 1 turn |

---

## 8. Multi-turn carving — what to ship and in what order

This is the recommended execution order. Each turn is roughly
1-day-of-work scoped.

### Phase 1: Standalone viewer (per pasted spec)

- **DV1**: Repository scaffold. `dosage_viewer/` directory,
  `01_prepare_dosage_store.py` reading dosage.tsv + sites.tsv,
  writing to Zarr or NumPy chunks. Manifest. Sample names.
  Tests against a synthetic 50-sample × 1000-site fixture.
- **DV2**: FastAPI server with `/api/manifest`, `/api/region`
  (raw + variance modes only). Tests for query parsing,
  position-bp index correctness.
- **DV3**: Add `even`, `random`, `hybrid`, `aggregate` modes.
  Tests for each mode's invariants.
- **DV4**: Add `/api/candidate`, `/api/breakpoint`, `/api/tile`,
  `/api/sites`, `/api/samples`. Candidate-regions.tsv loader.
- **DV5**: Frontend. Static `index.html` + `app.js` + `style.css`.
  Region-query inputs, mode dropdown, candidate picker, Canvas
  heatmap renderer (lighter version of the atlas's). Tests in
  JSDOM.
- **DV6**: Performance + polish. LRU cache, request debouncing,
  loading-spinner, error states.

That's the whole pasted spec, 6 turns of work. Each is testable
in isolation.

### Phase 2: Atlas adaptation

- **AT1**: Replace `_fetchAndCacheChunk` with a server-aware
  fetcher. Cache key includes mode + max_sites + sample_order.
  Settings UI in atlas: server URL + reachability check.
  Existing cursor strip continues to work, now powered by the
  server.
- **AT2**: New region-query toolbar UI + preset buttons (this
  candidate / left bp / right bp / chromosome view).
- **AT3**: Sample-order picker dropdown.

### Phase 3: Annotation extensions

Start with cheap and high-value:

- **AN1**: Inheritance-group row recoloring. Glues turn 115-122
  inheritance work onto the heatmap row colors.
- **AN2**: Family + ancestry + F_ROH row recoloring modes.
- **AN3**: Gene-conversion event overlay (lazy client-side
  computation from existing K3 labels).
- **AN4**: Right-side per-sample summary strips.
- **AN5**: Click-row detail panel.

Each is a single turn of self-contained work.

### Phase 4: Statistical extensions

- **ST1**: Cross-candidate haplotype tracking (cheap visualization).
- **ST2**: Family-stratified GC enrichment (Fisher tests +
  table panel).
- **ST3**: GC tract length histograms.
- **ST4**: Differential & residual heatmaps.
- **ST5**: Snapshot save.

### Phase 5: Heavy extensions

- **HV1**: hclust sample ordering (server computes; client
  receives).
- **HV2**: Recombination-rate inference from heterozygote
  breakpoints.
- **HV3**: PCA biplot overlay.

### Recommended next step

If Quentin wants to see something working soonest: **DV1 + DV2**
gives a usable standalone viewer in 2 turns. After that, AT1
(atlas adapter) makes the cursor strip live for the first time,
which unblocks all the annotation extensions. Total minimum-
viable path: 3 turns (DV1, DV2, AT1).

If the priority is "I want to color heatmap rows by inheritance
group RIGHT NOW even without streaming data", then AN1 alone is a
1-turn job — but it would be using fake/placeholder dosage data,
which seems pointless.

The honest recommendation is: build the data pipeline first
(DV1-DV2), then plug the atlas in (AT1), then start adding the
extensions you find most useful as you actually use it.

---

## 9. What's NOT in this spec

- A specific FastAPI implementation (skeleton — will design
  during DV1-DV2).
- A specific Zarr vs HDF5 vs NumPy decision (stub — will
  benchmark during DV1).
- Any code. This is a design pass.
- Any commitment to ship. Quentin reviews; we pick a starting
  turn together.

---

## 10. Risks

1. **Storage format choice locks in for years.** Zarr and HDF5
   are both mature; NumPy memmap is dead simple but doesn't
   compress. Pick after benchmarking on the real cohort.
2. **CORS / local-server friction.** The standalone server must
   send permissive CORS headers so the atlas (loaded from
   `file://` or another origin) can fetch from it. Easy fix in
   FastAPI; mention now so it doesn't surprise.
3. **Sample IDs drift.** Cohort sample IDs in the dosage TSV
   must match the atlas's `state.data.samples[i].cga`.
   Manifest endpoint should expose the sample list; atlas
   verifies on connect.
4. **Aggregate mode washes out direction.** `aggregate` returns
   mean dosage per bin per sample; you lose the per-marker
   polarity that makes the inversion bands legible. Document
   prominently.
5. **Variance mode confounds.** Already noted in the spec —
   variance enriches for family-LD markers, repeats, paralogy.
   The warning string in every variance/hybrid response makes
   this loud at the surface.
6. **Live-server dependency.** The atlas was self-contained
   (`open Inversion_atlas.html` and go). Adding a server
   dependency for dosage views means new install steps. Make
   sure the atlas degrades cleanly when the server is unreachable
   — every existing feature (PCA, lines panel, contingency, etc)
   continues to work; only the dosage strip shows the offline
   message.

---

## What this turn shipped

- This document. No code.
- `AUDIT_dosage_heatmap.md`. No code.

The recommendation is to come back to DV1 once Quentin has
reviewed both docs and decided: (a) build standalone first?
(b) atlas-internal first? (c) stop here for now and revisit after
AS2 / AS3 land?

This is a 5-15 turn body of work depending on which annotations
land. Picking a starting turn together, before any code is
written, is the right next step.
