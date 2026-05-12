# toolkit_registries — readiness audit

**Scope:** report only. Audits whether the four top-level specs and the
schema folders are the "upgraded" / current versions, and whether an
**activator** vs **extractor** schema distinction exists anywhere.

**Date:** 2026-05-12. Reviewer: claude (branch
`claude/organize-toolkit-registries-kIIrU`).

---

## 1. Top-level docs — what's current, what's drifting

| File | Self-declared status | Drafted | Actual state |
|---|---|---|---|
| `HIERARCHY_SPEC.md` | v1, "fifth pass" | 2026-05-06 (chat ~34) | **Newest.** Internally consistent. Describes species → genome → cohort → group as the upgraded model. Asserts that `species_scoped:` on roots is **superseded** by `cohort_scoped:` / `genome_scoped:` (see lines 397–404). |
| `MASTER_CONFIG.md` | v1 | 2026-05-06 (chat ~34) | Same date as HIERARCHY_SPEC, but **older in content**. Still teaches `species_scoped:` as the only scoping flag (§"Multi-species support", §"The roots section"). Does not mention `cohort_scoped` / `genome_scoped` anywhere. |
| `DATABASE_DESIGN.md` | chat-16 rewrite, refreshed chat ~34 | 2026-05-06 refresh | Refreshed but verbose. Two clear conventions: (a) R-API examples are labeled "illustrative", canonical surface is `registry.resolve()` / `registry.write()`; (b) the 4-role model survives. Internally consistent. The "Per-candidate folder layout" and "Where TSVs live" sections still carry chat-11/12 R API examples — flagged but not removed. |
| `SPEC_DEFERRED.md` | "LANTA-era reference document" | pre-chat-34 | Explicitly flagged at top as historical. Algorithms canonical; API surface gone. No action needed unless a deferred feature is picked up. |
| `README.md` | active | 2026-05-06 | Tables match files on disk (verified). |

**Readiness call:** HIERARCHY_SPEC is the **upgraded** doc you remember.
MASTER_CONFIG.md is half a step behind — it predates the
`cohort_scoped` / `genome_scoped` decision encoded in HIERARCHY_SPEC.
DATABASE_DESIGN.md is current but heavy.

### Concrete drift point — `species_scoped` vs `cohort_scoped` / `genome_scoped`

HIERARCHY_SPEC.md §"Where data physically lives", lines 397–404:

> The earlier `species_scoped: true` flag on roots in `master_config.yaml`
> is **superseded** by this layout. The new master_config (when refactored,
> next session) uses:
> - `genome_scoped: true` for roots like `precomp` and `dosage`
> - `cohort_scoped: true` for roots like `relatedness`, `ancestry`,
>   `popstats`, `candidates`, `groups`
> - Flat for `comparative`, `working_dir`, `cache`.

What actually exists today:

| File | Status |
|---|---|
| `toolkit_registries/schemas/registry_schemas/master_config.schema.json` | Defines only `species_scoped` (line 110); no `cohort_scoped` / `genome_scoped` property. |
| `master_config.example.yaml` | Uses `species_scoped: true` for 8 roots. |
| `master_config.yaml` (your machine) | `species_scoped: false` everywhere (single-species). |
| `MASTER_CONFIG.md` | Documents `species_scoped` only. |

So the "upgrade" HIERARCHY_SPEC announces has **not** landed in the schema
or the example yaml or MASTER_CONFIG.md. Three downstream artifacts need
to follow when you decide to do it.

### Minor drift points

- `README.md` line 20 references `SPEC_DEFERRED.md` as "each spec's Status
  line was rewritten" — true; SPEC_DEFERRED top-of-file banner is the
  rewrite. Consistent.
- `DATABASE_DESIGN.md` line 42 says "41 structured-block schemas". Actual
  count in `schemas/structured_block_schemas/`: **40** `.schema.json`
  files + 1 index + 1 BK_KEYS doc. The number "41" appears at least 2x
  in the docs. Off-by-one or one schema was removed; either way, **doc
  ↔ filesystem drift of 1**.

---

## 2. Registry schemas — version + readiness

All 10 files in `schemas/registry_schemas/` declare:
- `"$schema": "http://json-schema.org/draft-07/schema#"` (consistent)
- `"$id": "<filename>"` (consistent)

| Schema | $schema | $id | _doc constraint block | Status per README |
|---|---|---|---|---|
| `species.config` | draft-07 | yes | — | active |
| `genome.config` | draft-07 | yes | yes | active |
| `cohort.config` | draft-07 | yes | yes | active |
| `sample_master` | draft-07 | yes | — | active |
| `group_definition` | draft-07 | yes | yes | active |
| `sample_group` | draft-07 | yes | — | back-compat (superseded by group_definition) |
| `candidate_interval` | draft-07 | yes | — | active |
| `evidence_key` | draft-07 | yes | — | active |
| `result_row` | draft-07 | yes | — | active |
| `master_config` | draft-07 | yes | — | active but **stale wrt scoped flags** (see §1) |

All five hierarchy schemas referenced in HIERARCHY_SPEC §"Schemas written
this round" exist. Nothing missing.

`structured_block_schemas/` — 40 files plus `INDEX_remaining_blocks.json`
and `BK_KEYS_EXPLAINED.md`. README marks "draft; polished per-page during
atlas migration". No attempt was made to deep-audit each block.

---

## 3. Activator vs extractor schemas — the concept you described

You described two roles:
- **Activator** — "we use the activation schema to call an analysis"
  (create new results).
- **Extractor** — "extract results from a certain filetype or folder".

### Does this exist as named schemas in `toolkit_registries/`?

**No.** A repo-wide search for `activator` / `extractor`:

| Term | Hits |
|---|---|
| `activator` | 0 |
| `extractor` | 1 — and it's a passing reference to a "key-extractor library" in `structured_block_schemas/age_evidence.schema.json:68`, unrelated to your concept. |

There are no files like `activator.schema.json` or `extractor.schema.json`
in any registry folder.

### Does the **concept** exist under different names? Yes — in `core/`, not `toolkit_registries/`.

`core/registry_core.schema.json` defines `source_kind` (line 20) with
four values:

| `source` value | Direction | What you called it |
|---|---|---|
| `'file'` | Read a path from disk; extract a payload | **extractor** |
| `'operation'` | POST to a server endpoint; compute new result | **activator** |
| `'analysis'` | Call a browser-side JS module; compute new result | **activator** (browser variant) |
| `'inline'` | Constant value inline in config | neither |

Each layer entry in `<atlas>/registries/data/layers.registry.json`
declares which kind it is via `"source": "..."`. The runtime dispatch
lives in `core/registry_core.js:469` (`_fetchByEntry` → branches on
`entry.source`).

So your **activator** = `source: 'operation' | 'analysis'`
and your **extractor** = `source: 'file'`. The mental model is correct,
and it's wired through to the runtime; it just isn't named that way and
isn't split into two separate schemas.

### What the existing schemas in `toolkit_registries/` actually are

They are **payload contracts** — the shape of data that flows through
the registry, regardless of whether it was activator-produced or
extractor-read:

- `registry_schemas/*.schema.json` — config-row and manifest-row shapes
  (species/genome/cohort/group records, candidate_interval, result_row,
  evidence_key, master_config).
- `structured_block_schemas/*.schema.json` — per-aspect evidence block
  shapes (boundary_refined.json, gene_cargo.json, etc.).

The only "operation/activator-side" schema lives in
`core/registry_core.schema.json` as `operation_entry` (line 50):
```
{ endpoint, method, inputs, output_schema, cache_key, cache_tier, engine }
```
This is inline in the meta-schema, not a standalone `*.schema.json` file
in `toolkit_registries/`.

### What's missing if you want first-class activator/extractor schemas

Three plausible gaps, in increasing scope:

1. **Promote `operation_entry` to a standalone file** —
   `toolkit_registries/schemas/registry_schemas/operation_entry.schema.json`
   referenced from the meta-schema. Mechanical move; preserves all
   existing fields. This is the closest thing to an "activator schema".

2. **Add an `extractor_entry` schema** that captures the rules for
   reading a file/folder into the registry — currently this lives as
   the `layer_entry` fields `path`, `format`, `fields`, `schema`,
   `schema_status` in `core/registry_core.schema.json` (line 26). It
   could be lifted out and named explicitly. Today, "extractor" is
   implicit in `source: 'file'`.

3. **Document the activator/extractor framing** in a new short doc
   (e.g. `toolkit_registries/ACTIVATOR_EXTRACTOR.md`) that maps your
   mental model onto the existing `source_kind` enum + `operation_entry`
   + the file-source `layer_entry` subset. Cheapest move; no code
   changes. Could live as a section in `DATABASE_DESIGN.md` instead.

None of (1)–(3) have been done. The contract exists in `core/`; it just
isn't surfaced in `toolkit_registries/` under names that match how you
think about it.

---

## 4. Suggested next moves (no edits applied)

In order of value, cheapest first:

1. **Decide on activator/extractor terminology.** Either adopt the
   existing `source_kind` names (file / operation / analysis) and write
   a one-page mapping doc, or rename to activator/extractor and update
   the enum + `_fetchByEntry` dispatch. The former is a doc change; the
   latter touches `core/registry_core.js` and every existing
   `layers.registry.json`.

2. **Land the `cohort_scoped` / `genome_scoped` flags** that HIERARCHY_SPEC
   already promised. Three files change: `master_config.schema.json`
   (add the two boolean properties), `MASTER_CONFIG.md` (update §"Roots"
   and §"Multi-species support"), `master_config.example.yaml` (flip
   the appropriate roots). Existing `species_scoped` stays as
   back-compat per HIERARCHY_SPEC's per-page migration plan.

3. **Fix the "41 vs 40 structured block schemas" doc/filesystem drift.**
   Either re-add the missing schema or update the count to 40 in
   `README.md` and `DATABASE_DESIGN.md`.

4. **Promote `operation_entry` into `schemas/registry_schemas/` as a
   standalone file** if you want activator definitions to live next to
   the payload contracts.

No edits have been made to any file other than this audit document.
