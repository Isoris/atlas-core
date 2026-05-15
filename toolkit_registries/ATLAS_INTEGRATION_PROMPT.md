# ATLAS_INTEGRATION_PROMPT

A portable prompt for any other atlas project that wants its **IN / OUT
connectors** to plug into the **Atlas Manager: Layer Connector** page
(page 9 of `atlas-core`).

> Goal: prepare each atlas (inversion-atlas, relatedness-atlas,
> meiosis-atlas, evolution-atlas, genome-synteny-atlas, marker-design,
> …) so its biological objects show up correctly in the Layer Connector
> with the right Inputs → Layer → Outputs → Used-by wiring.

Copy the prompt below verbatim into a Claude session inside the target
atlas repo.

---

## The prompt to paste

```
You are wiring an atlas project into the atlas-core Layer Connector
(page 9). Prepare this atlas so that every biological object it
produces or consumes is registered as a research_product and the
Layer Connector can show its IN / OUT / USED-BY connections.

The Layer Connector reads these JSONL files from the workspace's
01_registry/ directory:

  01_registry/layer_registry.jsonl       (the WHERE — file/result/operation)
  01_registry/analysis_registry.jsonl    (the analyses + their input_layer_types / produces)
  01_registry/hook_registry.jsonl        (page hooks + required_layers)
  01_registry/products.jsonl             (the WHAT — biological objects)
  01_registry/questions.jsonl            (the WHY — research questions)
  01_registry/estimands.jsonl            (per-claim estimability)
  01_registry/sample_attributes.jsonl    (cohort metadata coverage)

Every record uses one canonical schema:

  research_product_v1   — biological_object, derived_table, intermediate
  research_question_v1  — what we're trying to answer
  estimand_v1           — one specific scientific claim, with preconditions
  layer_registry_row_v1 — one row per layer KIND
  analysis_registry_row_v1 — one row per analysis KIND
  hook_registry_row_v1  — one row per page hook

JSONL is canonical. TSV is a derived view emitted by
lib/tsv_from_jsonl.py.

For this atlas, do the following.

### Step 1 — inventory the biological objects worth registering

List every biological object this atlas produces or relies on.
Only register objects that:
  - are reusable by another atlas / page / analysis
  - have a stable identity (id + version)
  - represent ONE biological idea, not a pipeline buffer

Do NOT register:
  - intermediate buffers, sort keys, merge-state, raw bands
  - one-off plots, screenshots, slides
  - free-form notebook scratch

Convention for IDs:
  <snake_case_name>.v<N>
  e.g. inversion_karyotypes.v1, family_hubs.v1, dyads_phased.v2

For each object, mark its `kind`:
  biological_object   tracked by the Manager (default for the ones you list)
  derived_table       supports a biological_object but is itself not standalone
  intermediate        pipeline buffer; do NOT register in products.jsonl

### Step 2 — write products.jsonl

For each biological_object, write one JSONL row matching
research_product_v1.schema.json. Required fields:

  product_id          stable id
  schema_version      "research_product_v1"
  label               human-readable label
  kind                "biological_object"
  atlas               this atlas's id (e.g. "inversion_atlas")
  type                table | json | graph | scalar_set | matrix
  grain               row-level grain ("sample × inversion", "dyad",
                                       "interval_pair", "window × chr")
  biological_scope    { species, dataset, reference }
  sample_scope        the sample axis (e.g. "sample_registry.qcpass_226")
  coordinate_scope    the coordinate axis (e.g. "interval_registry.fClaHyb_Gar_LG")
  backed_by_layers    array of layer_ids that store the data
                      (registered in layer_registry.jsonl)
  produced_by         { analysis_id, version, result_id|null }
  depends_on          array of upstream product_ids
  valid_for           array of free-form downstream-use tokens
  confidence          review_passed | preliminary | unreviewed | rejected
  last_checked        ISO 8601 timestamp

Optional:
  partial_coverage    { covered, total, kind } when the product is partial
  notes               one-liner explaining missing producers, caveats

### Step 3 — wire backed_by_layers + produced_by

Every product MUST have its `backed_by_layers` set to a layer_id that
exists in layer_registry.jsonl. If the layer doesn't exist yet,
ADD a stub row to layer_registry.jsonl with:
  source_kind: "analysis_result" or "file"
  status: "stub"  or "experimental"
The Layer Connector will then show the product as `missing` with a
clear "no producing analysis registered yet" hint.

If the product is produced by an adapter, set:
  produced_by.analysis_id = <analysis_id from analysis_registry.jsonl>
Otherwise leave it empty.

### Step 4 — wire depends_on

For each product, list every UPSTREAM biological_object it requires.
This is the IN side of the connector. Examples:

  pedigree_dyads.v1 → depends_on: [parent_offspring_edges.v1]
  chromosome_meiosis_events.v1 → depends_on: [pedigree_dyads.v1, inversion_candidates.v1]

The Layer Connector walks depends_on backwards to flag blocked or
stale products.

### Step 5 — wire valid_for

For each product, list every DOWNSTREAM USE it enables, as free-form
tokens. Examples:

  inversion_karyotypes.v1.valid_for = [
    "classify_samples_by_inversion",
    "compare_karyotype_groups",
    "test_mendelian_transmission",
    "scope_meiosis_effects"
  ]

These tokens are surfaced in the Layer Connector's drawer under
"Valid for".

### Step 6 — write questions.jsonl

For each scientific question this atlas wants to answer, write one
JSONL row matching research_question_v1.schema.json:

  question_id         stable id (snake_case)
  schema_version      "research_question_v1"
  label               one-line natural-language question
  description         one-paragraph context
  biological_scope    same shape as the product
  requires            array of { product_id, role, required? }
  outputs             array of { product_id, type, grain }
  tags                array of free-form tags

The Layer Connector shows the question in the central card; required
products appear as INPUT cards; output products appear as OUTPUT cards.

### Step 7 — write estimands.jsonl (one per specific claim)

For each scientifically distinct *claim* the question implies, write
one estimand. Preconditions can be product / layer / sample_attribute.

The Estimability Manager distinguishes:
  - registry-fixable (a producing analysis exists; just run it)
    → not_estimable
  - structurally-fixable (need new metadata or new samples)
    → needs_extra_data

This is critical — same "missing" word, two different recovery paths.

### Step 8 — write sample_attributes.jsonl

For every sample-axis metadata the estimands depend on, write one
row in sample_attributes.jsonl:

  attribute           name (e.g. parent_sex_known, phased_offspring)
  scope               cohort id (e.g. "sample_registry.qcpass_226")
  status              known | covered | partial | unknown | missing
  n_covered, n_total  coverage counts
  reason              free-text explanation
  schema_version      "sample_attribute_v1"

### Step 9 — wire ID conventions

Use these exact id conventions so the Layer Connector can group
across atlases:

  atlas_id            <snake_case>_atlas
                      (inversion_atlas, relatedness_atlas, meiosis_atlas,
                       evolution_atlas, genome_synteny_atlas,
                       marker_design)
  product_id          <snake_case>.v<N>
  question_id         <snake_case>
  layer_id            <snake_case>           (no .v suffix)
  analysis_id         <snake_case>           (no .v suffix)
  hook_id             <page_id>_<event>
  panel_id            <name>_panel

### Step 10 — validate

Run the build + check tools from atlas-core's lib/:

  python3 -m lib.build_connection_map
    # must report 0 warnings — every adapter, every panel, every page
    # must FK cleanly into the registries.

  python3 -m lib.manager --product <one_of_your_products>
  python3 -m lib.manager --question <one_of_your_questions>
  python3 -m lib.estimability --question <one_of_your_questions>
    # all three must return a sensible status + reason.

  python3 -m lib.tsv_from_jsonl
    # regenerate the TSV derived view.

  open page/layer_connector.html
    # the central card should show the question; INPUTS / OUTPUTS /
    # USED-BY columns should populate; bottom table should list every
    # product; the right-column readiness report should match the CLI
    # output of lib.manager.

### Step 11 — the §refusals (carry these into the new atlas)

  1. Define products PROGRESSIVELY. Don't pre-define 200. Only register
     biological_objects that a real page or question consumes today.
  2. NEVER store status. Status is computed live by the Manager /
     Estimability Manager.
  3. Never store random JS adapter functions in the registry. Adapters
     live in analysis/<analysis_id>/adapter_atlas.js per ADAPTER_CONTRACT.md.
  4. JSONL is canonical. NEVER edit TSV by hand for adapter-backed rows.
  5. A product is `ready` only when confidence=review_passed.
     `preliminary` ⇒ max `validated`. No exceptions.
  6. Every product needs `biological_scope`. Cross-scope decisions
     belong to the downstream user, not the Manager.

### Step 12 — the minimal seed for a new atlas

Even before any analysis runs, write the *contracts*:

  1. Decide the atlas_id.
  2. Pick the 5-10 core biological_objects this atlas will publish.
  3. Add their stub rows to products.jsonl with backed_by_layers
     pointing at stub layer_registry rows.
  4. Write 1-3 research_questions that this atlas should answer.
  5. Run python3 -m lib.build_connection_map and fix any warnings.
  6. Open page 9 → the new atlas's question should appear with all
     products MISSING. That's the canonical starting state.

Now expand: each time a real producer (adapter) lands, the relevant
product flips from MISSING → AVAILABLE → VALIDATED → READY.

The Layer Connector renders this evolution automatically. You never
write status by hand.
```

---

## How to use the prompt

1. Open a fresh Claude session inside the target atlas repo.
2. Paste the prompt above (the fenced block).
3. Claude will inventory the atlas's biological objects, draft products
   / questions / estimands JSONL, and produce a checklist of stub layer
   rows to add to `layer_registry.jsonl`.
4. Run the validation commands in §10. Iterate until 0 warnings.
5. Open `page/layer_connector.html` and verify the new atlas's question
   appears with the right IN / OUT / USED-BY wiring.

## Files this prompt touches (per atlas)

Each atlas integrating with the Layer Connector ends up adding:

```
01_registry/
  products.jsonl              + 5–20 rows
  questions.jsonl             + 1–5 rows
  estimands.jsonl             + 1–5 rows per question
  sample_attributes.jsonl     + 0–10 rows
  layer_registry.jsonl        + stubs for any layer not yet registered
  analysis_registry.jsonl     + adapter rows when adapters land
```

No new schemas. No new tools. Just rows.

## The principle

> A biological object becomes a registered product the moment another
> page, question, or atlas depends on it. Until then it stays at the
> layer / result level. The Layer Connector enforces this by only
> rendering `kind=biological_object` products in its drawer; everything
> else stays in the librarian-level data tier.

---

_End of ATLAS_INTEGRATION_PROMPT.md (v1)._
