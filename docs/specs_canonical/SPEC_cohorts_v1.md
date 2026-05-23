# SPEC — `cohorts.registry.json` v1

**Status**: proposal. Authored 2026-05-23 in `inversion-atlas/docs/atlas-core-proposals/`, intended for `atlas-core/docs/SPEC_cohorts_v1.md`.

**Companion files**:
- Schema: `schemas/cohorts.schema.json`
- Reference impl: `reference_impl/cohorts_registry.js`, `reference_impl/cross_atlas_imports.js`
- Tests: `tests/cohorts_registry.test.js`, `tests/cross_atlas_imports.test.js`

**Open question (called out for review)**: should `cross_atlas_imports.js` hard-refuse cohort-mismatched reads, or default to a warning + opt-in strict mode? **Proposed: hard-refuse by default**, with per-import `allow_cohort_mismatch: true` (which logs a banner). The migration plan (`docs/MIGRATION_4_ATLASES.md` §5.3) assumes hard-refuse.

---

## 1. Problem

The inversion-atlas codebase enforces three-cohort discipline by **comment policing**:

> F1 hybrid (assembly paper) ≠ 226-sample pure *C. gariepinus* (current inversion atlas) ≠ pure *C. macrocephalus* wild (future paper). **Three cohorts must NEVER conflate.**

That comment appears in `pages/comparative/README.md`, `HANDOFF_COMPLETE.md` from the BP_ATLAS bundle, several SPECs in `specs_todo/`, and most module headers. Every time a contributor reads a layer that wasn't authored against their atlas's cohort, they're expected to remember the discipline.

This works in a single atlas where one human reads the code. It breaks when:

- The atlas is split into 4 (per `docs/MIGRATION_4_ATLASES.md`), and cross-atlas data flows go through registry imports rather than JS imports.
- A new contributor reads a layer whose `cohort_id` is implicit in its path (e.g. `data/comparative/cross_species/...`) without realising the conflation risk.
- An LLM-driven session writes code that joins `inversion.candidates_v1` (cohort: 226-Cgar hatchery) against `crossSpecies.breakpoints_consolidated_v1` (cohort: F1 hybrid 18-genome) and produces a manuscript table that silently confuses the two.

Atlas-core needs a machine-readable cohort registry that:

1. Names every cohort with a stable id.
2. Declares which atlases each cohort is in-scope for.
3. Explicitly enumerates the (small) set of cross-cohort coordinate handoffs that are legitimate (e.g. BP_ATLAS coordinates → hatchery atlas BP4 join).
4. Refuses cross-atlas reads where the cohort tag doesn't match the consuming atlas's declared cohorts (or isn't a registered handoff).

This SPEC also defines `cross_atlas_imports.js`, the runtime resolver that uses the cohort registry to police reads.

## 2. Design goals

1. **One registry per atlas-core install** (global, not per-atlas), so the cohort namespace is unambiguous across atlases.
2. **Cohort-tag travels with the data.** Every produced artifact (file, layer record) carries `cohort_id` + `reference_id`.
3. **Refuse mismatches by default.** Cross-atlas reads that don't match consumer's cohort fail loud unless explicitly handoff-tagged.
4. **No biology in the schema.** Cohorts can be fish populations, mouse strains, plant cultivars, human disease cohorts. Atlas-core's schema only requires `cohort_id`, `label`, `reference_id`, `scope`, `atlases[]`.
5. **Coordinate handoffs are first-class.** The BP_ATLAS pattern — "comparative cohort emits coordinates that the hatchery cohort joins to its own samples" — is the legitimate cross-cohort pattern and must be declarable.

## 3. File location + shape

Single global file: `atlas-core/core/cohorts.registry.json` (NOT per-atlas).

```jsonc
{
  "$schema": "./schemas/cohorts.schema.json",
  "version": "1.0",
  "cohorts": [
    {
      "cohort_id": "f1_hybrid_cga_cma",
      "label": "F1 hybrid (Clarias gariepinus × Clarias macrocephalus)",
      "species": ["Clarias gariepinus", "Clarias macrocephalus"],
      "reference_id": "fClaHyb_Gar_LG",
      "n_samples_approx": 18,
      "scope": "assembly_paper_only",
      "atlases": ["cross-species"],
      "notes": "18-genome comparative cohort used by the BP_ATLAS workflow. Never claims about individual variation."
    },
    {
      "cohort_id": "cgar_hatchery_226",
      "label": "226-sample pure C. gariepinus hatchery",
      "species": ["Clarias gariepinus"],
      "reference_id": "fClaHyb_Gar_LG",
      "n_samples_approx": 226,
      "scope": "inversion_atlas_main_cohort",
      "atlases": ["inversion", "evolution", "popstats"],
      "notes": "MS_Inversions_North_african_catfish. K=broodline. The primary cohort for per-individual claims."
    },
    {
      "cohort_id": "cmac_wild_future",
      "label": "Pure C. macrocephalus wild",
      "species": ["Clarias macrocephalus"],
      "reference_id": "fClaHyb_Mac_LG",
      "n_samples_approx": null,
      "scope": "future_paper",
      "atlases": [],
      "notes": "Not yet in any atlas. Layers tagged with this cohort_id are reserved for a future paper."
    }
  ],
  "cross_reference_handoffs": [
    {
      "handoff_id": "bp_atlas_to_hatchery_join",
      "from_cohort": "f1_hybrid_cga_cma",
      "to_cohort": "cgar_hatchery_226",
      "via_layer_pattern": "crossSpecies\\.(breakpoints_consolidated|bp_atlas_reciprocity|synteny_18sp|gene_order_catalog|atlas_paf_arcs)_v\\d+",
      "handoff_kind": "coordinate_handoff",
      "rationale": "Cross-species BP_ATLAS produces breakpoint coordinates on the fClaHyb_Gar_LG reference; the hatchery atlas reads those coordinates to test population-level overlap (BP4). Coordinates only — never inherit cohort claims."
    }
  ]
}
```

## 4. Schema overview (full schema in `cohorts.schema.json`)

A cohort has:

- **identity**: `cohort_id` (slug, unique), `label`, `species` (list), `reference_id`
- **scope**: `n_samples_approx`, `scope` (free text), `atlases` (list of atlas_ids this cohort appears in)
- **provenance**: `notes`

A `cross_reference_handoff` has:

- **identity**: `handoff_id`
- **direction**: `from_cohort`, `to_cohort` (cohort_ids)
- **scope**: `via_layer_pattern` (regex matched against `<atlas_id>.<layer_id>`)
- **kind**: `handoff_kind` ∈ `{coordinate_handoff, reference_join, none_yet}`
- **rationale**: free text — required, audited at review

## 5. Validation rules

The reference implementation validates:

1. Every `cohort_id` is unique.
2. Every `cohort.reference_id` is non-empty.
3. Every `cohort.atlases[]` entry refers to an installed atlas (cross-validated against `atlases/_index.json`).
4. Every `handoff.from_cohort` and `handoff.to_cohort` refers to a registered cohort.
5. Every `handoff.via_layer_pattern` is a valid regex.
6. No two handoffs match the same `(from_cohort, to_cohort, layer)` tuple.

Validation failures are loud — atlas-core refuses to start until they're fixed.

## 6. API surface (cohorts_registry.js exports)

```js
import { loadCohortsRegistry, validateCohortsRegistry,
         getCohort, listCohorts, getCohortsForAtlas,
         findHandoff, listHandoffs } from 'core/cohorts_registry.js';

const registry = await loadCohortsRegistry(coreRoot);
const errors = validateCohortsRegistry(registry, atlasesIndex);
if (errors.length) throw new RegistryError(errors);

// Per-atlas:
const cohorts = getCohortsForAtlas(registry, 'inversion');
// → [ {cohort_id: 'cgar_hatchery_226', ...} ]

// Handoff lookup at read time:
const hf = findHandoff(registry, 'f1_hybrid_cga_cma', 'cgar_hatchery_226', 'crossSpecies.breakpoints_consolidated_v1');
// → {handoff_id: 'bp_atlas_to_hatchery_join', ...} or null
```

## 7. `cross_atlas_imports.js` — the read-time policer

When atlas A wants to read atlas B's layer, the read goes through `cross_atlas_imports.read()`. The resolver enforces:

```js
read({
  consumer_atlas_id: 'inversion',
  layer_ref:         'crossSpecies.breakpoints_consolidated_v1',
  knob_hash:         null,        // optional, opt-in to staleness check
  allow_cohort_mismatch: false,   // default; per-call opt-out
}) → Promise<{
  data:                <layer data>,
  meta: {
    producer_atlas_id: 'cross-species',
    producer_cohort_id: 'f1_hybrid_cga_cma',
    consumer_cohorts:  ['cgar_hatchery_226'],
    handoff_used:      'bp_atlas_to_hatchery_join',
    knob_hash:         'a3b7c9d2',
    workflow_status:   'ok',     // or 'failed' / 'stale' / 'never_run'
  }
}>
```

Algorithm:

1. Look up the producer atlas of `layer_ref`. (Layer id is `<atlas_id>.<layer_id>`.)
2. Look up the producer cohort of the layer (from the producer atlas's `layers.registry.json`'s `cohort_id` field).
3. Look up the consumer's cohorts (from the cohorts registry, filtered by `consumer_atlas_id`).
4. If `producer_cohort` ∈ `consumer_cohorts`: pass. (Same cohort, no handoff needed.)
5. Else: look for a handoff in the registry matching `(producer_cohort, consumer_cohort, layer_ref)`.
   - If found: pass, attach `handoff_used` to meta.
   - If not found and `allow_cohort_mismatch === true`: pass, log a banner.
   - If not found and `allow_cohort_mismatch === false` (default): **reject** with `CohortMismatchError`.
6. Optionally, check `knob_hash` against the producer workflow's current `default_knob_hash`. If different, attach `workflow_status: 'stale'`.

## 8. Workflow-status integration

When a layer is produced by a registered workflow (per `SPEC_workflows_v1`), `cross_atlas_imports.read()` also reads the workflow's `status.json` and attaches `workflow_status` to the meta block. The consumer page can choose to render an "outputs stale" banner.

The four possible `workflow_status` values:

- `'ok'` — last run succeeded; knob_hash matches default
- `'stale'` — last run succeeded; knob_hash differs from default (a parameter sweep)
- `'failed'` — last run failed; data is from a prior successful run
- `'never_run'` — no `status.json` found; data is unknown provenance

## 9. Cohort discipline for *new* atlas-side code

When an atlas author writes a page that reads layers, they declare:

```jsonc
// in atlases/<atlas_id>/pages/<stage>/<page>.registry.json
{
  "page_id": "candidate_focus",
  "reads": [
    { "layer": "inversion.candidates_v1" },
    { "layer": "crossSpecies.breakpoints_consolidated_v1" }
  ]
}
```

At page-mount time, atlas-core calls `cross_atlas_imports.read()` for each entry. Cohort enforcement is automatic. The page receives `data` + `meta` for each.

For ad-hoc reads (page state callbacks, etc.) the page calls `cross_atlas_imports.read()` directly and gets the same enforcement.

## 10. Failure modes

| Failure | atlas-core behaviour |
|---|---|
| `cohorts.registry.json` is missing | atlas-core refuses to start; cohort discipline cannot be enforced |
| Schema validation fails | atlas-core refuses to start |
| A cohort references a non-existent atlas | atlas-core refuses to start; `atlas_id` in `cohorts.atlases[]` must match `atlases/_index.json` |
| A handoff regex doesn't compile | atlas-core refuses to start |
| Cross-atlas read with cohort mismatch and no handoff | `CohortMismatchError` thrown at the read site; calling page must catch and either pass `allow_cohort_mismatch: true` or refuse to mount |
| Cross-atlas read for a layer that doesn't exist | `LayerNotFoundError` |
| Cross-atlas read for an atlas that isn't installed | `AtlasNotInstalledError` |

`CohortMismatchError`'s message includes the regex pattern that *would* have matched, so the fix is "add a handoff entry" rather than "guess the right shape." Example:

```
CohortMismatchError: page 'inversion.review.candidate_focus' tried to read
'crossSpecies.dxy_per_inversion_v1' (cohort: f1_hybrid_cga_cma) from atlas
'inversion' (cohorts: [cgar_hatchery_226]). No matching cross-reference
handoff in cohorts.registry.json. To allow this read, add:

  {
    "handoff_id": "<choose-a-name>",
    "from_cohort": "f1_hybrid_cga_cma",
    "to_cohort":   "cgar_hatchery_226",
    "via_layer_pattern": "crossSpecies\\.dxy_per_inversion_v\\d+",
    "handoff_kind":      "coordinate_handoff",
    "rationale":         "<why this read is safe>"
  }
```

## 11. Migration path

When this SPEC ships, atlases that already use cross-page reads (today via JS imports) will start failing if the implicit cohort cross is illegitimate. To smooth migration:

1. **Phase 0a**: ship the SPEC + reference impl with `allow_cohort_mismatch: true` as the *default* for the first release. Log warnings, don't refuse.
2. **Phase 0b** (1-2 weeks later): flip the default to `false`. Atlases get a hard error and must declare handoffs explicitly.

This gives existing atlases a window to add handoff entries without breaking on the day the SPEC ships.

The migration plan (`docs/MIGRATION_4_ATLASES.md`) treats this as a Week 1 task in Phase 0.

## 12. Out of scope

- Per-sample cohort membership (a cohort is a set; sample-level membership is the producer's job, not the registry's).
- Cohort merging at runtime (cohorts are immutable identifiers; merging is a producer-side decision that creates a new cohort).
- Cohort versioning (a cohort that gains samples gets a new cohort_id, e.g. `cgar_hatchery_226` → `cgar_hatchery_300`).
- Cohort sub-cohorts (use a separate cohort_id, e.g. `cgar_hatchery_226_family_A`).

## 13. Versioning

`cohorts.registry.json` has a top-level `version` field. This SPEC is `v1.0`.

---

*End of SPEC. Reference implementations in `reference_impl/cohorts_registry.js` and `reference_impl/cross_atlas_imports.js`.*
