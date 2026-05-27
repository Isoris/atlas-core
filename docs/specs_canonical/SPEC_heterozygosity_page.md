# SPEC — population-atlas `heterozygosity ↗` page (cohort-summary lens)

**Status**: round-1 scaffold shipped (2026-05-11). This is one of three
**cross-reference summary lenses** (heterozygosity / diversity /
inbreeding) — they intentionally do NOT duplicate the deep per-sample
work; they show cohort headline numbers and route to the Diversity Atlas.

**Implemented in:**

| file | role |
|---|---|
| [`pages/structure/page_heterozygosity.html`](../atlases/population/pages/structure/page_heterozygosity.html) | static cross-reference card |
| [`pages/structure/page_heterozygosity.js`](../atlases/population/pages/structure/page_heterozygosity.js) | mount lifecycle (static; no render needed) |

---

## 1. The biological question

> What's the **cohort's heterozygosity profile** at a glance? Mean H,
> median H, ρ(H, F_ROH), and the Kruskal-Wallis H × K=8 cluster test.
> Then where to go for the per-sample drill-down.

## 2. Why this page is a "summary lens" not a deep view

This atlas covers the **226-fish cohort lens**. The deep per-sample
heterozygosity work (per-chromosome H, ANGSD pestPG ribbons, ROH-vs-
non-ROH H split) lives in the **Diversity Atlas's per_sample / chromosomes
/ hotspots pages**. To keep both atlases from drifting, this page
intentionally:

- Shows ONLY cohort-level headline numbers (mean, median, correlation,
  test statistic)
- Carries a prominent green callout pointing at the Diversity Atlas's
  matching deeper pages
- Renders NO interactive panels

This three-page pattern (heterozygosity ↗ / diversity ↗ / inbreeding ↗)
is per the four-atlas family table — population-atlas owns cohort
context; diversity-atlas owns per-sample depth.

## 3. Headline numbers (v2 target)

| metric | source | rationale |
|---|---|---|
| mean(H) across cohort | MODULE_3 per_sample_stats | distribution centre |
| median(H) | same | robust centre |
| H min / max range | same | spread |
| ρ(H, F_ROH) | derived | inbreeding-heterozygosity correlation |
| Kruskal-Wallis H × K=8 cluster p | structure cross-test | "do clusters differ in H?" |

## 4. Cross-atlas callout

```
┌───────────────────────────────────────────────────────────────┐
│ → Diversity Atlas · per_sample · chromosomes · hotspots       │
│   For per-sample H tables, per-chromosome ribbons, ROH-vs-    │
│   non-ROH H comparisons.                                       │
└───────────────────────────────────────────────────────────────┘
```

## 5. Data input

**v1 today** (scaffold): no layer loaded.

**v2 target**:
- `per_sample_stats_v1` (same layer as samples page; registry-cached)
- Headline numbers computed in-browser from the per-sample H column
  (no separate aggregate envelope needed for v2; an aggregate envelope
  is a v3 perf optimization)

## 6. State + interaction

- Cross-atlas link buttons → router navigate to diversity atlas pages
- No interactive state on this page

## 7. Failure modes

| # | condition | behaviour |
|---|---|---|
| 7.1 | `per_sample_stats` not loaded | scaffold renders with all-null headline numbers |
| 7.2 | H column missing on per_sample_stats | "data pending" chip per metric |

## 8. Promotion criteria

| criterion | v1 | v2 |
|---|---|---|
| Static scaffold renders | ✓ | ✓ |
| Cross-atlas callout | ✓ | ✓ |
| Headline numbers from `per_sample_stats` | ✗ | required |
| Kruskal-Wallis test | ✗ | required (computed client-side or via action) |
| Per-K-cluster H boxplots | ✗ | nice-to-have |

## 9. Open question

- **Should the Kruskal-Wallis run client-side or via a `/compute/`
  action?** Browser-side is fine for n=226; an action would centralise
  the test logic. Default: client-side using `shared/stats.js`.
