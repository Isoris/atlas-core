# Atlas architecture overview

This document is a 10-minute orientation for someone new to the
codebase. Read this AFTER `README_PAIRING.md` and BEFORE the specs.

## The big picture

```
┌─────────────────────────────────────────────────────────────────┐
│  Browser (index.html)                                           │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  Page module (e.g. page1.js)                             │   │
│  │  reads AtlasState directly for hot data                  │   │
│  │  calls registry.resolve() for warm/cold data             │   │
│  └──────────┬───────────────────────────┬───────────────────┘   │
│             │                           │                       │
│   ┌─────────▼─────────┐       ┌─────────▼─────────┐             │
│   │   AtlasState      │       │   Registry        │             │
│   │   (event bus)     │◄──────┤   (resolver)      │             │
│   └─────────┬─────────┘       └─────┬───────┬─────┘             │
│             │                       │       │                   │
│             │  ┌────────────────────┘       │                   │
│             │  │                            │                   │
│   ┌─────────▼──▼──────┐         ┌───────────▼─────────────┐     │
│   │  Prewarm          │         │  CacheStore             │     │
│   │  Scheduler        │         │  (RAM Map + IndexedDB)  │     │
│   └───────────────────┘         └─────────────────────────┘     │
│                                                                 │
└──────────────────────────────────┬──────────────────────────────┘
                                   │
                                   │  HTTP (cold tier)
                                   │
                ┌──────────────────▼──────────────────┐
                │  server/server.py (Flask)           │
                │  ├── /api/shared/...                │
                │  └── /api/inversion/...             │
                │       (mounted from server-adapters)│
                └──────────────┬──────────────────────┘
                               │
                ┌──────────────▼──────────────────────┐
                │  Compute engines                    │
                │  (inversion_popgen, conservation,   │
                │   etc — atlas-specific, not shown)  │
                └─────────────────────────────────────┘
```

## The two contracts that matter

**1. Pages read AtlasState directly for hot-tier data.**

When you migrate a page from the legacy monolith, the rule is:

```js
// LEGACY (monolith style):
//   state.simMat[i] is just a global-ish object property
const value = state.simMat[i];

// NEW (shell style):
//   AtlasState.inversion.tracks[chrom].sim_mat is the same data,
//   pinned by the prewarm scheduler at chrom_change.
const value = atlasState.inversion.tracks[chrom].sim_mat[i];
```

No `await`. No `resolve()`. The data is already there because the
prewarm scheduler put it there before the page mounted. This is what
makes scrolling stay at 60 fps.

**2. Pages use registry.resolve() for warm/cold-tier data.**

```js
// First time: ~50ms (IndexedDB miss → file fetch → cache to IndexedDB)
// Second time: ~10ms (IndexedDB hit)
const evidence = await registry.resolve('candidate_evidence', { candidate_id: 'lg28_15p115_18p005' });

// First time: ~2s (server compute)
// Second time: ~10ms (IndexedDB hit)
const fst = await registry.resolve('fst_hom1_hom2', { candidate_id: 'lg28_15p115_18p005' });
```

The page doesn't care which tier it is. The registry's tier table
(in `layers.registry.json` and `operations.registry.json`) decides.

## How the boot sequence works

`index.html` runs this sequence at page load:

1. Construct `AtlasState` (singleton).
2. Construct `Registry` (singleton, references AtlasState).
3. `bootstrap()` the public `atlas_api.js` facade so page modules
   can import a stable surface.
4. Call `discover()`. This reads `atlases/_index.json` (written by
   the assembly script) and loads each atlas's `manifest.json`.
5. For each discovered atlas:
   - Load its five registry config files (referenced from manifest).
   - `registry.register_atlas(atlas_id, configs)` — validates against
     meta-schema, builds internal indexes.
   - `state.registerAtlasSlots(atlas_id, slots)` — adds the bucket.
6. Construct `PrewarmScheduler`. It subscribes to AtlasState events
   (chrom change, candidate change, page mount).
7. Construct `AtlasRouter`. It renders the topbar, parses the URL
   hash, and mounts the initial page.

After step 7, the user sees the topbar and the initial page renders.

## The data flow for a single page action

Example: user clicks "page 1" in the topbar.

1. Router parses new hash `#/inversion/page1`.
2. Router calls previous page's `unmount()` (if any).
3. Router fetches `atlases/inversion/pages/discovery/page1.html`,
   injects into `#app-root`.
4. Router dynamically imports `atlases/inversion/pages/discovery/page1.js`.
5. AtlasState emits `shell.page_mount` event.
6. PrewarmScheduler catches the event, looks up `page1` in
   `pages.registry.json`, finds `preloads: ["scrubber_main", ...]`.
   Starts pre-warming all the listed layers in parallel.
7. Router calls `module.mount(root, atlasState, registry)`.
8. Page's `mount()` does its setup. May `await registry.resolve(...)`
   for warm/cold layers. May read state directly for hot layers.
9. User sees the page render.

If the user scrolls within page1, the scroll handler reads
`atlasState.inversion.tracks[chrom].sim_mat` directly — synchronous,
no registry call. < 1 ms per frame.

If the user clicks a "compute FST" button, the click handler does
`await registry.resolve('fst_hom1_hom2', ...)`. That hits the server
the first time (~2s, spinner shown), IndexedDB on subsequent calls.

## How a new atlas is added

There is no code change in `atlas-core/`. The new atlas is its own
package:

```
my-new-atlas/
└── atlases/
    └── my_new_atlas/
        ├── manifest.json
        ├── pages/
        ├── shared/
        ├── registries/
        │   ├── data/                    ← five JSON config files
        │   └── schemas/
        └── data/
```

Assembly merges its `atlases/` into the workspace. The shell
discovers it on next reload. That's it.

## What this architecture buys you

- **Hot-path performance.** Scrolling stays at 60 fps because hot
  data doesn't go through the resolve chain.

- **Composability.** Atlases compose by filesystem merge, no code
  change in the shell.

- **Future scaling.** The chunked/viewport hooks are baked into v1.
  When tracks get too big for whole-chromosome RAM loads, v2 turns
  them on without changing the engine API.

- **Editability.** No file in the codebase exceeds ~500 LOC. AI-
  assisted editing works because the unit of work is small.

- **Independent atlas development.** The four atlases (inversion,
  diversity, genome, population) live in four repos. They share
  only the contract pinned by the meta-schema — no code dependencies
  in either direction.

## What this architecture does NOT do

- It does NOT make the popstats server faster. The server is what
  it is.
- It does NOT eliminate the 290 TODO_MISSING markers in the page-
  split. Those are functions that need to be promoted to shared
  modules; orthogonal to the shell architecture.
- It does NOT solve multi-user / collaborative state. v1 is single-
  user.
- It does NOT do live tile streaming for large tracks. v1 hooks are
  in place; v2 implements them.

## Where to go next

- New to the codebase: read `README_PAIRING.md`, then this file,
  then `docs/SPEC_registry_v1.md`.
- Implementing core: follow the order in `SPEC_registry_v1.md §10`.
- Adding a new atlas: copy `tests/mock-atlas/` and rename.
- Adding a new operation to inversion: edit
  `atlases/inversion/registries/data/operations.registry.json`,
  add a server adapter under
  `atlases/inversion/server-adapters/`, write a schema under
  `atlases/inversion/registries/schemas/`. No core changes.
- Adding a Mode-B cross-check probe to an atlas page: read
  `docs/SPEC_mode_b_pattern.md`. ~1 import line + 1 helper function
  per page. 18 callsites shipped across 6 atlases as of 2026-05-20.
