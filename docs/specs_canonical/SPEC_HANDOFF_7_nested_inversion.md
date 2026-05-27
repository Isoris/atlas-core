# HANDOFF 7 — Nested inversion detection

**Goal**: detect whether a candidate inversion contains a smaller
inversion nested inside it, by conditional re-scanning of inversion
signals within each parent karyotype background.

**Status**: not started. Builds on HANDOFFs 1 (PCA producer for parent
karyotype assignment), 5 (tree, optionally re-run within stratum), and
6 (fingerprinter — already detects regime switches; this handoff adds
hierarchical structure detection that's complementary).

**Audience**: a fresh chat where Claude implements the nested-inversion
detection pipeline.

---

## The conceptual core

The fundamental question:

> Inside this candidate inversion, is there *another* karyotype axis?

The distinction between two outcomes:

| Pattern | Interpretation |
|---|---|
| One large coherent haplotype block | Simple inversion |
| Large block, plus a second independent split among carriers | **Nested inversion** |

The key diagnostic rule:

> **A true nested inversion should appear within one parent arrangement
> background, not only when all samples are mixed.**

This is what makes the test specific. A "smaller square inside a bigger
square" in a similarity matrix can be lots of things — family LD,
ancestry, low-recombination region, marker polarity artifact. A real
nested inversion shows a recurrent karyotype axis (3-band structure,
shared boundaries across many carriers) **inside one parent arrangement
class** — not just "in the data overall."

So the central technique is **conditional re-scanning**: stratify
samples by parent karyotype, re-run inversion-detection signals
(local PCA, contingency association, sample clustering) within each
stratum, and look for emergent 3-band structure that wasn't visible
in the whole-cohort scan.

---

## What this handoff is NOT

- **NOT a discovery pipeline.** Candidate parent inversions must
  already be identified by the upstream pipeline (your existing
  D17 / triangle / local-PCA detection, or HANDOFF 1's producer).
  This handoff *characterizes* candidates — does each one contain
  nested structure?
- **NOT a replacement for the fingerprinter** (HANDOFF 6). The
  fingerprinter detects *regime transitions along the genome* (the
  inversion changes through space). This handoff detects *hierarchical
  karyotype structure* (a second axis exists within the same spatial
  region). Both can appear in the same candidate; they're orthogonal
  signals.
- **NOT a replacement for the tree** (HANDOFF 5). The tree tests
  whether bands form clades; nested detection tests whether one band
  splits into sub-bands when isolated.

---

## The 10 methods (prioritized)

| Priority | Method | Purpose |
|---|---|---|
| **PRIMARY** | (1) Conditional local PCA per parent karyotype | Core test: emergent 3-band structure within stratum |
| **PRIMARY** | (8) Multi-PC scan (PC2, PC3, PC4) | Nested signals often hide on higher PCs |
| **PRIMARY** | (9) Peel method (drop one parent class, rescan) | Filter against family/ancestry artifacts |
| Secondary | (2) Residualize parent karyotype effect | When parent dominates entire signal |
| Secondary | (3) Conditional Cramér's V | Quantitative version of (1) |
| Secondary | (4) Hierarchical sample clustering inside parent | Visualizable complement to (1) |
| Secondary | (10) AF contrast inside arrangement backgrounds | Marker development output |
| External | (5) Breakpoint evidence (DELLY/Manta) | Supplementary; weak at 9× WGS |
| Existing | (6) Haplotype tree inside block | HANDOFF 5; rerun within stratum |
| Existing | (7) Recombination/DCO detector | HANDOFF 6; with disambiguation rule |

Primary methods (1, 8, 9) are the spec's core algorithm. Secondary
methods are computed for cross-validation but don't override the
primary verdict. External method (5) is out of scope — handled
elsewhere. Existing methods (6, 7) are integrated via cross-references.

---

## Pipeline architecture

```
                  ┌─────────────────────────────────┐
                  │ Candidate parent inversion      │
                  │ (from upstream local PCA / D17  │
                  │ / HANDOFF 1 producer)           │
                  │                                 │
                  │ Includes: chrom, start, end,    │
                  │ per-sample PC1 score, band      │
                  │ assignment HOM1/HET/HOM2        │
                  └────────────┬────────────────────┘
                               │
                               ▼
                  ┌─────────────────────────────────┐
                  │ Stratify samples by parent      │
                  │ karyotype                       │
                  │  - HOM1 stratum                 │
                  │  - HET stratum                  │
                  │  - HOM2 stratum                 │
                  │ Min stratum size check          │
                  └────────────┬────────────────────┘
                               │
            ┌──────────────────┼──────────────────┐
            ▼                  ▼                  ▼
    ┌───────────────┐  ┌───────────────┐  ┌───────────────┐
    │ Method 1:     │  │ Method 8:     │  │ Method 9:     │
    │ within-stratum│  │ multi-PC scan │  │ peel method   │
    │ local PCA     │  │ (PC1-PC5)     │  │ (rescan after │
    │ for each band │  │ per stratum   │  │ removing one  │
    │               │  │               │  │ stratum)      │
    └───────┬───────┘  └───────┬───────┘  └───────┬───────┘
            └──────────────────┼──────────────────┘
                               │
                               ▼
                  ┌─────────────────────────────────┐
                  │ Inner-interval candidates       │
                  │ (windows showing emergent       │
                  │ 3-band structure within         │
                  │ one parent stratum)             │
                  └────────────┬────────────────────┘
                               │
                               ▼
                  ┌─────────────────────────────────┐
                  │ Cross-validation (secondary):   │
                  │  - Method 2 residualization     │
                  │  - Method 3 conditional         │
                  │    Cramér's V                   │
                  │  - Method 4 hierarchical        │
                  │    sample clustering            │
                  │  - Method 10 AF contrast        │
                  └────────────┬────────────────────┘
                               │
                               ▼
                  ┌─────────────────────────────────┐
                  │ Boundary-recurrence test:       │
                  │ are inner-interval boundaries   │
                  │ shared across many carriers?    │
                  │ (filters DCO from nested)       │
                  └────────────┬────────────────────┘
                               │
                               ▼
                  ┌─────────────────────────────────┐
                  │ Final classification:           │
                  │  - simple_inversion             │
                  │  - nested_inversion             │
                  │  - overlapping_inversions       │
                  │  - recombination_leakage        │
                  │  - family_LD_artifact           │
                  │  - hidden_nested_pc2_pc3        │
                  └─────────────────────────────────┘
```

---

## Inputs

For each parent candidate:
- Candidate interval (chrom, start, end)
- Sample → parent karyotype assignment (HOM1 / HET / HOM2) from HANDOFF 1
- Per-sample dosage matrix in the candidate interval (from HANDOFF 1
  heatmap producer or from the filtered Beagle directly)
- Optional: HANDOFF 6 fingerprinter output (recombinant carrier list
  to exclude from primary nested test, since they're already known to
  be sample-level recombination events)

---

## Stage 1: stratification and minimum stratum size

```r
# Read parent karyotype labels
parent_kary <- read_band_labels("pca_results/pca_bi_baseline_*.json",
                                 candidate_id = "LG28_15.115_18.005")
# parent_kary: named vector, sample_id → "HOM1" | "HET" | "HOM2"

# Stratify
stratum_HOM1 <- names(parent_kary)[parent_kary == "HOM1"]  # n=60
stratum_HET  <- names(parent_kary)[parent_kary == "HET"]   # n=106
stratum_HOM2 <- names(parent_kary)[parent_kary == "HOM2"]  # n=60

# Minimum stratum size for reliable PCA
MIN_STRATUM_SIZE <- 20   # configurable; default 20

strata_to_scan <- c()
for (s in c("HOM1", "HET", "HOM2")) {
  size <- length(get(paste0("stratum_", s)))
  if (size >= MIN_STRATUM_SIZE) {
    strata_to_scan <- c(strata_to_scan, s)
  } else {
    message(sprintf("Stratum %s has only %d samples (< %d); skipping",
                    s, size, MIN_STRATUM_SIZE))
  }
}
```

For LG28's 60/106/60 split, all three strata pass. For an imbalanced
candidate (e.g., 5/15/206), only HET (15) and HOM2 (206) might pass at
threshold 20; HOM1 stratum (5) is too small.

**The HET stratum is special**: HET samples carry one chromosome of
each parent arrangement. Nested structure that segregates within one
parent arrangement may show up subtly in HET samples (because half of
each HET sample's chromatids carry that arrangement). For the primary
test, focus on HOM1 and HOM2 strata; HET stratum is supplementary.

---

## Stage 2 — Method 1 (PRIMARY): conditional local PCA per stratum

For each stratum that passes the size threshold, run windowed local PCA
on **only that stratum's samples** within the candidate interval.

```r
# For each stratum
for (stratum_name in strata_to_scan) {
  samples <- get(paste0("stratum_", stratum_name))
  n_samples_stratum <- length(samples)

  # Subset dosage matrix to this stratum's samples
  X_stratum <- dosage_matrix[samples, ]

  # Run windowed local PCA — same machinery as HANDOFF 1 producer
  per_window_pca <- run_local_pca_windowed(
    X = X_stratum,
    chrom = candidate$chrom,
    start = candidate$start,
    end = candidate$end,
    window_size = 50000,    # default; configurable
    window_step = 25000,
    n_pcs = 5               # IMPORTANT: scan PC1-PC5, not just PC1-PC2
  )

  # Save per-window PC scores for this stratum
  saveRDS(per_window_pca,
          paste0("nested_results/", candidate_id, "/stratum_",
                 stratum_name, "_per_window_pca.rds"))
}
```

This produces, per stratum, per window, a set of PC1-PC5 scores for
each sample in that stratum.

### What to look for

For each stratum's per-window PCA, ask **per window**:

> Does any of PC1-PC5 in this stratum show a clean 3-band pattern?

Operational test: K-means with K=3 on each PC's scores, then test
silhouette score. If silhouette > threshold (default 0.5) for any of
PC1-PC5 in a window, that window is an **inner-band candidate** for
that stratum.

```r
# Per window, per PC, test for 3-band structure
inner_band_candidates <- list()
for (w in seq_len(n_windows)) {
  for (pc_idx in 1:5) {
    scores <- per_window_pca[[w]]$scores[, pc_idx]
    km <- kmeans(scores, centers = 3, nstart = 25)
    sil <- mean(cluster::silhouette(km$cluster, dist(scores))[, 3])

    if (sil > 0.5) {
      inner_band_candidates[[length(inner_band_candidates) + 1]] <- list(
        stratum = stratum_name,
        window_idx = w,
        bp_start = per_window_pca[[w]]$start,
        bp_end = per_window_pca[[w]]$end,
        pc_index = pc_idx,
        silhouette = sil,
        cluster_assignment = km$cluster,
        cluster_centers = km$centers
      )
    }
  }
}
```

### Inner-interval definition

A **contiguous run** of windows showing 3-band structure on the same
PC index (e.g., PC2 of HOM1 stratum), with band assignments stable
across the run, is an **inner-interval candidate**:

```r
# Group inner-band candidates by (stratum, pc_index) and find runs
inner_intervals <- find_contiguous_runs(
  inner_band_candidates,
  group_by = c("stratum", "pc_index"),
  min_run_windows = 3   # default; nested signals need ≥3 contiguous windows
)
```

A nested inversion with internal coordinate `[c, d]` should produce a
contiguous run of windows from `c` to `d`, all showing 3-band structure
on the same PC index of the same stratum.

---

## Stage 3 — Method 8 (PRIMARY): multi-PC scan

Method 1 already scans PC1-PC5. This stage formalizes the
interpretation:

| PC where signal appears | Interpretation |
|---|---|
| PC1 of stratum (when stratum-internal) | Strong nested signal — dominant within-stratum axis |
| PC2 of stratum | **Most common location for nested signal** — parent has been "removed" by stratification, second axis is the nested arrangement |
| PC3-PC5 of stratum | Weaker nested signal, or family/ancestry substructure; flag for cross-validation |

In practice, **most real nested inversions appear on PC1 or PC2 of one
stratum** (the parent is gone within the stratum, so the next strongest
axis emerges to PC1 or PC2). PC3+ signals are higher-priority for
manual inspection because they could be artifacts.

### Implementation note

The scan in Method 1 already produces silhouette scores per
(stratum, window, PC). Tabulating these as a **PC × window** heatmap
per stratum is the most informative visualization:

```
HOM1 stratum:        windows
                     1  2  3  4  5  6  7  8  9  10
PC1 silhouette:     .2 .3 .2 .2 .8 .9 .9 .8 .3 .2   ← inner inversion on PC1
PC2 silhouette:     .3 .4 .3 .3 .4 .3 .3 .3 .3 .3
PC3 silhouette:     .2 .2 .2 .2 .2 .3 .2 .2 .2 .2
```

A nested inversion appears as a **horizontal block of high silhouette**
on one PC across consecutive windows.

---

## Stage 4 — Method 9 (PRIMARY): peel method

The peel method tests whether emergent inner-band structure persists
after removing one parent stratum. This is the **strongest filter
against family LD / ancestry artifacts**, which is critical for
hatchery cohorts.

### The logic

A true nested inversion exists within a parent arrangement background.
If we remove the parent HOM1 samples and run local PCA on
(HET + HOM2) samples only, the nested inversion that was inside HOM2
should still appear (because HOM2 samples are still present).
Conversely, family LD and ancestry signals depend on the full sample
composition; removing a stratum often makes them disappear.

### Implementation

```r
# For each combination of "samples to keep" — peel one stratum at a time
peel_runs <- list(
  "all"          = c(stratum_HOM1, stratum_HET, stratum_HOM2),  # baseline
  "no_HOM1"      = c(stratum_HET, stratum_HOM2),
  "no_HET"       = c(stratum_HOM1, stratum_HOM2),
  "no_HOM2"      = c(stratum_HOM1, stratum_HET),
  "only_HOM1"    = stratum_HOM1,
  "only_HOM2"    = stratum_HOM2
)

for (peel_name in names(peel_runs)) {
  samples <- peel_runs[[peel_name]]
  if (length(samples) < MIN_STRATUM_SIZE) next

  pca_result <- run_local_pca_windowed(
    X = dosage_matrix[samples, ],
    chrom = candidate$chrom,
    start = candidate$start,
    end = candidate$end,
    n_pcs = 5
  )
  saveRDS(pca_result, paste0("peel_", peel_name, ".rds"))
}
```

### Cross-checking inner intervals against peel results

For each inner-interval candidate from Method 1 (e.g., "PC2 of HOM1
stratum, windows 38-46"), check whether the same interval appears in
the peel runs that should preserve it:

| Inner interval found in | Should appear in peel | Interpretation |
|---|---|---|
| HOM1 stratum (PC2) | "only_HOM1" run, "no_HET" run | If yes → confirmed; if no → likely family LD |
| HOM2 stratum (PC1) | "only_HOM2" run, "no_HET" run | Same |

Inner intervals that **disappear** when relevant strata are kept but
others removed are flagged as `family_LD_artifact_candidate`.

Inner intervals that **persist** across all expected peels are flagged
as `nested_inversion_candidate_strong`.

---

## Stage 5 — Method 2 (Secondary): residualize parent karyotype

When the parent inversion's signal dominates the entire candidate
interval (large per-marker dosage shifts between HOM1/HET/HOM2), the
nested signal can be hidden inside the parent's residual variation.
Residualization removes the parent's mean effect per marker, then
re-runs the analysis.

### Math

For each marker `m` in the candidate, fit:

```
dosage_m ~ parent_karyotype_dummy + residual
```

where `parent_karyotype_dummy` is HOM1 = 0, HET = 1, HOM2 = 2 (or
treated as factor with two dummy variables for full flexibility).

```r
# Per marker, compute residual dosage
parent_dummy <- model.matrix(~ factor(parent_kary))
residual_dosage <- matrix(NA, nrow = n_samples, ncol = n_markers)
for (m in seq_len(n_markers)) {
  fit <- lm(dosage_matrix[, m] ~ parent_dummy)
  residual_dosage[, m] <- residuals(fit)
}

# Run local PCA on residuals (full cohort, all samples)
residual_pca <- run_local_pca_windowed(
  X = residual_dosage,
  chrom = candidate$chrom,
  start = candidate$start, end = candidate$end,
  n_pcs = 5
)
```

If a nested inversion exists, it should appear cleanly on PC1 of the
residualized data (because the parent's contribution has been removed).

### Cross-validation against Method 1

The same nested interval should appear in:
- **Method 1**: high silhouette on PC1-PC2 of HOM1 or HOM2 stratum
- **Method 2**: high silhouette on PC1 of residualized full cohort

If both methods agree → strong evidence. If only one → weaker; inspect.

---

## Stage 6 — Method 3 (Secondary): conditional Cramér's V

A quantitative complement to Method 1. For each pair of windows
`(i, j)` within the candidate, compute:

```r
# Within each parent stratum, contingency table of band assignments
# at window i vs band assignments at window j
for (stratum_name in strata_to_scan) {
  samples <- get(paste0("stratum_", stratum_name))
  bands_i <- per_window_bands[samples, i]
  bands_j <- per_window_bands[samples, j]
  tab <- table(bands_i, bands_j)
  cv_within_stratum[stratum_name, i, j] <- cramers_v(tab)
}

# Marginal Cramér's V (full cohort) for comparison
tab_marginal <- table(per_window_bands[, i], per_window_bands[, j])
cv_marginal[i, j] <- cramers_v(tab_marginal)
```

### What to look for

A nested inversion shows:
- **High `cv_within_stratum`** for window pairs inside the inner
  interval — the inner-interval bands within the stratum are coherent
- **`cv_marginal` may also be high**, but for the wrong reason (parent
  inversion creates association across the candidate)

The **diagnostic ratio**:

```r
nested_signal_ratio <- cv_within_stratum / cv_marginal
```

For windows inside a true nested interval, the ratio should be
elevated **within the stratum where the nested inversion segregates**.
For windows outside any nested interval, the ratio should be ≈1
(within-stratum association ≈ marginal association = parent signal).

### Output

A heatmap per stratum: window × window matrix of Cramér's V, with
nested intervals appearing as smaller squares inside the larger
parent square.

---

## Stage 7 — Method 4 (Secondary): hierarchical sample clustering

Visual complement to the per-window analyses. Build a hierarchical
clustering of samples using their dosage profile across the candidate:

```r
# Per-sample dosage vector across candidate windows
sample_profiles <- aggregate_dosage_per_window(dosage_matrix,
                                                 windows = candidate_windows)
# n_samples × n_windows matrix

# Hierarchical clustering
d <- dist(sample_profiles, method = "manhattan")
hc <- hclust(d, method = "ward.D2")

# Cut at multiple levels
cuts_K3 <- cutree(hc, k = 3)   # parent karyotype
cuts_K6 <- cutree(hc, k = 6)   # potentially nested
cuts_K9 <- cutree(hc, k = 9)
```

### Interpretation

A simple inversion should give:
- K=3 cuts → match parent karyotype assignment (HOM1 / HET / HOM2)
- K=6 cuts → split the parent classes evenly (no real structure)

A nested inversion should give:
- K=3 cuts → match parent karyotype
- K=6+ cuts → split **one parent class** asymmetrically — the parent
  class that contains the nested inversion subdivides into 3 sub-bands

The dendrogram shape itself is informative:

```
Simple inversion:                   Nested inversion:
                                    
  ┌── HOM1                            ┌── HOM1
  │                                   │
──┤                                 ──┤   ┌── HOM2.A
  │                                   │   │
  └── HET ── HOM2                     │ ──┤   ┌── HOM2.B (HET inside)
                                      │   │   │
                                      │   └───┤
                                      │       │
                                      │       └── HOM2.C
                                      │
                                      └── HET
```

### Output

Dendrogram PDF + a TSV listing how K=3, K=6, K=9 cuts relate. If a
parent class subdivides into 3 sub-bands at K=6, that's a candidate
nested inversion confined to that parent class.

---

## Stage 8 — Method 10 (Secondary): AF contrast inside arrangement backgrounds

For each candidate inner interval, compute allele frequency in:
- The full cohort (background)
- Each parent stratum (within-arrangement)
- Each putative nested-band sub-stratum (within sub-arrangement)

```r
# For an inner interval found in HOM1 stratum on PC2 with K=3 sub-bands
hom1_bandA <- samples_in_inner_band("HOM1", "A")
hom1_bandB <- samples_in_inner_band("HOM1", "B")
hom1_bandC <- samples_in_inner_band("HOM1", "C")

# For each marker in the inner interval
af_bandA <- compute_AF(dosage_matrix[hom1_bandA, inner_markers])
af_bandB <- compute_AF(dosage_matrix[hom1_bandB, inner_markers])
af_bandC <- compute_AF(dosage_matrix[hom1_bandC, inner_markers])

# Compute pairwise Fst
Fst_AB <- compute_Fst(af_bandA, af_bandB, n_bandA, n_bandB)
Fst_AC <- compute_Fst(af_bandA, af_bandC, n_bandA, n_bandC)
Fst_BC <- compute_Fst(af_bandB, af_bandC, n_bandB, n_bandC)
```

### What to look for

If the inner interval is a real nested inversion, Fst between the
putative sub-bands within HOM1 should be:
- **High inside the inner interval**: substantial differentiation
  between HOM1.A and HOM1.B (≥0.05, often much higher for real
  inversions)
- **Low outside the inner interval**: all HOM1 samples are essentially
  the same outside the nested inversion's coordinates

This produces the **classic suspension-bridge / inversion shelf
signature** but **inside one parent arrangement**, which is the
diagnostic feature.

### Marker development output

For each candidate nested inversion, output the top-N markers (highest
Fst between sub-bands) as **diagnostic markers**:

```
nested_diagnostic_markers.tsv:
inner_interval_id   marker                 Fst_AB   AF_bandA   AF_bandB   recommendation
LG28_15.5_15.8_HOM1_PC2  C_gar_LG28_15534521_A_G   0.62   0.05    0.85   genotype to assign HOM1 sub-arrangement
...
```

These can be PCR-typed in the lab to validate the nested inversion.

---

## Stage 9: boundary-recurrence test (the DCO disambiguation)

This is the test from method (7) of the user's text — distinguishing
nested inversions from per-sample DCO/recombination events.

A double crossover (HANDOFF 6 Stage 4) is a **per-sample, sample-
specific** event: one carrier shows HOM1 → HET → HOM1 in their dosage,
others don't.

A nested inversion is a **shared, cohort-level pattern**: many carriers
show the same boundaries because they all carry the same nested
arrangement.

### Test

For each candidate inner interval:

```r
# Among samples whose dosage at the inner interval is HET (relative to
# the inner-interval reference) — i.e., samples that visit the nested
# HET state — what are the boundaries?

inner_HET_samples <- which(inner_kary == "HET")

# For each such sample, identify the windows where they enter and exit
# the inner interval's HET state
sample_boundaries <- lapply(inner_HET_samples, function(s) {
  get_state_transitions(dosage_matrix[s, candidate_windows],
                         inner_state = "inner_HET")
})

# Test: are the boundary positions clustered?
boundary_starts <- sapply(sample_boundaries, function(b) b$entry_window)
boundary_ends   <- sapply(sample_boundaries, function(b) b$exit_window)

# A nested inversion has boundaries at the SAME positions across samples
# A DCO event has boundaries scattered across samples
boundary_clustering_score <- 1 - sd(boundary_starts) / mean(boundary_starts)
```

### Interpretation rules

| Boundary pattern across carriers | Verdict |
|---|---|
| Many carriers (>5), shared boundaries (low variance in entry/exit) | `nested_inversion_or_shared_recombinant_haplotype` |
| Few carriers (1-3), variable boundaries | `double_crossover_per_HANDOFF_6` |
| Many carriers, variable boundaries | `complex_recombination_landscape_inspect` |

The first two are unambiguous; the third is the difficult case where
multiple recombinant haplotypes exist (possibly from different
generations of crossover) without a common nested arrangement.

A nested inversion should also show:
- Recurrent boundaries → caught by this test
- 3-band structure within the parent class → caught by Methods 1, 8
- AF contrast within parent class → caught by Method 10

If all three signals agree → confident `nested_inversion`. If only the
first → could be `shared_recombinant_haplotype` (a recombinant tract
that's been propagated through the population by drift/selection,
producing similar carriers but no underlying inversion).

---

## Stage 10: integration with HANDOFF 5 (tree, optional)

For each candidate inner interval, optionally re-run HANDOFF 5's
sample-level tree but **only on samples in the relevant stratum** and
**only on markers in the inner interval**. The nested arrangement, if
real, should produce clade structure within the stratum's samples that
matches the inner-band assignments.

This is method (6) from the user's text. The HANDOFF 5 pipeline
(Path B: SNP alignment → IQ-TREE GTR+ASC) handles this directly:

```bash
# Subset to HOM1 stratum, inner interval markers
bash run_tree_for_candidate.sh \
  --candidate LG28_15.115_18.005_HOM1_inner \
  --bands_from nested_results/inner_band_assignments.json \
  --beagle_view bi_baseline.beagle.gz \
  --core_interval_chrom C_gar_LG28 \
  --core_interval_start 15500000 --core_interval_end 15800000 \
  --include_samples_only stratum_HOM1.txt \
  --het_mode iupac \
  --out_dir trees/LG28_HOM1_inner_15.5_15.8/
```

Concordance between inner-band assignments and tree clades → strong
support. This re-uses HANDOFF 5's full machinery (NJ on dXY, IQ-TREE
GTR+ASC, ARI/Cramér's V concordance) without any new code.

---

## Stage 11: classification

Combine evidence from all stages into a verdict per candidate:

```r
classify_nested <- function(candidate_results) {
  evidence <- list(
    method1_3band_in_stratum    = candidate_results$method1$any_inner_interval,
    method2_residual_3band      = candidate_results$method2$residual_pca_signal,
    method3_conditional_cramers = candidate_results$method3$signal_ratio_above_threshold,
    method4_hierarchical_split  = candidate_results$method4$asymmetric_K6_split,
    method8_pc_location         = candidate_results$method8$pc_index,
    method9_persists_in_peels   = candidate_results$method9$peel_consistency,
    method10_high_internal_Fst  = candidate_results$method10$Fst_within_stratum_above_threshold,
    boundary_recurrence         = candidate_results$boundaries$shared_across_carriers,
    tree_concordance            = candidate_results$tree$ARI_above_threshold   # optional
  )

  n_supporting <- sum(unlist(evidence), na.rm = TRUE)
  primary_methods_supporting <- sum(unlist(
    evidence[c("method1_3band_in_stratum",
               "method8_pc_location",
               "method9_persists_in_peels")]
  ), na.rm = TRUE)

  if (primary_methods_supporting == 3 && n_supporting >= 5) {
    return("nested_inversion_strong")
  } else if (primary_methods_supporting >= 2 && n_supporting >= 4) {
    return("nested_inversion_likely")
  } else if (evidence$method1_3band_in_stratum && !evidence$method9_persists_in_peels) {
    return("family_LD_artifact_candidate")
  } else if (evidence$method8_pc_location > 2 && primary_methods_supporting < 2) {
    return("hidden_pc3_signal_inspect")
  } else if (evidence$boundary_recurrence == "shared" && n_supporting < 3) {
    return("shared_recombinant_haplotype")
  } else if (n_supporting == 0) {
    return("simple_inversion")
  } else {
    return("complex_inspect_manually")
  }
}
```

### The diagnostic table (canonical)

This is the table from the user's text, formalized:

| Pattern | Verdict |
|---|---|
| One clean 3-band block across full interval | `simple_inversion` |
| Large block + smaller internal 3-band block inside one parent class | `nested_inversion` |
| Two blocks partly overlapping but not contained | `overlapping_inversions` |
| One/few samples switch band then return | `double_crossover_per_HANDOFF_6` |
| Many samples switch at same boundaries | `nested_inversion` or `shared_recombinant_haplotype` (Stage 9 disambiguates) |
| Internal block disappears after peeling stratum | `family_LD_artifact` |
| Internal block appears on PC2/PC3 but not PC1 | `nested_inversion_on_higher_PC` (worth inspection) |

---

## Outputs

```
nested_results/<candidate_id>/
├── stratum_assignments.tsv           # sample → parent karyotype
├── stratum_HOM1_per_window_pca.rds   # Method 1: per-stratum PCA
├── stratum_HET_per_window_pca.rds
├── stratum_HOM2_per_window_pca.rds
├── peel_runs/                         # Method 9
│   ├── all.rds
│   ├── no_HOM1.rds
│   ├── no_HET.rds
│   ├── no_HOM2.rds
│   ├── only_HOM1.rds
│   └── only_HOM2.rds
├── residual_pca.rds                   # Method 2
├── conditional_cramers_v.tsv          # Method 3
├── hierarchical_clustering.rds        # Method 4
├── nested_diagnostic_markers.tsv      # Method 10
├── boundary_recurrence_test.tsv       # Stage 9
├── inner_intervals_candidate.tsv      # all candidate inner intervals
├── classification.json                # final verdict per candidate
└── plot_pc_x_window_silhouette.pdf    # heatmap PC × window per stratum
└── plot_dendrogram.pdf
└── plot_residual_pca.pdf
└── plot_inner_diagnostic.pdf          # 4-panel summary per inner candidate
```

The 4-panel summary plot per candidate inner interval is the paper
figure: (a) PC × window heatmap showing where the signal lives;
(b) per-stratum scatter of inner-band PCs; (c) AF contrast track
across the candidate; (d) boundary recurrence histogram across
carriers.

---

## Driver

```bash
bash run_nested_for_candidate.sh \
  --candidate LG28_15.115_18.005 \
  --parent_pca pca_results/pca_bi_baseline_unweighted_bi_baseline.json \
  --beagle bi_baseline.beagle.gz \
  --beagle_sidecar bi_baseline.beagle.pairs.tsv \
  --window_size 50000 --window_step 25000 \
  --n_pcs 5 \
  --min_stratum_size 20 \
  --silhouette_threshold 0.5 \
  --min_run_windows 3 \
  --residualize TRUE \
  --conditional_cramers TRUE \
  --hierarchical TRUE \
  --af_contrast TRUE \
  --tree_within_stratum FALSE \
  --out_dir nested_results/LG28_15.115_18.005/
```

Flags:
- `--n_pcs`: PCs to scan per window per stratum (default 5)
- `--min_stratum_size`: min samples for a stratum to qualify (default 20)
- `--silhouette_threshold`: K=3 silhouette threshold for "3-band" call
  (default 0.5; tune per cohort)
- `--min_run_windows`: minimum contiguous windows for an inner interval
  (default 3; ≈150 kb at default window size)
- `--residualize`, `--conditional_cramers`, `--hierarchical`,
  `--af_contrast`: toggle secondary methods (default TRUE for all)
- `--tree_within_stratum`: optionally invoke HANDOFF 5 within stratum
  (default FALSE; expensive — run as follow-up if Stage 11 returns
  `nested_inversion_strong` or `nested_inversion_likely`)

---

## Implementation phases

### Phase 1: stratification + Method 1 (1-2 days)
- Parent karyotype assignment from PCA results
- Stratum size check
- Per-stratum local PCA scanning PC1-PC5
- K=3 silhouette per (stratum, window, PC)
- Output inner-interval candidates

### Phase 2: Method 8 + Method 9 (1-2 days)
- PC × window silhouette heatmap (Method 8 visualization)
- Peel runs (drop one stratum, re-PCA)
- Cross-check inner intervals against peel results
- Output: family-LD-artifact filter applied

### Phase 3: secondary methods (2-3 days)
- Method 2: residualization + full-cohort PCA on residuals
- Method 3: conditional Cramér's V matrices per stratum
- Method 4: hierarchical clustering with multi-K cuts
- Method 10: AF contrast within strata + diagnostic markers

### Phase 4: boundary-recurrence + classification (1-2 days)
- Stage 9 boundary clustering test
- Stage 11 evidence integration → final verdict
- Output classification.json per candidate

### Phase 5: visualization (1-2 days)
- 4-panel summary plot per candidate
- PC × window heatmaps per stratum
- Dendrograms with K=3/6/9 cut markers

### Phase 6: HANDOFF 5 integration (optional, 0.5-1 day)
- Wire `--include_samples_only` and `--core_interval_*` flags into
  the HANDOFF 5 driver
- Run within-stratum tree only when classification is
  `nested_inversion_strong` or `nested_inversion_likely`

Total ~1.5-2 weeks for full feature. **Phases 1+2 alone (3-4 days)
deliver the headline diagnostic** — conditional local PCA + peel
filter — which is the strongest method and sufficient for paper claims
in clean cases.

---

## Honest expected performance

The fundamental signal — emergent 3-band structure within a parent
stratum — is **biologically clean** when present. The detection has
high specificity in clear cases. Concerns:

### Will work
- Large nested inversion within a balanced parent inversion
  (LG28-style 60/106/60 with a real nested 15-30 Mb sub-inversion in
  the HOM2 background): clearly detectable on PC1 or PC2 of the HOM2
  stratum.
- Moderate-size nested with sufficient stratum size and reasonable
  recombination rate: detectable, especially with peel filter
  confirmation.

### Probably work, with care
- Smaller nested inversions (<500 kb): detectable if SNP density and
  stratum size suffice. May appear on PC2-3 rather than PC1.
- Imbalanced parent inversions (one stratum has few samples): the
  rare stratum can't be tested directly. The peel method partially
  mitigates by examining whether the signal persists across peels.

### Honestly uncertain
- **Distinguishing nested inversion from family LD substructure** in
  hatchery cohorts. The peel method is the best filter but won't
  remove all ambiguity. For severely family-structured cohorts,
  nested signals should be cross-validated with breakpoint evidence
  (when long-read data becomes available — Method 5, currently out of
  scope).
- **Distinguishing nested inversion from shared recombinant haplotype**
  (a recombinant tract carried by many samples without an underlying
  inversion). Stage 9 boundary recurrence is the diagnostic but isn't
  conclusive — both produce shared boundaries.
- **Multiple overlapping nested inversions** in the same candidate.
  The pipeline detects them as `complex_inspect_manually` rather than
  resolving them; manual inspection of PC × window heatmaps is needed.

### Recommended use

Treat the nested classifier as a **filter and prioritization tool**:
flagged candidates deserve detailed inspection (4-panel diagnostic
plot, per-stratum dendrograms, marker development, follow-up tree
analysis). The headline output is "this candidate likely contains a
nested inversion at coordinates X-Y inside parent stratum Z," which
becomes the working hypothesis for downstream characterization.

For the paper, a confident `nested_inversion_strong` verdict
(all three primary methods agree, plus secondary support) is
publishable. `nested_inversion_likely` and weaker categories should be
phrased as "candidate" or "putative" until follow-up evidence accrues.

---

## Paper-claim templates

For a confidently detected nested inversion:

> "Conditional re-scanning within parent-arrangement strata identified
> a nested inversion candidate at LG28:15.5-15.8 Mb segregating within
> the HOM2 background of the parent inversion at LG28:15.115-18.005 Mb.
> The nested signal appeared on PC2 of the HOM2 stratum (mean
> silhouette 0.71 across windows 38-44), persisted under peel-filter
> validation (signal retained when HOM1 samples were excluded; lost
> when HOM2 samples were excluded), and showed elevated within-stratum
> Fst between putative sub-bands (mean Fst_AB = 0.18 inside the inner
> interval vs. 0.02 in flanking regions). Boundary positions were
> shared across all 28 putative carriers, distinguishing the signal
> from per-sample double-crossover events."

For a candidate that's borderline:

> "Conditional re-scanning identified a candidate inner interval at
> LG28:16.0-16.3 Mb appearing on PC2 of the HOM1 stratum (silhouette
> 0.58), but the signal weakened under peel-filter validation,
> consistent with possible family-LD contamination in the hatchery
> cohort. Long-read breakpoint validation will be required to confirm
> this candidate."

---

## File map

```
mgl_adapter/                          (existing, HANDOFFs 0-4)
trees/                                (HANDOFF 5)
fingerprints/                         (HANDOFF 6)
nested/                               (this handoff)
├── stratify_by_parent.R              (Stage 1)
├── method1_conditional_pca.R         (Stage 2)
├── method8_multi_pc_scan.R           (Stage 3, mostly visualization)
├── method9_peel.R                    (Stage 4)
├── method2_residualize.R             (Stage 5)
├── method3_conditional_cramers.R     (Stage 6)
├── method4_hierarchical.R            (Stage 7)
├── method10_af_contrast.R            (Stage 8)
├── boundary_recurrence_test.R        (Stage 9)
├── classify_nested.R                 (Stage 11)
├── plot_4panel_diagnostic.R
├── plot_pc_x_window_heatmap.R
├── run_nested_for_candidate.sh       (driver)
└── nested_panel.js                   (atlas-side rendering, future)

specs/
└── HANDOFF_7_nested_inversion.md     (this document)
```

---

## What you can ignore

- **Method 5 (breakpoint evidence via DELLY/Manta)**: handled by your
  separate SV-calling pipeline. At 9× WGS, breakpoint-spanning evidence
  is weak. Reference but don't depend.
- **Cross-candidate nested-inversion comparison**: future work. Useful
  when many candidates exist to ask "do nested inversions cluster
  near specific genomic features?"
- **Pre-discovery scanning**: this handoff is post-discovery
  characterization. The upstream pipeline (D17 / triangle / HANDOFF 1)
  already identifies candidate inversions; we don't re-do that.

## Pointers to existing code

- HANDOFF 1 producer: `pca_<view>_<weighting>_<anchor>.json` per
  candidate; per-window cluster labels feed parent karyotype
  assignment.
- HANDOFF 5 (tree): re-callable per stratum via
  `--include_samples_only` + `--core_interval_*` flags (Stage 10
  integration).
- HANDOFF 6 (fingerprinter): per-sample recombinant carrier list
  feeds Stage 9 boundary disambiguation.
- `region_stats_dispatcher.R`: `get_region_stats()` is callable per
  stratum by passing only that stratum's samples in `groups` — useful
  for Method 10 AF contrast.

## External tools required

- R packages: `data.table`, `cluster` (for silhouette),
  `mclust` or `cluster::pam` (for K=3 clustering), `ape` (for
  dendrogram), already-listed packages from earlier handoffs.
- No external binaries beyond what HANDOFFs 1-6 already use.

---

## Validation checks for LG28

For LG28:15.115-18.005 (the known-positive control):

1. **Phase 1 baseline**: parent karyotype assignment should match
   existing biallelic pipeline (60 HOM1 / 106 HET / 60 HOM2). Strata
   sizes all pass `min_stratum_size` threshold.

2. **Method 1 negative result**: if LG28 is a simple inversion (not
   nested), no inner intervals should be detected. K=3 silhouette
   per stratum × window × PC should be uniformly low (<0.5). This is
   the expected outcome for the LG28 control.

3. **Method 9 peel consistency**: any signals detected in Method 1
   should be checked across peel runs. For a true simple inversion,
   no inner-interval signal exists in any peel.

4. **Method 4 dendrogram**: at K=6, the cut should approximately
   double-up parent karyotype classes (HOM1 splits into two
   roughly-equal subgroups by random rather than meaningful axis;
   same for HOM2). No asymmetric 3-way split within one class.

5. **Final classification**: `simple_inversion` for LG28.

If LG28 returns `nested_inversion_likely` or stronger, investigate —
either a real undiscovered nested arrangement (interesting!) or a
family-LD artifact (peel method should have caught it; if it didn't,
threshold tuning is needed).
