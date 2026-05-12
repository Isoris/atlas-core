# ACTIVATOR_EXTRACTOR — mapping the two access patterns

Two ways the registry produces a payload for the caller:

1. **Extractor** — read an existing file/folder, extract the payload.
2. **Activator** — call an analysis (server compute or browser-side
   module) that *produces* the payload.

Both flow through the same `registry.resolve(layerKey, args)` call.
The layer entry's `source` field tells the dispatcher which kind it is.

---

## The mapping

`source` lives on every layer entry in
`<atlas>/registries/data/layers.registry.json` and is enumerated in
`atlas-core/core/registry_core.schema.json` as `source_kind`:

| `source` value | Role         | Direction                              | Dispatch              |
|---|---|---|---|
| `'file'`       | **extractor**| Read a path from disk                  | `_fetchFromFile`      |
| `'operation'`  | **activator**| POST to server endpoint, compute new   | `OperationRunner.run` |
| `'analysis'`   | **activator**| Call a browser-side JS module          | `_fetchFromAnalysis`  |
| `'inline'`     | (neither)    | Constant declared inline in config     | `_fetchInline`        |

The runtime dispatch lives in `atlas-core/core/registry_core.js`
(`_fetchByEntry`, ~line 469).

---

## Extractor pattern (`source: 'file'`)

Reads a file from a master_config root, optionally parses it
(json/tsv/csv/binary), and returns the payload. The "extraction"
contract is whatever the layer's `schema` field points at — the schema
validates what came out of the file.

Required layer fields: `tier`, `source: 'file'`, `path`.

Optional: `root` + `path_under_root` (post-refactor; see
MASTER_CONFIG.md §"How layer entries reference roots"), `format`,
`schema`, `schema_status`, `fields`, `pin_to`, `chunked`, `writable`.

```jsonc
"relatedness_ngsrelate": {
  "tier":            "warm",
  "source":          "file",
  "root":            "cohort_relatedness",
  "path_under_root": "ngsrelate/{run_id}/relatedness.tsv",
  "format":          "tsv",
  "schema":          "schemas/relatedness.schema.json"
}
```

When the file doesn't exist, the layer resolves to `null` and the
caller gets a clean "no data" surface. No exception unless the schema
is `validated` and the parsed payload fails the schema check.

`registry.write(layerKey, args, payload)` is permitted for
`source: 'file'` layers when their `writable: true` flag is set — this
is how browser analysis modules persist results back to disk via the
server's `POST /file/` endpoint.

---

## Activator pattern (`source: 'operation'`)

Calls an HTTP endpoint on the atlas backend server (e.g.
`atlas_server.py`), returns the parsed JSON response.

Required layer fields: `tier`, `source: 'operation'`, `operation`
(name of an entry in `<atlas>/registries/data/operations.registry.json`).

The **operation entry** itself is the activator definition:

```jsonc
// operations.registry.json
"region_popstats": {
  "endpoint":       "/popstats/region",
  "method":         "POST",
  "inputs":         ["chrom", "start_bp", "end_bp", "group_id"],
  "output_schema":  "schemas/popstats_result.schema.json",
  "cache_key":      "{chrom}:{start_bp}-{end_bp}:{group_id}",
  "cache_tier":     "warm",
  "engine":         "region_popstats"
}
```

Layer-side wiring:

```jsonc
// layers.registry.json
"popstats_region": {
  "tier":      "warm",
  "source":    "operation",
  "operation": "region_popstats",
  "persist":   true,      // optional: write result to results cache
  "schema":    "schemas/popstats_result.schema.json"
}
```

When `persist: true`, the registry calls `write(layerKey, args, result)`
in the background after a successful operation — subsequent identical
calls hit the persisted cache instead of recomputing. See
`registry_core.schema.json` §`layer_entry.persist` for the exact
contract.

The full operation_entry schema lives at
`schemas/registry_schemas/operation_entry.schema.json` (canonical) and
is referenced from `core/registry_core.schema.json`.

---

## Activator pattern (`source: 'analysis'`)

Calls a JS module function inside the browser instead of hitting the
server. Same activator role; different execution surface.

Required layer fields: `tier`, `source: 'analysis'`, `analysis`
(path + export name, e.g. `'analysis/mendelian.js#runMendelianTest'`).

Useful when the computation is cheap enough to run in-browser, doesn't
need a C engine, and the result still belongs in the registry's cache
hierarchy so other layers can fan out from it.

---

## Choosing between the two

| Question | Answer |
|---|---|
| Data already produced by an upstream pipeline (SLURM, manual run)? | **extractor** (`file`) |
| Computation lives in a server C binary (region_popstats, angsd, …)? | **activator/operation** |
| Computation is a small JS calculation against already-resolved layers? | **activator/analysis** |
| Result should be persisted so the next call doesn't recompute? | activator with `persist: true`, or compute once and switch the layer to `file` once data lands |

---

## Where each side's schema lives

| Side | Schema | Location |
|---|---|---|
| **Extractor — payload shape** | per-layer (e.g. `relatedness.schema.json`, `boundary_refined.schema.json`) | `<atlas>/registries/schemas/` (atlas-specific), `toolkit_registries/schemas/registry_schemas/` (cross-atlas), `toolkit_registries/schemas/structured_block_schemas/` (per-aspect evidence) |
| **Extractor — layer wiring** | `layer_entry` definition | inline in `atlas-core/core/registry_core.schema.json` |
| **Activator — operation wiring** | `operation_entry` definition | canonical in `toolkit_registries/schemas/registry_schemas/operation_entry.schema.json`; mirrored inline in `atlas-core/core/registry_core.schema.json` |
| **Activator — output payload** | per-operation (e.g. `popstats_result.schema.json`) | `<atlas>/registries/schemas/` (atlas-specific) |

The cross-cutting takeaway: in `toolkit_registries/` everything is
*payload* contracts plus the canonical `operation_entry` definition.
The `source_kind` enum that decides extractor-vs-activator dispatch
stays in `core/` because it's a runtime concern.

---

## Why not rename the enum to `activator` / `extractor`?

Two reasons we keep `source: 'file' | 'operation' | 'analysis' | 'inline'`:

1. **Three activator variants would still need names.** `operation`
   and `analysis` already separate server-compute from browser-compute;
   a single `activator` value would collapse useful information.
2. **Every existing `layers.registry.json` uses these names.** A rename
   touches every atlas, every page, and `core/registry_core.js`.

What we do instead: this document and `STATUS.md` use "activator" /
"extractor" as the conceptual labels, and the enum stays as the
implementation labels. Cross-reference here when the terminology
mismatch is confusing.
