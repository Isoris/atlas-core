# SPEC — population-atlas `inbreeding ↗` page (cohort-summary lens)

**Status**: round-1 scaffold shipped (2026-05-11). Cross-reference
summary lens for cohort-level F_ROH — deep per-sample F_ROH atlas and
ROH composition work lives in the **Diversity Atlas**.

**Implemented in:**

| file | role |
|---|---|
| [`pages/structure/page_inbreeding.html`](../atlases/population/pages/structure/page_inbreeding.html) | static cross-reference card |
| [`pages/structure/page_inbreeding.js`](../atlases/population/pages/structure/page_inbreeding.js) | mount lifecycle (static) |

---

## 1. The biological question

> What's the **cohort's inbreeding profile** at a glance? F_ROH median,
> high-F_ROH carrier fraction, ROH length-bin distribution. Then where
> to drill in for per-sample composition.

## 2. Why this page is a "summary lens" not a deep view

Mirrors the [`heterozygosity ↗`](SPEC_heterozygosity_page.md) and
[`diversity ↗`](SPEC_diversity_page.md) pattern. Deep per-sample
F_ROH atlas + ROH composition + gene-overlap lives in the Diversity
Atlas's roh page — this page surfaces cohort headline + cross-atlas
pointer.

## 3. Headline numbers (v2 target)

| metric | source | rationale |
|---|---|---|
| median(F_ROH) across cohort | per_sample_stats | distribution centre |
| F_ROH Q3 + IQR cut | derived | outlier threshold for "high inbreeding" |
| count(samples with F_ROH > Q3+1.5×IQR) | derived | "high-F_ROH carrier" tally |
| ROH bin schema (length classes) | reference | aligns with diversity atlas |

## 4. ROH bin schema (informational)

| bin | length range | interpretation |
|---|---|---|
| short | < 1 Mb | ancient identity-by-descent |
| medium | 1 – 5 Mb | mid-historical IBD |
| long | ≥ 5 Mb | recent inbreeding |

Length-class decomposition (`F_ROH_short / F_ROH_medium / F_ROH_long`)
is the diversity atlas's primary inbreeding signal.

## 5. Cross-atlas callout

```
┌───────────────────────────────────────────────────────────────┐
│ → Diversity Atlas · roh                                       │
│   For per-sample F_ROH atlas, per-length-bin decomposition,   │
│   ROH × gene-model intersection (functional burden).          │
└───────────────────────────────────────────────────────────────┘
```

## 6. Data input

**v1 today** (scaffold): no layer loaded.

**v2 target**:
- `per_sample_stats_v1` (same layer as samples page; registry-cached)
- F_ROH headline numbers computed in-browser

## 7. Promotion criteria

| criterion | v1 | v2 |
|---|---|---|
| Static scaffold renders | ✓ | ✓ |
| Cross-atlas callout | ✓ | ✓ |
| Median F_ROH headline | ✗ | required |
| High-F_ROH carrier tally with threshold | ✗ | required |
| ROH bin schema grid | ✓ | ✓ |
| Per-length-bin headline numbers (short/medium/long) | ✗ | nice-to-have (requires per-bin columns on per_sample_stats) |

## 8. Open question

- **High-F_ROH threshold**: Tukey IQR vs fixed (F_ROH ≥ 0.05 per
  hatchery health page convention)? Default: Tukey for the "high-F_ROH
  carrier" tally on this page; fixed 0.05 on the hatchery-health page
  for verdict assignment. Document the divergence prominently.
