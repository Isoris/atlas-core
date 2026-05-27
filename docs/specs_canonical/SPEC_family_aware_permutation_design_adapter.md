# SPEC — family_aware_permutation_design IN/OUT JSON adapters

**Status**: shipped 2026-05-20. End-to-end smoke green; 6 new
assertions validate identifier drop, unknown-karyotype drop,
singleton-block diagnostic, karyotype-count aggregation, and summary
counts. Not consumed by a page yet — wires into the still-blocked
[`interchromosomal`](../specs_todo/SPEC_interchromosomal_page.md) page
as one of its four required builders (per
[SPEC_interchromosomal_page.md §6](../specs_todo/SPEC_interchromosomal_page.md) build
order step 4).

**Implemented in:**
- [`atlases/meiosis/registries/data/actions.registry.json`](../atlases/meiosis/registries/data/actions.registry.json) — `import_family_aware_permutation_design` + `normalize_family_aware_permutation_design` actions
- [`atlases/meiosis/registries/data/extractors.registry.json`](../atlases/meiosis/registries/data/extractors.registry.json) — 2 entries for layer_type `family_aware_permutation_design`
- [`atlases/meiosis/registries/runners/import_tsv.py`](../atlases/meiosis/registries/runners/import_tsv.py) — **shared** with the other three meiosis adapters
- [`atlases/meiosis/registries/runners/normalize_family_aware_permutation_design.py`](../atlases/meiosis/registries/runners/normalize_family_aware_permutation_design.py)
- [`atlases/meiosis/registries/extractors/family_aware_permutation_design_tsv.py`](../atlases/meiosis/registries/extractors/family_aware_permutation_design_tsv.py)
- [`atlases/meiosis/registries/extractors/normalize_family_aware_permutation_design.py`](../atlases/meiosis/registries/extractors/normalize_family_aware_permutation_design.py)
- 4 schemas under `atlases/meiosis/registries/schemas/{schema_in,schema_out}/`
- Smoke test extended in [`atlases/meiosis/registries/test_adapter_smoke.py`](../atlases/meiosis/registries/test_adapter_smoke.py)

This is the **fourth adapter** in the meiosis-atlas, built using
[atlas-core/docs/SPEC_atlas_adapter_cookbook.md](../../atlas-core/docs/SPEC_atlas_adapter_cookbook.md).

---

## 1. Goal

Provide the **null-model design table** that the `interchromosomal`
page consumes when running its family-aware permutation. Without this
design, naive permutation of karyotype labels would violate
sib-correlation: parents within the same family produce correlated
offspring outcomes, so karyotype swaps must happen *within* family
blocks (preserving the family ↔ karyotype joint distribution) rather
than across the whole cohort.

The design table prescribes the **permutation blocks** — equivalence
classes of parents that can swap karyotype assignments with each other
under the null. The consumer picks `n_permutations` (1k / 10k / 100k
per the page UI) and the actual shuffling happens at run time.

## 2. Two-action flow

```
producer TSV (one row per (focal_inversion × parent_id))
    │
    ▼ import_family_aware_permutation_design → staging_family_aware_permutation_design_v0
    │     loose payload: {columns, rows}
    │
    ▼ normalize_family_aware_permutation_design → family_aware_permutation_design_v1
       typed: {assignments[], summary}
       provenance.source_layer_ids = [<staging id>]
```

Layer type for both stages: `family_aware_permutation_design`.
Distinguished by `schema_version`.

The **import runner is shared** with the other three meiosis adapters
(`runners.import_tsv.import_tsv`) — same workspace-relative path
resolution, same copy-to-raw_results provenance.

## 3. Canonical columns (family_aware_permutation_design_v1)

Per [`schemas/schema_out/family_aware_permutation_design_v1.schema.json`](../atlases/meiosis/registries/schemas/schema_out/family_aware_permutation_design_v1.schema.json):

**Required (5 cols):**
```
focal_inversion_id   — which inversion's null model this row applies to.
                       A separate design exists per inversion because
                       karyotype labels are inversion-specific.
parent_id            — the sample being labeled.
family_id            — from relatedness-atlas family_hubs.v1; the family
                       block the permutation respects.
karyotype            — the parent's karyotype at focal_inversion_id;
                       enum {homA, het, homB}.
permutation_block    — equivalence-class id for shuffling. Typically
                       equals family_id, but can be coarser (e.g.
                       merging tiny families to avoid degenerate blocks)
                       or finer (e.g. splitting by sex).
```

**Optional (2 cols):**
```
hub_id               — ngsPedigree hub id (intermediate grouping;
                       family > hub > individual). For provenance /
                       diagnostics only — not used in the permutation.
n_offspring          — count of offspring this parent contributes (the
                       meiosis events at risk). Used by the consumer if
                       the null model weights by offspring count.
```

Type coercion:
- `parent_id`, `family_id`, `permutation_block`, `focal_inversion_id`,
  `hub_id` → string (strip + null on standard sentinels)
- `karyotype` → enum {homA, het, homB}; unknown values → row dropped
  (a row whose karyotype can't be classified is unusable in the null)
- `n_offspring` → int (null on parse failure)

Required identifier check: rows missing any of
`focal_inversion_id`, `parent_id`, `family_id`, `karyotype`, or
`permutation_block` are dropped silently — producer's join step should
have caught them.

## 4. Summary block

`family_aware_permutation_design_v1.summary` always includes:

```
n_assignments        — total row count after coercion + identifier drop.
n_focal_inversions   — distinct focal_inversion_id values.
n_families           — distinct family_id values.
n_permutation_blocks — distinct permutation_block values across all
                       focal inversions.
n_parents            — distinct parent_id values.
karyotype_counts     — {homA, het, homB}; aggregate across all focal
                       inversions; lets the page badge surface the
                       het / non-het balance at a glance.
n_singleton_blocks   — permutation blocks containing exactly one
                       parent (the permutation is trivially the
                       identity for these — useful diagnostic; if N is
                       high, the design is degenerate and the consumer
                       should widen blocks).
```

Drives the interchromosomal page status badge: "Null model: 47 families,
312 assignments, 3 singleton blocks (degenerate)."

## 5. Producer expectations

The producer side is NOT in scope of this adapter — it lives in the
`catfish-inversion-analysis` repo (or equivalent producer pipeline),
and ships a per-(focal_inversion × parent) TSV. Authors are expected
to:

1. Read `family_hubs.v1` from the relatedness-atlas envelope index
   (per `depends_on_atlases: [relatedness_atlas]`).
2. Read `inversion_karyotypes.v1` from the inversion-atlas to assign
   karyotypes at each focal inversion.
3. Decide on the **block strategy** — typically `permutation_block =
   family_id`. Document the policy in the producer's README; the atlas
   adapter is policy-agnostic.
4. Emit one row per surviving (focal_inversion, parent) pair with the
   columns listed in §3.

The atlas adapter is stage-agnostic past §3's schema check.

## 6. Manifest examples

Capture:
```json
{
  "action_id":  "act_import_2026_05_20_abc",
  "type":       "import_family_aware_permutation_design",
  "dataset_id": "226_WGS_hatchery",
  "target": {
    "path": "raw_results/null_models/family_aware_design.tsv",
    "scope": "cohort:226_WGS_hatchery",
    "source": "joined_from:family_hubs_v1+inversion_karyotypes_v1"
  },
  "expected_outputs": [
    { "layer_type": "family_aware_permutation_design",
      "schema_version": "staging_family_aware_permutation_design_v0",
      "stage": "staging" }
  ]
}
```

Promote:
```json
{
  "action_id":  "act_normalize_2026_05_20_def",
  "type":       "normalize_family_aware_permutation_design",
  "dataset_id": "226_WGS_hatchery",
  "target": {
    "source_layer_id": "family_aware_permutation_design_226_WGS_hatchery_abc"
  },
  "expected_outputs": [
    { "layer_type": "family_aware_permutation_design",
      "schema_version": "family_aware_permutation_design_v1",
      "stage": "normalized" }
  ]
}
```

## 7. Open work

- **No real data**: the join pipeline that emits this TSV hasn't run
  yet on the 226-sample cohort. The adapter is validated against a
  5-row synthetic fixture in
  [`test_adapter_smoke.py`](../atlases/meiosis/registries/test_adapter_smoke.py)
  covering: full row, dropped row (missing focal_inversion_id), dropped
  row (unknown karyotype enum), and a singleton block (one parent in a
  block — diagnostic counter).
- **Consumer not wired**: the `interchromosomal` page remains blocked
  on the LAST missing builder (`coincidence_matrix.v1`). When the third
  ships, the page consumes all four builders simultaneously per
  SPEC_interchromosomal_page.md §6.
- **Cross-atlas read for family_hubs**: producer reads from the
  relatedness-atlas (via the registered `family_hubs.v1` envelope
  shape). If the family-hub builder changes its definition (e.g.
  switches from full-sibling-only to broader hub merging), the producer
  rebuilds with the new family_id assignments but the atlas adapter is
  unaffected — it consumes whatever id ships.
- **Block strategy is producer-side policy** — the atlas does NOT
  enforce `permutation_block == family_id`. Producers may use coarser
  blocks (merging tiny families) or finer (splitting by sex). The
  `n_singleton_blocks` summary counter is the diagnostic if a policy
  produces too many degenerate blocks.

## 8. Decision rationale

- **Why `permutation_block == family_id` is the default policy**: family is the smallest unit of correlated meioses (siblings share parents → share karyotype at every locus by Mendelian descent). Shuffling within family preserves the (family, karyotype) joint marginal — the only "noise" the null model swaps is which specific parent within the family is labeled het. This is the same logic Drosophila ICE tests use for full-sibling families.
- **Why drop unknown karyotype values (vs coerce to null)**: a row whose karyotype is `?` or `partial` or `mosaic` is unusable in a binary het/non-het test — the permutation can't place it on either side. Silent-drop keeps the rest of the design usable; the consumer can see `summary.karyotype_counts` to know how many rows survived.
- **Why `n_singleton_blocks` is a summary field, not an error**: small families are common in catfish cohorts (one parent contributes one offspring batch and is never sampled again). The consumer's status badge surfaces `n_singleton_blocks` so the reviewer knows when the null is degenerate — but the adapter doesn't refuse to ship a design with singletons; the design is still useful even if the null is slightly under-powered.
- **Why per-focal-inversion rows (vs one karyotype column per inversion)**: long-format scales better. A 226-parent cohort × 50 focal inversions = 11_300 rows in long format vs 226 rows × 51 columns in wide. The consumer's permutation loop is also long-format (per-(focal × parent) iteration).
- **Why karyotype is required (vs nullable)**: a parent with no karyotype call at a focal inversion can't enter the test — neither side accepts them. The row would be dropped downstream anyway; refusing it at the adapter saves a later filter.

## 9. Worked example

Suppose 4 parents in 2 families, all assigned to focal inversion `INV_A`:

| focal_inversion_id | parent_id | family_id | karyotype | permutation_block |
|---|---|---|---|---|
| INV_A | P1 | F1 | het  | F1 |
| INV_A | P2 | F1 | homA | F1 |
| INV_A | P3 | F2 | het  | F2 |
| INV_A | P4 | F2 | homA | F2 |

Permutation: for each block, Fisher-Yates shuffle the karyotype labels among the parents in that block.

- Block F1 has 2 parents (P1, P2) with karyotypes (het, homA). Two possible labelings: (het, homA) — the observed — or (homA, het) — the swap. So Fisher-Yates gives **2 unique permutations** for this block.
- Block F2 similarly has 2 unique permutations.
- Joint permutation space across the cohort: 2 × 2 = **4 unique permutations** of karyotype labels.

If the consumer runs `n_permutations = 10_000`, the actual sampled permutations include many duplicates (the same 4 labelings sampled repeatedly). This is **correct**: the permutation p-value approaches the exact randomization p-value as `n_permutations → ∞`. With only 4 unique labelings, the minimum p-value the test can produce is `1 / (4 + 1) = 0.20` (using the add-one smoothing from [SPEC_interchromosomal_page.md §5.4](SPEC_interchromosomal_page.md)). Even with 10k perms, you can't refute H0 at α = 0.05 with this design — the cohort is too small or too block-structured.

Driving the status badge: "Null model: 2 families, 4 assignments, **0 singleton blocks** — but only **4 unique labelings available, p_min = 0.20**. Larger cohorts will need to scale up."

A diagnostic the consumer should add (not shipped today): compute the joint permutation space size as `prod_blocks(block_size! / prod_karyo(karyo_count_in_block!))` and surface alongside `n_singleton_blocks`. The above 4-parent example: `2! / (1! × 1!) = 2` per block; `2 × 2 = 4` total. Helps the reviewer know when n_perms exceeds the unique-permutation cap.

## 10. Failure modes

| # | condition | behaviour |
|---|---|---|
| 10.1 | Missing `focal_inversion_id` | row dropped silently (required) |
| 10.2 | Missing `parent_id` | row dropped silently (required) |
| 10.3 | Missing `family_id` | row dropped silently (required) |
| 10.4 | Missing `karyotype` | row dropped silently (required; row would be unusable in the binary test) |
| 10.5 | Missing `permutation_block` | row dropped silently (required; can't permute without knowing the block) |
| 10.6 | `karyotype` not in {homA, het, homB} | coerced to null → row dropped by 10.4 path |
| 10.7 | All blocks are singletons | summary `n_singleton_blocks = n_parents`; consumer can run permutation but every permutation reproduces the observed labeling → p = 1.0 (correctly, per design — see [SPEC_interchromosomal_page.md §7.5](SPEC_interchromosomal_page.md)) |
| 10.8 | Duplicate `(focal_inversion_id, parent_id)` rows with different karyotypes | both rows kept in the envelope; the consumer's `karyotypesAtFocal` Map collapses duplicates by last-write — non-deterministic; producer must dedupe upstream |
| 10.9 | `n_offspring` field omitted | not used in v1 permutation; reserved for an offspring-weighted v2 |
| 10.10 | All rows for a focal_inversion have karyotype = het (no contrast) | the consumer's `_splitRates` returns `xsNonhet = []` → welchT short-circuits with NaN → p = NaN → flagged as under-powered on the result table |
