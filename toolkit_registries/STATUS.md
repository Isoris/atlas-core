# toolkit_registries — readiness audit & branch state

**Scope:** snapshot of `claude/organize-toolkit-registries-kIIrU` after
13 commits of work. Tracks (a) which top-level specs are current, (b) what
has been built on this branch, (c) what is intentionally deferred.

**First written:** 2026-05-12.
**Last refreshed:** 2026-05-14 at session close — every link in the
action-pipeline chain is now wired, tested, and demonstrated in a real
page in each of the 5 atlases. See §1 commits 14-29 + §5 below.

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
| 14 | _unstaged_ | **Action-pipeline server endpoints in `atlas_server.py`**: `POST /api/actions`, `GET /api/actions/{id}`, `GET /api/layers`, `GET /api/layers/{id}`. Validates manifest, imports per-atlas `dispatcher.py`, runs it on a worker thread (so HTTP callbacks resolve), writes envelopes to `<workspace>/layers/...`, appends to `<workspace>/registry/actions.log.jsonl`, indexes in `<workspace>/registry/layers.registry.json`. No new pip deps. |
| 15 | _unstaged_ | **inversion-atlas end-to-end wiring**: `run_popstats` → `fst_windows_v1`. New folders `schemas/schema_in`, `schemas/schema_out`, `runners/`, `extractors/` + `dispatcher.py` + `actions.registry.json` + `extractors.registry.json`. Runner wraps `/api/popstats/groupwise`; extractor produces `{windows, summary}`. Smoke tests green for happy + 4 negative paths. |
| 16 | _unstaged_ | **diversity/population/genome/relatedness atlases — one worked action each** (same 7-file layout). Stage = `staging` so the schema_out is loose; promote later. Smoke tests green. Actions: `import_slot` (calls the new `/api/diversity/{slot}` sidecar), `compute_ancestry_q` (wraps `/api/ancestry/groupwise_q`), `import_table`, `import_relatedness_tsv`. |
| 17 | _unstaged_ | **Page-migration helper `core/layer_api.js`** + re-export from `core/atlas_api.js`. Six client-side helpers: `listLayers`, `getLayer`, `resolveLatestLayer`, `getLayersOfType`, `submitAction`, `getActionLog`, plus `newActionId`. `tests/test_layer_api.js` covers 27 assertions via mocked fetch. `docs/examples/layer_api_demo.html` is a framework-free worked page. |
| 18 | _unstaged_ | **diversity sidecar endpoint** `server/diversity_endpoint.py` + `app.include_router(...)` in `atlas_server.py`. Five read-only JSON slots: `embedded_tables`, `texture_metrics`, `functional_burden`, `roh_gene_overlap`, `divergence_network`. |
| 19 | _unstaged_ | **`package.json`** (`"type": "module"`) so `node tests/*.js` no longer warns / fails on the ESM `import` syntax that existing tests already used. Three existing JS tests + the new one run green; two pre-existing tests still need a `WORKSPACE` env var (unchanged behaviour). |
| 20 | _unstaged_ | **server/atlas_server.py: mount `population_endpoint.py`** + 3 new population-atlas actions (`import_slot`, `import_ngsadmix_q`, plus the existing `compute_ancestry_q`). Endpoint tests: 15/15 green across diversity + population. |
| 21 | _unstaged_ | **Live round-trip integration test `server/test_actions_endpoint.py`** — 12 tests boot `atlas_server` via FastAPI TestClient against a tmp workspace with an in-test "testatlas" dispatcher. Covers happy path + atlas resolution precedence + 6 negative paths. Plus repair of pre-existing `test_file_compute_endpoints.py` (3 POST tests targeted disallowed paths) and graceful skip in `test_ld_endpoint.py` (engine_fast_ld helpers absent in this checkout). |
| 22 | _unstaged_ | **scripts/atlas_action.py** — stdlib CLI, 5 subcommands (`submit`, `log`, `list`, `get`, `new-id`). Bridges "wiring is in" → "I can run analyses from a terminal". `scripts/test_atlas_action.py` boots uvicorn on a free port and exercises every subcommand: 13/13 green. |
| 23 | _unstaged_ | **Staging → normalized worked example in relatedness-atlas**: `normalize_relatedness` action promotes a `staging_relatedness_v0` envelope into typed `ngsrelate_pairs_v1` (canonical column map: a/b/theta/KING/R/nSites/IBS0/1/2 → ind1/ind2/theta/king/rab/n_sites/ibs0/1/2 with null-tolerant coercion + summary block). Dispatcher honours `manifest.target.source_layer_id(s)` → `envelope.provenance.source_layer_ids` for lineage. The 4-line dispatcher block was then ported to all 5 atlases uniformly — sweep test confirms (20/20). |
| 24 | _unstaged_ | **Per-atlas JS client surface** for the action pipeline. relatedness's existing `shared/api_client.js` got 6 new exports (throwing pattern, matches `core/layer_api.js`). diversity / population / genome got new `shared/api_client.js` files (same throwing pattern). inversion's existing `shared/atlas_server.js` got 6 new exports following its established **fail-soft** `{ok, status, json, error}` convention. Each atlas got its own `package.json` (`type: module`) and `shared/test_api_client.js` (or equivalent) with 23 assertions of mocked-fetch coverage. |
| 25 | _unstaged_ | **relatedness-atlas `network.js` migration** — first real-page envelope-aware migration. Probes `ngsrelate_pairs_v1` envelopes; renders status badge above the SVG. Existing DEMO rendering preserved. 15-assertion smoke test. |
| 26 | _unstaged_ | **relatedness-atlas `compatibility.js` migration** — same pattern, different domain framing: ties the badge text to the "Exclude close kin" UI filter checkbox. 14-assertion smoke test. |
| 27 | _unstaged_ | **genome-atlas `assembly/page1.js` migration** — different UI pattern: activates the 8 pre-existing `[data-ga-layer]` scaffold chips by matching `staging_genome_table_v0` envelope subject substrings against the chip's `data-ga-layer` attribute. 28-assertion smoke test (happy path, multi-chip, most-recent-wins-per-subject, fail-soft, idempotency). |
| 28 | _unstaged_ | **diversity-atlas `per_sample/page1.js` migration** — list+get fan-out pattern: filters `staging_diversity_slot_v0` envelopes by `payload.slot=embedded_tables` (which requires fetching each envelope to read payload). Provenance badge with humanised byte count. 14-assertion test including partial-fetch-failure resilience. |
| 29 | _unstaged_ | **population-atlas `structure/page3.js` migration** — richest pattern yet: declarative `_SLOT_LAYER_MAPPING` table maps 6 `data-pa-slot` panel-slot mockups to 3 different layer types, with per-payload-slot filtering for population_slot envelopes and "unwired" status messaging for slots without a registered action (natora, evaladmix). 15-assertion test including idempotency. |
| 30 | _unstaged_ | **inversion-atlas `catalogue/page_overview.js` migration** — closes the loop (5/5 atlases have a migrated page). Fills the legacy empty-stub `<div id="page_overview" class="page"></div>` with a workspace-wide envelope inventory table (multi-type grouping + most-recent-per-type). Uses inversion's fail-soft return shape `{ok, status, json, error}`; surfaces `status === 503` as "subsystem not configured — start atlas_server.py with `--workspace-root`". 16-assertion test including HTML escaping. |

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
- **Action pipeline end-to-end across all 5 atlases**: server endpoints (4), per-atlas dispatchers (5), staged & normalized envelopes, lineage via `provenance.source_layer_ids`, CLI for terminal submission, JS helpers in every atlas, real-page migration in every atlas. See §1 commits 14-30 and §5 below.
- **Live integration test** that boots `atlas_server` via FastAPI TestClient against a tmp workspace with a synthetic atlas — pins the manifest validation, dispatcher loading, envelope persistence, log appending, layer indexing, atlas resolution precedence, and 6 negative paths.
- **One worked staging→normalized promotion** (`normalize_relatedness` → `ngsrelate_pairs_v1`) — recipe is in place; the other 4 atlases inherit the dispatcher's `source_layer_ids` passthrough and can adopt it whenever a staging schema firms up.

### Intentionally deferred
- **LLM funnel** (page 1 content). Design lives in `page/conversation.html`; out of scope per user direction.
- **Page rendering using envelope payload data.** All 5 migrated pages currently *advertise* envelope availability; they don't yet *render with* the envelope's payload (i.e., compatibility.js's close-kin filter still consults DEMO data even when an `ngsrelate_pairs_v1` envelope exists). Switching from advertise → render is a domain decision per page (e.g., what theta threshold = "close kin"?).
- **Per-page atlas migration** of the existing `species_scoped` master_config flags to `cohort_scoped` / `genome_scoped` — explicitly per-page per HIERARCHY_SPEC.
- **Normalized payload schemas for the four staging actions in 4 atlases.** Only relatedness has shipped `normalize_*` (→ `ngsrelate_pairs_v1`). diversity / population / genome / inversion ship their first actions as `staging_*_v0` (`additionalProperties: true`). The dispatcher pattern is proven; adding `normalize_diversity_slot`, `normalize_population_slot`, etc. is mechanical once the renderers commit to columns/units.
- **Real runners** for ngsRelate / ngsPedigree / mendelian engines. The action-pipeline scripts register and validate envelope outputs; you still run the binaries yourself and use `atlas_action submit import_relatedness_tsv` to capture the result.
- **Shared `data-source-badge` helper.** Three of the migrations use a very similar inline-badge pattern; the abstraction is borderline-ready for extraction into per-atlas `shared/data_source_badge.js`. Deferred until a 4th migration uses the same pattern (current 5 split: 3 badge / 1 chip-activation / 1 inventory-table).
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

### Action-pipeline wiring (commits 14–30) — full footprint

The umbrella `bash atlas-core/scripts/_run_all_tests.sh` ran all suites
green at session close. The script adds `$HOME/mambaforge/bin` to PATH
when `python3` lacks fastapi (needed for non-login bash invocations).

```
--- atlas-core server                49 tests, 1 skipped
--- atlas-core CLI                   13 tests
--- atlas-core JS layer_api          27 assertions
--- inversion-atlas (api surface)    23 assertions
--- diversity-atlas (api surface)    23 assertions
--- population-atlas (api surface)   23 assertions
--- genome-atlas (api surface)       23 assertions
--- relatedness-atlas (api surface)  23 assertions
--- relatedness network page         15 assertions
--- relatedness compatibility page   14 assertions
--- genome page1 chips               28 assertions
--- diversity per_sample/page1       14 assertions
--- population structure/page3       15 assertions
--- inversion page_overview          16 assertions
                                     ─────
                                    ~306 green across 14 test suites
```

The one skip is `server/test_ld_endpoint.py` — its sibling `test_fast_ld`
helper module wasn't relocated with it during the turn-145 server-unify;
the guard raises `unittest.SkipTest` at module load so discovery doesn't
break the rest of the suite.

### What the user can run today (action-pipeline)

```bash
# 1. Boot the server pointing at the assembled workspace
cd atlas-core/server
python3 atlas_server.py --workspace-root <assembled-workspace> \
                        --project-root  <assembled-workspace> \
                        --host 127.0.0.1 --port 8000

# 2. Submit an action from the terminal — no browser needed
python3 atlas-core/scripts/atlas_action.py submit \
        -f manifest.json --atlas inversion --fetch

# 3. Browse envelopes via the umbrella CLI
python3 atlas-core/scripts/atlas_action.py list --layer-type fst_windows
python3 atlas-core/scripts/atlas_action.py get  <layer_id> --payload-only
python3 atlas-core/scripts/atlas_action.py log  <action_id>

# 4. Or open any atlas's UI — every migrated page advertises the
#    envelopes it can see, fail-soft when the server's offline:
#       inversion   page_overview   (workspace-wide inventory table)
#       relatedness network         (status badge for ngsrelate_pairs)
#       relatedness compatibility   (badge tied to close-kin filter)
#       diversity   per_sample/page1 (provenance badge for embedded_tables)
#       population  structure/page3  (per-panel-slot status, 6 panels)
#       genome      assembly/page1   (8 scaffold chips activated by subject)

# 5. Run the full test umbrella anytime
bash atlas-core/scripts/_run_all_tests.sh
```

No regressions.

---

## 5. Action-pipeline architecture — quick map

```
USER
  │
  ▼ atlas_action.py submit -f m.json --atlas X    (commits 17, 22)
  │
  ▼ POST /api/actions ?atlas=X                     (commit 14)
  │   ├ manifest schema validation
  │   ├ append queued + running to actions.log.jsonl
  │   └ asyncio.to_thread(dispatch_action, …)
  │
  ▼ <workspace>/atlases/X/registries/dispatcher.py (commits 15, 16, 23)
  │   ├ schema_in/<type>_v1.schema.json (manifest contract)
  │   ├ runners/<runner>.py (raw output)
  │   └ extractors/<extractor>.py (typed payload)
  │
  ▼ Returned envelopes
  │   ├ provenance.action_id (always)
  │   └ provenance.source_layer_ids (when manifest names sources, commit 23)
  │
  ▼ Server persists + indexes                      (commit 14)
  │   ├ <workspace>/layers/<layer_type>/<dataset_id>/<layer_id>.json
  │   └ <workspace>/registry/layers.registry.json
  │
  ▼ append success/error to actions.log.jsonl
  │
  ▼ HTTP 200 { ok, action_id, atlas_id, produced_layers }


BROWSER PAGE
  │
  ▼ import { listLayers, getLayer, resolveLatestLayer }
  │       from '../../shared/api_client.js'        (commit 24, all 5 atlases)
  │       (inversion uses shared/atlas_server.js + fail-soft return shape)
  │
  ▼ Each migrated page detects envelopes and shows them   (commits 25-30)
  │   relatedness/network    — badge above SVG
  │   relatedness/compat     — badge tied to close-kin UI
  │   genome/page1           — activate 8 scaffold chips
  │   diversity/per_sample   — provenance line with bytes
  │   population/page3       — 6 panel-slots × 3 layer types
  │   inversion/page_overview — workspace-wide inventory table
```

Recipe for migrating any new page (in any atlas):

1. `import { resolveLatestLayer }` (or `listLayers`/`getLayer`) from the
   atlas's `shared/api_client.js` (or `shared/atlas_server.js` for
   inversion).
2. In `mount()`, call the helper asynchronously with `.catch()` for fail-
   soft behaviour.
3. Add a DOM slot (`<div id="…DataSource">` or `data-*-slot` attributes).
4. Copy a sibling page's `test_*.js` and swap the imports + expected
   strings (~30 lines).
5. Append the test command to `atlas-core/scripts/_run_all_tests.sh`.
