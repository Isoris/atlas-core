# SPEC — diversity-atlas `divergence` page (group-divergence network)

**Status**: scaffold. Builds on the existing
[_handoff_docs/SPEC_2026-05-12_divergence_network.md](../_handoff_docs/SPEC_2026-05-12_divergence_network.md)
legacy spec (4-month-old design doc), which already covers the
biological reasoning + math. This SPEC layers the envelope-aware
contract + UI behaviour + cross-page hooks on top.

**Scaffolded in:**

| file | role |
|---|---|
| [`pages/stratified/divergence.html`](../atlases/diversity/pages/stratified/divergence.html) | static fragment with node-link SVG, edge filter caret menu, layout toggle |
| [`pages/stratified/divergence.js`](../atlases/diversity/pages/stratified/divergence.js) | mount lifecycle, force / circular layout, edge filtering, node drag |

**Sister pages**:
- [`ancestry`](SPEC_ancestry_page.md) — source of `state.shared.activeQK` which defines the default node set (K=8 clusters)
- [`burden`](SPEC_burden_page.md), [`roh`](SPEC_roh_page.md) — stratification-pill consumers; the divergence page is the **inter-group** view to their **per-group** views

---

## 1. The biological hypothesis

> Given a partition of the cohort into N groups (default: K=8 ancestry
> clusters), the **pairwise genetic distance** between each pair of
> groups should reveal the population structure as a graph: tightly
> connected nodes share recent ancestry; loosely connected nodes are
> diverged.

This is the **same single-view answer** to "how different are the
groups?" that the cohort has already (implicitly) computed via the K=8
ancestry decomposition — but visualised as a single node-link graph
rather than a matrix of pairwise stats.

The legacy [SPEC_2026-05-12_divergence_network.md](../_handoff_docs/SPEC_2026-05-12_divergence_network.md)
is the authoritative source for:
- Node design (one node per group; size ∝ within-group π)
- Edge design (one edge per pair; thickness ∝ divergence; colour-coded by significance / direction)
- Statistics used (FST, DXY, dA — choose at producer time)
- Layout (circular default; force-directed toggle)

This SPEC focuses on the **atlas-side contract**: envelope shape, UI
behaviour, cross-page hooks. The math + figure design live in the
legacy SPEC.

## 2. Data input

**v1 today** (static):
- `data/diversity/divergence_K8.tsv` — long form: (group_a, group_b, fst, dxy, dA, n_snps_used)
- `data/diversity/within_group_pi.tsv` — per-group within-group π (node size driver)

**v2 target** (envelope-aware): a typed `cohort_divergence_network_v1` envelope:

```
payload.nodes[i] = {
  group_id:       string,        // e.g. "K8_cluster_3"
  group_kind:     "K8" | "farm" | "sex" | "karyotype",  // partition type
  n_samples:      integer,
  within_pi:      number,        // mean within-group π — drives node size
  within_pi_ci:   [number, number],  // 95% CI for the node-size diagnostic
}

payload.edges[i] = {
  group_a:        string,
  group_b:        string,
  fst:            number | null,
  dxy:            number | null,
  dA:             number | null,        // = dxy − (pi_a + pi_b) / 2 (the net divergence)
  n_snps_used:    integer,
  bootstrap_ci:   { fst: [number, number], dxy: [number, number], dA: [number, number] } | null,
}

payload.summary = {
  partition_kind: "K8" | "farm" | ...,
  n_groups:       integer,
  n_edges:        integer,        // n_groups × (n_groups − 1) / 2
  stat_choice:    "fst" | "dxy" | "dA",  // producer's primary stat for edge-thickness
}
```

Producer: cross-atlas read from population-atlas's pairwise-FST pipeline +
local-π aggregation. Adapter pattern follows the cookbook.

## 3. The view

A single SVG node-link diagram filling the page body.

### 3.1 Nodes

- One node per group at the active partition
- **Position**: circular layout by default (n groups placed evenly on a circle); force-directed alternative (gravity ∝ within_pi; spring length ∝ chosen edge stat)
- **Radius** ∝ √within_pi (proportional area, not radius, so the visual area matches π magnitude)
- **Fill**: per-group colour from a deterministic palette (e.g. K=8 → 8 distinct hues)
- **Label**: `group_id` text inside the node when radius is large enough; outside as a tooltip otherwise

### 3.2 Edges

- One edge per pair (n × (n − 1) / 2 edges; K=8 → 28 edges)
- **Thickness** ∝ the chosen stat (`fst` by default; user can swap via §4 control)
- **Colour**: black by default; colour-coded by stat magnitude in v2 (red → high FST, blue → low; per-stat scale)
- **Visibility filter**: a caret-menu "show edges with stat ≥ threshold" hides edges below threshold (default: show all)
- **Click**: opens a side panel showing the edge's full stats + bootstrap CI + the n_snps_used

### 3.3 Caret-menu edge filter

A small dropdown at the top right of the SVG:
- Edge stat: FST | DXY | dA
- Min threshold slider (per stat)
- "Show CI band" toggle (renders edges with width = 2 × CI half-width, plus a centre line at the point estimate)

## 4. State + interaction

- `state.shared.activeQK` — read; the page picks the K=8 (or active K) partition
- `state.shared.activeGroup` — set on node click; sibling pages can scope to a group's samples
- `state.shared.activeEdge` — set on edge click; sibling pages can show the pair-specific θπ / F_ROH / burden contrast

## 5. The math

Per the legacy [SPEC_2026-05-12_divergence_network.md](../_handoff_docs/SPEC_2026-05-12_divergence_network.md).
Summary of the statistics:

- **Within-group π** (per-group node-size driver):

```
π_within(g) = (1 / |S_g|) × Σ_{i,j ∈ S_g, i ≠ j} per-site heterozygosity(i, j)
```

- **Pairwise FST** (Hudson's version):

```
FST(a, b) = 1 − π_within_avg(a, b) / π_between(a, b)
          = 1 − (π_a + π_b) / (2 × π_between)
```

- **DXY** (absolute divergence):

```
DXY(a, b) = (1 / (|S_a| × |S_b|)) × Σ_{i ∈ a, j ∈ b} per-site differences(i, j)
```

- **dA** (net divergence):

```
dA(a, b) = DXY(a, b) − (π_a + π_b) / 2
```

Bootstrap CI: producer-side resample SNPs (not samples — SNPs are the
unit, samples are fixed) 1000× and emit `[lo, hi]` per stat per edge.

The page **does not re-compute** these — it consumes them. The producer's
math is the canonical version; the atlas is a viewer.

## 6. Failure modes

| # | condition | behaviour |
|---|---|---|
| 6.1 | A group has n_samples < 5 | within_pi is unstable; node rendered with a dashed border + tooltip warning |
| 6.2 | An edge's `n_snps_used` is too low (< 10_000) | edge dashed + tooltip "low-power" warning |
| 6.3 | FST < 0 (numerical artefact from finite samples) | floor to 0; tooltip shows the raw value |
| 6.4 | Bootstrap CI not shipped | render edges with no CI band; the toggle is disabled |
| 6.5 | Force layout doesn't converge | switch back to circular after 5 seconds of jitter; surface a warning |
| 6.6 | Self-loops (group_a == group_b) in producer output | drop with a console warning |
| 6.7 | Partition_kind change mid-session | re-fetch envelope; full SVG redraw |

## 7. What's currently NOT modelled

### 7.1 Envelope-aware data source

Producer pipeline + adapter pair pending. v2 work.

### 7.2 Alternative stats

Beyond FST / DXY / dA: Reynolds' distance, F_ST(Weir & Cockerham), Nei's
genetic distance. Producer chooses one primary stat; the others can be
optional columns. v2 toggle.

### 7.3 Non-K-based partitions

The page accepts `group_kind ∈ {K8, farm, sex, karyotype}` per the envelope. v1 ships K-based only; farm-of-origin / sex / karyotype partitions need the producer to emit them. Future.

### 7.4 Significance of edges

An edge's bootstrap CI tells you the magnitude uncertainty, but not "is this edge significantly non-zero?" A null model — e.g. permute group labels across samples 1000× and recompute FST — would give a per-edge p-value. Out of scope for v1; the within / between contrast is large enough at typical K=8 that significance is rarely the limiting question. Visualisation > p-value here.

### 7.5 Cross-K comparison

Switching K (e.g. K=8 → K=10) gives a different node set. v2 should preserve node positions across K changes (matched by majority-overlap) so the user sees the partition evolve smoothly rather than re-laying-out from scratch.

### 7.6 Edge ordering / curve avoidance

At K=8 with 28 edges, the SVG starts to look cluttered. v2 could:
- Bundle parallel edges (when multiple stats are shown simultaneously)
- Edge-bundle adjacent low-magnitude edges
- Skip-hide low-stat edges by default; user reveals via the filter

## 8. Cross-page links

- Node click → `state.shared.activeGroup = group_id` → sibling pages scope to that group's samples (e.g. `samples` table filters to those rows)
- Edge click → `state.shared.activeEdge = (group_a, group_b)` → `burden` page (when wired) shows the burden differential for those two groups; `hotspots` page shows windows where the two groups diverge most

## 9. UI surface

```
┌────────────────────────────────────────────────────────────┐
│ status badge — partition · n_groups · stat-choice · CIs?   │
├────────────────────────────────────────────────────────────┤
│ ┌─ stat / filter caret menu ─┐                              │
│ │ Edge stat: FST | DXY | dA  │                              │
│ │ Min threshold: [slider]    │                              │
│ │ Show CI band: ☐            │                              │
│ │ Layout: circular | force   │                              │
│ └────────────────────────────┘                              │
│                                                            │
│ ╭──── SVG node-link diagram (circular default) ────╮       │
│ │            ●K8_1──────────●K8_2                  │       │
│ │           /    \           /                     │       │
│ │       ●K8_8     ●K8_3  ●K8_4                     │       │
│ │           \    /                                 │       │
│ │            ●K8_5────●K8_6     ●K8_7              │       │
│ ╰──────────────────────────────────────────────────╯       │
│                                                            │
│ Click node → activeGroup; click edge → activeEdge          │
├────────────────────────────────────────────────────────────┤
│ Edge inspector panel (slides out when an edge is clicked)  │
│   group_a · group_b · fst · dxy · dA · n_snps_used · CIs   │
└────────────────────────────────────────────────────────────┘
```

## 10. Promotion criteria

| criterion | v1 | v2 |
|-----------|----|----|
| Circular layout renders | ✓ | ✓ |
| Force layout toggle | ✓ | ✓ |
| Edge filter caret menu | ✓ | ✓ |
| Click handlers (node + edge → state.shared) | ✓ | ✓ |
| Envelope-aware (`cohort_divergence_network_v1`) | ✗ | required |
| Adapter pair shipped (cross-atlas from population-atlas FST pipeline) | ✗ | required |
| Bootstrap CI rendering | ✗ | required |
| Permutation-based edge significance test (§7.4) | ✗ | nice-to-have |
| Non-K partitions (farm / sex / karyotype) | ✗ | future |
| 25+ assertion JS smoke | ✗ | required |

## 11. Open biological design questions

### 11.1 Which stat for edge thickness

FST is the population-genetics standard but bounded in [0, 1] and can saturate for highly diverged groups. DXY is unbounded and proportional to time. dA removes the within-group component and is the cleanest "between-group divergence" stat. Default decision: FST for visual familiarity; user toggles to DXY/dA for quantitative work.

### 11.2 SNP set for the calculation

Per-edge stats can be biased by:
- SNPs in inversions (LD blocks inflate apparent divergence)
- Recent-mutation SNPs (low frequency, high noise)
- Sex-linked SNPs

Producer should ship `n_snps_used` and document the filter (e.g. "biallelic SNPs in callable regions, MAF ≥ 0.05, excluding inversion candidates"). Different SNP sets give different stat values; the user needs to know which they're looking at.

### 11.3 Within-group π normalisation

Node size ∝ √π means the visual area scales linearly with π. Some prefer linear-radius (so area scales with π²). Per the legacy SPEC, default is √-radius. Aesthetic decision.

### 11.4 Edge symmetry

FST is symmetric (FST(a, b) = FST(b, a)). DXY is symmetric. dA is symmetric. So edges are undirected. A future asymmetric stat (e.g. directed migration f3 or D-stat tests) would need directed-edge rendering.
