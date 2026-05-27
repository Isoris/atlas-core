# HANDOFF 6 — Fragment fingerprinter

**Goal**: detect whether two windows of an inversion candidate belong to
the same evolutionary regime (same inversion haplotype system), and
locate **double crossovers** and **nested rearrangements** as local
switches in the diversity pattern that return to baseline outside the
recombinant tract.

**Status**: not started. Builds on `region_popstats.c` (engine v2),
`region_stats_dispatcher.R` v12.2, and the band assignments from
HANDOFF 1's PCA producer. Independent of the multi-allelic mgl pipeline
(works on standard Beagle), but compatible with it.

**Audience**: a fresh chat where Claude implements the fingerprinter.

---

## What you're building

For each sliding window inside a candidate inversion interval, compute
a **diversity-profile vector** (per-band π, between-band dXY/dA/Fst,
private-allele structure, tree-clade signature). Then cluster windows
by their fingerprints and detect **regime switches** — windows whose
fingerprint differs from their neighbors but whose neighbors return to
the same fingerprint on both sides (double crossover signature) or
whose pattern shows extra substructure (nested rearrangement).

The deliverable is a **per-window regime label** that complements the
sample-level dosage state, plus a visualization that shows where in the
candidate interval the inversion architecture changes vs. is stable.

---

## What this answers (vs. PCA / heatmap / tree)

| Question | Tool |
|---|---|
| How are samples clustered overall? | PCA |
| What dosage patterns characterize each cluster? | Heatmap |
| Are clusters phylogenetic clades? | Tree |
| **Does the diversity pattern stay the same across the candidate, or does it switch in places?** | **Fingerprinter** |
| **Is this region one inversion, two adjacent inversions, or one inversion with a recombinant tract?** | **Fingerprinter** |

The fingerprinter is the **architecture diagnostic**. PCA/heatmap/tree
all assume the candidate is one coherent block; the fingerprinter tests
that assumption.

---

## The four scenarios it discriminates

Think of the candidate as a path of fragments along the genome:

```
       Fragment A — Fragment B — (boundary) — Fragment B' — Fragment A'
```

Each fragment gets a **diversity fingerprint**. The question is whether
fingerprints repeat in a meaningful pattern.

### Scenario 1: stable inversion (one regime)
All fragments share one fingerprint. No A-B distinction; the inversion
is a single coherent block.

```
fingerprint:  A — A — A — A — A
```

Verdict: `stable_inversion`.

### Scenario 2: double crossover / recombinant tract
Outer fragments share fingerprint type 1. A middle tract shows
fingerprint type 2 (or a "mixed" state). Outer fingerprint **returns**
on the other side.

```
fingerprint:  A — A — [B/mixed] — A — A
              └──────────────────────┘
              same fingerprint on both sides
```

Verdict: `one_inversion_with_recombinant_tract`.
Recombinant carriers identified per sample.

### Scenario 3: two adjacent inversions / no return
Left half has fingerprint type 1; right half has fingerprint type 2.
**No return** — the pattern doesn't go back.

```
fingerprint:  A — A — A — A | B — B — B — B
                         no return ───┘
```

Verdict: `two_adjacent_inversions` (consider splitting candidate).

### Scenario 4: nested / mosaic — the A-B-B'-A' signature
A more complex repeating pattern, where multiple fingerprint types
appear in symmetric positions:

```
fingerprint:  A — B — [crossover] — B' — A'
              ↑   ↑                  ↑    ↑
              fingerprint(A)  ≈  fingerprint(A')
              fingerprint(B)  ≈  fingerprint(B')
```

This is the structure for nested rearrangements or for inversions
with internal block repeats. Verdict: `nested_rearrangement` if the
fingerprint(A,A') and fingerprint(B,B') matches are clean;
`complex_architecture_check_alignment` otherwise.

The diagnostic is **fragment-pair similarity**: not just clustering
windows into regimes, but specifically asking whether fingerprints at
position p1 and position p2 are concordant. See Stage 2.5 below.

---

## Inputs

For a candidate (chrom, start, end):

- **Band assignments** per sample (from HANDOFF 1's PCA: which sample is
  in band A / B / C / ...)
- **Beagle** for the chromosome (existing biallelic Beagle is fine; for
  multi-allelic-aware fingerprints, use `all_pairs.beagle.gz` from
  HANDOFF 1)
- **Window definition**: bp_span (default 50 kb, configurable). Step
  configurable; for stable-vs-switch detection, use
  step = window_size / 2 (50% overlap) for smoother profiles.

---

## Stage 1: per-window diversity profile

For each window, run `region_popstats.c` via `region_stats_dispatcher.R`:

```r
source("region_stats_dispatcher.R")
configure_dispatcher(config_file = "00_ancestry_config.sh")

bands <- list(A = readLines("samples_A.txt"),
              B = readLines("samples_B.txt"),
              C = readLines("samples_C.txt"))

# One windowed call covering the whole candidate interval
result_dt <- route_to_c_popstats(
  chr = "C_gar_LG28",
  start = 15115000, end = 18005000,
  groups = bands,
  fixed_win = "50000:25000",   # 50 kb windows, 25 kb step
  downsample = 1, type = 2
)
# result_dt is a data.table: one row per window, many columns
```

### Profile vector per window

For each window row, the **fingerprint vector** is:

```
[
  pi_A, pi_B, pi_C,                                  # per-band diversity
  dXY_A_B, dXY_A_C, dXY_B_C,                         # between-band divergence
  dA_A_B, dA_A_C, dA_B_C,                            # net divergence
  Fst_A_B, Fst_A_C, Fst_B_C,                         # F-statistics
  TajimaD_A, TajimaD_B, TajimaD_C, TajimaD_all,      # SFS shape
  singleton_fraction_A, singleton_fraction_B, _C,    # rare-allele structure
  rare_fraction_A, rare_fraction_B, rare_fraction_C,
  age_proxy_A_B, age_proxy_A_C, age_proxy_B_C        # divergence-age proxy (see below)
]
```

That's ~25 dimensions per window for a 3-band candidate. Generalizes
naturally for K bands: `K + 4*K*(K-1)/2 + K + 1 + 2*K` features.

These columns all come directly from `region_popstats.c`'s output (the
age proxies are derived from dA — see Stage 2.5).

### Divergence-age proxy

For each pair of bands, compute the **age proxy** as:

```
age_proxy(A, B) = dA(A, B) / (2 * mu)
```

where `mu` is the per-site, per-generation substitution rate (literature
value or species-specific estimate). For *Clarias gariepinus*, use the
appropriate teleost rate (~1e-9 to 1e-8 per site per generation;
configurable via `--mu` flag).

**Important honesty**: this is a *proxy*, not a measured age. Reported
in millions of generations or, with generation-time, millions of years
— but always with the caveat that it assumes:
- Constant substitution rate across the genome
- No within-clade diversity contamination (dA already partially handles this)
- No selection or rate-variation effects

The atlas and paper text should label this column as "divergence age
proxy (Mya, assuming μ=X)", not "age".

For windows where dA < 0 (negative net divergence — happens when
within-clade π exceeds between-clade dXY due to noise or family
inflation), `age_proxy = 0` with a flag.

### Standardization

Within the candidate, z-score each feature column across windows:

```r
profile_mat <- as.matrix(result_dt[, ..feature_cols])
profile_z   <- scale(profile_mat)   # column-wise z-score
```

This makes the fingerprint **shape-based** — what matters is whether
two windows have a similar pattern of high/low across features, not the
absolute values. Robust to candidate-wide effects (high overall diversity,
etc.).

---

## Stage 2: rank-based fingerprint (the headline diagnostic)

Z-scored vectors capture magnitudes. **Rank-based fingerprints capture
the qualitative pattern** that the prompt emphasized — "same dXY/dA
ranking among bands."

For each window, extract the ranking signature:

```r
window_ranking <- function(row, bands) {
  # Per-band π ranking (low to high)
  pi_rank <- order(c(pi_A = row$theta_pi_A,
                     pi_B = row$theta_pi_B,
                     pi_C = row$theta_pi_C))
  # Pairwise dXY ranking (low to high)
  pairs <- combn(bands, 2)
  dXY_vals <- sapply(seq_len(ncol(pairs)), function(k) {
    a <- pairs[1, k]; b <- pairs[2, k]
    row[[paste0("dXY_", a, "_", b)]]
  })
  dXY_rank <- order(dXY_vals)
  # Fst ranking similarly
  Fst_vals <- sapply(seq_len(ncol(pairs)), function(k) {
    a <- pairs[1, k]; b <- pairs[2, k]
    row[[paste0("Fst_", a, "_", b)]]
  })
  Fst_rank <- order(Fst_vals)

  list(pi_rank = pi_rank, dXY_rank = dXY_rank, Fst_rank = Fst_rank)
}
```

Two windows have the **same regime fingerprint** if their pi_rank,
dXY_rank, and Fst_rank tuples all match.

### The regime-equivalence test

```r
same_regime <- function(window_i, window_j) {
  identical(window_i$pi_rank,  window_j$pi_rank) &&
  identical(window_i$dXY_rank, window_j$dXY_rank) &&
  identical(window_i$Fst_rank, window_j$Fst_rank)
}
```

This is the **headline diagnostic from the prompt**: "do these fragments
share the same diversity architecture?"

Stricter criterion (requires concordance on more axes); looser (just
dXY rank) is a relaxation.

---

## Stage 2.5: fragment-pair similarity matrix (the A-B-B'-A' diagnostic)

The regime clustering in Stage 3 asks: "do windows W1 and W2 belong to
the same regime?" That's a binary question.

This stage asks the **stronger** question: "for every pair of fragments
in the candidate, how similar are their fingerprints?" The output is an
N×N matrix (N = number of fragments), and the test for the A-B-B'-A'
pattern is whether the matrix shows **off-diagonal high-similarity
blocks** at symmetric positions.

### How fragments are defined (NOT a fixed size)

**Fragments are NOT a fixed size like 70 kb.** They are runs of
consecutive windows assigned to the same regime by Stage 3. So a
candidate's fragment layout is **emergent** from the regime
boundaries:

```
windows:    [1] [2] [3] [4] [5] [6] [7] [8] [9] [10]
regime:      R1  R1  R1  R2  R2  R1  R1  R1  R1  R1

→ fragments:
   Fragment 1 = windows 1-3 (regime R1, 3 windows)
   Fragment 2 = windows 4-5 (regime R2, 2 windows)
   Fragment 3 = windows 6-10 (regime R1, 5 windows)
```

A fragment can be as small as 1 window (50 kb default) or as large as
the whole candidate (e.g., for a stable inversion: 1 fragment = the
entire interval).

This contrasts with the *Drosophila subobscura* literature pattern
(e.g., Orengo et al., Sci Rep 2019), where fragments are defined by
**molecularly mapped breakpoints** at named cytological positions
(58D|59A, 64B|64C, 68B...). Those analyses are *known-breakpoint
comparisons*, asking whether arrangement E_1+2+9 shares fragment AK
with E_1+2+9+12. Our setting is *discovery*: we don't have molecular
breakpoint maps, so regime boundaries serve as the analogous
fragmentation. Once a candidate is confirmed and breakpoints are
mapped (e.g., from long-read assembly), this stage can be re-run with
named fragment boundaries instead of regime boundaries.

### Minimum fragment size and statistical reliability

Different statistics need different SNP counts to be reliable:

| Statistic | Minimum SNPs for stable estimate | Notes |
|---|---|---|
| **dXY between groups** | ~50 | Most robust; averages over all sites including invariant. |
| **π per group** | ~50-100 | Needs segregating sites within the group. |
| **dA = dXY − mean(π)** | ~100 | As reliable as the noisier of dXY and π. |
| **Fst** | ~100-200 | Needs allele-frequency differences; noisier with small groups. |
| **Tajima's D** | ~50 (engine guard); 100+ for stability | Engine emits NA below `--min_S` (default 5). |
| **Singleton/rare fractions** | 200+ | SFS-based; very noisy with small fragments. |
| **Age proxy (dA-derived)** | ~100 | Inherits dA's reliability. |

For a typical 50 kb window with average SNP density 1/200 bp, you get
~250 SNPs per window. So **a single window is usually enough for dXY
and π**, but Tajima's D and rare-allele fractions need at least 2-3
windows aggregated.

### Reliability tiers per fragment

Each fragment is annotated with a **reliability tier** based on its
total SNP count:

| Tier | SNP count | Use |
|---|---|---|
| `high` | ≥ 500 | All statistics trustworthy; full fingerprint comparison |
| `medium` | 100-499 | dXY, π, dA reliable; Fst marginal; Tajima_D and rare-fractions flagged unreliable; **fingerprint uses high-confidence subset** |
| `low` | 50-99 | Only dXY meaningful; **fingerprint comparisons downweighted** |
| `unreliable` | < 50 | **Excluded from similarity matrix**; flagged for inspection only |

For `medium` and `low` tiers, the cosine-similarity component of the
fingerprint matrix is computed **only over the trustworthy subset of
features**. Age proxies from low-tier fragments are reported but with
explicit confidence flags.

### Aggregating per-window stats into per-fragment fingerprint

For a fragment spanning windows `w_start..w_end`, the per-fragment
fingerprint feature is computed **site-weighted** across the included
windows (this is already the dispatcher's `weighted = TRUE` default in
`region_stats_dispatcher.R` v12.2):

```r
# For per-site metrics (π, dXY, dA, Fst):
fragment_stat <- sum(window_stat * window_n_sites) / sum(window_n_sites)

# For SFS counts (S, singletons, doubletons, rare):
fragment_stat <- sum(window_stat)

# For Tajima's D (already standardized):
fragment_stat <- mean(window_TajimaD)   # unweighted mean
```

The dispatcher exposes this as one call when given a fragment-spanning
range. So Stage 2.5 in practice is:

```r
# After Stage 3 has assigned regime labels per window:
fragments <- split_windows_by_regime(window_profiles)

for (frag in fragments) {
  # Re-call the dispatcher on the fragment's bp range — gives
  # site-weighted fragment-level stats correctly
  frag$fingerprint <- get_region_stats(
    chr   = candidate$chrom,
    start = frag$bp_start,
    end   = frag$bp_end,
    what  = c("Fst", "dXY", "dA", "theta_pi", "Tajima_D",
              "singleton_fraction", "rare_fraction"),
    groups = bands,
    popstats_opts = list(fixed_win = paste0(frag$bp_size, ":", frag$bp_size),
                         weighted = TRUE)
  )
  frag$reliability_tier <- tier_from_snps(frag$n_snps_total)
}
```

The `fixed_win = "<size>:<size>"` (no overlap, single window) trick
gives the per-fragment summary in one engine call, with the dA
invariant intact (because all stats come from the same engine call —
see `region_popstats.c` header for the cross-call composition rule).

### Why this matters

Same fingerprint and similar age both add support, but neither alone is
enough:

| Pattern | Verdict |
|---|---|
| Same fingerprint + similar age | Strong support for same evolutionary block |
| Same age only | Weak — many regions can have similar divergence by chance |
| Same fingerprint, different age | Possible recombination / selection / rate variation |
| Different fingerprint, same age | Probably not the same block |

So the matrix combines **fingerprint similarity** (full vector match)
and **age compatibility** (age proxies within tolerance).

### Computing the matrix

```r
# For each pair of fragments (i, j), compute similarity:
fingerprint_similarity <- function(fp_i, fp_j, age_tol = 0.5) {
  # Reliability-aware feature subset: use the intersection of features
  # both fragments can support. low-tier fragments only contribute dXY;
  # medium-tier add π, dA; high-tier add Fst, Tajima_D, fractions.
  trust_i <- trusted_features(fp_i$reliability_tier)
  trust_j <- trusted_features(fp_j$reliability_tier)
  features_used <- intersect(trust_i, trust_j)

  # 1. Vector cosine similarity on z-scored profile, using only
  #    features both fragments support reliably
  v_i <- fp_i$profile_z[features_used]
  v_j <- fp_j$profile_z[features_used]
  cos_sim <- sum(v_i * v_j) / (sqrt(sum(v_i^2)) * sqrt(sum(v_j^2)))

  # 2. Rank-equivalence (Stage 2): boolean — same ranking signature?
  #    Only computed if both fragments are at least 'medium' tier.
  if (fp_i$reliability_tier %in% c("high", "medium") &&
      fp_j$reliability_tier %in% c("high", "medium")) {
    rank_match <- identical(fp_i$ranking_signature, fp_j$ranking_signature)
  } else {
    rank_match <- NA
  }

  # 3. Age compatibility per band-pair (uses dA, so reliable from medium up)
  if (fp_i$reliability_tier %in% c("high", "medium") &&
      fp_j$reliability_tier %in% c("high", "medium")) {
    age_compat <- mean(abs(fp_i$age_proxy - fp_j$age_proxy) <
                       age_tol * pmax(fp_i$age_proxy, fp_j$age_proxy))
  } else {
    age_compat <- NA
  }

  # Combined score: cosine alone for low-tier; full weighting for high+medium.
  # When rank_match or age_compat is NA, redistribute weight to cosine.
  combined <- if (!is.na(rank_match) && !is.na(age_compat)) {
    0.5 * cos_sim + 0.3 * as.numeric(rank_match) + 0.2 * age_compat
  } else {
    cos_sim   # low-tier: cosine on robust features only
  }

  list(
    cosine             = cos_sim,
    rank_equivalent    = rank_match,
    age_compatible     = age_compat,
    combined           = combined,
    features_used      = features_used,
    confidence         = paste(fp_i$reliability_tier, fp_j$reliability_tier, sep = "/")
  )
}

trusted_features <- function(tier) {
  switch(tier,
    high       = c("pi_*", "dXY_*", "dA_*", "Fst_*", "TajimaD_*", "*_fraction_*", "age_proxy_*"),
    medium     = c("pi_*", "dXY_*", "dA_*", "age_proxy_*"),
    low        = c("dXY_*"),
    unreliable = character(0)
  )
}

# N×N matrix
fragments <- split_into_fragments(window_profiles)   # by regime boundaries
fragments <- Filter(function(f) f$reliability_tier != "unreliable", fragments)
M <- matrix(NA, length(fragments), length(fragments))
M_confidence <- matrix("", length(fragments), length(fragments))
for (i in seq_along(fragments)) for (j in seq_along(fragments)) {
  sim <- fingerprint_similarity(fragments[[i]], fragments[[j]])
  M[i, j] <- sim$combined
  M_confidence[i, j] <- sim$confidence
}
```

The fragments are continuous runs of windows in the same regime (from
Stage 3), so for a candidate with the A-B-B'-A' structure you'd have
~5 fragments (A, B, recombinant tract, B', A').

### Reading the matrix

For the A-B-B'-A' pattern:

```
        Frag1(A)  Frag2(B)  Frag3(crossover)  Frag4(B')  Frag5(A')
Frag1     1.0       0.3         0.2              0.3        0.95   ←
Frag2     0.3       1.0         0.4              0.92       0.3
Frag3     0.2       0.4         1.0              0.4        0.2
Frag4     0.3       0.92        0.4              1.0        0.3
Frag5     0.95      0.3         0.2              0.3        1.0    ←
            ↑                                       ↑
            high similarity at symmetric positions
```

The diagonal is always 1 (self-similarity). The **off-diagonal
high-similarity entries at symmetric positions** are the diagnostic for
A-B-B'-A' structure.

### Test for the symmetric-repeat pattern

For each fragment pair (i, j) with j > i, ask:
- Are they at **symmetric positions** around a midpoint? (e.g.,
  fragment 1 and fragment N, or fragment 2 and fragment N-1)
- Is the similarity above a threshold (e.g., 0.85)?

If yes for multiple symmetric pairs, the candidate has the A-B-B'-A'
signature. Output:

```json
"symmetric_repeat_pairs": [
  {
    "fragment_a": 1, "fragment_b": 5,
    "labels": ["A", "A'"],
    "cosine_similarity": 0.95,
    "rank_equivalent": true,
    "age_compatible": 1.0,
    "age_proxy_Mya_a": 2.30, "age_proxy_Mya_b": 2.32,
    "verdict": "matched"
  },
  {
    "fragment_a": 2, "fragment_b": 4,
    "labels": ["B", "B'"],
    "cosine_similarity": 0.92,
    "rank_equivalent": true,
    "age_compatible": 1.0,
    "age_proxy_Mya_a": 2.17, "age_proxy_Mya_b": 2.15,
    "verdict": "matched"
  }
]
```

When two or more symmetric pairs match, the architecture is reported as
`A-B-B'-A' nested mosaic`. When no symmetric pairs match, a
single-block stable-inversion or simple recombinant-tract verdict is
issued from Stage 3 alone.

### Honest framing for the paper

The age proxies are reported as `Mya assuming μ=X`. The verdict is
phrased as:

> "Fragments A and A' showed matched diversity fingerprints and similar
> divergence-age proxies (2.30 vs 2.32 Mya, μ=1e-9), consistent with
> repeated blocks of the same inversion haplotype background. Fragments
> B and B' showed a second matched fingerprint (2.17 vs 2.15 Mya),
> supporting a mosaic A-B-B'-A' structure consistent with historical
> double-crossover or recombinant haplotype formation."

Avoid: "The inversion is 2.3 million years old" (uncalibrated).
Use: "Divergence-age proxy ≈ 2.3 Mya" or "consistent with similar
divergence times".

---

## Stage 3: regime clustering and switch detection

### Clustering windows by profile

Two methods, run both:

**Method A: hierarchical clustering on z-scored profiles**
```r
d <- dist(profile_z, method = "euclidean")
hc <- hclust(d, method = "ward.D2")
regimes <- cutree(hc, k = NULL, h = threshold)
```

`threshold` chosen to give ~2-5 regimes for a typical candidate.
Adaptive: cut where the gap in fusion levels is largest.

**Method B: ranking-equivalence groups**
```r
# Each window gets a ranking signature string
sig <- function(row) paste(row$pi_rank, row$dXY_rank, row$Fst_rank,
                            sep = "|", collapse = "")
window_sigs <- sapply(seq_len(nrow(profile_dt)), function(i) sig(profile_dt[i,]))
# Windows with identical signatures form a regime group
regime_by_sig <- as.integer(factor(window_sigs))
```

This gives discrete regime IDs. Method A gives continuous similarity;
Method B gives strict equivalence classes. **Both are useful — A for
visualization, B for the binary "same regime?" decision.**

### Switch detection along the genome

Walk through windows in genomic order. A **switch** is a transition
between regimes. For double-crossover detection, the key pattern is:

```
window order:    1   2   3   4   5   6   7   8
regime:          R1  R1  R1  R2  R2  R1  R1  R1
                          ^─switch─^─return─^
```

Algorithm:

```r
detect_switches <- function(regime_ids, min_run = 2) {
  # Find runs of constant regime
  runs <- rle(regime_ids)
  switches <- list()
  for (i in seq_len(length(runs$lengths) - 2)) {
    # A "return switch" pattern: R1 ... R2 ... R1 with all runs >= min_run
    if (runs$values[i] == runs$values[i+2] &&
        runs$values[i] != runs$values[i+1] &&
        runs$lengths[i+1] >= min_run) {
      window_start <- sum(runs$lengths[seq_len(i)]) + 1
      window_end   <- window_start + runs$lengths[i+1] - 1
      switches[[length(switches) + 1]] <- list(
        type = "return_switch",
        regime_outer = runs$values[i],
        regime_inner = runs$values[i+1],
        window_idx_start = window_start,
        window_idx_end   = window_end
      )
    }
  }
  switches
}
```

A **return switch** = double-crossover signature.
A **terminal switch** (no return) = boundary to a different inversion.
A **brief switch** (single-window) without return is suppressed by
`min_run` (default 2 windows = 100 kb of sustained different signal).

### Output

```json
fingerprint.json:
{
  "candidate_id": "LG28_15.115_18.005",
  "n_windows": 116,
  "n_regimes_method_A": 2,
  "n_regimes_method_B": 3,
  "feature_names": ["pi_A", "pi_B", ...],
  "windows": [
    {
      "idx": 0,
      "start": 15115000, "end": 15165000,
      "regime_A": 1, "regime_B": 1,
      "ranking_signature": "1,2,3|1,2,3|1,3,2",
      "profile_z": [0.3, -0.5, 0.1, ...]
    },
    ...
  ],
  "switches": [
    {
      "type": "return_switch",
      "regime_outer": 1, "regime_inner": 2,
      "window_idx_start": 38, "window_idx_end": 42,
      "bp_start": 16365000, "bp_end": 16585000,
      "interpretation": "putative_double_crossover_or_recombinant_tract"
    }
  ],
  "verdict": "one_inversion_with_recombinant_tract"
}
```

`verdict` is a heuristic label:

| Pattern | Verdict |
|---|---|
| All windows same regime | `stable_inversion` |
| One return switch, brief | `one_inversion_with_recombinant_tract` |
| One terminal switch, two halves | `two_adjacent_inversions` (consider splitting) |
| Multiple non-returning switches | `complex_architecture_check_alignment` |
| Same regime overall but added substructure mid-region | `nested_rearrangement` (needs Stage 4) |

---

## Stage 4: per-sample regime painting and event classification

Stage 3 detects cohort-level regime switches; this stage answers two
finer-grained questions:

1. **Which samples** drive the switch? (carrier identification)
2. **What kind of event** does each carrier represent? (event
   classification — single crossover, double crossover, gene
   conversion-like)

Stage 4 is **the most reliable output of the fingerprinter**. It
operates per-sample on per-window dosage state, so it's robust even
when the cohort-level statistics are noisy (small carrier sets,
hatchery family inflation). It can run independently of Stage 3 if
the user already has a candidate carrier list from PCA.

### Stage 4a — carrier identification (cohort-level signal)

For each window in the inner regime of a return-switch (putative
recombinant tract):

```r
# Per-sample state assignment from dosage in window
# Reference centroids: cohort-level means in HOM1, HET, HOM2 bands
ref_centroids <- compute_band_centroids(dosage, bands)

# Each sample's state per window: which band's centroid is closest?
sample_state_outer <- assign_state(dosage[, outer_window_idx], ref_centroids)
sample_state_inner <- assign_state(dosage[, inner_window_idx], ref_centroids)

# Carriers: samples whose state differs between outer and inner
crossover_carriers <- which(sample_state_outer != sample_state_inner)
```

### Stage 4b — pre-screen carriers from PCA (alternative entry)

If Stage 3's cohort-level switch detection is too noisy (small carrier
sets, severe family structure), enter Stage 4 directly via PCA-based
pre-screening:

```r
# For each sample, compute per-window deviation from its assigned band's
# centroid. Samples whose PC score wanders away from their band centroid
# in some windows but not others are candidate carriers.
per_sample_deviation <- compute_pc_deviation_per_window(pca_results, bands)

# Flag samples whose deviation exceeds threshold in ≥2 contiguous windows
# but not across the whole candidate
candidate_carriers <- flag_localized_deviation(per_sample_deviation,
                                                threshold = 2.0,    # SDs
                                                min_run = 2)        # windows
```

This entry point is the **subset-of-catfish-first** workflow: identify
candidate carriers from per-sample deviation, then proceed to Stage 4c
event classification. It bypasses the cohort regime track entirely and
is more sensitive to small carrier sets.

### Stage 4c — event classification (the diagnostic)

**The headline signature**: in real hatchery (and most natural)
cohorts, the dominant — typically near-exclusive — carrier pattern is:

```
HOM-flank → HET-tract → HOM-flank
(same HOM state on both sides)
```

This is what the fingerprinter is actually detecting in the vast
majority of real cases. The full classification table below catalogues
the other theoretical patterns for completeness, but **expect 95%+ of
detected carriers to fall into this single category**. Other patterns
are either rare biology or, more often, indications that the carrier
flag is a false positive (centroid drift, mappability artifact,
unusual but non-recombinant haplotype).

**Practical implementation note**: the simplest version of Stage 4 is
a one-shot HOM→HET→HOM detector. Per carrier, ask:

1. Are flanks consistent (same HOM state on both sides)? If no, defer
   to the full table below.
2. Is the tract HET? If yes, classify as `double_crossover`, done.
3. Is the tract anything other than HET? If yes, flag as
   `atypical_pattern_inspect_manually` and defer to the full table.

This covers the dominant case cleanly. The full table is the reference
for the minority of carriers that fall outside the dominant signature.

For each identified carrier:

1. **Determine flanking arrangement state** from non-tract windows:
   - Compute mean dosage in flanking windows (typically the 5+ windows
     on either side of the tract)
   - Assign state by closest match to {HOM1, HET, HOM2} centroids
     computed from non-carriers only

2. **Determine in-tract arrangement state** from tract windows:
   - Same procedure but for windows inside the putative recombinant tract
   - Critical: reference centroids come from **non-carriers** in the
     same tract windows, so they represent the "normal" arrangement
     profiles in that region

3. **Classify the event** by comparing flank vs tract state:

| Flank | Tract | Event classification | Expected frequency | Mechanism |
|---|---|---|---|---|
| HOM1 | HET | `double_crossover` | **dominant** | One chromatid switched to arrangement B in tract via two crossover events; returns to A at second crossover. Textbook DCO signature. |
| HOM2 | HET | `double_crossover` | **dominant** | Mirror of above |
| HET | HOM1 | `gene_conversion_or_single_chromatid_dc` | **rare** | Tract gene conversion (B→A on one chromatid); DCO of an already-recombinant chromatid; or rare single-chromatid event. Real biological signal but uncommon. |
| HET | HOM2 | `gene_conversion_or_single_chromatid_dc` | **rare** | Mirror of above |
| HOM1 | HOM2 (return) | `tract_gene_conversion_both_chromatids` | **very rare** | Both chromatids' tract converted to opposite arrangement. Almost always implies the carrier flag is wrong, or the cohort centroids are unreliable in those windows. Inspect manually. |
| HOM2 | HOM1 (return) | `tract_gene_conversion_both_chromatids` | **very rare** | Mirror of above |
| HOM1 | HOM2 (terminal, no return) | `single_crossover_or_adjacent_inversion` | varies | Single crossover within the inversion changes arrangement to the end of the chromosome — looks identical at the per-sample level to a sample carrying a second adjacent inversion. Distinguishable only by external evidence (e.g., breakpoint mapping). |
| HOM2 | HOM1 (terminal, no return) | `single_crossover_or_adjacent_inversion` | varies | Mirror of above |
| HET | HET (same flanks both sides) | `apparent_no_event` | possible | Carrier flag may be false positive, OR the carrier's specific haplotype combination differs from the cohort HET centroid (legitimate but not an inversion event). |

### Why the frequency column matters

Empirically, in PCA per-window movement of carriers, **HOM-flank → HET-tract is by far the dominant signature**, and **HET-flank → HOM-tract events are rare to nearly absent**. This isn't a sampling artifact — it's predicted by the genetics:

- **HOM → HET (DCO)**: requires one parent to contribute a DCO chromatid (one B segment in an A background, or vice versa). DCOs occur in HET parents during meiosis at appreciable rates; the DCO chromatid is then inherited. **Common.**

- **HET → HOM (gene conversion)**: requires gene conversion of an entire tract, which is mechanistically rare because gene conversion tracts are typically short (~100 bp – 1 kb in most species). Converting the whole inversion tract is biologically unusual. **Rare.**

- **HOM → HOM-opposite (both chromatids converted)**: both chromatids' tracts must be converted in the same generation. Astronomically unlikely except in specific contexts (somatic mitotic recombination, pedigree errors, etc.). **Very rare.**

This means: **when Stage 4 flags a HET-flank carrier with a HOM-tract classification, treat it skeptically.** The more likely explanations, in order:

1. The cohort HET centroid is poorly defined in those windows (few HET samples reach those windows reliably; centroid drifts toward HOM)
2. The "carrier" is actually a sample with an unusual but non-recombinant haplotype combination
3. The mappability of those windows is unusual, distorting dosage estimates
4. Genuine but unusual gene conversion event (after ruling out the above)

**The asymmetry between HOM-flank and HET-flank events is itself a finding.** When reporting carrier events for the paper, count and report the ratio. A strong HOM-flank dominance is consistent with DCO-mediated flux and matches the standard biology. A near-equal split suggests either a young inversion (insufficient time for the asymmetry to develop), a pedigree-structured cohort confounding the analysis, or unusual recombination dynamics in this candidate.

### Stage 4d — asymmetry reporting

Across all carriers in a candidate, compute the **flank-state distribution** and report it alongside individual classifications:

```json
"carrier_asymmetry": {
  "n_carriers_total": 9,
  "n_HOM1_flank": 5,
  "n_HOM2_flank": 3,
  "n_HET_flank": 1,
  "n_other": 0,
  "HOM_to_HET_dominance_ratio": 8.0,   // (HOM1 + HOM2) / HET
  "interpretation": "HOM-flank dominance consistent with DCO-mediated gene flux"
}
```

Interpretation rules:
- HOM/HET ratio > 5 → "consistent with DCO-mediated flux" (textbook expectation)
- HOM/HET ratio 2-5 → "moderate DCO signal, some gene conversion"
- HOM/HET ratio < 2 → "atypical asymmetry; investigate centroid reliability and pedigree structure"
- HET-flank events with HOM-tract classifications → flag each individually for manual review

4. **Confidence score** per classification:

```r
event_confidence <- function(carrier, flank_dosage, tract_dosage,
                             centroids_flank, centroids_tract) {
  # Distance to assigned state's centroid, normalized by between-state distance
  flank_score <- 1 - dist_to_centroid(flank_dosage, centroids_flank[carrier$flank_state]) /
                     mean_between_centroid_distance(centroids_flank)
  tract_score <- 1 - dist_to_centroid(tract_dosage, centroids_tract[carrier$tract_state]) /
                     mean_between_centroid_distance(centroids_tract)
  min(flank_score, tract_score)
}
```

Confidence < 0.7 → flag for manual inspection. The carrier may be a
mosaic of multiple events, or the cohort centroids may be poorly
defined in those windows.

### Output

```json
"recombinant_carriers": [
  {
    "sample_id": "S0042",
    "tract_window_idx_start": 38, "tract_window_idx_end": 42,
    "tract_bp_start": 16365000, "tract_bp_end": 16585000,
    "flank_state": "HOM1",
    "flank_dosage_mean": [0.05, 0.08, 0.06, 0.04, ...],
    "tract_state": "HET",
    "tract_dosage_mean": [1.02, 0.94, 1.08, 0.96, ...],
    "event_classification": "double_crossover",
    "confidence": 0.94,
    "interpretation": "double_crossover_HOM1_HET_HOM1"
  },
  {
    "sample_id": "S0103",
    "tract_window_idx_start": 38, "tract_window_idx_end": 42,
    "flank_state": "HET",
    "tract_state": "HOM1",
    "event_classification": "gene_conversion_or_single_chromatid_dc",
    "confidence": 0.81,
    "interpretation": "loss_of_B_chromatid_in_tract"
  }
]
```

Plus a TSV summary:

```
recombinant_event_summary.tsv:
sample_id   flank_state   tract_state   event_type                              confidence
S0042       HOM1          HET           double_crossover                          0.94
S0103       HET           HOM1          gene_conversion_or_single_chromatid_dc    0.81
S0117       HOM1          HET           double_crossover                          0.87
S0182       HOM2          HET           double_crossover                          0.78
S0211       HOM2          HET           double_crossover                          0.93
```

### What this enables

For the paper, instead of:

> "5 samples carry a recombinant tract."

You can write:

> "Of 226 individuals, 5 carried localized arrangement-state changes in
> the central 200 kb (windows 38-42, 16.37-16.59 Mb). Four were
> classified as double crossovers (homozygous-to-heterozygous-to-
> homozygous transitions, returning to the same flanking state; mean
> confidence 0.88), and one as a partial chromatid-level event with a
> heterozygous flanking state (confidence 0.81). All five carriers
> were excluded from the clean-core haplotype tree (HANDOFF 5)."

That's forensic, per-sample, mechanistically interpretable.

### Why this is the most reliable output

Stage 4 is more robust than Stage 3 (cohort regime detection) because:

- It operates per-sample, not on cohort statistics → not confounded by
  family structure
- The reference centroids come from non-carriers in the same windows →
  controls for window-specific artifacts (mappability, repeat density)
- Confidence scores let downstream code distinguish clean events from
  ambiguous ones
- It can detect events affecting just 1-2 samples, which cohort-level
  Stage 3 cannot

For hatchery cohorts where double crossovers are rare events (1-15%
carrier fraction), Stage 4 is the workhorse.

### Handing off to HANDOFF 5

The carrier list (with event classifications) becomes
`--exclude_samples` for the clean-core tree. Excluded samples are
flagged with their event type so the methods can describe exactly what
was excluded:

> "Samples carrying recombinant tracts in the inversion core (n=5: 4
> double crossovers and 1 partial-chromatid event) were excluded from
> the haplotype tree to avoid contamination of clade structure by
> mosaic haplotypes."

---

## Stage 5: population-level inversion signatures

This stage looks at **cumulative, population-level patterns** of gene
flux across the inversion, complementing Stage 4's per-sample event
detection. The two operate at different time scales and answer
different questions:

| Stage | Question | Time scale |
|---|---|---|
| Stage 4 | Which individuals carry recombinant tracts right now? | Current generation events |
| Stage 5 | Has gene flux shaped the inversion's diversity landscape over its history? | Cumulative over many generations |

Both can show up in the same candidate. A young inversion may have
abundant Stage 4 carriers but no Stage 5 signature (insufficient time
for cumulative effects). An old inversion may show clean Stage 5
signatures but few current carriers (events accumulated, but
between-arrangement divergence may now suppress further flux).

### 5a — suspension-bridge test for cumulative gene flux

Theoretical prediction (Navarro et al., Andolfatto et al., literature
cited in inversion review papers): if gene flux occurs preferentially
in the middle of an inversion (because double crossovers and gene
conversion are easier to complete far from breakpoints), the
between-arrangement divergence pattern across the inversion should
look like:

```
dXY(HOM1, HOM2) value
   ▲
   │  ●─────────────────●     ← high near breakpoints
   │   ●               ●
   │     ●           ●
   │       ●       ●
   │         ●● ●●         ← low in middle (gene flux mixed things)
   │
   └─────────────────────► position along inversion
       L_breakpoint    R_breakpoint
```

This is the "suspension bridge" pattern. Per-window dXY between bands
is already in Stage 1's profile vector — no new computation needed.

```r
# For each window in the candidate, extract dXY(HOM1, HOM2)
dxy_track <- window_profiles$dXY_HOM1_HOM2

# Test for the bridge shape: edges high, middle low
edge_dxy   <- mean(c(head(dxy_track, 3), tail(dxy_track, 3)))
middle_dxy <- mean(dxy_track[ceiling(length(dxy_track)/2) - 1:1 + 1])
bridge_ratio <- edge_dxy / middle_dxy

# Bridge interpretation
if (bridge_ratio > 1.5) {
  signature <- "suspension_bridge"
  interpretation <- "evidence of historical gene flux concentrated in inversion middle"
} else if (bridge_ratio < 0.7) {
  signature <- "inverted_bridge"
  interpretation <- "atypical; possibly breakpoint-proximal sweeps or alignment artifacts"
} else {
  signature <- "flat_or_noisy"
  interpretation <- "no clear bridge pattern; inversion may be young, or recombination strongly suppressed"
}
```

Output:

```json
"suspension_bridge_test": {
  "edge_dxy_mean": 0.0048,
  "middle_dxy_mean": 0.0019,
  "bridge_ratio": 2.53,
  "signature": "suspension_bridge",
  "interpretation": "evidence of historical gene flux concentrated in inversion middle"
}
```

The bridge ratio threshold (1.5) is heuristic and should be tuned per
cohort. For paper-grade claims, a permutation test (shuffle window
order, recompute, see how often a ratio ≥ observed arises by chance)
gives a real p-value but is optional for the first pass.

### 5b — on "reciprocal" gene flux and what we observe

The literature describes gene flux as **reciprocal**: across many DCO
events over evolutionary time, variation flowing from arrangement
A → B is balanced by variation flowing B → A. This produces the
suspension-bridge pattern as both arrangements become more similar in
the middle of the inversion.

**However, reciprocity is a population-level statistical property,
not a directly observable predicate at the per-individual level**.
Specifically:

- A single DCO event in a HET parent produces 4 chromatids: 2
  unchanged, and 2 reciprocal recombinants (one with an A-on-B
  background, one with B-on-A). These reciprocal chromatids are
  inherited by **different offspring**.
- In a population sample, you observe individual carriers but cannot
  generally pair up siblings from the same meiosis.
- The "reciprocity" appears only as the integrated suspension-bridge
  signature over many cumulative events, not as observable sibling
  pairs in your dataset.

So when Stage 4 reports, say, 8 HOM1-flank DCO carriers and 3
HOM2-flank DCO carriers, **the asymmetry is expected** — sampling,
hatchery family structure, and selection can all bias which carriers
end up in your cohort, with no requirement that observed events
balance reciprocally.

### 5c — nested-rearrangement test

For windows where the outer regime persists but with **extra
within-band substructure**, look for emergent K-cluster expansion in
that window's local PCA:

```r
# Effective K via gap statistic or BIC on per-window PCs
local_K <- estimate_K_local(pc1[window_idx], pc2[window_idx])
```

If `local_K > overall_K` for a contiguous run of windows, those windows
have **extra substructure**.

If the inner-regime substructure also has the same dXY ranking as the
outer regime (just with band B splitting into B1/B2 internally), the
verdict is `nested_rearrangement`.

If the inner-regime substructure has a **different** dXY ranking, it's
not nested — it's a different inversion overlaid on the candidate
(complex case).

---

## Stage 6: visualization

Three plots per candidate:

### Plot 1: regime track along the genome

```
position  →  ─────────────────────────────────────────────
regime A: ████████████████░░░░░░░░░████████████████
regime B:                 ████████░░               
                                  ░░               (recombinant tract)
                          ↑ switch ↑ return
```

X-axis = bp; y-axis = regime ID; colored bars per window.

### Plot 2: profile heatmap

Rows = windows, columns = features (pi_A, pi_B, ..., dXY_A_B, ...).
Color = z-score. Easy to spot which features change at the switch
boundary.

### Plot 3: per-sample recombinant carrier track

For each crossover carrier sample, show their state assignment per
window as a colored row. The recombinant tract appears as a colored
gap in the row.

```
                15.1Mb  15.5Mb  16.0Mb  16.5Mb  17.0Mb  17.5Mb  18.0Mb
                ────────────────────────────────────────────────────
S0042  state:   B B B B B B B B A A A A B B B B B B B B B B B B
S0103  state:   A A A A A A A A B B B A A A A A A A A A A A A A
                              ↑ recombinant tract ↑
```

These align with the regime track from Plot 1.

---

## Outputs

```
fingerprints/<candidate_id>/
├── window_profiles.tsv             # per-window feature matrix (incl. age_proxy_*)
├── window_profiles_z.tsv           # z-scored
├── ranking_signatures.tsv          # per-window pi/dXY/Fst ranks
├── regime_assignments.tsv          # method A and method B regime IDs
├── fragment_similarity_matrix.tsv  # Stage 2.5: N×N fragment fingerprint similarity
├── symmetric_repeat_pairs.tsv      # Stage 2.5: matched A↔A' / B↔B' pairs
├── switches.tsv                    # detected regime switches
├── recombinant_carriers.tsv        # per-sample recombinant flags
├── fingerprint.json                # everything as JSON for atlas
├── plot_regime_track.pdf
├── plot_profile_heatmap.pdf
├── plot_fragment_similarity.pdf    # Stage 2.5 heatmap
└── plot_recombinant_carriers.pdf
```

---

## Driver

```bash
bash run_fingerprint_for_candidate.sh \
  --candidate LG28_15.115_18.005 \
  --bands_from pca_results/pca_bi_baseline_unweighted_bi_baseline.json \
  --beagle bi_baseline.beagle.gz \
  --window_size 50000 --window_step 25000 \
  --regime_threshold auto \
  --min_switch_run 2 \
  --min_fragment_snps_high 500 \
  --min_fragment_snps_medium 100 \
  --min_fragment_snps_low 50 \
  --mu 1e-9 \
  --age_tol 0.5 \
  --generation_time_years 3 \
  --out_dir fingerprints/LG28_15.115_18.005/
```

Flags introduced for Stage 2.5:
- `--mu`: per-site, per-generation substitution rate for the age-proxy
  computation. Default 1e-9. The output explicitly labels age-proxy
  columns as "(Mya, assuming μ=X)" so the assumption is never hidden.
- `--age_tol`: relative tolerance for age compatibility between
  fragments (fraction of the larger age proxy). Default 0.5 (i.e.,
  fragments are age-compatible if their age proxies are within 50% of
  each other). Tunable per cohort.
- `--generation_time_years`: for converting age proxy from generations
  to years. Optional; the matrix is reported in both units when given.
- `--min_fragment_snps_high/medium/low`: SNP-count thresholds for the
  reliability tiers (defaults 500/100/50). Fragments below the `low`
  threshold are excluded from the similarity matrix entirely.

### Related literature note

The named-fragment style of analysis used in the *Drosophila
subobscura* literature (e.g., Orengo et al., Sci Rep 2019:
`E_st → E_1+2 → E_1+2+9 → E_1+2+9+3 → E_1+2+9+12`) operates on
**molecularly mapped breakpoints** at named cytological positions. Once
a candidate inversion is confirmed and its breakpoints are mapped via
long-read assembly or PCR breakpoint-spanning, this stage can be
re-invoked with explicit named fragment boundaries instead of regime
boundaries. The fingerprint comparison logic is identical; only the
fragment definition changes.

For a discovery-stage analysis (your current setting), regime
boundaries from Stage 3 are the natural fragment boundaries. As
breakpoint resolution improves with future long-read data, the
fingerprinter results can be regenerated against the refined fragment
map.

---

## Atlas integration

Add a **fingerprint track** in Page-1 candidate mode, sitting above
the heatmap panel:

```
┌──────────────────────────────────────────────────────────────────┐
│ Top controls bar                                                  │
├───────────────────────────┬──────────────────────────────────────┤
│ PCA panel                 │ Heatmap panel                         │
├───────────────────────────┴──────────────────────────────────────┤
│ Fingerprint track                                                 │
│ regime: ████████████████░░░░░░████████████████                    │
│        │                  │     │                                  │
│ switches:                ▲▼     ▲▼   (return switch hover ⇒ list  │
│                                       of recombinant carriers)    │
├──────────────────────────────────────────────────────────────────┤
│ Tree panel                                                        │
└──────────────────────────────────────────────────────────────────┘
```

Hover a switch → highlight the recombinant carrier samples in PCA +
heatmap + tree (uses shared rendering state from HANDOFF 2 Section 10).

Click a regime-track segment → snap cursor to that window range.

---

## Implementation phases

### Phase 1: profiles + clustering (1-2 days)
- Run `region_popstats.c` with windowed mode
- Assemble feature matrix
- Z-score; method A clustering; method B ranking signatures
- Output regime assignments per window

### Phase 2: switch detection (0.5-1 day)
- Walk windows in order; detect return switches and terminal switches
- Apply min_run filter
- Verdict labels

### Phase 2.5: fragment-pair similarity matrix (1 day)
- Split windows into fragments using Phase 2's regime boundaries
- Compute per-fragment fingerprint vector (mean/median of in-fragment
  windows for each feature, including age proxies)
- Build N×N fragment similarity matrix combining cosine, rank-equivalence,
  and age compatibility
- Detect symmetric repeat pairs (A↔A', B↔B') above threshold
- Output `fragment_similarity_matrix.tsv` and `symmetric_repeat_pairs.tsv`
- Plot `plot_fragment_similarity.pdf` (heatmap with symmetric pairs marked)

### Phase 3: per-sample painting (1-2 days)
- Identify recombinant carriers per switch
- Compare per-sample state assignment outer vs inner
- Output carrier list

### Phase 4: visualization (1-2 days)
- Regime track plot
- Profile heatmap
- Per-sample recombinant track

### Phase 5: population-level signatures (1-2 days)
- Suspension-bridge test from per-window dXY (already in profile vector)
- Nested-rearrangement test via local-K estimation per window from PCA
- Asymmetry reporting: HOM-flank vs HET-flank carrier counts

### Phase 6: atlas integration (2-3 days)
- Fingerprint track component
- Hover linkage with PCA/heatmap/tree
- Switch-segment click handlers

Total ~2 weeks for full feature. **Phases 1+2 alone (1-2 days) give
the headline regime track** for paper; Phase 2.5 adds the A-B-B'-A'
diagnostic and age proxy (1 more day); Phase 3 adds the per-sample
carrier list. The minimum paper-grade pipeline is Phases 1+2+2.5+3
(~5 days) — produces regime track + fragment similarity matrix +
recombinant carrier list, no atlas dependency.

---

## Validation checks

For LG28:15.115-18.005 (known-positive control):

1. **Stable inversion expectation**: LG28 is well-characterized;
   fingerprinter should label it `stable_inversion`. If it finds switches,
   investigate — could be real recombinant tracts in specific samples,
   or could be noise.

2. **Window-size sensitivity**: rerun with 25 kb / 50 kb / 100 kb
   windows. Stable regimes should not depend on window size. Switches
   that disappear at larger windows are likely noise.

3. **Step-size sensitivity**: rerun with 50% vs 25% vs 0% overlap.
   Switch boundaries may shift slightly but the regime structure
   should be stable.

4. **Method A vs Method B agreement**: continuous clustering and
   rank-equivalence should largely agree. Disagreements are interesting
   (suggest fine-grained variation within a regime).

5. **Carrier sanity**: identified recombinant carriers should be a
   small minority of samples (typically <5% in clean inversions); if
   the algorithm flags 50% of samples as carriers in a switch,
   something's wrong — could be a regime difference rather than a
   crossover.

6. **Boundary effects**: switches at the very edges of the candidate
   (within 1-2 windows of start/end) are likely flank
   contamination — flag but don't trust.

7. **Fragment-pair symmetry (Stage 2.5)**: for LG28 (expected stable
   inversion), the fragment similarity matrix should have no strong
   off-diagonal symmetric pairs — every fragment is similar to every
   other (one-regime case). For a candidate with a real A-B-B'-A'
   architecture, you'd see two off-diagonal hot spots at symmetric
   positions; LG28 should be the negative control here.

8. **Age-proxy stability**: rerun with `--mu 5e-10` and `--mu 2e-9`.
   Absolute age proxies will scale, but the relative differences between
   fragments (and the symmetric-pair age compatibility verdicts) should
   be stable. If they're not, the age component is doing too much work.

---

## Honest expected performance

The fingerprinter is designed to summarize the recombination landscape
of an inversion candidate. Its reliability **depends on how strong the
signal is** — and that varies a lot by candidate. Here's an honest
calibration of what to expect, before running on real data.

### High-confidence cases (will work)

**Stable inversion, no architecture issues**: detected as a single
regime across the entire candidate. Fragment similarity matrix is
uniformly high. Verdict `stable_inversion` is reliable. LG28's clean
60/106/60 candidate likely falls here.

**Two adjacent inversions with distinct band assignments**: the bands
themselves change halfway through the candidate (e.g., samples that
are HOM in the left half are HET in the right half). Detected cleanly
as a terminal switch. Verdict `two_adjacent_inversions` is reliable.

**Obvious double crossover with a sizable carrier set**: e.g., 5+
samples carry a recombinant tract spanning ≥2 windows. **In essentially
all real cases, these carriers show the HOM-flank → HET-tract →
HOM-flank signature** (HOM1-flank fish wandering into HET territory in
the tract and returning; HOM2-flank fish doing the mirror). The regime
switches and returns; the dXY ranking shifts because some carriers'
arrangement assignment changes locally. Verdict
`one_inversion_with_recombinant_tract` is reliable. The per-sample
carrier list is identifiable. The HOM/HET asymmetry ratio (Stage 4d)
should be high (HOM-flank carriers far outnumber HET-flank ones).

These are the "summarize the recombination landscape" cases that
**this method definitely captures**. Conceptually, this is just
detecting "two different bands along the genome" — which it does.

### Medium-confidence cases (probably work)

**Recombinant tract carried by 1-3 samples** (small carrier fraction):
visible in per-sample dosage painting, but per-window dXY/π/Fst values
shift only slightly because the cohort-level statistics are robust to
a few outliers. Detection depends on whether the per-window switches
exceed `min_switch_run` (default 2 windows). May need tuning. Per-sample
carrier identification (Stage 4) is more reliable than the regime-level
switch detection here, because Stage 4 looks at individual samples'
state changes directly.

**Slight nested rearrangement** where one band acquires sub-structure
locally (band B → B1/B2 in middle windows): visible in Stage 5's
local-K estimation. May or may not show as a Stage 3 regime switch
depending on how much the dXY/dA ranking shifts. The feature-vector
similarity may flag it; the rank-equivalence test may not.

**Inversions with moderate within-arrangement diversity** (some
families dominate certain bands): dA correction helps, but the
fingerprint vector becomes noisier. Topology of the similarity matrix
should still be readable, but the absolute combined scores will be
lower across the board.

### Low-confidence / honest-uncertainty cases

**A-B-B'-A' nested mosaic with subtle A vs B fingerprint differences**:
the symmetric-pair detection assumes A and B are fingerprint-
distinguishable. If A and B differ only in subtle features (e.g.,
similar dXY ranking but different rare-allele fractions), the matrix
won't show clean off-diagonal blocks. We'd find one regime with some
noise rather than two distinct regimes. The honest verdict in that
case is `stable_inversion` with a note that finer-resolution analysis
might be warranted, not a falsely confident `nested_rearrangement`.

**Very old inversions where recombination has homogenized everything
except breakpoint-proximal regions**: fingerprints converge to "looks
like the cohort average" because the within-arrangement diversity
swamps the between-arrangement divergence except very near the
breakpoints. The fingerprinter will report `stable_inversion` even if
the true history is more complex, because the data don't carry the
signal anymore.

**Severe hatchery family inflation**: if a few large families dominate
each band, between-band dXY can be inflated by family-specific
variation rather than arrangement-specific variation. dA partially
corrects this, but if the inflation is severe the regimes become
family-driven rather than arrangement-driven. **Validation check 5**
(carrier-fraction sanity) is the early-warning signal: if the algorithm
flags 30%+ of samples as recombinant carriers in a switch, the regime
is probably family structure not recombination.

**Very small inversions** (~100-200 kb): there isn't enough genomic
space for multiple windows to define a regime. At default 50 kb
windows, you'd have 2-4 windows total — too few for switch detection.
Either skip the fingerprinter for these, or run with smaller windows
(`--window_size 10000 --window_step 5000`) at the cost of per-window
SNP counts dropping into `low` reliability tier.

### What this means for the paper

The honest paper claim is calibrated to the case at hand:

For a **clean candidate** (LG28-like, stable inversion):

> "Window-level diversity-profile fingerprinting supported a single
> coherent regime across the candidate (114/116 windows in regime 1).
> Fragment-pair similarity scores were uniformly high (mean = 0.94),
> consistent with a stable inversion arrangement."

For a **clean recombinant-tract case** (large carrier set, sustained
switch):

> "Diversity-profile fingerprinting identified a regime switch at
> windows 38-42 (16.37-16.59 Mb) carried by 5 of 226 individuals.
> All five carriers showed the canonical double-crossover signature
> (HOM-flank → HET-tract → HOM-flank, returning to the same flanking
> homozygous state on both sides; mean confidence 0.91), consistent
> with a localized recombinant tract within an otherwise coherent
> inversion. The HOM-to-HET flank asymmetry (5:0) matches the
> expected pattern under DCO-mediated gene flux."

For an **uncertain case** (no strong switches but the user suspects
something):

> "Diversity-profile fingerprinting did not identify clear regime
> switches within the candidate, although fragment-pair similarity
> scores showed greater variance in the central 200 kb (windows 22-26),
> warranting further investigation with refined breakpoint mapping."

Avoid: presenting the symmetric-pair test as having found A-B-B'-A'
structure unless the matrix shows two clear off-diagonal hot spots
**and** the sample-level dosage painting (HANDOFF 1's heatmap producer)
shows the corresponding state changes. Two lines of evidence required;
fingerprint matrix alone is suggestive, not conclusive.

### Recommended use

Treat the fingerprinter as a **first-pass diagnostic and visualization
tool**, not a final arbiter. Its output should be:

1. **Looked at by the user** (regime track plot, fragment similarity
   heatmap) — most architectural anomalies are visible by eye
2. **Cross-checked against the per-sample heatmap** — does the regime
   switch correspond to a visible band-state change in carriers?
3. **Cross-checked against the tree** (HANDOFF 5) — do flagged
   recombinant carriers fall in unusual positions on the clean-core
   tree?
4. **Used to flag samples for exclusion** in the clean-core tree — this
   use is robust regardless of whether the regime classification is
   "correct"; the per-sample dosage profile is the ground truth.

The fingerprinter's most reliable output is the **per-sample
recombinant carrier list** (Stage 4), because it's based on
per-sample dosage state directly rather than on cohort-level statistics
that can be confounded by family structure or low SNP counts.

---

## Why this matters for the paper

The fingerprinter answers a question that PCA, heatmap, and tree
collectively can't:

> **"Is this candidate one inversion, or are we accidentally combining
> two adjacent structural variants? And if it's one inversion, which
> samples carry recombinant tracts that should be excluded from the
> clean-core analyses?"**

For your hatchery cohort with possible double crossovers in the middle
of the inversion (your specific concern), the regime track + recombinant
carrier list is **the** diagnostic. It tells you:

- Whether the candidate boundaries are correct (or should be split)
- Which specific samples to drop from HANDOFF 5's clean-core tree
- Whether to flag specific genomic regions as "recombinant" in the
  paper's per-window dosage figure

It also formalizes the scientific argument: instead of saying "this
inversion looks like one block," you can say:

> "Window-level diversity profiles supported a single regime across
> 95% of the candidate (114/116 windows in regime 1; 2 windows in
> regime 2 corresponding to a putative recombinant tract carried by
> 3 individuals). The remaining samples (n=220) showed stable regime-1
> fingerprints across all windows, supporting a single coherent
> inversion."

That's a stronger argument than "PCA shows three bands."

---

## File map

```
mgl_adapter/                          (existing, HANDOFFs 0-4)
└── ...

trees/                                (HANDOFF 5)
└── ...

fingerprints/                         (this handoff)
├── compute_window_profiles.R         (Stage 1)
├── rank_signatures.R                 (Stage 2)
├── cluster_regimes.R                 (Stage 3)
├── detect_switches.R                 (Stage 3)
├── identify_carriers.R               (Stage 4)
├── nested_test.R                     (Stage 5, optional)
├── plot_regime_track.R               (Stage 6)
├── run_fingerprint_for_candidate.sh  (driver)
└── fingerprint_panel.js              (atlas-side rendering)

specs/
└── HANDOFF_6_fingerprinter.md        (this document)
```

---

## What you can ignore

- **Whole-genome scanning**: out of scope. Per-candidate only. (Could
  be a future extension to scan the genome for "regime change points"
  as a candidate-discovery method, but not now.)
- **Phasing**: regime detection works on diploid dosage; phasing helps
  carrier resolution but isn't required.
- **Cross-candidate fingerprint comparison**: future work. Useful for
  asking "do these two unrelated candidates share the same diversity
  architecture, suggesting a common evolutionary mechanism?"

## Pointers to existing code

- `region_stats_dispatcher.R` (uploaded): use `route_to_c_popstats()`
  for the windowed query. Set `fixed_win = "<size>:<step>"` for the
  whole candidate interval as one batch.
- `region_popstats.c` (uploaded): emits per-window per-band π, dXY,
  dA, Fst, Tajima's D, singleton/rare fractions. All columns needed for
  the fingerprint vector are already in the output.
- `LAUNCH_region_popstats.slurm`: existing runner; for fingerprinter,
  run on one chromosome with `--range` set to the candidate interval.
- HANDOFF 1 producer outputs: `pca_bi_baseline_*.json` contains per-window
  cluster labels → band assignments per sample.
- HANDOFF 5 (tree): the recombinant carrier list from Stage 4 should be
  passed to the tree builder as `--exclude_samples` for the clean-core
  tree.

## Pointers to mgl_adapter

- For multi-allelic-aware fingerprints: use `all_pairs.beagle.gz` from
  HANDOFF 1 instead of `bi_baseline.beagle.gz`. The fingerprint vector
  shape is the same — multi-allelic just gives more SNPs per window
  and may sharpen regime boundaries.

## External tools required

- R packages: `data.table`, `ape` (for clustering helpers), `mclust` or
  `cluster` (for regime number selection)
- No external binaries beyond what HANDOFFs 1-5 already use
