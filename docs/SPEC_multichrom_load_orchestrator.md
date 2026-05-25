# SPEC — Multi-chromosome JSON load orchestrator

**Status**: drafted turn 130 final session. **All three slices have
shipped 2026-05-26** — see slice notes below for caveats:
- [`core/chrom_summary.js`](../core/chrom_summary.js) — `buildChromSummary`,
  `setChromSummary`, `getChromSummary`, `listChromSummaries`
- [`core/atlas_state.js`](../core/atlas_state.js) — `chromSummaries` shared
  slot + convenience `setChromSummary()` setter that emits
  `shared.chromSummaries.changed`
- [`tests/test_chrom_summary.js`](../tests/test_chrom_summary.js) — round-trip
  + LG-natural-order + null-tolerance coverage

Slices 2 (bulk-load UI) + 3 (background compute scheduler) still pending.
Estimated remaining: ~0.5 turn each.

**Trigger** (Quentin):
> *"When we load all JSONs at once."*
>
> *"Soon its all ready then upload all chromosomes and it will be all
> automatic."*

The atlas today loads one chromosome JSON at a time. To support the
full-automatic vision (all 28 chroms → all candidates auto-promoted →
genome-wide ideogram), we need an orchestrator that handles loading
many JSONs without OOM-ing the browser.

---

## 1. The constraints

- 28 chromosome JSONs, ~50–300 MB each (varies with what layers are
  bundled). Worst case: 28 × 300 MB = 8.4 GB. Browser tabs typically
  cap around 4 GB heap on desktop, less on mobile.
- IndexedDB cache exists today (turn 95-ish from `07759823` chat) for
  per-chrom persistence. Per-origin quota varies (some browsers cap at
  200 MB, others at 60% of disk).
- The expensive computes (lineage, sweep, sliding-window) are
  per-chromosome and don't need cross-chrom data simultaneously.

## 2. Architecture

### 2.1 Lazy load with active-chrom focus

Default mode: **only the active chromosome's full JSON is in memory**.
Other chroms are reduced to a lightweight summary blob:

```
chromSummary[chrom] = {
  n_l2_envelopes,
  n_candidates,
  layersPresent,
  hasLineageCache,
  hasInheritanceCache,
  // small enough to keep in memory for all 28 chroms
}
```

When the user switches active chrom, the previous chrom's full data
goes back to IndexedDB; the new chrom's full data is loaded from
IndexedDB into memory.

### 2.2 Background pre-compute scheduling

When the user loads the multi-chrom bundle, the orchestrator schedules
the per-chrom expensive computes (lineage, sweep) via
`requestIdleCallback` chains:

```
queue = chrom_list.copy()
function nextChromCompute() {
  if (queue.empty) return;
  const chrom = queue.shift();
  loadChromIntoMemory(chrom);
  runLineageCompute({ chrom });
  runL2SweepInheritance({ chrom });
  cacheToIDB(chrom);
  unloadChromFromMemory(chrom);
  requestIdleCallback(nextChromCompute);
}
```

So the user can browse one chrom while the others are computing in the
background. Progress strip in the sidebar: "12 / 28 chromosomes
processed."

### 2.3 Bulk upload UI

New page or sidebar widget: "Bulk load 28 JSONs." Drag-drop a folder
or zip file. Atlas detects which files are chromosome JSONs (by
filename pattern + JSON `chrom` field), persists each to IDB, builds
chromSummary, schedules background compute.

## 3. State additions

```
state.chromSummary: { [chrom]: ChromSummary }
state.activeChrom: string
state.bulkLoadProgress: { total, processed, current }
state.computeQueue: chrom[]
```

## 4. Implementation slices

### Slice 1 — chromSummary infrastructure (~0.5 turn) — **SHIPPED 2026-05-26**
- ✅ Build summary blob on chrom load — `buildChromSummary(data)` is pure,
  null-tolerant, atlas-agnostic. Surfaces `chrom`, `n_windows`,
  `n_samples`, `chrom_length_bp`, `n_l2_envelopes`, `n_candidates`,
  `layers_present`, `has_lineage_cache`, `has_inheritance_cache`,
  `built_at_ms`, `data_version`.
- ✅ AtlasState carries `shared.chromSummaries` (Map keyed by chrom).
  `setChromSummary(chrom, summary)` fires `shared.chromSummaries.changed`
  for subscribers (Slice 2/3 will hook this).
- ✅ Test coverage: round-trip + LG-natural-order + cross-atlas payloads
  with no envelopes/candidates + null-tolerance + localStorage persistence
  round-trip across sessions.
- ✅ Page wiring: `local_pca_dosage.mount` and `haplotype_regimes.mount`
  both call `state.setChromSummary(chrom, buildChromSummary(data, { chrom }))`
  immediately after their `scrubber_main` resolve completes. Other pages
  that load `scrubber_main` will populate the cache automatically once
  they hit the same wiring (or via the in-flight Promise dedup when these
  two pages run first).
- ✅ Shell chip: `#chromSummaryBadge` in the header subscribes to
  `shared.chromSummaries.changed` and shows `chroms · N`. Clicking opens
  a modal listing every cached chrom with `n_windows · n_samples ·
  n_candidates · layers_present` plus a "jump →" button that dispatches
  a `change` event on the scopebar `<select>` (same path as a user
  gesture, so the router's full re-mount + prewarm pipeline fires).
- ✅ localStorage persistence: `savePersisted` / `loadPersisted` now
  round-trip the chromSummaries map, so a returning session sees the chip
  populated immediately instead of waiting for the user to revisit each
  chrom. Full payloads are still re-fetched on demand (this only
  persists the metadata cache).
- 🔜 IDB persistence of the full payload — uses the existing warm-tier
  cache via `registry.set('scrubber_main', payload, { chrom })`; no new
  IDB code needed. Slice 2 will wire the "unload non-active chrom" path.

### Slice 2 — bulk-load UI (~0.5 turn) — **SHIPPED 2026-05-26**
- ✅ `core/chrom_bulk_loader.js` — `loadChromJsons({ files, registry,
  atlasState, onProgress })` parses each JSON, writes the payload via
  `registry.set('scrubber_main', payload, { chrom })` (hot+warm tier),
  and populates the matching `chromSummary`. Skips files for documented
  reasons (`not_json`, `parse_error`, `chrom_unknown`, `registry_set_threw`)
  and surfaces each through `onProgress`.
- ✅ Chrom-id detection priority: `payload.chrom` → `payload.chromosome`
  → filename regex `(C_<species>_LG\d+|LG\d+)`. Skip-with-reason when
  none match — never guess.
- ✅ Shell modal UI: `📂 Bulk-load chrom JSONs…` button + hidden
  `<input type=file multiple accept=".json">`. Click opens the picker;
  selection triggers `loadChromJsons` with inline per-file progress in
  a status span. Modal re-renders when complete so the new rows show
  up alongside any previously-visited chroms.
- ✅ Test coverage: priority-ordered `_resolveChrom`, happy path (3
  files write correctly + chromSummaries populate), error paths
  (`not_json` / `parse_error` / `chrom_unknown` all bucket correctly,
  only valid files written), empty/null input.
- ✅ Drag-drop zone: the modal's bulk-load row is now a drop target with
  hover-state highlighting (border + bg flip to accent color). Dropped
  folders walk recursively via `DataTransferItem.webkitGetAsEntry` —
  the user can drop an entire workspace folder and only the `.json`
  leaves are picked up. Falls back to `dataTransfer.files` on older
  browsers without the folder API. Picker + drop share the same
  `runBulkLoad(files)` path.
- 🔜 Zip upload (would need a zip parser dep — defer).

### Slice 3 — background compute scheduler (~0.5 turn) — **PREVIEW SHIPPED 2026-05-26**
- ✅ `core/chrom_prewarm_scheduler.js` — `ChromPrewarmScheduler` class with
  `attach()` / `setEnabled()` / `kick()` / `abort()`. Walks the active
  scope picker's chrom list, orders by neighbors-first around the active
  chrom, skips chroms that already have a summary, and chains
  `requestIdleCallback`-scheduled `registry.resolve('scrubber_main', { chrom })`
  calls so the warm-tier IDB cache fills opportunistically.
- ✅ Opt-in via the chrom-summary modal toggle. Off by default to avoid
  blowing IDB quota for users who don't want it. Toggle persists across
  sessions via `localStorage['atlas.chromPrewarmEnabled']`.
- ✅ Token-based cancellation: each `kick()` invalidates older chains, so
  enable/disable toggling and rapid chrom switches don't race.
- ✅ Idle yield between chroms (~500ms timeout) so background fetches
  never starve the active page.
- ✅ Test coverage: localStorage round-trip, neighbors-first ordering,
  cached-chrom skip, abort cancellation.
- 🔜 Per-chrom progress chip ("12 / 28 chroms warmed") — could subscribe
  to `shared.chromSummaries.changed` and update inline; today the user
  sees progress via the chrom-summary chip count.
- 🔜 Lineage / inheritance compute (the heavy compute the original spec
  called out) — currently only `scrubber_main` is prewarmed; expanding
  to lineage/inheritance is a separate decision (those computes mutate
  candidate state, so the trigger conditions need design).

## 5. Open questions

1. **What goes in chromSummary?** Minimum to support genome-wide
   ideogram + cross-chrom lineage matching. Probably:
   `n_candidates`, `n_auto_promoted`, `n_lineages`, `chromosome_size_bp`,
   per-candidate `(start_bp, end_bp, tier, source)`.
2. **What if the user wants two chroms in memory simultaneously?**
   E.g., comparing LG12 and LG28 side-by-side. Edge case; defer.
3. **What about Save-Session?** The session export today is per-chrom
   data + state. Multi-chrom session adds chromSummary + IDB pointers.
   May need a session format bump.

## 6. Tests

- Bulk-load 3 synthetic JSONs → all 3 land in IDB, chromSummary
  populated, only the active one is in `state.data`.
- Switch active chrom → previous chrom's data unloaded, new chrom
  loaded.
- Background compute: schedule 3 chroms, verify each gets lineage +
  sweep results in IDB.
- Memory budget: synthetic 28 × 200MB JSONs → browser doesn't OOM
  (only one in memory at a time).

## 7. Dependencies

- Existing IDB cache (already shipped).
- Lineage compute (shipped turn 130).
- L2-sweep auto-promote (`SPEC_l2_sweep_inheritance.md`, queued).
- Cross-chrom lineage aggregator (`SPEC_cross_chromosome_lineages.md`,
  queued).
