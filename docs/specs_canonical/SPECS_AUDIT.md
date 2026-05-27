# SPECS_AUDIT — what specs exist, what's missing, what references what

**Question**: most specs seem to be gone — is that true?

**Short answer**: not gone, but **scattered across 4 different doc
folders + 1 nested folder structure**, with **~9 SPEC_* files
referenced in code that have no on-disk doc**. The full picture below.

---

## Spec / handoff folders (2026-05-15: consolidated)

| dir                | purpose | count |
|--------------------|---------|------:|
| `specs_todo/`             | design backlog (authored, not yet implemented) | 14 SPECs + nested `mgl_adapter/` + `pages_*/_to_do/` |
| `specs_done/`             | **NEW** — shipped SPECs (kept forever; seed material for the manual) | 2 SPECs |
| `handoff_docs/`           | older turn-by-turn handoffs (Atlas_round166 era) | 7 handoffs |
| `_handoff_docs/`          | newer turn-by-turn handoffs (chat 34/35/36 + 2026-05-12..14) | 36 files (handoffs + audits + plans) |
| `docs/`                   | migration tracking + family roadmap + TODO inventories | 3 .md + `merge_inputs/` |
| `atlases/inversion/*/README.md` | per-subsystem READMEs | 10 files |

→ entry point: `SPECS.md` at repo root.

---

## Example drop verified: `inversion_atlas_v3.4_DROP` (2026-05-08)

User uploaded two copies of this drop (`.gz` 187 KB / `.zip` 211 KB,
identical contents) as an example of the swept-style standalone
bundles. Contents:

| file | repo location | status |
|------|---------------|--------|
| `README.md` (27 KB, full pipeline diagram) | **not imported** as a standalone doc | content split into `pages.registry.json` page22 _doc + module headers |
| `HANDOFF.md` (37 KB, audit checklist) | **not imported** | same |
| `REGIME_ANNOTATION_SPEC.md` (1436 lines) | `specs_todo/SPEC_regime_annotation_v34.md` | **identical** (0 diff lines) |
| `FISH_ANCESTRY_SCROLLER_SPEC.md` (1599 lines) | `specs_todo/SPEC_fish_ancestry_scroller.md` | **identical** |
| `COPY_ORIGIN_PAINTING_SPEC.md` (500 lines) | `specs_todo/SPEC_copy_origin_painting.md` | **identical** |
| 21 `*.js` modules (anchor_signals / band_quality / window_classification / seed_discovery / cross_seed_voting / locus_construction / projection / breadth_voting / banding_pipeline / band_voters / partition_enumerate / partition_consensus / dosage_overlay / vote_evidence / karyotype_caller / hungarian / contingency + 3 page22 panels + band_tracking_index) | `shared/band_tracking/` + `shared/` + `pages/discovery/page22/` | **all imported** (15 byte-identical except 4 with import-path tweaks `./hungarian.js` → `../hungarian.js`; 2 page22 panels diverged by ~15 lines of post-import work; `band_tracking_index.js` renamed → `shared/band_tracking/index.js` and extended) |
| `band_tracking_index.js` (125 lines) | `shared/band_tracking/{index.js, index_min.js}` | renamed + extended (110 / 243 diff lines vs the two repo variants) |
| `smoke_test.mjs`, `smoke_test_v2.mjs`, `integration_test_v2.mjs`, `regimes_panel_smoke.mjs` | **dropped** | replaced by `tests/test_discovery_page22.js` (different framework) |

**Verdict on this drop**: completely imported, with proper renaming
(SPEC files got the `SPEC_*_v34.md` / `SPEC_*.md` convention,
band_tracking_index.js became the canonical `index.js`). The only
content lost: the 64 KB of meta-docs (README + HANDOFF) describing the
pipeline as a whole — that big pipeline diagram doesn't appear
verbatim anywhere in the repo. The current `pages.registry.json`
page22 _doc covers it at a higher level, but the per-stage diagram
with module names is gone.

**What this tells us**: the import process **kept the SPECs but
dropped the bundle-level READMEs**. If this is representative of how
the other drops landed, then `specs_done/` likely had a similar
shape (per-feature SPECs we now have under different names + meta-doc
READMEs that didn't survive). The SPECs themselves may not be lost;
they may just be renamed to fit the `SPEC_*.md` convention. Worth a
provenance audit: each `specs_todo/SPEC_*.md` should be traced back to
its original drop bundle name.

---

## SPEC_* files that **exist** on disk (16 total)

**Canonical library** (`specs_todo/`):
- `SPEC_arrangement_color_mode_and_arrangement_calls_v1.md`
- `SPEC_busco_4d_age_brackets.md`
- `SPEC_busco_anchors_v1.md`
- `SPEC_copy_origin_painting.md`
- `SPEC_fish_ancestry_scroller.md`
- `SPEC_functional_burden_per_candidate_v1.md`
- `SPEC_inversion_age_atlas_surface_AMENDMENT.md`
- `SPEC_inversion_divergence_network_v1.md`
- `SPEC_mendelian_inheritance_para_vs_peri_v1.md`
- `SPEC_page1_candidate_mode_ui.md`
- `SPEC_regime_annotation_v34.md`
- `SPEC_registry_v1.md`
- `SPEC_registry_write_and_page_isolation.md`
- `SPEC_xpehh_per_window_track.md`

**`mgl_adapter` family** (`specs_todo/mgl_adapter/`):
- `SPEC_0_master.md` — the master mgl_adapter spec
- `README.md` + `README_specs.md` — entry points
- `HANDOFF_1_producer.md`, `HANDOFF_3_validation.md`, `HANDOFF_7_nested_inversion.md`, `HANDOFF_8_dosage_clustering.md`, `HANDOFF_9_dosage_similarity.md`

**Nested per-page handoffs** (`specs_todo/pages_*/_to_do/`):
- `pages_candidate_mode/_to_do/HANDOFF_2_atlas_ui.md`
- `pages_custom_views/_to_do/HANDOFF_4_caching_custom.md`
- `pages_fingerprint_track/_to_do/HANDOFF_6_fingerprinter.md`
- `pages_similarity_panel/_to_do/HANDOFF_10_atlas_similarity.md`
- `pages_tree_panel/_to_do/HANDOFF_5_tree.md`

**Scattered elsewhere** (NOT in `specs_todo/`):
- `specs_done/SPEC_band_track_extraction_and_l3_single_band_rows.md` ← master band-tracking SPEC (moved 2026-05-15 from `handoff_docs/`)
- `specs_done/SPEC_registry_v2.md` ← v2 registry SPEC (moved 2026-05-15 from `_handoff_docs/`)
- `handoff_docs/HANDOFF_2026-05-06_morning_age_specs.md` ← contains inversion-age specs inline

---

## Why specs went missing — the `specs_done/` sweep

User recall: *"in the past we used to have many many specs but they got
done and swept for some reasons"* — **confirmed by `_handoff_docs/AUDIT_LOG.md:3517`**:

> `Atlas/specs_done/`, `specs_todo/`, `specs_new_turn131/` — spec inventory.

The legacy upload tarball (`Atlas_turn166_round2_2026-05-05_tar.gz`,
audited 2026-05-06 late evening) contained **three** spec folders:

| folder              | what it held | what happened |
|---------------------|--------------|---------------|
| `Atlas/specs_done/` | completed specs (the "many many" that got finished) | **NOT copied into this repo** |
| `Atlas/specs_todo/` | spec'd-but-not-implemented | copied to `inversion-atlas/specs_todo/` (the 14 SPECs you see today) |
| `Atlas/specs_new_turn131/` | turn-131 in-flight specs | **NOT copied** — but the legacy monolith still references e.g. `SPEC_per_candidate_breeding_readiness_card.md` (legacy lines 21424, 23239) from this folder |

Git-history check confirms nothing was deleted from this repo: 232 commits, the raw-log status codes are only `A` (add) and `M` (modify), zero `D` (delete). The "swept" specs were lost at **tarball import time**, not in any commit of this repo.

The convention was also documented in `handoff_docs/HANDOFF_2026-05-06_morning_age_specs.md:325`:

> "When the age layer ships into the production atlas, move both specs to `specs_done/` after archiving."

So the workflow was: spec → `specs_todo/` → implement → move to `specs_done/`. That `specs_done/` was archived/sweep-deleted **before** the inversion-atlas repo was seeded, so the audit trail of "what got implemented from what spec" is gone with it.

What remains as evidence the old specs existed:
- Inline references inside `legacy/Inversion_atlas.html` (12 unique `SPEC_*` names, including `SPEC_age_origin_panel`, `SPEC_observable_allele_h_label_system`, `SPEC_per_candidate_breeding_readiness_card`, `SPEC_inversion_age_atlas_surface`)
- 14 changelog turns (1..127) referenced in `AUDIT_LOG.md:3515` — at turn 127 the legacy was 62,023 LOC with 762/762 tests green. The changelogs themselves are also at `Atlas/changelogs/` in the un-imported tarball.

---

## SPEC_* files **referenced but missing** — STATUS UPDATE 2026-05-20

**ALL SPEC_* GAPS NOW RESOLVED.** The 2026-05-15 audit resolved 8 of 9;
the remaining real one — `SPEC_inversion_age_atlas_surface.md` (the
turn-117 parent of the `_AMENDMENT`) — was authored 2026-05-20 from
shipped code (`shared/mgl_inversion_divergence.js`,
`shared/age_model_suggester.js`, `shared/busco_4d_age.js`,
`pages/evolution/age_divergence.{html,js}`) and now lives at
[`specs_done/SPEC_inversion_age_atlas_surface.md`](../specs_done/SPEC_inversion_age_atlas_surface.md).
That SPEC carries explicit per-slice shipped/deferred status against
the AMENDMENT's row layout — the AMENDMENT remains in `specs_todo/`
because most of its prescribed slices are still deferred.

**Re-grep on 2026-05-20** found only 3 names referenced-in-code that
are not on disk:

| name | status |
|---|---|
| `SPEC_inversion_age_atlas_surface.md` | **RESOLVED 2026-05-20** — authored at `specs_done/` (see above) |
| `HANDOFF_BATCH_3.md` | **RETIRED 2026-05-20** — phantom handoff. Every citation is a corrective note (e.g. "HANDOFF_BATCH_3.md mislabels this page as 'Manual karyotype groups list' — corrected here"). The canonical record is `pages/catalogue/BATCH_3_NOTES.md`; the corrective citations stay as historical context explaining renames. |
| `HANDOFF_BATCH_5.md` | **RETIRED 2026-05-20** — same. Canonical record: `pages/comparative/BATCH_5_NOTES.md`. Corrective citations remain as historical context flagging the `help` vs `multi_species_cockpit` mislabel. |

**Notes on conventions discovered during the re-grep:**

- `SPEC_DEFERRED.md` is **NOT** an individual feature SPEC and was
  never meant to be one. Its references (in handoff docs) named a
  *register* of deferred decisions, which the audit decided is better
  expressed as inline `Status: deferred` annotations on the
  individual SPECs. The references in the original audit's "missing"
  table can be retired — no doc to author. Modern SPECs in
  `specs_done/` carry per-slice status inline (see
  `SPEC_inversion_age_atlas_surface.md` §3 for an example of the
  shipped/deferred matrix).
- `HANDOFF_BATCH_4.md` — referenced only in older audits; no citation
  in current code. No action.

How the 2026-05-20 re-grep was done:

```sh
grep -rohE "(SPEC|HANDOFF)_[A-Za-z0-9_.]+\.md" \
  --include="*.js" --include="*.html" --include="*.css" --include="*.py" \
  --include="*.json" --include="*.yaml" \
  atlases/ shared/ docs/ specs_todo/ specs_done/ tests/ engines/ \
  | sort -u
```

Cross-checked each name against `find specs_todo specs_done -name '$name'`.

---

## SPEC_* files **referenced but missing** — STATUS UPDATE 2026-05-15 (historical)

**ALL 8 PREVIOUSLY-MISSING SPECs NOW RESOLVED.** Each was authored
from shipped code + handoffs + legacy line citations and lives at
`specs_done/SPEC_<name>.md`. SPECS were not invented — every claim
in each new SPEC traces back to:
- shipped JS modules (with line numbers)
- legacy `Inversion_atlas.html` comments (with line numbers)
- prior handoffs (`_handoff_docs/HANDOFF_*.md` and `handoff_docs/HANDOFF_*.md`)
- the parent SPEC's interaction notes (where applicable)

Where the shipped code only implemented some of the SPEC's slices,
the SPEC is annotated with per-slice ✅ shipped / 🟡 deferred status
+ a brief reason for each deferral.

`SPEC_DEFERRED.md` (a register of deferred decisions, not an
individual feature SPEC) remains unauthored. Decision: this should
either become a meta-doc or be retired in favour of inline
`Status: deferred` annotations in the individual SPECs.

## SPEC_* files **referenced but missing** (original audit table)

These names appear in code or docs but have **no on-disk file** with that name:

| Referenced as | Referenced from | Status |
|---------------|-----------------|--------|
| `SPEC_DEFERRED.md` | `_handoff_docs/HANDOFF_2026-05-06_chat34_registry_v2_done.md`, `READ_MODES_CONFIRMED.md`, `AUDIT_LOG.md` | **MISSING** — multiple deferred-decisions references, no doc |
| `SPEC_distant_band_concordance_fish_trajectory.md` | `specs_done/SPEC_band_track_extraction_and_l3_single_band_rows.md`, `docs/MIGRATION_INVENTORY.md`, multiple legacy comments | **RESOLVED 2026-05-15** — Slices 1-5 SPEC authored from legacy comments + round-4 local_pca_dosage splits + lineage/band-trace shared modules into `specs_done/SPEC_distant_band_concordance_fish_trajectory.md`. Slice 6 (cross-strip chaining) deferred. |
| `SPEC_g_panel_unified_groups.md` | `pages/discovery/local_pca_dosage/pca_panel.js`, `local_pca_dosage.html` | **RESOLVED 2026-05-15** — Slice 1 SPEC authored from local_pca_dosage.html + pca_panel.js + manual_groups.js into `specs_done/SPEC_g_panel_unified_groups.md`. Slices 2 + 3 (Karyotype + Inheritance tabs) outlined but not yet implemented. |
| `SPEC_l2_sweep_inheritance.md` | `pages/discovery/local_pca_dosage.html`, `MIGRATION_INVENTORY.md`, band-track SPEC | **RESOLVED 2026-05-15** — authored from `local_pca_dosage/l2_sweep.js` (444 LOC) into `specs_done/SPEC_l2_sweep_inheritance.md` |
| `SPEC_l3_het_dosage_coloring.md` | `pages/discovery/local_pca_dosage.html` | **RESOLVED 2026-05-15** — Slice 1 SPEC authored from local_pca_dosage.html turn-128d annotation into `specs_done/SPEC_l3_het_dosage_coloring.md` |
| `SPEC_lasso_inheritance_backgrounds.md` | `handoff_docs/HANDOFF_2026-05-05_turn164_lasso_linkage.md`, `local_pca_dosage.html` | **RESOLVED 2026-05-15** — Slices 1 + 3 SPEC authored from turn-164 handoff + local_pca_dosage.html into `specs_done/SPEC_lasso_inheritance_backgrounds.md`. Slices 2/4/5 deferred. |
| `SPEC_lines_panel_candidate_bands.md` | `MIGRATION_INVENTORY.md`, band-track SPEC | **RESOLVED 2026-05-15** — SPEC authored from local_pca_dosage/lines_panel.js + local_pca_dosage/candidates.js into `specs_done/SPEC_lines_panel_candidate_bands.md` |
| `SPEC_review_surfaces_auto_and_lineages.md` | `css/inversion.css`, `MIGRATION_INVENTORY.md`, band-track SPEC | **RESOLVED 2026-05-15** — Slices 0-2 SPEC authored from CSS lines 947-960 + turn-130 + turn-165 handoffs into `specs_done/SPEC_review_surfaces_auto_and_lineages.md`. Slice 3 (lineages tab) deferred. |
| `SPEC_sv_evidence_page.md` | `engines/producers/sv_evidence/STEP_SV_GT_AGG_aggregate_genotype_counts.py`, `pages/review/sv_evidence.js` | **RESOLVED 2026-05-15** — authored from shipped code into `specs_done/SPEC_sv_evidence_page.md` |

**Also missing — STATUS UPDATE 2026-05-15**:
- `SCHEMA_V2.md` / `SCHEMA.md` — **RESOLVED 2026-05-15** — authored
  as `specs_done/SCHEMA.md`. Resolves §9, §10, §13, §19, §22, §26,
  §27 + reserves §0-§30 with explicit pointers to the 26 JSON
  schemas in `registries/schemas/`. Convention locked: "SCHEMA §N"
  and "SCHEMA_V2.md §N" both refer to sections in
  `specs_done/SCHEMA.md` (V2 designation is historical; one schema
  doc).
- `HANDOFF_BATCH_3.md`, `HANDOFF_BATCH_4.md`, `HANDOFF_BATCH_5.md` —
  still missing. Likely never authored; the
  `pages/<stage>/BATCH_*_NOTES.md` files are the de-facto handoffs.

---

## What's referenced as a SPEC but lives inside another file

These are NOT missing — they exist as **sections inside other docs**:
- `SPEC_0` → contents of `specs_todo/mgl_adapter/SPEC_0_master.md`
- `SCHEMA §9 / §10 / §19 / §22` → refers to schema sections in some doc; the JSON-schema definitions are in `atlases/inversion/registries/schemas/*.schema.json` (26 schema files exist there) — the prose document doesn't appear to exist anywhere on disk
- ~~`SCHEMA_V2.md` — pages.registry mentions "cross-refs SCHEMA_V2.md §19" but no file by that name exists; the 14-axis classification schema lives in `pages/review/karyotype_tier/tier_axes.js`~~ **RESOLVED 2026-05-15** — `specs_done/SCHEMA.md` §19 carries the 14-axis prose schema (pulled from `tier_axes.js#TIER_AXES`).
- legacy-line citations (e.g. "legacy lines 36977-37050") refer to `legacy/Inversion_atlas.html` — confirmed at `/home/user/inversion-atlas/legacy/` if that dir exists (haven't checked)

---

## What's healthy

- `SPEC_band_track_extraction_and_l3_single_band_rows.md` (the master band-tracking spec) is **explicitly** the parent doc — it lists 4 child SPECs as its dependency network, and 3 of those 4 children are **missing**. So this SPEC has a known "TODO_MISSING children" structural debt.
- `SPEC_registry_v2.md` (newest) supersedes `SPEC_registry_v1.md` — both exist; v1 in `specs_todo/`, v2 in `_handoff_docs/`. Consider promoting v2 into `specs_todo/`.
- `SPEC_0_master.md` (mgl_adapter master) is a self-contained mini-library with its own HANDOFFs and READMEs — closest thing to a clean documentation tree in the repo.

---

## Recommended actions (concrete + small)

### 1. Move all SPECs into one home
Move:
- `handoff_docs/SPEC_band_track_extraction_and_l3_single_band_rows.md` → `specs_todo/`
- `_handoff_docs/SPEC_registry_v2.md` → `specs_todo/`

Result: `specs_todo/` becomes the single SPEC home.

### 2. Author the 8 missing SPECs (or mark them retired)
For each of the missing SPEC_* names referenced from code, decide:
- **Author** — write a one-page SPEC that documents what the shipped code does (esp. `SPEC_g_panel_unified_groups`, `SPEC_lines_panel_candidate_bands`, `SPEC_l2_sweep_inheritance`, `SPEC_l3_het_dosage_coloring`, `SPEC_sv_evidence_page` — all reference shipping code)
- **Retire** — remove the reference from the code/doc (esp. `SPEC_DEFERRED.md`, which is a register of deferred decisions; either start the doc, or delete the references)

### 3. Author the prose SCHEMA doc
~~Currently `pages.registry.json` cross-refs `SCHEMA_V2.md §19` / `§22` / etc. but no such file exists.~~ **RESOLVED 2026-05-15** — `specs_done/SCHEMA.md` now exists and covers §9 / §10 / §13 / §19 / §22 / §26 / §27 with a complete `§0-§30` reservation map for future schemas.

### 4. Add `specs_todo/INDEX.md`
One-line per SPEC + status (DONE / IN_PROGRESS / NOT_STARTED / RETIRED) + which pages/modules consume it. Pairs with the `ATLAS_PAGES_MAP.md` we just shipped.

---

https://claude.ai/code/session_01KN8Jkn7aaWJvu53xd3EGnx
