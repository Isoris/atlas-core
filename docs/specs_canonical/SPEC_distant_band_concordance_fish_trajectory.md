# SPEC — Distant Band Concordance / Fish Trajectory

**Status**: SHIPPED (Slices 1 + 2 + 4 — fish-trajectory lineage
compute + lines color mode + band-trace strip) — was SPEC ONLY
(referenced from `specs_done/SPEC_band_track_extraction_and_l3_single_band_rows.md`
+ `docs/MIGRATION_INVENTORY.md` + multiple legacy comments without
an on-disk doc) until 2026-05-15.
**Authored from shipped code + handoffs** (recovery of a missing SPEC).

**Slice plan + status (2026-05-15)**:

| slice | what ships | status |
|-------|-----------|--------|
| **Slice 1** | Pure compute: `runLineageCompute()` — per-L2 dominant fish-trajectory lineage from K-means band trajectories | ✅ shipped (turn 130) |
| **Slice 2** | `lineage` color mode in lines panel — per-sample colour by lineage_id (golden-angle palette); always-available (no layer prerequisite) | ✅ shipped (turn 130) |
| **Slice 3** | Lineage strip on |Z| panel — per-L2 dominant lineage colour bar; grey-hatched gaps for Hungarian-chain breaks | ✅ shipped (turn 130 follow-up) |
| **Slice 4** | Band-trace UI: per-L2 strip above lines panel showing fish-set band occupancy; co-segregation markers + Shannon entropy + regime runs | ✅ shipped (turns 160 + 161, compute + UI) |
| **Slice 5** | TSV export of fish-trajectory tables | ✅ shipped (turn 162 — `_bandTraceDownloadTSV`) |
| **Slice 6** | Cross-strip / cross-chromosome chaining of fish trajectories | 🟡 deferred |

**Implemented in (legacy lines, not yet migrated to modular tree)**:
- `legacy/Inversion_atlas.html` lines 5722-5729 — lineage strip
  HTML control on |Z| panel
- `legacy/Inversion_atlas.html` line 9521+ — `bandTraceFishSet`
  state slot + companions
- `legacy/Inversion_atlas.html` line 9630 — Slice 4 UI doc + state
  layout
- `legacy/Inversion_atlas.html` line 33148 — `'lineage'` entry in
  `_LINES_COLOR_MODES`
- `pages/discovery/local_pca_dosage/lineage.js` — state-managed lineage compute
  wrapper (round-4 split brought it across)
- `shared/clustering.js` — pure clustering primitives
- `pages/discovery/local_pca_dosage/band_trace_state.js` — band-trace state +
  cache (per `state.bandTraceCacheKey`)
- `pages/discovery/local_pca_dosage/band_trace_tooltip.js` — band-trace tooltip
  + hit-test (legacy lines 40026-40202)

**Companion specs**:
- `specs_done/SPEC_band_track_extraction_and_l3_single_band_rows.md`
  (parent — defines the L3 cohort-paths view that this SPEC is the
  fish-paths dual representation of)
- `specs_done/SPEC_lasso_inheritance_backgrounds.md` (consumes
  `state.bandTraceFishSet` as the canonical fish-set source)

---

## §1. Purpose

Provide the **fish-paths dual representation** of the band-track
partition matrices defined by
`SPEC_band_track_extraction_and_l3_single_band_rows.md` (parent).

The parent SPEC operates on **cohort paths** (one row per band
cohort, one column per pane). This SPEC operates on **fish paths**
(one row per fish, one column per L2). Both are dual representations
of the same per-pane K×K transition matrices; both are useful for
different questions:

| representation | row | column | answers |
|----------------|-----|--------|---------|
| **Cohort paths** (parent SPEC) | one band cohort | one pane | "where does this cohort spread when projected through this pane?" |
| **Fish paths** (THIS spec) | one fish | one L2 | "which band of each L2 does this fish land in?" |

Two concrete user-facing surfaces draw on the fish-paths
representation:

1. **Lineage** (Slices 1 + 2 + 3) — automatically cluster fish
   trajectories into lineages via Hungarian-chain projection across
   all L2s; render per-sample colour + per-L2 dominant-lineage strip.
2. **Band-trace** (Slices 4 + 5) — user picks a fish-set; render a
   per-L2 strip above the lines panel showing how that fish-set's
   band occupancy varies along the chromosome.

## §2. Slice 1 — `runLineageCompute()` (shipped turn 130)

### §2.1 Pure compute

Location: `pages/discovery/local_pca_dosage/lineage.js` (state-managed wrapper)
+ `shared/clustering.js` (pure primitives).

Inputs:
- `state.data.l2_envelopes` + per-L2 K-means labels
- `state.k` (default 3 for the operational H-system)

Pipeline:
1. For each L2 envelope, gather K-means labels for all 226 samples.
2. Run **Hungarian-chain projection** across consecutive L2s to
   align label IDs (so lineage 0 means the same thing in L2[0],
   L2[1], L2[2], ...).
3. Where the Hungarian alignment fails (no good chain bridge), mark
   a **chain break** at that L2 boundary.
4. Cluster the per-fish trajectory strings into lineages
   (Hungarian-aligned canonical form).

Outputs (cached on `state.lineageResult` + `state.lineageCacheKey`):
- `lineage_id` per sample
- `dominant_lineage_per_L2` for the |Z| panel strip
- `chain_breaks` array (L2 boundaries where Hungarian failed)

### §2.2 Cache key

`state.lineageCacheKey` is invalidated by:
- chrom change
- `state.k` change
- L2-envelope set change

Forced recompute via `runLineageCompute(state, { force: true })`
(same convention as `SPEC_l2_sweep_inheritance` cache).

### §2.3 No JSON layer prerequisite

Slice 2's defining property: `runLineageCompute` operates on data
the atlas **already has** (per-L2 K-means labels). No upstream
producer needed. This is why the `'lineage'` color mode is **always
available** (no `_isLinesColorModeAvailable` gate).

## §3. Slice 2 — `lineage` lines color mode (shipped turn 130)

### §3.1 `_LINES_COLOR_MODES` entry

```js
{ id: 'lineage', layer: null, label: 'lineage' }
```

`layer: null` means always-available (no `state.layersPresent` check
in `_isLinesColorModeAvailable`).

### §3.2 Color resolver

When `state.linesColorMode === 'lineage'`, the per-sample colour
comes from `state.lineageResult.lineage_id_per_sample[sampleIdx]`
mapped via a **golden-angle palette rotation** (so adjacent lineage
ids get visually distinct hues).

Tracked samples retain their gold/cyan/violet tracking colour; the
lineage colour applies to the rest of the cohort.

## §4. Slice 3 — Lineage strip on |Z| panel (shipped turn 130 follow-up)

### §4.1 Visual

Per-L2 horizontal coloured bar painted just above the |Z| panel
(legacy lines 5722-5729):

- Each L2 painted with the colour of the lineage that dominates its
  largest band.
- Color **changes along the chromosome** where inheritance lineages
  re-organize.
- **Grey-hatched gaps** = Hungarian-chain breaks (the algorithm
  couldn't bridge across these L2s).

### §4.2 Tooltip

> Lineage strip (turn 130): per-L2 dominant fish-trajectory lineage.
> Each L2 painted with the color of the lineage that dominates its
> largest band. Color changes along the chromosome where inheritance
> lineages re-organize. Grey-hatched gaps = Hungarian-chain breaks
> (algorithm couldn't bridge across these L2s). Computed via
> `runLineageCompute()` on K-means band-trajectories — no JSON layer
> prerequisite.

### §4.3 No JSON layer needed

Same property as Slice 2: works on data the atlas already has. The
strip auto-paints whenever the lineage compute has run on the active
chromosome.

## §5. Slice 4 — Band-trace strip (shipped turns 160 + 161)

### §5.1 State surface

```js
state.bandTraceFishSet:    int[] | null    // sample indices to track
state.bandTraceOn:         boolean         // toggle; default OFF
state.bandTraceCache:      trace | null    // last-computed trace
state.bandTraceCacheKey:   string | null   // chrom + fingerprint(fish-set) + K
```

### §5.2 Compute layer (turn 160)

`_bandTraceForFishSet(fishSet, K, l2_envelopes)` → returns a per-L2
trace:

```js
[
  { l2idx, n_fish_in_band: [<K-length array>], dominant_band, shannon },
  ...
]
```

Plus:
- `_bandTraceRegimeRuns` — runs of consecutive L2s where the
  dominant band stays the same. Long stretches of co-segregation =
  candidate inversion footprints.
- `_bandTraceShannonEntropy` — per-L2 information content of the
  band-occupancy distribution. Low entropy = the fish-set is
  pinned to 1-2 bands; high entropy = the fish-set is spread across
  all K bands.

### §5.3 UI half (turn 161)

Per-L2 strip painted above the per-sample-lines panel showing how
the chosen fish-set's band occupancy varies along the chromosome:

- **Co-segregating L2s** (low entropy) → fish-set pinned to 1-2 bands
- **Fanned L2s** (high entropy) → fish-set spread across all K
- **Long stretches of co-segregation** → candidate inversion footprint

Toggleable via the lines header `[ ] band trace` checkbox plus the
`🔍 trace` button to set the fish-set from the current selection.

### §5.4 Observation-only framing

**Defaults: OFF.** The strip is observation-only — it surfaces
co-segregation patterns; it does NOT label them as inversions or
commit to any biological interpretation. That framing is deliberate
(Quentin's request — manuscript stays observational).

## §6. Slice 5 — TSV export (shipped turn 162)

`_bandTraceDownloadTSV(fishSet, traceResult, opts)` — pure
serializer. Per-L2 row with `n_fish_in_band[k]` columns, dominant
band, Shannon entropy, run length. Filename:
`band_trace_<chrom>_n<n_fish>.tsv`. Same headless-safe contract as
the lasso-linkage TSV per
`specs_done/SPEC_lasso_inheritance_backgrounds.md` §3.7.

## §7. Slice 6 — Cross-strip chaining (deferred)

When implemented, would chain fish trajectories across:

- Multiple L3 strips on the same chromosome
- Across chromosomes

This extension would let the user track a fish-set's inheritance
behaviour across the genome, not just within one chromosome. Per
the parent SPEC §1532: "Cross-system band tracks. A future extension
would chain tracks across multiple L3 strips on the same chromosome
(or even across chromosomes). That's
SPEC_distant_band_concordance_fish_trajectory.md's territory
operating at L2 envelopes."

**Deferred** because the L3 single-band-rows view (parent SPEC)
hasn't fully shipped yet — the cross-strip integration point doesn't
exist to write against.

## §8. Why the two surfaces (lineage + band-trace)

The two surfaces answer related but distinct questions:

| surface | scope | input | answers |
|---------|-------|-------|---------|
| **Lineage** | cohort-wide, automatic | all 226 fish, all L2s | "what are the major inheritance trajectories visible in this chromosome?" |
| **Band-trace** | per-fish-set, user-driven | user-picked fish-set, all L2s | "where do THESE fish co-segregate?" |

Lineage is the **discovery view** ("show me what's there");
band-trace is the **investigation view** ("now tell me where this
specific group sticks together"). They're complementary.

## §9. Migration into atlas-core

Most of this SPEC's pieces are still in `legacy/Inversion_atlas.html`
or in the round-4 splits inside `pages/discovery/local_pca_dosage/`. When the
remaining migration happens:

- **Lineage compute** → already at
  `pages/discovery/local_pca_dosage/lineage.js` ✅
- **Lineage palette + color mode resolver** → should land in
  `shared/lineage_palette.js` (golden-angle PRNG)
- **Lineage strip painter** → already part of `pages/discovery/local_pca_dosage/z_panel.js`
  via the strip overlays ✅
- **Band-trace compute** → should land in `shared/band_trace.js` ✅
  (already there per `pages/discovery/local_pca_dosage/band_trace_state.js`'s
  imports)
- **Band-trace strip painter** → already part of
  `pages/discovery/local_pca_dosage/z_panel.js#_drawBandTraceStrip` ✅
- **Band-trace tooltip** → already at
  `pages/discovery/local_pca_dosage/band_trace_tooltip.js` ✅
- **TSV export** → currently in legacy; migration TBD

## §10. References

- **Parent SPEC**: `specs_done/SPEC_band_track_extraction_and_l3_single_band_rows.md`
  (the cohort-paths dual)
- **Compute (lineage)**:
  `pages/discovery/local_pca_dosage/lineage.js#runLineageCompute`
- **Compute (band-trace)**:
  `pages/discovery/local_pca_dosage/band_trace_state.js` +
  `shared/band_trace.js`
- **Color mode entry**: `_LINES_COLOR_MODES` in
  `pages/discovery/local_pca_dosage/lines_panel.js` (search `'lineage'`)
- **Lineage strip painter**:
  `pages/discovery/local_pca_dosage/z_panel.js#_drawLineageStrip`
- **Band-trace strip painter**:
  `pages/discovery/local_pca_dosage/z_panel.js#_drawBandTraceStrip`
- **Band-trace tooltip**:
  `pages/discovery/local_pca_dosage/band_trace_tooltip.js`
- **TSV export**: `_bandTraceDownloadTSV` (legacy turn 162)
- **State slots**:
  - `state.lineageResult`, `state.lineageCacheKey`
  - `state.bandTraceFishSet`, `state.bandTraceOn`,
    `state.bandTraceCache`, `state.bandTraceCacheKey`

---

**Authored**: 2026-05-15 from `legacy/Inversion_atlas.html`
lines 5722-5729 + 9521+ + 9630 + 33148 + the round-4 splits inside
`pages/discovery/local_pca_dosage/`. The LAST of the 8 SPECs identified as
missing on disk in `_handoff_docs/SPECS_AUDIT.md`. **All 8 missing
SPECs now resolved.** Slices 1 + 2 + 3 + 4 + 5 SHIPPED; Slice 6
(cross-strip chaining) deferred until parent SPEC's L3
single-band-rows view ships.
