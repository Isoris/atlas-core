# SPEC — diversity-atlas `ancestry` page (K=8 + K-sweep + per-Q correlations)

**Status**: scaffold — page reads from static / legacy K-sweep TSVs;
v2 should consume a typed `cohort_ancestry_q_v1` envelope. The K=8
default is the canonical cohort assignment used by all sibling pages.

**Scaffolded in:**

| file | role |
|---|---|
| [`pages/stratified/ancestry.html`](../atlases/diversity/pages/stratified/ancestry.html) | static fragment with K dropdown, cluster bar chart, per-Q correlation matrix |
| [`pages/stratified/ancestry.js`](../atlases/diversity/pages/stratified/ancestry.js) | mount lifecycle, K-sweep navigation, KW + pairwise compute |

**Sister pages**:
- All other diversity pages consume `state.shared.activeQK` (the active K choice) — this is the source page

---

## 1. The biological hypothesis

> The 226-sample cohort is **structured** — it isn't a single panmictic
> population. NGSadmix at multiple K values decomposes each fish into a
> proportion vector Q over inferred ancestry clusters. Differences in
> per-sample diversity (θπ, F_ROH, het) **should correlate with Q
> composition** — high-Q-cluster-1 fish may show different θπ from
> high-Q-cluster-3 fish.

K=8 is the **canonical cohort assignment** — chosen because at lower K
the cohort under-splits (some biologically real sub-clusters merge);
at higher K the model over-fits (clusters become noise-dominated).
The user can sweep K = 2..20 to see how the structure changes.

The headline question this page answers: **which Q clusters drive the
cohort's diversity variance?**

## 2. Data input

**v1 today** (static):
- `data/diversity/ancestry_q_K8.tsv` — per-sample Q vector at K=8 (8 columns, summing to 1)
- `data/diversity/ancestry_q_sweep.tsv` — long form: sample × K × cluster → q-proportion
- `data/diversity/per_sample_h_froh.tsv` — per-sample H and F_ROH (joined for the correlation matrix)

**v2 target** (envelope-aware): a typed `cohort_ancestry_q_v1` envelope:

```
payload.q_per_sample[i] = {
  sample_id: string,
  K: integer,           // 2..20
  q: number[],          // length K, sums to 1
  hard_call: integer,   // index of max(q); -1 for admixed (max < 0.7)
}
payload.summary = {
  available_K: number[],          // K values shipped, e.g. [2, 3, ..., 20]
  canonical_K: integer,            // default K used by sibling pages (e.g. 8)
  cohort_n: integer,
}
```

Producer: NGSadmix sweep from `/mnt/e/results_population/03_ngsadmix/` (cross-atlas read — produced by the population-atlas's analysis pipeline, consumed here).

## 3. The three views

### 3.1 K selector + per-K cluster sizes

A K dropdown (K = 2..20) plus a horizontal bar showing the n_samples per
cluster at the selected K. Hard-call assignment per sample:

```
hard_call(sample) = argmax_k q[k]    if max(q) ≥ 0.7
                  = -1 (admixed)     otherwise
```

The 0.7 threshold is the standard "hard-call vs admixed" cutoff in
population-genetics; producers can override.

Visual cue: clusters with n_samples < 5 are flagged amber (likely
over-split at this K).

### 3.2 Per-cluster diversity summary table

For the selected K, per cluster c:

| col | computation |
|---|---|
| `cluster` | 1..K |
| `n_samples` | count of hard-called samples in cluster c |
| `mean_H` | per-sample heterozygosity, averaged within cluster |
| `sd_H` | within-cluster SD |
| `mean_F_ROH` | per-sample F_ROH, averaged within cluster |
| `mean_theta_pi` | per-sample θπ summary, averaged within cluster |
| `kw_p_H` | Kruskal-Wallis one-vs-all p-value for H (this cluster vs all others) |
| `kw_p_F_ROH` | same for F_ROH |

KW p-values are Bonferroni-corrected by K (the multi-cluster test count). Significant rows highlighted in red.

### 3.3 Per-Q correlation matrix

Spearman correlation between each q[k] (k = 1..K) and the per-sample
metrics (H, F_ROH, mean_θπ). Render as a K × 3 matrix; cell colour:
red = positive correlation, blue = negative; cell text = ρ (Spearman).

Significant cells (Bonferroni-corrected by K × 3) get a bold border.

This view is **richer than the hard-call table** because it uses the
continuous Q vector — a sample that is 60% cluster-1 + 40% cluster-3
contributes to both clusters' correlations, weighted by its q value.

## 4. The math

### 4.1 Kruskal-Wallis one-vs-all

For each cluster c at the active K:

```
group_c     = { H values for samples hard-called to c }
group_other = { H values for all other hard-called samples }
                (admixed samples — hard_call == -1 — are excluded)
KW H statistic + asymptotic chi-squared p, as in SPEC_chromosomes_page.md §4.2
```

Bonferroni: `p_bonf_c = min(1, p_c × K)`.

### 4.2 Spearman correlation

For each (cluster k, metric m ∈ {H, F_ROH, theta_pi}):

```
rho_km = Spearman(q[s,k] for s in cohort,
                  m[s] for s in cohort)
```

Spearman is rank-based — robust to outliers and doesn't assume
linearity. Significance test: t-statistic on Fisher-transformed ρ:

```
t = rho × sqrt((n - 2) / (1 - rho²))
df = n − 2
p = 2 × (1 − t_CDF(|t|))
```

Bonferroni divisor: K × 3 = 24 at K=8.

### 4.3 K-sweep diagnostics

When the user sweeps K, the page can show:

- **Per-K cluster-size distribution**: bar chart row per K, columns = cluster sizes. As K increases, clusters subdivide. Visual stability cue: the canonical K is where additional splits produce singletons or near-singletons (over-fitting onset).
- **Per-K cross-validation likelihood** (when producer ships it): NGSadmix reports a log-likelihood per K; the canonical K is often the elbow of the LL-vs-K curve.

These are reference plots, not statistical tests. v2 should ship the LL-vs-K curve as a small inset.

## 5. State + interaction

- `state.shared.activeQK` — the active K (default 8); set by the K dropdown; consumed by sibling pages (`burden`, `roh`, `texture` stratification pills)
- `state.shared.activeCluster` — currently null; v2 could let the user click a cluster row to scope sibling pages to that subset

## 6. Failure modes

| # | condition | behaviour |
|---|---|---|
| 6.1 | A cluster has n_samples < 3 | KW excluded; row greyed; correlation still computed but flagged |
| 6.2 | All samples admixed at the selected K | hard-call table is empty; correlation matrix still works (uses continuous q) |
| 6.3 | Sweep TSV missing some K values | available K's render; missing K's omitted from the dropdown |
| 6.4 | Per-sample H or F_ROH missing | sample excluded from that metric's KW + correlation; counts adjusted |
| 6.5 | Q vector doesn't sum to 1 | producer-side bug; render warning; normalize q in-page (divide by sum) |
| 6.6 | Q vector has negative values | producer-side bug; clamp to 0 + renormalize, with a console warning |
| 6.7 | Canonical K = N (cohort_n) | every sample is its own cluster; KW + correlation degenerate; render an over-split warning |

## 7. What's currently NOT modelled

### 7.1 Envelope-aware data source

The page reads from static TSVs today. v2: a `cohort_ancestry_q_v1` adapter + cross-atlas read from population-atlas's NGSadmix pipeline.

### 7.2 Choice of the canonical K

K=8 is hard-coded as the cohort canonical. Producer should ship `summary.canonical_K` and the page should default to that. v2.

### 7.3 K-stability / bootstrap

NGSadmix is stochastic — multiple runs at the same K give slightly different Q. A v2 robust pipeline would ship the **modal cluster assignment** across N independent runs + a stability score per sample. Today the producer ships one run; the page is unaware.

### 7.4 Tree of Q correlations

A v2 view could compute the Q-vector cosine-similarity tree across samples (a sample-similarity dendrogram from Q) and render it next to the correlation matrix. Out of scope today.

### 7.5 Per-K KW + correlation re-compute

Today's page recomputes everything on K change. For a 226-sample cohort × 20 K values × 3 metrics, that's tractable in-browser. For larger cohorts, pre-compute the KW + correlation per K in the producer and ship as part of the envelope.

### 7.6 Admixed-sample exclusion vs inclusion in KW

KW excludes admixed samples (hard_call = -1) per §4.1. An inclusive version would assign admixed samples to **their dominant cluster regardless of q-threshold** and run KW on the broader groups. Decision: KW is rank-based and robust; the exclusion is conservative. v2 might expose a toggle.

## 8. Cross-page links

This page is the **source** for `state.shared.activeQK`. Every sibling page consuming the stratification pill reads K from here:

- [`roh`](SPEC_roh_page.md), [`burden`](SPEC_burden_page.md), [`texture`](SPEC_texture_page.md), [`samples`](SPEC_samples_page.md) — when stratification is `K=8 cluster`, the page reads this atlas-state and groups its data accordingly
- [`hotspots`](SPEC_hotspots_page.md) — heatmap column ordering uses `state.shared.activeQK` to group columns by cluster
- [`divergence`](SPEC_divergence_page.md) — when nodes are "K=8 ancestry groups", the K choice is read from here

## 9. UI surface

```
┌────────────────────────────────────────────────────────────┐
│ status badge — canonical K = 8 · n samples · n clusters    │
├────────────────────────────────────────────────────────────┤
│ K dropdown: K = 2 3 4 5 6 7 [8] 9 10 ...                   │
│ cluster bar (n_samples per cluster)                        │
├────────────────────────────────────────────────────────────┤
│ Per-cluster diversity summary (sortable)                   │
│   cluster · n · mean_H · mean_F_ROH · mean_θπ · KW(H) · KW(F_ROH) │
├────────────────────────────────────────────────────────────┤
│ Per-Q correlation matrix (K rows × 3 metric columns)       │
│   cell: ρ, colour-coded; sig cells get bold border         │
├────────────────────────────────────────────────────────────┤
│ [Export TSV: cluster summary] [Export TSV: correlations]   │
└────────────────────────────────────────────────────────────┘
```

## 10. Promotion criteria

| criterion | v1 | v2 |
|-----------|----|----|
| K dropdown + cluster bar render | ✓ | ✓ |
| Per-cluster table renders + KW computes | ✓ | ✓ |
| Per-Q correlation matrix renders | ✓ | ✓ |
| Bonferroni-corrected highlights | ✓ | ✓ |
| Envelope-aware (`cohort_ancestry_q_v1`) | ✗ | required |
| Adapter pair shipped (cross-atlas read from population-atlas) | ✗ | required |
| Cluster click → state.shared.activeCluster | ✗ | nice-to-have |
| K-stability / multi-run consensus | ✗ | future |
| 25+ assertion JS smoke | ✗ | required |

## 11. Open biological design questions

### 11.1 Hard-call vs soft-stratification

Most sibling pages use the hard-call (sample → one cluster) for stratification. The continuous Q vector is more biologically honest (a 50/50 admixed sample shouldn't be force-assigned). v2 should support soft-stratification (weighted regression) on at least the headline metrics. Today: hard-call only.

### 11.2 What's the "right" K

This is the canonical question in admixture analyses. There's no single right answer; biologists use a combination of: NGSadmix LL elbow, sub-cluster stability across runs, prior knowledge of the system (in catfish: known hatchery origin populations). The page surfaces K=8 as the default but the user can sweep — that's the right level of opinion for a research tool.

### 11.3 Q outliers

A sample whose Q vector is extreme (one q[k] > 0.99) for an unexpected k may be a contamination event or a mis-assigned sample. A v2 "Q outlier flag" column would surface these for manual review.

### 11.4 Cross-K comparison

Are cluster #3 at K=8 and cluster #5 at K=10 the same biological group? Q-matching across K (via the Hungarian algorithm on q-vector overlap) would answer. Currently each K is treated as an independent labeling. Out of scope.
