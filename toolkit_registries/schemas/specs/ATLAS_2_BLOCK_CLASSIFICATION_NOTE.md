# Atlas 2.0 — block classification extension (rationale note)

> Companion to `block_alt_evidence.schema.json` and
> `block_classification.schema.json`. Extends the v2 Q7 framework. Not a
> rewrite — these two block_types are additive.

## Why

Local PCA clusters individuals wherever they carry different long
haplotypes. It does not care whether the haplotype was produced by a
classical inversion, a tandem-repeat expansion / contraction, a
higher-order-repeat (HOR) array variant, a segmental duplication, a CNV,
pericentromeric recombination suppression, collapsed paralogous mapping,
introgressed haplotype, or an ancient structural polymorphism. The same
local-PCA signal can have any of these architectural causes, and the
biology is not the same.

The v2 registry already addresses *whether* a candidate is real — that is
the Q7 existence question, answered by `existence_layer_a/b/c/d` and
`hypothesis_verdict`. What it does not have is a structured way to capture
*which architectural mechanism the candidate is most consistent with*. A
candidate that passes Q7 existence on local-PCA + GHSL evidence may still
be (a) a clean inversion, (b) a repeat-architecture haplotype, (c) an
SD-mediated NAHR system, (d) a CNV-driven signal, or (e) an artefact of
low mappability. Reporting all of these as "inversions" is the
overclaiming problem this extension addresses.

## Two new block types

- `block_alt_evidence` — raw measurements: TR / HOR / SD / gene / ncRNA
  overlap percentages, `mean_depth_ratio`, `low_mappability_pct`,
  `centromere_candidate_distance_bp`, `n_localpca_clusters`,
  `cluster_FST_like`, `HWE_FIS_pattern`. Inputs only; no class call.
- `block_classification` — the call: `class_primary` ∈ { INV_LIKE,
  TR_ASSOCIATED, HOR_ASSOCIATED, SD_ASSOCIATED, CEN_PERI_ASSOCIATED,
  CNV_LIKE, MIXED, ART_RISK }, plus `class_secondary`, `class_confidence`,
  `rationale_codes`, `depends_on_blocks`.

The split mirrors the existing `block_detect` (raw) ↔ `hypothesis_verdict`
(call) separation in v2.

## Relationship to v2's Q7

`block_classification` does **not** supersede `hypothesis_verdict`.
`hypothesis_verdict` answers "does this signal exist as a real
non-artefact"; `block_classification` answers "which mechanism is most
consistent with it." A block can pass `hypothesis_verdict` with
high-confidence existence and still be classified as `SD_ASSOCIATED` or
`MIXED` rather than `INV_LIKE`. Both calls are reported.

A defensible classification requires at least `block_alt_evidence` plus
`existence_layer_a`; without `block_alt_evidence` the classifier cannot
distinguish `INV_LIKE` from the alternative classes and must not be run.

## Class criteria (informal)

These are the criteria the classifier should encode; the formal
boundaries are intentionally not pinned in the schema, since
calibration depends on the cohort and on the TR / HOR / SD annotation
quality.

| Class                  | Pattern                                                                              |
|------------------------|--------------------------------------------------------------------------------------|
| `INV_LIKE`             | `n_localpca_clusters == 3`, `HWE_FIS_pattern == balanced_three_class`, low TR/HOR/SD/CNV overlap, `mean_depth_ratio ≈ 1`, low `low_mappability_pct`. |
| `TR_ASSOCIATED`        | Appreciable `tr_overlap_pct`; cluster structure consistent with repeat-length variation. |
| `HOR_ASSOCIATED`       | Appreciable `hor_overlap_pct`; usually `n_localpca_clusters > 3`.                    |
| `SD_ASSOCIATED`        | Appreciable `sd_overlap_pct`; raises NAHR mechanism prior; pairs with `mechanism` block. |
| `CEN_PERI_ASSOCIATED`  | Small `centromere_candidate_distance_bp`; overlap with pericentromeric architecture. |
| `CNV_LIKE`             | `mean_depth_ratio` markedly off 1, AND cluster membership correlates with depth.     |
| `MIXED`                | Inversion-like local-PCA AND strong repeat / SD overlap. Set `class_secondary` to the runner-up. |
| `ART_RISK`             | High `low_mappability_pct`; signal not defensible without orthogonal evidence.       |

`MIXED` is often the most useful category — many real long-range
haplotypes are inversion-like *and* repeat-rich, and committing to a
single mechanism on local-PCA alone would be overclaiming.

## Naming discipline

- `cluster_FST_like` (not bare `cluster_FST`): the contrast is over
  inferred local-PCA clusters, not declared populations, and is not a
  population-genetic FST estimator. Mirrors `arrangement_FST_like` used
  elsewhere in this registry.
- `HWE_FIS_pattern` (not bare `HWE_pattern`): the pattern is
  summarised at the inbreeding-coefficient level (FIS), so the field
  name names what is being summarised.

## For the discussion

A defensible framing for any chapter / paper that uses this:

> Some local-PCA blocks initially classified as inversion-like may
> represent a broader class of long-range haplotype structures associated
> with tandem repeats, higher-order repeat arrays, and segmental
> duplications. These regions may still be biologically meaningful, but
> their maintenance may reflect repeat architecture, copy-number
> variation, chromosomal mechanics, recombination suppression, or
> segregation-related processes rather than classical gene-level
> balancing selection alone.

This is the framing the `block_classification` enum is designed to
support — and to keep honest, by making the alternative classes
first-class in the registry rather than dismissed footnotes.
