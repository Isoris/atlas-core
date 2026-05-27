# SPEC — `workflows.registry.json` v1

**Status**: proposal. Authored 2026-05-23 in `inversion-atlas/docs/atlas-core-proposals/`, intended for `atlas-core/docs/SPEC_workflows_v1.md`.

**Companion files**:
- Schema: `schemas/workflows.schema.json`
- Reference impl: `reference_impl/workflows_registry.js`
- Tests: `tests/workflows_registry.test.js`

**Open question (called out for review)**: should `workflows.registry.json` sit per-atlas (proposed) or in atlas-core as a global registry that all atlases contribute to? Per-atlas mirrors the existing 5 registries pattern; global would centralise cross-atlas workflow visibility. **Proposed: per-atlas**, with a global aggregator view assembled at startup by atlas-core (read-only).

---

## 1. Problem

Atlases today can declare:
- `layers.registry.json` — data layers they own (one URL per layer)
- `files.registry.json` — file paths
- `operations.registry.json` — registry-side operations
- `pages.registry.json` — page declarations
- `slots.registry.json` — state slots

This is enough for atlases whose data is **one-file-per-layer, produced offline by a single script, manually copied into `data/`**. It is *not* enough for the comparative-genomics workflows the migration plan §2 describes, where:

- A workflow is **multi-stage** (BP_ATLAS has 6 stages: BP1 wfmash → BP2 events → BP3 zones → BP3c reciprocity → BP4 population overlap → BP5 figures → BP6 joint classification).
- A single stage produces a **directory tree** of artifacts, not one file.
- The workflow runs **two ways**: laptop sequential (`run_bp_atlas_LAPTOP.sh`, hours) and SLURM parallel (`SLURM_run_bp_atlas_PARALLEL.sh`, hours on a cluster).
- The workflow's outputs are **content-addressed by knob_hash** so the catalogue carries its own provenance.
- The workflow's outputs are read by **multiple atlases** (the cross-species atlas reads them natively; the inversion atlas reads them for the deferred BP4 hatchery-join step; the evolution atlas reads them for polarisation evidence).

Without a workflows registry, each atlas re-discovers these outputs by file-system globbing or hard-coded paths. There is no machine-readable answer to "which workflow produced this file?", "when did it last successfully run?", "what version of the producer-side code emitted these artifacts?", "is this catalogue current relative to its inputs?".

## 2. Design goals

1. **Each atlas declares its own workflows** (per-atlas registry).
2. **Each workflow declares its declared outputs** as a list of layer ids that other parts of the atlas (or other atlases) can consume.
3. **Each workflow carries its runners** (`laptop`, `slurm`, `cloud`, `local_test`) so the atlas chrome can surface a "rerun this workflow" affordance without each atlas inventing one.
4. **Each workflow stamps a knob_hash on its outputs** so atlases reading those outputs can detect staleness.
5. **No biology in the schema.** Comparative-genomics terms (`wfmash`, `BUSCO`, `breakpoint`) appear in atlas-side workflow entries, never in atlas-core.

## 3. File location + shape

Per atlas: `atlases/<atlas_id>/registries/data/workflows.registry.json`.

```jsonc
{
  "$schema": "../../../../core/schemas/workflows.schema.json",
  "atlas_id": "cross-species",
  "version": "1.0",
  "workflows": [
    {
      "workflow_id": "bp_atlas_pipeline",
      "label": "BP_ATLAS — cross-species breakpoints (Cgar/Cmac + 18 species)",
      "description": "Two-pass wfmash + event extraction + zone clustering + both-anchor reciprocity. Produces results_bpatlas/ tree. See engines/producers/bp_atlas/scripts/.",
      "version": "1.0",
      "knob_schema_ref": "engines/producers/bp_atlas/config/knobs.schema.json",
      "default_knob_hash": "auto",        // 'auto' = derive from knob_schema_ref defaults
      "stages": [
        {
          "stage_id": "BP1",
          "label": "pairwise wfmash (two-pass)",
          "script": "engines/producers/bp_atlas/scripts/STEP_BP1_pairwise_wfmash.sh",
          "produces": ["bp_atlas_passA_paf_v1", "bp_atlas_passB_paf_v1"],
          "consumes": ["haplotype_manifest_v1"],
          "estimated_runtime_min": 4320,    // 72 h on laptop, focal-only
          "estimated_ram_gb": 5
        },
        { "stage_id": "BP2", "script": "engines/producers/bp_atlas/scripts/STEP_BP2_call_breakpoints.py", "produces": ["bp_atlas_events_v1"], "consumes": ["bp_atlas_passA_paf_v1"], "estimated_runtime_min": 30 },
        { "stage_id": "BP3", "script": "engines/producers/bp_atlas/scripts/STEP_BP3_cluster_zones.py", "produces": ["bp_atlas_zones_v1"], "consumes": ["bp_atlas_events_v1", "bp_atlas_passB_paf_v1"], "estimated_runtime_min": 10 },
        { "stage_id": "BP3c", "script": "engines/producers/bp_atlas/scripts/STEP_BP3c_reciprocity.py", "produces": ["bp_atlas_reciprocity_v1"], "consumes": ["bp_atlas_zones_v1"], "estimated_runtime_min": 5 },
        { "stage_id": "BP5", "script": "engines/producers/bp_atlas/scripts/STEP_BP5_prep_atlas_data.py", "produces": ["bp_atlas_arcs_v1", "atlas_data_v1"], "consumes": ["bp_atlas_zones_v1"], "estimated_runtime_min": 5 },
        { "stage_id": "BP6", "script": "engines/producers/bp_atlas/scripts/STEP_BP6_joint_classify.py", "produces": ["joint_candidates_v1"], "consumes": ["bp_atlas_zones_v1", "bp_atlas_reciprocity_v1"], "estimated_runtime_min": 5 }
      ],
      "runners": [
        { "runner_id": "laptop", "script": "engines/producers/bp_atlas/runners/run_bp_atlas_LAPTOP.sh", "preset": "focal_only_2cpu_skiplargetargets" },
        { "runner_id": "slurm", "script": "engines/producers/bp_atlas/runners/SLURM_run_bp_atlas_PARALLEL.sh", "preset": "all_pairs_80cpu_200gb" }
      ],
      "post_run_chain": [
        { "step": "fold_into_clusters", "script": "engines/producers/bp_atlas/runners/run_fold_into_clusters_LAPTOP.sh" }
      ],
      "outputs_root": "data/breakpoints/results_bpatlas/",
      "status_file": "data/breakpoints/results_bpatlas/_status.json",
      "cohort_id": "f1_hybrid_cga_cma",
      "reference_id": "fClaHyb_Gar_LG"
    }
  ]
}
```

## 4. Schema overview (full schema in `workflows.schema.json`)

A workflow has:

- **identity**: `workflow_id` (unique within atlas), `label`, `description`, `version`, `cohort_id`, `reference_id`
- **provenance**: `knob_schema_ref`, `default_knob_hash`
- **structure**: an ordered list of `stages`, each with `stage_id`, `script` (relative to atlas root), `produces` (layer ids), `consumes` (layer ids), `estimated_runtime_min`, `estimated_ram_gb`
- **drivers**: one or more `runners` (each `runner_id` + `script` + optional `preset`)
- **post-run**: optional `post_run_chain` of follow-up scripts
- **outputs**: `outputs_root` directory path; `status_file` JSON path

A workflow's *produced layers* must each be declared in the atlas's `layers.registry.json`. A workflow's *consumed layers* may be declared in this atlas's `layers.registry.json` OR another atlas's (in which case the cross-atlas import resolver enforces the read).

## 5. The status file

Every workflow writes a `status.json` to its `status_file` path at the end of every (successful or failed) run. Shape:

```jsonc
{
  "workflow_id": "bp_atlas_pipeline",
  "started_at": "2026-05-22T10:14:33Z",
  "finished_at": "2026-05-22T14:01:12Z",
  "runner_id": "laptop",
  "knob_hash": "a3b7c9d2",         // SHA1 prefix of the knob set used
  "stages_completed": ["BP1", "BP2", "BP3", "BP3c", "BP5", "BP6"],
  "stages_failed": [],
  "outputs": {
    "bp_atlas_zones_v1": {
      "n_records": 28,
      "size_bytes": 12480,
      "modified_at": "2026-05-22T13:55:01Z"
    },
    "bp_atlas_reciprocity_v1": { "n_records": 11, "size_bytes": 4612, "modified_at": "2026-05-22T13:58:14Z" }
  },
  "host": "MacBook-Pro.local",
  "git_commit": "a1b2c3d4",
  "notes": "focal_only=1; skip_targets=Ngra,Plin,Capus"
}
```

Atlas chrome reads `status.json` to surface:
- "Last successful run: 14:01 today (3h47m)" badge
- "Outputs current: ✓" / "Outputs stale (inputs changed since last run)" badge
- "Rerun" button that calls the appropriate runner

The chrome's rerun affordance is a **follow-up UI surface** (out of scope for this SPEC); the registry data is what enables it.

## 6. Validation rules

The reference implementation validates:

1. Every `workflow_id` is unique within the atlas.
2. Every `produces` layer id appears in the atlas's `layers.registry.json`.
3. Every `consumes` layer id either appears in the atlas's `layers.registry.json` OR exists in another atlas's registry that's been declared via `cross_atlas_imports`.
4. Every stage's `script` path resolves to an existing file under the atlas root.
5. Every `runner.script` path resolves.
6. `cohort_id` must exist in the global `cohorts.registry.json` (cross-validation against SPEC_cohorts_v1).
7. Stages form a DAG (no cycles in `consumes` ↔ `produces`).
8. Stage ordering follows the DAG topological order (earlier stages cannot consume later stages' outputs).
9. `outputs_root` directory must be writable by the runner (existence checked at run time, not validation time).

Validation failures are loud — atlas refuses to mount until they're fixed.

## 7. API surface (the reference implementation exports)

```js
// workflows_registry.js

import { loadWorkflowsRegistry, validateWorkflowsRegistry,
         getWorkflow, listWorkflows, getStatusForWorkflow,
         isWorkflowOutputStale } from 'core/workflows_registry.js';

// At atlas mount:
const registry = await loadWorkflowsRegistry(atlasRoot);
const errors = validateWorkflowsRegistry(registry, layersRegistry, cohortsRegistry);
if (errors.length) throw new RegistryError(errors);

// At runtime:
const wf = getWorkflow(registry, 'bp_atlas_pipeline');
const status = await getStatusForWorkflow(atlasRoot, wf);
const stale = await isWorkflowOutputStale(atlasRoot, wf, status);

// For the chrome UI:
const all = listWorkflows(registry);  // → array of {workflow_id, label, status_summary}
```

## 8. Interaction with the existing 5 registries

- **`layers.registry.json`** — each layer that's a workflow output gets a `produced_by` field pointing at the producing `workflow_id`. (Optional; if absent, the layer is assumed manually maintained.)
- **`files.registry.json`** — unchanged. Files referenced from a workflow's `outputs_root` may still be registered if a page needs an alias.
- **`operations.registry.json`** — unchanged. Workflows are heavier than operations (offline, multi-stage); operations remain registry-side compute.
- **`pages.registry.json`** — pages MAY declare `requires_workflow: [...]`. A page that requires a workflow whose `status.json` indicates failure is mounted with a clear empty-state instead of silently rendering stale data.
- **`slots.registry.json`** — unchanged.

## 9. The migration-plan use case (worked example)

Per `docs/MIGRATION_4_ATLASES.md` §2, the BP_ATLAS workflow lands in `atlases/cross-species/engines/producers/bp_atlas/`. Its `workflows.registry.json` entry (sketched in §3 above) declares 6 stages, 2 runners, a post-run chain, and 8 produced layers.

The `evolution` atlas's `pages/polarize_synteny_vote.js` reads `crossSpecies.synteny_18sp_v1` — but `synteny_18sp_v1` is produced by a *different* workflow (`gene_order_consolidation`), not `bp_atlas_pipeline`. The cross-atlas-import resolver fetches both workflows' status to surface "synteny_18sp last refreshed 2 days ago; bp_atlas refreshed 3h ago" so the user sees what's current.

If `synteny_18sp_v1`'s status indicates it was run with knob_hash `X` but the registry's current default knob_hash is `Y`, the resolver flags the layer as stale and the consuming page renders an "outputs stale (knob set changed)" banner.

## 10. Out of scope

- Workflow scheduling / queue management (this SPEC describes declaration + status, not orchestration; orchestration lives in runners which are atlas-side bash/python).
- Distributed workflows that span multiple machines (the BP_ATLAS SLURM driver is a single sbatch script with internal parallelism — that's the supported pattern).
- Live progress streaming (the chrome reads `status.json` on mount + on user-requested refresh; no websocket / SSE).
- Workflow result caching across knob sets (each knob set writes its own subtree; content-addressed by knob_hash; cache eviction is out of scope).

## 11. Failure modes the SPEC explicitly handles

| Failure | Atlas-core behaviour |
|---|---|
| `workflows.registry.json` is missing | Atlas mounts; no workflows surfaced; pages that `requires_workflow` show empty-state with "workflow not configured" |
| Schema validation fails | Atlas refuses to mount; logs errors with `workflow_id` + `field` + `reason` |
| `status.json` is missing | Workflow is shown as "never run" in chrome |
| `status.json` indicates last run failed | Workflow is shown with red "last run failed" badge; outputs are still readable (stale data is still data) |
| Workflow output layer is read by a page when status indicates failure | Layer read succeeds; page receives data + a `data._workflow_status === 'failed'` flag the page can choose to surface |
| Workflow runner script does not exist | Validation failure; atlas refuses to mount |
| Workflow consumes a layer that doesn't exist | Validation failure; atlas refuses to mount |
| Workflow produces a layer that doesn't exist | Validation failure |
| Workflow's `cohort_id` is not in `cohorts.registry.json` | Validation failure |

## 12. Versioning

`workflows.registry.json` has a top-level `version` field. Compatible additions (new optional fields, new workflow entries) bump the patch version. Breaking changes (renamed fields, removed required fields) bump the minor version and the schema's `$id` URL.

This SPEC is `v1.0`. The reference impl declares `MAJOR_VERSION = 1`.

---

*End of SPEC. Reference implementation in `reference_impl/workflows_registry.js`.*
