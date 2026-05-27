# SPEC — population-atlas `hatchery health` page (F_ROH × H plane)

**Status**: round-1 verbatim JS lift shipped (2026-05-11) — ~360 LOC
from `legacy/Population_atlas.html` lines 2614-3071. JSON/TSV upload +
inline SVG scatter + comparator table + CSV export all functional.
Round-2 wires the focal cohort's data from the registry instead of an
explicit upload.

**Implemented in:**

| file | role |
|---|---|
| [`pages/health/page_hatchery_health.html`](../atlases/population/pages/health/page_hatchery_health.html) | layout with summary cards, plot slot, table slot, toolbar |
| [`pages/health/page_hatchery_health.js`](../atlases/population/pages/health/page_hatchery_health.js) | verbatim-lifted compute + render + wire functions |

---

## 1. The biological question (novel framework)

> Combining autozygosity (F_ROH) with diversity-baseline-referenced
> heterozygosity (H/H_ref), where does each stock sit in the 2D
> health plane? **Diversity-contextualised F_ROH** — introduced in
> the manuscript Discussion as a new framework for stock-level
> verdict assignment.

Quadrant matrix:

| F_ROH | H/H_ref | verdict | class |
|---|---|---|---|
| low | high | **Healthy** — outbred on diversity-replete background | `good` |
| high | high | **Recent inbreeding** — outcrossable | `review_inbreeding` |
| low | low | **Diversity erosion** — bottlenecked but not inbred | `review_erosion` |
| high | low | **Caution** — historical erosion + recent inbreeding | `caution` |

Default thresholds: F_ROH ≥ 0.05, H/H_ref ≥ 0.5. The extractor
auto-derives the verdict when `verdict` is absent on the input row.

## 2. Data input

**v1 today** (verbatim lift):
- User uploads `hatchery_health.json` or `.tsv` via the toolbar
- Schema: `{ cohorts: [{ cohort, species, F_ROH, H_per_site, H_ref?, citation?, notes?, is_focal? }, …] }`
- Focal cohort flagged via `is_focal: true`; otherwise highest-F_ROH
  used as focal
- H_ref resolved per cohort: explicit field > species-peer max > cohort-max fallback

**v2 target**:
- Focal cohort auto-populated from THIS cohort's registry layers
  (`per_sample_stats_v1` → median F_ROH + median H)
- Peer cohorts still come from uploaded JSON (literature reference set)
- Schema: [`hatchery_health_v1`](../atlases/population/registries/schemas/schema_out/hatchery_health_v1.schema.json)

## 3. The SVG scatter plot

Inline SVG (720 × 420 plot rect), F_ROH on x-axis, H/H_ref on y-axis.

- Median-split quadrant lines (frohCut + ratioCut derived from cohort)
- Per-cohort dot colored by verdict (`fhh-good / fhh-review / fhh-caution`)
- Focal cohort renders larger (r=7) with distinctive `fhh-focal` border
- Cohort name label next to each dot
- Tooltip on hover: cohort name, F_ROH, H/H_ref ratio, verdict label

## 4. Verdict summary cards

Four colored cards across the top:

```
┌────────────┬────────────┬────────────┬────────────┬────────────┐
│ Healthy: N │ Recent     │ Diversity  │ Caution: N │ Cohorts    │
│            │ inbreeding │ erosion: N │            │ loaded: N  │
│            │ : N        │            │            │            │
└────────────┴────────────┴────────────┴────────────┴────────────┘
```

## 5. Comparator table

One row per cohort: cohort name + focal marker, species, F_ROH (3
decimals), H/H_ref ratio (with H_ref scientific notation if present),
verdict cell colored by class.

## 6. Toolbar

| button | action |
|---|---|
| ▶ load hatchery_health… | file-picker → `_fhhIngestText` (JSON or TSV) |
| ▶ export CSV | `_fhhExportCsv` — full table with verdict columns |
| ▶ reset | clear cohorts; revert badge to scaffold state |

## 7. Cross-page handoff

`window._fhhFocalCohort()` + `window._fhhClassify()` + `window.FHH_VERDICTS`
are exposed for the breeding page's auto-derivation hook
(`_bpAutoHatcheryHealthRow`) so a focal cohort verdict can appear as a
row in the breeding-page highlights table.

## 8. State + interaction

- `window.state._hatcheryHealth.cohorts` — loaded cohorts
- `window.state._hatcheryHealth.metadata` — upload metadata
- Drag-drop file load supported

## 9. Failure modes

| # | condition | behaviour |
|---|---|---|
| 9.1 | No cohorts loaded | "No cohorts loaded yet. Upload …" hint in plot slot |
| 9.2 | Cohort has F_ROH but no H | classifier returns `verdict=null`, point skipped |
| 9.3 | All cohorts have F_ROH=0 or H=0 | quadrant lines collapse to axes; render anyway |
| 9.4 | Parse fails on upload | console warn, no state change |
| 9.5 | Cohort has no H_ref + no species peer | falls back to cohort-max H_ref (best-effort) |

## 10. Promotion criteria

| criterion | v1 (today) | v2 |
|---|---|---|
| Upload-driven cohort load | ✓ | ✓ (keep as peer-cohort path) |
| Inline SVG scatter | ✓ | ✓ |
| Comparator table | ✓ | ✓ |
| CSV export | ✓ | ✓ |
| 4-quadrant verdict assignment | ✓ | ✓ |
| Focal auto-derived from THIS cohort's registry | ✗ | required |
| Persisted peer-cohort reference set (no re-upload per session) | ✗ | nice-to-have |
| Per-quadrant cohort drill-down (click verdict card → highlight rows) | ✗ | nice-to-have |

## 11. Open biological questions

- **Threshold tuning**: 0.05 / 0.5 are reasonable defaults but should
  surface as editable UI knobs (v2 nice-to-have).
- **Species-baseline H_ref**: today's species-peer max is a heuristic.
  v2 could ship a species-baseline table (manuscript Supp Table SX)
  with curated H_ref values per species.
- **More than 4 verdicts**: e.g. an intermediate "caution-mild" tier
  if thresholds are too binary. Future refinement.
