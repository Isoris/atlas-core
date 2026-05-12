# toolkit_registries — readiness audit

**Scope:** readiness assessment of the top-level specs, schema folders,
and the activator/extractor terminology question.

**Originally written:** 2026-05-12.
**Refreshed:** 2026-05-12 after the four unblocked items landed in
commit `9fe3b9e`. Items marked **[LANDED]** were resolved on this
branch (`claude/organize-toolkit-registries-kIIrU`); items marked
**[BLOCKED]** wait on per-page atlas/analysis migration.

---

## 1. Top-level docs — what's current, what's drifting

| File | Self-declared status | State after the 9fe3b9e refresh |
|---|---|---|
| `HIERARCHY_SPEC.md` | v1, "fifth pass" | Newest. Internally consistent. Canonical for the species → genome → cohort → group model. |
| `MASTER_CONFIG.md` | v1 | **[LANDED]** New §"Cohort-scoped and genome-scoped roots" documents the three flags HIERARCHY_SPEC introduced. `species_scoped` is now labeled legacy. |
| `DATABASE_DESIGN.md` | chat-16 rewrite, refreshed chat ~34 | Refreshed. R-API examples remain as illustration; canonical surface is `registry.resolve()` / `registry.write()`. |
| `SPEC_DEFERRED.md` | LANTA-era reference | Historical. No action needed unless a deferred feature is picked up. |
| `README.md` | active | **[LANDED]** Tables now list `ACTIVATOR_EXTRACTOR.md`, `operation_entry.schema.json`, and updated to "40 structured-block schemas". |
| `ACTIVATOR_EXTRACTOR.md` | new | **[LANDED]** Maps activator/extractor onto the existing `source_kind` enum. |

### Drift points — status after refresh

| Drift | State |
|---|---|
| `cohort_scoped` / `genome_scoped` flags missing from the schema | **[LANDED]** Added to `master_config.schema.json`. Three new properties on `root_entry` (mutually exclusive with `species_scoped`) plus `atlas.active_cohort`. |
| `MASTER_CONFIG.md` only documents `species_scoped` | **[LANDED]** New section added; `species_scoped` labeled legacy with per-page migration posture documented. |
| `master_config.example.yaml` still uses `species_scoped: true` | **[BLOCKED]** HIERARCHY_SPEC explicitly says the example flips per-page as page1+ migration touches each layer. Intentional. |
| `master_config.yaml` (local) uses `species_scoped: false` everywhere | Single-species, single-cohort posture. Will flip per-page alongside the example. |
| Docs claimed "41 structured-block schemas", filesystem has 40 | **[LANDED]** Both `README.md` and `DATABASE_DESIGN.md` now say 40. `INDEX_remaining_blocks.json` is called out separately. |

---

## 2. Registry schemas — version + readiness

All 11 files in `schemas/registry_schemas/` declare draft-07 with `$id`
matching the filename.

| Schema | Status |
|---|---|
| `species.config` | active |
| `genome.config` | active |
| `cohort.config` | active |
| `sample_master` | active |
| `group_definition` | active |
| `sample_group` | back-compat (superseded by group_definition; clearly labeled in-file) |
| `candidate_interval` | active |
| `evidence_key` | active |
| `result_row` | active |
| `master_config` | **[LANDED]** active; now includes `cohort_scoped` / `genome_scoped` / `atlas.active_cohort` |
| `operation_entry` | **[LANDED]** new file; canonical activator definition; `core/registry_core.schema.json` mirrors it inline with a pointer back here |

`structured_block_schemas/` — 40 per-aspect `.schema.json` files plus
`INDEX_remaining_blocks.json` and `BK_KEYS_EXPLAINED.md`. README posture
is "draft; polished per-page during atlas migration" — **[BLOCKED]** on
that per-page touch.

---

## 3. Activator vs extractor — terminology

**[LANDED]** as `ACTIVATOR_EXTRACTOR.md`. The mental-model mapping:

| You called it | `source_kind` value | Dispatch |
|---|---|---|
| **extractor** | `'file'` | read a path from disk |
| **activator** (server) | `'operation'` | POST to atlas backend; runs C engine |
| **activator** (browser) | `'analysis'` | call a JS module function |
| (neither) | `'inline'` | constant inline in config |

The enum stays as-is (renaming would touch every atlas + `core/`); the
doc bridges the terminology.

The activator's *contract* lives in
`schemas/registry_schemas/operation_entry.schema.json` (canonical) and
is mirrored inline in `core/registry_core.schema.json` for the
self-contained meta-schema. Extractor *contract* is the per-layer
`schema` field, which in turn points at one of the payload schemas in
`registry_schemas/` or `structured_block_schemas/`.

---

## 4. What's left

### Anything still actionable inside `toolkit_registries/` without per-page work?

No. The four items flagged in this doc's first version (commit
`77330be`) have all landed in `9fe3b9e`. No further spec or schema
change here is unblocked.

### What remains, by category

**[BLOCKED] on per-page atlas migration:**
- Polish of the 40 `structured_block_schemas/*.schema.json` — each is
  tightened when a page consumes it.
- Flip `master_config.example.yaml` roots from `species_scoped: true`
  to `cohort_scoped:` / `genome_scoped:` per-layer-touched.
- 4-role JS facade (`registry.samples.X`, `registry.evidence.X`, …) in
  `core/registry_core.js`.
- Integrity-check JS implementation — waits for `result_row` write
  paths to be exercised.

**[BLOCKED] on use case / data availability:**
- `SPEC_DEFERRED.md` items (LANTA-era scientific specs).
- Sub-cluster group registration (`STEP_C01i_e_subcluster.R` equivalent).
- Atlas-specific schemas (`arrangement_calls`, `karyotype_assignment`)
  — those belong in `<atlas>/registries/schemas/`, not here.

**Low-value, do anytime:**
- Port some R-API illustrative examples in `DATABASE_DESIGN.md` to JS.
  The doc keeps them as illustration; rewriting is optional.

---

## 5. Commit history on this branch

- `77330be` — initial audit (`STATUS.md` v1, report-only).
- `9fe3b9e` — four unblocked items landed
  (`cohort_scoped`/`genome_scoped` in schema + doc, 41→40 count fix,
  `ACTIVATOR_EXTRACTOR.md`, `operation_entry.schema.json` promoted).
- (this commit) — `STATUS.md` refreshed to reflect that state.
