# atlas-core

Registry + dashboard + adapter scaffold for the **MS_Inversions** *Clarias gariepinus* manuscript (Nature Communications-tier, LG01 × LG28 pair-relation + LG27 cross-species bounded inversion).

Eight atlases, ~95 modules, ~120 analysis modes, ~150 layers, ~30 manuscript chunks — all declared as JSONL rows, surfaced through 13 browser pages, audited end-to-end on every commit.

---

## What this is (and isn't)

**It is** a registry of analyses, layers, modules, and manuscript chunks — plus a thin dashboard that surfaces what's registered, what's missing, what's runnable, and what's ready to write up.

**It isn't** a workflow engine. The dispatcher writes `action_manifest_v1` JSONs to `02_queue/`; an external runner picks them up. Pages never execute analyses. The §refusals layer is enforced everywhere:

> librarian → manager → dispatcher → chain audit → conductor → pages
> connect ≠ resolve ≠ run ≠ render

---

## Quick tour

### Pages (every page reads JSONL; the registry is the source of truth)

| # | page | reads | for |
|---|---|---|---|
| 1 | Conversation       | (LLM funnel) | natural-language → registered question |
| 2 | Action             | analysis_registry + module_registry + scope | "what should I run next?" + chain readiness |
| 3 | Registries         | all `01_registry/*.jsonl` | raw inspection + previews |
| 4 | Catalogue          | module_registry + analysis_modes + atlases | per-atlas module + analysis-mode card view |
| 5 | Layers             | layer_registry + analysis_results | per-layer view |
| 6 | Candidate review   | candidates + chain_evidence | per-candidate evidence |
| 7 | Graph builder      | layer_registry + edge_rules | declarative layer-graph editor |
| 8 | Readiness          | questions + estimands + products | per-question readiness |
| 9 | Layer Connector    | layer_registry + connection_map | DAG visualizer |
| 10 | Workspace Health  | atlases + every roll-up | one-glance KPI |
| 11 | Queue             | `02_queue/index.json` | dispatched action manifests |
| 12 | **Manuscript**    | manuscript_chunks + references | compose a draft from registered chunks |
| 13 | **Adapters**      | analysis/<id>/*.json | per-analysis in/out contract viewer |

### The eight atlases

| atlas | what it owns | status |
|---|---|---|
| `inversion_atlas`     | LG01 × LG28 pair-relation, the manuscript stress test | experimental |
| `cross_species_atlas` | comparative breakpoints across 18 catfish genomes — LG27 bounded inversion headline | experimental |
| `popstats_atlas`      | windowed FST / dxy / piN / piS between karyotype groups | experimental |
| `evolution_atlas`     | arrangement origin, selection, MSMC demography | experimental |
| `meiosis_atlas`       | CO / DCO / coincidence-of-coincidence + interchromosomal effects | experimental |
| `relatedness_atlas`   | ngsRelate → ngsPedigree → Mendelian QC + HPP burden | experimental |
| `diversity_atlas`     | θπ / θW / Hp / individual heterozygosity / ROH | experimental |
| `genome_atlas`        | F1 hybrid assembly-paper deliverables (different cohort) | experimental |
| `atlas_core`          | infrastructure (librarian / manager / dispatcher / conductor) | active |

### The five tiers

1. **Librarian** — resolves layer status from `analysis_results.jsonl` + filesystem. Pure read.
2. **Manager** — classifies product readiness + estimability per question.
3. **Dispatcher** — writes `action_manifest_v1` to `02_queue/`. Never executes.
4. **Chain audit** — per-chain "one step away vs blocked" verdict surfaced on page 2.
5. **Conductor** *(DYNAMIC_PANELS_SPEC §13 vertical slice live)* — composes which panels render in which slots from `panels.jsonl` + `spawn_rules.jsonl`.

---

## Cohort discipline (read first if touching biology)

Three *Clarias gariepinus* cohorts, **never** conflate:

1. **F1 hybrid** (C. gariepinus × C. macrocephalus) — assembly paper only. Owned by `genome_atlas`.
2. **226-sample pure C. gariepinus hatchery** — MS_Inversions manuscript. Owned by `inversion_atlas`, `relatedness_atlas`, `meiosis_atlas`, `popstats_atlas`, `diversity_atlas`.
3. **Pure C. macrocephalus wild** — future paper. Not owned yet.

Cross-atlas data use goes through `depends_on_atlases` (declarative). Coordinates can cross cohort boundaries; **claims cannot**.

---

## Repo layout

```
toolkit_registries/
├── relatedness/01_registry/         the canonical JSONL pool
│   ├── atlases.jsonl                11 atlas descriptors
│   ├── analysis_registry.jsonl      117+ analysis_ids + chains
│   ├── analysis_modes.jsonl         120+ analysis × mode rows
│   ├── module_registry.jsonl        95 biomod modules (canonical biomod_status enum)
│   ├── layer_registry.jsonl         146+ layers (file inputs + analysis_result outputs)
│   ├── products.jsonl               23 research products
│   ├── questions.jsonl              6 research questions
│   ├── estimands.jsonl              8 estimands with preconditions
│   ├── manuscript_chunks.jsonl      30 chunks across 7 atlases
│   ├── references.jsonl             18 references with DOIs
│   ├── panels.jsonl                 8 registered UI panels
│   ├── spawn_rules.jsonl            conductor spawn rules
│   └── connection_map.json          derived (~304 nodes / ~237 edges, regen on every commit)
├── relatedness/lib/                 librarian + manager + dispatcher + chain audit
├── relatedness/page/                13 browser pages + shared chrome (loader, search,
│                                     filters, scope, doc, previews, conductor, registry-cache)
├── relatedness/scripts/             check_analysis_registry, sync_biomod_status, tsv_from_jsonl, …
├── analysis/                        adapter folders (one per atlas-side analysis)
│   ├── cross_species_breakpoint_detection/
│   ├── inversion_pair_incompatibility/
│   ├── iv_candidate_promoter/
│   ├── karyotype_auto_caller/
│   └── karyotype_polarizer/         each 6/6: adapter_atlas.js + compute.js +
│                                     schema_in.json + schema_out.json +
│                                     example_input.json + example_output.json
├── scripts/                         smoke_all_stack.py + render_manuscript.py
└── *.md                             frozen specs (DYNAMIC_PANELS, DISPATCHER, MANAGER,
                                     LAYER_GRAPH_BUILDER, ADAPTER_CONTRACT,
                                     CROSS_SPECIES_BREAKPOINTS, …)
```

---

## Smoke / audit

Run before every commit:

```bash
python3 -m toolkit_registries.scripts.smoke_all_stack       # 13/13 in ~650ms
python3 -m toolkit_registries.relatedness.lib.build_connection_map  # 304 nodes / 237 edges / 0 warnings
python3 toolkit_registries/relatedness/scripts/check_analysis_registry.py  # FK + enum check
```

Then `python3 -m toolkit_registries.scripts.render_manuscript` regenerates `MANUSCRIPT_DRAFT_v0.md` from the chunk registry (the same path page 12's "Download .md" follows in-browser).

---

## How to add a new atlas

1. Add a row to `01_registry/atlases.jsonl` (`atlas_id`, `label`, `color`, `icon`, `status: experimental`).
2. Add the atlas's modules to `module_registry.jsonl` with `atlas: "<atlas_id>"`, canonical `biomod_status` ∈ {stable, experimental, planned, deprecated, contract_only}.
3. Add the atlas's analyses to `analysis_registry.jsonl` and their modes to `analysis_modes.jsonl`.
4. Add the layers each analysis produces to `layer_registry.jsonl`.
5. If the atlas has a deliverable, add manuscript chunks to `manuscript_chunks.jsonl` and any new refs to `references.jsonl`.
6. Run smoke. Audit. Push.

The Catalogue (page 4) picks up the new atlas via the badge automatically; page 13 surfaces any adapter folders under `analysis/<analysis_id>/`; the conductor's `atlas_summary_card` recounts on next reload.

---

## Spec docs (frozen contracts)

| spec | what it pins |
|---|---|
| `DISPATCHER_SPEC.md`           | manifest queue + §refusals (no execution from dispatcher) |
| `MANAGER_SPEC.md`              | product readiness + estimability classifier |
| `LAYER_GRAPH_BUILDER_SPEC.md`  | 5 node types, 9 librarian states, edge_rules.tsv |
| `ADAPTER_CONTRACT.md`          | compute.js vs adapter_atlas.js separation |
| `DYNAMIC_PANELS_SPEC.md`       | conductor / panels / spawn rules / fluidity / graphs / events / per-analysis panel requirements / research plans (v0.2, 1262 lines) |
| `CROSS_SPECIES_BREAKPOINTS_WORKFLOW.md` | the comparative chain + cohort discipline |
| `PIPELINE_FLOW.md`             | the four action-pipeline endpoints |

---

## Where to start reading code

- A new contributor: `MERGE_PLAN.md` lists the merge order of the stacked PRs.
- A biologist: `MANUSCRIPT_DRAFT_v0.md` shows the rendered output of the chunks; `CROSS_SPECIES_BREAKPOINTS_WORKFLOW.md` for the LG27 story.
- A dashboard user: open `toolkit_registries/relatedness/page/index.html` in any browser served from the repo root.
- A spec reader: `DYNAMIC_PANELS_SPEC.md` is the longest and most prescriptive.

---

_atlas-core is the registry that owns the manuscript's metadata so the manuscript can be assembled, not just written. Every paragraph traces back to a chunk, every chunk to an adapter, every adapter to a module, every module to an atlas._
