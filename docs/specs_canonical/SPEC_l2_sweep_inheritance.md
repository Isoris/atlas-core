# SPEC — L2 Sweep Inheritance (auto-promote pipeline)

**Status**: SHIPPED — was SPEC ONLY (referenced from local_pca_dosage / local_pca_dosage.html
without an on-disk doc) until 2026-05-15.
**Authored from shipped code** (recovery of a missing SPEC).
**Implemented in**:
- `atlases/inversion/pages/discovery/local_pca_dosage/l2_sweep.js` (444 LOC,
  the full pipeline)
- Called from `atlases/inversion/pages/discovery/local_pca_dosage.js`
  `applyData()` when `state.l2SweepEnabled === true`
- Tests: `tests/test_page1_l2_sweep_*.js` (if present — to verify)

**Page contract**: `docs/generated/page_contracts/local_pca_dosage/`
(L2-sweep listed under `state.l2SweepEnabled` and L2-sweep cartridge
in the subdir map)

**Companion specs**:
- `specs_done/SPEC_band_track_extraction_and_l3_single_band_rows.md`
  (defines L1/L2 envelope construction)
- (planned) `SPEC_lines_panel_candidate_bands.md` —
  `l2_sweep` produces candidates; `lines_panel.js` paints them

**Legacy source**: `legacy/Inversion_atlas.html` lines 41749-42153

---

## §1. Purpose

When the user navigates to a new chromosome (and
`state.l2SweepEnabled === true`), `local_pca_dosage.applyData()` runs an
**inheritance-group clustering over EVERY usable L2 envelope**,
treating each L2 as a synthetic candidate with its K-means labels.
L2 envelopes that pass six gates are **auto-promoted** into
`state.candidateList` with `source = 'auto_l2_sweep'` and
`confirmed = false`.

The promoted entries land in the review UI immediately so the user
can confirm or dismiss them in batch — **without participating in
the inheritance pills until confirmed**.

This is the system's "first-pass candidate discovery" engine. The
human user's job downstream is to confirm or dismiss; the sweep
proposes.

## §2. State surface (inputs)

Read from `state` (the local_pca_dosage atlas state):

| field | type | required | purpose |
|-------|------|----------|---------|
| `state.l2SweepEnabled` | bool | yes | gate; pipeline runs only when true |
| `state.data` | object | yes | the active chromosome's loaded envelope |
| `state.data.chrom` | string | yes | for cache key + dismissed-set localStorage key |
| `state.data.l2_envelopes` | Array | yes | L2 envelope list — each has `start_bp`, `end_bp`, `_s0`, `_e0` |
| `state.k` | number | yes | K=3 by default (locked_labels K) |
| `state.activeMode` | string | no | per-mode cache key suffix |
| `state.candidateList` | Array | yes | for Gate 2 (`ALREADY_IN_CANDIDATE`) + Gate 6 (dedupe radius) |

Mutated by the pipeline:

| field | when | content |
|-------|------|---------|
| `state.l2SweepResult` | after `runL2SweepInheritance` | augmented inheritance-group clustering result with `items_meta`, `l2_meta` |
| `state.l2SweepCacheKey` | after `runL2SweepInheritance` | `'sweep::' + chrom + '::' + inheritanceCacheKey(items, mode)` |
| `state.candidateList` | after `autoPromoteFromSweep` | one new entry per surviving L2 (via `addCandidateToList`) |

## §3. Pipeline

```
isUsableL2 filter (per L2 envelope)
    → silhouette + populated-band count + cluster ok
    ↓
synthetic items[] (one per usable L2)
    → { id: 'L2:<idx>', labels: cluster.fixedKLabels, K,
        start_bp, end_bp, meta: { source: 'l2_sweep', l2_idx } }
    ↓
inheritanceGroupClustering(sortedItems, opts)   ← shared/inheritance_groups.js
    ↓
cache on state.l2SweepResult + state.l2SweepCacheKey
    ↓
autoPromoteFromSweep
    → 6 gates per L2; survivors → addCandidateToList
```

### §3.1 `isUsableL2(state, l2idx)`

Returns `{ usable: bool, reason: string, env, cluster?, n_bands? }`.

Reasons (in check order):

| reason | condition |
|--------|-----------|
| `NO_DATA` | no `state.data.l2_envelopes` |
| `NO_ENV` | `l2_envelopes[l2idx]` is falsy |
| `NO_BP` | env.start_bp / env.end_bp not numeric |
| `CLUSTER_THREW` | `getL2Cluster(state, l2idx)` threw |
| `NO_CLUSTER` | cluster is falsy |
| `<cluster.reason>` or `CLUSTER_NOT_OK` | `cluster.ok === false` |
| `NO_FIXEDK_LABELS` | `cluster.fixedKLabels` empty |
| `TOO_FEW_BANDS` | populated bands < `IGC_MIN_BANDS_FOR_CLUSTERING` (3) |
| `OK` | passes all checks |

### §3.2 `runL2SweepInheritance(state, opts)`

1. Iterate every `l2idx` in `state.data.l2_envelopes`.
2. Build `items[]` from each `usable === true` L2 + a parallel
   `usableMeta[]` (l2idx, env, cluster, n_bands).
3. Sort items + parallel meta by `start_bp`; assign `seq_num`.
4. **Short-circuit**: if `< IGC_MIN_BANDS_FOR_CLUSTERING` items,
   wipe state and return null.
5. Build cache key:
   `'sweep::' + chrom + '::' + inheritanceCacheKey(sortedItems, mode)`.
6. **Cache hit** (and `!opts.force`) → return cached result.
7. Call `inheritanceGroupClustering(sortedItems, opts)` from
   `shared/inheritance_groups.js`.
8. Augment result with `items_meta` + `l2_meta` (carrying the
   per-L2 metadata the auto-promote gates need).
9. Cache on state and return.

### §3.3 `silhouetteForL2FixedK(state, l2idx, cluster)`

Returns the cluster's `silhouette` if pre-computed; else compute via
`silhouette1D(xsKept, labsKept, K)` over `aggregateL2(state, l2idx)`'s
`xs` (filtering `-1` labels). Returns `NaN` on insufficient data
(< 4 kept points or K < 2).

### §3.4 `autoPromoteFromSweep(state, result)`

For each L2 in `result.l2_meta`, evaluate the **6 gates** (in order;
first failure stops further evaluation for that L2).

Returns `{ promoted: number[], skipped: Array<{l2idx, reason, ...}> }`
so the caller can surface promotion stats in the UI.

## §4. The 6 gates

| # | reason | check | constants |
|---|--------|-------|-----------|
| 1 | `DISMISSED` | `dismissed.has(l2idx)` (loaded from localStorage) | `L2_SWEEP_DISMISSED_KEY_PFX = 'pca_scrubber_v3.l2SweepDismissed.'` |
| 2 | `ALREADY_IN_CANDIDATE` | another candidate's `l2_indices` includes this L2 | — |
| 3 | `LOW_SILHOUETTE` | `meta.silhouette < AUTO_PROMOTE_MIN_SILHOUETTE` | **0.30** |
| 4 | `SMALL_BAND` | `min(meta.n_per_group) < AUTO_PROMOTE_MIN_BAND_SIZE` | **5** |
| 5 | `TOO_FEW_GROUPS` | `groupsTouchingItem[item_idx].size < AUTO_PROMOTE_MIN_GROUPS` | **2** |
| 6 | `DEDUPE_TOO_CLOSE` | bp distance to ANY existing candidate `< AUTO_PROMOTE_DEDUPE_BP` | **100,000 bp** |

Gate failure modes:
- `ADD_THREW` — `addCandidateToList` rejected (e.g. duplicate id) or
  `getL2Cluster` threw on stale envelopes.

## §5. Promoted candidate shape

When all 6 gates pass:

```js
{
  id:                'auto_l2sweep_<chrom>_<l2idx>_<timestamp_ms>',
  source:            'auto_l2_sweep',
  chrom:             <string>,
  l2_indices:        [<l2idx>],
  ref_l2:            <l2idx>,
  ref_window:        env._s0 ?? null,
  K:                 state.k || 3,
  locked_labels:     cluster.fixedKLabels,   // K-means at this L2
  start_w:           env._s0 ?? null,
  end_w:             env._e0 ?? null,
  start_bp:          env.start_bp,
  end_bp:            env.end_bp,
  created_at:        <ISO 8601>,
  auto_promoted_at:  <ISO 8601>,
  notes:             '',
  confirmed:         false                    // critical — see §6
}
```

## §6. The `confirmed: false` discipline

Auto-promoted candidates land with `confirmed: false`. This means:

- They appear in the review UI (candidate_focus candidate-list, catalogue
  catalogue, annotation_cockpit annotation cockpit).
- They do **NOT** participate in the inheritance pills painted on
  local_pca_dosage's lines_panel — those only show confirmed candidates so the
  visual cohort isn't polluted by unverified auto-suggestions.
- They do **NOT** appear in confirmed_carousel's confirmed-carousel.
- The user's gesture to confirm flips `confirmed: true` (typically
  on candidate_focus or karyotype_tier).

## §7. Dismissed-set persistence (per chrom)

Per-chromosome dismissed-L2 set persisted to localStorage under
`pca_scrubber_v3.l2SweepDismissed.<chrom>`. Stored as a JSON array
of integer L2 indices.

API:
- `loadL2SweepDismissed(chrom): Set<number>` — fail-soft to empty Set.
- `saveL2SweepDismissed(chrom, set): void` — fail-soft.

User dismissal happens via the L2-sweep inspector UI (not in this
module — wired in `local_pca_dosage/sidebar.js`).

## §8. Cache invalidation

`state.l2SweepCacheKey` is invalidated when:
- chromosome changes (`chrom` is part of the key)
- active mode changes (`state.activeMode` is part of `inheritanceCacheKey`)
- the items hash changes (per `inheritanceCacheKey`)

Forced recompute via `runL2SweepInheritance(state, { force: true })`.

`invalidateL2SweepCache(state)` clears
`state.l2SweepResult` + `state.l2SweepCacheKey` to null without
running the pipeline.

## §9. Exports

```js
// constants
export const AUTO_PROMOTE_MIN_SILHOUETTE = 0.30;
export const AUTO_PROMOTE_MIN_GROUPS     = 2;
export const AUTO_PROMOTE_MIN_BAND_SIZE  = 5;
export const AUTO_PROMOTE_DEDUPE_BP      = 100_000;
export const L2_SWEEP_DISMISSED_KEY_PFX  = 'pca_scrubber_v3.l2SweepDismissed.';

// dismissed-set persistence
export function loadL2SweepDismissed(chrom): Set<number>;
export function saveL2SweepDismissed(chrom, set): void;

// usability filter
export function isUsableL2(state, l2idx): { usable, reason, env, cluster?, n_bands? };

// silhouette
export function silhouetteForL2FixedK(state, l2idx, cluster): number;

// pipeline
export function runL2SweepInheritance(state, opts?): result | null;
export function invalidateL2SweepCache(state): void;
export function autoPromoteFromSweep(state, result): { promoted, skipped };
```

## §10. Integration with local_pca_dosage.applyData()

```
local_pca_dosage.applyData(state, data)
  → ... (data load, schema detect)
  → if (state.l2SweepEnabled) {
      const sweepResult = runL2SweepInheritance(state, { force: false });
      if (sweepResult) {
        const { promoted, skipped } = autoPromoteFromSweep(state, sweepResult);
        // promoted.length surfaced in the inspector UI
      }
    }
  → ... (downstream redraws)
```

## §11. Tunable knobs (future SPEC v2)

The 4 numeric thresholds are exported as `const` and not currently
adjustable from the UI:

- `AUTO_PROMOTE_MIN_SILHOUETTE = 0.30`
- `AUTO_PROMOTE_MIN_GROUPS     = 2`
- `AUTO_PROMOTE_MIN_BAND_SIZE  = 5`
- `AUTO_PROMOTE_DEDUPE_BP      = 100_000`

A v2 SPEC could:
1. Surface these as user controls in the L2-sweep inspector.
2. Persist user overrides per cohort to localStorage.
3. Tag the promoted candidate's `auto_promote_thresholds` blob so
   the audit trail shows the exact gates that admitted it.

## §12. References

- **Source code**: `atlases/inversion/pages/discovery/local_pca_dosage/l2_sweep.js`
- **Caller**: `atlases/inversion/pages/discovery/local_pca_dosage.js#applyData`
- **Inheritance clustering primitive**:
  `atlases/inversion/shared/inheritance_groups.js`
  (`inheritanceGroupClustering`, `IGC_MIN_BANDS_FOR_CLUSTERING`)
- **L2 cluster getter**: `pages/discovery/local_pca_dosage/_data.js#getL2Cluster`
- **Add-candidate**: `pages/discovery/local_pca_dosage/candidates.js#addCandidateToList`
- **Cache key**: `pages/discovery/local_pca_dosage/inheritance.js#inheritanceCacheKey`
- **Aggregation**: `shared/per_l2_cluster.js#aggregateL2`
- **Silhouette**: `shared/kmeans.js#silhouette1D`

---

**Authored**: 2026-05-15 from `pages/discovery/local_pca_dosage/l2_sweep.js`
(444 LOC). One of the 8 SPECs identified as missing on disk in
`_handoff_docs/SPECS_AUDIT.md`. The shipped code's docstring at the
top of `l2_sweep.js` was the seed for §1, §3.
