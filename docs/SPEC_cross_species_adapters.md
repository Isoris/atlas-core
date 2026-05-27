# SPEC: cross-species atlas adapters

**Status:** shipped 2026-05-24 (Phase 1e — schemas + actions + extractors).
**Owner:** cross-species-atlas.
**Companion docs:** [SPEC_cross_atlas_adapters.md](SPEC_cross_atlas_adapters.md),
[SPEC_atlas_adapter_cookbook.md](SPEC_atlas_adapter_cookbook.md),
[SPEC_registry_v1.md](SPEC_registry_v1.md).

---

## Why this SPEC

The cross-species atlas now has two finished producer pipelines:

1. **macrosyntR gene-anchored 18-species synteny** (BUSCO single-copy ortholog
   backbone) — produces gene-order breakpoints with cross-species support counts.
2. **Sequence-based BP_ATLAS** (wfmash two-pass + STEP_BP* clustering) —
   produces raw events, per-anchor zones, both-anchor reciprocity, joint A-E
   classification, and figure inputs.

Their outputs feed everywhere: inversion-atlas's candidate catalogue,
evolution-atlas's polarisation, and the cross-species atlas's own 5 pages.
Without typed adapters, each consumer would parse raw TSVs differently and
column-name drift would compound. This SPEC pins:

- The **IN side** — JSON-Schema-validated action manifests that drive each
  pipeline through `POST /api/actions`.
- The **OUT side** — typed envelopes the consumer atlases see when they call
  `registry.resolve('cross-species.<layer_id>')`.
- The **adapters** — Python extractors that go raw → envelope.

---

## 1. IN side: action manifests

Three actions, each validated by a `schemas/schema_in/*.schema.json` file:

| action_type | manifest schema | What it runs | Outputs |
|---|---|---|---|
| `run_macrosyntr` | [run_macrosyntr_v1](../../cross-species-atlas/atlases/cross-species/registries/schemas/schema_in/run_macrosyntr_v1.schema.json) | macrosyntR + BUSCO actinopterygii_odb10 + tolerance sweep | `synteny_18sp_v1` or `synteny_5sp_v1` (per `target.panel`) |
| `run_bp_atlas_pipeline` | [run_bp_atlas_pipeline_v1](../../cross-species-atlas/atlases/cross-species/registries/schemas/schema_in/run_bp_atlas_pipeline_v1.schema.json) | wfmash 2-pass + STEP_BP2/3a/3c/5/6 | 7 layers: `bp_atlas_passA/B_paf_v1`, `bp_atlas_events_v1`, `bp_atlas_zones_v1`, `bp_atlas_reciprocity_v1`, `atlas_data_v1`, `bp_atlas_arcs_v1`, `joint_candidates_v1` |
| `run_gene_order_consolidation` | [run_gene_order_consolidation_v1](../../cross-species-atlas/atlases/cross-species/registries/schemas/schema_in/run_gene_order_consolidation_v1.schema.json) | Pure-Python join of sequence + gene-order calls | `breakpoints_consolidated_v1` (headline), `pairwise_summary_v1`, optionally `tolerance_sweep_v1` |

Each manifest has the same top-level shape:

```json
{
  "target": { "...what to run against..." },
  "params": { "...how to run it..." }
}
```

Submit via `POST /api/actions?atlas=cross-species` with `action_type` matching
one of the three slugs. The dispatcher (currently TBD on cross-species side;
the pattern mirrors `diversity-atlas/atlases/diversity/registries/dispatcher.py`)
routes to a `runner` and then to an `extractor`.

---

## 2. OUT side: envelopes

Six typed envelopes, each backed by a `schemas/schema_out/*.schema.json` file:

| Layer | Schema | What's in it |
|---|---|---|
| `synteny_18sp_v1` | [synteny_18sp_v1](../../cross-species-atlas/atlases/cross-species/registries/schemas/schema_out/synteny_18sp_v1.schema.json) | Gene-order breakpoints + support counts + stability scores. `focal_genome` + `min_species_support` + `breakpoints[]` |
| `synteny_5sp_v1` | [synteny_5sp_v1](../../cross-species-atlas/atlases/cross-species/registries/schemas/schema_out/synteny_5sp_v1.schema.json) | Same shape as 18sp, restricted to the 5-haplotype panel. `$ref`s into the 18sp schema for shared item types |
| `bp_atlas_events_v1` | [bp_atlas_events_v1](../../cross-species-atlas/atlases/cross-species/registries/schemas/schema_out/bp_atlas_events_v1.schema.json) | Raw events pre-clustering: `query_*`, `target_*`, `event_class`, `pair_kind`. Per-anchor (BP_ATLAS calls each event twice) |
| `bp_atlas_zones_v1` | [bp_atlas_zones_v1](../../cross-species-atlas/atlases/cross-species/registries/schemas/schema_out/bp_atlas_zones_v1.schema.json) | Clustered zones per anchor. `anchor`-keyed envelope (templated; one file per `{anchor}` arg) |
| `bp_atlas_reciprocity_v1` | [bp_atlas_reciprocity_v1](../../cross-species-atlas/atlases/cross-species/registries/schemas/schema_out/bp_atlas_reciprocity_v1.schema.json) | Both-anchor join. `cgar_zone_id` + `cmac_zone_id` + `confidence_tier` + `backbone_support` |
| `breakpoints_consolidated_v1` | [breakpoints_consolidated_v1](../../cross-species-atlas/atlases/cross-species/registries/schemas/schema_out/breakpoints_consolidated_v1.schema.json) | **HEADLINE**. Cross-method join. `tier` (1 = cross-method, 2 = recurrent single-method) + nested `sequence_evidence` + `gene_order_evidence` + `handoff_inversion_candidate_id` |

**Common envelope shape** (all six follow it):

```json
{
  "<primary_array_name>": [ /* the rows */ ],
  "summary":              { /* aggregates so consumers don't recompute */ },
  "_provenance":          { /* source_path, parsed_at, row_count, ... */ }
}
```

Tolerant column detection (multiple producer column names per logical field)
happens in the extractor — schema only validates the canonical output names.

---

## 3. The adapter wiring

```
   actions.registry.json                   layers.registry.json
   ┌─────────────────────────┐            ┌─────────────────────────┐
   │ "run_macrosyntr": {     │            │ "synteny_18sp_v1": {    │
   │   manifest_schema → IN  │  produces  │   produced_by → action  │
   │   runner          → py  │ ─────────► │   extractor       → py  │
   │   extractor       → py  │            │   output_schema   → OUT │
   │ }                       │            │ }                       │
   └─────────────────────────┘            └─────────────────────────┘
              │                                       ▲
              │                                       │
              │   extractors.registry.json            │
              │   ┌─────────────────────────┐         │
              └──►│ "extract_synteny_18sp": │─────────┘
                  │   input_layer  → layer  │
                  │   output_schema → OUT   │
                  │   module        → py    │
                  │ }                       │
                  └─────────────────────────┘
```

**Read path** (atlas pages):

```js
// cross-species's bp_catalogue page:
const headline = await registry.resolve('breakpoints_consolidated_v1');
// → fetch breakpoint_clusters.tsv via cross_species_consolidated root
// → run extract_breakpoints_consolidated_v1 (raw rows → typed envelope)
// → return envelope matching breakpoints_consolidated_v1.schema.json
```

**Cross-atlas read** (inversion atlas's catalogue):

```js
const xs = await registry.resolve('cross-species.breakpoints_consolidated_v1');
// → same path, dotted prefix stripped by registry._lookup
```

**Write path** (analyst triggers a re-run):

```
POST /api/actions?atlas=cross-species
{
  "action_type": "run_macrosyntr",
  "target": { "focal_genome": "fClaHyb_Gar",
              "haplotype_manifest_layer_id": "haplotype_manifest_v1",
              "panel": "18sp" },
  "params": { "min_species_support": 3,
              "tolerance_sweep_kb": [500, 200, 100, 50, 25, 10, 5, 1],
              "stability_min": 0.5 }
}
```

Dispatcher validates the manifest against `run_macrosyntr_v1.schema.json`,
calls `runners.gene_order.run_macrosyntr` (TBD), writes
`synteny_18sp_breakpoints.tsv` to `cross_species_gene_order/`, then
`extractors.synteny_panel.extract` reads it and emits the typed envelope. Next
`registry.resolve('synteny_18sp_v1')` returns the fresh envelope from cache.

---

## 4. Current implementation status

All schemas + registries are **shipped**.
All runners + extractors are **`_status: not_implemented`** — page code can
declare reads against the envelope shape today; the runners + extractors land
when the cluster-side pipelines are wired through the dispatcher.

**Lint:** `python atlas-core/build/_lint_atlases.py` returns 0 warnings —
every layer's `output_schema` points at an existing file, every action's
`manifest_schema` resolves, every extractor's `input_layer` matches a declared
layer.

---

## 5. Worked example: adding a 3rd panel

Say we get a denser 12-species panel later. The recipe:

1. Add `synteny_12sp_v1` to `layers.registry.json` with the same shape as 18sp
   + `output_schema: schemas/schema_out/synteny_18sp_v1.schema.json` (reuse) +
   `extractor: extract_synteny_18sp_v1` (reuse — extractor is panel-agnostic).
2. Add `12sp` to the `panel` enum in
   `schemas/schema_in/run_macrosyntr_v1.schema.json`.
3. Update `cohorts.registry.json` to add `cross-species.synteny_12sp_v1` to the
   producers map.
4. Add to cross_atlas.exports in cross-species manifest if any other atlas
   should consume it.
5. Run lint.

No new schemas, no new extractors, no new actions. The pattern carries.

---

## 6. Anti-patterns

- **Don't bake column names into page code.** The extractor handles tolerant
  column matching. Page code reads the envelope's canonical names.
- **Don't skip the IN schema.** Even contract-only pipelines should have a
  manifest schema — it's the spec for the eventual runner.
- **Don't write a per-page parser.** If a page is doing `text.split('\n').map(...)`
  on a raw TSV, the extractor is missing. Add it once, every page benefits.
- **Don't reference an extractor module that doesn't exist** without marking it
  `_status: not_implemented`. The contract-only pattern needs the flag to
  document that the wiring is pending.
