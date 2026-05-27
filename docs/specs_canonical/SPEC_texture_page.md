# SPEC — diversity-atlas `texture` page (DDI + χ_min)

**Status**: scaffold.

**Scaffolded in:**

| file | role |
|---|---|
| [`pages/per_sample/texture.html`](../atlases/diversity/pages/per_sample/texture.html) | static fragment with DDI vs χ_min scatter plot + per-sample table |
| [`pages/per_sample/texture.js`](../atlases/diversity/pages/per_sample/texture.js) | mount lifecycle, scatter plot, table render |

**Sister page**: [`roh`](SPEC_roh_page.md) — texture metrics are
companions to the F_ROH | H framework

---

## 1. The biological hypothesis

> The cohort's per-sample heterozygosity (H) distribution along the
> genome carries information beyond its mean. Two samples with the
> same mean H can have very different **textures** — one with smooth
> H across windows, another with H concentrated in a few high-diversity
> islands separated by ROH-like floors. The texture metrics quantify
> this within-genome structure.

Two complementary metrics:

1. **DDI** (Dispersion-of-Diversity Index) — within-genome dispersion
   of windowed heterozygosity (`H_w`). High DDI = "rough" texture
   (long stretches of low H with bursts of high H); low DDI = "smooth"
   texture (uniformly distributed H).

2. **χ_min** — the cohort-relative diversity floor. For each sample,
   the χ_min is the lowest windowed H reached, relative to the
   cohort's lower envelope. Captures how deep the sample's "valleys"
   go.

Together they answer: **how is this fish's diversity distributed along
its genome?** Two fish with the same total H but very different DDI / χ_min
have very different demographic histories.

## 2. Data input

**v1 today** (static):
- `data/diversity/texture_per_sample.tsv` — one row per sample: `sample_id, ddi, chi_min, n_windows_used`
- Optional: `data/diversity/heterozygosity_window_grid.tsv` — long form (sample × window → H_w) for the underlying H distribution

**v2 target** (envelope-aware): a typed `diversity_texture_v1` envelope.

## 3. The two views

### 3.1 DDI vs χ_min scatter

Each sample is a dot at `(DDI, χ_min)`. Colour by K=8 cluster or
per-sample F_ROH or family — switchable via the stratification pill.

Diagonal-band annotations:
- Top-right region: high DDI + high χ_min → smooth high-H sample
  (typical wild-type)
- Bottom-left region: low DDI + low χ_min → uniformly low-H sample
  (sustained inbreeding throughout the genome)
- Top-left: low DDI + high χ_min → uniformly high-H (rare; suggests
  recent admixture)
- Bottom-right: high DDI + low χ_min → "rough" texture (ancient
  inbreeding with recent diversity bursts)

Outlier samples in any region are biologically meaningful.

### 3.2 Per-sample table

Columns: `sample_id, ddi, chi_min, n_windows_used, K=8_cluster,
F_ROH_quartile`. Sortable; click → set `state.shared.activeSample`.

## 4. The math

### 4.1 DDI (Dispersion-of-Diversity Index)

For sample s, given the per-window heterozygosity series `H_w(s)` over
N windows (default window size 100 kb):

```
mean_H(s) = mean(H_w(s)) over all windows w with valid H_w
sd_H(s)   = unbiased SD(H_w(s))
DDI(s)    = sd_H(s) / mean_H(s)        (coefficient of variation)
```

DDI is unit-less and bounded below by 0 (constant H across windows).
Typical values: DDI ∈ [0.3, 2.0]. A "smooth" sample has DDI ≈ 0.5; a
"rough" sample has DDI ≈ 1.5.

The coefficient-of-variation form normalises by mean — samples with
high mean H and high SD aren't artificially flagged as rough; only
samples whose SD is high **relative to their mean** are.

### 4.2 χ_min (cohort-relative diversity floor)

For sample s, χ_min is the lowest `H_w(s)` reached, expressed relative
to the cohort's window-by-window 5th-percentile:

```
cohort_5pctl_w  = 5th-percentile of H_w across all samples for window w
chi_min(s)      = min_w ( H_w(s) − cohort_5pctl_w )
```

`chi_min(s) > 0` → the sample's lowest valleys are above the cohort
floor (relatively diverse even in its quiet regions).
`chi_min(s) < 0` → the sample reaches below the cohort floor in some
windows (unusual local homozygosity).
`chi_min(s) = 0` → matches the cohort's typical low-window.

This is the "**how low does this fish go?**" metric — distinct from
mean H (the average) and from DDI (the spread).

### 4.3 Per-sample stability of DDI / χ_min

Both metrics are sensitive to the windowing scheme (window size, step,
window-rejection thresholds). v2 should ship per-sample 95% CIs by
resampling windows via bootstrap. Out of scope for v1.

## 5. State + interaction

- `state.shared.activeSample` — set on row click in the table; routes sibling pages
- `state.shared.diversityStratification` — read; scatter colours respect the current stratification

## 6. Failure modes

| # | condition | behaviour |
|---|---|---|
| 6.1 | `n_windows_used < 100` for a sample | flag with a "low coverage" chip; DDI / χ_min still computed but rendered amber |
| 6.2 | `mean_H = 0` (no diversity) | DDI undefined (div-by-zero); render `—` |
| 6.3 | Per-window H missing for some windows | producer pre-filters; if some remain, sample-side handling drops them |
| 6.4 | Cohort 5th percentile in window w is null (sparse cohort coverage) | window excluded from χ_min computation; n_windows_used decremented |

## 7. What's currently NOT modelled

### 7.1 Envelope-aware data source

Producer pipeline + adapter pair pending. v2.

### 7.2 Bootstrap CIs

Per §4.3. v2.

### 7.3 Other texture metrics

DDI and χ_min are two of several possible texture statistics. Others:
- **H wave height** (variance of H_w over a smoothing window)
- **H autocorrelation** (cor(H_w, H_{w+lag}) for lag = 1..10 windows)
- **H entropy** (Shannon entropy of the H_w distribution, binned)

Each captures a different aspect of texture. v1 ships the two
implemented by the producer; v2 could add more.

### 7.4 Per-chromosome texture

The current DDI / χ_min are genome-wide. Per-chromosome versions would
reveal chromosome-specific texture differences (e.g. a sex chromosome
with very different texture than autosomes). Out of scope for v1.

### 7.5 Cross-cohort texture comparison

A v2 evolution-atlas might compare hatchery-cohort texture against
wild-cohort texture for the same species — DDI / χ_min are absolute
metrics so cross-cohort comparison is meaningful. Not in scope here.

## 8. Cross-page links

- Row click → `state.shared.activeSample` → sibling pages scope to that sample
- DDI / χ_min outlier samples often correlate with extreme F_ROH; the
  [`roh` page](SPEC_roh_page.md) is the natural drill-down
- Texture metrics are descriptive — a follow-up statistical test (e.g.
  "do K=8 clusters differ in median DDI?") lives on the
  [`ancestry` page](SPEC_ancestry_page.md)

## 9. UI surface

```
┌────────────────────────────────────────────────────────────┐
│ status badge — n_samples · stratification (from shared)    │
├────────────────────────────────────────────────────────────┤
│ DDI vs χ_min scatter plot                                  │
│   x: DDI · y: χ_min · dot colour: stratification           │
│   diagonal region annotations: smooth / inbred / etc.      │
├────────────────────────────────────────────────────────────┤
│ Per-sample table (sortable)                                │
│   sample_id · DDI · χ_min · n_windows · cluster · quartile │
│   row click → activeSample                                 │
├────────────────────────────────────────────────────────────┤
│ [Export TSV]                                                │
└────────────────────────────────────────────────────────────┘
```

## 10. Promotion criteria

| criterion | v1 | v2 |
|-----------|----|----|
| Scatter plot renders | ✓ | ✓ |
| Per-sample table | ✓ | ✓ |
| Stratification colour | ✓ | ✓ |
| Click-row → activeSample | ✓ | ✓ |
| Envelope-aware (`diversity_texture_v1`) | ✗ | required |
| Adapter pair shipped | ✗ | required |
| Bootstrap CIs on DDI / χ_min | ✗ | nice-to-have |
| Per-chrom texture | ✗ | future |
| Additional texture metrics (§7.3) | ✗ | future |
| 20+ assertion JS smoke | ✗ | required |

## 11. Open biological design questions

### 11.1 Window size for the H distribution

DDI is sensitive to window size. Default 100 kb (matches the diversity
pipeline's standard window). 10 kb gives finer texture but more noise;
1 Mb gives smoother texture but loses local structure. v2 should expose
the window size as a slider tied to the per-window H envelope.

### 11.2 Cohort 5th-percentile for χ_min

The 5th percentile is a robust lower-envelope choice. Some prefer 10th;
some prefer "1st-percentile + 2σ" or analogous robust statistics. v2
choice. v1: 5th, no override.

### 11.3 What texture says about biology

A "rough" texture (high DDI) can mean:
- Old inbreeding (long ROH valleys interrupted by recent admixture)
- Recent admixture (high-H islands within an inbred background)
- Sex-chromosome influence (if pooled into autosomes)

The metrics alone don't disambiguate; cross-page context with ROH
length-class spectrum + ancestry decomposition is needed.

### 11.4 Threshold for "unusual texture"

What DDI / χ_min count as "outlier"? v2 should compute the cohort's
empirical distribution and flag samples > 2σ from the mean. Today: no
flagging; descriptive view only.
