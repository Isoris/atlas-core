# SPEC — atlas adapter cookbook (IN/OUT envelope pairs)

**Audience**: anyone adding a new producer→atlas pipeline (i.e. "I have a
TSV from an analysis script; I want a typed envelope my atlas pages can
query via `GET /api/layers`").

**Status**: meta-pattern doc. Generalises the 12-file IN/OUT scaffold
shipped twice — relatedness-atlas
([commit 23 in STATUS.md](../toolkit_registries/STATUS.md)) and
meiosis-atlas ([SPEC_tract_classifications_adapter.md](../../meiosis-atlas/specs_done/SPEC_tract_classifications_adapter.md)).

The two existing implementations are the reference. Copy + edit. This doc
explains what to keep verbatim vs. what to customise.

---

## 1. When to use this pattern

You have:

1. A TSV (or other tabular file) produced by an analysis script outside
   the atlas (ngsRelate, ngsTracts, ngsPedigree, BRAKER, …).
2. An atlas page that wants to render that data through the action
   pipeline rather than via static `fetch('atlases/<id>/data/foo.tsv')`.

You want:

- A layer envelope (`{layer_id, layer_type, schema_version, payload}`) so
  pages call `resolveLatestLayer('<type>')` instead of hardcoding paths.
- Type coercion + summary statistics computed once at import time, not
  per-page.
- Schema validation that catches malformed producer output at import,
  not at render.
- Lineage tracking: the typed envelope's
  `provenance.source_layer_ids` points back at the staging envelope it
  was derived from.

If you DON'T want all of that (e.g. quick one-off data exploration),
just `fetch()` the file. The adapter scaffold is overkill below ~3 page
consumers.

## 2. Two-action flow

Every adapter ships **two** actions, not one:

```
producer file (TSV)
    │
    ▼ POST /api/actions {type: "import_<thing>"}
    │     runner: copy TSV to raw_results/
    │     extractor: parse TSV → {columns, rows} (loose)
    │
    ▼ staging_<thing>_v0 envelope (additionalProperties: true)
    │     — survives producer column-set drift; renderers can see
    │       raw rows even before a v1 schema exists
    │
    ▼ POST /api/actions {type: "normalize_<thing>",
    │                    target.source_layer_id: <staging id>}
    │     runner: load source envelope from layers index
    │     extractor: map columns, coerce types, compute summary
    │
    ▼ <thing>_v1 envelope (strict additionalProperties: false on rows)
       provenance.source_layer_ids = [<staging id>]  (lineage)
```

Why two actions:

- **Reversibility** — when the producer's columns drift, the staging
  payload still captures the data losslessly. You can write a
  `normalize_<thing>_v2` action later without re-importing.
- **Validation gate** — staging is `additionalProperties: true` (loose),
  normalized is strict. Producer changes that BREAK the contract fail
  at normalize, not at import. The raw data survives.
- **Independent reruns** — a normalize action consumes only its source
  envelope; you can iterate the normalizer (column-map fixes, summary
  field additions) without re-touching the TSV.

This is the **canonical staging→normalized example** from
[`PIPELINE_FLOW.md` §Reversibility](../toolkit_registries/PIPELINE_FLOW.md).

## 3. The 12-file canonical list

```
atlases/<id>/registries/
├── dispatcher.py                                      [VERBATIM]
├── data/
│   ├── actions.registry.json                          [TEMPLATE]
│   └── extractors.registry.json                       [TEMPLATE]
├── runners/
│   ├── __init__.py                                    [EMPTY]
│   ├── import_tsv.py                                  [TEMPLATE]
│   └── normalize_<thing>.py                           [TEMPLATE]
├── extractors/
│   ├── __init__.py                                    [EMPTY]
│   ├── <thing>_tsv.py                                 [TEMPLATE]
│   └── normalize_<thing>.py                           [HAND-WRITTEN]
└── schemas/
    ├── schema_in/
    │   ├── import_<thing>_v1.schema.json              [TEMPLATE]
    │   └── normalize_<thing>_v1.schema.json           [TEMPLATE]
    └── schema_out/
        ├── staging_<thing>_v0.schema.json             [TEMPLATE]
        └── <thing>_v1.schema.json                     [HAND-WRITTEN — strict]

PLUS:
test_adapter_smoke.py                                  [TEMPLATE]
```

**Marker legend:**
- **VERBATIM** — copy byte-for-byte from a sibling atlas. The dispatcher
  is atlas-agnostic.
- **EMPTY** — zero-byte file. Just makes the folder a Python package.
- **TEMPLATE** — copy from a sibling, change ~5 lines (atlas name, raw_results path, type names).
- **HAND-WRITTEN** — the only files that actually require thought. Type coercion + summary block in the normalizer; column list + enums in the v1 schema.

So the cost of a new adapter is approximately:
- 2 files of real design work (normalize extractor + v1 schema)
- 10 files of template-fill
- 1 smoke test

## 4. Step-by-step recipe

Pick a `<thing>` name (lowercase, underscore-separated, biological — e.g.
`tract_classifications`, `relatedness`, `pedigree_dyads`). Then:

### 4.1 Create the directory layout

```bash
mkdir -p atlases/<id>/registries/{data,runners,extractors,schemas/schema_in,schemas/schema_out}
touch atlases/<id>/registries/runners/__init__.py
touch atlases/<id>/registries/extractors/__init__.py
```

### 4.2 Copy the dispatcher VERBATIM

```bash
cp atlases/relatedness/registries/dispatcher.py \
   atlases/<id>/registries/dispatcher.py
# Only edit: the module docstring's atlas name reference. The actual
# code touches no atlas-specific path.
```

### 4.3 Write the v1 schema (HAND-WRITTEN)

This is the contract. Be strict — list every column with type, enum
constraints, `required`. Reference the producer's own schema doc if it
has one (ngsTracts has `docs/METHODOLOGY.md §5.1`).

Template: `schemas/schema_out/<thing>_v1.schema.json` with:

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "$id": "<thing>_v1.schema.json",
  "title": "<thing>_v1 — typed <description>",
  "type": "object",
  "required": ["<rows_key>", "summary"],
  "properties": {
    "<rows_key>": {
      "type": "array",
      "items": {
        "type": "object",
        "required": [/* every column the consumer relies on */],
        "additionalProperties": true,
        "properties": {
          "<col>": { "type": "...", "enum"|"minimum"|"pattern": "..." },
          ...
        }
      }
    },
    "summary": {
      "type": "object",
      "required": ["n_<rows>"],
      "properties": { ... }
    }
  }
}
```

Reference: [`meiosis-atlas/.../tract_classifications_v1.schema.json`](../../meiosis-atlas/atlases/meiosis/registries/schemas/schema_out/tract_classifications_v1.schema.json) (22 columns, 7-value class enum, `DEP_NNNNNN` regex pattern).

### 4.4 Write the staging v0 schema (TEMPLATE)

Loose; mirrors `staging_relatedness_v0`. Copy and rename:

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "$id": "staging_<thing>_v0.schema.json",
  "title": "staging_<thing>_v0 — loose capture of one <producer> file",
  "type": "object",
  "required": ["columns", "rows"],
  "additionalProperties": true,
  "properties": {
    "columns": { "type": "array", "items": { "type": "string" } },
    "rows":    { "type": "array", "items": { "type": "object", "additionalProperties": true } },
    "source":  { "type": "string" },
    "n_rows":  { "type": "integer", "minimum": 0 }
  }
}
```

### 4.5 Write the two schema_in manifest contracts (TEMPLATE)

Copy `import_relatedness_tsv_v1.schema.json` and
`normalize_relatedness_v1.schema.json`; rename and adjust `target.analysis`
enum if relevant.

### 4.6 Write the runners (TEMPLATE)

Two files. Both copy from relatedness with the `raw_results/<atlas>/`
prefix swapped:

- `runners/import_tsv.py` — copies producer TSV into `raw_results/<atlas>/<action_id>/` for provenance, returns `{tsv_path, source_rel, ...}`.
- `runners/normalize_<thing>.py` — resolves source envelope via `<workspace>/registry/layers.registry.json`, copies it into `raw_results/<atlas>_normalized/<action_id>/`, returns `{source_envelope, source_layer_id}`.

### 4.7 Write the staging extractor (TEMPLATE)

`extractors/<thing>_tsv.py` — auto-detect tab vs whitespace delimiter,
parse `{columns, rows[]}`. Identical pattern across atlases except for
the metadata fields it passes through. Mirror
[`extractors/relatedness_tsv.py`](../../relatedness-atlas/atlases/relatedness/registries/extractors/relatedness_tsv.py)
or [`extractors/tract_classifications_tsv.py`](../../meiosis-atlas/atlases/meiosis/registries/extractors/tract_classifications_tsv.py).

### 4.8 Write the normalize extractor (HAND-WRITTEN)

This is the second of the two design-heavy files. It does three things:

1. **Map columns** — `_DEFAULT_COLUMN_MAP` dict from producer name → canonical name (or identity map if the producer already uses canonical names).
2. **Coerce types** — per-column tables: `_INTEGER_COLS`, `_FLOAT_COLS`, `_STRING_COLS`, `_BOOL_COLS`. Handle null sentinels (`""`, `"NA"`, `"NaN"`, plus producer-specific ones like ngsTracts's `"-"` for `distance_to_nearest_inv_bp`).
3. **Compute summary** — at minimum `n_<rows>`; also any counts/aggregates the consuming page will want as headline numbers.

Reference: [meiosis's normalize_tract_classifications.py](../../meiosis-atlas/atlases/meiosis/registries/extractors/normalize_tract_classifications.py) handles:
- 22-col canonical list as a Python tuple
- 4 type-table sets (`_INTEGER_COLS`, `_FLOAT_COLS`, `_STRING_COLS`, `_BOOL_COLS`)
- Null-tolerant coercion (returns `None` on parse failure rather than raising)
- Special `'-'` sentinel for one specific int column (`distance_to_nearest_inv_bp`)
- Summary: `n_tracts`, `n_dyads`, `n_chroms`, per-class counts, `n_inside_inversion`

### 4.9 Write the two registry files (TEMPLATE)

`data/actions.registry.json`:

```json
{
  "actions": {
    "import_<thing>": {
      "runner":      "runners.import_tsv.import_tsv",
      "schema_in":   "import_<thing>_v1",
      "description": "..."
    },
    "normalize_<thing>": {
      "runner":      "runners.normalize_<thing>.normalize",
      "schema_in":   "normalize_<thing>_v1",
      "description": "..."
    }
  }
}
```

`data/extractors.registry.json`:

```json
{
  "extractors": [
    { "extractor_id": "extract_staging_<thing>_v0",
      "layer_type":   "<thing>",
      "schema_version": "staging_<thing>_v0",
      "stage":          "staging",
      "parser":         "extractors.<thing>_tsv.extract",
      "input_format":   "tsv" },
    { "extractor_id": "extract_<thing>_v1",
      "layer_type":   "<thing>",
      "schema_version": "<thing>_v1",
      "stage":          "normalized",
      "parser":         "extractors.normalize_<thing>.extract",
      "input_format":   "json" }
  ]
}
```

Note: `layer_type` is the SAME string for both stages — only `schema_version` differs.

### 4.10 Write the smoke test (TEMPLATE)

`test_adapter_smoke.py` at `atlases/<id>/registries/`. Drives the extractors directly (skip the dispatcher / server for the smoke). Pattern:

1. Synthesize a small TSV in `tempfile`.
2. Call `extractors.<thing>_tsv.extract({tsv_path, ...}, {})` — verify staging shape.
3. Wrap the staging payload in a `{layer_id, payload}` envelope, write to `tempfile`.
4. Call `extractors.normalize_<thing>.extract({source_envelope, ...}, {})` — verify normalized shape (`n_rows`, summary fields, type coercion spot-checks).
5. If `jsonschema` is installed: validate the normalized payload against the v1 schema.

Reference: [meiosis `test_adapter_smoke.py`](../../meiosis-atlas/atlases/meiosis/registries/test_adapter_smoke.py) — 6 assertions, ~120 lines.

### 4.11 Wire into the umbrella

Append to [`atlas-core/scripts/_run_all_tests.sh`](../scripts/_run_all_tests.sh):

```bash
echo '--- <atlas>-atlas adapter (staging + normalize) ---'
( cd /mnt/c/Users/quent/Desktop/<atlas>-atlas/atlases/<id>/registries && python3 test_adapter_smoke.py 2>&1 | tail -2 )
cd /mnt/c/Users/quent/Desktop/atlas-core
```

### 4.12 Document

Write a SPEC at `atlases/<id>/specs_done/SPEC_<thing>_adapter.md` with:
- Status line + Implemented in: links
- Goal (one paragraph)
- Two-action flow diagram (copy §2 above)
- Canonical column list with constraints
- Type coercion table
- Summary block shape
- Manifest examples (both `import_*` and `normalize_*`)

## 5. Diff table — what changes per atlas

| file                          | atlas-specific lines | per-thing-specific lines |
|-------------------------------|---------------------:|-------------------------:|
| `dispatcher.py`               | 1 (docstring)        | 0                        |
| `runners/__init__.py`         | 0                    | 0                        |
| `runners/import_tsv.py`       | 1 (raw_results path) | 0                        |
| `runners/normalize_<thing>.py`| 1 (raw_results path) | ~3 (workdir name)        |
| `extractors/__init__.py`      | 0                    | 0                        |
| `extractors/<thing>_tsv.py`   | 0                    | ~5 (pass-through fields) |
| `extractors/normalize_<thing>.py` | 0                | **HEAVY** — column map + type tables + summary |
| `schemas/schema_in/import_<thing>_v1.schema.json`    | 0 | ~3 (title, desc, target.path desc) |
| `schemas/schema_in/normalize_<thing>_v1.schema.json` | 0 | ~3 (title, desc, column_map desc) |
| `schemas/schema_out/staging_<thing>_v0.schema.json`  | 0 | ~3 (title, desc) |
| `schemas/schema_out/<thing>_v1.schema.json`          | 0 | **HEAVY** — full column spec, enums, patterns |
| `data/actions.registry.json`        | 0 | ~6 (action names, descriptions) |
| `data/extractors.registry.json`     | 0 | ~4 (extractor ids, layer_type, schema_versions) |
| `test_adapter_smoke.py`             | 0 | ~30 (synthetic fixture + assertions) |

**Total novel code per adapter**: ~50 lines (template fills) + ~100 lines hand-written (normalize extractor + v1 schema + smoke test fixture) = ~150 lines.

The dispatcher's 215 lines, all the registry plumbing, and the half-dozen
template files are reused verbatim.

## 6. Wiring into a page consumer

Once the adapter is shipped, a page consumes the typed envelope:

```js
import { resolveLatestLayer } from '../../shared/api_client.js';

export async function mount(root) {
  let envelope = null, error = null;
  try {
    envelope = await resolveLatestLayer('<thing>', { stage: 'normalized' });
  } catch (e) {
    error = (e && e.message) || String(e);
  }
  // Render status badge in 3 states (ok / empty / warn); render views
  // against envelope.payload.<rows_key>.
}
```

The page's smoke test mocks `globalThis.fetch` with a route table — the
same pattern as relatedness/network and meiosis/nco. See
[atlases/meiosis/pages/hub/test_nco_envelope.js](../../meiosis-atlas/atlases/meiosis/pages/hub/test_nco_envelope.js) for the
canonical example.

## 7. Existing adapters to copy from

| atlas | thing | files |
|-------|-------|-------|
| relatedness | `relatedness` (ngsRelate/ngsPedigree/mendelian TSVs) | [atlases/relatedness/registries/](../../relatedness-atlas/atlases/relatedness/registries/) |
| meiosis     | `tract_classifications` (ngsTracts STEP_TRC_01)       | [atlases/meiosis/registries/](../../meiosis-atlas/atlases/meiosis/registries/) |

Pick whichever producer-shape is closer to yours. The meiosis adapter is
more rigorous (strict v1 schema; relatedness's v1 is loose because
ngsRelate/ngsPedigree/mendelian have different per-tool columns the
relatedness page handles via a column_map).

## 8. Open questions / known limitations

- **No CSV / Parquet / non-tabular support yet.** Today the staging
  extractor assumes tab-separated text. A future variant would accept
  CSV (already handled via auto-detect: switches to whitespace) or
  Parquet/Arrow (would need a new staging extractor + the v1 schema's
  rows[] convention still works).
- **No partial-import / chunking.** Producer files >100 MB will swallow
  RAM in the runner's `shutil.copyfile` (fine) but the extractor will
  load every row into Python (less fine). When this matters, switch the
  extractor to stream + chunk.
- **No producer-side schema versioning.** The pattern assumes
  `<producer> v0.1 → adapter v1`. If the producer publishes
  `<producer> v0.2`, the adapter ALSO bumps to `v2` even if columns are
  unchanged. The lineage chain via `provenance.source_layer_ids`
  preserves which producer version produced which envelope; but the
  schema_version string itself doesn't encode producer-side version.
  Documented in [`SCHEMA_COMPATIBILITY.md`-style files inside each producer repo
  (ngsTracts has one)](../../ngsTracts/docs/SCHEMA_COMPATIBILITY.md).
- **Only the staging → normalized path is exercised.** A future bidirectional adapter (atlas → file) would need a `serialize_<thing>` action that writes a v1 envelope back to a TSV. No demand for that today.

## 9. Quick reference — file checklist

When adding a new adapter, you ship these 13 things (12 files + 1 SPEC):

- [ ] `registries/dispatcher.py` (VERBATIM)
- [ ] `registries/runners/__init__.py` (empty)
- [ ] `registries/runners/import_tsv.py`
- [ ] `registries/runners/normalize_<thing>.py`
- [ ] `registries/extractors/__init__.py` (empty)
- [ ] `registries/extractors/<thing>_tsv.py`
- [ ] `registries/extractors/normalize_<thing>.py` (hand-written)
- [ ] `registries/schemas/schema_in/import_<thing>_v1.schema.json`
- [ ] `registries/schemas/schema_in/normalize_<thing>_v1.schema.json`
- [ ] `registries/schemas/schema_out/staging_<thing>_v0.schema.json`
- [ ] `registries/schemas/schema_out/<thing>_v1.schema.json` (hand-written)
- [ ] `registries/data/actions.registry.json`
- [ ] `registries/data/extractors.registry.json`
- [ ] `registries/test_adapter_smoke.py`
- [ ] Append entry to `atlas-core/scripts/_run_all_tests.sh`
- [ ] `specs_done/SPEC_<thing>_adapter.md` in the atlas

Tick all 16 boxes and you have a shipped adapter.
