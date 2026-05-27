# atlas-core

Shell + registry engine for a family of browser-based genomics atlases targeting
the catfish (Cgar / Cmac) workspace. Loads a per-atlas manifest, registers each
atlas's layers / operations / pages with a central registry, and renders the
shell chrome (topbar atlas switcher, stage pills, page tabs, status badges).

This repo ships only the **core**: the boot loader, the registry engine, the
router, the unified server, and a minimal `core` atlas with 7 dashboard pages
(Conversation / Action / Registries / Catalogue / Inventory / SPECs / System
Health). The actual data atlases live in **sibling repos on Desktop**, picked up
by [`build/assemble.sh`](build/assemble.sh) and copied into a single
`atlas-workspace/` tree at build time.

---

## The 11 atlases

| Atlas | Repo | Role |
|---|---|---|
| `core` | atlas-core (bundled) | Registry dashboard + system health |
| `inversion` | inversion-atlas | Per-candidate inversion detection + classification (22 pages) |
| `diversity` | diversity-atlas | Per-sample diversity / ROH / theta_pi (10 pages) |
| `heterozygosity` | heterozygosity-atlas | Dedicated H surfaces (6 pages, Phase 1c split from diversity) |
| `population` | population-atlas | Cohort identity — families / kinship / breeding (9 pages) |
| `popstats` | popstats-atlas | Group-wise stat compute engine (3 pages, Phase 1a split from inversion) |
| `pods` | pods-atlas | PODs simulation framework — null distributions (4 pages, Phase 1d) |
| `relatedness` | relatedness-atlas | Pedigree / breeding / Mendelian distortion (9 pages) |
| `meiosis` | meiosis-atlas | CO / NCO / coincidence / interference (11 pages) |
| `cross-species` | cross-species-atlas | 18-genome breakpoint atlas (5 pages, Phase 1a split from inversion) |
| `evolution` | evolution-atlas | Per-candidate age + polarity + archaeology (9 pages, Phase 1a split from inversion) |
| `genome` | genome-atlas | Assembly + annotation + within-Cgar comparative (11 pages) |

Total: 12 atlases registered (counting `core`), ~110 pages, 155 declared layers,
30 server operations.

---

## Quick start (WSL)

```bash
# One-time: copy + edit atlas.config to point at your local repo paths
cp atlas-core/build/atlas.config.example atlas-core/build/atlas.config

# Assemble — copies every atlas repo into atlas-workspace/
bash atlas-core/build/assemble.sh

# Start the unified server (Starlette + uvicorn)
bash atlas-workspace/start.sh
```

Then open the URL the server prints. Cycle atlases via the topbar dropdown (sorted
alphabetically by display name).

---

## Cross-atlas data sharing

Each atlas's `manifest.json` declares a `cross_atlas` block listing what it imports
from other atlases and what it exports. Pages call:

```js
const cands = await registry.resolve('inversion.candidates_v1');
```

The dotted prefix is stripped at lookup time. The producer atlas's
`layers.registry.json` is the single source of truth for what's actually backed.

The master producer/consumer map lives in
[`cohorts.registry.json`](cohorts.registry.json) and is visualized live by the
`core` atlas's **System Health** page (Atlas Core → 7. System Health).

See [`docs/SPEC_cross_atlas_adapters.md`](docs/SPEC_cross_atlas_adapters.md) for the
full convention.

---

## Lint

Before committing any change that touches a `manifest.json`, registry file, or
`cross_atlas` block:

```bash
python atlas-core/build/_lint_atlases.py
```

Checks JSON syntax, page file existence, cross-atlas import resolution, and
`cohorts.registry` consistency across all 12 atlases. Target: zero warnings.

---

## Repo layout

```
atlas-core/
├── core/                       Engine: registry, router, state, discovery
│   ├── registry_core.js        register_atlas, resolve(), dotted-namespace lookup
│   ├── atlas_router.js         Topbar + stage pills + tab navigation
│   ├── atlas_state.js          Per-atlas state singletons
│   ├── atlas_discovery.js      Reads atlases/_index.json at boot
│   ├── shell_chrome.js         JS scripts badge, theme toggle, folder buttons
│   ├── mode_b_badge.js         Data-source probe + comparator badge
│   └── cache_store.js          Hot/warm tier cache
├── atlases/core/               The "core" atlas itself (7 dashboard pages)
├── server/                     Unified Starlette server (atlas_server.py)
├── docs/                       SPECs (architecture, registry, cohorts, adapters)
├── build/
│   ├── assemble.sh             Picks up sibling atlas repos + builds workspace
│   ├── atlas.config            (site-local) repo paths
│   └── _lint_atlases.py        Static lint pass across all manifests
├── css/                        Shell-level styles (tokens, base, badges, shell)
├── master_config.yaml          (site-local) named root paths for the data tree
├── cohorts.registry.json       Master producer/consumer index
├── toolkit_registries/         Per-atlas registry + manuscript work tree (see below)
└── index.html                  Shell bootstrap
```

---

## Manuscript work area (`toolkit_registries/`)

Companion to the shell engine above. `toolkit_registries/` is the JSONL-backed
registry + audit + manuscript-composition tree the `relatedness` atlas uses for
the **MS_Inversions** *Clarias gariepinus* manuscript (Nature Communications-tier;
LG01 × LG28 pair-relation + LG27 cross-species bounded inversion). It is a thin
dashboard that surfaces what's registered, what's missing, what's runnable, and
what's ready to write up — not a workflow engine. The dispatcher writes
`action_manifest_v1` JSONs to `02_queue/`; an external runner picks them up.

```
librarian → manager → dispatcher → chain audit → conductor → pages
connect ≠ resolve ≠ run ≠ render
```

Five tiers + a bridge tier:

1. **Librarian** — resolves layer status from `analysis_results.jsonl` + filesystem. Pure read.
2. **Manager** — classifies product readiness + estimability per question.
3. **Dispatcher** — writes `action_manifest_v1` to `02_queue/`. Never executes.
4. **Chain audit** — per-chain "one step away vs blocked" verdict.
5. **Conductor** *(DYNAMIC_PANELS_SPEC §13)* — composes which panels render in which slots from `panels.jsonl` + `spawn_rules.jsonl`.
6. **Bridge** *(BRIDGE_SPEC v0)* — direct HTTP wrappers around 10 external DBs (InterPro / UniProt / NCBI / PDB / UCSC / UniBind / STRING / Reactome / PubMed / QuickGO). No LLM in the call path.

Subtree layout:

```
toolkit_registries/
├── relatedness/01_registry/         the canonical JSONL pool
│   ├── atlases.jsonl                atlas descriptors
│   ├── analysis_registry.jsonl      analysis_ids + chains
│   ├── analysis_modes.jsonl         analysis × mode rows
│   ├── module_registry.jsonl        biomod modules (canonical biomod_status enum)
│   ├── layer_registry.jsonl         layers (file inputs + analysis_result outputs)
│   ├── products.jsonl / questions.jsonl / estimands.jsonl
│   ├── manuscript_chunks.jsonl + references.jsonl
│   ├── panels.jsonl + spawn_rules.jsonl + pages.jsonl
│   ├── external_databases.jsonl     bridge tier
│   └── connection_map.json          derived; regen on every commit
├── relatedness/lib/                 librarian + manager + dispatcher + chain audit + bridge_client
├── relatedness/page/                browser pages + shared chrome (loader, search,
│                                     filters, scope, doc, previews, conductor, registry-cache)
├── relatedness/scripts/             check_* validators (panels, plans, chunks,
│                                     analysis_registry, external_databases)
├── analysis/                        adapter folders (one per atlas-side analysis,
│                                     each 6/6: adapter_atlas.js + compute.js +
│                                     schema_in/out.json + example_in/out.json)
├── bridge/<db>/                     10 external-DB adapters (endpoints.json + LICENSE_NOTICE.md)
├── scripts/smoke_all_stack.py       21/21 audit pass
└── *.md                             frozen specs (ADDON_SPEC, DYNAMIC_PANELS_SPEC,
                                     DISPATCHER_SPEC, MANAGER_SPEC, BRIDGE_SPEC,
                                     LAYER_GRAPH_BUILDER_SPEC, …)
```

Cohort discipline (read first if touching biology): three *Clarias gariepinus*
cohorts that **never** conflate — F1 hybrid (assembly paper), 226-sample pure
*C. gariepinus* hatchery (MS_Inversions), pure *C. macrocephalus* wild (future
paper). Coordinates can cross cohort boundaries; **claims cannot**.

### Smoke / audit (toolkit_registries)

```bash
python3 -m toolkit_registries.scripts.smoke_all_stack       # 21/21
python3 -m toolkit_registries.relatedness.lib.build_connection_map
```

### Key specs (toolkit_registries)

| spec | what it pins |
|---|---|
| `ADDON_SPEC.md`                | the 6 addon kinds + panel-kind catalogue + data_source kinds + spawn `when` keys |
| `DISPATCHER_SPEC.md`           | manifest queue + §refusals (no execution from dispatcher) |
| `MANAGER_SPEC.md`              | product readiness + estimability classifier |
| `LAYER_GRAPH_BUILDER_SPEC.md`  | 5 node types, 9 librarian states, edge_rules.tsv |
| `ADAPTER_CONTRACT.md`          | compute.js vs adapter_atlas.js separation |
| `DYNAMIC_PANELS_SPEC.md`       | conductor / panels / spawn rules / fluidity / per-analysis panel requirements |
| `BRIDGE_SPEC.md` + `BRIDGE_USAGE.md` | the external-DB tier (10 adapters, no LLM in the call path) |
| `CROSS_SPECIES_BREAKPOINTS_WORKFLOW.md` | the comparative chain + cohort discipline |

---

## Key docs

- [`docs/SPEC_registry_v1.md`](docs/SPEC_registry_v1.md) — resolve / register_atlas / conflict resolution
- [`docs/SPEC_cohorts_v1.md`](docs/SPEC_cohorts_v1.md) — cohort model
- [`docs/SPEC_cross_atlas_adapters.md`](docs/SPEC_cross_atlas_adapters.md) — cross-atlas imports / exports
- [`docs/SPEC_atlas_adapter_cookbook.md`](docs/SPEC_atlas_adapter_cookbook.md) — recipes
- [`docs/SPEC_mode_b_pattern.md`](docs/SPEC_mode_b_pattern.md) — data-source probe pattern
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — overall architecture
- [`README_PAIRING.md`](README_PAIRING.md) — how atlas / analysis-side repos pair up
