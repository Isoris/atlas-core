# SPEC — population-atlas `diversity ↗` page (cohort-summary lens)

**Status**: round-1 scaffold shipped (2026-05-11). Cross-reference
summary lens for cohort-level θπ — deep per-chromosome / per-window θπ
work lives in the **Diversity Atlas**.

**Implemented in:**

| file | role |
|---|---|
| [`pages/structure/page_diversity.html`](../atlases/population/pages/structure/page_diversity.html) | static cross-reference card |
| [`pages/structure/page_diversity.js`](../atlases/population/pages/structure/page_diversity.js) | mount lifecycle (static) |

---

## 1. The biological question

> What's the **cohort's nucleotide diversity (θπ) profile** at a glance?
> Genome-wide mean, available scales, cohort distribution. Then where
> to drill in.

## 2. Why this page is a "summary lens" not a deep view

Mirrors the [`heterozygosity ↗`](SPEC_heterozygosity_page.md) pattern.
Per-chromosome and per-window θπ depth lives in the Diversity Atlas's
chromosomes / hotspots pages — this page surfaces the cohort headline
+ cross-atlas pointer.

## 3. Headline numbers (v2 target)

| metric | source | rationale |
|---|---|---|
| genome-wide cohort θπ | ANGSD pestPG aggregate | distribution centre |
| per-sample mean θπ across chromosomes | per_sample_stats | per-sample spread |
| available scales grid | precomp manifest | `win10000.step2000 / win5000.step1000 / win50000.step10000 / win500000.step500000` |
| comparison: θπ vs Hudson's per-cohort baseline | reference table | sanity check |

## 4. Cross-atlas callout

```
┌───────────────────────────────────────────────────────────────┐
│ → Diversity Atlas · chromosomes · hotspots                    │
│   For per-chromosome θπ ribbons, per-window scans across all  │
│   four scales, and the hotspot / coldspot detection layer.    │
└───────────────────────────────────────────────────────────────┘
```

## 5. Available scales grid (informational)

| scale | windows | step | use case |
|---|---|---|---|
| fine | 10 kb | 2 kb | per-gene resolution |
| medium-fine | 5 kb | 1 kb | dense |
| medium | 50 kb | 10 kb | per-region |
| coarse | 500 kb | 500 kb | chromosome-arm |

## 6. Data input

**v1 today** (scaffold): no layer loaded.

**v2 target**:
- `diversity_theta_pi_pestpg` layer (per-sample × per-scale; same as
  diversity atlas)
- Aggregate cohort headline computed via shared/cohort_diversity.js
  helper (sum of per-sample θπ across the cohort, normalized)

## 7. State + interaction

- Cross-atlas link buttons (router navigate)
- Scale dropdown (cosmetic — actual rendering deferred to diversity atlas)

## 8. Promotion criteria

| criterion | v1 | v2 |
|---|---|---|
| Static scaffold renders | ✓ | ✓ |
| Cross-atlas callout | ✓ | ✓ |
| Cohort θπ headline numbers | ✗ | required |
| Available-scales grid populated from manifest | ✗ | required |
| Per-sample mean θπ distribution chip | ✗ | nice-to-have |

## 9. Open question

- **Should this page show an inline cohort θπ histogram, or strictly
  hand off to the Diversity Atlas?** Default: strict hand-off; an
  inline summary panel is an explicit v3 decision.
