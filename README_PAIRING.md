# Atlas Core + Atlas Package Pairing

**Core is the machine; each atlas is a cartridge.**

This project is split into two parts:

1. `atlas-core/` — the generic shell, router, state, registry engine,
   cache, server bridge.
2. one or more atlas packages, such as:
   - `inversion-atlas/`
   - `population-atlas/`
   - `diversity-atlas/`
   - `genome-atlas/`

Neither half is useful alone. They are designed to run as a pair.

---

## 1. Mental model

Core provides the **machine**: HTML shell, JavaScript runtime,
filesystem discovery, page router, state container, registry engine,
cache chain (RAM → IndexedDB → file → server), HTTP bridge.

Each atlas package provides a **cartridge**: pages, manifests,
registry configurations, schemas, atlas-specific shared modules,
demo data, optionally backend adapters and engine code.

Core does not know what FST, PC1, inversion, ancestry, or
pseudogenisation mean. Atlases do not know how to wire a router or
manage IndexedDB. They meet at well-defined contracts: the page
mount API, the registry config schema, the state slot vocabulary.

---

## 2. Runtime layout (after assembly)

To run the Atlas, assemble a workspace by merging core with one or
more atlas packages:

```text
atlas-workspace/
├── index.html                  ← from core
├── core/                       ← from core
├── server/                     ← from core
└── atlases/
    └── inversion/              ← from inversion-atlas package
        ├── manifest.json
        ├── pages/
        ├── shared/
        ├── registries/
        ├── data/
        └── server-adapters/
```

For multiple atlases:

```text
atlas-workspace/
├── index.html
├── core/
├── server/
└── atlases/
    ├── inversion/
    ├── diversity/
    ├── genome/
    └── population/
```

Composition is filesystem-level. Clone one atlas repo → use one
atlas. Merge four → use four. Never edit `index.html` to add an
atlas.

---

## 3. What belongs in atlas-core

```text
atlas-core/
├── index.html
├── core/
│   ├── atlas_state.js
│   ├── atlas_router.js
│   ├── atlas_discovery.js
│   ├── atlas_api.js
│   ├── registry_core.js
│   ├── registry_core.schema.json
│   ├── cache_store.js
│   ├── operation_runner.js
│   ├── layer_router.js
│   └── prewarm_scheduler.js
├── server/
│   ├── server.py
│   ├── config.yaml
│   ├── api/
│   │   └── shared/             ← endpoints common to multiple atlases
│   └── adapters/               ← atlas-specific endpoints mounted at assembly
├── docs/
│   ├── SPEC_registry_v1.md
│   ├── SPEC_atlas_shell_v1.md
│   ├── SPEC_atlas_state_v1.md
│   ├── SPEC_server_bridge_v1.md
│   └── ARCHITECTURE.md
└── tests/
    └── mock-atlas/             ← minimal fake atlas for testing core
```

**Core responsibilities:**

- Discover installed atlases from `atlases/*/manifest.json`
- Route between pages
- Load page fragments and JS modules on demand
- Maintain shared and per-atlas state
- Communicate with the local backend server
- Provide the generic registry engine (resolution, cache chain, dispatch)
- Provide the meta-schema all atlas registry configs validate against

**Core constraints:**

- Must stay biology-neutral. No inversion, population, diversity, or
  genome-specific logic.
- Must not import from any `atlases/*/` directory at build time. All
  references happen at runtime via the discovery + manifest contract.
- Must validate atlas configs against the meta-schema and refuse to
  load malformed atlases with a clear error.

---

## 4. What belongs in an atlas package

```text
inversion-atlas/
└── atlases/
    └── inversion/
        ├── manifest.json
        ├── pages/
        │   ├── discovery/
        │   ├── review/
        │   ├── catalogue/
        │   └── comparative/
        ├── shared/
        │   ├── band_tracking/
        │   ├── kmeans.js
        │   ├── hungarian.js
        │   └── per_l2_cluster.js
        ├── registries/
        │   ├── data/
        │   │   ├── layers.registry.json
        │   │   ├── files.registry.json
        │   │   ├── operations.registry.json
        │   │   ├── pages.registry.json
        │   │   └── slots.registry.json
        │   ├── schemas/
        │   ├── transforms/
        │   ├── tests/
        │   └── docs/
        ├── data/
        │   ├── precomp/
        │   ├── candidates/
        │   ├── cohort/
        │   ├── arrangement_calls/
        │   └── comparative/
        ├── server-adapters/    ← Python adapters for backend endpoints
        └── engines/            ← atlas-specific compute (or links out)
```

**Atlas package responsibilities:**

- Declare pages in `manifest.json`
- Provide page fragments and page JS modules
- Provide atlas-specific schemas
- Declare data layers, files, operations, page requirements, slots
  in the five registry config files
- Optionally provide server adapters that mount under `core/server/`
- Optionally provide compute engines

**Atlas package constraints:**

- Must not reimplement the shell, router, generic cache, or registry
  engine.
- Must declare every result key it expects to resolve.
- Must namespace shared keys explicitly (e.g. `inversion:fst_hom1_hom2`)
  if collision with other atlases is anticipated.

---

## 5. The two registries (read this carefully)

There are TWO distinct registry concepts. Conflating them leads to
either bringing back a thing that was correctly dropped, or refusing
to add a thing that's actually needed. Name them separately.

### 5.1 The atlas registry (DROPPED — stays dropped)

A runtime registry that says "these atlases exist, here's how to
load them." This was tried and abandoned because filesystem
composition does the same job better: an atlas exists if its folder
exists at `atlases/<id>/manifest.json`. No registry needed. The
shell scans, finds manifests, mounts pages.

**Do not bring this back.** Filesystem discovery (in
`core/atlas_discovery.js`) replaces it.

### 5.2 The result/operation registry (KEPT — implemented in core)

A resolver between pages and data sources. A page calls
`reg.resolve('fst_hom1_hom2')`; the registry returns the value from
the fastest cache tier that has it (RAM, IndexedDB, file, or server
compute). Engine lives in `core/registry_core.js`. Configuration
lives in each atlas's `registries/data/*.json`.

**This is a real, useful component.** Spec:
[`SPEC_registry_v1.md`](docs/SPEC_registry_v1.md). 501 lines, covers
tiers, engine API, config schemas, conflict resolution, and the
hot-path / cold-path distinction critical for instant scrolling.

The previous chat may have remembered "registry was dropped" and
applied that memory to this proposal. That's the wrong inference.
The dropped thing was 5.1; the new thing is 5.2.

---

## 6. The latency tiers (the most important contract)

Every layer and operation is tagged with one of three tiers:

| Tier | Latency | Source | Page access |
|------|---------|--------|-------------|
| **hot** | < 1 ms | RAM (state) | direct read, synchronous |
| **warm** | 5–50 ms | IndexedDB | `await reg.resolve(...)` |
| **cold** | 100 ms – 10 s | file or server | `await reg.resolve(...)` |

Hot-tier data is pre-warmed by the registry at named trigger events
(`chrom_change`, `candidate_change`, `page_mount`) and pinned to
known locations in `AtlasState`. Pages read those locations directly,
with no `resolve()` call on the read path. This is what makes
scrolling, panning, zooming feel instant — the same way the legacy
monolith already worked, just made explicit.

If a page ever does `await reg.resolve(...)` inside a scroll handler
or draw loop, that's a bug.

See SPEC_registry_v1.md §2 for the full tier model.

---

## 7. Designed for scale (very large genomic tracks)

V1 ships with simple whole-load semantics: a hot layer's full
contents are loaded into RAM at the trigger event. This works for
single-chromosome scope (sim_mat ~1700×1700, robust_z ~5000 windows,
226 samples).

V2 will need to support larger scopes:
- Whole-genome at full resolution (28 chromosomes × ~10⁵ windows)
- Multi-species comparative (9–11 catfish genomes simultaneously)
- BAM-level coverage at base resolution
- Per-sample dosage matrices for hundreds of samples × millions of variants

To avoid a rewrite when v2 lands, v1 bakes in the necessary hooks:

1. **`resolve(key, args)` always takes args.** A `viewport` argument
   is just another arg. V1 ignores it for hot layers; v2 reads it.

2. **Layer entries can declare `chunked: true`.** V1 treats this as
   a no-op and loads the whole layer; v2 implements tile-based
   serving. The config is forward-compatible.

3. **Pre-warm scheduler accepts new trigger events.** V2 adds
   `viewport_change` to the existing three. V1's scheduler is
   designed as an event listener, so adding new events doesn't
   change the API.

4. **The cache key template supports viewport substitution.** A v1
   layer caches under `sim_mat:LG28`; a v2 chunked layer caches
   under `sim_mat:LG28:0:1000`. Same engine code; different config.

5. **`AtlasState` already namespaces by chromosome.** The pin
   location is `AtlasState.inversion.tracks.sim_mat[chrom]`, not a
   global. Adding viewport-tile namespacing is mechanical.

This means v1 is implementable in ~1000 LOC of core code, but the
contracts won't have to change for v2.

---

## 8. Server relationship

`atlas-core/server/` is the local backend bridge. It exposes:

- **shared endpoints** (`api/shared/`) for things common across
  atlases (cohort metadata, sample lookups, generic file fetch)
- **atlas-specific endpoints** (`api/<atlas_id>/`) mounted at
  assembly time by copying the atlas's `server-adapters/` into
  `server/api/<atlas_id>/`

The server is the interface between Atlas pages and compute engines.
Compute engines themselves (`engines/unified_ancestry/`,
`engines/inversion_popgen/`, etc.) live either inside an atlas
package or as external dependencies the server knows about.

The server itself stays in core because every atlas needs the same
HTTP plumbing. Atlas-specific routes are layered in via mountable
adapters.

---

## 9. Editing rules

**Core infrastructure task:** edit only `atlas-core/`. Use
`tests/mock-atlas/` for testing. Do not touch any atlas package.

**Atlas package task:** edit only `inversion-atlas/` (or
`<other>-atlas/`). Assume the core contract exists. Do not change
core.

**Metric integration task:** may edit both atlas-core and one atlas
package, but only for one named metric. Each metric integration must
include a `CONTRACT_DIFF.md` explaining:

- operation key
- endpoint
- inputs
- output schema
- cache key + tier
- page consumer
- core files changed
- atlas files changed
- test command

---

## 10. Assembly command

```bash
# Clean workspace
rm -rf atlas-workspace
mkdir -p atlas-workspace

# Stage 1: vendor the core
rsync -av atlas-core/ atlas-workspace/

# Stage 2: drop in atlas package(s)
rsync -av inversion-atlas/atlases/ atlas-workspace/atlases/

# Stage 3: mount atlas-specific server adapters
rsync -av inversion-atlas/atlases/inversion/server-adapters/ \
          atlas-workspace/server/api/inversion/

# Stage 4: link or copy atlas-specific engines
# (engines may be large; usually symlinked or referenced by path in config)
rsync -av inversion-atlas/atlases/inversion/engines/ \
          atlas-workspace/engines/inversion/

# Run
cd atlas-workspace
python server/server.py
# Open index.html in browser
```

For multiple atlases, repeat stages 2–4 for each atlas package.

---

## 11. Conflict policy

When two atlases declare the same key:

| Conflict type | Behavior |
|---------------|----------|
| Same key, identical config | silent merge (idempotent) |
| Same key, incumbent has `provisional: true` | NEW declaration wins, log info ("succession") |
| Same key, incumbent declares `owned_by: <new_atlas_id>` | NEW declaration wins, log info ("ownership transfer") |
| Same key, different config, no succession marker | throw at `register_atlas` time |
| Same operation key, different endpoints | throw |
| Same slot name in `slots.registry.json` | throw |
| Page id collision in `manifest.json` | namespace-suffix (`<atlas_id>:<page_id>`) |
| Server route collision | last-mount wins, log warning |

Atlases that anticipate sharing keys should namespace explicitly:
`inversion:fst_hom1_hom2` not `fst_hom1_hom2`. The engine treats
`:` as the namespace separator and does not auto-namespace.

### Why succession matters

The breeding-program order is genome → population → diversity →
inversion. Inversion is the LAST analytical step but also the FIRST
atlas to be implemented in this project (because the upstream files
already exist on disk, produced by ad-hoc pipelines).

This means inversion-atlas currently declares cohort-level layers
(`cohort_relatedness`, `cohort_sample_manifest`, `cohort_natora_pruned`,
etc.) that semantically belong to a future population-atlas. When
population-atlas eventually lands and declares those same keys, the
registry should NOT throw — it should let population take over
ownership.

The mechanism: inversion declares those layers with
`provisional: true` and `owned_by: "population"`. When population
registers, the registry sees the incumbent is provisional + names
the new atlas as the owner, so the new declaration wins silently.
No code change in inversion. No migration step. The hand-off is
declarative.

---

## 12. The one-sentence rule

> Core is the machine; each atlas is a cartridge.

Core provides the machinery. Atlases provide the science. Don't
duplicate atlas logic inside core. Don't duplicate core shell logic
inside atlases.

---

## 13. Reading order for a new contributor

1. This document — the pairing model.
2. `docs/SPEC_registry_v1.md` — the registry contract (hot/warm/cold,
   engine API, configs).
3. `docs/SPEC_atlas_shell_v1.md` (TBD) — the shell contract (router,
   discovery, mount API).
4. `docs/SPEC_atlas_state_v1.md` (TBD) — state slot vocabulary.
5. `docs/SPEC_server_bridge_v1.md` (TBD) — HTTP plumbing.
6. The mock atlas under `tests/mock-atlas/` — minimal working example.
7. `inversion-atlas/atlases/inversion/manifest.json` — real example.

---

End of pairing README.
