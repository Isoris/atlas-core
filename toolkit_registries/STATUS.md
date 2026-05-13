# toolkit_registries — readiness audit & branch state

**Scope:** snapshot of `claude/organize-toolkit-registries-kIIrU` after
13 commits of work. Tracks (a) which top-level specs are current, (b) what
has been built on this branch, (c) what is intentionally deferred.

**First written:** 2026-05-12.
**Last refreshed:** 2026-05-13 after commit `6a8e362`.

---

## 1. Branch commits (chronological)

| # | Hash | What landed |
|---|---|---|
| 1 | `77330be` | initial audit (STATUS.md v1, report-only) |
| 2 | `9fe3b9e` | `cohort_scoped` / `genome_scoped` flags in `master_config.schema.json` + `MASTER_CONFIG.md`; 41→40 structured-block count fix; `ACTIVATOR_EXTRACTOR.md`; promoted `operation_entry.schema.json` to a standalone canonical file |
| 3 | `60599b9` | STATUS.md refreshed after the above |
| 4 | `293e359` | Phase 1 contracts (no server code): `action_manifest`, `extractor_manifest`, `layer_envelope`, `action_log_entry` schemas + `PIPELINE_FLOW.md` + `ATLAS_WIRING_PROMPTS.md` |
| 5 | `072dc11` | content-hash identity: `sample_set_v1`, `analysis_result_v1`, `lib/set_algebra.py`, `REGISTRY_LOOKUP.md`. Collapses (groups × analysis × samples × intervals). |
| 6 | `dbc153d` | inventory viewer — `lib/registry_inventory.py` + `inventory/index.html` (single-page) |
| 7 | `ea5c712` | `set_registry` + `analysis_registry`: `entity_type_v1`, `set_v1`, `analysis_v1`, two TSV row schemas, `lib/registry_index.py`, `SETS_AND_ANALYSES.md` |
| 8 | `f2eb360` | inventory page tabs (Results / Sets / Analyses / Chain) + chain composer |
| 9 | `4bafbdf` | `derivation_v1` + `operation_params_v1` (separates the "thin500 is not one thing" problem) + Derivations and Params tabs |
| 10 | `275d968` | **`relatedness/`** — the pragmatic minimum: 6 flat TSV registries (sample_sets, group_sets, interval_sets, site_sets, input_values, analysis_results) + 4 contract checkers + `register_result.py`. Stdlib only. |
| 11 | `a7a35f0` | `relatedness/01_registry/analysis_modes.tsv` + `scripts/resolve.py` — the mode-driven contract resolver |
| 12 | `c5bb26e` | `relatedness/page/index.html` — single-page chain compatibility viewer |
| 13 | `6a8e362` | atlas-core 3-page dashboard: page 1 (Conversation, stub), page 2 (Action, readiness ladder), page 3 (Registries, chains). Shared top nav. |

---

## 2. Two layers, one branch

The branch landed two parallel things — both intended, both compatible:

### A. The rich, long-term registry (under `toolkit_registries/`)

Per-record JSON files with content-hash identity, set algebra, action
manifests, extractor manifests, layer envelopes, derivations, parameter
bundles, an inventory page with a chain composer. This is the design
shape for atlas-core's future runtime.

Schemas (`schemas/registry_schemas/`):

| Schema | Purpose |
|---|---|
| `species.config`, `genome.config`, `cohort.config`, `sample_master`, `group_definition`, `sample_group`, `candidate_interval`, `evidence_key`, `result_row`, `master_config` | Existing hierarchy schemas (pre-branch) |
| `operation_entry` | Activator definition (promoted from inline) |
| `action_manifest`, `extractor_manifest`, `layer_envelope`, `action_log_entry` | The action pipeline contracts |
| `sample_set_v1`, `analysis_result_v1` | Content-hashed sample sets + per-computation lookup |
| `entity_type_v1`, `set_v1`, `set_registry_row_v1` | Generalized "set of any entity type" + TSV catalogue row |
| `analysis_v1`, `analysis_registry_row_v1` | Analysis-kind catalogue + TSV row |
| `derivation_v1`, `operation_params_v1`, `derivation_registry_row_v1`, `operation_params_registry_row_v1` | "how a set was made" + reusable param bundles + TSV rows |

Docs (`toolkit_registries/`):

| File | Purpose |
|---|---|
| `HIERARCHY_SPEC.md` | species → genome → cohort → group; current upgrade target |
| `MASTER_CONFIG.md` | one config file, `cohort_scoped` / `genome_scoped` flags documented |
| `DATABASE_DESIGN.md` | 4-role mental model |
| `SPEC_DEFERRED.md` | LANTA-era reference |
| `ACTIVATOR_EXTRACTOR.md` | maps "activator/extractor" onto `source_kind` enum |
| `PIPELINE_FLOW.md` | action → runner → raw → extractor → envelope → registry → Atlas |
| `ATLAS_WIRING_PROMPTS.md` | paste-ready prompts for other atlases (inversion, unified-ancestry, …) |
| `REGISTRY_LOOKUP.md` | (groups × analysis × samples × intervals) collapse via content hash |
| `SETS_AND_ANALYSES.md` | the set/analysis registries + derivation/params decomposition |
| `STATUS.md` (this file) | branch state snapshot |

Helpers (`toolkit_registries/lib/`):

| File | Purpose |
|---|---|
| `set_algebra.py` | materialize set expressions, hash, lookup `plan()` |
| `registry_inventory.py` | scan JSONs, emit `inventory.json` (results + sets + derivations + params + analyses) |
| `registry_index.py` | scan JSONs, emit four flat TSV catalogues (set_registry, derivation_registry, operation_params_registry, analysis_registry) |

UI (`toolkit_registries/inventory/`):

| File | Purpose |
|---|---|
| `index.html` | 6-tab inventory page (Results, Sets, Derivations, Params, Analyses, Chain) |
| `example_data/registry/` | synthetic JSON-per-record demo registry |

### B. The pragmatic minimum (under `toolkit_registries/relatedness/`)

Hand-authorable flat TSV registries + checker scripts + a 3-page
dashboard. Solves the immediate ngsRelate → ngsPedigree → mendelian
contract problem with stdlib Python and no external deps. Drop-in
into a real workspace.

Six TSVs in dependency order (`relatedness/01_registry/`):

```
WHO       sample_sets.tsv
LABELS    group_sets.tsv
WHERE     interval_sets.tsv
WHICH     site_sets.tsv
WHAT-IN   input_values.tsv
WHAT-OUT  analysis_results.tsv
HOW       analysis_modes.tsv         ← the resolver's brain
```

Scripts (`relatedness/scripts/`):

| Script | What it does |
|---|---|
| `io_helpers.py` | shared TSV / BEAGLE loaders |
| `check_beagle_header_vs_samples.py` | BEAGLE column order vs sample_set |
| `check_beagle_rows_vs_sites.py` | BEAGLE row count vs site_set (+ optional row-by-row marker check) |
| `check_group_samples_vs_sample_set.py` | group_set ⊆ sample_set |
| `check_result_contract.py` | **master check** — recursive FK + input contract for a result_id |
| `register_result.py` | append a row to `analysis_results.tsv`, refuses if contract fails |
| `resolve.py` | mode-driven contract resolver: turns "ngsrelate per_chromosome LG12" into the full contract |

3-page dashboard (`relatedness/page/`):

| Page | What it does |
|---|---|
| `conversation.html` | stub for the LLM funnel (page 1) |
| `action.html` | readiness & routing dashboard — RESULT_READY / RUN_READY / SPAWNABLE / BLOCKED / MISSING per step (page 2) |
| `index.html` | chain compatibility viewer (page 3) |

---

## 3. What's done / what's deferred

### Done on this branch
- All registry contracts (rich JSON form + flat TSV form)
- Content-hash identity collapses the (groups × analyses × samples × intervals) explosion
- Mode-driven resolver (CLI + JS in the page)
- Contract checker walks 3 levels deep through the ngsRelate → ngsPedigree → mendelian chain
- 3-page dashboard (page 2 is the new piece; page 3 is the chain viewer; page 1 is documentation-only)

### Intentionally deferred
- **LLM funnel** (page 1 content). Design lives in `page/conversation.html`; out of scope per user direction.
- **Server endpoints** for the action pipeline (`POST /api/actions`, `GET /api/layers`, etc.). Defined in `PIPELINE_FLOW.md`; not implemented in `atlas_server.py` yet.
- **Per-page atlas migration** of the existing `species_scoped` master_config flags to `cohort_scoped` / `genome_scoped` — explicitly per-page per HIERARCHY_SPEC.
- **Real runners** for ngsRelate / ngsPedigree / mendelian. The scripts register and validate; you still run the binaries yourself.
- **Filter profile registry** (`filter_profile_v1`). Free-form string id for now in derivation rows.
- **Backfill helper** that walks an existing `.res/` folder and registers everything. Not built; the contract checker + register_result is enough to do it by hand for now.

### Things the user can run today

```bash
# 3-page dashboard
python3 -m http.server -d toolkit_registries/relatedness 8765
# → http://127.0.0.1:8765/page/action.html

# CLI: the master check (recursive, 3 levels deep)
cd toolkit_registries/relatedness/scripts
python3 check_result_contract.py --result mendelian_LG12_v1
#   → OVERALL: ✓ OK; READY FOR: family-QC summary tables, trio reliability flags

# CLI: the mode-driven resolver
python3 resolve.py --analysis ngsrelate --mode per_chromosome \
                   --sample-set samples_226_v1 --chromosome C_gar_LG12 --explain
#   → STATUS: ✓ OK  ready to run

# CLI: ASCII inventory of the rich registry
python3 ../../lib/registry_inventory.py --example --print

# Or the inventory page (6 tabs incl. Chain composer)
python3 -m http.server -d toolkit_registries/inventory 8000
# → http://127.0.0.1:8000/
```

---

## 4. Verification (after the latest linter touches)

```
119/119 JSON files parse OK
check_result_contract.py --result mendelian_LG12_v1   ✓ OK (3-level recursion green)
resolve.py --analysis ngsrelate --mode per_chromosome ✓ OK ready to run
3-page dashboard                                       ✓ all routes serve 200
```

No regressions.
