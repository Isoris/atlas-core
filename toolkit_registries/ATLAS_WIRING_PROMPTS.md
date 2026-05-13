# ATLAS_WIRING_PROMPTS — handoff prompts for each atlas / engine repo

Paste-ready prompts to send to a Claude session (or a human) working
on each downstream atlas or engine repo. They link back to the
contracts in `atlas-core/toolkit_registries/` and tell the receiving
session what to add on its side so the action-pipeline works
end-to-end.

**Required reading for every receiving session:**

1. `atlas-core/toolkit_registries/PIPELINE_FLOW.md` — the architecture.
2. `atlas-core/toolkit_registries/schemas/registry_schemas/layer_envelope.schema.json`
3. `atlas-core/toolkit_registries/schemas/registry_schemas/action_manifest.schema.json`
4. `atlas-core/toolkit_registries/schemas/registry_schemas/extractor_manifest.schema.json`
5. `atlas-core/toolkit_registries/schemas/registry_schemas/action_log_entry.schema.json`
6. `atlas-core/server/SERVER_README.md` — what the server already exposes.

The contract is intentionally minimal (per PIPELINE_FLOW.md §"Minimal
stable core"): nine required envelope fields, three required manifest
fields, one dispatcher. Don't over-engineer your end; just wire what
exists.

---

## Prompt 1 — Generic atlas (template, edit before sending)

```
We're wiring this atlas to atlas-core's action-pipeline contract.

CONTEXT — read first:
  atlas-core/toolkit_registries/PIPELINE_FLOW.md
  atlas-core/toolkit_registries/schemas/registry_schemas/layer_envelope.schema.json
  atlas-core/toolkit_registries/schemas/registry_schemas/action_manifest.schema.json
  atlas-core/toolkit_registries/schemas/registry_schemas/extractor_manifest.schema.json
  atlas-core/toolkit_registries/schemas/registry_schemas/action_log_entry.schema.json
  atlas-core/server/SERVER_README.md

YOUR JOB — create this folder layout under THIS atlas:

  <this-atlas>/registries/
  ├── schemas/
  │   ├── schema_in/      ← one .schema.json per action type this atlas supports
  │   └── schema_out/     ← one .schema.json per layer type this atlas produces
  ├── data/
  │   ├── actions.registry.json     ← maps type → runner module
  │   ├── extractors.registry.json  ← maps layer_type → parser module
  │   └── (existing layers.registry.json / operations.registry.json
  │        stay as-is)
  ├── dispatcher.py                  ← copy the ~80-line skeleton from
  │                                    PIPELINE_FLOW.md §"dispatcher.py"
  ├── runners/                       ← Python modules called by dispatcher
  └── extractors/                    ← Python modules called by dispatcher

RULES:
  1. Use the layer_envelope shape exactly. Required fields:
     layer_id, layer_type, schema_version, stage, dataset_id,
     status, created_at. Plus optional coordinate, sample_scope,
     source_files, provenance, payload.
  2. If the final normalized schema for a layer type isn't settled,
     ship a staging_<type>_v0.schema.json that's permissive
     (additionalProperties: true). DO NOT block on getting the
     normalized schema perfect.
  3. Every action manifest your runner accepts must have a matching
     schema_in/<type>_v1.schema.json. Keep it small.
  4. Every layer your extractor produces must have a matching
     schema_out/<schema_version>.schema.json. Keep payloads simple:
     arrays of rows with the columns the Atlas needs to render.
  5. The dispatcher validates manifest → runs runner → validates
     output payload → wraps in envelope → POSTs to /file/<path>
     via the existing atlas_server endpoint.
  6. Append every accepted manifest to registry/actions.log.jsonl.

DELIVERABLES:
  - schema_in/ + schema_out/ folders populated.
  - actions.registry.json + extractors.registry.json populated.
  - dispatcher.py functional.
  - At least one runner + one extractor end-to-end.
  - One worked example commit that runs the pipeline against a real
    upstream output and produces a normalized layer.

DO NOT:
  - Invent new server endpoints. Use the existing /api/popstats/...,
    /api/ancestry/..., /api/ld/..., /file/, /compute/ endpoints from
    atlas_server.py. The action endpoint orchestrates these; it
    doesn't replace them.
  - Modify the envelope shape. Add extra top-level fields if you
    must; never remove required ones.
  - Couple runners to the registry. Runners produce raw output
    files; the dispatcher does envelope-wrapping.

When done, push to <branch> and post the schema_in/ + schema_out/ file
list back here so atlas-core can confirm naming conventions.
```

---

## Prompt 2 — inversion-atlas (specific)

```
We're wiring inversion-atlas to atlas-core's action-pipeline contract.
You're starting with the existing inversion analyses (local PCA, D17,
candidate registration, karyotype assignment, recombinant maps, FST
scans within candidates, dosage heatmaps).

CONTEXT — read first (in order):
  1. atlas-core/toolkit_registries/PIPELINE_FLOW.md
  2. atlas-core/toolkit_registries/HIERARCHY_SPEC.md
  3. atlas-core/toolkit_registries/DATABASE_DESIGN.md (skim §"The four
     roles" + §"Sample group naming convention")
  4. atlas-core/toolkit_registries/schemas/registry_schemas/
     layer_envelope.schema.json, action_manifest.schema.json,
     extractor_manifest.schema.json
  5. atlas-core/toolkit_registries/schemas/structured_block_schemas/
     — these are the 40 per-aspect evidence-block schemas. Each maps
     to a layer_type your atlas already knows about.

YOUR JOB:

  Add the per-atlas wiring under
    inversion-atlas/atlases/inversion/registries/

  with this layout:
    schemas/schema_in/
      run_popstats_v1.schema.json          ← FST/dXY/π inside a candidate
      run_hobs_v1.schema.json              ← HOBS/HWE for a candidate
      run_d17_v1.schema.json               ← D17 candidate detection
      register_candidate_v1.schema.json    ← write a new candidate row
      assign_karyotype_v1.schema.json      ← write karyotype groups
      import_d17_staging_v0.schema.json    ← import messy D17 output as staging
      normalize_candidate_v1.schema.json   ← promote staging → normalized
    schemas/schema_out/
      candidate_regions_v1.schema.json
      fst_windows_v1.schema.json
      hobs_windows_v1.schema.json
      karyotype_assignment_v1.schema.json
      recombinant_map_v1.schema.json       ← already exists as a structured-block
      boundary_refined_v1.schema.json      ← already exists
      gene_cargo_v1.schema.json            ← already exists
      staging_d17_candidate_v0.schema.json ← capture-first envelope
    data/
      actions.registry.json
      extractors.registry.json
    dispatcher.py
    runners/
      popstats.py     ← wraps existing /api/popstats/groupwise
      hobs.py         ← wraps existing /api/popstats/hobs_groupwise
      d17.py          ← runs D17 R/python script and captures output
      candidate.py    ← writes candidate registration
      karyotype.py    ← writes karyotype groups
      import.py       ← reads D17 / Excel and emits staging
      normalize.py    ← converts staging → normalized
    extractors/
      fst_windows.py
      hobs_windows.py
      candidate_regions.py
      karyotype.py
      recombinant_map.py
      d17_staging.py

REUSE WHAT EXISTS:
  - Many of your structured_block_schemas/*.schema.json files in
    atlas-core/toolkit_registries/ already describe candidate-evidence
    payloads. Use those as the basis for your schema_out/ files; copy
    them into schema_out/ with the layer_type and a _v1 suffix.
  - Don't replicate the popstats engine. Your popstats.py runner is
    a thin Python wrapper that POSTs to /api/popstats/groupwise (the
    existing endpoint). The server runs region_popstats. Your runner
    captures the response into a TSV file. Your extractor reads the
    TSV and emits the fst_windows_v1 payload.

ON STAGING vs NORMALIZED:
  - For NEW analyses you're prototyping (e.g. a new boundary
    refinement method), ship a staging_<type>_v0.schema.json that's
    permissive. Capture raw fields. Promote later via a converter.
  - For settled analyses (FST windows, karyotype groups,
    candidate_regions) go straight to _v1 normalized.

DELIVERABLES:
  - All schema_in/ and schema_out/ files populated.
  - dispatcher.py copied from PIPELINE_FLOW.md skeleton + inversion
    specifics filled in.
  - Two end-to-end worked actions:
     (a) run_popstats inside a candidate → normalized fst_windows_v1.
     (b) import_d17_staging → staging_d17_candidate_v0 →
         normalize_candidate → candidate_regions_v1.
  - Update inversion-atlas page modules to read the new envelope
    layers via registry.resolve('fst_windows', { layer_id }) or
    similar — DO NOT have pages reading TSV directly.

DO NOT:
  - Change the envelope shape.
  - Modify atlas-core. If something's missing in the envelope or
    manifest schema, raise it back via an issue against atlas-core,
    don't fork.

When done, push and link the PR.
```

---

## Prompt 3 — unified-ancestry (binaries + caches)

```
We're wiring unified-ancestry's compute outputs into atlas-core's
action-pipeline contract. unified-ancestry currently produces:

  - region_popstats output (TSV per chrom/region/group set)
  - hobs_windower output (TSV with HOBS + HWE per window)
  - angsd_patched HWE outputs (gzipped TSV per group)
  - instant_q per-window per-sample Q matrices (TSV.gz precomputed)
  - ngsAdmix .qopt / .fopt files (whole-genome Q/F)

These are all already exposed through atlas_server.py endpoints
(/api/popstats/groupwise, /api/popstats/hobs_groupwise,
/api/ancestry/groupwise_q). The atlas can call them, but each call
just returns parsed JSON — there's no layer envelope, no action log,
no provenance trail.

YOUR JOB:

  Decide whether unified-ancestry needs its own atlas-level wiring,
  or whether it stays as an engine bundle that other atlases call
  into. Two patterns:

  Pattern A (RECOMMENDED): unified-ancestry stays an engine bundle.
    - It does NOT get its own registries/ folder.
    - Other atlases (inversion-atlas, population-atlas, …) wire their
      own dispatchers to call /api/popstats/groupwise etc. and wrap
      the response in their own layer envelopes.
    - unified-ancestry's job: keep the engines compilable, keep the
      cache layout under master_config.roots.precomp /
      master_config.roots.cohort_ancestry stable, document the
      output TSV column conventions in your README.
    - Action: write a SHORT engine_outputs.md in unified-ancestry
      listing the column names and value units of each engine's
      output, so atlas extractors know what to parse.

  Pattern B: unified-ancestry gets its own thin registries/ folder.
    - Useful if you have analyses that produce layers DIRECTLY
      (e.g. precomputed K=2..K=20 ngsAdmix sweeps, served as
      ancestry_q_v1 layers without any per-atlas action).
    - Layout:
        unified-ancestry/registries/
        ├── schemas/schema_in/
        │   └── precompute_ngsadmix_v1.schema.json
        ├── schemas/schema_out/
        │   ├── ancestry_q_v1.schema.json
        │   ├── ancestry_f_v1.schema.json
        │   └── instant_q_window_v1.schema.json
        ├── data/actions.registry.json
        ├── data/extractors.registry.json
        ├── dispatcher.py
        ├── runners/precompute_ngsadmix.py
        └── extractors/ngsadmix_qopt.py
    - The action endpoint would orchestrate
      a 28-chrom × 19-K sweep and emit one ancestry_q_v1 layer per
      (chrom, K). dataset_id = cohort_id; sample_scope.group_id =
      'all_<n>'; coordinate.chrom set; payload = the Q matrix.

DELIVERABLES:
  - Pick Pattern A or B in a short proposal commit.
  - If A: write engine_outputs.md describing what each binary
    produces (column names, units, missing-value sentinels).
  - If B: write the dispatcher + at least one runner +
    one extractor + one end-to-end example
    (precompute_ngsadmix → ancestry_q_v1 layer for one chrom × K=8).

REUSE WHAT EXISTS:
  - atlas_server.py's existing /api/popstats/* and
    /api/ancestry/groupwise_q endpoints stay as engine surfaces.
    Pattern A is essentially "leave them as engines, let atlases
    wrap them in their own layers".
  - The instant_q TSV.gz cache layout is canonical; don't move it.

DO NOT:
  - Build a new compute server. atlas_server.py already wraps the
    engines.
  - Make atlases call the binaries directly. Always through the HTTP
    endpoints so the cache is shared.

When done, push and link the PR plus the proposal commit.
```

---

## Prompt 4 — population-atlas / genome-atlas / comparative-atlas (any future atlas)

```
We're wiring this new atlas to atlas-core's action-pipeline contract.

CONTEXT — read first:
  atlas-core/toolkit_registries/PIPELINE_FLOW.md
  atlas-core/toolkit_registries/HIERARCHY_SPEC.md  ← cohort vs species model
  atlas-core/toolkit_registries/schemas/registry_schemas/layer_envelope.schema.json
  atlas-core/server/SERVER_README.md

YOUR JOB:

  This atlas is starting from scratch. Set up the standard registry
  folder layout and pick which existing analyses you want to expose
  as actions on day 1.

  Standard layout (same as every other atlas):
    <this-atlas>/registries/
    ├── schemas/schema_in/
    ├── schemas/schema_out/
    ├── data/
    │   ├── actions.registry.json
    │   ├── extractors.registry.json
    │   ├── layers.registry.json
    │   └── operations.registry.json   (optional; for source='operation'
    │                                   layers that DON'T go through the
    │                                   action endpoint)
    ├── dispatcher.py
    ├── runners/
    └── extractors/

  Pick your day-1 analyses. Suggested minimal set:
    - one read-only action that just imports a manual table
      (Excel/TSV) → staging layer. Lets you validate your folder
      layout end-to-end with no compute.
    - one compute action that wraps an existing atlas_server endpoint
      (e.g. /api/popstats/groupwise for FST, /api/ld/split_heatmap
      for LD). Produces one normalized layer type.
    - one normalize_layer action that converts the staging layer to
      a normalized layer when the schema firms up.

RULES — same as the generic prompt:
  1. Envelope shape is fixed.
  2. Staging is the relief valve.
  3. No new compute endpoints.
  4. Dispatcher is ~80 lines, copy from PIPELINE_FLOW.md.

DELIVERABLES:
  - Folder layout populated.
  - Three actions working end-to-end (one import, one compute, one
    normalize).
  - Atlas pages read via registry.resolve(<layer_type>, { layer_id })
    only.

When done, push and link the PR.
```

---

## How to use these prompts

1. Pick the matching prompt for the atlas/engine repo you're handing
   off to.
2. Replace `<this-atlas>` placeholders with the actual atlas name.
3. Paste into a fresh Claude session (or send to the human owner)
   inside that repo's working directory.
4. The receiving session should commit on a feature branch and link
   the PR. atlas-core reviews the schema_in/ + schema_out/ layout to
   confirm naming and envelope compliance, then merges.

The atlas-core side does not change to accommodate a new atlas; the
new atlas slots into the contract.
