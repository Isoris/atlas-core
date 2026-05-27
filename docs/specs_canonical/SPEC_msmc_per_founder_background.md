# SPEC — MSMC demographic validation per founder-like background

**Status**: SPEC ONLY — confirmed unimplemented after 2026-05-21 audit.
Stays in `specs_todo/` (no shipped code to archive). Audit findings
below; SPEC body preserved verbatim from the 2026-05-19 chat origin.

**Audit summary (2026-05-21):**

No part of the MSMC-per-founder pipeline is implemented anywhere in the
codebase. Grep across `inversion-atlas/`, `atlas-core/`,
`Specs_WIP_modules/`, and `catfish-inversion-analysis/` returns zero
hits for `founder_population` / `founder_background` / `regime_sharing_matrix`
/ `per_founder` / `inversion_masked` / `masked_msmc` outside this SPEC's
own text.

The single MSMC-adjacent file in the repo —
[`atlases/inversion/shared/mgl_founder_consensus.js`](../atlases/inversion/shared/mgl_founder_consensus.js)
(265 lines) — solves a **different** problem: per-site founder-like
allele frequency for inversion *arrangements* (dosage consensus within
an INV class). It does not group samples by demographic background and
does not feed MSMC. Naming overlap only.

**Blockers (in build order):**

| step | what it requires                                                       | status |
|------|------------------------------------------------------------------------|--------|
| 1    | Regime-sharing matrix (per-(sample × sample) regime-co-occurrence)    | ⏳ not shipped — upstream input the SPEC reuses from `pca_comparator/heatmap.js`'s per-window band labels |
| 2    | Sample clustering on the regime-sharing matrix → founder-like groups   | ⏳ not started |
| 3    | Per-founder MSMC config writer (with inversion intervals masked)       | ⏳ not started — would live producer-side in catfish-inversion-analysis |
| 4    | MSMC runner + per-founder Ne(t) output collation                       | ⏳ not started — external tool |
| 5    | Atlas page consumer (overlay Ne(t) curves per founder)                 | ⏳ not started |

**Closest existing primitives** (would be inputs / reused machinery,
not implementations):
- [`atlases/inversion/pages/discovery/pca_comparator/heatmap.js`](../atlases/inversion/pages/discovery/pca_comparator/heatmap.js)
  — per-(sample × window) dosage K-band labels via `windowToL2[w] →
  getL2Cluster(state, l2).labels`. Step 1's regime-sharing matrix
  would be derived from these.
- [`atlases/inversion/shared/regimes_registry.js`](../atlases/inversion/shared/regimes_registry.js) — regime catalog
- [`atlases/inversion/shared/boundary_evidence.js`](../atlases/inversion/shared/boundary_evidence.js) — regime-boundary primitives

**Recommended sequencing**: ship Step 1 (regime-sharing matrix
producer) FIRST as a standalone deliverable. It has standalone value
(visualisable as a sample-similarity heatmap) and unblocks Steps 2–5
on its own timeline. Don't start MSMC config-writing until real founder
clusters are observable in Step 1's output — premature implementation
would lock in a clustering choice before any data validates it.

**Companion specs**:
- `SPEC_local_pca_comparator.md` (the band-persistence heatmap is the
  upstream visual; this SPEC reuses its per-window band assignments
  as the input to the regime-sharing matrix)
- `SPEC_regime_annotation_v34.md` (downstream regime classification)

## User question

> "long-range haplotype regimes → identify putative founder populations
> → run MSMC per putative founder population → exclude inversions →
> infer Ne and population history. its just so we get our matrix after
> the long range regime which basically will help for the MSMC eventually"

## The problem this SPEC fixes

Naive MSMC on a mixed sample pool (and naive "one Ne per chromosome")
both produce misleading demographic histories. Two failure modes:

1. **Mixed-pool failure.** MSMC infers Ne(t) and split times from
   genome-wide coalescence patterns. If the sample contains hidden
   ancestries (multiple source populations, hatchery founders,
   introgressed lineages), deep coalescence *between* backgrounds gets
   read as ancient large Ne, a population split, or a bottleneck —
   none of which are demographic events in the modern population. For
   a 226-sample catfish atlas this is the dominant risk.

2. **Per-chromosome Ne failure.** Chromosomes differ in recombination
   rate, inversion content, ROH burden, callability, and
   mappability. "Ne(chr1) vs Ne(chr2)" curves mostly report
   *chromosome-level genomic behavior*, not population history. The
   population has *one* demographic history; chromosomes are noisy
   samples of it.

The correct unit is **ancestry group → one Ne history**, computed on
**neutral collinear callable regions** after excluding inversions, LRRs,
centromeric repeats, low-mappability windows, and long ROH segments.

## Naming discipline

Throughout this SPEC and the eventual UI/producer outputs, call the
groups:

- **putative founder-like ancestry groups** (atlas headline)
- **founder-like backgrounds** (figure labels)

Never **wild populations**, **founder populations**, or **source
populations** in atlas-shipped JSON/UI text. Reason: a long-range
haplotype regime in a hatchery/mixed cohort can equally represent a
real source population, a family-founder haplotype, an introgressed
background, an inversion arrangement, a recent relatedness block, or a
selection-maintained haplotype. The atlas-side label must reflect that
classification uncertainty until a downstream classifier resolves it.

## Pipeline

```
long-range haplotype regimes               (already shipped: pca_comparator heatmap)
        │
        ▼
sample × sample regime-sharing matrix      (new producer)
        │
        ▼
cluster → founder-like backgrounds         (new producer)
        │
        ▼
exclude inversions / LRR / ROH /           (new producer; reuses
repeats / bad-callability                  boundary_evidence + ROH calls)
        │
        ▼
select clean unrelated representatives     (new producer)
        │
        ▼
MSMC / MSMC2 per group                     (heavy compute — cluster-side)
        │
        ▼
validate with π / Watterson / Tajima's D   (existing primitives + new
/ LD decay / FHOM / FROH / private          aggregations)
alleles / heterozygosity
        │
        ▼
atlas page: founder_background_panel       (new page; reads JSONs)
```

## Producer outputs (cluster-side)

All under `out/founder_demography/` per atlas, written by a new LANTA
step (`STEP_F01_founder_backgrounds`).

### 1. `regime_sharing_matrix.json`

Pairwise long-range regime sharing across neutral windows.

```jsonc
{
  "n_samples": 226,
  "samples": ["si0001", "si0002", ...],        // sample IDs aligned to matrix rows/cols
  "n_windows_used": 184221,                    // total neutral comparable windows
  "n_windows_excluded": {
    "candidate_inversions": 32104,
    "low_recombination":    18550,
    "roh_heavy":             4203,
    "low_mappability":       8907,
    "low_callability":       2118,
    "repeats":               9482
  },
  "method": "dosage_kband_majority",           // which regime label was used
  "regime_label_source": "local_pca_dosage",   // future: theta_pi, ghsl
  "matrix": {
    "shape": [226, 226],
    "dtype": "float32",
    "encoding": "flat",
    "values": [/* 226*226 floats in [0,1], row-major */]
  }
}
```

**Sharing definition**:
```
sharing[i][j] = (# neutral windows where i and j carry same regime label)
              / (# neutral windows comparable for both i and j)
```

A "comparable window" requires both samples to have a valid (non-null)
regime label at that window AND the window to pass the neutral mask.

### 2. `founder_groups.json`

Output of clustering the sharing matrix.

```jsonc
{
  "n_groups": 3,
  "group_labels": ["A", "B", "C"],
  "sample_assignment": {
    "si0001": { "group": "A", "confidence": 0.92, "is_mosaic": false },
    "si0002": { "group": "MOSAIC", "confidence": 0.41, "is_mosaic": true },
    ...
  },
  "per_sample_composition": {
    "si0001": { "A": 0.92, "B": 0.05, "C": 0.03 },
    ...
  },
  "group_summary": [
    {
      "group": "A",
      "n_samples": 78,
      "mean_within_group_sharing": 0.81,
      "mean_cross_group_sharing":  0.34,
      "qc": { "family_hub_fraction": 0.18, "roh_outlier_fraction": 0.04 }
    },
    ...
  ],
  "clustering_method": "spectral_k=auto",
  "cluster_quality": { "silhouette": 0.41, "modularity": 0.39 }
}
```

A sample is **mosaic** if its top-group share is < 0.7 or no single
group dominates by ≥ 0.2 over the next. Mosaic samples are excluded
from MSMC inputs by default but stay visible on the atlas page.

### 3. `clean_msmc_representatives.json`

The per-group sample shortlist actually fed to MSMC.

```jsonc
{
  "groups": {
    "A": {
      "selected_samples": ["si0014", "si0067", "si0099", "si0152"],
      "rejected": [
        { "sample": "si0033", "reason": "kinship > 0.10 with si0014" },
        { "sample": "si0088", "reason": "FROH > 0.15" }
      ],
      "selection_criteria": {
        "max_pairwise_kinship": 0.10,
        "max_froh":             0.15,
        "min_coverage_x":       15,
        "max_callability_drop": 0.05
      }
    },
    ...
  }
}
```

### 4. `msmc_per_group/{group}.json`

Standard MSMC2 output per group, plus metadata.

```jsonc
{
  "group": "A",
  "input_samples": ["si0014", "si0067", "si0099", "si0152"],
  "genome_mask": {
    "callable_bp":             1.84e9,
    "excluded_inversion_bp":   3.20e7,
    "excluded_lrr_bp":         1.85e7,
    "excluded_roh_bp":         4.20e6,
    "excluded_repeat_bp":      9.48e6,
    "excluded_mappability_bp": 8.91e6
  },
  "ne_curve": {
    "t_generations": [/* time bins */],
    "ne":            [/* per-bin Ne estimates */],
    "ne_lower":      [/* bootstrap CI lower */],
    "ne_upper":      [/* bootstrap CI upper */]
  },
  "cross_coalescence": null,        // set when this is a pair file
  "mutation_rate":     7.89e-9,
  "generation_time_y": 4,           // catfish-appropriate value
  "msmc_version":      "msmc2 2.1.4"
}
```

### 5. `msmc_pair_cross_coalescence/{groupA}_{groupB}.json`

Cross-coalescence between groups → approximate separation timing.

### 6. `founder_diversity_validation.json`

Per-group diversity metrics for cross-validation of MSMC Ne curves.

```jsonc
{
  "per_group": {
    "A": {
      "theta_pi_mean":    0.0042,
      "theta_w_mean":     0.0048,
      "tajimas_d_mean":  -0.32,
      "ld_decay_50pct_kb": 18.2,
      "froh_mean":        0.061,
      "fhom_mean":        0.018,
      "private_alleles":  1.2e5,
      "het_mean":         0.71
    },
    ...
  }
}
```

The atlas page's interpretation text combines MSMC Ne and these
metrics — the spec explicitly forbids "MSMC proves drift" in any UI
text. The acceptable formulation is the conjunction:

> "Group A has lower Ne in MSMC, lower π, higher LD, and higher FROH —
> consistent with stronger drift / bottleneck / inbreeding."

### 7. `msmc_chromosome_loo_qc.json`

Sensitivity check (NOT the main result):

```jsonc
{
  "per_group": {
    "A": {
      "full_genome":      { "ne_curve": [...] },
      "leave_out_chr1":   { "ne_curve": [...] },
      "leave_out_chr2":   { "ne_curve": [...] },
      ...
      "max_relative_drift": 0.18    // largest deviation across LOO runs
    }
  }
}
```

If `max_relative_drift > 0.30` for a group, the page surfaces a
"sensitive to chromosome leave-out" badge — that group's curve is
disproportionately driven by one chromosome and should be interpreted
with caution.

## Neutral-region mask (shared with other modules)

The same `neutral_collinear_callable_mask.bed` is reused by:

- regime-sharing matrix
- MSMC input
- π / Watterson / Tajima's D / LD decay (per-group)

Exclusion sources, listed in priority order:

1. **Candidate inversions / LRRs** — from the inversion atlas's own
   regime registry (`regimes_registry.js`) and boundary calls
   (`boundary_evidence.js`). This is the most important exclusion;
   the SPEC's whole point is that you must NOT define the population
   with the same regions you then feed to MSMC (circular logic).
2. **Low recombination regions** — from the species recombination map.
3. **Centromeric / pericentric repeats** — RepeatMasker output.
4. **Low-mappability windows** — typically GEM mappability ≤ 0.9.
5. **Low-callability windows** — per-window callable-fraction < 0.8
   across all samples in the cohort.
6. **Long ROH segments (per-sample basis)** — sample × window mask;
   each sample's own long-ROH segments are masked when that sample
   contributes to a group's MSMC input.

Output: a per-window boolean mask (`neutral_keep[w]`), plus a
per-sample × window boolean for ROH masking (`roh_keep[si][w]`).

## Atlas-side page: `founder_background_panel`

New page, stage `discovery_3` (or `analysis` — TBD when wired). Layout:

```
┌────────────────────────────────────────────────────────────────────┐
│  Founder-like ancestry backgrounds (putative)                       │
│  · 3 groups · 184221 neutral windows · 72954 excluded                │
├──────────────────────────────────┬──────────────────────────────────┤
│  sample × sample regime-sharing  │  per-sample composition          │
│  heatmap (clustered)             │  stacked bar (A/B/C/mosaic)      │
│                                  │                                   │
│  clusters: A (78) B (94) C (32)  │  click sample → drill page-1      │
│  + mosaic (22)                   │                                   │
├──────────────────────────────────┴──────────────────────────────────┤
│  excluded-regions track (chromosome × bp)                             │
│  inversions / LRR / repeats / low-mappability / low-callability       │
├──────────────────────────────────────────────────────────────────────┤
│  Ne curves per group (MSMC2)                                         │
│    Group A ──   Group B ──   Group C ──   (with bootstrap bands)     │
│  Time: 1e3 — 1e6 generations ago                                     │
│  ⓘ Sensitivity badge: Group B "chromosome-LOO drift = 0.34"           │
├──────────────────────────────────────────────────────────────────────┤
│  Diversity validation table                                          │
│  Group │ π     │ θ_W   │ Tajima D │ LD½ (kb) │ FROH │ FHOM │ private │
│  A     │ ...   │ ...   │ ...      │ ...      │ ...  │ ...  │ ...     │
│  B     │ ...                                                          │
│  C     │ ...                                                          │
├──────────────────────────────────────────────────────────────────────┤
│  Cross-coalescence matrix                                            │
│  approximate separation times A↔B, A↔C, B↔C                           │
└──────────────────────────────────────────────────────────────────────┘
```

**Interactions**:
- Hover sample on heatmap → highlights its row in composition bar,
  badges its group in Ne curves, and (cross-page) sets
  `state.hoveredSample` so the `pca_comparator` heatmap sees it too.
- Click sample → drills to `candidate_focus` page filtered to that
  sample's mosaic windows (if mosaic).
- Click excluded region → drills to its source page (inversion → page-1
  candidate; LRR → boundary_evidence panel).

**Read-only**. Writes nothing — pure JSON consumer.

## Atlas-side reuse of upstream primitives

| Need | Existing primitive | Status |
|------|--------------------|--------|
| per-(sample × window) dosage band labels | `pca_comparator/heatmap.js`'s `_buildLabelMatrix()` | shipped — extract into `shared/regime_label_matrix.js` for reuse |
| K-band coloring | `shared/page1_data_helpers.js` `groupColor()` | shipped |
| Inversion candidate exclusion list | `shared/regimes_registry.js` + `boundary_evidence.js` | shipped (partial) |
| ROH calls | (none) | producer-side step needed |
| Mappability / callability tracks | (varies per atlas) | producer-side step needed |

## Forbidden patterns (lint these in code review)

1. **No "wild population" labels** in atlas-side JSON, page text, or
   figure captions — always "putative founder-like ancestry group".
2. **No "one Ne per chromosome" headline figure.** Chromosome-LOO is a
   sensitivity badge, not a deliverable.
3. **No MSMC run on a sample pool that mixes groups.** If unclassified
   samples need a single Ne curve, run it on the *full callable
   genome* with a clear "ungrouped, pooled" disclaimer — and never
   present it as the demographic history.
4. **No MSMC run on regions defined by the same regime used to
   classify the group.** Inversion-defined groups must have inversion
   regions masked from MSMC input. The page enforces this via
   `genome_mask.excluded_inversion_bp > 0` being required for any
   group whose definition involves an inversion.
5. **No "MSMC proves X" interpretation.** The acceptable conjunction
   is "lower MSMC Ne + lower π + higher LD + higher FROH → consistent
   with stronger drift".

## Open questions (for audit before implementation)

1. **Clustering method.** Spectral on the sharing matrix, or NMF on
   the regime-composition tensor, or graph-community (Louvain) on a
   thresholded sharing graph? Spectral is simplest; NMF gives
   per-sample composition vectors directly; Louvain auto-picks `k`.
   Default proposal: **spectral with `k` chosen by eigengap, then
   compute composition by soft-cluster reassignment**.

2. **Regime-label source.** SPEC ships v1 with dosage K-band majority
   per window. A v2 should compose dosage + θπ + GHSL into a
   per-window 3-tuple regime label, with sharing computed on the tuple
   (or on each axis separately, three matrices). Defer to v2.

3. **Generation time / mutation rate.** For the channel catfish atlas:
   tentative `mu = 1.0e-8` per site per generation, `g = 4 years`.
   Both need cross-checking against the species-specific literature
   before any MSMC curve ships to a user-facing page.

4. **Bootstrap.** MSMC2 supports block-bootstrap; spec defaults to 100
   bootstrap replicates, 1Mb blocks. Producer step records the seed.

5. **Family-hub deflation.** Even after the kinship-based exclusion,
   a group dominated by 2-3 family hubs may still have inflated
   coalescence at recent times. Add a per-group "family hub fraction"
   QC field; if > 0.3 the page surfaces a "family-hub-skewed" badge.

## Out of scope for this SPEC

- Recombination-map inference itself (assumed input).
- ROH calling pipeline (assumed input).
- Phasing pipeline (assumed input — MSMC2 needs phased haplotypes).
- Cross-species demographic comparison (a separate `comparative_*`
  page would consume these per-atlas outputs).

## Why this connects to the inversion atlas at all

Inversions distort local coalescence. A demographic history that
ignores them assigns inversion-driven deep coalescence to ancestral
demography. Conversely, a demographic history that includes inversions
without masking them mis-locates Ne troughs. The atlas already knows
where the inversions are; this SPEC closes the loop by feeding that
knowledge into the MSMC input mask and surfacing the corrected Ne
curves as a first-class atlas page. The long-range regime view is what
makes the *grouping* defensible; the inversion mask is what makes the
*Ne curve* defensible. Both halves are needed.
