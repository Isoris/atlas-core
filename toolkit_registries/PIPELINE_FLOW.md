# PIPELINE_FLOW — actions, extractors, and the layer registry

**Status:** v1 spec, drafted 2026-05-12. Grounded in the existing
`atlas-core/server/atlas_server.py` (FastAPI, ~2.4k lines) and
`atlas-core/core/registry_core.js` (~700 lines). No new compute
engines, no replacement endpoints — this doc layers a thin
action/extractor/envelope contract on top of what's already running.

---

## The principle

> **Capture first, normalize later. Raw outputs are not Atlas data —
> only validated layer envelopes are. Actions create or modify layers.
> Extractors convert raw output into layer payloads. The registry
> indexes layer envelopes. The Atlas renders them.**

Three rules:

1. **Atlas pages MUST consume layer envelopes only.** Never raw TSV,
   never random Excel, never RDS.
2. **Every state-changing call MUST be an action manifest** — recorded
   in `registry/actions.log.jsonl`.
3. **Staging is allowed.** If the final schema isn't known, capture
   the raw fields in a `stage: "staging"` envelope so the data is
   discoverable. A converter later promotes it to `stage: "normalized"`.

---

## The minimal stable core

Every layer envelope has exactly these fields (per
`schemas/registry_schemas/layer_envelope.schema.json`):

| Field | Required | Purpose |
|---|---|---|
| `layer_id`       | yes | stable id, globally unique |
| `layer_type`     | yes | type tag (`fst_windows`, `inversion_candidate`, …) |
| `schema_version` | yes | names the per-type payload schema (`fst_windows_v1`, `staging_inversion_candidate_v0`, …) |
| `stage`          | yes | `"staging"` (loose) or `"normalized"` (strict) |
| `dataset_id`     | yes | cohort_id (HIERARCHY_SPEC) or species_id (legacy) |
| `coordinate`     | no  | `{chrom, start_bp, end_bp}` if applicable |
| `sample_scope`   | no  | `{group_id?, group_ids?, sample_ids?}` |
| `source_files`   | no  | paths of raw files this came from |
| `provenance`     | no  | `{action_id, source_layer_ids, runner, extractor, engine, engine_version, config_hash}` |
| `status`         | yes | `review` / `active` / `deprecated` / `stale` / `superseded` |
| `created_at`     | yes | ISO 8601 |
| `payload`        | no  | the typed data (loose for staging, schema-validated for normalized) |

Atlases may add extra top-level fields. They must not remove any of
the required ones.

---

## The flow

```
┌─────────────┐
│   Atlas     │  user clicks a button
│   (page)    │
└──────┬──────┘
       │  1.  POST /api/actions
       │      { action_id, type, dataset_id, runner, target, params,
       │        expected_outputs: [{layer_type, schema_version}] }
       ▼
┌─────────────────────────────────────────┐
│   atlas_server (existing FastAPI)        │
│  ┌───────────────────────────────────┐  │
│  │ 2. validate manifest              │  │
│  │    against action_manifest.schema │  │
│  │    and atlas.schema_in/<type>.    │  │
│  │ 3. append to actions.log.jsonl     │  │
│  │    status=queued                  │  │
│  └────────────┬──────────────────────┘  │
│               │ dispatch_action(manifest)│
│               ▼                          │
│  ┌───────────────────────────────────┐  │
│  │   atlas dispatcher                 │  │
│  │   (per-atlas Python module)        │  │
│  │   maps type → runner               │  │
│  │   e.g. type='run_popstats' →       │  │
│  │       calls /api/popstats/groupwise│  │
│  │   e.g. type='import_excel' →       │  │
│  │       reads Excel file directly    │  │
│  └────────────┬──────────────────────┘  │
│               │ raw outputs (TSV, JSON,  │
│               │ Excel, RDS, …)           │
│               ▼                          │
│  ┌───────────────────────────────────┐  │
│  │   atlas dispatcher                 │  │
│  │   maps layer_type → extractor      │  │
│  │   extractor.parse(raw) → payload   │  │
│  │   validate payload against         │  │
│  │     schema_out/<schema_version>    │  │
│  │   wrap payload in layer_envelope   │  │
│  │   write to layers/<layer_id>.json  │  │
│  │   append to layers.registry.json   │  │
│  └────────────┬──────────────────────┘  │
│               │                          │
│  ┌────────────▼──────────────────────┐  │
│  │ 4. append to actions.log.jsonl    │  │
│  │    status=success                  │  │
│  │    produced_layers=[layer_id, …]   │  │
│  └────────────┬──────────────────────┘  │
└───────────────┼──────────────────────────┘
                │  HTTP 200 { layer_ids }
                ▼
┌─────────────┐
│   Atlas     │  5. GET /file/layers/<layer_id>.json
│   (page)    │     render payload
└─────────────┘
```

---

## What the existing server already does — re-use, don't replace

| New thing | Existing primitive |
|---|---|
| Write a layer JSON to disk | `POST /file/<path>` (registry.write) — already allowlisted, see `_is_path_allowed_for_write` in atlas_server.py |
| Read a layer JSON from disk | `GET /file/<path>` (registry.resolve via LayerRouter) |
| Run popstats / FST / dXY | `POST /api/popstats/groupwise` — wraps `region_popstats` from `unified_ancestry/engines/fst_dxy/` |
| Run HOBS / HWE | `POST /api/popstats/hobs_groupwise` — wraps `angsd_patched` + `hobs_windower` |
| Read instant_q ancestry | `POST /api/ancestry/groupwise_q` — reads the `unified_ancestry/src/instant_q` cache |
| Run an LD test | `POST /api/shelf_ld_test`, `POST /api/ld/split_heatmap` |
| Cache compute results | Already content-addressable at `${cache_dir}/<subsystem>/<hash>.json` |
| Free-form server compute | `POST /compute/<name>` (see `core/operation_runner.js`) |

So the new endpoints are **only**:

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/actions` | submit an action manifest |
| `GET`  | `/api/actions/{action_id}` | read the action log entry (status/produced_layers/error) |
| `GET`  | `/api/layers` | list registered layers (with filters) |
| `GET`  | `/api/layers/{layer_id}` | read one envelope (redirect/equivalent to `GET /file/<path>`) |

Everything else is existing primitives. The action endpoint is a thin
wrapper that *orchestrates* runner + extractor + envelope-write +
log-append.

---

## Per-atlas wiring — `schema_in/`, `schema_out/`, dispatcher

Each atlas lays out its registry like this:

```
<atlas>/
└── registries/
    ├── schemas/
    │   ├── schema_in/                ← input manifests (one per action type)
    │   │   ├── run_popstats_v1.schema.json
    │   │   ├── run_ngsadmix_v1.schema.json
    │   │   ├── import_excel_v1.schema.json
    │   │   └── normalize_layer_v1.schema.json
    │   └── schema_out/               ← layer payload schemas
    │       ├── fst_windows_v1.schema.json
    │       ├── ancestry_q_v1.schema.json
    │       ├── candidate_regions_v1.schema.json
    │       ├── staging_inversion_candidate_v0.schema.json
    │       └── staging_excel_table_v0.schema.json
    ├── data/
    │   ├── actions.registry.json     ← action type → runner module
    │   ├── extractors.registry.json  ← layer_type → extractor module
    │   ├── layers.registry.json      ← (existing) layer index
    │   └── operations.registry.json  ← (existing) source='operation' layers
    └── dispatcher.py                 ← THE dispatcher (≤ 100 lines)
```

Two folders, one dispatcher. That's the per-atlas contract.

### dispatcher.py — the only Python file each atlas needs

Skeleton (~80 lines, copy-paste between atlases):

```python
# <atlas>/registries/dispatcher.py
import importlib, json, pathlib, time, uuid, jsonschema

HERE        = pathlib.Path(__file__).parent
ACTIONS     = json.loads((HERE / "data/actions.registry.json").read_text())
EXTRACTORS  = json.loads((HERE / "data/extractors.registry.json").read_text())
SCHEMA_IN   = HERE / "schemas/schema_in"
SCHEMA_OUT  = HERE / "schemas/schema_out"

def _load_schema(folder, name):
    return json.loads((folder / f"{name}.schema.json").read_text())

def _import(dotted):
    mod, fn = dotted.rsplit(".", 1)
    return getattr(importlib.import_module(mod), fn)

def dispatch_action(manifest, atlas_server_client):
    # 1. validate manifest against schema_in/<type>_v<N>.schema.json
    type_schema = _load_schema(SCHEMA_IN, manifest["type"] + "_v1")
    jsonschema.validate(manifest, type_schema)

    # 2. look up runner
    entry = ACTIONS["actions"][manifest["type"]]
    runner = _import(entry["runner"])

    # 3. run it; returns dict of named raw output paths
    raw_outputs = runner(manifest, atlas_server_client)

    # 4. for each expected output, find the extractor, parse, wrap
    produced = []
    for out in manifest.get("expected_outputs", []):
        ex = next(e for e in EXTRACTORS["extractors"]
                  if e["layer_type"] == out["layer_type"]
                  and e["schema_version"] == out["schema_version"])
        parser = _import(ex["parser"])
        payload = parser(raw_outputs, ex.get("params", {}))

        # validate payload against schema_out/<schema_version>.schema.json
        if out.get("stage", "normalized") == "normalized":
            payload_schema = _load_schema(SCHEMA_OUT, out["schema_version"])
            jsonschema.validate(payload, payload_schema)

        envelope = _wrap(manifest, ex, out, payload, raw_outputs)
        layer_path = _persist(envelope, atlas_server_client)
        produced.append(envelope["layer_id"])

    return produced

def _wrap(manifest, ex, out, payload, raw_outputs): ...
def _persist(envelope, client): ...
```

### actions.registry.json

```jsonc
{
  "actions": {
    "run_popstats": {
      "runner":          "runners.popstats.run_fst",
      "schema_in":       "run_popstats_v1",
      "description":     "Pairwise FST/dXY/π via region_popstats."
    },
    "import_excel": {
      "runner":          "runners.import.import_excel_table",
      "schema_in":       "import_excel_v1",
      "description":     "Import a manually-curated Excel table as a staging layer."
    },
    "normalize_layer": {
      "runner":          "runners.normalize.run_converter",
      "schema_in":       "normalize_layer_v1",
      "description":     "Promote a staging layer to a normalized layer via a converter."
    }
  }
}
```

### extractors.registry.json

```jsonc
{
  "extractors": [
    {
      "extractor_id":  "extract_fst_windows_v1",
      "layer_type":    "fst_windows",
      "schema_version":"fst_windows_v1",
      "stage":         "normalized",
      "parser":        "extractors.fst_windows.extract",
      "input_format":  "tsv"
    },
    {
      "extractor_id":  "extract_excel_staging_v0",
      "layer_type":    "excel_table",
      "schema_version":"staging_excel_table_v0",
      "stage":         "staging",
      "parser":        "extractors.excel.import_staging",
      "input_format":  "excel"
    }
  ]
}
```

---

## Folder convention (workspace side)

```
<dataset_root>/
├── registry/
│   ├── layers.registry.json          ← index of all envelope files
│   ├── actions.log.jsonl             ← append-only action log
│   └── runner_logs/                  ← per-action stdout/stderr
│       └── act_<id>.log
│
├── raw_results/                      ← whatever pipelines produced (TSV, Excel, RDS, …)
│   ├── popstats/
│   ├── d17/
│   ├── unified_ancestry/
│   └── manual_excel/
│
├── layers/                           ← envelope JSONs, by type
│   ├── fst_windows/<dataset_id>/<chrom>/<layer_id>.json
│   ├── ancestry_q/<dataset_id>/<chrom>/<layer_id>.json
│   ├── candidate_regions/<dataset_id>/<layer_id>.json
│   └── staging/<layer_type>/<dataset_id>/<layer_id>.json
│
└── cache/                            ← ephemeral (server cache lives outside the project tree)
```

`layers/` and `registry/` are the new directories the action endpoint
writes to. Both are added to `master_config.yaml` as roots
(`role: results`, `writable: true`, `cohort_scoped: true` if the atlas
has migrated to the cohort-scoped layout — see HIERARCHY_SPEC.md).

---

## Worked example — three flows end-to-end

The example uses the existing `inversion-atlas` and the existing
`/api/popstats/groupwise` endpoint. Nothing here is hypothetical.

### Flow A — Atlas reads a layer (extractor / read pattern)

```
1. Atlas page calls:
     registry.resolve('fst_windows', {
       dataset_id: 'main_226_hatchery',
       chrom:      'C_gar_LG28',
       layer_id:   'fst_windows_main_226_hatchery_LG28_INV_001_v1'
     })

2. registry_core.js resolves layer entry source='file':
     GET /file/layers/fst_windows/main_226_hatchery/C_gar_LG28/
           fst_windows_main_226_hatchery_LG28_INV_001_v1.json

3. Server returns the envelope JSON; LayerRouter parses; page receives:
     {
       layer_id:   "fst_windows_main_226_hatchery_LG28_INV_001_v1",
       layer_type: "fst_windows",
       schema_version: "fst_windows_v1",
       stage:      "normalized",
       dataset_id: "main_226_hatchery",
       coordinate: { chrom: "C_gar_LG28", start_bp: 14815000, end_bp: 18305000 },
       sample_scope: { group_ids: ["inv_LG28_INV_001_HOM_REF",
                                    "inv_LG28_INV_001_HOM_INV"] },
       provenance: { action_id: "act_1715000000000_a4b",
                     engine: "region_popstats", engine_version: "v0.4.1" },
       status:     "active",
       created_at: "2026-05-12T14:35:22Z",
       payload: {
         windows: [
           { start_bp: 14815000, end_bp: 14825000, fst: 0.02, n_sites: 412 },
           { start_bp: 14825000, end_bp: 14835000, fst: 0.05, n_sites: 388 }
         ],
         summary: { n_windows: 2, mean_fst: 0.035, max_fst: 0.05 }
       }
     }

4. Page renders payload.windows as the FST track.
```

### Flow B — Atlas runs popstats end-to-end (action pattern)

```
1. User clicks "compute FST inside candidate LG28_INV_001".

2. Atlas constructs an action manifest and POSTs it:
     POST /api/actions
     {
       "action_id":    "act_1715000000000_a4b",
       "type":         "run_popstats",
       "dataset_id":   "main_226_hatchery",
       "runner":       "run_popstats",
       "target": {
         "chrom":    "C_gar_LG28",
         "start_bp": 14815000,
         "end_bp":   18305000,
         "groups": {
           "inv_LG28_INV_001_HOM_REF": ["CGA_001", "CGA_007", ...],
           "inv_LG28_INV_001_HOM_INV": ["CGA_003", "CGA_017", ...]
         }
       },
       "params": { "stat": "fst", "win_bp": 10000, "step_bp": 5000 },
       "expected_outputs": [
         { "layer_type": "fst_windows", "schema_version": "fst_windows_v1" }
       ]
     }

3. Server (atlas_server.py) does:
   a. Validate the manifest against action_manifest.schema.json +
      atlas schema_in/run_popstats_v1.schema.json.
   b. Append a 'queued' entry to registry/actions.log.jsonl.
   c. Call the atlas dispatcher: dispatch_action(manifest, server_client).
   d. dispatcher.dispatch_action() resolves type='run_popstats' →
      runner='runners.popstats.run_fst'.
   e. The runner internally POSTs to /api/popstats/groupwise (the
      existing endpoint), which runs region_popstats, returns parsed
      windows.  The runner writes those to
        cache/act_<id>/popstats.windows.tsv
      as raw output.
   f. dispatcher picks the extractor matching layer_type='fst_windows'
      + schema_version='fst_windows_v1', calls
        parser(raw_outputs, params) → payload dict.
   g. dispatcher validates payload against
        schema_out/fst_windows_v1.schema.json.
   h. dispatcher wraps payload in a layer envelope, POSTs to
        /file/layers/fst_windows/.../fst_windows_…_v1.json
      (the existing write endpoint — already allowlisted).
   i. dispatcher appends layer_id to layers.registry.json.
   j. Server appends 'success' entry to actions.log.jsonl with
        produced_layers=[fst_windows_…_v1].

4. Server responds:
     HTTP 200 { "action_id": "act_...", "produced_layers": ["fst_..._v1"] }

5. Atlas page calls registry.resolve(...) on the new layer_id — Flow A
   from here.
```

### Flow C — Atlas imports a messy Excel table as a staging layer

```
1. User clicks "import manual-curation table".

2. Atlas POSTs:
     POST /api/actions
     {
       "action_id":    "act_1715000099000_z8q",
       "type":         "import_excel",
       "dataset_id":   "main_226_hatchery",
       "runner":       "import_excel",
       "target":       { "file": "manual_curation/candidates_2026_05.xlsx" },
       "params":       { "sheet": "candidates", "header_row": 0 },
       "expected_outputs": [
         { "layer_type": "excel_table",
           "schema_version": "staging_excel_table_v0",
           "stage": "staging" }
       ]
     }

3. Dispatcher routes to runners.import.import_excel_table, which reads
   the .xlsx, returns { excel_rows: [...] } as raw output.

4. Extractor extract_excel_staging_v0 wraps the rows in a staging
   envelope:
     {
       "layer_id":       "staging_excel_table_main_226_hatchery_v1",
       "layer_type":     "excel_table",
       "schema_version": "staging_excel_table_v0",
       "stage":          "staging",
       "dataset_id":     "main_226_hatchery",
       "source_files":   ["manual_curation/candidates_2026_05.xlsx"],
       "provenance":     { "action_id": "act_1715000099000_z8q",
                           "runner": "import_excel" },
       "status":         "review",
       "created_at":     "2026-05-12T16:02:10Z",
       "payload": {
         "rows": [ /* whatever the Excel produced */ ]
       }
     }

5. The Atlas can show this staging layer on review pages. Later, a
   converter action (type='normalize_layer', source_layer_ids=[...])
   transforms it into one or more normalized candidate_regions_v1
   layers, with provenance.source_layer_ids back-pointing here.
```

---

## Action log — what gets recorded

Every state-changing POST appends to `registry/actions.log.jsonl`:

```jsonl
{"action_id":"act_1715000000000_a4b","manifest":{...},"submitted_at":"2026-05-12T14:30:00Z","started_at":null,"finished_at":null,"status":"queued","produced_layers":[]}
{"action_id":"act_1715000000000_a4b","manifest":{...},"submitted_at":"2026-05-12T14:30:00Z","started_at":"2026-05-12T14:30:01Z","finished_at":null,"status":"running","produced_layers":[]}
{"action_id":"act_1715000000000_a4b","manifest":{...},"submitted_at":"2026-05-12T14:30:00Z","started_at":"2026-05-12T14:30:01Z","finished_at":"2026-05-12T14:35:22Z","status":"success","produced_layers":["fst_windows_main_226_hatchery_LG28_INV_001_v1"],"duration_ms":321000}
```

`GET /api/actions/{action_id}` returns the latest entry. Readers should
keep the latest entry per action_id (last write wins).

**GET endpoints do NOT write to the log.** Only state-changing POSTs.
The log is the durable record of "what was asked, what happened,
which layers came out". Reproducibility lives here.

---

## Writing an extractor

The extractor parser is a Python function with this signature:

```python
def parse(input_files: dict[str, str], params: dict) -> dict:
    """
    Convert raw outputs into a layer payload.

    input_files:  { 'fst_table': '/path/to/popstats.tsv', ... }
                  paths to whatever the runner produced.
    params:       dict from extractor_manifest.params (chrom_col, etc.).

    returns:      payload dict that validates against
                  schema_out/<schema_version>.schema.json
                  for normalized stage; loose dict for staging.
    """
```

Example for FST windows (TSV → payload):

```python
import pandas as pd

def extract(input_files, params):
    df = pd.read_csv(input_files["fst_table"], sep="\t")
    windows = [
        {
            "start_bp": int(r[params.get("start_col", "start_bp")]),
            "end_bp":   int(r[params.get("end_col",   "end_bp")]),
            "fst":      float(r[params.get("value_col", "fst")]),
            "n_sites":  int(r.get(params.get("n_sites_col", "n_sites"), 0)),
        }
        for _, r in df.iterrows()
    ]
    return {
        "windows": windows,
        "summary": {
            "n_windows": len(windows),
            "mean_fst":  float(df[params.get("value_col", "fst")].mean()),
            "max_fst":   float(df[params.get("value_col", "fst")].max()),
        },
    }
```

The dispatcher validates the return value against
`schema_out/fst_windows_v1.schema.json` before wrapping it in an
envelope.

---

## Writing a runner

The runner is a Python function with this signature:

```python
def run(manifest: dict, server_client) -> dict[str, str]:
    """
    Execute the action; return paths to raw output files.

    manifest:       the validated action_manifest dict.
    server_client:  a small helper exposing
                    server_client.post(path, json) → dict
                    server_client.get(path) → bytes
                    so the runner can call other endpoints
                    (e.g. /api/popstats/groupwise) without
                    knowing the base URL.

    returns:        { 'name': '/path/to/raw_output_file', ... }
                    keys match extractor.input_files.
    """
```

Example for `run_popstats` (calls the existing popstats endpoint):

```python
def run(manifest, server_client):
    res = server_client.post("/api/popstats/groupwise", {
        "chrom":   manifest["target"]["chrom"],
        "region":  { "start_bp": manifest["target"]["start_bp"],
                     "end_bp":   manifest["target"]["end_bp"] },
        "groups":  manifest["target"]["groups"],
        "metrics": [manifest["params"]["stat"]],
        "win_bp":  manifest["params"]["win_bp"],
        "step_bp": manifest["params"]["step_bp"],
    })
    workdir = pathlib.Path("cache") / manifest["action_id"]
    workdir.mkdir(parents=True, exist_ok=True)
    out = workdir / "popstats.tsv"
    out.write_text(res["tsv"])           # popstats endpoint returns parsed
                                          # data + the raw tsv string
    return { "fst_table": str(out) }
```

The runner doesn't know about envelopes, doesn't know about extractors,
doesn't write to the registry. Single responsibility: produce raw
output files from an action manifest.

---

## Reversibility — staging today, normalized tomorrow

If the final normalized schema for a layer type isn't settled yet:

1. Ship a `staging_<type>_v0.schema.json` in `schema_out/` that allows
   roughly anything (`additionalProperties: true`, minimal required
   fields).
2. The action manifest declares `stage: "staging"` in its
   expected_outputs. The dispatcher writes a staging envelope.
3. The atlas's review/debug pages can show staging layers.
4. When the normalized schema settles: write `<type>_v1.schema.json`
   in `schema_out/`. Ship a converter (a runner of
   `type: "normalize_layer"`) that reads
   `source_layer_ids = [staging_id]`, transforms the payload, and
   writes a `stage: "normalized"` layer with
   `provenance.source_layer_ids = [staging_id]`.
5. Mark the staging layer's status `superseded`. Keep it on disk for
   provenance.

No data is lost. The Atlas progressively switches from showing the
staging layer to showing the normalized one as schemas firm up.

---

## What atlas-core promises vs what each atlas promises

**atlas-core (this repo) promises:**
- The four envelope/manifest schemas under `toolkit_registries/schemas/registry_schemas/`.
- The four new endpoints on `atlas_server.py` (`POST /api/actions`, `GET /api/actions/{id}`, `GET /api/layers`, `GET /api/layers/{id}`).
- The existing primitives (`/file/`, `/compute/`, `/api/popstats/...`, `/api/ancestry/...`, etc.) keep working unchanged.
- A reference `dispatcher.py` skeleton (~80 lines) that atlases can copy.

**Each atlas promises:**
- `schemas/schema_in/<action_type>_v1.schema.json` — one per action it accepts.
- `schemas/schema_out/<layer_type>_v<N>.schema.json` — one per layer type it produces. Staging variants start `staging_*_v0`.
- `data/actions.registry.json` and `data/extractors.registry.json`.
- `dispatcher.py` — copy of the skeleton, plus any atlas-specific helpers.
- Python runner modules and extractor modules.

No atlas owns the envelope shape. No atlas owns the action log shape.
Those are universal across atlases.

---

## What this does NOT do (intentionally)

- **Does not invent new compute endpoints.** popstats/HOBS/ancestry
  stay where they are. Actions wrap them.
- **Does not require a queue / background worker.** Actions run
  synchronously inside the request for now; the action log already
  has `queued/running/success/error` so a worker can be added later
  without breaking the contract.
- **Does not unify the cache.** Server compute cache
  (`${cache_dir}/popstats|hobs|ancestry/<hash>.json`) and the layer
  registry (`layers/`) stay separate. The compute cache is by
  content hash; the layer registry is by layer_id. Both are useful.
- **Does not freeze normalized schemas.** Staging is the relief
  valve — anything uncertain can land as `_v0` and be promoted later.
