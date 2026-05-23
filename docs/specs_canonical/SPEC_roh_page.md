# SPEC — diversity-atlas `roh` page (ROH composition: bins + heatmap + spectrum)

**Status**: scaffold.

**Scaffolded in:**

| file | role |
|---|---|
| [`pages/per_sample/roh.html`](../atlases/diversity/pages/per_sample/roh.html) | static fragment with view selector + length-class bins chart + heatmap + length-spectrum histogram |
| [`pages/per_sample/roh.js`](../atlases/diversity/pages/per_sample/roh.js) | mount lifecycle, view routing, stratification-pill consumer |

**Sister pages**:
- [`burden`](SPEC_burden_page.md) — shares the stratification pill
- [`samples`](SPEC_samples_page.md) — drill-down source

---

## 1. The biological hypothesis

> A sample's **ROH (Runs of Homozygosity) composition** carries
> information about its demographic history. Two samples with the
> same F_ROH total can have very different ROH length distributions:
> one with many short ROH (ancient bottleneck — pruning continues to
> chop long ROH over generations), another with few long ROH (recent
> inbreeding — full ROH segments still surviving). Different length
> classes index different demographic events.

Three orthogonal views:

1. **Length-class bins** — per-sample stacked bar: F_ROH_short
   (< 1 Mb), F_ROH_medium (1–10 Mb), F_ROH_long (> 10 Mb). The
   classical inbreeding-class decomposition.
2. **Per-chrom × per-sample F_ROH heatmap** — rows = samples,
   cols = chromosomes; cell intensity = F_ROH on that (sample, chrom).
   Reveals chromosome-specific ROH (sex-linked, low-recombination,
   under-purifying-selection).
3. **Length spectrum** — cohort-wide histogram of ROH segment lengths.
   Used to calibrate the length-class thresholds.

## 2. Data input

**v1 today** (static):
- `data/diversity/roh_per_sample.tsv` — one row per sample: `sample_id, F_ROH_short, F_ROH_medium, F_ROH_long, F_ROH_total, n_segments`
- `data/diversity/roh_segments.tsv` — long form: one row per ROH segment per sample
- `data/diversity/roh_per_chrom.tsv` — long form: per-(sample × chrom) F_ROH

**v2 target** (envelope-aware): a typed `diversity_roh_v1` envelope. Producer: `/mnt/e/results_diversity/04_roh/` from the ROH bundle (Module 04). Adapter pattern follows the cookbook.

```
payload.per_sample[i] = {
  sample_id, F_ROH_total,
  F_ROH_short, F_ROH_medium, F_ROH_long,
  length_thresholds: { short_max_bp, medium_min_bp, medium_max_bp, long_min_bp },
  n_segments: integer,
}
payload.per_chrom[i] = {
  sample_id, chrom, F_ROH, n_segments,
}
payload.segments[i] = {
  sample_id, chrom, start_bp, end_bp, length_bp, called_by,
}
payload.summary = {
  cohort_n, length_thresholds, mean_F_ROH, sd_F_ROH,
}
```

## 3. The three views

### 3.1 Length-class bins (default)

Per sample, a horizontal stacked bar with three segments:
- F_ROH_short (light shade)
- F_ROH_medium (mid shade)
- F_ROH_long (dark shade)

Bar width = F_ROH_total (so the visual emphasis is on samples with
high overall F_ROH). Stack order is fixed (short → medium → long).

Default stratification: cohort aggregate (no pill).

### 3.2 Per-chrom × per-sample F_ROH heatmap

A grid:
- Rows = samples (sortable: by sample_id, F_ROH_total, or K=8 cluster)
- Cols = chromosomes (sorted alphabetically: Chr01..Chr28)
- Cell colour intensity = `F_ROH(sample, chrom)`, scaled to the cohort
  max

Reveals chromosome-specific ROH:
- A sex chromosome (when present) shows a vertical band of high F_ROH
- Low-recombination chromosomes accumulate ROH
- Specific (sample, chrom) hotspots index family-level inbreeding

### 3.3 Length spectrum

A cohort-wide histogram: x = log(length_bp), y = count of ROH segments.
Two reference lines mark the short/medium boundary (1 Mb) and the
medium/long boundary (10 Mb). The user can drag the lines to retune
the thresholds for the v1 binning.

Typically bimodal:
- A low-length mode (~100 kb – 500 kb) — short ROH from old shared
  haplotypes
- A high-length mode (~5 Mb – 30 Mb) — long ROH from recent inbreeding

## 4. The math

### 4.1 Length-class binning

Per sample, given the segment set `R_s = { (start, end, length) }`:

```
F_ROH_short(s)  = Σ length  for segments with length < 1_000_000        / genome_length_bp
F_ROH_medium(s) = Σ length  for segments with 1_000_000 ≤ length < 10_000_000  / genome_length_bp
F_ROH_long(s)   = Σ length  for segments with length ≥ 10_000_000        / genome_length_bp
F_ROH_total(s)  = F_ROH_short + F_ROH_medium + F_ROH_long
```

The thresholds (1 Mb, 10 Mb) are configurable — they're producer-side
parameters shipped in `payload.length_thresholds`. The user can retune
them via the length-spectrum view's draggable lines.

### 4.2 Per-chrom F_ROH

For sample s, chrom c:

```
F_ROH(s, c) = Σ length(seg)  for seg in R_s with seg.chrom == c   / chrom_len_bp(c)
```

### 4.3 Length spectrum (cohort-wide)

For each segment across all samples, log10(length_bp) is the x-axis.
y is the count of segments per bin (50 bins evenly spaced in log).

Optional: a per-sample colour overlay so the user sees which samples
contribute to each length-class.

## 5. Shared stratification pill

The pill (atlas-state `state.shared.diversityStratification`) has 5
options:

| value | behaviour on this page |
|---|---|
| `all` (default) | cohort-wide; no per-stratum split |
| `K=8 cluster` | length-class bins: per-cluster aggregated; heatmap: rows grouped by cluster |
| `family` | per-family aggregation |
| `per-sample` | one bar per sample (the default view) |
| `F_ROH-quartile` | bin by F_ROH_total: Q1..Q4; aggregate within bin |

Pill state is **shared with the `burden` page** so toggling on one
toggles on both — keeps the per-stratum diversity vs burden view in
sync.

## 6. State + interaction

- `state.shared.activeSample` — set on row click (heatmap or length-bins bar)
- `state.shared.activeChrom` — set on heatmap column click
- `state.shared.diversityStratification` — shared with `burden`

## 7. Failure modes

| # | condition | behaviour |
|---|---|---|
| 7.1 | A sample has no ROH segments | F_ROH_total = 0; rendered as an empty bar |
| 7.2 | A sample has all segments < 1 Mb | F_ROH_medium = F_ROH_long = 0; bar all light shade |
| 7.3 | Length threshold dragged below the spectrum minimum | clamp to minimum; show a hint |
| 7.4 | Per-chrom F_ROH missing for some samples | heatmap cell rendered grey |
| 7.5 | A segment spans an assembly gap | producer should split; if shipped as one segment, render with a warning |
| 7.6 | Stratification pill = K=8 but the active K is something else | use whatever K is active (state.shared.activeQK); UI label updates |
| 7.7 | F_ROH_total > 1.0 (impossible — bug upstream) | clamp at 1.0; surface a warning |

## 8. What's currently NOT modelled

### 8.1 Envelope-aware data source

Producer pipeline + `diversity_roh_v1` adapter pending. v2 work.

### 8.2 Cohort-vs-individual mode

Toggle to view one sample against the cohort distribution
(per-bin reference curve overlaid on the sample's bar). v2 nice-to-have.

### 8.3 Pedigree-inbreeding overlay

When the relatedness atlas's `pedigree_f_v1` envelope is available,
overlay the **pedigree-expected** F (from known family relationships)
alongside the **genomic F_ROH**. Disagreement indicates either
pedigree errors or unusual ROH-call behaviour.

### 8.4 ROH source attribution

Each ROH segment came from ngsF-HMM. v2 could expose the segment's
called-by-method, confidence score, and per-window F. Diagnostic;
out of scope for v1.

### 8.5 Length-threshold sensitivity analysis

The 1 Mb / 10 Mb thresholds are common but not unique. v2 could show
"if you used 500 kb / 5 Mb instead, here's what changes" as a
calibration tool. The draggable threshold lines hint at this but
don't auto-recompute the bins yet.

## 9. Cross-page links

- Row click on length-bins bar / heatmap → `state.shared.activeSample`
- Column click on heatmap → `state.shared.activeChrom`
- Stratification pill state shared with `burden`
- Active sample → drill-down on sibling pages (`samples`, `texture`)

## 10. UI surface

```
┌────────────────────────────────────────────────────────────┐
│ status badge — cohort n · stratification (shared)         │
├────────────────────────────────────────────────────────────┤
│ Stratification pill: [all] K=8 | family | per-sample | F_ROH-quart│
│ View toggle:         [bins] heatmap | spectrum             │
├────────────────────────────────────────────────────────────┤
│ View — bins (default):                                     │
│   Per-sample stacked bars: short / medium / long           │
│                                                            │
│ View — heatmap:                                            │
│   Grid: rows = samples (sortable), cols = chromosomes      │
│   Cell colour = F_ROH(sample, chrom)                       │
│                                                            │
│ View — spectrum:                                           │
│   log-x histogram of segment lengths                       │
│   draggable threshold lines at 1 Mb and 10 Mb              │
└────────────────────────────────────────────────────────────┘
```

## 11. Promotion criteria

| criterion | v1 | v2 |
|-----------|----|----|
| Bins / heatmap / spectrum views render | ✓ | ✓ |
| View toggle | ✓ | ✓ |
| Stratification pill (5 modes) | ✓ | ✓ |
| Pill state shared with `burden` | ✓ | ✓ |
| Click handlers (row, col → state.shared) | ✓ | ✓ |
| Envelope-aware (`diversity_roh_v1`) | ✗ | required |
| Adapter pair shipped | ✗ | required |
| Draggable threshold lines auto-recompute bins | ✗ | nice-to-have |
| Pedigree-inbreeding overlay | ✗ | future |
| 25+ assertion JS smoke | ✗ | required |

## 12. Open biological design questions

### 12.1 Length-class boundary tuning

1 Mb and 10 Mb are typical; some studies prefer 500 kb and 5 Mb (for
species with high recombination), or 1.5 Mb and 30 Mb (for slow-
recombination species). Per-species calibration is a v2 nice-to-have;
v1 ships with the convention defaults and lets the user adjust via
the spectrum view's draggable lines.

### 12.2 Sex-chromosome treatment

The X / Y / W / Z chromosomes have different ROH expectations than
autosomes. Today they're pooled into F_ROH_total. v2 should expose a
"autosomes only" toggle so the F_ROH numbers aren't sex-chromosome
biased.

### 12.3 ROH-call method comparison

ngsF-HMM is one of several methods (PLINK --homozyg, BCFtools/RoH).
v2 could ship two methods and compare; for now the producer picks one
and the page consumes it.

### 12.4 Per-chrom recombination-rate normalisation

Low-recombination chromosomes accumulate ROH at any given F_ROH. A
v2 KW test of per-chrom F_ROH residuals after regressing on
recombination rate would identify chromosomes with **unusual ROH**
beyond what recombination alone explains.
