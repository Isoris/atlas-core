# MANAGER_SPEC — the readiness layer above the librarian

Status: **v1 (frozen)**.  Schema version: `manager_v1`.

> **Librarian** = knows *where* data / results are.
> **Manager**   = knows *whether* they are usable now.

The manager does **not replace** the librarian.  It sits above it and
answers six questions per page / layer / analysis:

1. Which biological objects does this provide?
2. Are those objects `ready` / `partial` / `missing` / `blocked` / `stale`?
3. Which sample group do they apply to?
4. Which interval / chromosome / reference do they apply to?
5. Which downstream pages or analyses can reuse them?
6. What is missing before this page becomes usable?

**The growth rule (non-negotiable):** define biological objects
*progressively*, only when a real page or research question needs them.
Do not pre-define 200 objects.  This document seeds the **9 core
products** the current manuscript requires; everything else grows by
demand.

---

## §0 The three-tier model

```
                          ┌────────────────────────────┐
                          │  Question                  │
                          │  "Does inversion karyotype │
                          │   affect meiosis per chrom?"│
                          └──────────────┬─────────────┘
                                         │ requires[]
                                         ▼
                          ┌────────────────────────────┐
   research products  →   │  MANAGER (lib/manager.py)  │  ← scientific certifier
                          │  check_product_status(...) │
                          │  check_question_readiness  │
                          └──────────────┬─────────────┘
                                         │ backed_by_layers[]
                                         ▼
                          ┌────────────────────────────┐
   layers / pages     →   │  PLANNER (readiness_       │  ← procedural
                          │  planner.py) +              │
                          │  LIBRARIAN (resolve_layer)  │
                          └──────────────┬─────────────┘
                                         │
                                         ▼
                          ┌────────────────────────────┐
   adapters / files   →   │  REGISTRY                  │  ← contracts + results
                          └────────────────────────────┘
```

| Tier | Question it answers | Lives in |
|---|---|---|
| **Manager**   | "Is the biological object `inversion_karyotypes.v1` ready and valid for downstream use?  Is the question `inversion_effect_on_meiosis` answerable today?" | `lib/manager.py` |
| **Planner**   | "Does this hook / package have all its required layers?  What's BLOCKED / READY_TO_RUN?" | `lib/readiness_planner.py` |
| **Librarian** | "Does this layer resolve in this scope?  RESOLVED / COMPLETE / KNOWN_MISSING / …" | `lib/resolve_layer.py` |

Pages call the tier that matches their need.  Page 6 (Candidate review)
calls the planner.  Page 8 (Question readiness, this PR) calls the manager.

---

## §1 Research product

A **research product** is the registered, named, status-bearing biological
object that other atlas layers depend on.  Not every file is a product;
only the ones worth promoting to "downstream consumers can rely on this".

```json
{
  "product_id":       "inversion_karyotypes.v1",
  "schema_version":   "research_product_v1",
  "label":            "Inversion karyotype assignments",
  "kind":             "biological_object",
  "atlas":            "inversion_atlas",
  "type":             "table",
  "grain":            "sample x inversion",
  "status":           "ready",
  "confidence":       "review_passed",
  "reason":           "Karyotype table exists, sample IDs match, coordinates match fClaHyb_Gar_LG, manual review passed.",
  "biological_scope": { "species": "Clarias gariepinus", "dataset": "226_WGS_hatchery", "reference": "fClaHyb_Gar_LG" },
  "sample_scope":     "sample_registry.qcpass_226",
  "coordinate_scope": "interval_registry.fClaHyb_Gar_LG",
  "backed_by_layers": ["karyotype_calls", "polarized_karyotype_calls"],
  "produced_by":      { "analysis_id": "karyotype_polarizer", "version": "v0", "result_id": null },
  "depends_on":       ["inversion_candidates.v1", "beagle_dosage.qcpass"],
  "valid_for":        ["classify_samples_by_inversion", "compare_karyotype_groups", "test_mendelian_transmission"],
  "path":             "02_sets/karyotype/karyotype_calls.tsv",
  "schema_path":      "schemas/structured_block_schemas/karyotype_calls_v1.json",
  "last_checked":     "2026-05-15T00:00:00Z"
}
```

### `kind` enum

| `kind`              | What it is | Example |
|---|---|---|
| `biological_object` | The unit of scientific currency.  Tracked by the manager.  Other atlas layers depend on it. | `inversion_karyotypes`, `meiosis_dyads`, `recombination_rate_by_inversion_karyotype` |
| `derived_table`     | A useful table that supports a `biological_object` but is not itself the answer to anything. | per-window FST tracks, per-pair relatedness matrices |
| `intermediate`      | Throwaway artefacts of a pipeline.  Not exposed as products; logged in `analysis_results.jsonl` and forgotten. | merged-bands buffer, sort-key indexes |

The manager **only tracks `biological_object` products**.  Derived tables
and intermediates stay at the layer / result level.

### `status` ladder

```
missing      no input/result exists; the product has never been computed
available    files exist, contract not verified
validated    schema/QC checks pass
ready        scientifically usable — passed review or `confidence: review_passed`
stale        produced from older inputs (one of its depends_on changed)
blocked      cannot run because a `depends_on` product is missing/blocked/failed
deprecated   superseded by a newer version; kept for history
```

`ready` is the only state a downstream consumer should rely on.  Everything
else is informational.

### `confidence` enum

```
review_passed   human reviewer signed off
preliminary     produced; not yet reviewed
rejected        reviewer rejected
unreviewed      no review attempt
```

Independent of `status`.  A product can be `ready` only when
`confidence in {review_passed}`.

### Backing & provenance

- **`backed_by_layers`** is the FK chain into `layer_registry.jsonl`.  When all backing layers resolve to `RESOLVED` / `COMPLETE` for the product's scope, the product is at least `available`.
- **`produced_by.result_id`** points at the `analysis_results.jsonl` row that produced the current backing data.  Optional for file-kind products curated by hand.
- **`depends_on`** is a list of other `product_id`s the product semantically needs.  This is what the manager walks to compute `blocked` / `stale`.

### `valid_for`

A free-form list of downstream use tokens.  Convention: short snake-case verbs
(`compare_karyotype_groups`, `test_mendelian_transmission`).  Used by the
question's `requires[].role` lookup (informational).

---

## §2 Research question

A **research question** is the user-facing scientific goal.  It declares
which products it requires and which products it produces.

```json
{
  "question_id":      "inversion_effect_on_meiosis_per_chromosome",
  "schema_version":   "research_question_v1",
  "label":            "Do inversions affect meiosis per chromosome?",
  "description":      "Compare meiotic recombination rates between karyotype groups within and outside inversion intervals, per chromosome.",
  "biological_scope": { "species": "Clarias gariepinus", "dataset": "226_WGS_hatchery", "reference": "fClaHyb_Gar_LG" },
  "requires": [
    { "product_id": "inversion_candidates.v1",         "role": "define inversion intervals" },
    { "product_id": "inversion_karyotypes.v1",         "role": "assign each catfish to homA/het/homB per inversion" },
    { "product_id": "long_range_haplotype_regimes.v1", "role": "define extended inheritance blocks around inversions" },
    { "product_id": "pedigree_dyads.v1",               "role": "define parent-offspring meioses" },
    { "product_id": "chromosome_meiosis_events.v1",    "role": "count recombination/transmission events per chromosome" }
  ],
  "outputs": [
    { "product_id": "inversion_meiosis_effects.v1", "type": "table", "grain": "inversion x chromosome x dyad_group" }
  ],
  "status": "blocked",   // computed live by the manager
  "tags":   ["inversions", "meiosis", "recombination", "manuscript"]
}
```

The `status` field is **computed** by `check_question_readiness()`; it is
not stored.  Authors set `requires`, `outputs`, `biological_scope`; the
manager fills in the rest at read time.

---

## §3 The manager's algorithm

```
check_product_status(product_id, scope)
  1.  load the product row.
  2.  if backed_by_layers is empty → status = "missing" (nothing to back it).
  3.  resolve each backing layer via the librarian.
  4.  if any backing layer is UNKNOWN_CONTRACT      → "missing"  (contract not there)
      if any backing layer is FAILED                → "blocked"
      if all backing layers RESOLVED/COMPLETE       → at least "available"
      else                                          → "missing"
  5.  if "available", check confidence:
        review_passed                              → status = "ready"
        preliminary / unreviewed                   → "validated" (if schema passes) else "available"
        rejected                                   → "blocked"
  6.  for each depends_on product, recursive call.
        any missing/blocked/deprecated upstream    → status = "blocked"  (record why)
        any stale upstream                         → status = "stale"
  7.  return { status, reason, missing, stale, deprecated, ready_when }

check_question_readiness(question_id, scope)
  1.  load the question.
  2.  for each requires[].product_id, call check_product_status.
  3.  aggregate:
        all ready                                  → status = "ready_to_run"
        some ready, some blocked                   → "partial"
        none ready                                 → "blocked"
        any required product UNKNOWN               → "unknown"
  4.  collect next_actions:
        for each missing product, look up its produced_by analysis_id.
        emit { action: "run", analysis_id, produces: product_id, label }
  5.  return the full readiness report (UI-friendly JSON).
```

The algorithm is **read-only**.  No analysis runs; no file is written;
no result row is mutated.  Status is recomputed on every call.

---

## §4 §refusals

1. **No silent compute on read.**  `check_product_status` and
   `check_question_readiness` are *queries*; they never trigger work.
2. **No invented products.**  Every `product_id` in `questions.jsonl`
   must resolve to a row in `products.jsonl` (or the question's status
   becomes `unknown` and lists the unresolved product).
3. **No drift between product.backed_by_layers and the layer registry.**
   The builder (next phase) cross-checks every product's backing layers
   resolve.
4. **No `ready` without review.**  A product cannot be `ready` while
   `confidence in {preliminary, unreviewed, rejected}`.  Maximum is
   `validated`.
5. **No untyped scope.**  `biological_scope` is required on every product
   and every question.  Cross-scope use is a downstream decision, not the
   manager's.

---

## §5 What the user sees — page 8 (Question readiness)

Per question:

```
Research question:
  Do inversions affect meiosis per chromosome?

Status: BLOCKED

Required products:
  ✓ inversion_candidates.v1                  ready  (backed by layer: inversion_candidates)
  ✓ inversion_karyotypes.v1                  ready  (backed by layer: karyotype_calls, polarized_karyotype_calls)
  ⚠ long_range_haplotype_regimes.v1         missing (no producing analysis registered yet)
  ✗ pedigree_dyads.v1                       blocked (depends_on: parent_offspring_edges — missing)
  ✗ chromosome_meiosis_events.v1            blocked (depends_on: pedigree_dyads.v1, marker_phasing.v1 — both missing)

Next useful actions:
  - Register a producer for long_range_haplotype_regimes.v1
  - Build pedigree_dyads.v1 from parent_offspring_edges
  - Build chromosome_meiosis_events.v1 from dyads + informative markers
```

The page is a *query view*.  No buttons execute; **Suggest run** opens a
modal that copies a dispatch intent JSON (the dispatcher, when it lands,
will consume that).

---

## §6 Files

```
schemas/registry_schemas/
  research_product_v1.schema.json
  research_question_v1.schema.json

01_registry/
  products.jsonl                  canonical
  questions.jsonl                 canonical

lib/
  manager.py                      check_product_status + check_question_readiness

page/
  readiness.html                  page 8 — research question readiness

MANAGER_SPEC.md                   this document
```

---

## §7 Migration order

1. **This PR** — spec + schemas + seed products + seed questions + manager + page 8.
2. **Next** — wire the existing analyses' outputs into products (every analysis_registry row that has a `produces` layer can have a matching product if it's biologically meaningful).
3. **Later** — review workflow: a human reviewer flips `confidence` from `preliminary` to `review_passed` after looking at the product.  Until then, products stay at `validated` max.
4. **Later still** — `valid_for` becomes the join axis with `question.requires[].role`; the manager warns when a question uses a product for a `role` not in its `valid_for` list.

---

_End of MANAGER_SPEC.md (v1)._
