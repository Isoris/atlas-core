# SPEC — diversity-atlas `pruning_qc` page (NAToRA + ngsF-HMM stability + Spearman + het in/out ROH)

**Status**: scaffold.

**Scaffolded in:**

| file | role |
|---|---|
| [`pages/qc/pruning_qc.html`](../atlases/diversity/pages/qc/pruning_qc.html) | static fragment with the 4 view sections (NAToRA pruning, ngsF-HMM stability, Spearman matrix, het in/out ROH) |
| [`pages/qc/pruning_qc.js`](../atlases/diversity/pages/qc/pruning_qc.js) | mount lifecycle, per-section renderers |

---

## 1. The biological + technical hypothesis

> The 226-sample cohort isn't homogeneous in coverage, kinship, or
> ROH-call quality. Before downstream diversity analyses can be trusted,
> the cohort must be **pruned** (close-relative redundancy removed) and
> **quality-controlled** (per-sample stability of inbreeding calls
> validated). This page surfaces the QC layer.

Four orthogonal QC views:

1. **NAToRA pruning** — relatedness-based pruning result: the
   unrelated-subset that downstream analyses should use as the
   reference cohort.
2. **ngsF-HMM stability** — per-sample reproducibility of the
   inbreeding (F) call across pipeline replicates / parameter
   variants. A sample whose F changes wildly with parameter choice
   has an unstable call.
3. **Spearman correlation matrix** — per-metric pairwise correlation
   across the cohort's measured variables (H, F_ROH, F_HMM, θπ, etc.).
   Reveals which stats are redundant vs orthogonal.
4. **Het in/out ROH** — per-sample heterozygosity inside vs outside
   ROH segments. A clean cohort has zero het inside ROH; deviations
   index ROH-boundary errors or sequencing errors.

Together these four views answer: **which samples can we trust
downstream, and which stats are independent enough to combine?**

## 2. Data input

**v1 today** (static):
- `data/qc/natora_pruned.tsv` — per-sample row: `sample_id, pruned (bool), pruned_reason, kept_subset_size`
- `data/qc/ngsf_hmm_stability.tsv` — per-sample F variance across replicates: `sample_id, f_mean, f_sd, f_min, f_max, n_replicates`
- `data/qc/cohort_metric_correlations.tsv` — Spearman ρ matrix
- `data/qc/het_in_out_roh.tsv` — per-sample: `sample_id, het_inside_roh, het_outside_roh, ratio`

**v2 target** (envelope-aware): a `diversity_qc_v1` envelope folding all four sub-tables.

## 3. The four views

### 3.1 NAToRA pruning

NAToRA is a graph-based pruning algorithm: build the kinship graph
(edges where pairwise relatedness ≥ threshold, default 1st-cousin
≈ 0.0625), greedily remove the node with the highest degree until no
edges remain. The remaining set is the unrelated subset.

Table:

| col | source |
|---|---|
| `sample_id` | input |
| `pruned` | bool — true if removed by NAToRA |
| `pruned_reason` | "high_kinship_n_neighbors=X" or null |
| `kinship_max` | the sample's highest pairwise kinship to any other sample |
| `kept_neighbors` | comma-separated list of sample_ids kept that this sample is related to (when pruned) |

Headline: "NAToRA kept N of 226 samples (kinship threshold = 0.0625)".

### 3.2 ngsF-HMM stability

For each sample, ngsF-HMM is run multiple times with parameter
variants (different transition prior, different SNP filter, different
initial F guess). The dispersion of F across these runs measures call
stability.

Table:

| col | meaning |
|---|---|
| `sample_id` | input |
| `f_mean` | mean F across replicates |
| `f_sd` | SD of F across replicates |
| `f_min`, `f_max` | range |
| `n_replicates` | how many runs |
| `unstable_flag` | true if `f_sd > 0.05` (5 percentage points) |

Unstable samples are highlighted in amber. The biology: a stable
F=0.05 sample is reliably mildly inbred; an unstable F=0.05 ± 0.15
sample is genuinely uncertain and downstream stats should treat F as
NA.

### 3.3 Spearman correlation matrix

A square N × N matrix where N is the number of cohort metrics:
H, F_ROH, F_HMM, θπ, mean depth, missing rate, etc. (typically 6–10
metrics).

Cell value: Spearman ρ between metrics m_i and m_j across the cohort.
Cell colour: red (positive), blue (negative); cell text: ρ.

Interpretation:
- High |ρ| between two metrics → they're measuring the same thing;
  downstream models should pick one or use PCA
- ρ ≈ 0 between two metrics → orthogonal information

Bonferroni-corrected highlight on cells with p < α/(N choose 2).

### 3.4 Het in/out ROH

Per sample:

```
het_inside_roh   = #{ het sites in ROH segments } / total het sites in sample
het_outside_roh  = #{ het sites outside ROH segments } / total het sites in sample
ratio            = het_inside_roh / het_outside_roh
```

In an ideal callset: ROH segments are stretches of homozygosity, so
het_inside_roh ≈ 0 → ratio ≈ 0. Real cohorts have:
- Sequencing errors creating spurious hets inside ROH (ratio ~ 0.01 typical)
- ROH-call boundary errors leaving real hets just inside the "ROH" interval
- Mis-mapped reads (paralogous-region duplicates) creating false hets

Samples with `ratio > 0.05` are flagged: either the ROH caller is
mis-calling at this sample, or the sample has unusual sequencing
artifacts. Either case warrants review before downstream use.

## 4. The math

### 4.1 NAToRA pruning algorithm

Inputs: pairwise kinship matrix K (e.g. from ngsRelate).

```
Graph G:
  nodes = samples
  edges = (i, j) where K[i,j] ≥ threshold  (default 0.0625, ≈ 1st cousin)

While G has any edges:
  v = node with maximum degree in G  (tie-break: lowest sample_id)
  Remove v and all incident edges
  Mark v as pruned

Kept set = nodes remaining (no edges)
```

The greedy "remove highest-degree node first" minimises the cohort
loss while breaking all kinship edges. Producer ships the pruning
result; the page renders.

### 4.2 ngsF-HMM stability statistic

Per sample s:

```
f_values_s = [F estimates across N replicates of ngsF-HMM]
f_mean_s   = mean(f_values_s)
f_sd_s     = unbiased SD(f_values_s)
unstable_flag = (f_sd_s > 0.05)
```

The 0.05 threshold is calibrated to "5 percentage points of F
disagreement across reasonable parameter choices" — large enough that
the call is biologically uncertain.

### 4.3 Spearman ρ

Standard: rank both metrics across samples (average rank for ties),
then Pearson correlation on ranks.

```
For two metrics m_i, m_j across N samples:
  rank_i[s] = rank of m_i[s] in m_i across cohort
  rank_j[s] = rank of m_j[s] in m_j across cohort
  rho = Pearson(rank_i, rank_j)
```

Significance: Fisher-transform + standard error per
[SPEC_ancestry_page.md §4.2](SPEC_ancestry_page.md). Bonferroni divisor:
`N_metrics × (N_metrics − 1) / 2` for the matrix.

### 4.4 Het in/out ROH

Per sample s, given the ROH segment set R_s:

```
sites_in_roh(s)  = #{ informative sites at positions ∈ R_s }
sites_out_roh(s) = #{ informative sites at positions ∉ R_s }
het_inside(s)    = #{ het calls at positions ∈ R_s }   / sites_in_roh(s)
het_outside(s)   = #{ het calls at positions ∉ R_s }   / sites_out_roh(s)
ratio(s)         = het_inside(s) / het_outside(s)
```

Threshold for unstable flag: `ratio > 0.05` (5% of het rate inside ROH
relative to outside is the biologically-unexpected-but-tolerable
upper bound).

## 5. State + interaction

- `state.shared.activeSample` — set on row click in any of the four tables; routes sibling pages to that sample's drill-down
- `state.qc.prunedSet` — module-local; cached after first render

## 6. Failure modes

| # | condition | behaviour |
|---|---|---|
| 6.1 | NAToRA kept set empty (everyone is related) | render warning; default to full cohort with a "no pruning applicable" hint |
| 6.2 | NAToRA threshold not shipped by producer | default to 0.0625; show as a chip "threshold = 0.0625 (default)" |
| 6.3 | ngsF-HMM only one replicate per sample | f_sd undefined; stability column reads `—`; instability flag never fires |
| 6.4 | Spearman matrix has missing pairs | render those cells grey |
| 6.5 | Het in/out ratio = ∞ (het_outside = 0; pathological) | clamp to a large value; flag as "review pathological" |
| 6.6 | Sample appears in NAToRA but not in ngsF-HMM | shown only in NAToRA; the other 3 tables drop it |

## 7. What's currently NOT modelled

### 7.1 Envelope-aware data source

Single `diversity_qc_v1` envelope envisioned but adapter pending.

### 7.2 Pruning threshold sensitivity

The 0.0625 threshold is biologically motivated (1st-cousin cutoff). A
0.0156 (2nd cousin) threshold prunes more aggressively; 0.25 (full
sibs) less so. v2 should expose a slider so the user sees how the
kept set changes — this is the single most important QC decision for
downstream cohort definition.

### 7.3 Pruning policy alternatives

NAToRA's "remove highest-degree node" is one of several greedy
strategies. KING-robust kinship + a different tie-break would give
different kept sets. v2 could ship multiple algorithm outputs side-by-
side, letting the reviewer pick.

### 7.4 ngsF-HMM stability — what parameters are varied?

Producer must document the parameter grid that defines the
"replicates". Different grids give different stability numbers. v2
should ship `summary.parameter_grid` so the reviewer knows what's
been tested.

### 7.5 Cross-platform sequencing-batch effect on QC

Batch effects (sequencing run / library prep) influence het rate and
F_HMM stability. v2 should annotate each sample with its batch_id and
visualise per-batch QC distributions side-by-side.

### 7.6 Per-chromosome het in/out ROH

§3.4 aggregates across the whole genome. Per-chrom decomposition
would reveal chromosome-specific ROH-call problems (e.g. a sex chrom
with weird F). v2 nice-to-have.

## 8. Cross-page links

- Active sample → sibling pages (`samples`, `roh`, `texture`,
  `burden`) scope to that sample's drill-down
- NAToRA-pruned subset can be propagated via
  `state.shared.diversityPrunedSet` to filter all downstream pages
- High-instability samples could be hidden cohort-wide via a UI
  filter (v2)

## 9. UI surface

```
┌────────────────────────────────────────────────────────────┐
│ status badge — NAToRA kept N · n_unstable · n_flagged_het  │
├────────────────────────────────────────────────────────────┤
│ Section 1: NAToRA pruning                                  │
│   table: sample_id · pruned · reason · kinship_max         │
├────────────────────────────────────────────────────────────┤
│ Section 2: ngsF-HMM stability                              │
│   table: sample_id · f_mean · f_sd · range · unstable_flag │
├────────────────────────────────────────────────────────────┤
│ Section 3: Spearman correlation matrix                     │
│   N × N grid, cell colour by ρ, sig cells bold border      │
├────────────────────────────────────────────────────────────┤
│ Section 4: Het in/out ROH                                  │
│   table: sample_id · het_in · het_out · ratio · flag       │
└────────────────────────────────────────────────────────────┘
```

## 10. Promotion criteria

| criterion | v1 | v2 |
|-----------|----|----|
| 4 sections render from static data | ✓ | ✓ |
| Pruning threshold slider | ✗ | required |
| Envelope-aware (`diversity_qc_v1`) | ✗ | required |
| Click-row → activeSample | ✓ | ✓ |
| Pruned-set propagation to sibling pages | ✗ | nice-to-have |
| 20+ assertion JS smoke | ✗ | required |

## 11. Open biological design questions

### 11.1 What kinship metric

NAToRA can use any kinship matrix: ngsRelate KING-robust, GRM,
ngsRelate KING-asymmetric, identity-by-descent estimates. The
producer picks one; the page is agnostic. Documentation: ship
`summary.kinship_method` in the envelope.

### 11.2 Stability threshold

`f_sd > 0.05` is the unstable-flag threshold. Producers shipping
deeper replicate sweeps (N ≥ 10 runs) can use a 95-CI-based threshold
instead (`f_q97.5 − f_q2.5 > 0.10`). v2 should expose.

### 11.3 Het-in/out-ROH theoretical zero

In a perfect callset het_inside_roh = 0 exactly. Empirically it's 0.005–0.02. What's the threshold for "this is noise" vs "this is a real problem"? Calibrated against real catfish data; tightened with more sequencing.
