# HANDOFF 8 — Adaptive interval dosage clustering

**Goal**: produce per-chromosome and per-candidate dosage-profile plots
where curves are grouped by **adaptive dosage clusters defined from the
data itself**, not by population labels or PCA bands. Output is a
self-defining visualization + classification tool that complements the
PCA / heatmap / tree / fingerprinter / nested-detector pipeline.

**Status**: not started. Builds on HANDOFF 1 (filtered Beagle and
sample dosage matrix) and HANDOFFs 6-7 conceptually (this provides a
data-driven view that PCA assumes when it picks K=3).

**Audience**: a fresh chat where Claude implements the dosage-clustering
pipeline.

---

## What you're building

Two outputs per scope:

### Per-chromosome (whole-chromosome scan)
Like Stickleback Fig. 2: one curve per cluster across each chromosome,
showing the average genotype dosage across genomic position. Curves
identify regions where samples diverge into distinct dosage groups
(candidate inversions, copy number variants, ancestry blocks, etc.).

### Per-candidate (interval-focused)
Inside a candidate inversion, finer-resolution dosage curves with
adaptive K selection. Detects whether the candidate has 3 (simple),
5-6 (compound/nested), or other structure — without imposing K=3 as
PCA does.

The visualization is **self-defining**: cluster labels are derived
from the data each time, not imported from population metadata or
PCA results. Concordance with PCA bands is computed as a downstream
check, not an input.

---

## What this handoff IS NOT

- **NOT a population-genetics curve** like the Stickleback figure where
  curves are colored by population (North Carolina, etc.). Those
  curves test pop-structure hypotheses; ours test dosage-cluster
  hypotheses defined by the data.
- **NOT a replacement for PCA bands.** PCA bands come from HANDOFF 1's
  local PCA and assume K=3. Dosage clusters are independently derived
  and may agree or disagree with PCA bands. Comparing them is the
  diagnostic.
- **NOT a hypothesis test.** This is a visualization + structure-
  inference tool that feeds downstream tests (HANDOFFs 5-7).

---

## The conceptual core

> **For each interval, let the data choose the best number of dosage
> clusters. Cluster samples by the shape of dosage across the interval,
> not just mean dosage.**

A fish is represented by a **dosage profile vector** across the
interval:

```
fish_001 = [0.12, 0.15, 0.18, 0.80, 0.84, 0.82, 0.20, 0.18]
```

Not just `mean(dosage_001) = 0.41`.

Because nested inversions and double crossovers are about **where** the
dosage changes along the interval, not just average dosage.

A simple inversion produces three profile shapes:
```
HOM1: [low, low, low, low, low]
HET:  [mid, mid, mid, mid, mid]
HOM2: [high, high, high, high, high]
```

A nested inversion produces additional shapes inside one parent
arrangement:
```
HOM2.A: [high, high, high, high, high]
HOM2.B: [high, high, low,  low,  high]    ← nested HET inside
HOM2.C: [high, high, mid,  mid,  high]    ← nested HOM2 inside
```

Adaptive clustering finds these shapes without prior knowledge of how
many or what they look like.

---

## Pipeline architecture

```
                  ┌─────────────────────────────────┐
                  │ Beagle (filtered) for the chrom │
                  │ or candidate interval           │
                  └────────────┬────────────────────┘
                               │
                               ▼
                  ┌─────────────────────────────────┐
                  │ Build dosage matrix             │
                  │ samples × windows               │
                  │ (mean and median dosage         │
                  │  per window)                    │
                  └────────────┬────────────────────┘
                               │
                               ▼
                  ┌─────────────────────────────────┐
                  │ Window-level QC                 │
                  │  - missing > threshold          │
                  │  - low MAF                      │
                  │  - low variance                 │
                  │  - missingness bias             │
                  └────────────┬────────────────────┘
                               │
                               ▼
                  ┌─────────────────────────────────┐
                  │ Adaptive K selection            │
                  │  - test K = 1..K_max            │
                  │  - silhouette                   │
                  │  - bootstrap stability          │
                  │  - minimum cluster size         │
                  │  - spatial coherence            │
                  │  → pick smallest stable K       │
                  └────────────┬────────────────────┘
                               │
                               ▼
                  ┌─────────────────────────────────┐
                  │ Hierarchical refinement (opt.)  │
                  │  - within each cluster, test if │
                  │    it contains substructure     │
                  │  - recursively split until no   │
                  │    stable subcluster            │
                  └────────────┬────────────────────┘
                               │
                               ▼
                  ┌─────────────────────────────────┐
                  │ Per-cluster mean & median       │
                  │ dosage curves across interval   │
                  └────────────┬────────────────────┘
                               │
            ┌──────────────────┼──────────────────┐
            ▼                  ▼                  ▼
    ┌───────────────┐  ┌───────────────┐  ┌───────────────┐
    │ Panel A:      │  │ Panel B:      │  │ Panel C:      │
    │ dosage curves │  │ sample heatmap│  │ dendrogram    │
    │               │  │ ordered by    │  │ (hierarchical)│
    │               │  │ cluster       │  │               │
    └───────────────┘  └───────────────┘  └───────────────┘
                               │
                               ▼
                  ┌─────────────────────────────────┐
                  │ Panel D: concordance vs PCA     │
                  │ bands (table + ARI/Cramér's V)  │
                  └─────────────────────────────────┘
```

---

## Two scopes (per-chrom and per-candidate)

### Per-chromosome scope
- Window size: large (e.g., 10,000 SNPs / 2,500 SNP step — matches
  Stickleback Fig. 2's iDIG-style setup)
- Goal: show whole-chromosome dosage landscape; identify intervals
  where samples diverge into distinct dosage groups (candidate
  inversions or other structural events)
- Adaptive K typically reflects chromosome-wide population structure
  + a few inversion-driven groups (so K can be moderate, e.g. 4-8)

### Per-candidate scope
- Window size: small (e.g., 50 kb / 25 kb step — matches HANDOFFs
  5-7 default)
- Goal: characterize the structure of one candidate inversion
  interval; distinguish simple (K=3), nested (K=5-6), compound
  (K=6+), or noisy/family-LD (unstable K)
- Adaptive K should reveal the inversion's internal architecture
  cleanly

The same algorithm runs at both scopes; only window size changes.

---

## Stage 1: dosage matrix construction

### Input
- Filtered Beagle for the chromosome or candidate interval (from
  HANDOFF 1's view filter, default `bi_baseline` for paper figures)
- Sample list

### Per-window dosage

For each window covering the requested scope:

```r
# For each sample, compute window-level dosage
# Two summary statistics per window per sample:
window_mean_dosage   <- mean(per_marker_dosage_in_window)
window_median_dosage <- median(per_marker_dosage_in_window)
```

Both `mean` and `median` are computed because:
- `mean` is sensitive to outlier markers (paralogs, mappability
  artifacts, recent mutations) — useful when you want amplification
- `median` is robust — useful as the default cluster input

By default, **median is used for clustering**, mean for diagnostic
overlay. Configurable via `--summary_stat`.

### Output

A samples × windows matrix `D_med` (median) and `D_mean` (mean), each
row = one sample's dosage profile across the interval.

```r
D_med  <- compute_window_dosage(beagle, windows, stat = "median")
D_mean <- compute_window_dosage(beagle, windows, stat = "mean")
```

---

## Stage 1.5: marker polarity correction (NEW)

**Why this matters**: each Beagle row represents a pair (allele_a,
allele_b) and dosage is "expected count of allele_b." Which allele is
"a" vs "b" is set per-site by the cohort-count ranking convention
(MAJOR/MINOR1/MINOR2 — see SPEC_0 §1), but **the resulting per-marker
direction is not aligned with any biological axis**. Adjacent markers
inside an inversion may have inverted polarity relative to each other
just by chance. Without correction:

- Sample–sample similarity is robust (Pearson absorbs polarity flips
  via sign), so **discovery scans tolerate polarity issues**
- Per-cluster mean dosage curves are messy (random flipping
  cancels out structure), so **interpretable curve plots require
  correction**
- Per-cluster mean curves with corrected polarity make the inversion
  band assignments visually obvious (low dosage = arrangement A
  consistently, high = arrangement B)

### The four modes

The pipeline supports four polarity-handling modes, configurable via
`--polarity_mode`:

| Mode | What it does | When to use |
|---|---|---|
| `raw_scan` | No correction; use \|correlation\| or genotype distance for similarity | First-pass discovery; before any group hypothesis exists |
| `polarity_corrected_outer` | Flip markers so they align with the major (outer) inversion contrast | After outer candidate is identified; cleanest plots for simple-inversion cases |
| `polarity_corrected_inner` | Flip markers so they align with the inner contrast within one outer stratum | After nested architecture is suspected; cleanest plots inside the inner-event region |
| `hierarchical_u_v` | Two-axis correction: each marker assigned to outer (u) or inner (v) axis based on which contrast it correlates with most | The publication-grade mode for nested cases; produces two clean matrices (outer-oriented + inner-oriented) |

### Mode 1: `raw_scan` (no correction)

Default for first-pass discovery. Sample–sample similarity computed
as **absolute Pearson correlation** or normalized L1 distance:

```r
S <- abs(cor(t(D)))
# or: S <- 1 - as.matrix(dist(D, method = "manhattan")) / (2 * ncol(D))
```

Both are polarity-invariant: two markers with opposite polarity but
the same biological signal contribute equally to the similarity.

The cluster curves WILL look messy in this mode because mean dosage
across randomly-polarized markers averages out. Use this mode for
discovering structure, not for figures.

### Mode 2: `polarity_corrected_outer`

After identifying the outer candidate (from upstream local PCA / D17
or Stage 3 adaptive K), correct each marker's polarity to align with
the outer contrast.

The outer contrast is defined by **the average dosage difference
between two reference outer groups**. Choose two contrasting groups
(e.g., HOM1 vs HOM2 from the candidate's local PCA bands):

```r
# Step A: define outer reference groups from upstream PCA bands or
# Stage 3 adaptive K assignment
outer_ref_pos <- which(parent_kary == "HOM2")    # samples in arrangement B
outer_ref_neg <- which(parent_kary == "HOM1")    # samples in arrangement A

# Step B: per marker, compute the contrast and decide whether to flip
contrast_outer <- numeric(n_markers)
for (m in seq_len(n_markers)) {
  pos_mean <- mean(D[outer_ref_pos, m], na.rm = TRUE)
  neg_mean <- mean(D[outer_ref_neg, m], na.rm = TRUE)
  contrast_outer[m] <- pos_mean - neg_mean
}

# Step C: flip markers where the contrast is negative
flip_outer <- contrast_outer < 0
D_corrected_outer <- D
D_corrected_outer[, flip_outer] <- 2 - D[, flip_outer]   # flip dosage 0↔2, 1 stays 1
```

After this, **all markers contribute in the same direction to the
outer contrast**: HOM2 samples have systematically higher dosage,
HOM1 systematically lower, HET in between. Mean curves per cluster
become clean.

This is the right mode for **simple inversion** plots (LG28-style). The
caveat: markers that are noise / unrelated to the inversion get
flipped randomly and just add noise to the curves; they don't
introduce systematic bias.

### Mode 3: `polarity_corrected_inner` — ASK QUENTIN FOR DETAILS

Same idea as Mode 2, but for the inner contrast within one outer
stratum. Requires:
- Outer candidate identified
- Outer groups assigned per sample (from Mode 2's reference)
- Inner candidate suspected (from HANDOFF 9 contingency test or
  Stage 4 hierarchical refinement)
- Inner reference groups defined within one outer stratum (e.g., HOM2.A
  vs HOM2.B from the suspected nested inversion)

```r
# Define inner reference groups (samples within one outer stratum,
# split by suspected inner band)
inner_ref_pos <- which(parent_kary == "HOM2" & inner_band == "B")
inner_ref_neg <- which(parent_kary == "HOM2" & inner_band == "A")

# Per marker, compute inner contrast and flip
contrast_inner <- numeric(n_markers)
for (m in seq_len(n_markers)) {
  pos_mean <- mean(D[inner_ref_pos, m], na.rm = TRUE)
  neg_mean <- mean(D[inner_ref_neg, m], na.rm = TRUE)
  contrast_inner[m] <- pos_mean - neg_mean
}

flip_inner <- contrast_inner < 0
D_corrected_inner <- D
D_corrected_inner[, flip_inner] <- 2 - D[, flip_inner]
```

**OPEN QUESTION FOR QUENTIN**: how to handle the choice between Mode 2
and Mode 3 when both are applicable?

A naive approach: if Mode 2 is computed and the inner inversion
exists in only one outer stratum, then within that stratum the
inner contrast competes with the outer contrast at the per-marker
level. A marker in the inner-event region could correlate with
both axes, and Mode 2's flip + Mode 3's flip might conflict.

Plausible policies (Quentin to decide):
- **(a)** Apply Mode 2 globally first, then Mode 3 only inside the
  inner interval and only for samples in the relevant outer stratum.
  Two corrected matrices for two regions of the genome.
- **(b)** Apply Mode 3 only inside the inner interval (windows
  inner_left:inner_right) and Mode 2 elsewhere; concatenate.
- **(c)** Use Mode 4 (hierarchical_u_v) instead, which formalizes
  this question.

Implementation defers this choice; Mode 3 produces a corrected matrix
restricted to a user-specified interval and stratum, and the user
decides how to combine it with Mode 2's output.

### Mode 4: `hierarchical_u_v` — ASK QUENTIN FOR DETAILS

The cleanest nested-case mode. Each marker is assigned to one of two
axes based on which contrast it correlates with most strongly:

```r
# Per marker
r_u <- cor(D[, m], outer_contrast_score)     # correlation with outer axis
r_v <- cor(D[, m], inner_contrast_score)     # correlation with inner axis

if (abs(r_u) > abs(r_v)) {
  marker_axis[m] <- "u"
  flip[m] <- r_u < 0
} else if (abs(r_v) > abs(r_u)) {
  marker_axis[m] <- "v"
  flip[m] <- r_v < 0
} else {
  marker_axis[m] <- "noise"   # neither axis loads strongly
}

# Build two matrices
D_outer_layer <- D[, marker_axis == "u"]
D_outer_layer[, flip[marker_axis == "u"]] <- 2 - D_outer_layer[, ...]

D_inner_layer <- D[, marker_axis == "v"]
D_inner_layer[, flip[marker_axis == "v"]] <- 2 - D_inner_layer[, ...]
```

Two clean matrices: one shows the outer arrangement contrast across
all markers that load on the outer axis; the other shows the inner
arrangement contrast across markers that load on the inner axis.

**OPEN QUESTIONS FOR QUENTIN**:
1. **How to define `outer_contrast_score` and `inner_contrast_score`?**
   - Option A: PC1 score from the outer PCA, PC2 from the inner PCA
   - Option B: difference of band means (e.g., HOM2_mean - HOM1_mean
     for outer; HOM2.B_mean - HOM2.A_mean for inner)
   - Option C: explicit user-specified contrast vectors
   The choice affects how robust the assignment is, especially for
   markers near the breakpoints.

2. **What threshold for `|r_u| ≈ |r_v|`?**
   When a marker correlates roughly equally with both axes, how to
   handle? Options:
   - Assign to the higher one regardless (current pseudocode)
   - Drop the marker as ambiguous
   - Assign to both layers with reduced weight
   - Use a deadband: |r_u - r_v| > 0.1 to assign decisively, else drop

3. **Marker weighting beyond binary axis assignment?**
   A marker with r_u = 0.7 and r_v = 0.3 contributes more cleanly to
   the outer layer than a marker with r_u = 0.4 and r_v = 0.35. Should
   markers be weighted by their axis-specificity in the cluster
   computations, not just binary-assigned?

4. **What about markers with low correlation on both axes (noise)?**
   Drop them entirely, or include them in a third category that
   contributes uniform noise to both layers?

For the first implementation, a reasonable default is:
- Threshold |r_u - r_v| > 0.1 to assign decisively
- Drop ambiguous markers (within 0.1 of each other)
- Drop markers with max(|r_u|, |r_v|) < 0.2 as noise
- No weighting beyond binary assignment

But these defaults should be tuned empirically with Quentin's input
on what works for the *C. gariepinus* data.

### When to apply each mode

```
First-pass discovery scan
   │
   ▼
─── Mode 1 (raw_scan, abs correlation) ───
   │
   ▼
Did the scan find structured windows?
   │
   ├── No → stop here, no inversion detected
   │
   └── Yes → outer candidate identified
        │
        ▼
─── Mode 2 (polarity_corrected_outer) ───
        │
        ▼
   Are there >3 dosage groups inside the candidate?
        │
        ├── No → simple inversion; Mode 2 plot is the paper figure
        │
        └── Yes → nested suspected
             │
             ▼
        ─── Mode 3 or Mode 4 (hierarchical_u_v) ───
             │
             ▼
        Two-layer plot is the paper figure
```

The pipeline runs Mode 1 always, Mode 2 conditionally on detected
structure, Mode 3/4 conditionally on detected nesting. Each mode's
output is saved for cross-validation between them.

### Output

```
polarity/
├── flip_decisions_outer.tsv          # per marker, was it flipped under Mode 2?
├── flip_decisions_inner.tsv          # per marker, Mode 3
├── flip_decisions_hierarchical.tsv   # per marker, axis (u/v/noise) and flip
├── D_corrected_outer.bin             # corrected dosage matrix, Mode 2
├── D_corrected_inner.bin             # corrected dosage matrix, Mode 3
├── D_outer_layer.bin                 # u-axis matrix, Mode 4
└── D_inner_layer.bin                 # v-axis matrix, Mode 4
```

These corrected matrices feed into Stage 2 onwards, replacing the raw
`D` from Stage 1.

### Important caveat (don't over-correct early)

Polarity correction is a **conditional** step: it requires reference
groups, and reference groups come from upstream analysis. If you use
suspected inner groups to correct polarity before confirming the
inner groups are real, you can manufacture a clean-looking pattern
that's actually just confirmation bias.

The safe pattern:
1. Mode 1 first to discover structure
2. Mode 2 only after outer candidate is confirmed by independent
   methods (PCA, dosage similarity matrix from HANDOFF 9)
3. Mode 3/4 only after nested architecture is confirmed by ≥2
   independent methods (HANDOFFs 7, 9 cross-validation)
4. Validate the corrected curves against independent summaries: π,
   dXY, Fst, private alleles per group should also separate the
   groups, not just the corrected dosage

This protects against the "I corrected polarity and got a clean
nested signal" that turns out to be circular.

---

## Stage 2: window-level QC

Before clustering, drop windows that introduce noise:

| Check | Default threshold | Rationale |
|---|---|---|
| Missing rate per window | < 0.20 | Beagle GLs may be 1/3-1/3-1/3 if no reads; high missingness destabilizes clustering |
| Marker-level MAF | ≥ 0.02 | Very rare alleles add noise to per-window dosage |
| Window-level variance | top 95% retained | Drop windows with near-zero variance across samples (uninformative) |
| Missingness-vs-PC1 correlation | |r| < 0.3 | Drop windows where missingness correlates strongly with population structure (likely batch effects) |

```r
# Window-level QC
qc_pass <- apply(D_med, 2, function(col) {
  miss_rate <- mean(is.na(col))
  variance  <- var(col, na.rm = TRUE)
  miss_rate < 0.20 & variance > variance_threshold
})

D_med  <- D_med[, qc_pass, drop = FALSE]
D_mean <- D_mean[, qc_pass, drop = FALSE]
windows <- windows[qc_pass]
```

Output: cleaned dosage matrix + QC log of dropped windows.

---

## Stage 3: adaptive K selection

For each scope (per-chrom or per-candidate), test K = 1 to K_max
(default `K_max = 6`) and select the smallest stable K.

### Per-K evaluation

For each K:

```r
# 1. Cluster (K-means; or hierarchical for complex shapes)
km <- kmeans(D_med, centers = K, nstart = 50)

# 2. Silhouette score
sil <- mean(cluster::silhouette(km$cluster, dist(D_med))[, 3])

# 3. Bootstrap stability
boot_stability <- bootstrap_cluster_stability(D_med, K, n_boot = 100,
                                                marker_subsample = 0.8)
# bootstrap_cluster_stability returns a value in [0, 1] reflecting how
# often samples cluster together across bootstrapped marker subsets

# 4. Minimum cluster size
min_size <- min(table(km$cluster))

# 5. Spatial coherence
# For each cluster, fit a smooth curve to its mean dosage profile
# and check whether the within-cluster variance around the curve is
# small relative to between-cluster variance
spatial_coh <- compute_spatial_coherence(D_med, km$cluster)
# spatial_coh in [0, 1]: 1 = perfectly coherent dosage shapes per
# cluster; 0 = random within-cluster scatter
```

### Decision rule (key innovation)

**Pick the smallest K such that all of the following hold**:

1. `silhouette(K) > 0.4` (configurable; default 0.4)
2. `boot_stability(K) > 0.7` (default 0.7)
3. `min_size(K) >= max(5, 0.02 * n_samples)` (no tiny groups; floor 5)
4. `spatial_coh(K) > 0.5` (clusters have coherent dosage shapes)
5. The improvement of K vs K-1 in silhouette ≥ 0.05 (an extra cluster
   must actually help; default 0.05)

If multiple K values pass, **pick the smallest**. This guards against
overfitting (K=5 or K=6 may have slightly higher silhouette than K=3
just by adding noise-driven splits).

```r
adaptive_K <- function(D, K_max = 6, ...) {
  results <- lapply(1:K_max, function(K) {
    if (K == 1) return(list(K=1, silhouette=0, stability=1,
                            min_size=nrow(D), spatial_coh=0,
                            passes=TRUE))   # K=1 is always valid baseline
    km <- kmeans(D, centers = K, nstart = 50)
    list(
      K = K,
      silhouette  = compute_silhouette(km, D),
      stability   = bootstrap_cluster_stability(D, K),
      min_size    = min(table(km$cluster)),
      spatial_coh = compute_spatial_coherence(D, km$cluster),
      cluster     = km$cluster
    )
  })

  # Apply decision rule
  for (res in results) {
    res$passes <- res$silhouette > 0.4 &
                  res$stability > 0.7 &
                  res$min_size >= max(5, 0.02 * nrow(D)) &
                  res$spatial_coh > 0.5
  }

  # Improvement check
  for (i in 2:length(results)) {
    if (results[[i]]$silhouette - results[[i-1]]$silhouette < 0.05) {
      results[[i]]$passes <- FALSE
    }
  }

  # Pick smallest K that passes
  passing_Ks <- which(sapply(results, function(r) r$passes))
  if (length(passing_Ks) == 0) return(list(K_chosen = 1, ...))   # no structure
  return(results[[min(passing_Ks)]])
}
```

### When K_chosen = 1

If no K passes, the candidate has **no detectable cluster structure**
above noise. Verdict: `no_structure` (uniform population, or signal too
weak). This is a meaningful negative result; report it, don't
artificially force K=3.

---

## Stage 4: hierarchical refinement (optional, for nested detection)

Adaptive K detects the dominant structure. To detect nested structure
explicitly, refine recursively:

```r
hierarchical_dosage_cluster <- function(D, samples, depth = 0,
                                          max_depth = 3) {
  if (length(samples) < min_cluster_size_for_split) return(NULL)

  # Subset matrix to current sample set
  D_sub <- D[samples, , drop = FALSE]

  # Adaptive K on the subset
  result <- adaptive_K(D_sub)
  if (result$K_chosen == 1) return(NULL)   # no further structure

  # Record split
  current_split <- list(
    depth = depth,
    samples = samples,
    K = result$K_chosen,
    cluster = result$cluster
  )

  # Recursively refine each subcluster
  if (depth < max_depth) {
    for (k in seq_len(result$K_chosen)) {
      sub_samples <- samples[result$cluster == k]
      child_split <- hierarchical_dosage_cluster(D, sub_samples,
                                                   depth + 1, max_depth)
      current_split$children[[k]] <- child_split
    }
  }

  current_split
}
```

A simple inversion gives a **flat** hierarchy:
- Top: K=3 (HOM1, HET, HOM2)
- All three subclusters: K=1 (no further structure)

A nested inversion gives a **deep** hierarchy in one branch:
- Top: K=3 (HOM1, HET, HOM2)
- HOM1: K=1, HET: K=1
- HOM2: K=3 (HOM2.A, HOM2.B, HOM2.C — the nested arrangement)

This is the dosage-based version of HANDOFF 7's nested detector. The
two are independent — they should agree on real nested inversions and
each catches signals the other might miss. HANDOFF 7 uses local PCA
within strata; this uses dosage-shape clustering directly.

---

## Stage 5: per-cluster dosage curves

Once K is selected (and optionally hierarchy refined), compute the
**mean and median dosage curve per cluster** across the interval:

```r
# For each cluster, per window, mean and median across samples in cluster
curves <- list()
for (k in unique(cluster_labels)) {
  cluster_samples <- which(cluster_labels == k)
  curves[[paste0("cluster_", k)]] <- list(
    n_samples = length(cluster_samples),
    mean_curve   = colMeans(D_mean[cluster_samples, , drop = FALSE], na.rm = TRUE),
    median_curve = apply(D_med[cluster_samples, , drop = FALSE], 2, median, na.rm = TRUE),
    sd_curve     = apply(D_med[cluster_samples, , drop = FALSE], 2, sd, na.rm = TRUE)
  )
}
```

These curves are the **paper-grade output**: one curve per cluster,
plotted across the interval with confidence ribbons (mean ± 1 SD).

---

## Stage 5.5: pairwise cluster contrast and driver segments (NEW)

**The missing step**: once we have K clusters from Stage 3 (or
hierarchical refinement from Stage 4), we know *that* the clusters
exist but not *why*. This stage answers:

> Which part of the interval is responsible for separating each pair
> of clusters?

Without this stage, an 8-cluster result is descriptive but not
mechanistically interpretable. With this stage, each cluster pair gets
a **driver segment**: the genomic interval where their dosage curves
diverge most strongly.

### The conceptual core

For two clusters A and B, the per-position contrast is:

```
Δ_AB(x) = mean_dosage_A(x) - mean_dosage_B(x)
```

Plotted across the interval, this curve tells you *where* A and B
differ. Three diagnostic shapes:

| Δ shape | Interpretation |
|---|---|
| High across whole interval (flat top) | Clusters differ by the **outer arrangement** |
| High only in the middle (single peak) | Clusters differ by an **inner / nested segment** |
| High only at one edge | Clusters differ by a **boundary / adjacent event** or local artifact |
| Weak everywhere | Clusters are not really distinguished by dosage; one may be noise |

The full output is a **K × K matrix of contrast curves**, one per
cluster pair, classified by shape into driver segments.

### Stage 5.5a — pairwise contrast curves

For each pair of clusters (A, B):

```r
compute_pairwise_contrast <- function(D, cluster_labels, A, B) {
  samples_A <- which(cluster_labels == A)
  samples_B <- which(cluster_labels == B)
  if (length(samples_A) < 3 || length(samples_B) < 3) return(NULL)

  delta <- numeric(ncol(D))
  effect_size <- numeric(ncol(D))

  for (m in seq_len(ncol(D))) {
    a_vals <- D[samples_A, m]
    b_vals <- D[samples_B, m]
    a_vals <- a_vals[!is.na(a_vals)]
    b_vals <- b_vals[!is.na(b_vals)]
    if (length(a_vals) < 2 || length(b_vals) < 2) {
      delta[m] <- NA
      effect_size[m] <- NA
      next
    }

    delta[m] <- mean(a_vals) - mean(b_vals)
    pooled_sd <- sqrt(((length(a_vals) - 1) * var(a_vals) +
                        (length(b_vals) - 1) * var(b_vals)) /
                       (length(a_vals) + length(b_vals) - 2))
    effect_size[m] <- delta[m] / max(pooled_sd, 0.05)   # floor SD to avoid blowup
  }

  list(A = A, B = B, n_A = length(samples_A), n_B = length(samples_B),
       delta = delta, effect_size = effect_size)
}

# Run for all pairs
n_K <- length(unique(cluster_labels))
pairs <- combn(unique(cluster_labels), 2, simplify = FALSE)
contrasts <- lapply(pairs, function(p) compute_pairwise_contrast(D, cluster_labels, p[1], p[2]))
```

Cohen's d (effect_size) normalizes the difference by within-group
variability. Default conventions:
- |d| > 0.8: large effect
- |d| > 0.5: medium effect (the **default driver threshold**)
- |d| > 0.2: small effect
- |d| < 0.2: no meaningful difference

### Stage 5.5b — smoothing the contrast curves

Per-marker effect sizes are noisy. Smooth across positions before
identifying driver segments:

```r
smooth_effect_size <- function(effect_size, marker_positions, bandwidth_bp = 100000) {
  # Loess smoothing in genomic space, not marker space
  fit <- loess(effect_size ~ marker_positions,
               span = min(bandwidth_bp / diff(range(marker_positions)), 1.0),
               na.action = na.exclude)
  predict(fit, marker_positions)
}
```

Bandwidth default 100 kb; configurable via `--contrast_smoothing_bp`.
For very dense SNP regions a smaller bandwidth (50 kb) gives sharper
boundaries; for sparse regions, larger (250 kb) reduces noise.

### Stage 5.5c — driver-segment identification

A driver segment for cluster pair (A, B) is a contiguous run of
positions where the smoothed |effect_size| exceeds threshold:

```r
identify_driver_segments <- function(smoothed_effect, marker_positions,
                                       threshold = 0.5, min_run_bp = 50000) {
  above <- abs(smoothed_effect) > threshold
  runs <- find_contiguous_runs(above)
  segments <- list()
  for (r in runs) {
    bp_start <- marker_positions[min(r)]
    bp_end <- marker_positions[max(r)]
    if (bp_end - bp_start < min_run_bp) next   # too short to count
    segments[[length(segments) + 1]] <- list(
      bp_start = bp_start,
      bp_end = bp_end,
      bp_width = bp_end - bp_start,
      max_effect = max(abs(smoothed_effect[r])),
      mean_effect = mean(abs(smoothed_effect[r]))
    )
  }
  segments
}
```

Default `threshold = 0.5` (medium effect) and `min_run_bp = 50000`
(50 kb). Configurable per-cohort.

### Stage 5.5d — contrast shape classification

For each cluster pair, classify the overall shape of the contrast
curve based on coverage of the candidate interval:

```r
classify_contrast_shape <- function(driver_segments, candidate_start, candidate_end) {
  if (length(driver_segments) == 0) return("weak_or_noise")

  total_driver_bp <- sum(sapply(driver_segments, function(s) s$bp_width))
  candidate_bp <- candidate_end - candidate_start
  coverage_fraction <- total_driver_bp / candidate_bp

  # Are driver segments concentrated in the middle, edges, or spread?
  segment_centers <- sapply(driver_segments,
                              function(s) (s$bp_start + s$bp_end) / 2)
  rel_positions <- (segment_centers - candidate_start) / candidate_bp

  if (coverage_fraction > 0.7) {
    return("outer_whole_interval")
  } else if (all(rel_positions > 0.25 & rel_positions < 0.75)) {
    return("inner_middle_only")
  } else if (all(rel_positions < 0.25) || all(rel_positions > 0.75)) {
    return("edge_or_adjacent")
  } else {
    return("complex_or_split_drivers")
  }
}
```

### Stage 5.5e — the cluster-pair driver matrix

The full output of Stage 5.5 is a table:

```
contrast_pair    n_A   n_B   shape                    driver_segments               max_effect
C1_vs_C2          60   106   outer_whole_interval    [15.1-18.0 Mb]                2.3
C1_vs_C3          60    60   outer_whole_interval    [15.1-18.0 Mb]                4.7
C2_vs_C3         106    60   outer_whole_interval    [15.1-18.0 Mb]                2.4
C3_vs_C4          25    35   inner_middle_only       [16.4-16.7 Mb]                3.1   ← nested signature
C1_vs_C4          60    35   complex_or_split        [15.1-18.0 Mb, 16.4-16.7 Mb]  4.9
C5_vs_C6           7     5   weak_or_noise            [ ]                          0.3
...
```

Reading this matrix, the user immediately sees:
- **C1, C2, C3 are the outer arrangements** (whole-interval contrasts)
- **C3 vs C4 is a nested split** (middle-only contrast) — C4 is the
  inner-event subcluster of C3
- **C5, C6 are noise** (weak contrasts)

This matrix is the bridge from "8 clusters exist" to "the architecture
is: outer K=3 with one inner K=2 nested inside C3."

### Stage 5.5f — leave-segment-out validation

When a contrast is classified as `inner_middle_only` for cluster pair
(A, B), validate by re-running clustering with the suspected driver
segment masked:

```r
validate_driver_via_loo <- function(D, marker_positions, cluster_labels,
                                       A, B, driver_segments) {
  # Mask markers in driver segments
  driver_marker_mask <- rep(FALSE, ncol(D))
  for (s in driver_segments) {
    driver_marker_mask <- driver_marker_mask |
      (marker_positions >= s$bp_start & marker_positions <= s$bp_end)
  }
  D_masked <- D[, !driver_marker_mask, drop = FALSE]

  # Re-run adaptive K on samples in clusters A and B only
  samples_AB <- which(cluster_labels %in% c(A, B))
  D_sub <- D_masked[samples_AB, , drop = FALSE]
  result_loo <- adaptive_K(D_sub)

  if (result_loo$K_chosen == 1) {
    return("driver_confirmed")    # cluster A vs B disappears without driver segment
  } else if (result_loo$K_chosen == 2) {
    return("driver_partial")      # A vs B persists; driver explains some but not all
  } else {
    return("driver_complex")      # masking changed structure unpredictably
  }
}
```

Three outcomes:

| LOO result | Meaning |
|---|---|
| `driver_confirmed` | Cluster A vs B disappears when driver segment is removed → driver fully explains separation |
| `driver_partial` | A vs B persists at lower K → driver is one contributor among several |
| `driver_complex` | Masking creates a different structure → manual inspection needed |

This is the cleanest test that the spec offers for the question "is
this cluster genuinely driven by this segment, or is the segment
correlated with broader structure?"

### Stage 5.5g — bimodality of effect-size distribution (optional, noisy)

A diagnostic that's been requested but flagged as **noisy / don't
over-interpret**: the distribution of effect sizes across positions
within a contrast can be tested for bimodality.

Idea: if the contrast is driven by a localized segment, effect sizes
should be **bimodal** — high in the driver region, low elsewhere. If
the contrast is broad, effect sizes should be unimodal (most positions
at moderate-to-high).

```r
test_bimodality <- function(smoothed_effect) {
  # Hartigan's dip test for unimodality (rejecting unimodality = bimodal)
  result <- diptest::dip.test(abs(smoothed_effect))
  list(dip_statistic = result$statistic,
       p_value = result$p.value,
       rejection = result$p.value < 0.05)
}
```

**Caveats** (be honest in the spec):
- Effect sizes within a contrast are spatially autocorrelated; the
  dip test assumes independence. p-values are unreliable.
- A bimodal distribution can arise from many causes besides nested
  inversions (paralog clusters, repeat-rich regions, sequencing
  artifacts).
- Better: just look at the smoothed effect-size curve directly; if it
  has clear peaks and valleys, that's the signal you want.

The bimodality test is **provided as an optional output** because the
user requested it, but the recommended primary diagnostic is the
shape-classification rule from Stage 5.5d which is more robust.

### Output

```
pairwise_contrasts/
├── all_pairs_contrast_curves.tsv       # per pair × position: delta, effect_size
├── all_pairs_smoothed.tsv              # smoothed effect_size per pair × position
├── driver_segments_per_pair.tsv        # driver segment table per pair
├── contrast_shape_classification.tsv   # one row per pair: shape verdict
├── leave_one_out_validation.tsv        # LOO outcome per pair w/ inner-middle shape
├── bimodality_diagnostics.tsv          # optional, with caveats
├── plot_contrast_matrix.pdf            # K × K grid of contrast curves
├── plot_driver_segments.pdf            # genome track with driver segments per pair
└── architecture_summary.json           # final architecture interpretation
```

The architecture summary integrates all pairwise results into a
high-level structure:

```json
"architecture_summary": {
  "n_clusters_total": 8,
  "outer_clusters": ["C1", "C2", "C3"],     // whole-interval drivers
  "inner_relationships": [
    {"parent_cluster": "C3", "inner_subclusters": ["C4"], "driver_segment": "16.4-16.7 Mb"}
  ],
  "edge_clusters": [],
  "noise_clusters": ["C5", "C6", "C7", "C8"],
  "verdict": "outer_inversion_with_one_nested_event_in_C3"
}
```

That JSON is the **mechanistic interpretation** of the cluster
landscape.

### Visualization

The Stage 5.5 paper figure: K × K grid of contrast curves, one per
cluster pair, with the driver segments highlighted as colored bands
underneath each curve.

```
        C1          C2          C3          C4          C5
C1   ────────   ─[wide]─   ─[wide]─   ─[wide+narrow]─  noise
C2              ────────   ─[wide]─   ─[wide+narrow]─  noise
C3                         ────────   ─[narrow]─       noise
C4                                    ────────         noise
C5                                                     ────
```

`[wide]` = whole-interval contrast (outer arrangement difference)
`[narrow]` = middle-only contrast (inner-event difference)
`[wide+narrow]` = both (cluster differs from another by both outer and
inner arrangement)
`noise` = weak/uninformative

The pattern of wide vs narrow vs both contrasts directly reveals
the architecture. For LG28 (simple inversion, no nesting), all
non-trivial pairs should show `wide` only.

### Stage 5.5h — per-candidate inner-interval table and genome-wide summary (NEW)

After Stages 5.5a-g identify the driver segments per cluster pair, two
roll-up reports give the per-candidate and cohort-wide views.

#### Why this stage exists (and what it deliberately doesn't try to do)

A clean approach to "find all the nested intervals" is to read off
contiguous-runs-above-threshold from the smoothed effect-size curves
(Stage 5.5c already does this). When a contrast has two separate
spikes inside a candidate, `find_contiguous_runs` returns two driver
segments. The shape classifier flags this as
`complex_or_split_drivers`. So multi-event detection is already
supported by the math; this stage just rolls up and reports.

**What this stage explicitly avoids**: KDE-based mode finding on
effect-size distributions, "peak detection" on noisy curves, or any
density-estimation method. The smoothed effect-size curve is already
a smoothing pass; second-order density operations on noisy genomic
data add noise dressed up as math. The contiguous-runs approach is
honest about what it can detect — runs of high effect — and that's
sufficient for the "how many inner intervals does this candidate
have?" question.

#### Per-candidate inner-interval roll-up

For each candidate that runs through Stage 5.5, produce a one-row
summary:

```r
build_candidate_inner_summary <- function(stage_5_5_results, candidate) {
  pairs <- stage_5_5_results$pairs
  candidate_bp <- candidate$end - candidate$start

  # Collect all driver segments classified as inner_middle_only or
  # complex_or_split_drivers (which contain inner-like spikes)
  inner_intervals <- list()
  for (p in pairs) {
    if (p$shape %in% c("inner_middle_only", "complex_or_split_drivers")) {
      for (seg in p$driver_segments) {
        rel_start <- (seg$bp_start - candidate$start) / candidate_bp
        rel_end <- (seg$bp_end - candidate$start) / candidate_bp
        # Keep only segments that are genuinely "inside" (not at edges)
        if (rel_start > 0.10 && rel_end < 0.90) {
          inner_intervals[[length(inner_intervals) + 1]] <- list(
            from_pair = paste(p$A, p$B, sep = "_vs_"),
            bp_start = seg$bp_start,
            bp_end = seg$bp_end,
            bp_width = seg$bp_width,
            max_effect = seg$max_effect,
            parent_outer_cluster = identify_parent_outer(p, stage_5_5_results)
          )
        }
      }
    }
  }

  # Merge overlapping intervals from different cluster pairs
  inner_intervals_merged <- merge_overlapping_intervals(inner_intervals,
                                                          merge_distance_bp = 100000)

  list(
    candidate_id = candidate$id,
    candidate_bp_start = candidate$start,
    candidate_bp_end = candidate$end,
    candidate_width_bp = candidate_bp,
    n_inner_intervals = length(inner_intervals_merged),
    inner_intervals = inner_intervals_merged,
    total_inner_bp = sum(sapply(inner_intervals_merged, function(s) s$bp_width)),
    pct_of_candidate = sum(sapply(inner_intervals_merged, function(s) s$bp_width)) / candidate_bp * 100
  )
}
```

The "merge overlapping intervals from different cluster pairs" step
matters: a single nested event will appear as a driver segment in
multiple cluster pairs (e.g., C3 vs C4, C4 vs C5, C3 vs C5 if both
C4 and C5 are inside C3). Merging avoids triple-counting. Default
merge distance: 100 kb (intervals within 100 kb of each other are
merged).

The output table:

```
candidate_id           candidate_width_bp   n_inner   inner_intervals                    total_inner_bp   pct_of_candidate
LG28_15.115_18.005     2890000              0         ─                                  0                 0.0
LG12_8.0_11.0          3000000              2         [9.10-9.30 Mb, 10.20-10.50 Mb]    500000            16.7
LG07_22.0_24.5         2500000              1         [23.40-23.80 Mb]                  400000            16.0
LG21_5.5_9.0           3500000              3         [6.20-6.40, 7.10-7.30, 8.00-8.30] 700000            20.0
...
```

The `n_inner` column directly answers "how many nested intervals does
this candidate have?" without any KDE / mode detection.

#### Genome-wide architecture summary

Across all candidates analyzed, count and tabulate:

```r
genome_wide_summary <- function(per_candidate_summaries) {
  list(
    n_candidates_total      = length(per_candidate_summaries),
    n_simple_inversion      = sum(sapply(s, function(c) c$n_inner == 0)),
    n_with_one_inner        = sum(sapply(s, function(c) c$n_inner == 1)),
    n_with_two_inner        = sum(sapply(s, function(c) c$n_inner == 2)),
    n_with_three_or_more    = sum(sapply(s, function(c) c$n_inner >= 3)),
    n_with_any_inner        = sum(sapply(s, function(c) c$n_inner >= 1)),

    pct_nested              = mean(sapply(s, function(c) c$n_inner >= 1)) * 100,
    pct_complex             = mean(sapply(s, function(c) c$n_inner >= 2)) * 100,

    median_candidate_width  = median(sapply(s, function(c) c$candidate_width_bp)),
    median_inner_width      = median(unlist(lapply(s, function(c)
                                  sapply(c$inner_intervals, function(i) i$bp_width)))),

    median_inner_pct        = median(sapply(s, function(c)
                                  if (c$n_inner >= 1) c$pct_of_candidate else NA),
                                na.rm = TRUE),

    distribution_inner_count = table(sapply(s, function(c) c$n_inner))
  )
}
```

Output JSON:

```json
"genome_wide_architecture_summary.json":
{
  "n_candidates_total": 32,
  "n_simple_inversion": 24,
  "n_with_one_inner": 5,
  "n_with_two_inner": 2,
  "n_with_three_or_more": 1,
  "n_with_any_inner": 8,

  "pct_nested": 25.0,
  "pct_complex": 9.4,

  "median_candidate_width_bp": 2400000,
  "median_inner_width_bp": 380000,
  "median_inner_pct_of_candidate": 14.2,

  "distribution_inner_count": {"0": 24, "1": 5, "2": 2, "3": 1},

  "per_candidate_table_path": "candidate_inner_summary.tsv",

  "produced_at": "2026-05-10T18:30:00Z"
}
```

That JSON is the manuscript-grade summary: "Of 32 inversion candidates
in *C. gariepinus*, 24 (75%) were simple and 8 (25%) showed nested
architecture, with 3 candidates containing two or more nested events.
Median candidate width was 2.4 Mb; median nested-interval width was
380 kb (14% of candidate width)."

#### Output files

```
pairwise_contrasts/
├── (existing files from Stages 5.5a-g)
├── candidate_inner_summary.tsv             # Stage 5.5h per-candidate roll-up
├── genome_wide_architecture_summary.json   # Stage 5.5h cohort summary
├── genome_wide_architecture_summary.tsv    # same data as TSV
└── plot_genome_wide_architecture.pdf       # bar chart: simple vs nested counts
```

#### Honest framing

This stage is **counting and reporting**, not detection. The detection
happened in Stages 5.5a-g via the smoothed-effect contiguous-runs
approach. If the upstream stages miss an inner event (e.g., because
the effect size is just below threshold), this stage won't recover it.
Tuning the upstream `threshold` and `min_run_bp` parameters affects
what shows up here.

For the LG28 negative-control case: per-candidate row should show
`n_inner = 0`; genome-wide summary's `pct_nested` should be ≈0% if all
analyzed candidates are simple. Any non-zero count here, when LG28 is
the only candidate analyzed, indicates threshold tuning is needed.

### How this integrates with the rest of HANDOFF 8

| Stage | Question answered |
|---|---|
| Stage 3 | How many clusters are there? |
| Stage 4 | Are clusters hierarchically organized (recursive K)? |
| Stage 5 | What does each cluster's mean dosage curve look like? |
| **Stage 5.5** | **Which genomic intervals separate each cluster pair?** |
| Stage 6 | Do clusters match PCA bands? |
| Stage 8 | What's the overall architecture verdict? |

Stage 5.5 is the **mechanistic** stage that turns descriptive cluster
labels into causal architectural claims. It feeds Stage 8's
classification with explicit driver-segment evidence.

### Recommended workflow

1. Run Stages 1-5 to get clusters + per-cluster curves
2. Run Stage 5.5 to identify driver segments and contrast shapes
3. Read the architecture_summary.json for the high-level verdict
4. Validate inner-middle drivers with Stage 5.5f leave-one-out
5. Cross-validate with HANDOFFs 7 and 9 — driver segments from this
   stage should match the inner intervals identified independently

When all three methods (HANDOFF 8 driver segments, HANDOFF 7
conditional PCA inner intervals, HANDOFF 9 contingency-table inner
intervals) agree on the inner-event coordinates, the nested-inversion
claim is paper-grade.

---

## Stage 6: concordance with PCA bands (downstream check)

Compute the agreement between dosage clusters and PCA bands from
HANDOFF 1 (or the existing biallelic local-PCA pipeline):

```r
pca_bands <- read_band_labels("pca_results/pca_bi_baseline_*.json",
                                candidate_id)
dosage_clusters <- cluster_labels  # from Stage 3

# Contingency table
agreement_table <- table(dosage = dosage_clusters, pca = pca_bands)

# ARI
ari <- mclust::adjustedRandIndex(dosage_clusters, pca_bands)

# Cramér's V
cv <- cramers_v(agreement_table)
```

### Interpretation

| ARI | Interpretation |
|---|---|
| > 0.8 | Dosage clusters and PCA bands agree → simple inversion or compound structure that both methods see consistently |
| 0.5-0.8 | Partial agreement → likely the same major structure, but dosage clustering finds finer subdivisions or different cluster boundaries |
| < 0.5 | Disagreement → either dosage method finds extra structure PCA missed, or one method is noisy. Inspect manually. |

### When dosage finds K > PCA's K=3

This is the **interesting case**. Dosage clusters split one PCA band
into sub-bands → suggests:
- Nested inversion (HANDOFF 7 should agree)
- Family LD substructure (HANDOFF 7 peel filter should reveal)
- Local sub-arrangement that's smaller than the PCA-detected
  candidate

Cross-reference with HANDOFF 7's verdict.

### When dosage finds K = 2 where PCA finds K = 3

This is **rare** but happens when HET samples have intermediate
dosage profiles that K-means assigns to one of the homozygous bands
(because dosage-profile distance is smaller from HET to one HOM than
to the other HOM, or because HET samples have heterogeneous shapes).
Flag for inspection; usually HET samples should form their own cluster
unless they're truly bimodal in dosage shape.

---

## Stage 7: visualization

### Panel A: dosage curves
One curve per dosage cluster, plotted across the interval (per-chrom
or per-candidate). Y-axis: average genotype dosage [0, 1]. X-axis:
chromosome position (Mb).

```
Average genotype
 1.0 │              ╭─────╮
     │     ╭───────╯       ╰────────╮
 0.5 │────╯                          ╰────────  ← cluster 2 (HET)
     │
 0.0 │────────────────────────────────────────  ← cluster 1 (HOM1)
     ├────────────────────────────────────────►
     0   50   100   150   200   250   300 (kb)
```

For per-chromosome scope, this is the Stickleback Fig. 2 style plot
but with adaptive dosage clusters instead of populations.

### Panel B: sample heatmap ordered by cluster
Samples × windows heatmap with rows ordered by adaptive cluster.
Visualizes the underlying data that produced the curves.

### Panel C: dendrogram
Hierarchical clustering tree, colored by cluster assignment. Shows
the relationships between clusters and any nested substructure from
Stage 4.

### Panel D: agreement table
Confusion matrix of dosage cluster × PCA band, with ARI and Cramér's
V annotated.

This 4-panel layout per candidate is the paper figure: data-defined
curves (A), the underlying matrix (B), the structure (C), and
cross-validation (D).

---

## Stage 7.5: synchronized scrubbing track with HANDOFF 10 (NEW)

When this handoff runs in atlas mode (live exploration rather than
offline analysis), the per-cluster dosage curves and the interactive
similarity matrix panel (HANDOFF 10) share a common genome cursor.
A synchronized scrubbing track ties them together with scale-change
hints.

### What it looks like

```
┌─ Dosage curves (HANDOFF 8) ──────────────────────────────────────┐
│ dosage                                                           │
│   2.0 │      ╭─ cluster A (HOM2)      [cursor here]              │
│       │     ╱                                                    │
│   1.0 │  ──╱──── cluster B (HET)                                  │
│       │  ╱                                                       │
│   0.0 │─╯──────── cluster C (HOM1)                                │
│       └────────────────────────────────────────────────►         │
│       15.0      15.5      16.0      16.5      17.0      17.5     │
└──────────────────────────────────────────────────────────────────┘
        ▲                                                  ▲
        │ shared genome cursor                             │
        ▼                                                  ▼
┌─ Scale-suggestion track ─────────────────────────────────────────┐
│ K_blocks per scale:                                              │
│   100 kb │░░░░░▒▒▒▓▓▒▒▒▒░░░░░░░░░░░ │                           │
│   250 kb │░░░░▓▓▓▓▓▓▓▓▓▒▒░░░░░░░░░░ │  <- recommended at cursor  │
│   500 kb │░░░▓▓▓▓▓▓▓▓▓▓▓▒░░░░░░░░░░ │                           │
│     1 Mb │░░░▓▓▓▓▓▓▓▓▓▓▓▓▓░░░░░░░░░ │                           │
│           K=1 ░  K=3 ▓  K=4+ ▓                                   │
│           silhouette: low░ high▓                                 │
└──────────────────────────────────────────────────────────────────┘
        ▲                                                  ▲
        │                                                  │
        ▼                                                  ▼
┌─ Similarity matrix panel (HANDOFF 10) ───────────────────────────┐
│ [Matrix N × N at current window, current scale]                  │
└──────────────────────────────────────────────────────────────────┘
```

### Scale-suggestion track logic

The middle track shows, for each scale, where structured windows
exist along the genome. It pre-computes (server-side, once) per-scale
**block-detection summaries** for the chromosome:

```r
# Per scale, per window-position, save K_blocks and silhouette
for (scale in c(100000, 250000, 500000, 1000000)) {
  for (wpos in seq(chrom_start, chrom_end, by = scale / 4)) {
    sim_mat <- compute_similarity(chrom_data, wpos, wpos + scale)
    blocks <- detect_blocks(sim_mat)
    summary[scale][wpos] <- list(K = blocks$K, sil = blocks$silhouette)
  }
}
saveRDS(summary, "atlas_data/scale_suggestion/<chrom>.rds")
```

This is fast (~1 second per chromosome at a few scales) and produces
~100 kB of metadata per chromosome. Loaded once on chromosome entry,
not per scrub event.

### Which scale to recommend

At the current cursor position, the panel highlights the scale where
the silhouette × K_blocks signal is strongest:

```javascript
function recommendedScaleAt(cursorPos) {
  const candidates = [100000, 250000, 500000, 1000000];
  let bestScore = 0, bestScale = 250000;
  for (const scale of candidates) {
    const summary = scaleSuggestionData[scale];
    const wpos = nearestWindowPos(summary, cursorPos);
    const score = (summary[wpos].K - 1) * summary[wpos].silhouette;
    if (score > bestScore) {
      bestScore = score;
      bestScale = scale;
    }
  }
  return bestScale;
}
```

The recommendation is **a hint**, not auto-applied. The user can
override; the dropdown shows a small ★ next to the recommended scale.

### Hand-off rule for scale changes

When moving across the genome:
- **Outside candidates** (K=1 at all scales): default to 1 Mb (coarse,
  fast)
- **Approaching a candidate**: 500 kb often shows boundaries clearly
- **Inside outer-only stretches** (K=3): 250 kb or 500 kb
- **Inside putative inner regions** (K≥4): switch to 100 kb or 250 kb
  for sharper boundary detection

The scale-suggestion track makes this visually obvious: the user sees
a "high signal" band light up at certain scales over certain regions
and can click directly on the recommended scale.

### Sync between dosage curves and similarity matrix

The shared cursor position (from HANDOFF 2's shared rendering state)
drives both panels. When the user drags the cursor in either panel,
the other follows.

What's shown at each cursor position:
- **Dosage curves panel**: vertical line at cursor position; current-
  window cluster colors shown alongside the curves
- **Similarity matrix panel**: the matrix at the current window, at
  the current scale, with the current polarity mode

The dosage curves panel is the "structure across genome" view; the
similarity matrix panel is the "structure at this window" view. Both
update together; the scale-suggestion track in between tells the user
when finer or coarser detail would help.

### Note on offline / non-atlas use

This stage applies only when HANDOFF 8 runs as part of the live
atlas. For offline per-candidate analysis (Stages 1-7), no scrubbing
or scale recommendation is needed — the user picks one scale up
front via `--window_size_bp` and the analysis runs to completion.

The scale-suggestion track is a separate **atlas data product**
generated once per chromosome and is independent of the offline
analysis pipeline.

---

## Stage 8: classification

Combine adaptive K + hierarchy + concordance into a verdict:

```r
classify_dosage_structure <- function(adaptive_result, hierarchy, concordance) {
  K <- adaptive_result$K_chosen
  has_nested <- any(sapply(hierarchy$children, function(c) !is.null(c)))

  if (K == 1) return("no_structure")
  if (K == 2) return("biallelic_two_arrangement")
  if (K == 3 && !has_nested) return("simple_inversion_dosage")
  if (K == 3 && has_nested) return("simple_inversion_with_nested_substructure")
  if (K %in% c(5, 6) && has_nested) return("compound_or_nested_inversion")
  if (K > 6) return("complex_or_family_LD_inspect")
  return("unusual_K_inspect")
}
```

The classification names are deliberately suffixed with `_dosage` to
distinguish them from HANDOFFs 6/7's verdicts. Both methods produce
classifications; their agreement is the strongest signal.

---

## Outputs

```
dosage_clustering/<scope>/<id>/
├── dosage_matrix_median.tsv         # samples × windows
├── dosage_matrix_mean.tsv
├── window_qc.tsv                    # per-window QC results
├── adaptive_K_selection.tsv         # K vs silhouette/stability/etc.
├── cluster_assignments.tsv          # sample → cluster
├── hierarchy.json                   # hierarchical refinement tree
├── per_cluster_curves.tsv           # mean & median dosage curves
├── concordance_with_PCA.json        # ARI, Cramér's V, contingency table
├── classification.json              # final verdict
├── plot_panel_A_curves.pdf
├── plot_panel_B_heatmap.pdf
├── plot_panel_C_dendrogram.pdf
└── plot_panel_D_concordance.pdf
```

`<scope>` is `chrom` or `candidate`; `<id>` is the chromosome name or
candidate ID.

For per-chromosome runs, additionally produce a multi-chromosome
summary plot mirroring Stickleback Fig. 2 layout (one panel per
chromosome, all clusters' curves).

---

## Driver

```bash
# Per-chromosome
bash run_dosage_clustering.sh \
  --scope chrom \
  --chrom C_gar_LG28 \
  --beagle bi_baseline.beagle.gz \
  --beagle_sidecar bi_baseline.beagle.pairs.tsv \
  --window_size 10000 \
  --window_step 2500 \
  --window_unit snps \
  --K_max 8 \
  --summary_stat median \
  --silhouette_threshold 0.4 \
  --stability_threshold 0.7 \
  --spatial_coh_threshold 0.5 \
  --hierarchical TRUE \
  --max_hierarchy_depth 3 \
  --pca_for_concordance pca_results/pca_bi_baseline_*.json \
  --out_dir dosage_clustering/chrom/C_gar_LG28/

# Per-candidate
bash run_dosage_clustering.sh \
  --scope candidate \
  --candidate LG28_15.115_18.005 \
  --beagle bi_baseline.beagle.gz \
  --beagle_sidecar bi_baseline.beagle.pairs.tsv \
  --window_size 50000 \
  --window_step 25000 \
  --window_unit bp \
  --K_max 6 \
  --hierarchical TRUE \
  --pca_for_concordance pca_results/pca_bi_baseline_*.json \
  --out_dir dosage_clustering/candidate/LG28_15.115_18.005/
```

Window units configurable: `snps` (matches Stickleback iDIG-style;
robust to SNP density variation) or `bp` (matches HANDOFFs 5-7;
gives uniform spatial resolution). Default is `snps` for per-chrom,
`bp` for per-candidate.

---

## Implementation phases

### Phase 1: dosage matrix + QC (1 day)
- Read Beagle, compute per-window mean/median dosage
- Window-level QC filters
- Output cleaned dosage matrices

### Phase 2: adaptive K selection (1-2 days)
- Per-K silhouette, bootstrap stability, min size, spatial coherence
- Decision rule (smallest stable K)
- Output K selection table + chosen K + cluster assignments

### Phase 3: hierarchical refinement (1 day, optional)
- Recursive within-cluster adaptive K
- Output hierarchy tree

### Phase 4: per-cluster curves + concordance (1 day)
- Mean & median dosage curves with SD ribbons
- ARI / Cramér's V vs PCA bands
- Output per-cluster curves TSV + concordance JSON

### Phase 5: visualization (1-2 days)
- Panel A: curves plot (per-chrom multi-panel and per-candidate)
- Panel B: ordered heatmap
- Panel C: dendrogram
- Panel D: concordance matrix
- Multi-chromosome summary plot (Stickleback-style)

### Phase 6: classification + integration (0.5-1 day)
- Combine adaptive K + hierarchy + concordance into verdict
- Cross-link with HANDOFFs 6, 7 verdicts
- Output classification.json

Total ~1-1.5 weeks for full feature. **Phases 1+2+4+5 (4-5 days)
deliver the headline output** — adaptive curves, concordance,
publication figure — without hierarchical refinement.

---

## Honest expected performance

### Will work
- **Whole-chromosome scans** showing inversion-like dosage shifts:
  the Stickleback paper demonstrates this works at 10k-SNP windows.
  Adaptive K should typically converge on K=3-4 for chromosomes with
  one major inversion + population structure.
- **Per-candidate clean inversion**: K=3 with three coherent dosage
  curves (low / mid / high). Concordance with PCA bands ≥ 0.9.
- **Per-candidate compound/nested inversion**: K=5-6 with shape-
  distinct curves; hierarchy reveals which curves are sub-arrangements
  of which parent.

### Probably work
- **Heterogeneous within-cluster shapes** in hatchery cohorts: if HET
  samples come from many family backgrounds, their dosage shapes may
  spread. The adaptive criterion (spatial coherence) should still
  group them, but with lower silhouette.
- **Boundary effects** at chromosome ends: iDIG-style smoothing helps;
  edges may have noisy curves but cluster assignments should be
  robust.

### Honestly uncertain
- **Severely imbalanced clusters** (K=3 with 1/5/220 split): the rare
  cluster (n=1) fails minimum-size filter; algorithm reports K=2.
  This is correct behavior but loses the rare arrangement signal.
  Manual inspection of low-similarity outliers is needed for
  comprehensive characterization.
- **Cryptic ancestry / family LD vs nested structure**: the algorithm
  alone can't distinguish these. Cross-reference with HANDOFF 7's
  peel filter is required.
- **Mean vs median sensitivity**: for paralog-rich regions, median is
  more robust but may under-detect arrangements with strong tail
  effects. Run with both `--summary_stat mean` and `--summary_stat
  median` and compare; substantial disagreement flags the region for
  manual inspection.

### Recommended use

This is **the most directly visualizable diagnostic** in the whole
pipeline. The Stickleback-style curves are intuitive and require no
methodological knowledge to read. Use the dosage-clustering output
as:
1. The publication-grade figure for whole-chromosome visualization
2. A first-pass per-candidate sanity check before committing to
   HANDOFFs 5-7
3. Cross-validation: dosage clusters that don't match PCA bands flag
   candidates needing detailed analysis

When dosage clustering disagrees with PCA banding, **trust the
disagreement** — it's signaling something the K=3-assuming PCA may
have missed. Resolve via HANDOFF 7 (nested check) and/or HANDOFF 6
(architecture check).

---

## Paper-claim templates

For a clean simple inversion:

> "Adaptive dosage-profile clustering at LG28:15.115-18.005 Mb
> identified three sample groups with distinct mean dosage curves
> (silhouette = 0.78, bootstrap stability = 0.94). Adaptive K was
> selected from K = 1-6 and converged at K = 3. The clusters
> corresponded to homozygous-reference, heterozygous, and homozygous-
> alternative arrangements with adjusted Rand index 0.96 against
> independent local-PCA bands."

For a nested-structure case detected:

> "Adaptive dosage-profile clustering at LG28:15.115-18.005 Mb
> selected K = 5 (silhouette = 0.71). Hierarchical refinement showed
> that one of the three primary clusters subdivided into three
> sub-clusters with distinct dosage curves at LG28:15.5-15.8 Mb,
> consistent with a nested arrangement segregating within one parent
> background. The substructure showed concordance with the
> conditional local-PCA test (HANDOFF 7) on the same interval."

For a no-structure case (negative result on a non-inversion region):

> "Adaptive dosage-profile clustering across LGxx returned K = 1
> (no stable cluster structure detected at silhouette > 0.4 and
> bootstrap stability > 0.7), consistent with a non-inversion region
> showing only background population structure."

---

## File map

```
mgl_adapter/                          (existing, HANDOFFs 0-4)
trees/                                (HANDOFF 5)
fingerprints/                         (HANDOFF 6)
nested/                               (HANDOFF 7)
dosage_clustering/                    (this handoff)
├── compute_dosage_matrix.R           (Stage 1)
├── window_qc.R                       (Stage 2)
├── adaptive_K.R                      (Stage 3)
├── hierarchical_refinement.R         (Stage 4)
├── per_cluster_curves.R              (Stage 5)
├── concordance_pca.R                 (Stage 6)
├── plot_panel_A_curves.R             (Stage 7)
├── plot_panel_B_heatmap.R
├── plot_panel_C_dendrogram.R
├── plot_panel_D_concordance.R
├── plot_multi_chrom_summary.R        (Stickleback Fig. 2 style)
├── classify_dosage.R                 (Stage 8)
├── run_dosage_clustering.sh          (driver)
└── dosage_panel.js                   (atlas-side rendering, future)

specs/
└── HANDOFF_8_dosage_clustering.md    (this document)
```

---

## What you can ignore

- **Population labels**: this handoff deliberately does not use them
  for clustering. They can be overlaid post-hoc on the curves as
  metadata, but cluster assignments are dosage-defined.
- **Phasing**: dosage clustering works on diploid posterior dosage
  directly; no phasing required.
- **Tree-based clustering**: HANDOFF 5 already does this; the dosage
  approach is complementary, not duplicative.

## Pointers to existing code

- HANDOFF 1's filtered Beagle (`bi_baseline.beagle.gz`) is the
  primary input. Multi-allelic versions (`all_pairs.beagle.gz`) work
  identically — extra rows just enrich the dosage matrix.
- HANDOFF 1's heatmap producer computes per-marker dosage; reuse the
  same `dosage_b = P(Aa) + 2*P(aa)` primitive for window summaries.
- HANDOFF 5 (tree) and HANDOFF 7 (nested detector) provide independent
  cross-validation; their `cluster_labels` outputs can be loaded into
  Stage 6 for ARI computation against dosage clusters.
- HANDOFF 1's `pca_<view>_*.json` provides PCA bands for Stage 6
  concordance.

## External tools required

- R packages: `data.table`, `cluster` (silhouette), `mclust` (ARI),
  `fpc` (cluster stability), `dynamicTreeCut` (optional for
  hierarchical cuts), already-listed packages from earlier handoffs.
- No external binaries.

---

## Validation checks for LG28

1. **Per-candidate K=3 expectation**: at LG28:15.115-18.005, adaptive
   K should converge at 3, with sample counts approximately matching
   the known 60/106/60 split. Concordance with biallelic PCA bands
   should be ARI > 0.9.

2. **Per-chromosome behavior**: scanning LG28 with 10k-SNP windows
   should show a clear dosage-curve divergence at 15.1-18.0 Mb (the
   inversion) and otherwise flat curves. Adaptive K may exceed 3 if
   population structure or family LD adds independent groupings;
   that's expected for a hatchery cohort.

3. **No-nested expectation**: hierarchical refinement should not find
   stable substructure within any LG28 PCA band. If it does, this
   is either a real nested arrangement (cross-check with HANDOFF 7)
   or family LD (peel filter via HANDOFF 7).

4. **Mean vs median agreement**: running with `--summary_stat mean`
   and `--summary_stat median` should give nearly identical
   classifications at LG28. Substantial disagreement would indicate
   paralog/mappability artifacts.

5. **Window-size sensitivity**: rerun with 25-kb, 50-kb, and 100-kb
   windows. Adaptive K should be stable; cluster boundaries may
   slightly shift but assignment changes for ≥5% of samples → flag.

If LG28 returns anything other than K=3 with high concordance, the
algorithm or thresholds need tuning before applying to other
candidates.
