# SPEC — meiosis-atlas `nco` page (gene-conversion view)

**Status**: shipped 2026-05-20 as v1 (envelope-aware, 4 views, 36-assertion
smoke). v2 needs a proper statistical null for the `in_vs_out` view: the
v1 implementation shows the crosstab and amber-highlights the
MOSAIC_SHORT × inside-inversion cell, but emits no enrichment p-value
(§4 below documents the missing math).

**Implemented in:**

| file | role |
|---|---|
| [`pages/hub/nco.html`](../atlases/meiosis/pages/hub/nco.html) | controls + result slot |
| [`pages/hub/nco.js`](../atlases/meiosis/pages/hub/nco.js) | mount / probe / Render / Export wiring; 5 exported renderers (filterTracts, renderPerDyad, renderLengthHist, renderPerChrom, renderInVsOut, renderStatusBadge) |
| [`css/pages/nco.css`](../atlases/meiosis/css/pages/nco.css) | `#nco`-scoped badge / table / bar / hint styles; MOSAIC_SHORT × yes accent |
| [`pages/hub/test_nco_envelope.js`](../atlases/meiosis/pages/hub/test_nco_envelope.js) | 36-assertion smoke (filterTracts, per-view renderers, status badge in 3 states) |
| [`shared/api_client.js`](../atlases/meiosis/shared/api_client.js) | self-contained re-export of listLayers / getLayer / resolveLatestLayer (created for this page; reused by all meiosis pages since) |

**Sister pages**:
- [`crossovers`](SPEC_crossovers_page.md) — CO/DCO companion; same scaffolding shape
- [`interchromosomal`](SPEC_interchromosomal_page.md) — the inter-chrom test that the gene-conversion signal contextualises

---

## 1. The biological hypothesis

> Inside inversion heterozygotes' inverted segments, **double-crossover-shaped tracts of 50–200 kb** that the legacy classifier called "DCO" are often **gene-conversion events**, not double crossovers. ngsTracts separates these as the `MOSAIC_SHORT` class.

The biology: in an inversion heterozygote, recombination intermediates inside the inverted region typically resolve as **non-crossovers (gene conversions)** because the orientation mismatch makes crossover resolution unviable in meiosis. The result is short tracts of allelic swap (typically 1–10 kb in classical literature, up to ~200 kb for the longest documented gene-conversion tracts in plants/fish).

ngsTracts' classifier flags these as `MOSAIC_SHORT` when:
- tract length ∈ [50 kb, 200 kb]
- inside an inversion (or its flanking region)
- the surrounding context isn't consistent with a true return-to-flank DCO

If the inversion-vs-gene-conversion biology is real in this cohort, **the `MOSAIC_SHORT × inside_inversion = yes` cell of the per-class × inside-inversion crosstab should be enriched above the marginal rate.** That's the headline signal.

The other tract classes are reported for context:
- `NCO` — classical short gene conversions (anywhere in the genome)
- `MOSAIC_LONG` — long-span departures with matching flanks (suspicious; could be ancient gene conversions, miscalled rearrangements, or assembly errors)
- `AMBIG` / `LOW_CONFIDENCE` — filter rejects; rendered in the table but not central to any view

## 2. Data input — `tract_classifications_v1`

Single envelope, fetched via
`resolveLatestLayer('tract_classifications', { stage: 'normalized' })`
in `mount()`. Per
[`SPEC_tract_classifications_adapter.md`](SPEC_tract_classifications_adapter.md)
the typed payload exposes:

```
payload.tracts[i] = {
  interval_id,           // DEP_NNNNNN — Stage 3's stable ID
  parent_id, offspring_id,
  chrom, start, end, span_bp,
  class:                 // NCO | CO | DCO | MOSAIC_SHORT | MOSAIC_LONG | AMBIG | LOW_CONFIDENCE
  confidence:            // high | medium | low
  flanking_left_state, flanking_right_state, departure_state,
  n_sites, n_discordant,
  inside_inversion:      // yes | partial | no
  distance_to_nearest_inv_bp,
  prior_log_ratio_co_nco,
  refined_breakpoint_bp, refined_ci_left, refined_ci_right,  // STEP_TRC_02 only
  manual_review_flag, notes,
}
payload.summary = {
  n_tracts, n_dyads, n_chroms, n_inside_inversion,
  class_counts: { NCO, CO, DCO, MOSAIC_SHORT, MOSAIC_LONG, AMBIG, LOW_CONFIDENCE }
}
```

The page filters to **gene-conversion-like classes** for most views (`NCO`, `MOSAIC_SHORT`, `MOSAIC_LONG`) and uses `class` + `inside_inversion` as the primary stratifiers.

## 3. The four views

UI selects view via `#ncoView`. Class scope via `#ncoClass` (NCO / MOSAIC_SHORT / MOSAIC_LONG / **ALL_NCO_LIKE** = NCO ∪ MOSAIC_SHORT, default). Region scope via `#ncoScope` (all / inside_inv / outside_inv).

### 3.1 `per_dyad` — tract count per (parent, offspring)

`renderPerDyad(tracts)` in [`nco.js:68`](../atlases/meiosis/pages/hub/nco.js).

Tally `tracts` by `(parent_id, offspring_id)` after the filter cascade, sort descending by count, render as a two-column table. Descriptive — no statistical test, no normalisation by chrom length or by n_sites.

A future v2 may divide by `Σ n_sites` per dyad to give a per-site NCO rate, but the v1 view is just a count for inspection.

### 3.2 `length_hist` — tract-length histogram

`renderLengthHist(tracts)` in [`nco.js:86`](../atlases/meiosis/pages/hub/nco.js).

10-bucket histogram of `span_bp` for the filtered tracts. Bar width is rendered as a percentage of the max bucket. The histogram is **fixed-bin** between observed min and max; that means a small effect at the long tail (a single MOSAIC_LONG outlier) compresses all the other bars. v2 should expose a log-scale toggle.

The bimodal shape (one peak at NCO scale, one at MOSAIC_SHORT scale) is the visual proxy for the underlying gene-conversion-class structure.

### 3.3 `per_chrom` — tract count per chromosome

`renderPerChrom(tracts)` in [`nco.js:116`](../atlases/meiosis/pages/hub/nco.js).

Tally by `chrom`, sort alphabetically. Descriptive only.

Limitation: not normalised by chromosome length, so it's a count-of-tracts view, not a rate-per-Mb view. v2 should join against `chromosome_meiosis_events_v1` (which has `chrom_len_bp`) to derive a per-Mb rate.

### 3.4 `in_vs_out` — class × inside_inversion crosstab (HEADLINE)

`renderInVsOut(tracts)` in [`nco.js:131`](../atlases/meiosis/pages/hub/nco.js).

Computes a 3×3 contingency table:

```
                    inside_inversion
                yes    partial    no
            ┌──────┬─────────┬──────┐
NCO         │ n11  │  n12    │ n13  │
            ├──────┼─────────┼──────┤
MOSAIC_SHORT│ n21  │  n22    │ n23  │  ← headline cell: n21
            ├──────┼─────────┼──────┤
MOSAIC_LONG │ n31  │  n32    │ n33  │
            └──────┴─────────┴──────┘
```

Cell `n21` (MOSAIC_SHORT × yes) is rendered with `color: var(--accent)` and bold — visual highlight. A hint line below reads: "Bold amber: MOSAIC_SHORT × yes — gene-conversion tracts inside inversions, the meiosis-atlas headline signal."

#### 3.4.1 What's wrong with this in v1 (honest)

**No null model.** The crosstab shows raw counts. Whether `n21` is enriched **above what we'd expect by chance** isn't tested. A small cohort with a few MOSAIC_SHORT calls all happening to land inside inversions would *visually* look like the headline signal, but lack any statistical support.

**The right test is documented in §4 below; it's not yet implemented in v1.**

## 4. The correct null for the `in_vs_out` view

The biological null hypothesis:

> H0: A tract's class (NCO / MOSAIC_SHORT / MOSAIC_LONG) is **independent** of its `inside_inversion` status (yes / partial / no), given the marginal totals.
>
> H1: They are not independent — specifically, MOSAIC_SHORT is over-represented inside inversions.

### 4.1 Test choice

Three reasonable approaches, in order of statistical-power vs assumption-burden:

**1. Fisher's exact test on the 2×2 simplified contingency.**

Collapse the 3×3 to a 2×2 by lumping:
- rows: MOSAIC_SHORT vs (NCO ∪ MOSAIC_LONG)
- cols: inside (yes) vs outside (partial ∪ no)

```
          inside  outside
MOSAIC_SHORT  a      b
others        c      d
```

Two-sided Fisher's exact p tests independence in the 2×2.

Pros: exact (no asymptotic approximation), works at small n.
Cons: collapses information; conflates "partial" with "no".

**2. Chi-squared on the full 3×3.**

```
χ² = Σᵢⱼ (Oᵢⱼ − Eᵢⱼ)² / Eᵢⱼ     where Eᵢⱼ = (rowᵢ × colⱼ) / N
df = (3−1) × (3−1) = 4
```

Pros: uses all cells; standard test.
Cons: asymptotic — unreliable when expected cell count < 5.

**3. Permutation test on the MOSAIC_SHORT cell.**

Shuffle the `inside_inversion` labels across tracts (preserving class). Recount `n_MOSAIC_SHORT_inside`. The p-value is the empirical tail probability of the observed `n21` under the null.

Pros: no asymptotic assumption; matches the family-aware permutation idiom of the sister pages.
Cons: doesn't address the family-block question (MOSAIC_SHORT calls within a single family-of-related-fish are not independent observations — see §4.3).

### 4.2 Recommendation for v2

**Use Fisher's exact on the 2×2 (option 1) as the primary p-value**, plus report the **odds ratio + 95% CI** as the effect size:

```
OR = (a × d) / (b × c)
log(OR) ~ Normal(log(OR_true), 1/a + 1/b + 1/c + 1/d)
95% CI on log(OR):  log(OR) ± 1.96 × sqrt(1/a + 1/b + 1/c + 1/d)
```

When n grows large enough that Fisher's is slow, the chi-squared on the
3×3 is the secondary test. Both reported.

### 4.3 What Fisher's exact does NOT account for

**Family / parent clustering.** Multiple tracts from the same dyad share a meiosis; multiple dyads from the same family share parents. Treating each tract as an independent observation inflates n and deflates p.

For the **family-aware version**, run Fisher's exact on a per-family roll-up:

```
For each family F:
  a_F = #{ MOSAIC_SHORT tracts in F × inside_inv yes }
  b_F = #{ MOSAIC_SHORT tracts in F × inside_inv no/partial }
  c_F = #{ other tracts in F × inside_inv yes }
  d_F = #{ other tracts in F × inside_inv no/partial }
Aggregate: Mantel-Haenszel test or Stouffer combination of per-family p-values
```

This is the gene-conversion equivalent of the family-block permutation
in the [interchromosomal page](SPEC_interchromosomal_page.md). When the
producer's tract data includes the family hub structure (which today's
adapter doesn't propagate; see §7.5 below), the Mantel-Haenszel test
becomes the correct null.

### 4.4 What does an enriched MOSAIC_SHORT × inside_inv actually mean?

If the test rejects H0 with OR > 1:
- **Strongest interpretation**: ngsTracts' MOSAIC_SHORT classification captures a biologically distinct class — inversion-region gene conversions that the legacy CO classifier would have miscounted. The meiosis-atlas approach validates.
- **Weaker interpretation**: the classifier may be **biased** to call MOSAIC_SHORT preferentially inside inversions (e.g. because the inside_inversion = yes status is a feature in the classifier). This would be a producer-side bias, not a biological signal. Mitigation: validate the classifier's per-class decision rule against a held-out cohort.
- **Null result (OR ≈ 1, p large)**: either the biology isn't there, or the classifier doesn't separate MOSAIC_SHORT from CO/DCO well, or n is too small.

The SPEC for the producer-side decision tree is in [`ngsTracts/docs/METHODOLOGY.md` §3](../../ngsTracts/docs/METHODOLOGY.md); the relevant gate is whether `inside_inversion ∈ {yes, partial}` is itself an input to the MOSAIC_SHORT classifier or only a downstream label.

## 5. Worked example (synthetic)

Suppose 100 tracts with the following counts:

```
                    inside_inversion
                yes    partial    no
NCO              5       2       30    = 37
MOSAIC_SHORT     8       1       3     = 12
MOSAIC_LONG     2       1       8     = 11
                15      4       41    = 60 (excluding CO/DCO/AMBIG/LOW_CONFIDENCE)
```

(Other classes total 40 to reach n_tracts=100.)

### 5.1 The v1 render

`renderInVsOut` flags the MOSAIC_SHORT × yes cell (8) in amber bold. The user eyeballs and concludes the signal looks present.

### 5.2 What §4.1 option 1 (Fisher 2×2) gives

Collapse:

```
         inside  outside (no + partial)
MOSAIC_SHORT  8       4
others       7      41
```

Two-sided Fisher's exact: p ≈ **0.0018** (calculation by Fisher's exact test for `a=8, b=4, c=7, d=41`).

Odds ratio: `(8 × 41) / (4 × 7)` ≈ **11.7**.
log(OR) = 2.46; SE = sqrt(1/8 + 1/4 + 1/7 + 1/41) ≈ 0.62.
95% CI on OR: `exp(2.46 ± 1.96 × 0.62)` ≈ **(3.5, 39.5)**.

**Conclusion (v2 view)**: MOSAIC_SHORT tracts are 11.7× more likely to occur inside an inversion than other gene-conversion tracts; the 95% CI excludes 1; the test rejects H0 at α = 0.05 with margin.

The v1 page shows the raw counts and a colour highlight. The v2 page would also show OR = 11.7 (3.5 – 39.5), p = 0.0018.

### 5.3 What would change with family-aware Mantel-Haenszel

If those 100 tracts came from 5 families with very unequal sizes — say one big family contributed 6 of the 8 MOSAIC_SHORT × yes tracts — Fisher's on the pooled counts would still give p ≈ 0.0018, but the **family-clustered** test would correctly say "this signal rests on one family; we don't know if it generalises." A naive Fisher's exact misses this.

The producer-side gap (§7.5) means we can't run the family-aware test in v1. Documenting the gap is part of why this SPEC is worth writing.

## 6. Filters + per-view effect

| filter | applies | how |
|--------|---------|-----|
| `#ncoClass` | all 4 views | filters `tracts` by class before any computation |
| `#ncoScope` | all 4 views | filters by `inside_inversion ∈ {yes, no}` (or any) before any computation |

Filter order: class first, then scope, then per-view tally. The order doesn't matter for the final counts; it does affect intermediate row counts shown in the status messages.

When `#ncoClass = ALL_NCO_LIKE` (default), the filter is `class ∈ {NCO, MOSAIC_SHORT}` — MOSAIC_LONG is excluded because it's the "suspicious long" bucket, not gene-conversion-like.

The `in_vs_out` view IGNORES `#ncoClass` because the crosstab itself is the stratification. It uses all NCO / MOSAIC_SHORT / MOSAIC_LONG rows regardless of the class filter. v2 should make this explicit in the UI (e.g. grey-out the class selector when `#ncoView = in_vs_out`).

## 7. What's currently NOT modelled

### 7.1 Statistical test on `in_vs_out`

Per §4 above. v1 shows raw counts + a colour highlight. v2 needs Fisher's exact (or chi-squared on 3×3) + odds ratio with 95% CI + the Mantel-Haenszel family-aware variant when family hub data is available.

### 7.2 Per-Mb rate on `per_chrom`

Per §3.3 above. v2 should join against `chromosome_meiosis_events_v1` for `chrom_len_bp` and render rate per Mb alongside the raw count.

### 7.3 Log-scale toggle on `length_hist`

Per §3.2 above. A single MOSAIC_LONG outlier compresses the rest of the histogram. A `log10(span_bp)` x-axis would separate the bimodal distribution cleanly.

### 7.4 Tract-quality filtering

Tracts have `confidence` (high / medium / low) and `manual_review_flag`. The v1 page does NOT filter on these. A reviewer who wants only `confidence = high` tracts in the `in_vs_out` test has no UI control today. Add `#ncoConfidence` and `#ncoFlagged` filters in v2.

### 7.5 Family/parent clustering for the `in_vs_out` null

Per §4.3 above. Adding this needs the producer to emit family/block IDs alongside each tract, or the page needs to join against the FAPD envelope (which today is consumed only by the interchromosomal page).

### 7.6 Sex stratification

Pooled across sexes today. As with the [interchromosomal §9.4](SPEC_interchromosomal_page.md) and [crossovers §9.3](SPEC_crossovers_page.md) gaps, heterochiasmy may give different MOSAIC_SHORT-inside-inv enrichments in males vs females. Add `#ncoSex` filter in v2.

### 7.7 Per-inversion drill-down

The `in_vs_out` view shows aggregate counts. A click-through that opens a per-inversion crosstab ("for inversion `INV_LG28_01`, here's the MOSAIC_SHORT × {yes, no} count among its carrier dyads") would let the user trace strong overall signals to specific inversions. Not in v1.

## 8. Reproducibility

v1 is fully deterministic — sums + groupings + a colour highlight. Identical envelope → identical render.

v2's Fisher's exact is also deterministic (it's an exact combinatorial enumeration). The Mantel-Haenszel variant is deterministic too. **No RNG is needed for the nco page.** That's a meaningful difference from the sister pages — `interchromosomal` and the v2 `crossovers` use permutation tests that need RNG.

## 9. UI surface

```
┌────────────────────────────────────────────────────────────┐
│ status badge (ok / empty / warn)                           │
│   ok: layer_id · N tracts · K dyads · L chroms ·           │
│       inside_inv: X · NCO: a · MOSAIC_SHORT: b ·           │
│       MOSAIC_LONG: c                                       │
├────────────────────────────────────────────────────────────┤
│ #ncoClass ▾ (NCO / MOSAIC_SHORT / MOSAIC_LONG / ALL_NCO_LIKE)│
│ #ncoScope ▾ (all / inside_inv / outside_inv)               │
│ #ncoView  ▾ (per_dyad / length_hist / per_chrom / in_vs_out)│
│ [Render] [⤓ Export]                                         │
├────────────────────────────────────────────────────────────┤
│ #ncoResultSlot — depends on #ncoView:                      │
│   per_dyad:     (parent → offspring × n_tracts) table      │
│   length_hist:  10-bin span_bp histogram with bars         │
│   per_chrom:    (chrom × n_tracts) table                   │
│   in_vs_out:    3×3 (class × inside_inv) crosstab          │
│                 + MOSAIC_SHORT × yes amber-bold highlight  │
│                 + hint line                                │
└────────────────────────────────────────────────────────────┘
```

## 10. Promotion criteria

| criterion | v1 | v2 |
|-----------|----|----|
| `mount()` calls `resolveLatestLayer()` with fail-soft | ✓ | ✓ |
| Status badge in 3 states | ✓ | ✓ |
| `per_dyad`, `length_hist`, `per_chrom`, `in_vs_out` views render | ✓ | ✓ |
| MOSAIC_SHORT × yes highlight in `in_vs_out` | ✓ (cell colour only) | ✓ + p-value + OR + CI |
| Fisher's exact p-value on `in_vs_out` | ✗ | required |
| Odds ratio + 95% CI | ✗ | required |
| Mantel-Haenszel family-aware variant | ✗ | required when family hub is available |
| TSV export | ✓ | ✓ |
| Per-chrom rate (per Mb) | ✗ | nice-to-have (§7.2) |
| Confidence / manual-review-flag filters | ✗ | required (§7.4) |
| Log-scale on length_hist | ✗ | nice-to-have (§7.3) |
| 30+ assertion JS smoke | ✓ (36) | ≥ 36 |

v1 is shipped under "useful but flagged". v2 promotion blocks on (a) the Fisher's exact + odds-ratio implementation, (b) a tested fixture where the MOSAIC_SHORT × yes cell is statistically significant under H0, (c) the family-block plumbing for Mantel-Haenszel (which today is missing from the tract_classifications envelope).

## 11. Open biological design questions

### 11.1 Is `inside_inversion = partial` enrichment-relevant?

§3.4 collapses to 2×2 by lumping `partial` with `no`. But `partial` (tract crosses an inversion boundary) is biologically interesting — gene conversions at inversion boundaries are predicted to be common because the orientation mismatch creates breaks at the edge. v2 should report a 2×3 chi-squared as a secondary view: `MOSAIC_SHORT vs others × {yes, partial, no}` to test whether `partial` is intermediate between `yes` and `no`.

### 11.2 What about CO/DCO inside inversions?

The `in_vs_out` view excludes CO and DCO because they're handled on the [crossovers page](SPEC_crossovers_page.md). But a complementary expected-counts question is: **inside inversions, the ratio MOSAIC_SHORT / CO should approach infinity** (i.e. no true crossovers inside; everything is gene conversion). A v2 cross-page view could merge the two pages' data and report this ratio.

### 11.3 Length-class boundary at 50 kb / 200 kb

The MOSAIC_SHORT class is defined as `span_bp ∈ [50 kb, 200 kb]`. These boundaries are producer-side decisions (ngsTracts METHODOLOGY §3). If the catfish data has a different gene-conversion-length distribution, the cutoffs may misclassify true gene conversions as `NCO` (below 50 kb) or `MOSAIC_LONG` (above 200 kb). The v2 page could expose a "show length distribution by class" diagnostic (a per-class violin plot) to surface this.

### 11.4 Confidence × class interaction

`confidence = low` tracts may be disproportionately MOSAIC_LONG (since the classifier is more conservative about calling DCO at low n_sites). A v2 stratified table — `(class × confidence × inside_inv)` — would surface this and let the user filter to high-confidence-only for the headline test.

### 11.5 Real-data calibration of the 50–200 kb window

The MOSAIC_SHORT window is currently a defined-by-fiat parameter. With real cohort data, the v2 view should produce a length-density plot per class to validate that MOSAIC_SHORT really does have a distinct mode separable from NCO and MOSAIC_LONG. If the modes overlap, the classification is doing real work (and we should keep going); if they're indistinguishable, the class itself is suspect.
