# SPEC — relatedness-atlas `karyotypes` page

**Status**: scaffold (extracted from legacy; not yet envelope-aware).

**Scaffolded in:**
- [`atlases/relatedness/pages/hub/karyotypes.html`](../atlases/relatedness/pages/hub/karyotypes.html) — extracted from legacy `Relatedness_atlas.html`
- [`atlases/relatedness/pages/hub/karyotypes.js`](../atlases/relatedness/pages/hub/karyotypes.js)

---

## 1. Goal

Full karyotype matrix view of the cohort: **rows = individuals**,
**columns = inversion candidates** (subset chosen by the cross-tab
chromosome filter). Cells colour-coded by genotype call:

- `0/0` — reference homozygote (light)
- `0/1` — heterozygote (mid)
- `1/1` — inverted homozygote (dark)
- `NA` — missing call (grey)

An **ancestry stripe** column on the left shows the K=8 admixture
decomposition for each row, so the user can scan ancestry composition
alongside karyotype patterns at a glance.

STD/INV alphabet labels appear only when an inversion's named-allele
convention is defined upstream (per the inversion-atlas's manifest).

## 2. Data dependencies

Today: reads `DEMO.karyotype_matrix`.

Envelope-aware target:
- `inversion_karyotypes.v1` from inversion-atlas (per-sample, per-candidate 0/1/2 call)
- `cohort_ancestry.qK_v1` from population-atlas (admixture Q matrix; layer name TBD)

Both reads cross atlas boundaries via the workspace-wide envelope index
(`resolveLatestLayer` works across atlases).

## 3. Surface

```
#karyoChromFilter    — chrom filter (cross-tab — same select as elsewhere)
#karyoMatrix         — the matrix table; sticky header row, sticky stripe column
#karyoLegend         — colour legend (0/0, 0/1, 1/1, NA, STD, INV)
#karyoDataSource     — envelope status badge (to be added in the migration)
```

## 4. Behaviour

`mount()`:
1. Restore active chrom from `state.shared.activeChrom`.
2. Filter inversion candidates by chrom.
3. For each (sample, candidate) cell, render colour-coded swatch.
4. Render ancestry stripe (8 colours per K=8 row).

`unmount()`: detach listeners; no module-level state survives.

State hooks:
- `state.shared.activeChrom` (read + subscribe; re-render on change)
- `state.shared.focalIndividual` (read; highlights the row)

## 5. Promotion criteria

- [ ] `mount()` calls `resolveLatestLayer('inversion_karyotypes', { stage: 'normalized' })` and is fail-soft
- [ ] At least the matrix cells render from the real envelope (fall back to DEMO when missing)
- [ ] Smoke test in `pages/hub/test_karyotypes_data_source.js` following the network/compatibility pattern
- [ ] Move this SPEC to `specs_done/`, add `Implemented in:` block

## 6. Open work

- **Sort ordering** — currently rows are sample-id alphabetical. Consider sort-by-family, sort-by-K8-cluster, sort-by-genotype-similarity options.
- **Filtering rows** — there's no row filter today (only column filter via chrom). Per-family filtering would be useful for the 226-sample view.
- **Per-cell tooltip** — show theta to focal individual, sex, family on hover. Requires lookups against the ngsrelate_pairs_v1 envelope.
- **Cross-atlas read** — when the ancestry stripe is wired against the real envelope, the population-atlas's K=8 admixture layer name needs to be confirmed.
