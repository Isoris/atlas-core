# SPEC — population-atlas `breeding` page (sample highlights table)

**Status**: round-1 verbatim JS lift shipped (2026-05-11) — ~330 LOC
from `legacy/Population_atlas.html` lines 2017-2612. Five auto-derivation
hooks + manual JSON/TSV upload + filter/sort/render + CSV export are
all functional today off `window.state.*` slots. Round-2 swaps each
`window.state.*` slot for a registry layer subscription.

**Implemented in:**

| file | role |
|---|---|
| [`pages/health/page_breeding.html`](../atlases/population/pages/health/page_breeding.html) | layout: source cards · toolbar · table slot · data-sources doc card |
| [`pages/health/page_breeding.js`](../atlases/population/pages/health/page_breeding.js) | verbatim-lifted derive + render + wire |

---

## 1. The biological question

> Which samples need a **breeding-committee look** this week? Surface
> rows where each sample has a notable feature across five source
> categories: diversity, relatedness, burden, inversions, markers.
> Traffic-light status per row.

The page is the **breeding-committee inbox** — auto-derived rows
flag samples that crossed a domain-specific threshold, plus a manual
upload path for curated rows.

## 2. Five auto-derivation hooks

| source | data slot | rule | status default |
|---|---|---|---|
| `Diversity` | `window.state.perSampleStats` | top 1% F_ROH; top 1% θπ | red / green |
| `Relatedness` | `window.state.familyClusters` | members of largest cluster (≥ 2) | yellow |
| `Burden` | `window.state.perSampleStats.deleterious_burden` | top 1% | red |
| `Inversions` | `window.state.inversionCarriers` | rare-frequency carriers (≤ 5%) | green |
| `Markers` | `window.state.markerControls` | positive/negative/het controls | green |

Plus a 6th derived hook: `_bpAutoHatcheryHealthRow` reads the hatchery-
health page's focal cohort verdict (via `window._fhhFocalCohort` /
`_fhhClassify` / `FHH_VERDICTS`) and emits one row per session.

## 3. Manual rows

| input | format |
|---|---|
| ▶ load highlights… | JSON `{ rows: [{ sample, highlight, value, source, status, notes, ref_url }] }` or TSV |
| User rows merge with auto-derived rows — same (sample, source) key wins manual |

## 4. Filtering + view modes

- Source filter: dropdown of present source categories
- Status filter: `all / green / yellow / red`
- View mode: `Simple` (5 columns) or `Detailed` (adds status label + origin)
- Filters persist in localStorage

## 5. The table

Columns (Simple):

| col | source |
|---|---|
| sample | row.sample |
| highlight | row.highlight (or row.highlight_html for the HC verdict row) |
| value | row.value |
| source | colored dot + category name |
| status | (Detailed only) green/yellow/red label |
| origin | (Detailed only) `auto:X` / `user` / `overlaid` |

Source cards above the table show per-category counts.

## 6. State + interaction

| state slot | purpose |
|---|---|
| `window.state._breedingPage.user_rows` | uploaded rows |
| `window.state._breedingPage.derived_rows` | most recent _bpDerivedRows() result (refreshed per render) |
| `window.state._breedingPage.view_mode` | `simple` / `detailed` |
| `window.state._breedingPage.filter_status` | `all` / `green` / `yellow` / `red` |
| `window.state._breedingPage.filter_source` | `all` / source name |
| `window._bpRender` | exposed so page_hatchery_health can fire a re-render after its ingest |

## 7. v2: swap `window.state.*` for registry layers

Each hook becomes a `Registry.subscribe(layer)` call:

| current slot | round-2 layer |
|---|---|
| `window.state.perSampleStats` | `per_sample_stats_v1` (same as samples page) |
| `window.state.familyClusters` | `family_clusters_v1` (new) |
| `window.state.inversionCarriers` | `inversion_carriers_v1` (cross-atlas from inversion catalogue) |
| `window.state.markerControls` | `marker_controls_v1` (cross-atlas) |
| `window.state._hatcheryHealth` | stays — page-local; not a registry concern |

Registry-cache means a single fetch satisfies samples + breeding +
hatchery-health for the per_sample_stats layer.

## 8. Failure modes

| # | condition | behaviour |
|---|---|---|
| 8.1 | No `window.state.*` slot populated | empty auto-derived rows; manual upload still works |
| 8.2 | Upload parse fails | console warn, no state change |
| 8.3 | Same (sample, source) in user + derived | user wins, origin marked `overlaid` |
| 8.4 | Hatchery-health page hasn't mounted | HC hook returns []; no warn |
| 8.5 | All rows filtered out | empty table hint; counts on cards still show pre-filter total |

## 9. CSV export

`_bpExportCsv` writes a single `breeding_highlights.csv` with columns
`sample, highlight, value, source, status, notes, ref_url, origin`.
Triggered via toolbar; cell-escapes per RFC 4180.

## 10. Cross-page handoff

- Read: per_sample_stats, family_clusters, inversion_carriers,
  marker_controls (round 2 via Registry; round 1 via `window.state`)
- Read: `window._fhhFocalCohort / _fhhClassify / FHH_VERDICTS` from
  hatchery-health page (live; re-renders on HC ingest)
- Write: localStorage only (filter persistence)
- No write-back to atlas state

## 11. Promotion criteria

| criterion | v1 | v2 |
|---|---|---|
| Five auto-derivation hooks | ✓ | ✓ (via Registry) |
| Manual JSON/TSV upload | ✓ | ✓ |
| Source + status filters | ✓ | ✓ |
| Simple/Detailed view toggle | ✓ | ✓ |
| Hatchery-health overlay row | ✓ | ✓ |
| CSV export | ✓ | ✓ |
| Registry-subscribed slots (replace `window.state.*`) | ✗ | required |
| Per-row sample drill-down (router navigate to samples page) | ✗ | required |
| Per-row provenance chip (which producer) | ✗ | nice-to-have |
| Cross-session rule customisation (edit thresholds) | ✗ | future |

## 12. Open questions

- **Top-1% vs other thresholds**: per-hook cutoffs are hard-coded to
  Q99 / Q01. v2 could expose a per-source threshold knob.
- **Family flag scope**: today's relatedness hook only flags the
  largest cluster. Should we flag all clusters ≥ N members?
- **Burden source**: today's hook reads `deleterious_burden` field on
  per_sample_stats. When SPEC_2026-05-12_functional_burden ships, swap
  to that layer's per-sample burden score.
