# ADAPTER_CONTRACT — what every `adapter_atlas.js` must export

Status: **v1 (frozen)**.  Schema version: `adapter_atlas_v1`.

This is the contract between an **analysis module** and the Atlas/APLR
runtime.  Every analysis in the catalogue lives at
`analysis/<analysis_id>/` and follows this exact layout.

---

## §1 The folder layout

```
analysis/<analysis_id>/
├── schema_in.json          input contract (params + input layer types)
├── schema_out.json         output contract (one entry per produced layer)
├── compute.js              pure JSON-in / JSON-out, registry-agnostic
├── adapter_atlas.js        bridges compute() to Atlas/APLR runtime
├── example_input.json      fixture for tests / docs
├── example_output.json     precomputed reference output
└── README.md               (optional) short rationale + provenance
```

Plus an optional thin legacy shim at `analysis/<analysis_id>.js` for
older callers, **only** if anything still uses the pre-adapter calling
convention.  New code does not use the shim.

---

## §2 The §rules — what each file may and may NOT do

### compute.js — pure science

```js
// analysis/<analysis_id>/compute.js
export function compute(inputs, params) {
  // pure JSON-in / JSON-out function.
  // inputs is { layer_id: payload_object } as declared by adapter.meta.input_layer_types.
  // params  is { ... }  as declared by schema_in.json.
  // returns { layer_id: payload_object } as declared by adapter.meta.produces.
  return { ...output_layers };
}
```

**Forbidden in `compute.js`**:
- importing the registry, APLR, the librarian, the dispatcher, or any page-side helper
- DOM / `window` / `document` access
- `fetch()` / `XMLHttpRequest`
- filesystem paths (no `node:fs`, no relative file paths embedded in the science)
- reading or writing global state
- runtime feature detection ("if APLR exists then …")

`compute.js` is the science.  It must be testable from a unit-test runner
with nothing more than the two fixtures `example_input.json` and
`example_output.json`.

### adapter_atlas.js — the bridge

```js
// analysis/<analysis_id>/adapter_atlas.js
import { compute } from "./compute.js";

export const meta = {
  // identity
  analysis_id:        "iv_candidate_promoter",
  analysis_version:   "v1",
  atlas_id:           "inversion_atlas",
  schema_version:     "adapter_atlas_v1",

  // human-facing
  label:              "Inversion candidate promoter",
  description:        "Promotes window-band signals into a candidate-interval registry with chain evidence.",

  // contract — these must match schema_in.json / schema_out.json
  input_layer_types:  ["window_band_calls", "l3_contingency", "dosage_summary"],
  produces:           ["candidate_registry", "chain_evidence"],

  // runtime
  engine:             "atlas_js",      // | "atlas_js_worker" | "subprocess" | "endpoint"
  schema_in:          "./schema_in.json",
  schema_out:         "./schema_out.json",
  example_input:      "./example_input.json",
  example_output:     "./example_output.json",
  trigger_policy:     "manual",        // never "auto" on first registration
  status:             "active",        // | "experimental" | "deprecated" | "stub"
};

// Required: run.  Loads inputs (the librarian has already resolved them),
// validates them against schema_in.json, calls compute, validates outputs
// against schema_out.json, returns { layer_id: payload }.
export async function run(inputs, params, context) {
  // context: { atlas_id, scope, action_id, dispatcher } — registry-aware.
  return compute(inputs, params);
}

// Optional: preview.  Returns a DOM node (or a small JSON the page can render)
// for the panel that consumes one of the produced layers.  Used by page 6 /
// page composition fan-out so panels can render without re-implementing the
// layer's display logic.
export function preview(output_layers, panel_id) {
  // return a HTMLElement OR a {kind: "table" | "track" | "scatter" | ...} payload
}

// Optional: explain.  Returns a short string for the right-side inspector
// in the Graph Builder.  Free-form; informational only.
export function explain() { return "what this analysis does, why, what it doesn't"; }
```

**Allowed in `adapter_atlas.js`**:
- importing the local `compute.js`
- importing helpers from `analysis/_shared/` (e.g. fixture validators)
- reading the panel id from `context` to vary the preview shape

**Forbidden in `adapter_atlas.js`**:
- running anything when the module is imported (no side effects at load time)
- writing to the registry directly — the runtime / dispatcher does that
- silently downgrading `trigger_policy` from `manual` to `auto`

### schema_in.json — params + input contract

```json
{
  "$id":         "adapter_in_iv_candidate_promoter_v1",
  "schema_version": "adapter_in_v1",
  "params": {
    "type": "object",
    "additionalProperties": false,
    "properties": {
      "min_band_score":     { "type": "number", "default": 0.5 },
      "merge_windows_bp":   { "type": "integer", "default": 50000 }
    }
  },
  "inputs": {
    "window_band_calls": { "schema_ref": "../../schemas/structured_block_schemas/window_band_calls_v1.json" },
    "l3_contingency":    { "schema_ref": "../../schemas/structured_block_schemas/l3_contingency_v1.json" },
    "dosage_summary":    { "schema_ref": "../../schemas/structured_block_schemas/dosage_summary_v1.json" }
  }
}
```

### schema_out.json — one entry per produced layer

```json
{
  "$id":         "adapter_out_iv_candidate_promoter_v1",
  "schema_version": "adapter_out_v1",
  "produces": {
    "candidate_registry": {
      "schema_ref":   "../../schemas/structured_block_schemas/candidate_registry_v1.json",
      "stage":        "normalized",
      "description":  "One row per promoted candidate interval with chain provenance."
    },
    "chain_evidence": {
      "schema_ref":   "../../schemas/structured_block_schemas/chain_evidence_v1.json",
      "stage":        "normalized"
    }
  }
}
```

`schema_ref` is the source of truth for the layer's row contract.  If
the layer has a `layer_envelope_v1` form, the envelope wraps these rows.

### example_input.json / example_output.json

Tiny fixtures (≤ 20 rows where applicable).  The same fixtures power:

1. unit tests of `compute.js`
2. the page-6 panel preview when no real result exists yet
3. the docs for the analysis

**Rule**: `compute(example_input, default_params)` must deep-equal
`example_output` byte-for-byte (after stable sort) for every registered
adapter.  CI gate.

---

## §3 The §rules — what the registry tracks vs what code does

| Lives in the registry (JSONL)        | Lives in code (adapter / page)       |
|---|---|
| `analysis_registry.jsonl` row         | `compute.js`                         |
| `layer_registry.jsonl` row            | the layer's `schema_ref`             |
| `hook_registry.jsonl` row             | the panel's render function          |
| `analysis_results.jsonl` row          | the produced layer payload (on disk) |
| `connection_map.json` (built)         | the adapter's `meta` (read by the builder) |

**Critical**: the registry stores **contracts, results, and identity**.
It never stores random JS functions, page state, or in-memory objects.

---

## §4 The §rules — how pages/panels consume layers

Per `LAYER_GRAPH_BUILDER_SPEC.md` §0: **modules produce layers; pages
consume layers**.  Concretely:

- A page declares `requires_layers` and `optional_layers` in
  `hook_registry.jsonl`.
- A panel declares ONE `layer_id` it renders, plus its `panel_id`.
- The librarian resolves all of them and emits a `page_composition_plan_v1`.
- The panel calls `adapter.preview(layer_payload, panel_id)` (when the
  producing analysis has a preview function) OR renders from the layer
  envelope directly.

**Forbidden between pages/panels**:
- passing hidden in-memory JS objects for *scientific* outputs (use a
  layer or commit a result)
- using `window.SOME_GLOBAL` for cross-page data

**Allowed locally (per spec §5.6)**:
- temporary UI transforms: color choice, sort order, zoom level, facet layout
- these stay in the panel's `localStorage` and never become layers

---

## §5 §refusals

These survive prompt-rewrites:

1. **No registry imports in `compute.js`.**  If a science routine needs
   registry data, the *adapter* loads it and passes it as an input layer.
2. **No `auto` trigger on first registration.**  Promoting to auto is a
   deliberate per-workspace decision after the analysis has proven stable.
3. **No silent side effects at module load.**  Importing
   `adapter_atlas.js` must be cheap.  Heavy initialisation belongs in `run()`.
4. **No drift between TSV and JSONL.**  JSONL is canonical; TSV is a
   derived view emitted by `lib/tsv_from_jsonl.py`.  Editing TSV by hand
   for adapter-backed rows is forbidden (CI gate later).
5. **No magical analysis_id minting.**  The `analysis_id` is what the
   adapter declares.  The registry FK'ing into it must match exactly.
6. **No `compute(inputs, params)` that depends on global time / random
   without a seeded `params.rng_seed`.**  Reproducibility is a hard
   requirement; the result-cache lookup hashes the inputs + params.

---

## §6 The build / validate pipeline

```
              ┌──────────────────────────────────┐
              │  analysis/<id>/adapter_atlas.js   │ ← runtime
              │  analysis/<id>/schema_*.json      │ ← contracts
              │  analysis/<id>/example_*.json     │ ← fixtures
              └──────────────────────────────────┘
                              │
                              ▼ scan
              ┌──────────────────────────────────┐
              │  lib/build_connection_map.py      │
              │  – reads adapter meta             │
              │  – reads package_manifest_v1      │
              │  – reads page_v1 / panel_v1       │
              │  – joins layers ↔ analyses ↔ hooks │
              └──────────────────────────────────┘
                              │
                              ▼ emits
              ┌──────────────────────────────────┐
              │  01_registry/connection_map.json  │
              │  01_registry/*.jsonl (canonical)  │
              │  01_registry/*.tsv  (derived)     │
              └──────────────────────────────────┘
                              │
                              ▼ consumed by
              ┌──────────────────────────────────┐
              │  lib/readiness_planner.py         │
              │  – given requested pages/packages │
              │  – walks the map backwards        │
              │  – returns a readiness plan       │
              └──────────────────────────────────┘
                              │
                              ▼
              ┌──────────────────────────────────┐
              │  Pages render the plan            │
              │  (no analysis runs from a page)   │
              └──────────────────────────────────┘
```

The builder does **not** run any analysis.  It only validates the
catalogue and computes the connection map.  Running is the dispatcher's
job (separate concern, separate PR).

---

## §7 Packages, recipes, and the user-facing modes

**Package** = a bundle of related analyses, layers, and panels.
Declared in `packages/<package_id>/manifest.json` per
`package_manifest_v1.schema.json`.

**Recipe** = a saved selection of pages + packages + analyses + layers
for one project / run.  Declared in `recipes/<recipe_id>.json` per the
same `recipe_v1` shape (TBD; for v1 we use the in-browser `localStorage`
graph from the Graph Builder).

**Normal user mode** — the user picks pages or packages.  APLR
expands the selection into required layers, maps layers to producing
adapters, checks which results exist, and emits a readiness plan with
per-step states (COMPLETE / READY_TO_RUN / BLOCKED / STALE / MISSING /
UNAVAILABLE).

**Developer / debug mode** — the user opens the Graph Builder (page 7)
or the connection map; sees the whole graph with adapter ↔ layer ↔
panel ↔ page edges.

---

## §8 Worked example

The `discovery_karyotype_package` bundles three coupled adapters with
their layers and panels (manuscript path: candidate calling → karyotype
calling → polarisation):

```
packages/discovery_karyotype_package/manifest.json:

  analyses:
    iv_candidate_promoter         produces candidate_registry, chain_evidence
    karyotype_auto_caller         produces unpolarized_karyotype_calls
    karyotype_polarizer           produces polarized_karyotype_calls

  layers:
    candidate_registry            consumed by candidate_review_panel
    chain_evidence                consumed by candidate_review_panel
    unpolarized_karyotype_calls   consumed internally + karyotype_panel
    polarized_karyotype_calls     consumed by karyotype_panel + mendelian, popstats

  panels:
    candidate_overview_panel
    candidate_review_panel
    karyotype_panel

  pages:
    candidate_review              uses candidate_review_hook (page 6 today)
```

Each adapter has its own folder with its own `compute.js`.  The package
just lists them; coupling is opt-in (`requires`) in the manifest.

---

## §9 Migration plan

Existing analyses (`ngsrelate`, `ngspedigree`, `mendelian`, `popstats`)
were registered before the adapter contract existed.  They will be
migrated one at a time:

1. Create `analysis/<id>/{compute.js, adapter_atlas.js, schema_in.json, schema_out.json}`.
2. The legacy `scripts/runners/run_<id>.py` becomes the `engine: "subprocess"` reference.
3. Once the adapter exists, the row in `analysis_registry.jsonl` is regenerated by `build_connection_map.py`.
4. CI gate: `compute(example_input) == example_output` on every adapter.

Until migration completes, both old rows (without adapters) and new
adapter-backed rows coexist.  `build_connection_map.py` flags rows
without a backing adapter as `status: stub`.

---

_End of ADAPTER_CONTRACT.md (v1)._
