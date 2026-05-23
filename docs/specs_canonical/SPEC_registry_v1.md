# SPEC — Atlas registry v1

**Date**: 2026-05-06
**Status**: design spec, not yet implemented
**Scope**: the registry layer that sits between Atlas pages and data
sources (RAM / IndexedDB / shipped files / backend server).
**Companion docs**: `STARTER_atlas_shell_architecture.md` (the shell),
`README_PAIRING.md` (core + cartridge pairing).

---

## 1. What this is

The registry is the resolver between an Atlas page and the data it
needs. A page asks for a named result; the registry returns it from
the fastest source that has it. The page does not know or care
whether the answer came from a hot RAM array, an IndexedDB cache, a
shipped JSON file, or a freshly computed backend operation.

The registry is split into two halves:

- **Engine** (in `core/`) — generic, biology-blind, never changes
  when a new atlas ships. Knows how to resolve, cache, dispatch.
- **Configuration** (in `atlases/<atlas_id>/registries/`) — declarative
  JSON. Knows what each atlas's data layers, files, operations, and
  pages mean. Knows nothing about resolution mechanics.

The engine reads the configuration. That is the entire relationship.

---

## 2. The latency tiers (the most important section in this spec)

Every operation in the registry is tagged with a **tier**. The tier
determines how the registry serves it. The mistake to avoid is
routing every read through the full resolve chain — scrolling along a
chromosome must not hit IndexedDB, let alone the server.

### Tier table

| Tier | Latency budget | Source | Page access pattern |
|------|----------------|--------|---------------------|
| **hot** | < 1 ms | RAM (direct state read) | `state.tracks[chrom][window]` — synchronous |
| **warm** | 5–50 ms | IndexedDB | `await reg.resolve(key)` — async, fast |
| **cold** | 100 ms – 10 s | shipped JSON or server | `await reg.resolve(key)` — async, may show spinner |

### How each tier is served

**hot** — pre-warmed by the registry at a known trigger event
(chromosome change, candidate change, page mount). The registry
loads the data and pins it to a known location in `AtlasState`. The
page then reads that location directly, with no registry call on the
read path. Scrolling, panning, zooming, hover updates — all hot-tier
reads. Never await anything.

**warm** — held in IndexedDB. The registry pre-warms IndexedDB on
the same triggers as hot, but does not pin to RAM. First page access
is async but completes within ~50 ms. Subsequent accesses in the
same session are also ~50 ms. Used for things you'll probably need
soon but not on every frame: per-candidate evidence, sample-level
metadata that exceeds RAM budget.

**cold** — fetched on demand. Either a shipped JSON file or a backend
operation. The page shows a spinner. Used for things that are
expensive to compute (FST, θπ, BEAGLE uncertainty) or rarely needed
(pseudogenisation scan on a specific gene, permutation tests).

### Trigger events

The registry pre-warms on three named events:

- `chrom_change` — user switched active chromosome
- `candidate_change` — user switched active candidate
- `page_mount` — user navigated to a new page

Each layer in `layers.registry.json` declares which event triggers
its pre-warm. The default for an unflagged layer is `cold` /
`explicit` (no pre-warm).

### Why this matters

Your legacy monolith already does this implicitly: `applyData()`
loads everything into `state.*`, then `drawSim()` and `drawZ()` read
`state.simMat[i]` synchronously. The new architecture makes it
explicit: pages declare what they need hot, and the registry honors
that declaration.

If a page ever does `await reg.resolve(...)` inside a scroll handler
or a draw loop, that's a bug. The spec's success criterion is that
panning a chromosome stays at 60 fps with the registry layer in
place.

---

## 3. Engine API

The engine exposes five methods. That's it.

```js
// In core/registry_core.js

class Registry {
  // Get a value. Returns immediately for hot tier, async for warm/cold.
  // For hot tier, this is a thin wrapper over a direct state read.
  resolve(key, args = {})        // → value | Promise<value>

  // Manually set a value. Used by pre-warm, by manual cache injection,
  // by tests. Writes through to the appropriate cache tier.
  set(key, value, args = {})     // → void

  // Drop a cached value (e.g. when the underlying data changed).
  invalidate(key, args = {})     // → void

  // Atlas-side registration. Called once at atlas-load time per atlas.
  // Registers the atlas's layers, files, operations, pages, slots.
  // Throws on conflict (same key registered twice).
  register_atlas(atlas_id, configs)  // → void

  // Diagnostic. Returns the resolution path that would be taken for
  // a given key, without actually fetching. Used by the dev console.
  trace(key, args = {})          // → ResolutionPlan
}
```

`ResolutionPlan` is a struct:

```js
{
  key: 'fst_hom1_hom2',
  args: { candidate_id: 'lg28_15p115_18p005' },
  tier: 'cold',
  source: 'server',
  endpoint: '/api/inversion/fst_hom1_hom2',
  cache_key: 'fst:lg28_15p115_18p005:default',
  cache_status: 'miss',   // 'hot' | 'warm' | 'miss'
  schema: 'schemas/fst_hom1_hom2.schema.json'
}
```

That's the entire engine surface. Pages call `resolve` and `set`.
Tests call `trace` and `invalidate`. The shell calls `register_atlas`
once per discovered atlas at startup.

---

## 4. The five configuration files

Each atlas ships a `registries/data/` folder with five JSON files.
All five are declarative — no JS logic, no functions, just data.

### 4.1 `layers.registry.json`

Defines the data layers an atlas knows about and their tier.

```json
{
  "sim_mat": {
    "tier": "hot",
    "preload_on": "chrom_change",
    "source": "file",
    "path": "data/precomp/{chrom}/sim_mat_nn40.json",
    "shape": "matrix",
    "schema": "schemas/sim_mat.schema.json"
  },
  "robust_z": {
    "tier": "hot",
    "preload_on": "chrom_change",
    "source": "file",
    "path": "data/precomp/{chrom}/robust_z.json",
    "shape": "array",
    "schema": "schemas/robust_z.schema.json"
  },
  "candidate_evidence": {
    "tier": "warm",
    "preload_on": "candidate_change",
    "source": "file",
    "path": "data/candidates/{candidate_id}/evidence.json",
    "schema": "schemas/candidate_evidence.schema.json"
  },
  "fst_hom1_hom2": {
    "tier": "cold",
    "source": "operation",
    "operation": "fst_hom1_hom2"
  }
}
```

Path templating uses `{slot_name}` — the engine substitutes from
`AtlasState.shared.*` and `args` at resolve time.

### 4.2 `files.registry.json`

Static file inventory. Distinct from layers because some files back
multiple layers (e.g. one cohort metadata file backs five different
"layer" views).

```json
{
  "cohort_metadata": {
    "path": "data/cohort/metadata.json",
    "schema": "schemas/cohort_metadata.schema.json",
    "tier": "warm",
    "preload_on": "page_mount",
    "scope": "global"
  },
  "lg28_precomp": {
    "path": "data/precomp/LG28/precomp.json",
    "schema": "schemas/precomp.schema.json",
    "tier": "hot",
    "preload_on": "chrom_change",
    "scope": "per_chrom"
  }
}
```

### 4.3 `operations.registry.json`

Compute recipes that go through the backend.

```json
{
  "fst_hom1_hom2": {
    "endpoint": "/api/inversion/fst_hom1_hom2",
    "method": "POST",
    "inputs": ["activeCandidate", "arrangementCalls", "sampleIds"],
    "output_schema": "schemas/fst_hom1_hom2.schema.json",
    "cache_key": "fst:{candidate_id}:{grouping}",
    "cache_tier": "warm",
    "estimated_latency_ms": 2000
  },
  "theta_pi_by_invgt": {
    "endpoint": "/api/inversion/theta_pi",
    "method": "POST",
    "inputs": ["activeCandidate", "arrangementCalls", "sampleIds", "windowSize"],
    "output_schema": "schemas/theta_pi.schema.json",
    "cache_key": "theta_pi:{candidate_id}:{window_size}",
    "cache_tier": "warm",
    "estimated_latency_ms": 1500
  }
}
```

`inputs` are slot names from `AtlasState.shared.*` or
`AtlasState.<atlas_id>.*`. The engine pulls them at resolve time and
sends them as the POST body. The page does not assemble payloads.

### 4.4 `pages.registry.json`

What each page needs to function.

```json
{
  "candidate_focus": {
    "requires_layers": ["sim_mat", "robust_z", "candidate_evidence"],
    "requires_operations": [],
    "requires_slots": ["activeChrom", "activeCandidate"],
    "preloads": ["sim_mat", "robust_z"]
  },
  "popstats": {
    "requires_layers": [],
    "requires_operations": ["fst_hom1_hom2", "theta_pi_by_invgt"],
    "requires_slots": ["activeCandidate", "arrangementCalls", "sampleIds"]
  }
}
```

The shell uses `requires_slots` to know whether a page can be
rendered at all. If `activeCandidate` is null and the page requires
it, the shell shows a placeholder. `preloads` is the explicit list
the engine pre-warms when this page mounts.

### 4.5 `slots.registry.json`

Private state slots this atlas declares. The shell merges these into
`AtlasState.<atlas_id>.*` at startup.

```json
{
  "lockedBands": { "type": "array", "default": null, "persist": true },
  "linesColorMode": { "type": "string", "default": "kmeans", "persist": true },
  "arrangementCalls": { "type": "object", "default": null, "persist": false },
  "cachedTracks": { "type": "object", "default": null, "persist": false }
}
```

`persist: true` round-trips through localStorage. `persist: false` is
in-memory only.

---

## 5. The meta-schema

All five config files validate against a meta-schema shipped in
`core/registry_core.schema.json`. This is the only "shared registry
vocabulary" the atlases agree on. New atlases must pass meta-schema
validation at `register_atlas` time or the engine throws.

The meta-schema pins:
- valid tier values: `hot | warm | cold`
- valid preload_on values: `chrom_change | candidate_change | page_mount | explicit`
- valid source values: `file | operation | inline | analysis`
- required fields per entry type

---

## 6. The resolution chain (worked example)

A page calls `reg.resolve('fst_hom1_hom2')`. Trace:

1. **Engine looks up `fst_hom1_hom2` in the merged registry.**
   Finds it in `inversion`'s `layers.registry.json` with
   `source: operation, operation: fst_hom1_hom2`.

2. **Engine looks up the operation.** Finds it in
   `operations.registry.json` with `cache_tier: warm`,
   `cache_key: "fst:{candidate_id}:{grouping}"`.

3. **Engine resolves the cache key.** Pulls `activeCandidate.id`
   from `AtlasState.shared`, pulls `grouping` default from the page's
   call args. Cache key becomes `fst:lg28_15p115_18p005:default`.

4. **Engine checks RAM.** Miss (warm tier doesn't pre-pin to RAM).

5. **Engine checks IndexedDB.** Miss (first time this candidate has
   been queried).

6. **Engine pulls operation inputs from state.**
   `activeCandidate`, `arrangementCalls`, `sampleIds`.

7. **Engine POSTs to `/api/inversion/fst_hom1_hom2`.** Server runs
   the compute, returns JSON.

8. **Engine validates against `schemas/fst_hom1_hom2.schema.json`.**
   If invalid, throw with a clear error.

9. **Engine writes to IndexedDB under
   `fst:lg28_15p115_18p005:default`.** Returns the value to the page.

10. **Page renders.** Next time the user picks the same candidate,
    step 5 hits and returns in ~10 ms.

If the user changes `activeCandidate`, step 3 produces a different
cache key and the chain runs again for the new candidate. The old
candidate's result stays in IndexedDB for fast return on back-navigation.

### Hot-tier worked example

A page draws sim_mat. It does NOT call `reg.resolve('sim_mat')` in
its draw loop. Instead:

1. **At chrom_change**, the engine pre-warmed `sim_mat`. It read
   `data/precomp/LG28/sim_mat_nn40.json` and pinned the array to
   `AtlasState.inversion.tracks.sim_mat`.

2. **The page's `mount(root, AtlasState)` runs.** It cached a
   reference: `this.simMat = AtlasState.inversion.tracks.sim_mat`.

3. **Scroll handler fires.** `drawSim()` reads `this.simMat[i][j]`
   directly. No registry call, no async, no await. < 1 ms.

4. **User changes chrom.** Engine pre-warms again, replaces the
   pinned array, fires a `chrom_changed` event the page listens to.
   Page rebinds `this.simMat` and redraws.

This is exactly what the legacy monolith already does. The registry
just formalizes the pre-warm step.

---

## 7. Conflict rules

Two atlases registering the same key. Pin behavior:

- **Same key, identical config** → silent merge (idempotent)
- **Same key, different config** → throw at `register_atlas` time
- **Same operation key, different endpoints** → throw
- **Same slot name in `slots.registry.json`** → throw

Atlases that anticipate sharing keys with other atlases should
namespace explicitly: `inversion:fst_hom1_hom2`, not just
`fst_hom1_hom2`. The engine treats `:` as the namespace separator
and does not auto-namespace — that's the atlas author's call.

If atlas A's page asks for `inversion:fst_hom1_hom2` but the
`inversion` atlas isn't loaded, `resolve` returns `null` and logs a
warning. The page decides whether to render an empty state or hide.

---

## 8. What lives where (final layout)

### Core (the engine, generic)

```
core/
├── registry_core.js              ← the Registry class (§3)
├── registry_core.schema.json     ← the meta-schema (§5)
├── cache_store.js                ← memory + IndexedDB primitives
├── operation_runner.js           ← backend POST/GET, schema validation
├── layer_router.js               ← hot/warm/cold dispatch
├── prewarm_scheduler.js          ← listens for trigger events, pre-warms layers
├── atlas_state.js
├── atlas_router.js
├── atlas_discovery.js
└── atlas_api.js
```

### Atlas package (the configuration, atlas-specific)

```
atlases/inversion/registries/
├── data/                         ← all JSON, declarative
│   ├── layers.registry.json
│   ├── files.registry.json
│   ├── operations.registry.json
│   ├── pages.registry.json
│   └── slots.registry.json
├── schemas/                      ← per-result JSON Schemas
│   ├── candidate_evidence.schema.json
│   ├── fst_hom1_hom2.schema.json
│   ├── theta_pi.schema.json
│   ├── arrangement_calls.schema.json
│   └── ...
├── transforms/                   ← genuinely atlas-specific JS (rare)
│   └── enrichment_merger.js      ← if you have one
├── tests/
│   ├── test_registry_resolve.js
│   ├── test_layer_router.js
│   └── test_operation_registry.js
└── docs/
    ├── HOW_TO_USE.md
    └── DATABASE_DESIGN.md
```

The thing to notice: `core/` has all the JS, `atlases/.../registries/`
has almost no JS. The atlas package is mostly declarative. That's the
point. Adding a new atlas means writing JSON, not writing JavaScript.

---

## 9. What this spec does NOT cover

- The popstats backend itself. It exists. It works. The registry
  treats it as an opaque endpoint.
- The shell, router, discovery, state. Covered in
  `SPEC_atlas_shell_v1.md` (TBD) — this spec assumes those exist.
- Multi-user / collaborative state. Out of scope for v1.
- Server-side caching. The server can do whatever it wants; the
  registry only knows about its own three tiers.
- Streaming results (e.g. progress updates during long compute).
  v1 is request/response only. v2 may add SSE / WebSocket support;
  the engine API is designed to extend by adding a fourth method
  (`subscribe`), not by changing the existing four.

---

## 10. Implementation order

1. **Meta-schema** (`core/registry_core.schema.json`) — ~80 lines.
   Locks the vocabulary so config validation is mechanical.
2. **Cache store** (`core/cache_store.js`) — ~200 lines. Memory Map +
   IndexedDB wrapper. Standalone, easy to test.
3. **Operation runner** (`core/operation_runner.js`) — ~150 lines.
   Fetch + schema validate + error mapping.
4. **Registry engine** (`core/registry_core.js`) — ~400 lines. Ties
   the above together. Implements the five-method API.
5. **Pre-warm scheduler** (`core/prewarm_scheduler.js`) — ~150 lines.
   Listens for `chrom_change`, `candidate_change`, `page_mount`;
   walks the layer registry; calls `set` on the engine.
6. **One atlas config** (`atlases/inversion/registries/data/*.json`)
   — start with five layers and two operations, not the full set.
7. **One page migration**: `popstats`. Consumes one operation
   end-to-end. Proves the loop closes.
8. **Hot-path proof**: migrate `candidate_focus` sim_mat draw,
   confirm 60 fps scroll with registry pre-warm in place.

Total core: ~1000 LOC. Achievable in 3–4 focused turns. The atlas
config is mostly mechanical translation from the existing
`state_io.js` `KNOWN_LAYERS` table.

---

## 10.5 The `analysis` source kind (browser-side compute)

Added after v1 design review when the analysis-module pattern was
formalized. Rationale: some computes are heavy enough to benefit
from caching but not heavy enough to need the server. Trio
identification, Mendelian tests, per-cluster purity scoring — these
run in milliseconds in the browser and shouldn't pay the round-trip
cost of going through Flask.

### Declaration

In `layers.registry.json`:

```json
"mendelian_test": {
  "tier": "warm",
  "source": "analysis",
  "analysis": "analysis/mendelian.js#runMendelianTest",
  "schema": "schemas/mendelian_test.schema.json",
  "cache_key": "mendelian:{candidate_id}"
}
```

The `analysis` field uses `path/to/module.js#exportName` syntax. The
path is resolved relative to the atlas root.

### Module contract

The exported function MUST have the signature `(reg, ctx) → Promise<value>`:

```js
export async function runMendelianTest(reg, ctx) {
  const inputs = await Promise.all([
    reg.resolve('candidate_karyotype_per_sample', { candidate_id: ctx.candidate_id }),
    reg.resolve('cohort_relatedness')
  ]);
  const result = computeMendelianTest(...inputs);
  await reg.set('mendelian_test', result, { candidate_id: ctx.candidate_id });
  return result;
}
```

### Why the module must write back through `reg.set()`

When page A calls `reg.resolve('mendelian_test', ...)`, the registry
sees the warm cache miss, calls the analysis module, the module
computes the result and `reg.set()`s it to warm cache, then returns
it to the registry, which returns it to page A.

When page B later calls `reg.resolve('mendelian_test', ...)` with
the same args, the warm cache hits and the module never runs again.
This is the key property: cross-page reuse without recomputation.

If the analysis module just `return`-ed without `set`-ing, page B
would recompute. Always write back.

### Why `reg` is passed re-entrantly

The analysis module receives the SAME registry instance that called
it. This is deliberate — it's how the module can call `reg.resolve()`
for its inputs (which themselves might be other analysis results or
file layers or server operations). The registry handles the
recursion; the module just composes calls.

### Module isolation

ES module scoping protects analysis modules from each other. A
`const ALPHA = 0.05` in `mendelian.js` is invisible to other modules
unless explicitly `export`-ed. There is no need for the registry to
enforce isolation — JavaScript already does.

### Source-kind comparison

| Source | Where compute runs | Latency | When to use |
|--------|-------------------|---------|-------------|
| `file` | nowhere (just fetch) | network | Pre-computed results from the R/Python pipeline |
| `inline` | nowhere | none | Constants, demo data, test fixtures |
| `analysis` | browser | <100 ms typical | Light biology compute that benefits from caching |
| `operation` | server | 100 ms – 30 s | Heavy compute that can't run in the browser |



## 11. Success criteria for v1

The registry is done when:

- A page can call `resolve('fst_hom1_hom2')` and get a result, with
  no manual fetch / cache / endpoint plumbing in the page.
- Scrolling LG28 stays at 60 fps with the registry layer in place
  (hot-tier reads bypass the resolve chain entirely).
- Adding a new operation requires editing one JSON file (and
  optionally one schema), no JS changes in the engine.
- Adding a new atlas requires writing the five config JSON files,
  no JS changes in the engine.
- All 290 `TODO_MISSING` markers in the page-split can be resolved
  by either: (a) promoting the missing function to a shared module,
  or (b) replacing the call with a `resolve(...)` call.

---

End of spec.
