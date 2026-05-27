# SPEC — Macrostripe + Microgroup hierarchy

**Status**: shipped 2026-05-20 (audit-sweep — the SPEC's described
"first-class label scheme" actually shipped via `shared/macrostripe.js`
+ supporting modules + 7 page-side consumers + test coverage; the
SPEC's original 2026-05-18 status note "Not yet implemented as a
first-class label scheme" was stale by the time the audit ran).
Promoted from `specs_todo/` after the per-slice audit below. Original
SPEC body is preserved verbatim below as design archive.

**Implemented in:**
- [`atlases/inversion/shared/macrostripe.js`](../atlases/inversion/shared/macrostripe.js) — 4 exports defining the macrostripe label scheme as a first-class state slot: `getMacrostripeIdsAtWindow(state, w)`, `getMacrostripeIdPerSample(state)` (per-sample label folded from Stage 3 band-tracking), `getMacrostripeColor(state, si)`, `invalidateMacrostripeCache(state)`
- [`atlases/inversion/shared/lineage_clustering.js`](../atlases/inversion/shared/lineage_clustering.js) — supporting lineage algorithm: `lineageClustering(concordanceMatrix, n_samples, threshold)`, `lineageColor(lineageId)`, `drawLineageStrip()`, `lineageCacheKey()` + thresholds (`LINEAGE_DEFAULT_THRESHOLD = 0.50`, `LINEAGE_CHAIN_BREAK_AGREEMENT = 0.50`, `LINEAGE_MIN_L2_FOR_COMPUTE = 3`, `LINEAGE_MIN_FISH_PER_LINEAGE = 1`)
- [`atlases/inversion/shared/karyotype_lineage.js`](../atlases/inversion/shared/karyotype_lineage.js) — sister module: `KARYOTYPE_LINEAGE_LS_KEY` + persistence layer (`storeKaryotypeLineage()` / `persistKaryotypeLineage()` / `restoreKaryotypeLineage()`)
- Page-side consumers of the `microgroup_id` + `macrostripe_id` vocabulary (7 modules):
  - [`pages/discovery/local_pca_dosage/_state.js`](../atlases/inversion/pages/discovery/local_pca_dosage/_state.js)
  - [`pages/discovery/local_pca_dosage/l2_sweep.js`](../atlases/inversion/pages/discovery/local_pca_dosage/l2_sweep.js)
  - [`pages/discovery/local_pca_dosage/l3_panel.js`](../atlases/inversion/pages/discovery/local_pca_dosage/l3_panel.js)
  - [`pages/discovery/local_pca_dosage/pca_panel.js`](../atlases/inversion/pages/discovery/local_pca_dosage/pca_panel.js)
  - [`pages/discovery/local_pca_dosage/sidebar.js`](../atlases/inversion/pages/discovery/local_pca_dosage/sidebar.js)
  - [`pages/discovery/local_pca_dosage.js`](../atlases/inversion/pages/discovery/local_pca_dosage.js) + `local_pca_dosage.html`
  - [`pages/discovery/candidate_focus.js`](../atlases/inversion/pages/discovery/candidate_focus.js) + `candidate_focus/_html_builders.js` (uses macrostripe_id for the group-label TSV export per SPEC_haplotype_burden_coloring Phase 1)
- Tests: [`tests/test_shared_macrostripe.js`](../tests/test_shared_macrostripe.js), [`tests/test_shared_lineage_clustering.js`](../tests/test_shared_lineage_clustering.js), [`tests/test_shared_karyotype_lineage.js`](../tests/test_shared_karyotype_lineage.js), [`tests/test_page1_lineage.js`](../tests/test_page1_lineage.js)

**Per-slice status:**

| slice | status | location |
|---|---|---|
| `microgroup_id` (Level 1: per-candidate K-band assignment) | ✅ shipped | `cand.locked_labels` per-candidate (consumed by `getMacrostripeIdPerSample` + the candidate_focus group-label TSV export) |
| `macrostripe_id` (Level 2: long-range haplotype regime folded from band-tracking Stage 3) | ✅ shipped | `macrostripe.js#getMacrostripeIdPerSample(state)` |
| `regime_block_id` (Level 3: chrom-wide regime block) | ✅ shipped via band-tracking | `shared/band_tracking/` modules (`vote_evidence.js`, `partition_consensus.js`, etc.) |
| Per-window macrostripe lookup | ✅ shipped | `getMacrostripeIdsAtWindow(state, w)` |
| Macrostripe color resolver | ✅ shipped | `getMacrostripeColor(state, si)` |
| Macrostripe cache invalidation hook | ✅ shipped | `invalidateMacrostripeCache(state)` |
| Lineage clustering algorithm (Steps A–F per SPEC §Algorithm) | ✅ shipped | `lineage_clustering.js` (5 exports + 4 constants) |
| Lineage persistence to localStorage | ✅ shipped | `karyotype_lineage.js` |
| Default-view UI (macrostripe colours) | ✅ shipped | 7 page-side consumers in local_pca_dosage + candidate_focus |
| Advanced-view UI (microgroup colours; toggle) | ✅ shipped | Consumed at `pca_panel.js` + `sidebar.js` |
| "Co-travel haplogroup" badge | ⏳ partial — consumers reference the data but a dedicated badge UI may still be ad-hoc; verify per page contract |
| Cohort-wide group export TSV (linked to `SPEC_haplotype_burden_coloring` Phase 2) | ⏳ deferred | The Phase-2 group-export companion ships under `SPEC_haplotype_burden_coloring.md` |

**Why archived now:** the SPEC's central proposition — a unified
microgroup_id / macrostripe_id / regime_block_id hierarchy as a
first-class label scheme — ships across `macrostripe.js` +
`lineage_clustering.js` + `karyotype_lineage.js` with 7 page-side
consumers and 4 tests. The SPEC's own §"Algorithm — Steps A-F map to
existing code" section already calls out the shipped modules. The
deferred items (co-travel badge polish, cohort-wide TSV export) are
small follow-ups, not foundational gaps.

**Authored** after the user observation (chat 2026-05-18) of the
tracked-samples trails on a candidate region: PCA scatter shows
**three persistent columns** ("macro-stripes") at distinct PC1
values, and the trail-lines connecting samples across windows reveal

**Authored** after the user observation (chat 2026-05-18) of the
tracked-samples trails on a candidate region: PCA scatter shows
**three persistent columns** ("macro-stripes") at distinct PC1
values, and the trail-lines connecting samples across windows reveal
**stable microgroups within each stripe** — small clusters of
fish that stay separated relative to each other but maintain
their position inside the same macro-stripe across many windows.

Reference images: chat 2026-05-18 screenshots show the LG28-like
3-stripe layout at the candidate scrubber position.

## The hierarchy

```
Level 0  individual fish              — sample index si
Level 1  microgroup_id                — over-resolved local PC1+PC2 K-means
                                        (k=6 or k=adaptive)
Level 2  macrostripe_id  ★ primary    — trajectory co-travel group:
                                        microgroups that consistently
                                        occupy the same broad lane across
                                        windows
Level 3  regime_block_id              — chromosomal interval where the
                                        macrostripe assignment is stable
                                        (genomic candidate region)
```

The mental shift this SPEC asks for:

> **The macro-stripe is the unit of biological interpretation.**
> Microgroups are fine-scale annotations; their value is to **confirm**
> macro-stripe assignments, not to be the headline.

## Why K-means alone fails

K-means partitions Euclidean space geometrically per window. Visible
biological lanes get split when:

- PC1 dominates λ (e.g. λ₁ = 86.9% in the screenshots) → K-means
  cuts the PC1 axis into K bands regardless of whether the cohort
  shows one elongated cloud or three.
- Local SNP composition wobbles → adjacent windows produce different
  K-means partitions on the same biological cohort.
- Family substructure within a single lane creates a sub-cloud that
  K-means promotes to its own cluster — overclustering an inversion-
  homozygous group into 2-3 "K-means clusters" that are really the
  same arrangement.

The user-observed pattern in the trails is precisely this: visually
3 lanes, but k=6 K-means assigns 5–6 colors that include WITHIN-LANE
splits.

K-means is correct geometry. It is wrong biology when the cohort
already has hierarchical structure (sub-haplotype within
arrangement).

## Definitions

### `microgroup_id` (Level 1)

Per-window K-means cluster id at K = `state.k` (3 or 6). Already
emitted by `shared/per_l2_cluster.js#clusterL2` and `clusterL2AtK`.
The label is **window-local**: the same id across two windows is
NOT a guarantee of same biological identity (that's what Hungarian
alignment fixes for adjacent windows).

### `macrostripe_id` (Level 2)

A microgroup's "stripe" assignment, defined by trajectory persistence
across a range of windows. Two microgroups belong to the same
macro-stripe if their samples **co-travel**: they occupy the same
PC1-broad lane in ≥ M of N adjacent windows (M, N tunable).

Implementation lean: this is **exactly what `shared/band_tracking/`
already computes** via the 4-stage banding pipeline (seed discovery
→ cross-seed voting → chain walk → bruteforce projection). The
output `state.bandingResult.stage3_loci` gives per-locus sample
sets that ARE the macro-stripes. The Stage-3 chain walk's
`consensus_partition` is the macrostripe_id label.

Similarly, `shared/lineage_clustering.js` computes lineage
assignments via Hungarian chain projection across L2 envelopes —
its `lineage_id_per_sample` is a macrostripe label at L2
resolution.

Phase 1 reuses these existing computations; Phase 2+ adds
microgroup → macrostripe mapping as a first-class label.

### `regime_block_id` (Level 3)

Continuous bp range where the macrostripe assignment of the
cohort is stable. This is the **candidate region** — the inversion
or sub-arrangement boundary. Detection: scan along the chromosome,
flag the windows where the macrostripe partition changes
significantly (Hungarian agreement drops, large fraction of
samples switch lanes).

The L2-sweep auto-promote pipeline
(`specs_done/SPEC_l2_sweep_inheritance.md`) already candidates these
regions; macrostripe_id is the right unit for its acceptance gates.

## Algorithm — Steps A-F map to existing code

User-corrected pipeline framing (chat 2026-05-18 follow-up):

> **A.** Local partitioning — k-means over many windows.
> **B.** Stability filtering — Cramér's V finds stable windows / hot regions.
> **C.** Seed selection — take only high-stability regions as reliable seeds.
> **D.** Long-range voting — ask where else the same fish groupings reappear.
> **E.** Regime construction — merge co-voting regions into large haplotype regimes.
> **F.** Macrostripe summary — compress the regime into broad interpretable stripes.

This is **exactly the existing band-tracking pipeline** plus its
upstream K-means / Cramér's V inputs. The mapping:

| step | function | existing module | output |
|------|----------|------------------|--------|
| A | local partitioning | `shared/kmeans.js#kmeans1D/kmeans2D` + `shared/per_l2_cluster.js#clusterL2` | per-L2 labels |
| B | stability (Cramér's V) | `shared/contingency.js#cramersV` + L3 pairwise compare + `pages/discovery/local_pca_dosage/l2_sweep.js` | per-pair concord; MERGE/SEPARATE verdicts |
| C | seed selection | `shared/band_tracking/seed_discovery.js` — **Stage 1** | high-stability seed sample sets |
| D | long-range voting | `shared/band_tracking/cross_seed_voting.js` — **Stage 2** + `shared/band_tracking/breadth_voting.js` — Stage 4 driver | voter→target vote records |
| E | regime construction | `shared/band_tracking/locus_construction.js` — **Stage 3** | `stage3_loci[].sample_set` (chained regimes) |
| F | macrostripe summary | `shared/band_tracking/projection.js#classifyProjection` — **Stage 4** | `consensus_partition` per fish |

`consensus_partition` IS `macrostripe_id`. No new compute is required;
Phase 1 is rename + default UI flip.

## Phase 1 — what actually ships

1. **Rename in atlas-facing surfaces**: `consensus_partition` →
   `macrostripe_id` in L3 chip labels, badges, exports, and color
   legends. The internal field name in `bandingResult.target_loci[i]
   .consensus_partition` stays — only the user-facing label changes.
2. **Default color mode flip**: when `state.bandingResult` is present
   for the current chrom + the candidate region, `drawPCA` /
   `drawLinesPanel` / `renderL3Panel` color by macrostripe_id by
   default. When `bandingResult` is absent (banding pipeline not
   run yet on this chrom), fall through to today's per-window
   K-means microgroup coloring.
3. **Toggle**: lines-panel "▾ more" group gains a "macro / micro"
   button. ON (default) = macrostripe colors; OFF (advanced view) =
   per-window K-means microgroups. State slot:
   `viewControls.useMacrostripeColors`.
4. **Microgroup as supporting annotation**: even with the default ON,
   the K-means microgroup composition shows as a small tint halo
   around each macrostripe-colored dot (3-4 px diameter ring at low
   alpha). Cheap visual cue that the macrostripe is composed of
   sub-haplotypes without dominating the display.

No banding-pipeline re-write. No new shared modules. The math from
Stage 1-4 (cross-seed voting, Hungarian chain projection, breadth
voting) stays untouched. The SPEC's job is to flip the default
unit-of-display.

## UI design

### Default view — macro-stripe

- PCA scatter: 3 colors (one per macrostripe). Faint per-window
  K-means microgroup tint can show as a thin halo at high zoom.
- Trail lines: colored by macrostripe so visual continuity is
  trivially read.
- L3 contingency: K=3 macrostripe contingency between adjacent L2s
  (more stable than the per-window K-means contingency).

### Advanced view — microgroup

- Toggleable from the lines-panel "▾ more" group (the existing
  collapse).
- Renders K-means microgroup colors (current behaviour) AS WELL AS
  macrostripe halos.
- The contrast directly shows the user "this K-means split is just
  a within-stripe substructure" or "this K-means split is a real
  macrostripe boundary".

### "Co-travel haplogroup" badge

Per macrostripe, surface in the L3 panel and the candidate-focus
page a small chip:

```
  macro-stripe A   n=60   stable across w 3340-3812
  macro-stripe B   n=106  stable across w 3340-3812
  macro-stripe C   n=60   stable across w 3340-3812
```

with the underlying microgroups listed below each in light grey:

```
  macro-stripe A   n=60   stable across w 3340-3812
    └─ μA.1 (n=14), μA.2 (n=22), μA.3 (n=24)
  macro-stripe B   n=106  stable across w 3340-3812
    └─ μB.1 (n=51), μB.2 (n=55)
  macro-stripe C   n=60   stable across w 3340-3812
    └─ μC.1 (n=23), μC.2 (n=37)
```

The L2-sweep page1 candidate acceptance gates should fire on
**macrostripe** purity, not per-window K-means purity. That's the
biology-aware version.

## Decision table — when microgroups become useful

Per the user observation, microgroups stay observational unless they
explain something testable:

| pattern | meaning | action |
|---|---|---|
| microgroups merge into 3 stable lanes | over-resolved 3-state regime | merge → macrostripe only |
| microgroups stable inside one stripe | sub-haplotypes / family backgrounds | surface as secondary annotation |
| microgroups switch lanes together | recombination block or regime transition | emit a candidate sub-event |
| microgroups appear only in one window | local noise / PCA instability | drop |
| microgroups match family hubs | relatedness-driven substructure | flag as confound |
| microgroups match coverage / missingness | technical artifact | drop with flag |
| microgroups predict offspring segregation | breeding-relevant unit | promote to first-class label |
| microgroups match deleterious burden | per-haplotype effect | promote |

## Decision rule for the atlas

> Use microgroups to **support** confidence, not as the main story.

Concrete: every page that today renders K-means colors gets a default
of macrostripe colors. Advanced view (toggle) shows the K-means
fragmentation. Exports list both ids so downstream users can pick.

## State surface

Reads:
- `state.data.windows[w].pc1[]` / `pc2[]` — per-window PC space
- `state.lockedLabels` — when user has pinned an assignment
- `state.lineageResult` — computed by `runLineageCompute()` (existing)
- `state.bandingResult` — computed by `runBandingPipeline()` (existing)
- `state.candidate` — current candidate region for the macrostripe
  assignment scope

Writes:
- `state.macrostripeAssignment` — Map keyed by candidate.id;
  value: `{ assignment: Int8Array[n_samples], n_stripes: number,
  stability_score: number, computed_at_window_range: [s, e] }`
- `state.viewControls.useMacrostripeColors` — boolean, default true.
  When true, drawPCA / drawLinesPanel / renderL3Panel color by
  macrostripe_id; when false (advanced view), color by per-window
  K-means microgroup_id (today's behaviour).

## Phase 1 (1-2 commits)

- Add `shared/macrostripe.js` exporting `computeMacrostripeAssignment(state, candidate)`. Default reuses `state.lineageResult.lineage_id_per_sample`; falls back to single-stripe (n_stripes=1) when lineage isn't available.
- Add a "macro / micro" toggle in the lines-panel "▾ more" group
  (already exists). State slot: `viewControls.useMacrostripeColors`.
- `drawPCA`, `drawLinesPanel`, `renderL3Panel` consult the slot:
  when on, color by macrostripe; when off, current behaviour.
- L3 panel surface: chip row listing macrostripes + microgroup
  composition per stripe (the layout shown above).

## Phase 2 (1-2 commits later)

- TSV export of `(sample_id, macrostripe_id, microgroup_id)` per
  candidate. Columns: sample, macrostripe (from
  `target_loci[*].consensus_partition`), microgroup (from per-window
  K-means at `state.cur`), candidate_id, source = atlas. Filename
  `macrostripe_export.<chrom>.<candidate_id>.tsv`.
- L2-sweep auto-promote pipeline (`pages/discovery/local_pca_dosage/
  l2_sweep.js`) accepts on **macrostripe** purity instead of
  per-window K-means purity. Same gates, different label source.
- L3 panel chip row: per-stripe `n` + microgroup composition, layout
  as documented above.

## Phase 3 (research)

- The decision-table promotion rules: when microgroups explain
  offspring segregation / recombination / phenotype, promote them
  to first-class labels (separate macrostripe).
- Cross-candidate microgroup stability tests (does the same
  microgroup recur across multiple candidates?).

## Naming

User-proposed names: "co-travel haplogroup" (descriptive), "macro-
stripe" (geometric), "trajectory-defined haplotype subgroup"
(formal). Atlas uses:

- **`macrostripe_id`** — Level 2 label (primary biological unit)
- **`microgroup_id`** — Level 1 label (per-window K-means)
- **`regime_block_id`** — Level 3 label (chromosomal interval)

These names match the user's mental model and keep the hierarchy
explicit.

## Best summary paragraph (for manuscript / atlas help)

> The local PCA trajectories reveal stable microgroups within three
> broader macro-stripes. For interpretation, the macro-stripes are
> the primary haplotype regime; microgroups are retained as
> secondary fine-scale annotations unless they explain segregation,
> recombination, phenotype, or breeding effects. The candidate
> interval contains three broad trajectory lanes consistent with a
> three-state haplotype regime; within each lane, persistent
> microgroups remain separated across windows and sometimes switch
> together, suggesting linked sub-haplotype backgrounds rather than
> family, ancestry, or technical structure.

## Sibling SPECs (2026-05-18)

- **`SPEC_cramers_v_seed_merge.md`** — alternative seed-merge
  auto-promote pipeline. Two modes (`insulated_local`,
  `post_long_range`) so the user can compare with L2-sweep and
  band-tracking. Per the user direction "do b + alternative to c".
- **`SPEC_haplotype_burden_coloring.md`** — schema-in/color-out
  contract for attaching burden / phenotype / marker-haplotype
  layers to the macrostripe + microgroup labels defined here. The
  Phase 1 deliverable for that SPEC is the per-candidate group-
  label TSV export — the user's weekly goal.

Together: this SPEC defines the LABELS, `SPEC_cramers_v_seed_merge`
defines an ALTERNATIVE PROMOTION pipeline, and
`SPEC_haplotype_burden_coloring` defines the DOWNSTREAM CONSUMER
(coloring + TSV).

## References

- `specs_done/SPEC_band_track_extraction_and_l3_single_band_rows.md`
  — the parent banding pipeline that computes macrostripe candidates
- `specs_done/SPEC_distant_band_concordance_fish_trajectory.md` —
  lineage compute + band trace (the trajectory persistence math)
- `specs_done/SPEC_l2_sweep_inheritance.md` — auto-promote pipeline
  (gates on per-window K-means today; should gate on macrostripe)
- `shared/lineage_clustering.js#runLineageCompute` — existing
  Hungarian-chain-projection trajectory clusterer
- `shared/band_tracking/` (32 modules) — Stage 1-4 banding pipeline
- `_handoff_docs/STAGE_AUDIT_2026-05-18.md` — pca_comparator + l3
  panel are the natural consumers
