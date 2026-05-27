# SPEC — coincidence_matrix IN/OUT JSON adapters

**Status**: shipped 2026-05-20. End-to-end smoke green; 7 new
assertions validate identifier drop, explicit-c preservation, c
derivation from r_a/r_b/r_ab when producer omits it, the r_a=0 guard,
negative-interference flagging at default and overridden thresholds,
and summary aggregates. **Unblocks** the
[`interchromosomal`](../specs_todo/SPEC_interchromosomal_page.md) page
— with this shipped, all four required builders are satisfied.

**Implemented in:**
- [`atlases/meiosis/registries/data/actions.registry.json`](../atlases/meiosis/registries/data/actions.registry.json) — `import_coincidence_matrix` + `normalize_coincidence_matrix` actions
- [`atlases/meiosis/registries/data/extractors.registry.json`](../atlases/meiosis/registries/data/extractors.registry.json) — 2 entries for layer_type `coincidence_matrix`
- [`atlases/meiosis/registries/runners/import_tsv.py`](../atlases/meiosis/registries/runners/import_tsv.py) — **shared** with the other four meiosis adapters
- [`atlases/meiosis/registries/runners/normalize_coincidence_matrix.py`](../atlases/meiosis/registries/runners/normalize_coincidence_matrix.py)
- [`atlases/meiosis/registries/extractors/coincidence_matrix_tsv.py`](../atlases/meiosis/registries/extractors/coincidence_matrix_tsv.py)
- [`atlases/meiosis/registries/extractors/normalize_coincidence_matrix.py`](../atlases/meiosis/registries/extractors/normalize_coincidence_matrix.py)
- 4 schemas under `atlases/meiosis/registries/schemas/{schema_in,schema_out}/`
- Smoke test extended in [`atlases/meiosis/registries/test_adapter_smoke.py`](../atlases/meiosis/registries/test_adapter_smoke.py)

This is the **fifth adapter** in the meiosis-atlas, built using
[atlas-core/docs/SPEC_atlas_adapter_cookbook.md](../../atlas-core/docs/SPEC_atlas_adapter_cookbook.md).

---

## 1. Goal

Provide the **per-(interval-pair) coefficient-of-coincidence table** —
the statistic that drives both the `interchromosomal` page's
`c_coincidence` view and the relatedness-atlas's `coincidence` Sandler
interference map.

The coefficient of coincidence per pair of non-overlapping intervals A
and B on the same chromosome is:

```
C = r_ab / (r_a * r_b)
```

where `r_a` and `r_b` are single-CO rates in intervals A and B, and
`r_ab` is the double-CO rate (CO in BOTH intervals). Interpretation:

| C value          | meaning |
|------------------|---------|
| `C ≈ 1`          | independence — no interference |
| `C < 1`          | positive interference (the normal pattern; one CO suppresses another nearby) |
| `C ≫ 1` (e.g. ≥ 3) | "negative interference" — usually an artefact (low sample size, miscalled COs, contamination); flag for review |

When stratified by karyotype at a focal inversion (the
interchromosomal use case), the page tests whether `C` on a tested
chromosome **differs** between het and non-het carriers — a
manuscript-grade signal of interchromosomal effect.

## 2. Two-action flow

```
producer TSV (one row per interval pair)
    │
    ▼ import_coincidence_matrix → staging_coincidence_matrix_v0
    │     loose payload: {columns, rows}
    │
    ▼ normalize_coincidence_matrix → coincidence_matrix_v1
       typed: {pairs[], summary}
       provenance.source_layer_ids = [<staging id>]
```

Layer type for both stages: `coincidence_matrix`. Distinguished by
`schema_version`.

The **import runner is shared** with the other four meiosis adapters
(`runners.import_tsv.import_tsv`) — same workspace-relative path
resolution, same copy-to-raw_results provenance.

## 3. Canonical columns (coincidence_matrix_v1)

Per [`schemas/schema_out/coincidence_matrix_v1.schema.json`](../atlases/meiosis/registries/schemas/schema_out/coincidence_matrix_v1.schema.json):

**Required (3 cols):**
```
chrom            — the chromosome (both intervals on it; cross-chrom pairs
                   live in a separate envelope when needed)
interval_a_id    — stable id for interval A
interval_b_id    — stable id for interval B
```

**Recommended (1 col; derived when omitted):**
```
c_coincidence   — r_ab / (r_a * r_b); the headline statistic. Extractor
                  derives this from r_a + r_b + r_ab when the producer
                  omits it; null when any input is null or r_a * r_b == 0.
```

**Always present (8 cols total — the 3 required + 4 interval coords + 1 c):**
```
interval_a_start_bp, interval_a_end_bp
interval_b_start_bp, interval_b_end_bp
```

**Optional (6 cols):**
```
r_a, r_b               — single-CO rates in intervals A and B
r_ab                   — double-CO rate (both intervals)
n_offspring            — sample size used in the rate computation (diagnostic)
karyotype_at_focal_inv — homA/het/homB enum; populated when stratified
focal_inversion_id     — the focal inversion under which this matrix is
                         stratified; null for cohort-wide (un-stratified)
                         matrices
```

Type coercion:
- `*_start_bp`, `*_end_bp`, `n_offspring` → int (null on parse failure)
- `r_a`, `r_b`, `r_ab`, `c_coincidence` → float (null on parse failure;
  negative values coerce to null since rates and C must be ≥ 0)
- `chrom`, `interval_a_id`, `interval_b_id`, `focal_inversion_id` → string (strip + null on standard sentinels)
- `karyotype_at_focal_inv` → enum {homA, het, homB}; unknown → null

Derived field:
- `c_coincidence` computed as `r_ab / (r_a * r_b)` when producer omits
  it AND all three inputs are present + valid (r_a > 0, r_b > 0).
  Otherwise null.

Required identifier check: rows missing `chrom` OR `interval_a_id`
OR `interval_b_id` are dropped silently.

## 4. Summary block

`coincidence_matrix_v1.summary` always includes:

```
n_pairs                     — total row count after coercion + identifier drop
n_chroms                    — distinct chrom values
n_focal_inversions          — distinct non-null focal_inversion_id values
n_stratified_rows           — rows with karyotype_at_focal_inv non-null
karyotype_counts            — {homA, het, homB} across stratified rows
mean_c                      — mean c_coincidence across all non-null rows
                              (sanity check; should be < 1 for normal interference)
median_c                    — median c_coincidence
n_neg_interference_flagged  — rows with c_coincidence > 3 (flagged as
                              likely artefact; consumer rendering should
                              highlight these in red)
```

Drives the interchromosomal page status badge: "Coincidence matrix:
4,210 pairs over 29 chroms; mean C = 0.42; 18 pairs flagged."

## 5. Producer expectations

The producer side is NOT in scope of this adapter — it lives in the
ngsTracts producer pipeline (or a successor builder), and ships the
per-interval-pair table. Authors are expected to:

1. Choose interval definitions (typically equal-width windows, e.g.
   1 Mb) and assign stable ids.
2. For each (chrom, interval_a, interval_b) pair on the same chrom,
   compute `r_a`, `r_b`, `r_ab` from CO calls per
   `tract_classifications_v1` (or `chromosome_meiosis_events_v1` when
   working from aggregated counts).
3. If stratifying by karyotype: emit one row per (focal_inversion,
   karyotype, chrom, interval_a, interval_b) tuple, with
   `karyotype_at_focal_inv` + `focal_inversion_id` populated.
4. The atlas adapter derives `c_coincidence` when the producer omits
   it — producers can ship a smaller table by omitting the derived
   column.

## 6. Manifest examples

Capture:
```json
{
  "action_id":  "act_import_2026_05_20_abc",
  "type":       "import_coincidence_matrix",
  "dataset_id": "226_WGS_hatchery",
  "target": {
    "path": "raw_results/coincidence/coincidence_matrix.tsv",
    "scope": "cohort:226_WGS_hatchery",
    "source": "computed_from:chromosome_meiosis_events_v1+tract_classifications_v1"
  },
  "expected_outputs": [
    { "layer_type": "coincidence_matrix",
      "schema_version": "staging_coincidence_matrix_v0",
      "stage": "staging" }
  ]
}
```

Promote:
```json
{
  "action_id":  "act_normalize_2026_05_20_def",
  "type":       "normalize_coincidence_matrix",
  "dataset_id": "226_WGS_hatchery",
  "target": {
    "source_layer_id": "coincidence_matrix_226_WGS_hatchery_abc"
  },
  "expected_outputs": [
    { "layer_type": "coincidence_matrix",
      "schema_version": "coincidence_matrix_v1",
      "stage": "normalized" }
  ]
}
```

## 7. Open work

- **No real data**: the builder hasn't run yet. The adapter is validated
  against a 5-row synthetic fixture in
  [`test_adapter_smoke.py`](../atlases/meiosis/registries/test_adapter_smoke.py)
  covering: full data with explicit c, missing c with r_a/r_b/r_ab so c
  must be derived, missing c with r_a == 0 so c stays null, a flagged
  high-C row (artefact), and a dropped row missing chrom.
- **Consumer not wired**: the `interchromosomal` page is now
  **unblocked** — all four builders are shipped. Wiring is the next
  SPEC.
- **Stratification mode**: this adapter supports both un-stratified
  (cohort-wide matrix for the relatedness `coincidence` page) and
  karyotype-stratified (per-focal-inversion matrix for the
  interchromosomal page) modes via the optional
  `karyotype_at_focal_inv` + `focal_inversion_id` columns. Producer
  picks which to emit; same envelope shape either way.

## 8. Decision rationale

- **Why `c_coincidence` is derivable, not required**: producers that already compute c (the canonical builder pipeline) can ship the column. Producers that have only `r_a`, `r_b`, `r_ab` save effort by letting the adapter derive. Either path produces the same envelope shape — consumers don't need to know which produced it.
- **Why `C > 3` is the artefact-flag threshold**: classical *Drosophila* and mouse interference patterns put `C` in [0, 1] (positive interference) or near 1 (independence). `C > 1` is "negative interference" — possible but rare. `C > 3` strongly suggests artifactual co-occurrence (mis-mapping, low n in either interval producing rate inflation, contamination, ploidy errors). Producers can override via `params.neg_interference_threshold`.
- **Why drop negative-rate rows silently**: rates are physically ≥ 0. A negative value is data corruption upstream (sign error, arithmetic underflow). The adapter coerces to null and the row's `c` stays null. The consumer sees these as missing data rather than as suspicious results.
- **Why interval ids are strings (not enforced format)**: producers vary in how they name intervals — equal-width windows might use `LG07_W1`, gene-boundary intervals might use `LG07_g1234`, recombination-hotspot intervals might use `LG07_HS_8.3Mb`. The adapter doesn't pretend to know the producer's convention; the ids just have to be stable strings.
- **Why `chrom` is a single field (no cross-chrom pair shape)**: the v1 use case is intrachromosomal coincidence — both intervals on the same chrom. A cross-chrom coincidence statistic exists in some literature but is rare; if needed, a v2 schema would replace `chrom` with `chrom_a` + `chrom_b`. v1 ships the simpler form.

## 9. Worked example

Suppose a producer emits 3 rows for `chrom = C_gar_LG07`, focal inversion `INV_A`, het carriers only:

| interval_a_id | interval_b_id | r_a  | r_b  | r_ab  | c (input)  |
|---|---|---|---|---|---|
| LG07_W1 | LG07_W2 | 0.05 | 0.04 | 0.001 | (omitted) |
| LG07_W1 | LG07_W3 | 0.05 | 0.06 | 0     | (omitted) |
| LG07_W2 | LG07_W3 | 0    | 0.06 | 0.002 | (omitted) |

The extractor derives `c_coincidence = r_ab / (r_a × r_b)`:

- Row 1: `0.001 / (0.05 × 0.04) = 0.001 / 0.002 = 0.5` → **positive interference** (C < 1, the normal Drosophila-style pattern)
- Row 2: `0 / (0.05 × 0.06) = 0.0` → no double-CO observed; could be sampling limitation (low n_offspring) or genuine total interference. Kept as 0.0 (not null) — the data DOES say zero.
- Row 3: `r_a = 0` → division by zero — `c` stays null (the adapter's guard at `normalize_coincidence_matrix.py`). The row is kept in the envelope but the renderer treats it as missing.

If `r_ab` had been `0.005` instead of `0.001` on row 1: `0.005 / 0.002 = 2.5` → still finite, **not flagged** (default threshold C > 3). If `r_ab = 0.01`: `0.01 / 0.002 = 5.0` → **flagged** in `n_neg_interference_flagged` and rendered red on the coincidence map.

Resulting summary block:

```
n_pairs                    = 3
n_chroms                   = 1
mean_c                     = (0.5 + 0.0 + null) → mean over non-null = 0.25
n_neg_interference_flagged = 0
```

The relatedness-atlas's `coincidence` page renders these 3 rows as cells in the LG07 heatmap: W1×W2 = light green (C = 0.5), W1×W3 = darkest green (C = 0.0), W2×W3 = greyed-out (C = null, missing data).

## 10. Failure modes

| # | condition | behaviour |
|---|---|---|
| 10.1 | Missing `chrom` | row dropped silently (required) |
| 10.2 | Missing `interval_a_id` or `interval_b_id` | row dropped silently (required) |
| 10.3 | `r_a = 0` (and `c_coincidence` not pre-computed) | `c` stays null per derivation guard; row kept in envelope as missing-data |
| 10.4 | `r_b = 0` | same as 10.3 |
| 10.5 | Negative rate (`r_a < 0`, etc.) | coerced to null per type-coercion table; row kept but `c` derivation produces null |
| 10.6 | `c_coincidence > params.neg_interference_threshold` (default 3) | flagged via `n_neg_interference_flagged`; renderer highlights in red |
| 10.7 | Cross-chrom pair (producer ships rows with `interval_a` and `interval_b` on different chroms) | not directly encoded — the schema requires a single `chrom` field. If a producer wants cross-chrom pairs, they need a v2 schema (out of scope for v1). |
| 10.8 | `karyotype_at_focal_inv` not in {homA, het, homB} | coerced to null; row treated as cohort-wide (un-stratified) |
| 10.9 | Same `(chrom, interval_a, interval_b)` appears under multiple focal inversions | kept (this is the karyotype-stratified case); consumer filters by `focal_inversion_id` |
| 10.10 | Identical `interval_a_id == interval_b_id` (self-pair) | allowed; producer-side decision whether to ship (`C` would be ill-defined for `r_ab == r_a`, but doesn't crash) |
| 10.11 | `c_coincidence` shipped by producer AND `r_a/r_b/r_ab` shipped, but values disagree | the shipped `c` wins; the derivable inputs are kept as diagnostic context but not re-derived. Producer is the source of truth when explicit. |
