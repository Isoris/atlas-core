# SPEC — Haplotype burden coloring (schema-in, color-out)

**Status**: shipped 2026-05-20 (audit-sweep — Phase 1 deliverables
confirmed shipping per inline citations in `candidate_focus.js`
dated 2026-05-20; Phase 2 + 3 deliverables deferred per the SPEC's
own staging plan). Promoted from `specs_todo/` after the per-slice
audit below. Original SPEC body is preserved verbatim below as
design archive.

**Implemented in:**
- [`atlases/inversion/pages/discovery/candidate_focus.js`](../atlases/inversion/pages/discovery/candidate_focus.js) line 367 — explicit inline citation: `2026-05-20 (SPEC_haplotype_burden_coloring.md Phase 1 deliverable #3): export per-sample group labels TSV. microgroup_id comes from cand.locked_labels (per-candidate K-band assignment); macrostripe_id comes from getMacrostripeIdPerSample which folds Stage 3 band-tracking results onto the cohort.`
- [`atlases/inversion/pages/discovery/candidate_focus/_html_builders.js`](../atlases/inversion/pages/discovery/candidate_focus/_html_builders.js) line 157 — matching HTML scaffold for the Phase 1 deliverable
- Companion modules (already in `specs_done/` per [`SPEC_macrostripe_microgroup_hierarchy.md`](SPEC_macrostripe_microgroup_hierarchy.md)): `shared/macrostripe.js` provides the `macrostripe_id` data path; `cand.locked_labels` provides the `microgroup_id` data path

**Per-slice status:**

The SPEC stages its deliverables in three phases. Per the SPEC body §"Phase 1 deliverables" / §"Phase 2 deliverables" / §"Phase 3 deliverables":

| phase | deliverable | status | location |
|---|---|---|---|
| 1 | Per-sample group-label TSV export (microgroup_id + macrostripe_id columns) | ✅ shipped 2026-05-20 | `candidate_focus.js` line 367 + `_html_builders.js` line 157 (inline cite confirms) |
| 1 | Schema-in for the per-sample numeric layer + per-group categorical layer + per-macrostripe aggregate layer (the three schemas in SPEC §"Schema-in: layer files") | ⏳ partial — SPEC defines the three shapes; runtime consumers exist via `macrostripe.js` and the SPEC_macrostripe pipeline, but a dedicated schema validator for incoming burden JSON is not yet shipped |
| 1 | Color modes that ship (per SPEC §"Color modes that ship") | ⏳ partial — macrostripe + microgroup color paths ship via `macrostripe.js#getMacrostripeColor` + the page-side palette; the burden-color mode specifically (continuous heatmap over per-sample burden values attached to group labels) is the deferred slice |
| 2 | Per-candidate burden-join export TSV | ⏳ deferred | The SPEC's Phase 2 goal — joins the Phase 1 group-label export with per-sample burden values; pending |
| 2 | Cohort-wide group export | ⏳ deferred | Same staging |
| 3 | (Phase 3 deliverables — see SPEC body) | ⏳ deferred | Out-of-week per SPEC's own staging note ("For this week, don't analyze") |

**Why archived now:** the SPEC's Phase 1 deliverable #3 (per-sample
group-label TSV export) ships with an explicit dated inline citation
in `candidate_focus.js`. The infrastructure the SPEC depends on
(`macrostripe.js`, microgroup_id from `cand.locked_labels`,
macrostripe_id from `getMacrostripeIdPerSample`) all live in
already-archived `SPEC_macrostripe_microgroup_hierarchy.md` (now in
`specs_done/`). Phases 2 + 3 are the SPEC's own forward-looking
deliverables that haven't been touched yet — they're tracked in this
archived SPEC's slice table for future pickup. The SPEC has done its
job: Phase 1 shipped, the design framework for Phase 2 + 3 is
captured, the code citations make the audit trail durable.

**Companion** to [`SPEC_macrostripe_microgroup_hierarchy.md`](SPEC_macrostripe_microgroup_hierarchy.md)
(at `specs_done/` since 2026-05-20) — that SPEC defines the group
labels (`macrostripe_id` / `microgroup_id`); this SPEC defines the
schema-in/color-out pattern for attaching per-sample or per-group
burden / phenotype data to those labels.

User direction (chat 2026-05-18):

> *"Microgroups are not the final goal by themselves. They become
> useful only when you ask: does this trajectory-defined lineage
> carry more or less deleterious burden than another lineage? So
> it is basically the same framework, just with a different
> phenotype/statistic attached … For this week, don't analyze
> burden. Just make sure the atlas can export the group labels
> cleanly. That is enough."*

This SPEC is **coloring + I/O, not analysis**. The atlas doesn't
compute burden; it consumes a precomp file or user-uploaded JSON
that carries the metric, and renders the metric as colors on the
PCA / lines / L3 surfaces.

## The pattern

```
SCHEMA IN ─────────────────────────────────────────────────────┐
                                                                │
  Any per-sample (or per-group) burden / phenotype table:       │
                                                                │
    sample_id → numeric_or_categorical                          │
                                                                │
  Examples (each is an independent layer):                      │
    sample_id → lof_count            (categorical / count)      │
    sample_id → missense_burden      (numeric, normalized)      │
    sample_id → froh                 (numeric, 0..1)            │
    sample_id → survival_weeks       (numeric)                  │
    sample_id → growth_rate          (numeric)                  │
    sample_id → marker_haplotype_id  (categorical)              │
                                                                │
  OR aggregated to group level:                                 │
    macrostripe_id → mean_lof_count                             │
    microgroup_id  → mean_lof_count                             │
                                                                │
COLOR OUT ─────────────────────────────────────────────────────┤
                                                                │
  Each layer registers a new entry in _LINES_COLOR_MODES:       │
    { id: 'lof_burden',  layer: 'lof_burden',  label: 'LoF' }  │
    { id: 'froh',        layer: 'sample_froh', label: 'F_ROH' }│
    ...                                                         │
                                                                │
  The line-color resolver in shared/per_sample_line_color.js   │
  already supports per-sample values + arbitrary ramps. Each   │
  new layer is an entry in perSampleValuesForMode + a ramp    │
  in perSampleColorFor.                                        │
                                                                │
TSV OUT ───────────────────────────────────────────────────────┘

  Per-candidate export:
    sample_id | macrostripe_id | microgroup_id | <metric columns>

  This is the deliverable the user explicitly wants for "this
  week": make sure the atlas can export the group labels cleanly.
```

## Schema-in: layer files

Each burden / phenotype layer is a separate JSON file added to
the precomp tree, named per `SCHEMA.md` convention. The producer
side (R-pipeline or upstream tool) writes the file; the atlas
detects it via `shared/page1_data_helpers.js#detectSchemaAndLayers`.

### Per-sample numeric layer

Schema key: `<metric_name>`. Example: `lof_burden`.

```json
{
  "schema_version": 1,
  "layer": "lof_burden",
  "samples": ["CGA001", "CGA002", ...],
  "values": [3.0, 0.0, ...],
  "_doc": "Number of LoF variants per sample in the candidate-region
           bp span. Counts homozygous as 2, heterozygous as 1.
           Source: STEP_R??_emit_lof_burden_per_sample.R"
}
```

`samples` is the cohort-order sample id list (matches `data.samples`
by `id` / `cga` / `ind` / `sample`). `values` is parallel. The
atlas's per-sample resolver projects to cohort-index space (same
pattern as `dosage_chunks.js#computeDosageMeanForRange`).

### Per-group categorical layer

Schema key: `<group>_haplotype_id`. Example: `marker_haplotype_id`.

```json
{
  "schema_version": 1,
  "layer": "marker_haplotype_id",
  "samples": ["CGA001", "CGA002", ...],
  "values": ["H1", "H2", "H1", ...],
  "_doc": "PCR / TaqMan marker haplotype call per sample for the
           candidate region. Source: lab-pipeline export.",
  "_palette": "default"
}
```

Categorical layers render with a discrete palette (the existing
`groupColor` palette extended, or `_palette: "default"` /
`_palette: "h_system"`).

### Per-macrostripe aggregate layer

The atlas DERIVES this from per-sample + macrostripe_id, no separate
file needed. Computed at render time by:

```
macrostripe_burden(macrostripe_id) =
  median over (samples whose macrostripe_id == this) of (per-sample burden)
```

Median by default; opt into mean via a per-layer flag.

## Color modes that ship

Extends the existing `_LINES_COLOR_MODES` array in
`shared/page1_data_helpers.js`. The mode appears in:

- `#linesColorModeSelect` (per-sample lines)
- `#colorModeBar` (PCA scatter scope)
- `state.l3HetColoring`-equivalent toggle (L3 mini-PCA dot fill)

Each mode auto-disables when its source layer isn't loaded. Same
`_isLinesColorModeAvailable` predicate that gates het / dosage /
θπ / GHSL today.

The full set of envisioned modes (each is a separate layer file
the producer emits separately):

| mode id | source layer | type | ramp |
|---------|--------------|------|------|
| `lof_burden` | `lof_burden` | count | sequential grey → red |
| `missense_burden` | `missense_burden` | numeric | sequential blue → orange |
| `gene_set_burden` | `gene_set_burden` | numeric | sequential blue → red |
| `froh` | `sample_froh` | numeric in [0,1] | sequential grey → red (already shipped) |
| `survival_weeks` | `survival` | numeric | sequential blue → red |
| `growth_rate` | `growth` | numeric | sequential blue → red |
| `marker_haplotype_id` | `marker_haplotype` | categorical | discrete (h_system palette) |
| `macrostripe_id` | derived | categorical | 3-color (shipped via macrostripe SPEC) |
| `microgroup_id` | derived | categorical | groupColor (today's K-means coloring) |

This SPEC is the GATING contract for whichever subset ships first.
The infrastructure is the same; each layer is opt-in.

## Schema-out: TSV exports

Three exports the atlas should produce. The first is the only one
strictly required by the user's stated weekly goal ("make sure the
atlas can export the group labels cleanly").

### 1. Per-candidate group-label export (Phase 1)

Trigger: button on the candidate-focus page ("📊 export group labels").
Filename: `macrostripe_groups.<chrom>.<candidate_id>.tsv`.

Columns:
```
sample_id   macrostripe_id   microgroup_id   stability_score
```

`stability_score` is the per-sample Hungarian-chain agreement
within the candidate range (already computed in
`shared/lineage_clustering.js` / band tracking).

### 2. Per-candidate burden-join export (Phase 2)

Trigger: button on candidate-focus, opt-in via "include burden
columns" checkbox listing the loaded layers.

Columns:
```
sample_id   macrostripe_id   microgroup_id   stability_score   <metric1>   <metric2>   ...
```

The metric columns appear in the order the user toggles them on.
Renders only when the corresponding layer is loaded.

### 3. Cohort-wide group export (Phase 2)

Trigger: button on the catalogue page ("📊 export all candidates").
Filename: `macrostripe_groups.all_candidates.<cohort>.tsv`.

Columns:
```
sample_id   candidate_id   macrostripe_id   microgroup_id   stability_score
```

One row per (sample × candidate) pair. Long-format — joins cleanly
in R / pandas downstream.

## State surface

Reads:
- `state.data.<metric_name>` — per-sample burden layer (if loaded)
- `state.macrostripeAssignment` — per-candidate macrostripe_id (from
  `SPEC_macrostripe_microgroup_hierarchy.md`)
- `state.candidate` — active candidate

Writes:
- `state.colorMode` — when user picks one of the burden modes
- `state.viewControls.<metric>_visible` — per-metric toggle bookkeeping

## What this SPEC does NOT do

- It does NOT compute burden. The atlas reads burden tables; the
  R-pipeline writes them.
- It does NOT test for burden differences between macrostripes.
  That's a downstream analysis the user runs in R after exporting
  the TSV. The atlas is the *visualization + label-export tool*,
  not the statistical-testing tool.
- It does NOT cluster on burden. K-means / lineage compute / band
  tracking stay PC-space driven; burden is a coloring overlay only.

## Phase 1 deliverables (this week's goal)

1. `shared/per_sample_burden.js` — generic per-sample-keyed layer
   loader. `loadPerSampleLayer(state, layer_key)` reads
   `state.data.<layer_key>` and returns `Float32Array[nS]` (numeric)
   or `string[]` (categorical) projected to cohort-index space.
2. `shared/per_sample_line_color.js` — extend
   `perSampleValuesForMode` to recognize layer ids registered as
   "burden" modes. Each new layer ships with its ramp in
   `perSampleColorFor`.
3. Candidate-focus page: "📊 export group labels" button → emits
   TSV format 1 (sample_id × macrostripe_id × microgroup_id ×
   stability_score). NO burden columns yet; just the labels.

## Phase 2 deliverables

- Per-metric registration in `_LINES_COLOR_MODES` + `detectSchemaAndLayers`.
- Burden-join TSV export (format 2).
- Cohort-wide group export (format 3).

## Phase 3 deliverables

- Per-macrostripe / per-microgroup aggregate computation +
  rendering (median / mean per group). Done at render time, no new
  precomp.
- Optional in-atlas "do macrostripes differ in burden?" badge
  (descriptive only — Mann-Whitney U or rank-sum, reported as
  effect size + p-value WITHOUT calling it "significant").

## References

- `shared/page1_data_helpers.js` — `_LINES_COLOR_MODES` array;
  `detectSchemaAndLayers` for layer detection; the adapter pattern
- `shared/per_sample_line_color.js` — existing per-sample resolver
  split (compute + ramp) that this SPEC extends
- `shared/dosage_chunks.js` — example of a per-sample layer loader
  with chunk-projection semantics
- `SPEC_macrostripe_microgroup_hierarchy.md` — defines the group
  labels that the export joins to
- `SCHEMA.md` — naming convention for layer keys (`<metric_name>`,
  `<group>_haplotype_id`, etc.)

## Best summary paragraph (for atlas help text)

> Burden, phenotype, and marker-haplotype data attach to the
> trajectory-defined macrostripe / microgroup labels by joining on
> sample_id. The atlas does not compute burden — it consumes
> per-sample layer files emitted by the upstream pipeline and
> renders them as colors on the PCA / lines / L3 surfaces. The
> export TSV joins sample_id × macrostripe_id × microgroup_id ×
> stability_score with whatever burden columns are loaded, so the
> downstream R / pandas analysis tests whether trajectory-defined
> haplotype backgrounds differ in deleterious load.
