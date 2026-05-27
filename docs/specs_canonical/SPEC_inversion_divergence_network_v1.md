# SPEC — inversion divergence-network overlay (v1)

**Status**: shipped 2026-05-20 (audit confirmed pre-existing implementation
matches the v1 contract verbatim — same exports, same math, same render-hint
shape). Promoted from `specs_todo/` after the audit. **What ships is the
pure-data layer per §6**; panel wiring (canvas/SVG + hover + click-to-track)
remains a follow-up.

**Implemented in:**
- [`atlases/inversion/shared/divergence_network.js`](../atlases/inversion/shared/divergence_network.js) — `computeDivergenceNetwork` + `divergenceNetworkRenderHints` + the published constants (`DIVERGENCE_NETWORK_SOURCES`, `DIVERGENCE_NETWORK_METRICS`, `DIVERGENCE_LOW_POWER_MIN_N`, `DIVERGENCE_FST_{WEAK,STRONG}_THRESHOLD`, `DIVERGENCE_EDGE_COLORS`, `DIVERGENCE_LABEL_ORDER`)
- [`tests/test_shared_divergence_network.js`](../tests/test_shared_divergence_network.js) — 412-line smoke covering group membership, Nei FST (dosage), variance-ratio FST (pc1), Euclidean distance, low-power/weak/strong flag thresholds, circular layout positions, edge stroke selection from flag
- Imports `XP_K_PALETTE` from [`atlases/inversion/shared/cross_page_clusters.js`](../atlases/inversion/shared/cross_page_clusters.js) for arrangement node colors (per §7)
- Doc-referenced by [`atlases/inversion/pages/catalogue/stats_profile.js`](../atlases/inversion/pages/catalogue/stats_profile.js) (region/genome masking derivation note)

**Scope**: Inversion Atlas only (overlay version)
**Sibling spec**: a future Diversity Atlas version would extend
this with ancestry-group nodes; this spec is intentionally narrow.

**Authored**: drafted 2026-05-12.

---

## 1. What this is

A small, candidate-scoped diagnostic panel: a node-link diagram where

| Element | Meaning |
|---|---|
| **Node** | one karyotype group (STD / HET / INV — or arrangement 0/1/2/... for K > 3) |
| **Node label** | within-group nucleotide diversity π (or heterozygosity, when π is unavailable) |
| **Node size** | sample count in that group |
| **Node color** | arrangement color from the shared K-cluster palette |
| **Edge** | between-group pairwise divergence |
| **Edge label** | FST (or Dxy / dA as alternatives) |
| **Edge thickness** | proportional to divergence magnitude |
| **Edge color** | grey baseline; red when FST ≥ 0.25 (strong); amber 0.10 ≤ FST < 0.25 |

It answers ONE question for the active candidate:

> Is this arrangement *measurably* divergent from the standard, or is the PCA split a within-population artifact?

The signal complements the K-means PCA scatter:
- Page1 PCA = "how do samples cluster?"
- Per-band stats / haplotype_vocab = "how clean is each band?"
- **Divergence network = "do the bands differ in genome content, not just position in PC space?"**

## 2. Why "overlay" and not its own page

The diagram only makes sense in the context of a single candidate's
karyotype calls. It belongs alongside the PCA scatter and the heatmap,
not as a separate top-level page. Implementation:

- One new panel that mounts under the local_pca_dosage PCA scatter when a
  candidate is active (`state.candidate` non-null and has K + locked_labels)
- Empty-state placeholder when the candidate is missing or has K=1
- Rebuilds whenever `state.candidate`, `state.cur`, or the candidate's
  karyotype labels change

The actual DOM/canvas rendering is out of scope for this spec — it
ships in a follow-up. THIS spec defines the pure-data layer that any
renderer (Canvas, SVG, D3, …) reads from.

## 3. Inputs

The compute function takes three required inputs:

```js
computeDivergenceNetwork(state, candidate, karyotypeBySample, opts?)
```

| Arg | Shape | Source |
|---|---|---|
| `state` | the local_pca_dosage state object | `state.data.windows[]`, `state.data.n_samples` |
| `candidate` | a candidate-registry entry | `{id, chrom, K, start_w, end_w, locked_labels?}` |
| `karyotypeBySample` | per-sample label dict OR Array | `{0: 'STD', 1: 'HET', 2: 'INV', ...}` or `['STD', 'HET', ...]` |
| `opts.source` | `'pc1'` or `'dosage'` | which per-sample value drives the math (default `'pc1'`) |
| `opts.metric` | `'fst' \| 'distance'` | edge-weight metric (default `'fst'`) |
| `opts.includeRecombinants` | boolean | when true, RECOMBINANT-labeled samples form their own node (default false: dropped) |

`karyotypeBySample` labels are free strings — typically `'STD' / 'HET' / 'INV'` from
the standard vocab, but also `'arr_0' / 'arr_1' / 'arr_2'` for multi-haplotype K=6 candidates.
Any label is accepted; the function groups by exact string match.

Samples with label `null` / `undefined` / `'RECOMBINANT'` are silently dropped
unless `opts.includeRecombinants` is true.

## 4. Math

### 4.1 Per-window per-sample value

For each window `w ∈ [candidate.start_w, candidate.end_w]`:
- `x[i, w]` = `state.data.windows[w].pca.pc1[i]` (when `source = 'pc1'`)
- `x[i, w]` = `state.data.windows[w].dosage[i]` (when `source = 'dosage'`, IF available)

A window is skipped when its `pc1` / `dosage` is missing.

### 4.2 Within-group stats (node label)

For each group `g` with members `S_g`:

```
n_g       = |S_g|
mean_g(w) = (1/n_g)  Σ_{i ∈ S_g} x[i, w]
var_g(w)  = (1/n_g)  Σ_{i ∈ S_g} (x[i, w] - mean_g(w))²
within_g  = mean across windows of var_g(w)
```

`within_g` is reported as the node label. With `source = 'dosage'`
this is a direct proxy for nucleotide diversity π (the variance of
allele dosage in [0, 2] tracks expected heterozygosity at the
constituent sites). With `source = 'pc1'` it's a coarser "PC1
heterogeneity within group" signal — useful as a diagnostic, not
a manuscript stat.

### 4.3 Edge weight: FST (Nei / Hudson-Slatkin)

For each pair `(g1, g2)`:

```
For each window w:
  m_g(w) = group mean as above
  Let p1 = m_g1(w), p2 = m_g2(w), n1 = |S_g1|, n2 = |S_g2|

  # For dosage values in [0, 2], divide by 2 to get allele freq p ∈ [0, 1].
  # For pc1, work on raw values; FST formula still meaningful as a
  # "variance partition" but loses its allele-frequency interpretation.

  if source == 'dosage':
    p1 = m_g1(w) / 2
    p2 = m_g2(w) / 2
    p_bar = (n1 p1 + n2 p2) / (n1 + n2)
    Hs(w) = (n1 * 2 p1 (1-p1) + n2 * 2 p2 (1-p2)) / (n1 + n2)
    Ht(w) = 2 p_bar (1 - p_bar)
    fst(w) = Ht(w) > 0 ? (Ht(w) - Hs(w)) / Ht(w) : 0
  else:
    # variance-ratio FST_PT for continuous values
    mu      = (n1 m_g1(w) + n2 m_g2(w)) / (n1 + n2)
    SS_t    = Σ_{i in S_g1 ∪ S_g2} (x[i,w] - mu)²
    SS_w    = Σ_{i in S_g1} (x[i,w] - m_g1(w))² + Σ_{i in S_g2} (x[i,w] - m_g2(w))²
    SS_b    = SS_t - SS_w
    fst(w)  = SS_t > 0 ? SS_b / SS_t : 0

fst_pair = mean across windows of fst(w)
```

Negative values (which can arise from finite-sample noise) are clamped to 0.

### 4.4 Edge weight: distance (alternative metric)

```
For each window w:
  dist(w)² = (m_g1(w) - m_g2(w))²
distance_pair = sqrt(mean across windows of dist(w)²)
```

Euclidean distance over the per-window group-mean trajectory.
Independent of FST — useful when FST is dominated by within-group
variance noise (small groups, e.g. only 5 HET samples).

### 4.5 Confidence flagging

For each pair `(g1, g2)`:
- `low_power` if `min(n_g1, n_g2) < 5`
- `weak` if metric < 0.10 (FST) or < 0.5 standard deviations of values
- `strong` if metric ≥ 0.25 (FST) or ≥ 2 σ of values

These tags drive the edge color/thickness in render hints (§5).

## 5. Output shape

```js
{
  meta: {
    candidate_id, chrom, start_w, end_w, n_windows_used,
    source: 'pc1' | 'dosage',
    metric: 'fst' | 'distance',
    generated_at: ISO,
  },

  nodes: [
    {
      id: 'STD',           // group label string
      n: 102,              // sample count
      sample_idx: [/*...*/], // optional, controlled by opts.expose_membership
      within_pi: 0.0012,   // §4.2 result
      mean_pc1: -0.42,     // overall mean across windows (for layout)
      mean_pc2:  0.05,     // (when source='pc1' OR when state.data has pc2)
      color: '#4fa3ff',    // from XP_K_PALETTE (shared/cross_page_clusters.js)
    },
    // ...
  ],

  edges: [
    {
      a: 'STD', b: 'INV',
      fst: 0.45,           // when metric='fst'
      distance: null,      // (other metric is null when not computed)
      flag: 'strong' | 'weak' | 'low_power' | null,
      weight: 0.45,        // normalized scalar driving render thickness
    },
    // ...
  ],

  stats: {
    n_samples_total,
    n_samples_classified,
    n_samples_unclassified,
    n_groups,
    skipped_groups: ['RECOMBINANT'],   // when includeRecombinants=false
  },
}
```

## 6. Render hints (separate helper)

```js
divergenceNetworkRenderHints(network, layout?) → {
  nodes: [{ id, x, y, radius, fill, stroke, ... }, ...],
  edges: [{ a, b, x1, y1, x2, y2, width, stroke, ... }, ...],
}
```

The compute step returns pure stats. The render-hints step adds:
- Node `radius`: scales with sqrt(n) (area-proportional)
- Node `fill`: from `XP_K_PALETTE` mapped by group id when possible,
  else a deterministic hash
- Edge `width`: scales with edge.weight, clipped to [1, 8] px
- Edge `stroke`: grey by default; amber when flag='weak';
  red when flag='strong'; dashed when flag='low_power'
- Layout: simple circular-arrangement positioning when `layout` is
  omitted; pass `{layout: 'force', ...}` to defer to a force-directed
  pass (out of scope for v1; v1 ships circular layout only)

## 7. Where it sits in the cartridge

- `atlases/inversion/shared/divergence_network.js` — pure compute +
  render hints. State-as-first-arg. Imports `XP_K_PALETTE` from
  `shared/cross_page_clusters.js`.
- Page1 wires it in via:
  ```js
  import { computeDivergenceNetwork, divergenceNetworkRenderHints }
    from '../../../shared/divergence_network.js';
  ```
  Karyotype labels come from `haplotype_vocab.js`'s autoClassifier,
  the user's locked_haplotype_labels, or a future inheritance-group
  layer.

The pure data layer (this spec) lands first. The local_pca_dosage panel wiring
(canvas/svg + hover + click-to-track) is a follow-up.

## 8. v1 vs future

**v1 ships:**
- pc1 source + variance-ratio FST
- dosage source + Nei FST (when state.data ships per-sample dosage)
- distance metric as the alternative
- Render hints: radius / fill / width / stroke from precomputed stats
- Circular layout

**Future (not v1):**
- `source = 'theta_pi'` when `state.data.per_sample_theta_pi` ships
- `source = 'allele_count'` for true Dxy / dA via discrete genotype calls
- Force-directed layout
- Permutation test for edge significance (k random shuffles of group labels)
- Diversity-Atlas variant where nodes are ancestry groups instead of arrangements

## 9. Open questions

1. **Single-window vs span-aggregated**: this spec aggregates across
   `[candidate.start_w, candidate.end_w]`. An alternative is per-window
   FST plotted as a small-multiples track. Decision deferred to the
   renderer spec.
2. **What FST estimator** for the manuscript figure: this spec ships
   Nei (clean, intuitive). Weir & Cockerham's θ̂ is the field-standard
   for cohort-level FST; revisit when allele-frequency data lands.
3. **Whether to include RECOMBINANT as its own node**: legacy
   convention is to drop them (their PC1 wobbles between two
   arrangements; treating them as a node smears the diagnostic).
   `opts.includeRecombinants = true` is provided as an escape hatch
   for users who want to see the recombinant-vs-arrangement structure
   explicitly.
