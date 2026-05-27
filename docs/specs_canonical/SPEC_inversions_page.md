# SPEC — relatedness-atlas `inversions` page

**Status**: scaffold (extracted from legacy; not yet envelope-aware).

**Scaffolded in:**
- [`atlases/relatedness/pages/hub/inversions.html`](../atlases/relatedness/pages/hub/inversions.html) — extracted from legacy `Relatedness_atlas.html` lines 1466–1473
- [`atlases/relatedness/pages/hub/inversions.js`](../atlases/relatedness/pages/hub/inversions.js)

---

## 1. Goal

Paginated table of every inversion candidate from the inversion-atlas.
Columns:
- `inversion_id` (e.g. `INV_LG28_01`)
- `status` (PASS / WARN / FAIL)
- `chrom`
- `start_bp`, `end_bp`, `length_bp`
- `frequency` (inverted-allele frequency in the cohort)
- `n_hom_ref / n_het / n_hom_inv` (karyotype counts)
- `notes`

Filters:
- status (PASS / WARN / FAIL / any)
- chromosome (single-select dropdown)
- frequency threshold (slider: `>= 0.05`, `>= 0.10`, `>= 0.20`)

Click a row → emit `inversion_selected` event; sibling pages (network,
karyotypes, inspector) scope to that candidate.

Also exports an **"open in Mendelian"** action — pre-seeds the
`mendelian` page's selection state to test this specific inversion.

## 2. Data dependencies

Today: reads `DEMO.inversion_candidates`.

Envelope-aware target:
- `inversion_candidates.v1` from inversion-atlas (the primary product)
- Optionally `inversion_karyotypes.v1` for the n_* karyotype-count columns (compute from per-sample calls if not pre-aggregated)

Cross-atlas read via `resolveLatestLayer('inversion_candidates', ...)`.

## 3. Surface

```
#invFilterStatus       — <select> for status filter
#invFilterChrom        — <select> for chrom filter
#invFilterFreq         — <select> for freq threshold
#invTable              — paginated table; sticky header
#invPager              — page controls (prev / next / N of M)
#invDataSource         — envelope status badge (to be added)
```

## 4. Behaviour

`mount()`:
1. Resolve `inversion_candidates.v1` envelope (fail-soft).
2. Render the status badge.
3. Render the table from envelope.payload.candidates (or DEMO fallback).
4. Wire filters → re-render the visible rows; pager → re-render the page slice.
5. Wire row-click → `state.shared.activeCandidate = id` + emit event.
6. Wire "open in Mendelian" button → pre-seed `state.mend._pendingFromInversion`, route to `#/relatedness/mendelian`.

`unmount()`: detach listeners.

## 5. Renderers

The "open in Mendelian" path is the cross-page state mechanism:

```js
state.mend._pendingMode = 'all_dyads';
state.mend._pendingFromInversion = inversion_id;
window.location.hash = '#/relatedness/mendelian';
```

When `mendelian.js` mounts, it sees the pending state and applies it.

Also exports `renderInversionTablesInline(rootEl, n_rows)` which the
[`network` page](../specs_done/SPEC_network_page.md) reuses for its
inline preview (4-row paginated). Keep that signature stable when
migrating.

## 6. Promotion criteria

- [ ] `mount()` calls `resolveLatestLayer('inversion_candidates', { stage: 'normalized' })` and is fail-soft
- [ ] Table rows render from the envelope when present
- [ ] `renderInversionTablesInline` still works (network page is a consumer)
- [ ] Smoke test in `pages/hub/test_inversions_data_source.js`
- [ ] Move this SPEC to `specs_done/`

## 7. Open work

- **Per-inversion drill-down** — clicking a row could open a detail panel showing the full envelope record for that inversion. Today the click only emits an event for sibling pages.
- **Sort by any column** — currently sorted by chrom + start_bp. Other sorts (frequency desc, status priority, length) would be useful.
- **Bulk select** — checkboxes for multi-select feeding "open all in Mendelian" or "export selected as TSV." Not in scope yet.
- **Frequency colour-coding** — high-frequency rows could be amber/red to highlight common inversions visually.
