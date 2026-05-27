# SPEC — tract_classifications IN/OUT JSON adapters

**Status**: shipped 2026-05-20. Contract-only (no real data yet — see §7 Open
work below). End-to-end smoke green; jsonschema validation against the
strict v1 schema passes on a 3-row synthetic fixture.

**Implemented in:**
- [`atlases/meiosis/registries/dispatcher.py`](../atlases/meiosis/registries/dispatcher.py) (atlas-agnostic; mirrors relatedness)
- [`atlases/meiosis/registries/runners/import_tsv.py`](../atlases/meiosis/registries/runners/import_tsv.py)
- [`atlases/meiosis/registries/runners/normalize_tract_classifications.py`](../atlases/meiosis/registries/runners/normalize_tract_classifications.py)
- [`atlases/meiosis/registries/extractors/tract_classifications_tsv.py`](../atlases/meiosis/registries/extractors/tract_classifications_tsv.py)
- [`atlases/meiosis/registries/extractors/normalize_tract_classifications.py`](../atlases/meiosis/registries/extractors/normalize_tract_classifications.py)
- 4 schemas under `atlases/meiosis/registries/schemas/{schema_in,schema_out}/`
- 2 registry tables: `data/actions.registry.json`, `data/extractors.registry.json`
- Smoke test: [`atlases/meiosis/registries/test_adapter_smoke.py`](../atlases/meiosis/registries/test_adapter_smoke.py)

Wired into umbrella at [`atlas-core/scripts/_run_all_tests.sh`](../../atlas-core/scripts/_run_all_tests.sh) — runs as "meiosis-atlas adapter (staging + normalize)".

---

## 1. Goal

Bridge ngsTracts STEP_TRC_01 output (`tract_classifications.tsv`) into the
atlas action-pipeline envelope contract, so any meiosis-atlas page can
read a typed `tract_classifications_v1` envelope via `GET /api/layers/{id}`.

Mirrors the relatedness-atlas's `import_relatedness_tsv` + `normalize_relatedness`
pair (the canonical staging→normalized example from
`atlas-core/toolkit_registries/PIPELINE_FLOW.md`).

## 2. Two-action flow

```
ngsTracts/out/tract_classifications.tsv
    │
    ▼ POST /api/actions { type: "import_tract_classifications", ... }
    │   → runners.import_tsv.import_tsv
    │   → extractors.tract_classifications_tsv.extract
    │   → staging_tract_classifications_v0 envelope (loose: {columns, rows})
    │
    ▼ POST /api/actions { type: "normalize_tract_classifications",
    │                     target.source_layer_id: <staging envelope id> }
    │   → runners.normalize_tract_classifications.normalize
    │   → extractors.normalize_tract_classifications.extract
    │   → tract_classifications_v1 envelope (typed: {tracts[], summary})
    │
    ▼ envelope.provenance.source_layer_ids = [<staging envelope id>]
       (lineage preserved per PIPELINE_FLOW.md §Reversibility)
```

Layer type: `tract_classifications` (single name, two schema_versions).
Backs registered meiosis_atlas product `gene_conversion_tracts.v1`.

## 3. Canonical columns (tract_classifications_v1)

Per [`ngsTracts/docs/METHODOLOGY.md` §5.1](../../ngsTracts/docs/METHODOLOGY.md), 22
columns total:

**Always present (19 cols):**
```
interval_id, parent_id, offspring_id, chrom, start, end, span_bp,
class, confidence,
flanking_left_state, flanking_right_state, departure_state,
n_sites, n_discordant, inside_inversion, distance_to_nearest_inv_bp,
prior_log_ratio_co_nco, manual_review_flag, notes
```

**STEP_TRC_02 only (3 cols):**
```
refined_breakpoint_bp, refined_ci_left, refined_ci_right
```

Strict schema constraints:
- `interval_id` matches `^DEP_[0-9]{6,}$` (per ngsPedigree Stage 3 contract)
- `class` ∈ `{NCO, CO, DCO, MOSAIC_SHORT, MOSAIC_LONG, AMBIG, LOW_CONFIDENCE}`
- `confidence` ∈ `{high, medium, low}`
- `flanking_*_state` ∈ `{hapA, hapB, boundary}`
- `departure_state` ∈ `{hapA, hapB, neither}`
- `inside_inversion` ∈ `{yes, partial, no}`
- `n_sites >= 3` (Stage 3 filters lower)
- `start >= 1`, `end >= 1`, `span_bp >= 1` (1-based inclusive)

## 4. Type coercion rules

In [`extractors/normalize_tract_classifications.py`](../atlases/meiosis/registries/extractors/normalize_tract_classifications.py):

| canonical column        | type   | null sentinels                          |
|-------------------------|--------|-----------------------------------------|
| start, end, span_bp, n_sites, n_discordant | int    | `''`, `NA`, `NaN`, `null`, `None`       |
| distance_to_nearest_inv_bp                  | int    | adds `'-'` (per SCHEMA.md when no atlas) |
| refined_breakpoint_bp, refined_ci_left/right| int    | empty string when STEP_TRC_01-only       |
| prior_log_ratio_co_nco                       | float  | as above + `'NaN'`                       |
| manual_review_flag                           | bool   | accepts `0/1`, `true/false`, `yes/no`    |
| interval_id, parent_id, offspring_id, chrom, class, confidence, flanking_*, departure_state, inside_inversion, notes | string | as above (but **not** `'-'` — that's a legitimate "no notes" marker) |

Coercion is null-tolerant: any unparseable value becomes `None` rather than
raising — production data is messy, refuse-to-classify is preferable to
refuse-to-load.

## 5. Summary block

`tract_classifications_v1.summary` always includes:
- `n_tracts` — total row count
- `n_dyads` — distinct `(parent_id, offspring_id)` pairs
- `n_chroms` — distinct `chrom` values
- `class_counts` — per-class tract count, all 7 enum values present (zero when missing)
- `n_inside_inversion` — tracts with `inside_inversion == 'yes'`

Drives the [`nco` page](../atlases/meiosis/pages/hub/nco.html) headline counters
and the inside-vs-outside-inversion enrichment view per §3.2 of ngsTracts
METHODOLOGY.

## 6. Why mirror relatedness verbatim

The dispatcher logic is atlas-agnostic; copying relatedness's
[`dispatcher.py`](../../relatedness-atlas/atlases/relatedness/registries/dispatcher.py)
keeps the action-pipeline contract uniform across atlases. The runners
diverge only on the `raw_results/<atlas>/` directory prefix. The extractors
diverge on the column map (relatedness: a/b/theta/KING/R; meiosis: 22-col
ngsTracts shape).

Following this pattern means each new atlas adapter is a deterministic
7-file scaffold + 2-file customisation (extractors). The cost of adding
the next adapter pair (e.g. `import_chromosome_meiosis_events` once the
builder lands) is ~1 hour of typing.

## 7. Open work

- **No real data**: ngsTracts STEP_TRC_01 hasn't run on the 226-sample
  hatchery cohort yet. The adapter is validated against a 3-row synthetic
  fixture in [`test_adapter_smoke.py`](../atlases/meiosis/registries/test_adapter_smoke.py).
  When real data arrives, expect schema-validation failures on edge cases
  the fixture doesn't cover (very long tracts, unusual flank states, etc.) —
  the strict v1 schema will surface them clearly.
- **No page consumer**: the [`nco` page](../atlases/meiosis/pages/hub/nco.html)
  declares a `Render` button that says "Stub — needs ngsTracts loader". When a
  `tract_classifications_v1` envelope exists, that button should call
  `resolveLatestLayer('tract_classifications', { stage: 'normalized' })` and
  render the per-class tract count table. See `SPEC_meiosis_atlas_pages.md` for
  the page contract.
- **STEP_TRC_02 path not separately tested**: the smoke fixture exercises
  refined_* cols populated AND empty. A real STEP_TRC_02 run hasn't validated.
  Same envelope shape — no second action needed.

## 8. Manifest example

```json
{
  "action_id":  "act_import_2026_05_20_abc",
  "type":       "import_tract_classifications",
  "dataset_id": "226_WGS_hatchery",
  "target": {
    "path": "raw_results/ngsTracts/out/tract_classifications.tsv",
    "step": "STEP_TRC_01",
    "scope": "cohort:226_WGS_hatchery"
  },
  "expected_outputs": [
    { "layer_type": "tract_classifications",
      "schema_version": "staging_tract_classifications_v0",
      "stage": "staging" }
  ]
}
```

Then promote:
```json
{
  "action_id":  "act_normalize_2026_05_20_def",
  "type":       "normalize_tract_classifications",
  "dataset_id": "226_WGS_hatchery",
  "target": {
    "source_layer_id": "tract_classifications_226_WGS_hatchery_abc"
  },
  "expected_outputs": [
    { "layer_type": "tract_classifications",
      "schema_version": "tract_classifications_v1",
      "stage": "normalized" }
  ]
}
```

## 9. Decision rationale

- **Why mirror the relatedness adapter verbatim**: the dispatcher logic is atlas-agnostic; copying the dispatcher + runner shape keeps the action-pipeline contract uniform across atlases. The cost of "this is the second time" is ~150 LOC of customization (mostly the v1 schema + the normalize extractor); the cost of "drift" if every adapter invented its own dispatcher would be much higher. The cookbook (atlas-core/docs/SPEC_atlas_adapter_cookbook.md) was distilled from this precedent.
- **Why `'-'` is a `distance_to_nearest_inv_bp`-specific null sentinel** (not a global one): ngsTracts' SCHEMA.md §distance_to_nearest_inv_bp explicitly defines `'-'` as "no inversion atlas supplied for this chrom". Other producers may use `'-'` to mean a real string literal (e.g. an actual character in a `notes` field). The adapter respects this — `'-'` coerces to null ONLY for `distance_to_nearest_inv_bp` and for string columns where it would otherwise be ambiguous; for the literal-`notes` case, the `'-'` survives as the string value.
- **Why strict `additionalProperties: false` on tracts[]**: producer-side bugs (a typo'd column header that lands as an unknown field on every row) should fail validation, not silently propagate. Strict-schema-on-typed means the v1 envelope is contractually clean; the producer is forced to ship known fields.
- **Why the staging schema is loose (`additionalProperties: true`)**: the staging path captures whatever the producer ships, even when the column set drifts. This is the "reversibility" guarantee — when the producer changes columns and the strict v1 normalize fails, the staging envelope still has the data and a new `normalize_*_v2` can be written without re-importing.
- **Why classification enum is enforced at schema (not just at coerce time)**: the `class` field is the central pivot — every consumer page filters / groups by it. An unrecognised enum value (e.g. `'CO_v2'` from a producer using a newer ngsTracts) should fail loudly at normalize so the user sees the version mismatch, not silently render an empty `NCO` count.

## 10. Worked example

Suppose ngsTracts STEP_TRC_01 emits this 3-row tract_classifications.tsv on the 226-sample cohort:

| interval_id | parent_id | offspring_id | chrom | start | end | span_bp | class | confidence | flanking_left_state | flanking_right_state | departure_state | n_sites | n_discordant | inside_inversion | distance_to_nearest_inv_bp | prior_log_ratio_co_nco | refined_breakpoint_bp | refined_ci_left | refined_ci_right | manual_review_flag | notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| DEP_000001 | P_HET_3 | O_3_1 | LG07 | 100   | 5000    | 4901    | NCO | high | hapA | hapA | hapB | 42 | 7  | no  | 125000 | 0.4  |         |         |         | 0 | - |
| DEP_000002 | P_HET_3 | O_3_2 | LG07 | 2e6   | 3e6     | 1000001 | CO  | high | hapA | hapB | hapB | 58 | 30 | no  | -      | 2.1  | 2500000 | 2499800 | 2500200 | 0 | refined |
| DEP_000003 | P_HET_5 | O_5_1 | LG28 | 1000  | 50000   | 49001   | DCO | medium | hapA | hapA | hapB | 40 | 22 | yes | 0      | -1.8 |         |         |         | 1 | - |

After `import_tract_classifications` + `normalize_tract_classifications`:

- 3 rows survive (no required-column drop)
- Row 1: `distance_to_nearest_inv_bp = 125000` (int), `refined_*` all null, `notes = "-"` preserved
- Row 2: `distance_to_nearest_inv_bp = null` (the `'-'` sentinel), `refined_breakpoint_bp = 2500000`
- Row 3: `inside_inversion = "yes"`, `manual_review_flag = true` (the `"1"` string → bool)

Summary:

```
n_tracts            = 3
n_dyads             = 2  (P_HET_3 has 2 offspring rows; P_HET_5 has 1)
n_chroms            = 2  (LG07, LG28)
n_inside_inversion  = 1
class_counts        = { NCO: 1, CO: 1, DCO: 1, MOSAIC_SHORT: 0, MOSAIC_LONG: 0, AMBIG: 0, LOW_CONFIDENCE: 0 }
```

This drives the `nco` page status badge: "tract_classifications_226_WGS_hatchery_xyz · 3 tracts · 2 dyads · 2 chroms · inside_inv: 1 · NCO: 1 · MOSAIC_SHORT: 0 · MOSAIC_LONG: 0".

## 11. Failure modes

| # | condition | behaviour |
|---|---|---|
| 11.1 | Missing `interval_id` | row dropped silently (required) |
| 11.2 | Missing `parent_id` or `offspring_id` | row dropped silently (required) |
| 11.3 | Missing `chrom` | row dropped silently (required) |
| 11.4 | `class` not in {NCO, CO, DCO, MOSAIC_SHORT, MOSAIC_LONG, AMBIG, LOW_CONFIDENCE} | schema validation fails at normalize — the entire promote action errors out, surfacing the producer-version mismatch to the user. By design (per §9). |
| 11.5 | `confidence` not in {high, medium, low} | schema validation fails (same path as 11.4) |
| 11.6 | `n_sites < 3` | schema validation fails (`minimum: 3` constraint). ngsTracts STEP_TRC_01 filters these upstream, so this is a producer-bug catch-all. |
| 11.7 | `interval_id` doesn't match `^DEP_[0-9]{6,}$` | schema validation fails (pattern constraint). |
| 11.8 | `'-'` in `distance_to_nearest_inv_bp` | coerced to null per the SCHEMA.md sentinel convention (§9 above) |
| 11.9 | `'-'` in `notes` | preserved as the string `"-"` — distinguished from the int-column sentinel |
| 11.10 | `manual_review_flag = "1"` / `"true"` / `"yes"` | coerced to `true` (3 string forms accepted) |
| 11.11 | `manual_review_flag = "1.0"` (float-shaped string) | falls through to `_coerce_bool`, which doesn't accept float strings → null. Producer should ship `"1"` not `"1.0"`. |
| 11.12 | STEP_TRC_02 columns (`refined_*`) present but null | all 3 refined fields can be null on the same row; the schema permits this (`type: ["integer", "null"]`) |
| 11.13 | STEP_TRC_02 columns shipped on a STEP_TRC_01-only TSV | adapter doesn't distinguish — refined_* present and populated would be treated as ground truth even if the producer's `step` field claims STEP_TRC_01. Producer-side responsibility. |
