# SPEC — diversity-atlas `hotspots` page (θπ outlier windows)

**Status**: scaffold — per the manifest tooltip, the page targets "19
hotspots above the 99th percentile" of θπ across windowed genome.
Today reads from static demo / legacy files; v2 should consume a
typed `diversity_hotspots_v1` envelope.

**Scaffolded in:**

| file | role |
|---|---|
| [`pages/per_chromosome/hotspots.html`](../atlases/diversity/pages/per_chromosome/hotspots.html) | static fragment with hotspot list + per-sample heatmap |
| [`pages/per_chromosome/hotspots.js`](../atlases/diversity/pages/per_chromosome/hotspots.js) | mount lifecycle, outlier detection, heatmap render |

**Sister pages**:
- [`chromosomes`](SPEC_chromosomes_page.md) — chromosome-level aggregate; this page zooms to the windowed outlier level

---

## 1. The biological hypothesis

> Most of the genome has θπ near the cohort median. Windows with θπ
> well above this — local "hotspots" of high nucleotide diversity —
> identify regions experiencing **balancing selection**, **introgression
> from a divergent source**, or **gene-conversion accumulating divergent
> haplotypes**. Conversely, very-low-θπ outliers index regions under
> **strong purifying selection** or **recent selective sweeps**.

This page surfaces the **high-θπ tail** specifically. The default cutoff
is the 99th percentile across genome-wide windows — yielding ~19
hotspots on a 226-sample catfish cohort (per the manifest tooltip's
documented expected count). The 1st-percentile-low-θπ analogue is a
v2 view (see §7.2).

## 2. Data input

**v1 today** (static):
- `data/diversity/hotspots.tsv` — pre-computed outliers (one row per hotspot window): `chrom, win_start_bp, win_end_bp, theta_pi, percentile, rank`
- `data/diversity/hotspots_per_sample.tsv` — per-(sample × hotspot) θπ values feeding the heatmap

**v2 target** (envelope-aware): a typed `diversity_hotspots_v1` envelope produced by a builder that:
1. Reads cohort-wide windowed θπ from ANGSD pestPG outputs
2. Computes the global percentile distribution
3. Emits one row per window in the top tail (default top 1% = ~99th percentile cutoff)
4. Joins per-sample θπ on each hotspot window for the heatmap view

## 3. The two views

### 3.1 Hotspot list table

Columns:

| col | source | meaning |
|---|---|---|
| `rank` | producer | 1 = highest θπ |
| `chrom` | producer | chromosome the window sits on |
| `win_start_bp`, `win_end_bp` | producer | window coords; default size 10 kb (matches ANGSD pestPG) |
| `theta_pi` | producer | cohort-wide θπ in this window |
| `percentile` | producer | global percentile rank (default cutoff: ≥ 99.0) |
| `n_samples_supporting` | producer | count of samples with non-null θπ in this window |
| `nearby_features` | reference | gene names within ±5 kb (when reference annotation is joined) |

Click a row to scope the heatmap below.

### 3.2 Per-sample heatmap

Rows = hotspots, columns = samples. Cell colour intensity = per-sample θπ at that hotspot, scaled per row (0 = white, max per row = darkest red). Sorting:

- Default row order: hotspot rank ascending
- Default column order: cohort K=8 cluster (so cohort sub-structure shows as vertical colour blocks)

Heatmap reveals **which samples drive each hotspot**: a hotspot is interesting if many samples support it; less interesting if it's one sample with one outlier window (likely a data artefact).

## 4. The math

### 4.1 Cohort-wide θπ percentile cutoff

For window w of width `w_bp` (default 10 kb):

```
theta_pi(w) = ANGSD pestPG cohort-wide θπ in window w
percentile(w) = #{ windows w' : theta_pi(w') ≤ theta_pi(w) } / N_windows × 100
hotspot ⇔ percentile(w) ≥ 99.0
```

Equivalent: the top 1% of windows by θπ.

The producer ships windowed θπ in pestPG format; the builder enumerates,
computes the empirical percentile, and emits the top-tail subset.

### 4.2 What counts as "supporting" per sample

For each (hotspot w, sample s):

```
theta_pi(s, w) = ANGSD per-sample θπ in window w
sample s supports hotspot w  ⇔  theta_pi(s, w) ≥ cohort_median_theta_pi_global
                                AND not null
```

`cohort_median_theta_pi_global` is the median across all windows in
the cohort-wide θπ distribution. The "supports" predicate is a fairly
loose threshold; it just filters out samples where the hotspot signal
is absent.

`n_samples_supporting` is the count of samples passing this predicate.
Hotspots with low support (< 50% of cohort) are likely artefact-driven
(one outlier sample × one window).

### 4.3 Per-row colour scale on the heatmap

For each hotspot row:

```
row_max = max( theta_pi(s, w) for s in cohort, valid )
cell_intensity(s, w) = theta_pi(s, w) / row_max  ∈ [0, 1]
```

Per-row scaling means each hotspot is shown with full colour range
even if one is much higher overall than another. Reveals *which*
samples each hotspot belongs to, regardless of its absolute height.
v2 should expose a "global scale" toggle for cross-hotspot magnitude
comparison.

## 5. State + interaction

- `state.shared.activeChrom` — clicking a hotspot row sets this and routes sibling pages
- `state.shared.activeWindow` — new: scopes to the (chrom, win_start, win_end) triple; the [`burden`](SPEC_burden_page.md) page can read this and show functional features in the window

v2 should expose:
- Percentile-cutoff slider (default 99.0; let user slide to 99.5 / 95 / 90)
- Filter: minimum n_samples_supporting (default 50% of cohort)
- Heatmap column ordering: K=8 / family / sex / sample-id

## 6. Failure modes

| # | condition | behaviour |
|---|---|---|
| 6.1 | No windows above the percentile cutoff | render an empty-state hint; no rows. Should be rare given the 99% cutoff is empirically tuned. |
| 6.2 | A hotspot's window crosses an assembly gap | producer should drop these; if shipped, rendered with a warning chip |
| 6.3 | `n_samples_supporting < 10` (5% of cohort) | flag in the table (yellow row) but don't drop — the user can decide |
| 6.4 | Per-sample θπ missing for some hotspots | heatmap cell rendered grey; sample's mean intensity (for column ordering) computed only on non-null cells |
| 6.5 | Cutoff hardcoded at 99.0 | v2 should expose; v1 producer-bakes the threshold and ships the subset |
| 6.6 | Annotation absent (no `nearby_features`) | column hidden; rest of the table renders |

## 7. What's currently NOT modelled

### 7.1 Statistical significance of an individual hotspot

Being above the 99th percentile is **descriptive**, not a hypothesis test. A formal test would compare the observed θπ against the expected θπ under a neutral demography (e.g. coalescent simulations under the cohort's inferred Ne). Out of scope today; descriptive ranking is the manuscript-grade output for this page.

### 7.2 Cold-spot (low-θπ outlier) view

The mirror analysis — windows in the bottom 1% — indexes regions under strong purifying selection or recent sweep. v2 should ship a sister `coldspots` page or extend this one with a tail-direction toggle.

### 7.3 Window-size choice

Default 10 kb (matches ANGSD pestPG). Coarser (50 kb) windows smooth the signal; finer (1 kb) detect narrower hotspots but suffer noise. v2 should accept multiple window sizes and let the producer ship all of them, with a UI selector.

### 7.4 Overlap with known features

`nearby_features` is a simple ±5 kb gene-name lookup. A richer annotation join (regulatory elements, TE density, recombination rate) would help the reviewer interpret why a hotspot is hot. Cross-atlas read from `genome-atlas/annotation` envelopes.

### 7.5 Overlap with inversion candidates

Inversion-atlas inversion candidates often contain hotspots (the het haplotype is divergent from the hom haplotype at the SNP scale → elevated θπ within the inverted span). A v2 column `overlaps_inversion: inversion_id | null` would cross-link.

### 7.6 Per-K=8-cluster decomposition

The cohort-wide θπ in a window is high if the cohort is mixing two diverged ancestries. A per-cluster θπ decomposition would distinguish "high θπ from balancing selection within one cluster" from "high θπ from cluster admixture". Out of scope for v1.

## 8. Cross-page links

- Row click → `state.shared.activeChrom` + `state.shared.activeWindow`
- [`chromosomes`](SPEC_chromosomes_page.md) → click chromosome → load just that chrom's hotspots
- [`burden`](SPEC_burden_page.md) → for the active hotspot window, show functional annotations
- [`ancestry`](SPEC_ancestry_page.md) → re-order heatmap columns by K=8 cluster (shared `state.shared.activeQK`)

## 9. UI surface

```
┌────────────────────────────────────────────────────────────┐
│ status badge — n_hotspots · cutoff (99th pctl)             │
│   "19 hotspots above the 99th percentile of cohort θπ."    │
├────────────────────────────────────────────────────────────┤
│ hotspot list table (sortable)                              │
│   rank · chrom · start · end · θπ · pctl · n_supp · features│
│   row click → scope                                        │
├────────────────────────────────────────────────────────────┤
│ per-sample heatmap (rows = hotspots, cols = samples)       │
│   cell colour: per-row θπ intensity                        │
│   default column order: K=8 cluster grouping               │
├────────────────────────────────────────────────────────────┤
│ [Export TSV]                                                │
└────────────────────────────────────────────────────────────┘
```

## 10. Promotion criteria

| criterion | v1 | v2 |
|-----------|----|----|
| Hotspot list table renders | ✓ | ✓ |
| Per-sample heatmap renders | ✓ | ✓ |
| Click-row → state.shared.activeChrom + activeWindow | ✓ | ✓ |
| Envelope-aware (`diversity_hotspots_v1`) | ✗ | required |
| Adapter pair shipped | ✗ | required |
| Percentile-cutoff slider | ✗ | required |
| Cold-spot tail-direction toggle | ✗ | nice-to-have |
| Per-K=8 decomposition (§7.6) | ✗ | nice-to-have |
| 20+ assertion JS smoke | ✗ | required |

## 11. Open biological design questions

### 11.1 Window-size sensitivity

The 19-hotspot count is conditional on 10 kb windows. At 1 kb windows the count grows to hundreds (many spurious); at 100 kb windows it drops to ~5 (only the strongest). The producer ships one size; v2 may need multiple.

### 11.2 What threshold for "supporting samples"

§4.2 uses `theta_pi(s, w) ≥ cohort_median_theta_pi_global`. Alternative: `θπ(s, w) ≥ θπ(s, genome-wide) × 1.5` (relative to that sample's own genome-wide baseline — controls for sample-level coverage / sequencing-depth variation). v2 decision; v1 uses the simpler cohort-median threshold.

### 11.3 Multi-testing correction for cold + hot

A v2 with both tails should adjust for the doubled test count. Bonferroni or BH on the joint hotspot+coldspot list, not just the hot tail.
