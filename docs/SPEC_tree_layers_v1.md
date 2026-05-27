# SPEC — tree-layer family v1

**Status**: proposal. Authored 2026-05-23 in `inversion-atlas/docs/atlas-core-proposals/`, intended for `atlas-core/docs/SPEC_tree_layers_v1.md`.

**Companion files**:
- Schema: `schemas/tree_layer.schema.json`
- Reference impl: extension to atlas-core's existing `layer_router.js` (sketch in §6 below)

**Open question (called out for review)**: should the tree-layer schema allow nested tree-layer references (a tree-layer whose nodes are themselves tree-layers)? **Proposed: no.** One level of tree is enough; nest by stacking layer dependencies instead. This keeps the resolver simple and avoids cycles.

---

## 1. Problem

Atlas-core's `layers.registry.json` today assumes one URL per layer — typed access to a single file (TSV, JSON, PAF, etc.). Real producer workflows often emit a **directory tree** of artifacts:

```
results_bpatlas/
├── 02_paf_passA/
│   ├── Cgar_h1_vs_Cmac_h1.paf
│   ├── Cgar_h1_vs_Cmac_h2.paf
│   └── ... (one per pair)
├── 02_paf_passB/
│   └── ... (parallel structure)
├── 03_breakpoints/
│   ├── anchor_Cgar/
│   │   └── breakpoint_zones.tsv
│   ├── anchor_Cmac/
│   │   └── breakpoint_zones.tsv
│   ├── reciprocity/
│   │   └── reciprocity_table.tsv
│   └── breakpoints_raw.tsv
├── 05_atlas_data/
│   ├── atlas_data.json
│   └── atlas_paf_arcs.json
└── 06_joint/
    └── joint_candidates.tsv
```

Three options for handling this today:

1. Register every file as its own layer (12+ layers for the BP_ATLAS tree). Pollutes the registry and forces the page to know each path.
2. Register the root as one layer and have the page glob (the "Mode B raw-folder interface" pattern from `data/comparative/cross_species/README.md`). Page-side, not type-checked.
3. New layer family: **tree-layer**. The registry declares the root + the expected structure + the leaf layer types. The router resolves sub-paths typed.

This SPEC defines option 3.

## 2. Design goals

1. **One registry entry per tree** instead of N entries per leaf.
2. **Typed access** — page asks for `bp_atlas.tree.03_breakpoints.reciprocity` and gets the resolved file content (TSV parsed, JSON parsed) without each page reimplementing the path walk.
3. **Schema-validated structure** — the registry declares the expected sub-paths; missing files surface as typed errors.
4. **Workflow integration** — a tree-layer's root maps to a workflow's `outputs_root` (per `SPEC_workflows_v1`). Tree-layer staleness is the workflow's status.
5. **No nested tree-layers** (open question above). Tree-layer leaves are scalar layers.

## 3. File location + shape

Inside `atlases/<atlas_id>/registries/data/layers.registry.json`, a tree-layer is one entry with `kind: "tree"`:

```jsonc
{
  "layer_id": "bp_atlas_results_v1",
  "kind": "tree",
  "label": "BP_ATLAS — full results tree",
  "version": 1,
  "cohort_id": "f1_hybrid_cga_cma",
  "reference_id": "fClaHyb_Gar_LG",
  "produced_by": "bp_atlas_pipeline",          // workflow_id from workflows.registry.json
  "root": "data/breakpoints/results_bpatlas/",
  "tree": {
    "02_paf_passA": {
      "kind": "dir",
      "children_pattern": "*.paf",
      "leaf_kind": "paf",
      "label": "Pass A wfmash PAFs (per pair)"
    },
    "02_paf_passB": {
      "kind": "dir",
      "children_pattern": "*.paf",
      "leaf_kind": "paf",
      "label": "Pass B wfmash PAFs (per pair)"
    },
    "03_breakpoints": {
      "kind": "dir",
      "children": {
        "anchor_Cgar": { "kind": "dir", "children": { "breakpoint_zones.tsv": { "kind": "leaf", "leaf_kind": "tsv" } } },
        "anchor_Cmac": { "kind": "dir", "children": { "breakpoint_zones.tsv": { "kind": "leaf", "leaf_kind": "tsv" } } },
        "reciprocity": { "kind": "dir", "children": { "reciprocity_table.tsv": { "kind": "leaf", "leaf_kind": "tsv" } } },
        "breakpoints_raw.tsv": { "kind": "leaf", "leaf_kind": "tsv" }
      }
    },
    "05_atlas_data": {
      "kind": "dir",
      "children": {
        "atlas_data.json":      { "kind": "leaf", "leaf_kind": "json" },
        "atlas_paf_arcs.json":  { "kind": "leaf", "leaf_kind": "json" }
      }
    },
    "06_joint": {
      "kind": "dir",
      "children": { "joint_candidates.tsv": { "kind": "leaf", "leaf_kind": "tsv" } }
    }
  }
}
```

## 4. Three node kinds in the tree

- **`dir`** — a directory. Has either `children` (explicit map of child names to nodes) OR `children_pattern` (glob for fan-out) + `leaf_kind` (type each match is parsed as).
- **`leaf`** — a single file. Has `leaf_kind` ∈ `{tsv, csv, json, paf, jsonl, bed, fasta, fai, vcf, vcfgz, gff, bin}`.
- **`tree_ref`** — (proposed but flagged in the open question) a reference to another tree-layer. **Default: not allowed** per the open question.

## 5. Leaf kinds (extensible)

| `leaf_kind` | Parsed as | Notes |
|---|---|---|
| `tsv` | array of row-objects keyed by header | First row is header; tab-delimited |
| `csv` | array of row-objects keyed by header | First row is header; comma-delimited |
| `json` | parsed JSON | |
| `jsonl` | array of parsed JSON objects | One per line |
| `paf` | array of PAF row-objects (12+ fields) | First 12 fields are PAF spec; rest are tagged-fields parsed into a `.tags` sub-object |
| `bed` | array of BED row-objects | First 3 cols required; extras parsed |
| `fasta` | iterator over `{name, seq}` | Streamed (don't load 2GB FASTA into memory) |
| `fai` | array of `{name, length, offset, linebases, linewidth}` | FASTA index |
| `vcf` | iterator over records | Streamed |
| `vcfgz` | iterator over records | Bgzipped + indexed; streamed via tabix-style |
| `gff` | array of GFF row-objects | |
| `bin` | raw bytes (Uint8Array) | Caller parses |

New leaf kinds can be added without changing the schema; the resolver looks up the kind in a registry of parsers.

## 6. API surface (layer_router.js extension)

Today `layer_router.js` exports something like:

```js
read(layerId) → Promise<data>
```

After this SPEC, scalar layers continue to work unchanged. Tree-layers add typed-path access:

```js
// New: typed-path read into a tree-layer
read(layerId, treePath?) → Promise<data>

// Examples:
await read('crossSpecies.bp_atlas_results_v1', '03_breakpoints.reciprocity.reciprocity_table.tsv');
// → parsed TSV array

await read('crossSpecies.bp_atlas_results_v1', '02_paf_passA');
// → Map of pair_name → parsed PAF (fan-out via children_pattern)

await read('crossSpecies.bp_atlas_results_v1');
// → metadata object describing the tree structure (no leaf parsing)
```

The `treePath` uses dot-separated keys matching the schema's `children` map. For `children_pattern` nodes, the path can include a wildcard:

```js
await read('crossSpecies.bp_atlas_results_v1', '02_paf_passA.Cgar_h1_vs_Cmac_h1.paf');
// → that specific PAF, parsed
```

Or the path can stop at the directory and get a Map:

```js
await read('crossSpecies.bp_atlas_results_v1', '02_paf_passA');
// → Map<filename, parsedPAF>
```

## 7. Validation rules

The reference implementation validates:

1. The root path exists.
2. Every explicitly-declared `children` entry resolves to an existing path.
3. Every `children_pattern` directory contains at least one match (warn if zero, don't fail — a workflow may not have run yet).
4. Every leaf node's `leaf_kind` is in the registered parsers list.
5. `produced_by` references a registered workflow id (cross-validation against `workflows.registry.json`).
6. `cohort_id` references a registered cohort (cross-validation against `cohorts.registry.json`).
7. Tree-paths are validated against the schema at read time; invalid paths throw `InvalidTreePathError`.

## 8. Interaction with the other registries

- **`workflows.registry.json`** — a tree-layer's `produced_by` field links it to a workflow. The workflow's status (per `SPEC_workflows_v1`) determines tree-layer staleness.
- **`cohorts.registry.json`** — a tree-layer carries `cohort_id`; cross-atlas reads of tree-layers go through the same cohort-discipline enforcement.
- **`pages.registry.json`** — pages can declare `requires_layer: 'crossSpecies.bp_atlas_results_v1.03_breakpoints.reciprocity.reciprocity_table.tsv'` (typed sub-path) and atlas-core mounts the page only if the path resolves.

## 9. Caching

Tree-layers cache per typed-path. Reading `03_breakpoints.reciprocity.reciprocity_table.tsv` doesn't load `02_paf_passA/`. The cache key includes the workflow's `knob_hash` (from status.json) so a workflow rerun with new knobs invalidates the relevant cache entries.

## 10. Lazy vs eager

Tree-layers are **lazy by default**. Reading the layer-id alone returns metadata (the parsed tree structure) but does NOT load leaf data. Eager loading is opt-in:

```js
await read('crossSpecies.bp_atlas_results_v1', { eager: true });
// → entire tree loaded; expensive for fan-out directories
```

For a 240-pair `02_paf_passA/` directory with 50KB PAFs each, eager loading is ~12MB. Acceptable for some workflows; refuse-with-explanation for others. Decision is per-page.

## 11. Failure modes

| Failure | atlas-core behaviour |
|---|---|
| Tree root path doesn't exist | Validation failure; atlas refuses to mount the layer |
| Tree-path read with invalid path | `InvalidTreePathError` at read time |
| Tree-path read with valid path but file missing | `FileNotFoundError` with the resolved absolute path |
| Tree-path read with valid path but parse fails | `ParseError` with line number (when parser supports it) |
| `children_pattern` glob returns zero matches | Warn at validation; reads return empty Map at run time |
| `leaf_kind` not in parsers registry | Validation failure |

## 12. Out of scope

- Streaming reads for non-streamed leaf kinds (TSV / JSON are loaded whole; FASTA / VCF are streamed; if you need streamed JSON, use JSONL).
- Watch-on-change (the cache invalidates on workflow knob_hash change, not on filesystem change; a long-running atlas session that wants to detect re-runs while open uses the workflow status_file's modified time).
- Write-back through tree-layers (registry is read-only at the atlas-core level; writes go through producer workflows).
- Nested tree-layers (the open question above; revisit in v2 if a real need emerges).

## 13. Versioning

Tree-layer entries have a `version` field per layer. The tree-layer SCHEMA has its own version (this SPEC is `v1.0`). Both versions are independent.

---

*End of SPEC. Reference implementation slots into atlas-core's existing `layer_router.js`.*
