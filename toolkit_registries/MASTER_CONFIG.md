# MASTER_CONFIG — the one config file that knows where everything is

**Status:** v1, drafted 2026-05-06 (chat ~34).
**Companion files:**
- `atlas-core/master_config.example.yaml` — the template you copy and edit.
- `toolkit_registries/schemas/registry_schemas/master_config.schema.json` — the JSON Schema the engine validates against at startup.

---

## The contract in one sentence

> **The atlas registry knows where data lives because `master_config.yaml`
> tells it. Layer entries reference roots by name; literal paths exist
> only in this file. Move to a different machine: edit one file. The
> atlas adapts.**

---

## Why this exists

Before this contract, paths were scattered:

- `inversion-atlas/atlases/inversion/registries/data/layers.registry.json` had `path: data/cohort/relatedness/...` baked in.
- `popstats_server.config.yaml` had `base: /scratch/lt200308-agbsci/...` hardcoded.
- Pages did `fetch('data/...')` directly in some places.
- Test runs assumed the project tree was the data tree.

Moving the project to a new machine meant editing N files, hoping you
caught them all. Splitting "I'm computing fresh results" from "I'm
reading reference data" was a convention nobody enforced. New data
domains (SVs, recombination, anything) needed parallel paths added in
multiple places.

The master config fixes this by inverting the relationship:

- **The atlas defines named roles** (`cohort_relatedness`,
  `cohort_ancestry`, `candidates`, `cache`, `working_dir`, ...).
- **The master config maps role names to filesystem paths** on this
  particular machine.
- **Layer entries reference the role name**, not a literal path.
- **The engine resolves the role to a path** at fetch time.

The atlas code itself becomes path-free.

---

## File location and discovery

The master config sits at the workspace root:

```
<workspace>/
├── master_config.yaml            ← here
├── atlas-core/
│   ├── master_config.example.yaml  ← template; copy this and edit
│   └── core/
│       └── ...
├── inversion-atlas/
│   └── atlases/inversion/
│       └── ...
└── data/                         ← read-only data roots (one option)
    └── ...
```

Discovery order (engine startup, in `atlas-core/core/`):

1. `MASTER_CONFIG` env var → use that path.
2. `<cwd>/master_config.yaml`.
3. `<workspace>/master_config.yaml` (walk parents to find one).
4. Fall back to `master_config.example.yaml` and log a warning that
   the user should copy and edit it.

---

## The five top-level sections

| Section | Required | Purpose |
|---|---|---|
| `atlas`    | yes | workspace identity (root, default atlas, default chrom) |
| `species`  | no  | list of species this atlas knows about (multi-species support) |
| `roots`    | yes | named root directories the registry routes to |
| `server`   | no  | popstats_server.py settings (bind, CORS, caches) |
| `engines`  | no  | paths to compiled binary engines (server reads) |
| `defaults` | no  | per-engine default parameters |

`roots` is the heart of the file. Everything else exists to support
the atlas's other components (server, engines) but the **registry
itself only needs `atlas` + `roots`** to function. `species:` is
required only if you want multi-species behaviour; single-species
atlases can omit it.

---

## Multi-species support

The atlas registry supports running analyses on multiple species
side-by-side without forking the codebase. The pattern:

**1. One species.config.yaml per species** declaring its identity,
cohort, populations, and reference. See
`atlas-core/species.example.yaml` for two filled-in examples
(gariepinus, macrocephalus) and
`toolkit_registries/schemas/registry_schemas/species.config.schema.json`
for the formal contract.

**2. The master config's `species:` array lists active species.**
Each entry references a species.config file by path. Exactly one
species is `active: true` (the default focus); the others remain
loadable for cross-species analyses.

```yaml
species:
  - id:     "gariepinus"
    config: "species/gariepinus.config.yaml"
    active: true
  - id:     "macrocephalus"
    config: "species/macrocephalus.config.yaml"
    active: false
```

**3. Read-only data roots that exist per-species are
`species_scoped: true`.** The path contains `{species_id}` which the
registry resolves at fetch time:

```yaml
roots:
  precomp:
    path:           "./data/{species_id}/precomp"
    role:           "intervals"
    species_scoped: true

  cohort:
    path:           "./data/{species_id}/cohort"
    role:           "samples"
    species_scoped: true
```

When the active species is `gariepinus`, `precomp` resolves to
`./data/gariepinus/precomp`. Switch to `macrocephalus`, same root
entry resolves to `./data/macrocephalus/precomp`. **One root entry,
two species, no duplication in the config.**

**4. Roots NOT species-scoped are shared across species.**
Candidates, working_dir, cache, comparative — flat roots; species_id
is recorded as a field inside the data, not in the path. A candidate
from any species lives under `data/candidates/{candidate_id}/` and
its `lineage.json` carries `species_id: "gariepinus"` (or whatever).

This is the **plug-and-play model** for new species:

```
Day 1 — only gariepinus:
   master_config.species:        [gariepinus]
   data/gariepinus/...              ← read by species_scoped roots
   data/candidates/...              ← shared, species_id inside files

Day N — bighead catfish data lands:
   master_config.species:        [gariepinus, macrocephalus]   ← +1 entry
   data/macrocephalus/...           ← drop folder; same root entries serve it
   data/candidates/...              ← still shared; new candidates carry species_id
```

No layer entries change. No registry code change. No schema change.
The atlas absorbs species 2 with one new species.config.yaml and one
new line in master_config.

**5. Population substructure inside a species is append-only.** The
species.config.yaml's `populations:` list starts with one placeholder
entry (`mixed`, members: ALL) when substructure is unresolved.
Resolving substructure later (NGSadmix, pedigree) appends new entries
with new `population_id`s; the old `mixed` stays for back-compat —
results computed against `mixed` remain valid against their declared
population.

**What multi-species support does NOT do (intentionally):**

- No mixed-species cohorts — each cohort is one species. If a
  cross-species comparison is needed, run the analysis on each
  species' cohort separately and combine in the comparative layer.
- No species inference from data — species_id is declared in the
  config; data files trust the declaration.
- No species hierarchy / phylogeny inside the registry — that's a
  domain layer (`phylo_tree`), not registry config.

---

## The roots section

Roots are the registry's named addresses — what every layer entry
references when it says "where do I read this from?"

Each root is a named directory with a 4-role assignment:

```yaml
roots:
  cohort_relatedness:
    path: "./data/cohort/relatedness"
    role: "samples"
    description: "ngsRelate / KING raw outputs."
```

Three categories of roots, distinguished by `writable` + `ephemeral`:

### Category 1 — read-only data roots

Filled by upstream pipelines (LANTA SLURM, manual analyses, external
tools). The registry **reads**, never writes.

Examples: `precomp`, `cohort`, `cohort_relatedness`, `cohort_ancestry`,
`cohort_dosage`, `beagle`, `bams`, `reference`, `comparative`.

```yaml
cohort_relatedness:
  path: "/path/to/relatedness"
  role: "samples"
  # writable: false (default)
  # ephemeral: false (default)
```

When data is missing, layers that reference these roots return `null`
with a clear "no data at <root>/<sub>" warning rather than crashing.
Pages handle the null case gracefully (typically: render an empty
panel with a "no data" message).

### Category 2 — working_dir

Persistent working directory for browser-side analysis outputs that
don't fit the per-candidate layout. Atlas reads, atlas writes,
persistent across sessions.

```yaml
working_dir:
  path: "./working_dir"
  role: "results"
  writable: true
  description: "Cohort-wide derived tables, exports, etc."
```

Examples: a cohort-wide dN/dS table computed in the browser, an
exported CSV of candidate calls, a manuscript-ready figure JSON.

### Category 3 — cache

Ephemeral results cache. Server compute results land here so a re-call
hits cached JSON instead of recomputing. Browser-side intermediate
state may also use it.

**Safe to delete.** Gets rebuilt on next call.

```yaml
cache:
  path: "/mnt/e/inversion-atlas-cache"
  role: "results"
  writable: true
  ephemeral: true
  excluded_from_tarballs: true
```

The cache root sits **outside the project tree** by convention so
test-run accumulation doesn't bloat handoff tarballs or git status.

Layout under the cache root:

```
<cache>/
├── server_results/             ← persist hook target
│   └── {op_id}/{hash}.json
└── (free-form for the rest)
```

---

## Roles — the 4-namespace organizing logic

Inherited from the LANTA-era toolkit registries; canonical mental
model for how data divides:

| Role | Asks the question | Roots that contribute |
|---|---|---|
| **samples** | WHO?  | `cohort`, `cohort_relatedness`, `cohort_ancestry`, `bams` |
| **intervals** | WHERE? | `precomp`, `cohort_dosage`, `beagle`, `reference`, `comparative` |
| **evidence** | WHAT (per-candidate)? | `candidates`, `arrangement_calls`, `review_sessions` |
| **results** | WHAT (numerical)? | `working_dir`, `cache` |

These are **API namespaces**, not folder names. Layer entries in the
atlas registry inherit the role from their root, and the registry's
4-role facade (when implemented in a future session) exposes
`reg.samples.X()` / `reg.intervals.X()` / `reg.evidence.X()` /
`reg.results.X()` as friendly wrappers around `reg.resolve(...)`.

A root that mixes roles is a smell: split it.

---

## How layer entries reference roots (forthcoming refactor)

**Today** (chat ~34 state):

```jsonc
"cohort_relatedness": {
  "tier": "warm",
  "source": "file",
  "path": "data/cohort/relatedness/ngsrelate/{run_id}/relatedness.tsv"
}
```

**Tomorrow** (the refactor that lands when page1 migration touches
this layer):

```jsonc
"cohort_relatedness": {
  "tier": "warm",
  "source": "file",
  "root": "cohort_relatedness",
  "path_under_root": "ngsrelate/{run_id}/relatedness.tsv"
}
```

The engine `_fillTemplate` learns to resolve `root` → master_config
roots → prepend → `path_under_root` with slot-fill. The layer is now
machine-portable. Same layer entry works on LANTA, on `/mnt/e/`, on a
laptop dev environment.

**The refactor is per-page, not all-at-once.** Page1 migration touches
some layers, those get rebased. Subsequent migrations touch others.
After all 22 pages are migrated, every layer is rebased. No big-bang.

---

## Server section — popstats_server.py settings

The server reads master_config too. Sections it cares about:

```yaml
server:
  bind:           { host, port }
  cors_origins:   [...]
  validation:     { min_group_n: 10 }
  popstats_cache: { path, max_bytes, health_ttl_sec }
  dosage:         { max_region_bp, samples_file }

engines:
  region_popstats: "/path/to/binary"
  hobs_windower:   "/path/to/binary"
  ...

defaults:
  popstats:  { win_bp, step_bp, type, downsample, ncores }
  hobs:      { scales: [...] }
  angsd:     { threads, major_minor, min_maf, ... }
```

Launch:

```bash
python popstats_server.py --master-config /path/to/master_config.yaml
```

For back-compat the server still accepts `--config <legacy>` pointing
at the old `popstats_server.config.yaml` shape. The two configs do not
need to coexist — picking master config is the recommended path going
forward.

---

## Variable substitution

The config supports `${roots.X.path}` substitution to avoid duplicating
paths:

```yaml
server:
  popstats_cache:
    path: "${roots.cache.path}/popstats_engine_cache"
```

Substitution is resolved once at config-load time. Cycles are
detected and rejected (the engine throws with a clear cycle path).

---

## Validation

The engine validates `master_config.yaml` against
`master_config.schema.json` at startup. Failure → engine refuses to
start with the validation error printed.

Two warnings (not errors):
- `roots.X.path` doesn't exist on disk → log "missing root: X" and
  continue. Layers referencing it will return null at resolve time.
- `engines.X` is null but a layer needs it → log "engine X disabled
  but layer Y requires it" and continue. The layer's resolve fails
  cleanly.

---

## Adding a new data domain

You have ngsAdmix output for the whole genome and want to wire it.
Three steps:

1. **Add a root to `master_config.yaml`:**

   ```yaml
   roots:
     cohort_ngsadmix_genome:
       path: "/some/path/to/ngsadmix_whole_genome"
       role: "samples"
       description: "Whole-genome NGSadmix Q matrices."
   ```

2. **Add a layer entry referencing that root** (in the atlas's
   `layers.registry.json`):

   ```jsonc
   "ngsadmix_genome_q": {
     "tier": "warm",
     "preload_on": "page_mount",
     "source": "file",
     "root": "cohort_ngsadmix_genome",
     "path_under_root": "K{K}/ngsadmix.qopt",
     "schema": "schemas/ngsadmix_q.schema.json"
   }
   ```

3. **Drop the schema** in the atlas's `schemas/` folder if one
   doesn't exist yet.

That's it. No engine code change. Pages call
`registry.resolve('ngsadmix_genome_q', { K: 8 })` and get the data.

---

## Adding a new computer

You're moving the work from your laptop to a workstation, or back to
LANTA, or sharing with a colleague. Steps:

1. Copy the project tarball.
2. `cp atlas-core/master_config.example.yaml master_config.yaml`.
3. Edit the `roots:` section: change paths to match this machine's
   filesystem.
4. Edit `engines:` if engine binaries live in different places.
5. Launch.

The atlas code, the layer registry, the schemas, the pages — none of
it changes. Only `master_config.yaml`.

---

## What this does NOT do

- It does NOT replace per-atlas `layers.registry.json` /
  `operations.registry.json` etc. Those define WHAT the registry
  serves. The master config defines WHERE.
- It does NOT define schemas. Schemas live alongside layers in
  `<atlas>/registries/schemas/` (atlas-specific) or in
  `toolkit_registries/schemas/` (registry-wide canonical).
- It does NOT prescribe a folder layout inside roots. Each root's
  internal layout is a per-domain decision (matches the upstream
  tool's native layout when reading raw, matches the atlas
  convention when reading curated).
- It does NOT belong to any one atlas. Future atlases (genome,
  population, comparative) all read the same master config; their
  layer entries reference the same roots.

---

## Reading order for a new contributor

1. **This file** — you're reading it.
2. `master_config.example.yaml` — the template; copy and edit it.
3. `DATABASE_DESIGN.md` — the 4-role mental model (samples /
   intervals / evidence / results) and FK discipline.
4. `<atlas>/registries/data/layers.registry.json` — what the atlas
   actually serves.
5. The page or analysis module you're working on — what it actually
   needs.

That's the chain. Master config → layers → pages.
