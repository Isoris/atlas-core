# HANDOFF 9 — Dosage similarity matrix + outer/inner block separation

**Goal**: detect nested and compound inversion architecture by computing
per-window **dosage similarity matrices** (catfish × catfish) across a
candidate inversion plus modest flanks, identifying block structure per
window, comparing block structure between windows, and classifying the
candidate as simple / nested / overlapping based on whether the inner
subdivision is contained within one outer block.

This is the **population-level diagnostic** illustrated in your nested-
inversion conceptual figure: a nested inversion looks normal at the
single-fish level, but when many catfish are compared together, the
nested structure emerges as block subdivision in one outer-arrangement
group.

**Status**: not started. Builds on HANDOFF 1 (dosage matrix from
filtered Beagle) and complements HANDOFFs 7 (conditional PCA, top-down
stratification) and 8 (adaptive K on dosage shape). This handoff takes
the **pairwise-similarity** angle, which catches block structure the
other methods can miss.

**Audience**: a fresh chat where Claude implements the dosage-similarity
matrix pipeline for one candidate at a time.

---

## Scope: candidate + flanks, NOT whole genome

For each candidate inversion (e.g., LG28:15.115-18.005, span ~2.89 Mb),
the analysis runs on an **extended interval** = candidate ± flanks.

**Flank policy** (default):
- Flank size = 20% of candidate width on each side
- Capped at 1 Mb on each side
- Minimum 100 kb on each side
- Configurable via `--flank_size_bp` or `--flank_fraction`

For LG28 (2.89 Mb) → flanks ~580 kb each side → analysis window ~4.05 Mb.
For a 500 kb candidate → flanks 100 kb each side → 700 kb total.

**Why flanks**:
1. **Reference baseline** — flanks tell you what "no structure" looks
   like in this candidate's neighborhood. Family LD that persists
   genome-wide will show in the flanks too; real inversion structure
   will not.
2. **Boundary refinement** — upstream PCA candidate boundaries are
   approximate. The dosage similarity matrix can refine them: real
   outer breakpoints are where block structure begins/ends.
3. **Honest "outside" comparison** — for the contingency-table test
   below, you need a genuine no-structure window from this candidate's
   neighborhood, not from a distant chromosomal region.

**This handoff is NOT a per-chromosome or genome-wide scanner.**
Adjacent / overlapping inversion detection is HANDOFF 6's job (regime
detector along the genome). Each candidate gets its own independent
HANDOFF 9 run.

---

## The conceptual core

Three views of the same nested-inversion biology, lifted from your
figure:

| View | What it shows |
|---|---|
| Single individual | Two haplotypes, both valid arrangements — looks normal |
| Population haplotypes | 3 distinct haplotypes circulating: STD, OUTER_INV, OUTER+INNER_INV |
| Population diplotypes | Up to 6 diplotype combinations → >3 dosage groups visible |

A nested inversion is a **population/haplotype architecture**, not a
strange-looking individual. The signature:

> **More than three coherent dosage groups within the candidate, with
> the extra groups appearing only inside one outer arrangement
> background.**

The diagnostic object is the **per-window catfish × catfish similarity
matrix**:

| Position along extended interval | Block structure |
|---|---|
| Far flank (well outside candidate) | Mostly uniform low values; no clear blocks |
| Approaching candidate | Block structure starts appearing |
| Inside outer arrangement (no inner event) | 3 large blocks (STD/STD, STD/OUTER_INV, OUTER_INV/OUTER_INV) |
| Inside an inner event | One outer block subdivides into smaller sub-blocks; other outer blocks unchanged |
| Past inner, back inside outer | Returns to 3-block pattern |
| Past outer right boundary | Blocks dissolve to flank baseline |

The asymmetric subdivision is the diagnostic — one outer block contains
the inner event, the others don't. That's distinct from:
- All three outer blocks subdividing (= two adjacent inversions)
- Subdivision crossing outer block assignments (= independent event)
- No subdivision at all (= simple inversion)

---

## Naming conventions: avoid "IBD"

| Avoid | Use instead |
|---|---|
| "IBD heatmap" | "Dosage similarity heatmap" or "Local haplotype-sharing similarity" |
| "Outer/inner inversion" before validation | "Major candidate" / "Internal candidate" / "Sub-block" |

After validation, "outer" and "inner" are fine as **structural** terms
(outer = larger spatial container; inner = smaller contained event).
They don't imply biological hierarchy or evolutionary order.

True IBD means inherited-from-common-ancestor. We compute dosage
similarity (correlation of per-marker dosage vectors), which captures
haplotype sharing without claiming inheritance. In hatchery cohorts IBD
is genuinely confounded with family structure; dosage similarity is
more honest about what we measure.

---

## What this handoff is NOT

- **NOT a replacement for HANDOFFs 7/8.** It adds a per-pair perspective:
  - HANDOFF 7: "does each parent stratum have its own PCA structure?"
  - HANDOFF 8: "does the data have natural K clusters by dosage shape?"
  - **HANDOFF 9: "do specific pairs of fish share specific windows, and
    how does the block pattern change along the genome?"**
  Same biology, different angle. They cross-validate.
- **NOT inference of haplotype phasing.** Dosage similarity is diploid;
  phasing would help but isn't required for the population-level
  architecture diagnosis.
- **NOT a genome-wide IBD scanner.** Per candidate, with flanks. Use
  HANDOFF 6 for genome-wide architecture.

---

## Pipeline architecture

```
                  ┌─────────────────────────────────┐
                  │ Candidate interval + flanks     │
                  │ (chrom, start, end, flank_size) │
                  │ + dosage matrix (samples ×      │
                  │ markers) from HANDOFF 1         │
                  └────────────┬────────────────────┘
                               │
                               ▼
                  ┌─────────────────────────────────┐
                  │ Per-window dosage similarity    │
                  │ matrix construction             │
                  │ (catfish × catfish, 1 per       │
                  │ window across extended interval)│
                  └────────────┬────────────────────┘
                               │
                               ▼
                  ┌─────────────────────────────────┐
                  │ Per-window block detection      │
                  │  - hierarchical clustering on   │
                  │    each window's matrix         │
                  │  - adaptive cut → block count   │
                  │  - per-window block assignment  │
                  └────────────┬────────────────────┘
                               │
                               ▼
                  ┌─────────────────────────────────┐
                  │ Block-transition track          │
                  │  - count block boundaries       │
                  │    along the genome             │
                  │  - identify where blocks split, │
                  │    merge, dissolve              │
                  │  - block-transition score per   │
                  │    window                       │
                  └────────────┬────────────────────┘
                               │
                               ▼
                  ┌─────────────────────────────────┐
                  │ Boundary identification         │
                  │  - outer left / outer right     │
                  │  - inner left / inner right     │
                  │  (refined positions)            │
                  └────────────┬────────────────────┘
                               │
                               ▼
                  ┌─────────────────────────────────┐
                  │ Contingency-table tests         │
                  │  - outer-only vs inner-region   │
                  │  - test for asymmetric subdiv   │
                  │  - test for cross-block subdiv  │
                  │  - test for all-block subdiv    │
                  └────────────┬────────────────────┘
                               │
                               ▼
                  ┌─────────────────────────────────┐
                  │ Classification:                 │
                  │  - simple_inversion             │
                  │  - nested_inversion             │
                  │  - two_adjacent_inversions      │
                  │  - independent_overlapping      │
                  │  - structure_only_in_flanks     │
                  │  - no_structure                 │
                  └────────────┬────────────────────┘
                               │
                               ▼
                  ┌─────────────────────────────────┐
                  │ Cross-validation against        │
                  │ HANDOFFs 5, 6, 7, 8             │
                  └─────────────────────────────────┘
```

---

## Stage 1: extended-interval definition

```r
# Read candidate
candidate <- read_candidate_table(candidate_id = "LG28_15.115_18.005")
# candidate$chrom, candidate$start, candidate$end

# Compute flanks
candidate_width <- candidate$end - candidate$start
flank_size <- min(max(0.20 * candidate_width, 100000),    # default 20%
                    1000000)                                # cap 1 Mb

# Extended interval
ext_start <- max(1, candidate$start - flank_size)
ext_end   <- candidate$end + flank_size   # check chromosome length

# Define windows across the extended interval
window_size_bp <- 50000   # default 50 kb (configurable)
window_step_bp <- 25000   # default 50% overlap
windows <- seq(ext_start, ext_end - window_size_bp, by = window_step_bp)
n_windows <- length(windows)
```

For LG28 with 2.89 Mb candidate + 580 kb flanks each side, 50 kb
windows / 25 kb step → ~160 windows.

---

## Stage 2: per-window dosage similarity matrix

For each window, compute the n_samples × n_samples similarity matrix
based on dosage correlation across markers in that window.

### Math

Let `D_w` be the n_samples × n_markers_w dosage matrix in window `w`,
with marker dosages computed as:
```
dosage_im = P(Aa)_im + 2 * P(aa)_im     [posterior expected count]
```
(same dosage primitive as HANDOFFs 1, 7, 8 — the master Beagle is
the source).

Per-window similarity:

```r
# Option 1: Pearson correlation between sample dosage vectors
S_w <- cor(t(D_w))   # n_samples × n_samples; 1 = perfect correlation

# Option 2: 1 - normalized L1 distance
S_w <- 1 - as.matrix(dist(D_w, method = "manhattan")) / (2 * ncol(D_w))

# Option 3: 1 - normalized L2 distance (Euclidean)
S_w <- 1 - as.matrix(dist(D_w)) / max(dist(D_w))
```

**Default: Pearson correlation** (Option 1). Robust to dosage scale
differences across markers, captures shape similarity, fast to
compute. Switchable via `--similarity_metric`.

### QC per window

Drop windows where:
- Marker count < `min_markers_per_window` (default 20) — not enough
  signal to compute reliable similarity
- Marker missingness > 0.20 — too many incomplete samples
- All samples have nearly identical dosage profiles (variance too low) —
  no information

Flagged windows get N/A for similarity matrix and are skipped in
downstream block detection.

### Output

A 3D array `S` of shape `n_windows × n_samples × n_samples`. For
n_windows = 160, n_samples = 226: ~8 MB at double precision.
Manageable in RAM.

Also save the per-window matrices as separate files for inspection:
`window_<idx>_similarity.tsv`.

---

## Stage 3: per-window block detection

For each window's similarity matrix, identify the block structure.

### Method: hierarchical clustering with adaptive cut

```r
detect_blocks <- function(S_w, n_min_block = 10, sil_threshold = 0.4) {
  # Convert similarity to distance
  D_dist <- as.dist(1 - S_w)

  # Hierarchical clustering (Ward.D2, matches HANDOFF 7's choice)
  hc <- hclust(D_dist, method = "ward.D2")

  # Try cuts at K = 1..6, pick best by silhouette + min block size
  best_K <- 1
  best_sil <- 0
  best_assignment <- rep(1, n_samples)
  for (K in 2:6) {
    cl <- cutree(hc, k = K)
    if (min(table(cl)) < n_min_block) next   # skip if any block too small
    sil <- mean(cluster::silhouette(cl, D_dist)[, 3])
    if (sil > best_sil && sil > sil_threshold) {
      best_K <- K
      best_sil <- sil
      best_assignment <- cl
    }
  }

  list(K = best_K, silhouette = best_sil, assignment = best_assignment,
       hclust_obj = hc)
}
```

Per window, output: number of blocks (`K`), block assignment per sample,
silhouette quality.

### Why hierarchical clustering, not K-means

Hierarchical clustering preserves the **nested structure naturally**:
the dendrogram already reflects which samples are most similar at fine
resolution and which group them at coarse resolution. K-means imposes
a flat K. For tracking block subdivision (where one block splits into
sub-blocks), hierarchical clustering is the right tool.

### When K = 1 (no structure)

Windows in the flanks should typically return K = 1 — uniform
similarity, no clear blocks. This is the **null reference**. If flank
windows return K > 1 with high silhouette, there's family LD or
ancestry structure pervading the genome, not specific to the
candidate. Note this in the QC output.

---

## Stage 4: block-transition track

Walk through the extended-interval windows in genomic order and
compute per-window summaries:

```r
transitions <- data.frame(
  window_idx = seq_len(n_windows),
  bp_center = (windows + window_size_bp/2),
  K_blocks = sapply(per_window_blocks, function(b) b$K),
  silhouette = sapply(per_window_blocks, function(b) b$silhouette),
  ARI_with_previous = NA   # filled below
)

# ARI between adjacent windows: how much do block assignments change?
for (i in 2:n_windows) {
  cl_prev <- per_window_blocks[[i-1]]$assignment
  cl_curr <- per_window_blocks[[i]]$assignment
  transitions$ARI_with_previous[i] <- mclust::adjustedRandIndex(cl_prev, cl_curr)
}

# Block-transition score: 1 - ARI gives high values where structure shifts
transitions$transition_score <- 1 - transitions$ARI_with_previous
```

The transition score per window quantifies "how much did block
assignment change from the previous window?" High score = boundary;
low score = stable region.

### Visualization

```
K_blocks
 6 │                  ╭───────╮
 5 │              ╭───╯       ╰───╮
 4 │         ╭────╯               ╰────╮
 3 │     ╭───╯                         ╰────╮
 2 │   ╭─╯                                  ╰─╮
 1 │───╯                                      ╰────────
   ├──────────────────────────────────────────────────► position
       L_outer  L_inner          R_inner   R_outer

transition score
high │     ╷                             ╷
     │     │                             │
     │     │       ╷               ╷     │
     │     │       │               │     │
low  │_____│       │_______________│_____│
     ├──────────────────────────────────────────────────► position
```

Four candidate boundary positions emerge directly from these tracks:
- **Outer left**: where K transitions from low (1-2) to higher (3+)
- **Inner left**: where K increases further (3 → 4+)
- **Inner right**: where K decreases back (4+ → 3)
- **Outer right**: where K returns to low

---

## Stage 5: outer/inner boundary identification

### Algorithm

```r
identify_boundaries <- function(transitions, K_outer = 3,
                                  flank_K_threshold = 2) {
  # Find the largest contiguous run with K >= K_outer
  outer_runs <- find_contiguous_runs(transitions$K_blocks >= K_outer)
  outer_run <- outer_runs[which.max(sapply(outer_runs, length))]
  outer_left  <- min(outer_run)
  outer_right <- max(outer_run)

  # Inside the outer run, find any sub-run with K > K_outer (inner candidate)
  inner_candidate <- which(transitions$K_blocks[outer_left:outer_right]
                           > K_outer) + outer_left - 1
  if (length(inner_candidate) >= 3) {
    inner_runs <- find_contiguous_runs(inner_candidate, contiguous = TRUE)
    # Keep only runs of >= 3 windows (~150 kb at default settings)
    inner_runs <- Filter(function(r) length(r) >= 3, inner_runs)
    if (length(inner_runs) >= 1) {
      inner_run <- inner_runs[[1]]   # largest if multiple
      inner_left  <- min(inner_run)
      inner_right <- max(inner_run)
    } else {
      inner_left <- inner_right <- NA
    }
  } else {
    inner_left <- inner_right <- NA
  }

  list(outer_left_bp = transitions$bp_center[outer_left],
       outer_right_bp = transitions$bp_center[outer_right],
       inner_left_bp = if (!is.na(inner_left)) transitions$bp_center[inner_left] else NA,
       inner_right_bp = if (!is.na(inner_right)) transitions$bp_center[inner_right] else NA,
       outer_window_idx = outer_left:outer_right,
       inner_window_idx = if (!is.na(inner_left)) inner_left:inner_right else NULL)
}
```

`K_outer = 3` is the default expected outer-arrangement block count
for a balanced inversion (HOM1, HET, HOM2). Configurable.

### Output

```json
"boundaries": {
  "outer_left_bp": 14920000,
  "outer_right_bp": 18120000,
  "inner_left_bp": 16400000,
  "inner_right_bp": 16700000,
  "candidate_left_bp_input": 15115000,    // from upstream
  "candidate_right_bp_input": 18005000,
  "outer_left_refinement": -195000,        // outer left is 195 kb to the left of input
  "outer_right_refinement": 115000,
  "inner_detected": true
}
```

The boundary refinement values quantify how much the dosage similarity
analysis adjusted the upstream PCA-based boundary estimates.

---

## Stage 6: contingency-table tests (the nesting diagnostic)

This is the test from your conceptual figure: does the inner-region
subdivision respect the outer block structure?

### Setup

Pick two reference windows:
- **Outer-only window**: a window inside the outer interval but
  outside the inner interval. Its block assignment defines outer
  arrangement membership for each sample.
- **Inner-region window**: a window inside the inner interval. Its
  block assignment includes any inner-driven subdivision.

```r
# Median-position window in outer-only stretch
outer_only_idx <- outer_window_idx[!outer_window_idx %in% inner_window_idx]
ref_outer_window <- outer_only_idx[length(outer_only_idx) %/% 2]

# Median-position window in inner stretch
ref_inner_window <- inner_window_idx[length(inner_window_idx) %/% 2]

# Block assignments at each
outer_blocks <- per_window_blocks[[ref_outer_window]]$assignment
inner_blocks <- per_window_blocks[[ref_inner_window]]$assignment

# Contingency table
ct <- table(outer = outer_blocks, inner = inner_blocks)
```

### Three diagnostic patterns

For an outer-only with K=3 and inner with K=4:

**Pattern 1: Asymmetric subdivision (NESTED)**:
```
                  Inner blocks
                  I1   I2   I3a  I3b
Outer    O1       60    0    0    0
blocks   O2        0  106    0    0
         O3        0    0   25   35
```
One outer block (O3) subdivides into I3a and I3b; others stay intact.
**Verdict: `nested_inversion`**.

**Pattern 2: All blocks subdivide (TWO ADJACENT)**:
```
                  Inner blocks
                  I1a  I1b  I2a  I2b  I3a  I3b
Outer    O1       28   32    0    0    0    0
blocks   O2        0    0   54   52    0    0
         O3        0    0    0    0   28   32
```
All three outer blocks split. **Verdict: `two_adjacent_inversions`**
(two distinct events, partly overlapping).

**Pattern 3: Subdivision crosses outer blocks (INDEPENDENT)**:
```
                  Inner blocks
                  I1   I2   I3   I4
Outer    O1       30   18    8    4
blocks   O2       58   24   16    8
         O3       22   18   16    4
```
Inner blocks distribute across outer blocks roughly proportionally.
**Verdict: `independent_overlapping_event`** (could be ancestry,
family LD, an unrelated SNP cluster, or a real but unrelated event).

### Quantitative test

```r
classify_nesting <- function(ct, asymmetry_threshold = 0.8,
                              proportional_threshold = 0.2) {
  # For each outer block, compute the fraction of its samples that go
  # into a single inner block (purity)
  purity_per_outer <- apply(ct, 1, function(row) max(row) / sum(row))

  # Count outer blocks where most samples stay in a single inner block
  n_outer_intact <- sum(purity_per_outer > asymmetry_threshold)
  n_outer_split <- length(purity_per_outer) - n_outer_intact

  # Distribution of inner blocks across outer blocks
  # If each inner block lives mostly in one outer block, that's nested
  purity_per_inner <- apply(ct, 2, function(col) max(col) / sum(col))
  n_inner_localized <- sum(purity_per_inner > asymmetry_threshold)
  n_inner_total <- length(purity_per_inner)

  if (n_outer_intact >= length(purity_per_outer) - 1 &&
      n_inner_localized == n_inner_total) {
    return("nested_inversion")
  } else if (n_outer_split == length(purity_per_outer)) {
    return("two_adjacent_inversions")
  } else if (n_outer_intact == 0 || n_inner_localized < 0.5 * n_inner_total) {
    return("independent_overlapping_event")
  } else {
    return("ambiguous_inspect_manually")
  }
}
```

### Output

```json
"nesting_test": {
  "ref_outer_window_bp": 17400000,
  "ref_inner_window_bp": 16550000,
  "contingency_table": {
    "O1": {"I1": 60, "I2": 0, "I3a": 0, "I3b": 0},
    "O2": {"I1": 0, "I2": 106, "I3a": 0, "I3b": 0},
    "O3": {"I1": 0, "I2": 0, "I3a": 25, "I3b": 35}
  },
  "purity_per_outer": [1.0, 1.0, 0.58],
  "purity_per_inner": [1.0, 1.0, 1.0, 1.0],
  "verdict": "nested_inversion",
  "subdividing_outer_block": "O3",
  "n_inner_subblocks": 2
}
```

---

## Stage 7: cross-validation with HANDOFFs 5, 6, 7, 8

A confident `nested_inversion` verdict requires multi-method agreement:

| Method | Expected for nested |
|---|---|
| HANDOFF 6 fingerprinter | Either stable_inversion (no regime switch) or `nested_rearrangement` |
| HANDOFF 7 nested detector | `nested_inversion_strong` or `nested_inversion_likely`; subdividing stratum should match this handoff's `subdividing_outer_block` |
| HANDOFF 8 dosage clustering | Adaptive K = 5 or 6; hierarchy refined inside one cluster |
| HANDOFF 5 tree | Inner sub-block samples form a sister clade within the parent clade |
| **HANDOFF 9 (this)** | `nested_inversion`, asymmetric contingency |

When 3+ of these 5 methods agree on nesting → **strong nested inversion**.
When only 1-2 methods report it → **weak; inspect manually**.
The full diagnostic JSON cross-references each method's verdict.

```r
integrate_classifications <- function(h6, h7, h8, h9, h5) {
  votes_nested <- sum(c(
    h6$verdict %in% c("stable_inversion", "nested_rearrangement"),
    h7$classification %in% c("nested_inversion_strong", "nested_inversion_likely"),
    h8$classification %in% c("compound_or_nested_inversion",
                             "simple_inversion_with_nested_substructure"),
    h9$verdict == "nested_inversion",
    !is.null(h5$nested_subclade)
  ))
  if (votes_nested >= 3) return("strong_nested_inversion")
  if (votes_nested >= 1) return("weak_nested_inversion_inspect")
  return("simple_inversion_or_other")
}
```

---

## Stage 8: visualization

### Plot 1: similarity matrix mosaic

Pick 4-6 representative windows across the extended interval (one in
each flank, one in outer-only stretch, one in inner stretch, one back
in outer-only). Display their similarity matrices side-by-side as a
mosaic:

```
[Far flank]  [Outer left edge]  [Outer-only]  [Inner]  [Outer-only]  [Far flank]
   no blocks     blocks emerge    3 blocks    3+sub     3 blocks      no blocks
```

This is the headline figure for the paper — it directly shows the
block-transition story along the genome.

### Plot 2: block-transition track + boundary markers

Two-panel: top shows K_blocks vs position; bottom shows transition_score
vs position. Vertical lines at outer_left, inner_left, inner_right,
outer_right.

### Plot 3: per-block dosage curves

For each block in the outer-only reference window (typically 3 blocks):
plot mean dosage across the extended interval, colored by outer block
membership. This shows the outer arrangement's dosage profile along
the genome, with the inner-region windows marked.

For nested cases, additionally show: dosage curves of the two inner
sub-blocks (samples in O3 split into I3a vs I3b), restricted to the
outer block where the inner event lives. The curves should diverge
inside the inner interval and converge outside.

### Plot 4: contingency table heatmap

The diagnostic from Stage 6 visualized as a small heatmap:
rows = outer blocks, columns = inner blocks, cell color = sample count,
annotation = purity scores.

This 4-plot panel is the per-candidate paper figure.

---

## Outputs

```
dosage_similarity/<candidate_id>/
├── extended_interval.tsv             # candidate + flank coordinates
├── per_window_similarity_matrices/   # *.tsv per window (or compressed RDS)
├── per_window_blocks.tsv             # K, assignment, silhouette per window
├── transitions_track.tsv             # block_count + transition_score per window
├── boundaries.json                   # outer_left, inner_left, etc.
├── contingency_table_test.json       # Stage 6 output
├── classification.json               # final verdict + cross-validation
├── plot_similarity_mosaic.pdf        # the headline figure
├── plot_blocks_track.pdf
├── plot_block_dosage_curves.pdf
└── plot_contingency_heatmap.pdf
```

---

## Driver

```bash
bash run_dosage_similarity.sh \
  --candidate LG28_15.115_18.005 \
  --beagle bi_baseline.beagle.gz \
  --beagle_sidecar bi_baseline.beagle.pairs.tsv \
  --flank_fraction 0.20 \
  --flank_size_max_bp 1000000 \
  --flank_size_min_bp 100000 \
  --window_size_bp 50000 \
  --window_step_bp 25000 \
  --similarity_metric pearson \
  --min_markers_per_window 20 \
  --K_outer_expected 3 \
  --silhouette_threshold 0.4 \
  --min_block_size 10 \
  --min_inner_run_windows 3 \
  --asymmetry_threshold 0.8 \
  --cross_validate_with_handoffs TRUE \
  --out_dir dosage_similarity/LG28_15.115_18.005/
```

Flags worth highlighting:
- `--flank_fraction`: default 0.20 (20% of candidate width on each side)
- `--flank_size_max_bp` / `--flank_size_min_bp`: caps and floors
- `--similarity_metric`: pearson | manhattan | euclidean
- `--K_outer_expected`: expected outer block count (3 for typical
  inversions; 2 for SNP-style biallelic CNVs; etc.)
- `--asymmetry_threshold`: purity threshold for nested verdict (0.8
  default)
- `--min_inner_run_windows`: minimum contiguous inner-region windows
  for inner_detected = true (3 default; ~150 kb at default window size)

---

## Implementation phases

### Phase 1: similarity matrix construction (1-2 days)
- Extended interval definition
- Per-window dosage extraction from Beagle
- Pearson correlation matrix per window
- QC and storage

### Phase 2: block detection + transition track (1-2 days)
- Hierarchical clustering per window
- Adaptive K cut
- ARI between adjacent windows
- Transition score track

### Phase 3: boundary identification + contingency tests (1-2 days)
- Outer left/right detection
- Inner left/right detection  
- Reference window selection
- Asymmetric subdivision test
- Three-way classification

### Phase 4: cross-validation integration (0.5-1 day)
- Read HANDOFFs 5, 6, 7, 8 outputs (when available)
- Vote-based integration
- Final classification JSON

### Phase 5: visualization (1-2 days)
- Similarity matrix mosaic (4-6 windows)
- Block-transition track plot
- Per-block dosage curves
- Contingency heatmap

Total ~1-1.5 weeks for full feature. **Phases 1+2+3 alone (4-6 days)
deliver the headline classification** and similarity-matrix figures
without atlas integration or full cross-validation.

---

## Honest expected performance

### Will work
- **Clean nested inversion** (your conceptual figure case): outer K=3,
  inner subdivides one outer block into 2 sub-blocks. Block detection
  in similarity matrices is robust at 50 kb windows with default
  density.
- **Detection of non-inversion null**: flank windows return K=1 with
  low silhouette → confirms the "no structure" baseline. Family LD
  that pervades the genome shows in flanks too; the contrast confirms
  inversion-specific signal.
- **Boundary refinement**: similarity-matrix transitions are typically
  sharper than PCA-based boundaries. Expect refinement of ±100-300 kb
  for typical candidates.
- **Three-way classification** (nested vs adjacent vs independent):
  the contingency-table test is unambiguous when block assignments
  are stable. The asymmetry purity scores typically separate the three
  patterns clearly.

### Probably work
- **Smaller inner inversions** (~100-200 kb): may produce only 1-2
  windows of inner-block subdivision; below `min_inner_run_windows`.
  Tune the threshold per cohort.
- **Mildly imbalanced parent karyotypes** (e.g., 10/100/116): the rare
  outer block (n=10) may not subdivide cleanly even if it carries the
  inner event, because n=10 is below `min_block_size`. Consider lower
  thresholds for small candidates.
- **Modest family LD**: flank windows show some block structure but
  with low silhouette. The contrast with the inversion-region
  silhouette should still be detectable.

### Honestly uncertain
- **Severely imbalanced karyotypes** (e.g., 5/15/206): rare outer
  block too small for reliable block detection. Manual inspection
  of similarity matrices remains necessary.
- **Two truly independent overlapping inversions** (Pattern 3 verdict):
  distinguishing this from family LD or ancestry block can be
  difficult; cross-validation with HANDOFF 7 peel filter is required.
- **Continuous gradients of similarity** instead of discrete blocks:
  if family structure dominates, samples form continuous similarity
  patterns rather than discrete blocks. Hierarchical clustering will
  still report a K, but silhouette will be low. Trust the silhouette
  threshold; report as `no_structure` when silhouette < threshold.

### Recommended use

Run HANDOFF 9 on each promising candidate after upstream PCA detection
identifies it. The **headline figure** (similarity-matrix mosaic
across the extended interval) is the most direct visual evidence of
nested architecture and should be the per-candidate paper figure when
nesting is detected.

When HANDOFF 9 disagrees with HANDOFFs 7 or 8 about whether nesting
is present, trust the multi-method integration — single-method
verdicts can be misled by edge cases. Manual inspection of the
similarity-matrix mosaic settles most ambiguities.

---

## Paper-claim templates

For a confident nested inversion:

> "Per-window dosage similarity matrices computed across the candidate
> interval LG28:15.115-18.005 Mb plus 580 kb flanks revealed a clear
> three-block structure throughout the candidate, with one outer
> block (n=60 carriers) subdividing into two coherent sub-blocks
> (n=25 and n=35) within the interval LG28:16.4-16.7 Mb. The
> contingency table between outer-only and inner-region windows showed
> asymmetric subdivision (outer block O3 purity 0.58, all other outer
> blocks purity 1.0), consistent with a nested inversion architecture.
> The signal was supported by HANDOFFs 7 (conditional PCA detected
> nested signal in the HOM2 stratum on PC2, silhouette 0.71) and 8
> (adaptive K = 5 with hierarchical refinement of one cluster)."

For two adjacent inversions:

> "Per-window dosage similarity matrices showed coordinated subdivision
> of all three outer blocks within LG28:16.4-16.7 Mb (purity scores
> 0.45, 0.51, 0.48 respectively). This pattern is consistent with
> two adjacent inversions sharing a partial overlap in coordinates,
> rather than a single nested inversion. Splitting the candidate into
> two distinct candidates is recommended for downstream analyses."

For a no-structure flank baseline:

> "Flanking regions of the candidate (LG28:14.5-14.9 and 18.1-18.5 Mb)
> showed no block structure (mean K_blocks = 1.2, mean silhouette =
> 0.18), confirming the local null reference. The block structure
> within the candidate is therefore inversion-specific rather than
> reflecting genome-wide family LD."

---

## File map

```
mgl_adapter/                          (existing, HANDOFFs 0-4)
trees/                                (HANDOFF 5)
fingerprints/                         (HANDOFF 6)
nested/                               (HANDOFF 7)
dosage_clustering/                    (HANDOFF 8)
dosage_similarity/                    (this handoff)
├── extended_interval.R               (Stage 1)
├── compute_similarity_matrices.R     (Stage 2)
├── detect_blocks.R                   (Stage 3)
├── transitions_track.R               (Stage 4)
├── identify_boundaries.R             (Stage 5)
├── contingency_test.R                (Stage 6)
├── integrate_classifications.R       (Stage 7)
├── plot_similarity_mosaic.R          (Stage 8)
├── plot_blocks_track.R
├── plot_block_dosage_curves.R
├── plot_contingency_heatmap.R
├── run_dosage_similarity.sh          (driver)
└── similarity_panel.js               (atlas-side rendering, future)

specs/
└── HANDOFF_9_dosage_similarity.md    (this document)
```

---

## What you can ignore

- **True IBD inference** (using IBDseq, hap-IBD, Beagle IBD): out of
  scope. Dosage similarity is sufficient for the architecture
  diagnosis and avoids the family-structure confounding issue. If
  pedigree validation is needed later, use those tools as separate
  follow-up.
- **Phasing**: not required. Diploid dosage similarity captures the
  population-level signature directly.
- **Per-chromosome scanning**: out of scope. Run per candidate. Use
  HANDOFF 6 for genome-wide architecture diagnosis.
- **Cross-candidate similarity** (e.g., do candidates A and B share
  carriers?): out of scope. Future extension.

## Pointers to existing code

- HANDOFF 1's filtered Beagle (`bi_baseline.beagle.gz`) is the
  primary input. Multi-allelic versions (`all_pairs.beagle.gz`) work
  identically with extra rows enriching the dosage matrix.
- HANDOFF 1's heatmap producer computes per-marker dosage; reuse the
  same `dosage_b = P(Aa) + 2*P(aa)` primitive.
- HANDOFFs 5, 6, 7, 8 produce verdicts that integrate at Stage 7.
  Each handoff's classification.json output is read for cross-
  validation.
- `region_stats_dispatcher.R get_region_stats()` is NOT used here;
  dosage similarity is computed directly from the Beagle.

## External tools required

- R packages: `data.table`, `cluster` (silhouette), `mclust` (ARI),
  `RSpectra` (optional, for fast eigendecomposition of large matrices).
- No external binaries.

---

## Validation checks for LG28

1. **Flank windows return K=1**: confirms baseline. If flanks return
   K > 1 with high silhouette, family LD or ancestry pervades the
   genome; flag as `genome_wide_structure_present` in QC log.

2. **Outer-only windows return K=3**: matches expected balanced
   60/106/60 karyotype. Block sizes should approximate this.

3. **Boundary refinement modest**: similarity-based outer boundaries
   should be within ±200 kb of upstream PCA-based boundaries. Larger
   shifts indicate the upstream PCA-based candidate definition was
   off.

4. **No inner detected (LG28 expected)**: LG28 is well-characterized
   as a simple inversion. The expected verdict is `simple_inversion`
   (no inner-region windows with K > 3 of sufficient duration). If
   HANDOFF 9 returns `nested_inversion`, this is an interesting
   finding — investigate or troubleshoot threshold tuning.

5. **Cross-validation**: HANDOFFs 7 and 8 should also return
   non-nested verdicts for LG28. If they disagree, manual inspection
   of the similarity-matrix mosaic is the tiebreaker.

If LG28 returns `simple_inversion` from HANDOFF 9 with all flanks at
K=1 and outer-only at K=3 with high silhouette, the pipeline is
calibrated correctly for application to other candidates.
