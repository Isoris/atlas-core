# SPEC — Functional burden / selection efficacy: per-inversion-candidate overlay (v1)

**Status**: shipped 2026-05-20 (audit-sweep — atlas-side compute surface
fully shipping; per-candidate overlay-panel UI deferred). Promoted from
`specs_todo/` after the per-slice audit below. Original SPEC body is
preserved verbatim below as design archive.

**Implemented in:**
- [`atlases/inversion/shared/functional_burden.js`](../atlases/inversion/shared/functional_burden.js) — 15 exports covering the full per-candidate metric surface: `FUNCTIONAL_BURDEN_VERDICTS` / `FUNCTIONAL_BURDEN_TAGS` / `FUNCTIONAL_BURDEN_METRICS` / `FUNCTIONAL_BURDEN_TAG_METRICS` / `FUNCTIONAL_BURDEN_DEFAULTS` / `KARYOTYPE_GROUPS = ['STD/STD', 'HET', 'INV/INV']` / `FUNCTIONAL_BURDEN_MODULE_VERSION = 'functional_burden_per_candidate_v1.0'` (the SPEC's own version stamp), `aggregatePerSampleWithinCandidate()`, `summarizeByKaryotype()`, `pairwiseWilcoxonByKaryotype()`, `classifyMetricVerdict()`, `compositeSummaryTag()`, `summarizeCandidateFunctionalBurden()` (the SPEC's end-to-end entry point), `compareHomokaryotypePiToAll()`, `subsampleControlForHomokaryotypePi()`
- [`atlases/inversion/shared/wilcoxon.js`](../atlases/inversion/shared/wilcoxon.js) — supporting Wilcoxon rank-sum primitive
- [`atlases/inversion/shared/sigma_profile.js`](../atlases/inversion/shared/sigma_profile.js) — supporting σ-profile primitive
- [`atlases/inversion/shared/inheritance_compute.js`](../atlases/inversion/shared/inheritance_compute.js) — supporting inheritance primitive
- [`atlases/inversion/shared/contingency.js`](../atlases/inversion/shared/contingency.js) + [`atlases/inversion/shared/het_rate.js`](../atlases/inversion/shared/het_rate.js) — pre-existing dependencies
- Tests: [`tests/test_shared_functional_burden.js`](../tests/test_shared_functional_burden.js), [`tests/test_shared_wilcoxon.js`](../tests/test_shared_wilcoxon.js), [`tests/test_shared_sigma_profile.js`](../tests/test_shared_sigma_profile.js)
- Downstream documentation consumer: [`atlases/inversion/pages/catalogue/stats_profile.js`](../atlases/inversion/pages/catalogue/stats_profile.js) — 7 `derive_from:` references documenting which axes are computed via the functional_burden producer (the compute is wired up at the axis-definition level; a dedicated per-candidate overlay-panel UI has not shipped)

**Per-slice status:**

| slice | status | location |
|---|---|---|
| Per-sample aggregation within a candidate span | ✅ shipped | `aggregatePerSampleWithinCandidate()` |
| Per-karyotype-group summarisation (STD/STD, HET, INV/INV) | ✅ shipped | `summarizeByKaryotype()` + `KARYOTYPE_GROUPS` |
| Pairwise Wilcoxon rank-sum across karyotype groups | ✅ shipped | `pairwiseWilcoxonByKaryotype()` + `wilcoxon.js` |
| Per-metric verdict classifier (STRONG / MODERATE / WEAK / NONE per the verdict enum) | ✅ shipped | `classifyMetricVerdict()` + `FUNCTIONAL_BURDEN_VERDICTS` |
| Composite summary tag across metrics | ✅ shipped | `compositeSummaryTag()` + `FUNCTIONAL_BURDEN_TAGS` |
| End-to-end summary entry point | ✅ shipped | `summarizeCandidateFunctionalBurden()` |
| Homokaryotype-vs-all comparison + subsample control | ✅ shipped | `compareHomokaryotypePiToAll()` + `subsampleControlForHomokaryotypePi()` |
| Version stamp + defaults | ✅ shipped | `FUNCTIONAL_BURDEN_MODULE_VERSION` + `FUNCTIONAL_BURDEN_DEFAULTS` |
| Per-candidate overlay panel UI (the SPEC's title surface) | ⏳ deferred | No dedicated panel JS yet; `stats_profile.js` documents the compute hookpoints via `derive_from:` strings. The panel would call `summarizeCandidateFunctionalBurden()` and render the per-karyotype-group bars per SPEC. |
| Per-candidate producer JSON schema (`functional_burden` layer) | ⏳ deferred | Cluster-side; the compute is invocable from in-state per-window records today |

**Why archived now:** the SPEC's atlas-side compute surface ships
end-to-end (entry point `summarizeCandidateFunctionalBurden()`, verdict
classifier, composite tag, pairwise Wilcoxon, homokaryotype-vs-all
comparison, subsample control). The module's own version constant
matches the SPEC name (`functional_burden_per_candidate_v1.0`),
confirming the SPEC's contract is what was implemented. What's left is
a *page-side overlay panel* that invokes these primitives — and a
*cluster-side producer* that emits the per-window records. Both are
follow-up tasks owned by separate workstreams; this SPEC's
compute-layer contract is done.

**Scope**: per-inversion-candidate overlay panel that summarises
functional / deleterious-mutation burden per karyotype group
(STD/STD, HET, INV/INV). The same metric primitives also power the
Diversity Atlas "Functional burden / selection efficacy" page —
this spec only defines the **inversion-side overlay**.
**Builds on**: `atlases/inversion/shared/contingency.js`,
`atlases/inversion/shared/wilcoxon.js`,
`atlases/inversion/shared/het_rate.js`,
`atlases/inversion/shared/sigma_profile.js`,
`atlases/inversion/shared/inheritance_compute.js`.

**Authored**: drafted 2026-05-12.

---

## 0. The split: Diversity Atlas vs Inversion Atlas

The same five burden metrics serve two different questions on two
different atlases:

| Atlas | Question | Granularity |
|-------|----------|-------------|
| **Diversity Atlas** (main home) | What is the functional genetic health of each fish / family / ancestry group / population? | Per-fish, per-family, per-ancestry, per-population — whole-genome aggregates |
| **Inversion Atlas** (this spec) | Does this inversion arrangement carry more functional burden than its alternative? | Per (candidate × karyotype group) — restricted to the inversion's footprint |

The Diversity Atlas owns the metric definitions, the layer
producers, and the global per-fish summary. The Inversion Atlas
**reuses** those same producer outputs, **subset to each
candidate's bp range**, and stratifies by karyotype group instead
of by fish.

This way:

- No double-implementation of the metrics.
- No fish-level controversy bleeds into per-candidate panels.
- Per-candidate overlay always asks the same question:
  *"is this inversion sheltering load?"*

---

## 1. The five metrics

All five are computed per-window (bp interval) by the producer
side, then summarised per-candidate via window aggregation. The
inversion-side compute is **a thin aggregator**, not a re-implementation.

### 1.1 π — nucleotide diversity (baseline)

Average pairwise differences per site within a group of samples.
Per-window, per-group: π_g = (n choose 2)⁻¹ Σ_pairs d_ij.

**Role**: baseline / denominator. πN/πS and π0/π4 are ratios on
top of this; LOF/VESM/ROH burden compare against it for scale.

### 1.2 πS and πN — synonymous / non-synonymous diversity

- **πS**: π restricted to synonymous (4-fold degenerate) sites.
  Treated as ≈ neutral; reflects effective population size.
- **πN**: π restricted to non-synonymous sites. Under purifying
  selection, πN < πS.

**Ratio πN/πS** = selection-efficacy index. Lower = stronger
purifying selection on protein-coding variation.

### 1.3 π0-fold / π4-fold — degeneracy-class diversity

Equivalent re-framing using degenerate-position classes:

- **π0-fold**: π at 0-fold-degenerate sites (every change is
  non-synonymous).
- **π4-fold**: π at 4-fold-degenerate sites (every change is
  synonymous).

**Ratio π0/π4** = same selection-efficacy signal as πN/πS, but
more robust to codon-usage skews.

References (per user note): Harrang et al. 2013, Lohmueller 2014,
Do et al. 2015, Henn et al. 2015.

### 1.4 VESM deleterious burden

Count (or sum-of-score) of missense variants in protein-coding
sequence classified as deleterious by VESM (variant effect score
of missense mutations). One score per variant; per-sample burden =
Σ over the candidate's bp interval of (VESM_score × dosage).

**Role**: most direct molecular-impact measure. Already on the
roadmap for the Inversion Atlas (user note: "it will be on the
same page as VESM missense Deleterious").

### 1.5 LOF burden

Count (or sum-of-score) of loss-of-function variants (stop-gained,
splice-disruptor, frameshift, start-lost). Per-sample burden =
Σ over the candidate's bp interval of (dosage × indicator).

**Role**: complementary to VESM — captures variants too severe
for missense-impact scoring. Smaller N but larger per-variant
effect.

### 1.6 ROH-overlap burden

Fraction of the candidate's bp interval covered by per-sample runs
of homozygosity (ROH calls from the cohort-level ROH layer).

**Role**: identifies samples carrying the inversion within a
recently-co-inherited block — a recombination-suppression
diagnostic that's independent of variant calling.

---

## 2. Per-candidate stratification

For each candidate × karyotype group:

1. Resolve the per-sample karyotype call for the candidate (from
   the existing inversion-atlas pipeline: `STD/STD` /
   `HET` / `INV/INV` derived from K-means + dosage).
2. For each metric M ∈ {π, πN/πS, π0/π4, VESM_burden, LOF_burden,
   ROH_overlap}:
   - Aggregate the producer-side per-window M values within
     `[start_bp, end_bp]` of the candidate.
   - For each karyotype group g ∈ {STD/STD, HET, INV/INV},
     summarise across the samples in that group:
     - median
     - IQR
     - n samples
3. Test for between-group differences:
   - 3-group Kruskal–Wallis (or pairwise Wilcoxon: STD/STD vs
     INV/INV, STD/STD vs HET, HET vs INV/INV).
   - Effect sizes: median difference + bootstrap CI.

### 2.1 Worked example (single inversion)

```
INV_LG14_002 (pericentric, 12.4 Mb–19.7 Mb on chr_LG14)

Karyotype   n   π            πN/πS     VESM     LOF     ROH
─────────────────────────────────────────────────────────────
STD/STD    32   0.0042       0.18      4.1      0.3     0.04
HET        51   0.0061       0.21      5.0      0.4     0.07
INV/INV    18   0.0035       0.39      8.7      1.1     0.31
─────────────────────────────────────────────────────────────
KW p      —     0.003        2e-5      8e-7     0.001   3e-9
verdict   —     mixed        elevated  elevated elevated load-rich
```

Interpretation: INV/INV homozygotes show elevated πN/πS, VESM
burden, LOF burden, and dramatic ROH overlap → this inversion
**is sheltering load** (recombination suppression keeps mildly
deleterious variants linked).

---

## 3. Verdict / annotation

For each (candidate × metric) summary emit one of:

| Verdict          | Pattern                                            |
|------------------|----------------------------------------------------|
| `neutral`        | KW p ≥ 0.05 or all-group medians within ±10 %      |
| `inv_elevated`   | INV/INV median significantly > STD/STD median      |
| `inv_depleted`   | INV/INV median significantly < STD/STD median      |
| `heterosis_like` | HET median lowest among the three                  |
| `mixed`          | Two groups elevated, one depleted (rare)           |
| `underpowered`   | n_min < 5 in any group, or no producer layer present |

Per-candidate composite tag (across all 5 metrics):
- `load_rich`: ≥ 3 of {πN/πS, VESM, LOF, ROH} = `inv_elevated`.
- `clean`: ≥ 3 = `neutral`.
- `mixed`: otherwise.

---

## 4. Output schema

```jsonc
{
  "candidate_id": "INV_LG14_002",
  "inversion_type": "pericentric",
  "chrom": "LG14",
  "start_bp": 12400000,
  "end_bp":  19700000,
  "summary_tag": "load_rich",          // §3 composite
  "per_metric": {
    "pi":             { ... },         // shape below
    "pi_n_pi_s":      { ... },
    "pi0_pi4":        { ... },
    "vesm_burden":    { ... },
    "lof_burden":     { ... },
    "roh_overlap":    { ... }
  },
  "warnings": [],                       // missing-layer notes
  "created_at": "2026-05-12T10:00:00Z",
  "module_version": "functional_burden_per_candidate_v1.0"
}
```

Each `per_metric.<name>` row:

```jsonc
{
  "groups": {
    "STD/STD":  { "n": 32, "median": 0.0042, "iqr": [0.0030, 0.0061] },
    "HET":      { "n": 51, "median": 0.0061, "iqr": [0.0044, 0.0083] },
    "INV/INV":  { "n": 18, "median": 0.0035, "iqr": [0.0028, 0.0047] }
  },
  "kw_p":           0.003,             // Kruskal–Wallis p-value
  "pairwise": {
    "std_vs_inv":  { "wilcoxon_p": 0.45, "delta_median": -0.0007 },
    "std_vs_het":  { "wilcoxon_p": 0.001, "delta_median": 0.0019 },
    "het_vs_inv":  { "wilcoxon_p": 6e-4, "delta_median": -0.0026 }
  },
  "verdict": "mixed",
  "n_windows": 73                       // number of windows aggregated
}
```

---

## 5. Where this fits in the cartridge

### 5.1 Producer side (NOT this spec)

The Diversity Atlas owns the layer producers. Five layers feed the
inversion-side aggregator:

```
evidence_registry/diversity/
  pi_per_window_v1.json
  pi_syn_per_window_v1.json
  pi_nonsyn_per_window_v1.json
  vesm_per_variant_v1.json
  lof_per_variant_v1.json
  roh_per_sample_v1.json
```

Each layer is per-window or per-variant — the aggregator subsets
to a candidate's bp range and joins on sample_id.

### 5.2 Inversion-atlas consumer (this spec)

```
atlases/inversion/
  analysis/
    functional_burden_per_candidate.js   # NEW — thin aggregator
      runFunctionalBurdenPerCandidate({registry, candidate_id, ...})
  pages/review/
    functional_burden_panel/             # NEW — panel renderer
      render.js
      legend.js
  registries/schemas/
    functional_burden_per_candidate.schema.json   # NEW
  shared/
    (no new module — primitives exist:
       contingency.js#chiSquare / kruskalWallis-via-wilcoxon
       wilcoxon.js#mannWhitneyU
       het_rate.js for sample dosage lookups)
```

The aggregator is a Mendelian-inheritance-style orchestrator
(see `analysis/mendelian_inheritance.js` for the canonical pattern):

1. Resolve candidate + karyotype calls (already cached).
2. Resolve each of the 5 producer layers (degrades gracefully when
   absent → `underpowered` verdict + warning).
3. Subset windows / variants to the candidate's bp range.
4. Stratify by karyotype group.
5. Per-metric: KW + pairwise Wilcoxon (existing wilcoxon.js).
6. Compose verdicts + summary_tag.
7. Write back through registry as
   `functional_burden_per_candidate` block.

---

## 6. UI panel: "Functional consequence of this inversion"

A single panel on the candidate-review page (`pages/review/`).
Three-row layout, one row per karyotype group:

```
STD/STD  n=32  ●  π 0.0042   πN/πS 0.18   VESM 4.1   LOF 0.3   ROH  4 %
HET      n=51  ●  π 0.0061   πN/πS 0.21   VESM 5.0   LOF 0.4   ROH  7 %
INV/INV  n=18  ●  π 0.0035   πN/πS 0.39   VESM 8.7   LOF 1.1   ROH 31 %
                              [elevated] [elevated] [elev.]  [load-rich]
                              KW p=2e-5  KW p=8e-7  p=1e-3   p=3e-9
                  Summary: this inversion is LOAD-RICH on INV/INV.
```

- Group medians as numbers with the verdict chip next to each
  metric column.
- Composite `summary_tag` shown as a header chip.
- One-click drill-down to the Diversity Atlas "Functional burden /
  selection efficacy" page, pre-scoped to the candidate's bp
  range — so the user can compare per-fish detail.

---

## 7. Cross-candidate cohort view (deferred to v2)

Once per-candidate rows are populated for the full cohort, the
review page gains a sortable table column "Burden tag" + filters
for `load_rich` candidates. The same data also feeds a
para-vs-peri test for "do pericentric inversions shelter more
load than paracentric?" — a structural-biology question that
mirrors SPEC_mendelian_inheritance_para_vs_peri_v1 §3.

```
2×2 table (load_rich vs clean × para vs peri):

             load_rich   clean
paracentric        7       18
pericentric       15        9
```

Fisher's exact (via `shared/contingency.js#fisher2x2`).

---

## 8. Statistical notes

- **πN/πS at the candidate scale**: ratios are noisy when N or S
  variant counts are small. The aggregator emits a `low_n_variants`
  warning when |Σ S variants| < 30 in any group.
- **VESM/LOF burden vs gene length**: burden scales with the number
  of coding bases in the inversion. Within a single candidate
  this is a constant across karyotype groups, so the comparison
  is fair. Cross-candidate comparisons (deferred v2) need to
  normalise by coding-base count.
- **ROH-overlap and karyotype call**: ROH calls and karyotype
  calls share inputs (homozygosity). A circular signal could
  arise — the aggregator emits a `roh_overlap_high` warning when
  > 80 % of INV/INV samples are inside an ROH (suggests the
  signal is mostly ROH-driven, not inversion-driven).
- **HET-group middle position**: under simple dominance, HET sits
  between the homozygotes. Strong deviation → epistasis or
  recombination-suppression heterosis. The `heterosis_like`
  verdict captures this.

---

## 9. Implementation steps (rough)

1. Diversity Atlas producers ship `pi_per_window_v1.json` and
   `pi_syn|nonsyn_per_window_v1.json` (one shared schema). (out of
   scope for this spec — Diversity Atlas owns.)
2. VESM + LOF + ROH layers wired through the registry.
3. `atlases/inversion/analysis/functional_burden_per_candidate.js`
   (~150 lines) — orchestrator following `mendelian_inheritance.js`
   pattern.
4. `atlases/inversion/registries/schemas/functional_burden_per_candidate.schema.json`
   to validate the §4 payload.
5. Panel renderer in `pages/review/functional_burden_panel/`
   — three-row grid, verdict chips, drill-down link.
6. Test fixture: candidate with 2 of 6 layers missing → confirms
   `underpowered` verdict on the absent metrics, full verdict on
   the rest.

---

## 10. Manuscript sentence

> For each inversion candidate we summarised the functional
> burden carried by each karyotype group (STD/STD, HET, INV/INV)
> using five complementary metrics: nucleotide diversity (π),
> the non-synonymous / synonymous diversity ratio (πN/πS, with
> π0-fold / π4-fold as a degeneracy-class alternative), VESM-based
> deleterious-missense burden, loss-of-function burden, and run-of-
> homozygosity overlap. Per-candidate Kruskal–Wallis tests
> assessed whether burden differs across karyotype groups,
> allowing inversions that shelter functional load (recombination
> suppression linking mildly deleterious variants) to be
> identified separately from neutral structural polymorphisms.

---

## 10b. Cross-reference: log–log πN/πS vs πS plot (Diversity Atlas)

The canonical nearly-neutral-theory diagnostic — a log(πN/πS) vs
log(πS) scatter with slope = −β (DFE shape parameter, gamma model;
Kimura 1979, Welch et al. 2008, Romiguier et al. 2014) — belongs
on the **Diversity Atlas** "Functional burden / selection
efficacy" page, **not** on the inversion-atlas panel. The
inversion-side overlay defined in this spec links to that
Diversity-Atlas plot (one-click drill-down, §6) but does not
duplicate it.

The Diversity Atlas owns: producer-side π / πN / πS layers, the
log–log regression fit, the bin-mean residual-linearity check,
the bootstrap CI on β, and the manuscript sentence anchoring the
nearly-neutral interpretation.

---

## 11. Deferred to v2

- Allele-frequency-weighted versions of VESM/LOF (per Henn 2015):
  emphasises rare-variant load.
- Per-gene drill-down inside a candidate (which genes carry the
  burden).
- Mutation-load polarisation against the ancestral karyotype (needs
  reconstructed ancestor — see SPEC_inversion_age_atlas).
- Linkage of `load_rich` × `recombination_suppressed` ×
  `dxy_elevated` for a coherent "old, sheltered" inversion class.
