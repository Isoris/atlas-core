# SPEC — KBC: Karyotype Burden Contrast

**Status:** SPEC ONLY — awaiting audit before implementation.
**Version:** v0.8 (three-tier damaging-variant definition: Tier 1
high-confidence LoF as headline; Tier 2 LoF + validated splice
Class A as robustness; Tier 3 LoF + splice + strong missense as
exploratory. Splice-validation six-check gate added at §1.9. Manuscript
headline = Tier 1 only; tier-stability column added to table E.)
v0.7 (per-inversion as independent test unit, no pooled raw counts,
dN/dS exclusion, across-inversion summary table F)
v0.5 (split from IHC v0.4 — sibling spec to HPP)
**Sibling spec:** `HPP_SPEC.md` (Haplotype Projection from Pedigree)
**Scope:** `MS_Inversions_North_african_catfish` — 226-sample pure
*C. gariepinus* hatchery cohort, ~9× WGS, joint VCF, candidate inversions
with PCAngsd K=3 karyotype calls and L / M / R POD partitioning already
available.
**Position in stack:** downstream of `MODULE_CONSERVATION`
(SnpEff / SIFT4G / VESM / splice module / scoring weights) and the
inversion atlas (karyotype calls, candidate intervals, POD segments).
**Repo home (proposed):** `catfish-variant-analysis/Modules/NN_kbc/`.
**Manuscript role:** **headline POD result** — feeds v20 directly.

---

## 0. One-line goal

> For each candidate inversion, test whether AA and BB homozygotes show
> higher hom-exposed deleterious load than AB heterozygotes, segment by
> segment (L / M / R for double-CO PODs, whole for single-CO). This is
> the POD-compatible structural-mutational signal — distinct from any
> claim about selection or fitness.

---

## 1. Conceptual overview

### 1.1 What KBC is

A cohort-level burden contrast across the three karyotype classes of
each candidate inversion. The unit of analysis is
**inversion × karyotype class × POD segment**. The headline number is
**`exposure_delta_vs_AB`**: how much more hom-exposed deleterious load
an AA or a BB sample carries, on average, than an AB sample in the same
segment. The headline complementation number is the **AB
`complementation_index`**: the fraction of damaging genes where hap-A
and hap-B carry *different* damaging variants — the POD-compatible
masking signal.

### 1.2 The biology

Most deleterious coding variants are recessive or partially recessive:
a damaging allele on one chromosome copy is usually masked at the
protein-function level when the other copy is intact and produces
functional protein. A homozygous (or compound-heterozygous in trans)
damaging configuration is exposed — no backup.

Inside an inversion, the two arrangements have accumulated different
deleterious-variant sets under recombination suppression (Muller's
ratchet — the expected null, neutral or otherwise). Therefore:

- **AA homozygote** — both copies arrangement A → hom-exposed at A-private damaging sites.
- **BB homozygote** — both copies arrangement B → hom-exposed at B-private damaging sites.
- **AB heterozygote** — hap-A carries A-private set, hap-B carries B-private set → at each gene, one copy damaged and the other intact → het-masked. AB is the **masking reference**.

The defensible claim from this contrast is:

> The two inversion haplotypes carry non-overlapping deleterious variant
> sets; homozygotes for either arrangement expose haplotype-private
> recessive load that is masked in AB heterozygotes by gene-level
> complementation between the two arrangement backgrounds. This pattern
> is consistent with pseudo-overdominance maintaining inversion
> polymorphism, although direct fitness measurement is not available
> in this cohort.

KBC does not claim balancing selection. Does not claim fitness. Does not
use HWE deviation as evidence. The interpretation level is
**POD-compatible**, never "POD found".

### 1.3 Why "het count inside inversions" is the wrong response variable

Inside an inversion, AB heterozygotes carry more heterozygous variants
per sample than AA or BB — at every variant class, neutral and
synonymous as well as deleterious — because the two arrangements have
diverged under recombination suppression. Reporting "AB has more het
deleterious variants than AA / BB" is therefore a karyotype tautology
at the variant level, not a load measurement.

The biologically meaningful summary is **gene-level**:

| Level | Quantity | Use for headline burden? | Why |
|---|---|---|---|
| per-variant het count | het damaging variants per sample inside the inversion | **No** | inflated for AB by construction at every variant class |
| per-gene het-masked count | genes where this sample is a damaging-allele carrier with the other copy intact | **Yes, as carrier-load reservoir** — AB is expected to be high here, and that high value is informative | this is the masked recessive reservoir |
| per-gene hom-exposed count | genes where both copies are damaged in this sample | **Yes — this is the exposure / functional-burden headline** | AA / BB > AB is the POD-compatible signal |

### 1.4 Three-cohort rule

KBC operates exclusively on the 226-sample pure *C. gariepinus*
hatchery cohort. The F1 hybrid and *C. macrocephalus* wild cohorts are
not inputs. K clusters from PCAngsd are hatchery broodline structure,
**not species admixture**.

### 1.5 Relatedness handling

The cohort is mixed-family at the hub level — ngsRelate first-degree
edge clustering produces hubs that often contain multiple unrelated
parental pairs that contributed offspring to the same hatchery batch.
Family hubs are therefore **not a unit of summary** in KBC. They are
treated as a relatedness confound.

The cohort-level contrast is run in two modes:

- **Primary:** NAToRA-pruned 81-unrelated subset (already established
  in the manuscript framework).
- **Secondary / robustness:** full 226 samples with a kinship random
  effect in the burden GLM (mixed model), using the ngsRelate kinship
  matrix.

These two modes mirror the existing F_ROH × ancestry analysis pattern
in the manuscript.

### 1.6 Per-inversion as the unit of analysis

**Each candidate inversion is one independent test unit.** KBC computes
the AA-vs-AB and BB-vs-AB exposure deltas *within* each inversion (and
within each POD segment for double-CO PODs), then summarises the
distribution of inversion-level results across the candidate set. The
spec does **not** pool raw counts across inversions for the headline
test.

The reason is straightforward: candidate inversions differ in length,
gene density, variant density, karyotype balance (n_AA / n_AB / n_BB),
callability, and POD structure. A single 50 Mb gene-rich inversion
would dominate any pooled count, so a pooled "AA vs AB across the
whole candidate set" would mostly be a test of the largest inversion,
not a cohort-wide test of inversions as a class.

The correct hierarchy:

```
within each inversion:
    within each POD segment (L / M / R / whole):
        per-sample hom_exposed_gene_count          (damaging)
        per-sample hom_exposed_gene_count          (synonymous control)
        compute ΔAA = mean(AA) − mean(AB)
        compute ΔBB = mean(BB) − mean(AB)
        compute p_AA, p_BB (Wilcoxon, NAToRA-pruned subset)
        compute kinship-corrected p_AA, p_BB (full cohort robustness)
        apply sample-size gate, synonymous-control gate, QC gates
        assign kbc_signal_class to the inversion

across inversions:
    distribution of ΔAA, ΔBB (forest plot, volcano)
    counts in each kbc_signal_class
    optional: meta-analysis combining inversion-level effects
              with inverse-variance weighting (not by raw counts)
```

What can be pooled safely:

- **counts of inversions** in each `kbc_signal_class`
  ("12/47 inversions POD-compatible on both arrangements, 8/47
  asymmetric, 5/47 failed synonymous control, 22/47 no signal");
- **per-inversion effect sizes** as the unit of a meta-analytic
  summary (random-effects model on Δ across inversions, weighted by
  inverse variance, never by raw sample count alone);
- **per-segment classification counts** for double-CO PODs
  ("L-segment signal in 10 inversions, M-segment signal in 3").

What must NOT be pooled:

- raw hom-exposed gene counts summed across inversions, then
  AA-vs-AB tested on the sum — this dilutes everything to the
  largest inversion and is uninterpretable.

The headline manuscript figure is the per-inversion result. The
across-inversion summary is descriptive: how many candidates show the
POD-compatible pattern, and how strong are the effects on average.

### 1.7 Synonymous variants are a control, not a denominator

KBC does **not** use dN/dS or any ratio-form normalisation as the
headline statistic. The synonymous variant counts enter as a
**parallel test** (the same contrast structure applied to synonymous
variants), not as a denominator in a ratio.

The reason: dN/dS is an evolutionary-substitution-rate concept,
designed to ask "did this lineage evolve faster at nonsynonymous sites
than at synonymous sites over time?" KBC's question is different:
"are damaging variants exposed in AA / BB and masked in AB *right now*,
in *this cohort*?" That is a present-day genotype-exposure question,
not a substitution-rate question. Mixing the two by using a
dN/dS-style ratio as the headline number would conflate divergence
process with functional exposure state and make the result harder to
interpret.

Operationally, ratios are also numerically unstable when the
denominator is near zero — which is exactly what you want in a
well-behaved synonymous control (small synonymous delta = clean
signal). Reporting `Δ damaging` and `Δ synonymous` as parallel
quantities, with the rule that POD-compatibility requires the
damaging delta to be large *and* the synonymous delta to be small,
sidesteps the instability entirely.

A dN/dS-style descriptive supplement is allowed — for example,
reporting per-arrangement private damaging variant counts divided by
per-arrangement private synonymous variant counts, as an
"arrangement-level enrichment of damaging variation". But this is a
**supplementary diagnostic**, not the KBC headline. It answers a
different question (is the arrangement enriched for damaging
variation overall?) than the KBC headline (are damaging genes
gene-level-exposed in homozygotes and masked in heterozygotes?).

### 1.8 Tiered damaging-variant definition — LoF first

Not all "damaging" variant calls are equally defensible. The KBC test
runs three times in parallel, on three nested damaging-variant tiers,
and the **headline manuscript claim uses Tier 1 only**:

| Tier | Variants included | Use for | Why this hierarchy |
|---|---|---|---|
| **Tier 1 — high-confidence LoF** | `stop_gained`, `frameshift_variant`, `start_lost`, canonical `splice_donor_variant`, canonical `splice_acceptor_variant` | **manuscript headline** | These are variants for which the loss-of-function claim is mechanistically obvious from sequence: premature stops truncate the protein, frameshifts scramble downstream codons, start losses prevent translation initiation, canonical splice site disruptions abolish exon recognition. No model support beyond SnpEff's annotation is required. Tier 1 is the conservative defensible signal. |
| **Tier 2 — LoF + validated splice Class A** | Tier 1 + Class A splice subclasses (`splice_donor_5th_base`, `splice_branch`, `polypyrimidine_tract` flagged Class A by the splice module) | **secondary, robustness check** | Splice variants beyond the canonical donor/acceptor are real but their LoF status depends on the splice annotation pipeline's quality. Tier 2 runs only after the splice module passes the validation checklist below. If KBC's POD-compatible classification at the inversion level is stable between Tier 1 and Tier 2, the splice additions are reinforcing, not distorting. |
| **Tier 3 — LoF + splice + strong missense** | Tier 2 + SIFT4G-deleterious missense + VESM LLR ≤ −7 missense + domain-disrupting missense | **exploratory / supplementary** | Strong missense is biologically interesting but the LoF inference is model-dependent. Tier 3 is reported in supplementary tables and used to ask "does the POD-compatible signal extend to predicted-damaging missense?" not "is this the headline burden?" |

Per-inversion results from all three tiers are emitted to table E
(see §3). The `kbc_signal_class` field is computed independently per
tier and reported as a tuple
`(tier_1_class, tier_2_class, tier_3_class)`. The manuscript headline
uses `tier_1_class`; tier 2 and tier 3 are reported as concordance
diagnostics.

**Tier-stability diagnostic** (table E, §3): for each inversion,
report whether the three tiers agree on the signal class. An
inversion that is POD-compatible at Tier 1 *and* Tier 2 *and* Tier 3
is the strongest claim. An inversion that flips from no-signal to
POD-compatible only at Tier 3 is reported with a caveat — the signal
depends on the model-dependent missense layer.

### 1.9 Splice validation checklist (gate for Tier 2)

The Class A splice subclasses are read from the project's existing
splice module. **Tier 2 is only enabled after the splice module passes
these six validation checks:**

1. **Canonical site identification.** Sample 100 random Class A
   `splice_donor_variant` calls; manually verify they hit a GT
   dinucleotide and 100 random Class A `splice_acceptor_variant`
   calls hit an AG dinucleotide, in the correct strand orientation.
2. **GFF/GTF coordinate consistency.** For 100 random Class A calls,
   verify the variant position is within ± 8 bp of an annotated
   exon-intron boundary in the transcript model the splice module
   used.
3. **Strand handling.** Compare Class A calls on `+` and `−` strand
   genes; the donor/acceptor proportions should be similar
   (canonical splicing is strand-symmetric overall). A large
   asymmetry suggests a strand bug.
4. **Intron-exon boundary classification.** For 50 variants at exon
   boundaries, manually classify their position (in-exon last 3 bp,
   intron first 6 bp, etc.) and check the splice module's
   `SPLICE_SUBCLASS` matches.
5. **SnpEff concordance.** For variants the splice module calls
   Class A, cross-check that SnpEff's annotation is in
   {`splice_donor_variant`, `splice_acceptor_variant`,
   `splice_region_variant`} with HIGH or MODERATE impact. Calls that
   SnpEff labels as `intron_variant` or non-coding with no splice
   flag are red flags.
6. **Transcript isoform stability.** For genes with multiple
   transcript isoforms, the splice module's call should be reported
   per isoform; check that the Class A call appears in the canonical
   transcript and not only in a minor isoform.

If any of these checks fail, Tier 2 stays disabled and the manuscript
uses Tier 1 only. Tier 3 (with model-dependent missense) does not
require splice validation, but inherits the splice validation status
in its caveats.

---

## 2. Inputs

### 2.1 Required

| File | Source | Notes |
|---|---|---|
| `variant_master_scored.tsv` | `MODULE_CONSERVATION` STEP 16 | canonical CSQ + SIFT + VESM + splice + scoring |
| Joint multisample VCF/BCF | `MODULE_CONSERVATION` STEP 03 | bcftools-normalised, multiallelics split — used for genotype-level hom / het classification |
| Inversion karyotype table | PCAngsd K=3 + Hungarian | per-sample arrangement call per inversion; values in {AA, AB, BB, NA} |
| Inversion interval table | inversion atlas | candidate intervals + L / M / R POD partition |
| Sample metadata | project sample sheet | sample_id, cohort, batch, NAToRA-pruned flag |
| Scoring weights | `scoring_weights.tsv` | reused as-is; not re-derived |
| ngsRelate kinship matrix | existing 23-col `.res` | for the mixed-model secondary mode |

### 2.2 Optional

| File | Source | Adds |
|---|---|---|
| Ancestry Q matrix + group labels | NGSadmix best-K + evalAdmix | ancestry covariate in the GLM |
| ROH BED per sample | `MODULE_3` | F_ROH covariate; cross-check for unintended ROH overlap with the inversion interval |
| Local ancestry / instant-Q | Engine B | sanity-check the inversion interval is not actually a local-ancestry artefact |
| Callable / depth mask | existing | denominator correction for variant-density bias |

KBC reads only the consequence / impact / SIFT class / VESM LLR /
splice-subclass fields from `variant_master_scored.tsv`. No dependency on
GERP / phastCons / phyloP / orthology-tier / CAFE / family-evolution
columns; the EGO pipeline is not a prerequisite.

---

## 3. Outputs

All outputs are TSV with sidecar JSON schemas. Paths under
`${BASE}/results/catfish-variant-analysis/NN_kbc/`.

### A. `kbc_sample_inversion_burden.tsv`

One row per sample × inversion × POD segment.

| col | type | req | description |
|---|---|---|---|
| `sample_id` | str | yes | |
| `inversion_id` | str | yes | |
| `pod_segment` | enum | yes | `L` / `M` / `R` / `whole` |
| `karyotype_class` | enum | yes | `AA` / `AB` / `BB` / `NA` |
| `n_damaging_variants` | int | yes | inside the segment, this sample (informational only — not used as response variable; see §1.3) |
| `het_masked_gene_count` | int | yes | genes where one copy carries a damaging variant and the other is intact (no damaging variant in trans at the same gene; no ROH overlap) |
| `hom_exposed_gene_count` | int | yes | genes where both copies are damaged (homozygous variant, or compound-het in trans where the genotype data supports it) |
| `compound_het_unknown_gene_count` | int | yes | genes with two damaging hets where phase is not determinable from the genotype-only data (these are **not** counted as hom-exposed) |
| `burden_score_sum` | float | yes | sum of per-variant scores (from scoring_weights.tsv), restricted to damaging classes |
| `is_pruned_unrelated` | bool | yes | NAToRA flag — true for the 81-unrelated subset |
| `roh_overlap_frac` | float | opt | fraction of this segment covered by ROH for this sample |
| `f_roh` | float | opt | per-sample F_ROH covariate |
| `ancestry_group` | str | opt | NGSadmix best-K hard call |

### B. `kbc_variant_arrangement_assignments.tsv`

For each damaging variant inside an inversion interval, which arrangement
background does it sit on?

| col | type | req | description |
|---|---|---|---|
| `variant_id` | str | yes | chrom:pos:ref:alt |
| `inversion_id` | str | yes | |
| `pod_segment` | enum | yes | |
| `gene_id` / `transcript_id` | opt | |
| `consequence` / `impact` / `sift_class` / `vesm_llr` / `splice_subclass` | yes | from variant_master_scored.tsv |
| `arrangement_background` | enum | yes | `A_private` / `B_private` / `shared` / `unassigned` |
| `assignment_method` | enum | yes | `AA_BB_homozygotes` / `freq_in_AA_vs_BB` / `unassigned` |
| `n_AA_samples_alt` / `n_AB_samples_alt` / `n_BB_samples_alt` | int | yes | sample counts carrying the ALT allele in each karyotype class |
| `f_AA` / `f_AB` / `f_BB` | float | yes | ALT allele frequency in each class |
| `assignment_confidence` | enum | yes | `high` (called in all AA-only and absent in all BB-only, or vice versa) / `medium` (frequency ≥ 0.8 in one class, ≤ 0.2 in the other) / `low` (mixed) / `unassigned` |

The arrangement-background assignment is **not** done by statistical
phasing. It is done from the karyotype distribution itself: a variant
that is present in AA homozygotes and absent in BB homozygotes is on the
A background; vice versa for B. This is the same logic the inversion
atlas already uses for per-arrangement variant frequency tracks.

### C. `kbc_karyotype_burden_summary.tsv` (the headline table)

One row per inversion × karyotype class × POD segment.

| col | type | req | description |
|---|---|---|---|
| `inversion_id` | str | yes | |
| `karyotype_class` | enum | yes | `AA` / `AB` / `BB` |
| `pod_segment` | enum | yes | `L` / `M` / `R` / `whole` |
| `n_samples` | int | yes | samples in this cell |
| `n_samples_pruned_unrelated` | int | yes | NAToRA-pruned subset count |
| `mean_burden_score` / `median_burden_score` | float | yes | per sample |
| `mean_hom_exposed_gene_count` | float | yes | per sample |
| `mean_het_masked_gene_count` | float | yes | per sample |
| `arrangement_private_damaging_count` | int | yes | unique damaging variants assigned to this class's arrangement background from table B (A-private for AA and the A side of AB; B-private for BB and the B side of AB) |
| `arrangement_shared_damaging_count` | int | yes | damaging variants on both backgrounds |
| `complementation_index` | float | yes | **AB-only**, undefined elsewhere — fraction of damaging genes where the A-side carries a different damaging variant than the B-side |
| `exposure_delta_vs_AB` | float | yes | **AA / BB only**, undefined for AB — `mean_burden_score(this_class) − mean_burden_score(AB at same segment)` |
| `exposure_delta_vs_AB_hom_genes` | float | yes | **AA / BB only** — same delta on `mean_hom_exposed_gene_count` |
| `wilcoxon_p_vs_AB` | float | yes | **AA / BB only** — Mann-Whitney U on hom_exposed_gene_count, this class vs AB, run on the NAToRA-pruned subset |
| `glm_kinship_p_vs_AB` | float | yes | **AA / BB only** — secondary, full-cohort kinship-corrected mixed model |
| `n_genes_arrangement_specific` | int | yes | genes hit by ≥ 1 arrangement-private damaging variant |

### D. `kbc_synonymous_control_summary.tsv`

Same shape as C, but computed on **synonymous variants only**. This is
the neutral negative control: the same per-karyotype-class contrast
should show **no** `exposure_delta_vs_AB` signal under the null. If it
does, the result in C is confounded (variant-density bias, callable-mask
artefact, or local-ancestry confound).

| col | type | req | description |
|---|---|---|---|
| identical schema to C | | yes | computed on synonymous variants instead of damaging ones |

### E. `kbc_per_inversion_report.tsv`

One row per inversion — flat headline table for the manuscript. Each
of the three damaging-variant tiers (§1.8) gets its own signal class
and delta columns.

| col | type | req | description |
|---|---|---|---|
| `inversion_id` | str | yes | |
| `pod_segment_with_largest_delta_tier1` | enum | yes | L / M / R / whole — based on Tier 1 deltas |
| **Tier 1 — high-confidence LoF (headline)** | | | |
| `tier1_signal_class` | enum | yes | `POD_compatible_AA_exposed` / `POD_compatible_BB_exposed` / `POD_compatible_both` / `asymmetric_AA_only` / `asymmetric_BB_only` / `no_signal` / `inconclusive_small_n` / `failed_synonymous_control` |
| `tier1_delta_AA_vs_AB` / `tier1_delta_BB_vs_AB` | float | yes | on hom-exposed gene count, Tier 1 variants |
| `tier1_delta_AA_vs_AB_synonymous` / `tier1_delta_BB_vs_AB_synonymous` | float | yes | synonymous control |
| `tier1_complementation_index_AB` | float | yes | AB-only |
| `tier1_n_variants` | int | yes | total Tier 1 variants in inversion |
| **Tier 2 — LoF + validated splice Class A (robustness)** | | | |
| `tier2_signal_class` | enum | yes | same enum as tier1 |
| `tier2_delta_AA_vs_AB` / `tier2_delta_BB_vs_AB` | float | yes | |
| `tier2_delta_AA_vs_AB_synonymous` / `tier2_delta_BB_vs_AB_synonymous` | float | yes | |
| `tier2_complementation_index_AB` | float | yes | |
| `tier2_n_variants` | int | yes | |
| `tier2_enabled` | bool | yes | false if splice validation (§1.9) did not pass; values above are null |
| **Tier 3 — LoF + splice + strong missense (exploratory)** | | | |
| `tier3_signal_class` | enum | yes | |
| `tier3_delta_AA_vs_AB` / `tier3_delta_BB_vs_AB` | float | yes | |
| `tier3_delta_AA_vs_AB_synonymous` / `tier3_delta_BB_vs_AB_synonymous` | float | yes | |
| `tier3_complementation_index_AB` | float | yes | |
| `tier3_n_variants` | int | yes | |
| **Tier-stability diagnostics** | | | |
| `tier_concordance` | enum | yes | `all_three_pod_compatible` / `tier1_pod_only` / `tier2_3_pod_only` / `tier3_only_pod` / `all_three_no_signal` / `inconsistent` |
| `headline_class` | enum | yes | **always Tier 1's class** — this is what goes in the manuscript |
| **Common (karyotype counts, double-CO test)** | | | |
| `n_AA` / `n_AB` / `n_BB` | int | yes | NAToRA-pruned subset |
| `dco_segment_test_p_tier1` | float | opt | L vs M contrast within karyotype class, Tier 1 only |
| `notes` | str | opt | |

The `kbc_signal_class` enum is deliberately conservative.
`failed_synonymous_control` and `inconclusive_small_n` exist precisely
so the headline table can report "no defensible claim" rather than
forcing a POD-compatible call on every inversion.

`tier_concordance` is the headline diagnostic. An inversion that is
POD-compatible at all three tiers is the strongest claim. An
inversion that is POD-compatible only at Tier 3 (`tier3_only_pod`)
means the signal depends on the model-dependent missense layer, and
the manuscript should not lead with it — but it is reported because
the missense-only signal is itself interesting biology.

### F. `kbc_across_inversion_summary.tsv`

The cohort-wide descriptive summary across the candidate inversion
set. One row per signal class, plus aggregate rows. This is the
"final paragraph" table — it answers "out of N candidate inversions,
how many show the POD-compatible pattern?"

| col | type | req | description |
|---|---|---|---|
| `kbc_signal_class` | enum | yes | from table E |
| `n_inversions` | int | yes | count of inversions in this class |
| `median_delta_AA_vs_AB` | float | opt | median across inversions in this class |
| `median_delta_BB_vs_AB` | float | opt | |
| `iqr_delta_AA_vs_AB` | str | opt | "Q1 – Q3" format |
| `iqr_delta_BB_vs_AB` | str | opt | |
| `median_complementation_index_AB` | float | opt | |
| `total_candidate_inversions` | int | yes | denominator — same in every row |

A second sheet of the same file emits the **meta-analytic summary**:
per-inversion effect sizes combined with inverse-variance weighting
under a random-effects model. This is descriptive only — the
manuscript headline is the count of POD-compatible inversions, not the
meta-analytic effect.

| col | type | req | description |
|---|---|---|---|
| `contrast` | enum | yes | `AA_vs_AB` / `BB_vs_AB` |
| `pooled_delta_random_effects` | float | yes | |
| `pooled_delta_95ci_low` / `pooled_delta_95ci_high` | float | yes | |
| `heterogeneity_i_squared` | float | yes | between-inversion heterogeneity |
| `n_inversions_in_pool` | int | yes | excludes failed_synonymous_control and inconclusive_small_n |

Pooling **excludes** inversions classified as
`failed_synonymous_control` or `inconclusive_small_n`. The pool is
the well-behaved subset.

---

## 4. Core algorithm

### Step 1 — Ingest + QC

- Read `variant_master_scored.tsv`; restrict to variants inside any
  candidate inversion interval.
- Read joint VCF for genotype calls at those variants.
- QC: drop sites failing depth / missingness / GL thresholds (defensive,
  even though MODULE_CONSERVATION already filters).
- Define the **three damaging-variant tiers** (see §1.8 for the
  rationale):

  - **Tier 1 — high-confidence LoF (headline).** Variants that
    truncate the protein or eliminate it: SnpEff `stop_gained`,
    `frameshift_variant`, `start_lost`, `splice_donor_variant`,
    `splice_acceptor_variant` at canonical GT/AG sites. These are
    the variants for which the LoF claim is defensible without
    additional model support.
  - **Tier 2 — LoF + validated splice Class A.** Tier 1 plus
    Class A splice subclasses from the splice module
    (`splice_donor_5th_base`, `splice_branch`,
    `polypyrimidine_tract` where the splice module assigns Class A
    confidence). Used only after the splice pipeline passes the
    validation checklist in §1.8.
  - **Tier 3 — LoF + splice + strong missense (exploratory).**
    Tier 2 plus SIFT4G-deleterious missense, VESM LLR ≤ −7
    missense, and domain-disrupting missense from VEP/SnpEff
    annotations.

- Define the **synonymous control set**: SnpEff
  `synonymous_variant`. The synonymous control is run in parallel
  for **all three damaging tiers** — each tier's POD-compatibility
  decision uses its own synonymous comparator.

### Step 2 — Per-sample, per-inversion, per-segment counts

For each (sample, inversion, segment):
- count damaging variants this sample carries;
- per damaging gene in the segment, classify this sample as
  `reference_like` / `het_masked` / `hom_exposed` /
  `compound_het_unknown` using the rules in §5;
- aggregate to row in table A.

### Step 3 — Variant-to-arrangement assignment from karyotype distribution

For each damaging variant in an inversion interval:
- compute ALT frequency in AA-only, BB-only, and AB samples;
- classify per the rules in §6;
- write row to table B.

### Step 4 — Karyotype × segment summary, per tier

**Loop over the three damaging-variant tiers** (§1.8). For each tier
× (inversion, karyotype_class, segment):
- aggregate from table A across samples in this cell, using only
  variants in this tier's damaging set;
- compute `complementation_index` for AB rows only;
- compute `exposure_delta_vs_AB` for AA and BB rows only;
- run Wilcoxon (primary, pruned) and kinship-corrected GLM (secondary,
  full cohort) for AA vs AB and BB vs AB;
- write rows to table C (with a `tier` column distinguishing
  T1 / T2 / T3).

Tier 2 rows are emitted only if the splice validation checklist (§1.9)
has passed. Otherwise Tier 2 columns in table E are null and
`tier2_enabled = false`.

### Step 5 — Synonymous-control parallel run, per tier

Repeat Step 4 with the synonymous variant set, **for each tier**. The
synonymous count is the same regardless of tier (synonymous variants
do not change between tiers), but the per-tier comparison is what
gates each tier's POD-compatibility classification. Write to table D
with the same `tier` column.

### Step 6 — Per-inversion report and signal classification, per tier

Apply the decision tree in §7 **three times** — once per tier — to
assign `tier1_signal_class`, `tier2_signal_class`, `tier3_signal_class`
in table E. Compute the `tier_concordance` field by comparing the
three classes. Set `headline_class = tier1_signal_class` always.

### Step 7 — Diagnostics

Per inversion, emit a small diagnostic figure stub (PDF):
- karyotype × per-sample burden boxplot (3 boxes: AA / AB / BB),
  **for Tier 1 as the headline panel, with Tier 2 and Tier 3 as
  side panels for tier-stability inspection**,
- AA-vs-AB and BB-vs-AB delta with 95% CI from bootstrap,
- synonymous control side-by-side,
- L / M / R sub-panels for double-CO PODs.

### Step 8 — Across-inversion summary

After all per-inversion tests are complete:
- count inversions in each `kbc_signal_class`, write to table F sheet 1;
- on the well-behaved subset (excluding `failed_synonymous_control`
  and `inconclusive_small_n`), fit a random-effects meta-analytic
  model on the per-inversion effect sizes with inverse-variance
  weighting, write to table F sheet 2;
- apply Benjamini-Hochberg FDR correction at q = 0.05 across all
  per-inversion p-values from table C (separately for AA-vs-AB and
  BB-vs-AB);
- emit a cohort-level forest plot of per-inversion effect sizes,
  ordered by inversion ID, with the random-effects summary at the
  bottom — this is the manuscript Figure X candidate.

---

## 5. Per-gene status assignment rules (Step 2)

For each (sample S, gene G, inversion I, segment Seg):

```
damaging_variants_in_G = damaging variants in G, in segment Seg
sample_S_genotypes = genotypes for sample S at those variants

case 1: all genotypes 0/0
        → reference_like

case 2: at least one variant 1/1
        → hom_exposed
        (homozygous damaging — exposed regardless of phase)

case 3: exactly one variant 0/1, no 1/1
        if ROH(S) covers the gene:
            → hom_exposed   (ROH forces the other copy to match → both damaged)
        else:
            → het_masked

case 4: two or more variants in 0/1 state, no 1/1
        → compound_het_unknown
        (without phase: could be cis, masked, or trans, exposed —
         KBC at the genotype level does not assert; HPP can resolve
         this for dyads with Stage 3 inheritance maps)
```

`compound_het_unknown` is reported separately in table A so the
headline counts are not inflated by ambiguous compound hets. The signal
classification in table E uses `hom_exposed_gene_count` only.

**Note on the case 3 ROH-overlap test (added at MVP 1 audit).** "ROH(S)
covers the gene" is evaluated as a half-open interval overlap between
each of sample S's ROH intervals and the gene's coordinate span. The
gene span is taken from a GFF3 annotation when provided (production
path; recommended); when GFF3 is unavailable the gene span falls back
to the bounding box of the gene's Tier-1 damaging variants in the
segment, and the gene record carries `span_source = "variant_bbox"`
through the per-gene record so downstream summaries can audit how many
genes were classified under the fallback. The current implementation
treats "overlap" rather than "fully contained" as the trigger; this is
the more permissive reading of the spec text and is open for audit.

---

## 6. Variant-to-arrangement assignment rules (Step 3)

Inputs: ALT frequency in AA-only, BB-only, AB samples; sample counts.

```
let n_AA, n_AB, n_BB = sample counts with karyotype calls at this inversion
let f_AA, f_AB, f_BB = ALT allele frequency in each class

require: n_AA >= 3 AND n_BB >= 3 else assignment_confidence = 'unassigned'

if   f_AA >= 0.95 AND f_BB <= 0.05:
       arrangement_background = 'A_private', confidence = 'high'
elif f_BB >= 0.95 AND f_AA <= 0.05:
       arrangement_background = 'B_private', confidence = 'high'
elif f_AA >= 0.80 AND f_BB <= 0.20:
       arrangement_background = 'A_private', confidence = 'medium'
elif f_BB >= 0.80 AND f_AA <= 0.20:
       arrangement_background = 'B_private', confidence = 'medium'
elif f_AA >= 0.50 AND f_BB >= 0.50:
       arrangement_background = 'shared',    confidence = 'high'
else:
       arrangement_background = 'shared',    confidence = 'low'
```

For AB samples, ALT frequency should fall near the mean of f_AA and
f_BB under the assumption of clean heterozygous inheritance. A large
deviation flags the variant for a `pod_segment = M` recombinant island
or genotyping noise.

Variants with `assignment_confidence = unassigned` are excluded from
table C's `arrangement_private_damaging_count` but retained in table A's
per-sample counts.

---

## 7. Signal classification rules (table E)

```
Inputs per inversion:
  delta_AA = exposure_delta_vs_AB on hom_exposed_gene_count, AA - AB
  delta_BB = same for BB - AB
  delta_AA_syn, delta_BB_syn = same on synonymous variants (the control)
  p_AA, p_BB = Wilcoxon p-values (primary, NAToRA-pruned subset)
  n_AA, n_BB, n_AB = sample sizes in pruned subset

Step 1 — sample-size gate:
  if min(n_AA, n_AB, n_BB) < 5:
      → 'inconclusive_small_n'

Step 2 — synonymous control gate:
  if |delta_AA_syn| > 0.5 * |delta_AA|  OR  |delta_BB_syn| > 0.5 * |delta_BB|:
      → 'failed_synonymous_control'
      (the AB-referenced delta is being driven by variant-density bias
       or local-ancestry confound, not by deleterious-load exposure)

Step 3 — signal call:
  significant_AA = (p_AA < 0.05) AND (delta_AA > 0)
  significant_BB = (p_BB < 0.05) AND (delta_BB > 0)

  if significant_AA AND significant_BB:
      → 'POD_compatible_both'
  elif significant_AA AND not significant_BB:
      → 'POD_compatible_AA_exposed'  (asymmetric — A carries the heavier private load)
  elif significant_BB AND not significant_AA:
      → 'POD_compatible_BB_exposed'  (asymmetric — B carries the heavier private load)
  else:
      → 'no_signal'

Step 4 — double-CO L vs M follow-up (PODs with explicit M segment):
  Run a secondary Wilcoxon on delta_AA and delta_BB between L and M
  segments. Report dco_segment_test_p. If significant, the M
  recombinant island shows a different burden architecture than the
  flanking L / R — the project-locked structural claim.
```

The conservative defaults are deliberate. The `failed_synonymous_control`
class is the spec's protection against the karyotype tautology (§1.3) —
if the AB delta is showing up at synonymous sites too, the result is not
a deleterious-load signal regardless of how strongly it shows up at
damaging sites.

---

## 8. Implementation design

### 8.1 Directory layout

```
catfish-variant-analysis/Modules/NN_kbc/
  README.md
  SPEC_KBC.md
  config/
    kbc_config.sh
    weights.tsv             ← symlink to MODULE_CONSERVATION scoring_weights.tsv
  schemas/
    A_kbc_sample_inversion_burden.schema.json
    B_kbc_variant_arrangement_assignments.schema.json
    C_kbc_karyotype_burden_summary.schema.json
    D_kbc_synonymous_control_summary.schema.json
    E_kbc_per_inversion_report.schema.json
  scripts/
    01_validate_inputs.sh
    02_ingest_variants.py
    03_per_sample_per_segment.py
    04_arrangement_assignment.py
    05_karyotype_summary.py
    06_synonymous_control.py
    07_signal_classify.py
    08_diagnostic_figures.py
  src/
    kbc/
      __init__.py
      io.py
      gene_status.py
      assignment.py
      summary.py
      stats.py            ← Wilcoxon + kinship-corrected GLM
      plot.py
  tests/
    fixtures/             ← tiny inversion + 3-class karyotype + variants
    test_gene_status.py
    test_assignment.py
    test_complementation.py
    test_synonymous_control.py
    test_signal_classify.py
  outputs/                ← .gitignored; results land under ${BASE}/results/
```

### 8.2 Function names

```
kbc_load_config()
kbc_validate_inputs()
kbc_ingest_variants()
kbc_define_damaging_set()
kbc_define_synonymous_control()
kbc_classify_per_gene_status()
kbc_count_per_sample_segment()
kbc_assign_arrangement_background()
kbc_summarise_per_karyotype()
kbc_complementation_index_AB()
kbc_exposure_delta_vs_AB()
kbc_wilcoxon_vs_AB()
kbc_kinship_glm_vs_AB()
kbc_synonymous_control_run()
kbc_classify_signal()
kbc_diagnostic_figure()
kbc_export_tables()
kbc_write_report()
```

### 8.3 Language + dependencies

- **Python 3.11**.
- `pysam` / `cyvcf2` for VCF.
- `pandas` / `polars` for tables.
- `scipy.stats` for Wilcoxon.
- `statsmodels` for the kinship-corrected mixed-effects GLM (or pull in
  the existing `MASS::glmmPQL` / `lme4` wrapper if the project's
  established stats path is R).
- Conda env `assembly` covers most; new YAML `envs/kbc.yaml` for the
  rest.

---

## 9. Staged MVP plan

### MVP 1 — Per-sample, per-segment counts (table A)

- Ingest variants, classify per-gene status, emit table A.
- No statistical contrasts yet.
- **Deliverable:** strict, segment-aware version of the per-sample
  burden table that already exists, with `hom_exposed_gene_count` and
  `het_masked_gene_count` separated.

### MVP 2 — Variant-to-arrangement assignment (table B)

- Implement §6 rules.
- Cross-check against the inversion atlas's existing per-arrangement
  variant frequency tracks for consistency.

### MVP 3 — Karyotype × segment summary (table C)

- Aggregate, compute `complementation_index` for AB, run AA-vs-AB and
  BB-vs-AB Wilcoxon on the NAToRA-pruned subset.
- **Manuscript-ready headline numbers.**

### MVP 4 — Synonymous control + signal classification (tables D, E)

- Re-run on synonymous variants, apply §7 decision tree.
- This is the gate between "we have a result" and "we can claim a
  POD-compatible pattern".

### MVP 5 — Mixed-model robustness + L vs M test for double-CO PODs

- Full-cohort kinship-corrected GLM as secondary mode.
- L vs M secondary test for double-CO PODs.

### MVP 6 — Diagnostic figures

- Per-inversion 3-class boxplot + delta + synonymous-control panel.

---

## 10. Pseudocode

### 10.1 Per-sample per-gene status

```python
def kbc_classify_per_gene_status(sample, gene, variants_in_gene,
                                 genotypes, roh_intervals):
    damaging = [v for v in variants_in_gene if is_damaging(v)]
    if not damaging:
        return 'reference_like'

    gts = [genotypes[(sample, v.variant_id)] for v in damaging]

    if any(gt == '1/1' for gt in gts):
        return 'hom_exposed'

    n_het = sum(1 for gt in gts if gt == '0/1')
    if n_het == 0:
        return 'reference_like'

    in_roh = gene_overlaps_any(gene, roh_intervals.get(sample, []))

    if n_het == 1:
        return 'hom_exposed' if in_roh else 'het_masked'

    # n_het >= 2 → compound het, phase unknown from genotype alone
    return 'compound_het_unknown'
```

### 10.2 Arrangement assignment

```python
def kbc_assign_arrangement_background(variant, karyotypes, genotypes):
    AA = [s for s in karyotypes if karyotypes[s] == 'AA']
    AB = [s for s in karyotypes if karyotypes[s] == 'AB']
    BB = [s for s in karyotypes if karyotypes[s] == 'BB']
    if len(AA) < 3 or len(BB) < 3:
        return 'shared', 'unassigned'
    f = lambda group: alt_freq(variant, group, genotypes)
    f_AA, f_BB = f(AA), f(BB)
    if f_AA >= 0.95 and f_BB <= 0.05:
        return 'A_private', 'high'
    if f_BB >= 0.95 and f_AA <= 0.05:
        return 'B_private', 'high'
    if f_AA >= 0.80 and f_BB <= 0.20:
        return 'A_private', 'medium'
    if f_BB >= 0.80 and f_AA <= 0.20:
        return 'B_private', 'medium'
    if f_AA >= 0.50 and f_BB >= 0.50:
        return 'shared', 'high'
    return 'shared', 'low'
```

### 10.3 Karyotype × segment summary

```python
def kbc_summarise_per_karyotype(inv, segment, samples_in_cell,
                                table_A, table_B):
    for kc in ('AA', 'AB', 'BB'):
        cell = [s for s in samples_in_cell
                if karyotype(s, inv) == kc]
        if not cell:
            continue
        burden = mean([table_A.burden_score_sum[s, inv, segment]
                       for s in cell])
        hom_exp = mean([table_A.hom_exposed_gene_count[s, inv, segment]
                        for s in cell])
        het_msk = mean([table_A.het_masked_gene_count[s, inv, segment]
                        for s in cell])
        if kc == 'AB':
            ci = complementation_index_AB(inv, segment, cell, table_B)
            emit_C_row(inv, kc, segment, mean_burden_score=burden,
                       mean_hom_exposed_gene_count=hom_exp,
                       mean_het_masked_gene_count=het_msk,
                       complementation_index=ci,
                       exposure_delta_vs_AB=None,
                       exposure_delta_vs_AB_hom_genes=None,
                       wilcoxon_p_vs_AB=None,
                       glm_kinship_p_vs_AB=None)
        else:
            ab_burden = lookup_AB_mean_burden(inv, segment)
            ab_hom_exp = lookup_AB_mean_hom_exp(inv, segment)
            delta_burden = burden - ab_burden
            delta_hom_exp = hom_exp - ab_hom_exp
            p_wilcox = wilcoxon_vs_AB(inv, segment, kc, table_A,
                                      pruned_unrelated_only=True)
            p_glm = kinship_glm_vs_AB(inv, segment, kc, table_A)
            emit_C_row(inv, kc, segment, mean_burden_score=burden,
                       mean_hom_exposed_gene_count=hom_exp,
                       mean_het_masked_gene_count=het_msk,
                       complementation_index=None,
                       exposure_delta_vs_AB=delta_burden,
                       exposure_delta_vs_AB_hom_genes=delta_hom_exp,
                       wilcoxon_p_vs_AB=p_wilcox,
                       glm_kinship_p_vs_AB=p_glm)
```

### 10.4 Complementation index (AB)

```python
def complementation_index_AB(inv, segment, AB_samples, table_B):
    a_priv = damaging_genes_with_assignment(table_B, inv, segment,
                                            'A_private')
    b_priv = damaging_genes_with_assignment(table_B, inv, segment,
                                            'B_private')
    distinct_pair_genes = a_priv & b_priv
    union_damaging = a_priv | b_priv
    if not union_damaging:
        return 0.0
    return len(distinct_pair_genes) / len(union_damaging)
```

### 10.5 Signal classification

```python
def kbc_classify_signal(inv, table_C, table_D):
    delta_AA = lookup_delta(table_C, inv, 'AA')
    delta_BB = lookup_delta(table_C, inv, 'BB')
    delta_AA_syn = lookup_delta(table_D, inv, 'AA')
    delta_BB_syn = lookup_delta(table_D, inv, 'BB')
    n_AA, n_AB, n_BB = pruned_counts(inv)
    p_AA = lookup_p(table_C, inv, 'AA')
    p_BB = lookup_p(table_C, inv, 'BB')

    if min(n_AA, n_AB, n_BB) < 5:
        return 'inconclusive_small_n'

    if (abs(delta_AA_syn) > 0.5 * abs(delta_AA) or
        abs(delta_BB_syn) > 0.5 * abs(delta_BB)):
        return 'failed_synonymous_control'

    sig_AA = p_AA < 0.05 and delta_AA > 0
    sig_BB = p_BB < 0.05 and delta_BB > 0

    if sig_AA and sig_BB:    return 'POD_compatible_both'
    if sig_AA:               return 'POD_compatible_AA_exposed'
    if sig_BB:               return 'POD_compatible_BB_exposed'
    return 'no_signal'
```

---

## 11. QC and caveats

- **Low coverage (~9×):** propagates to genotype uncertainty. KBC uses
  hard genotype calls from MODULE_CONSERVATION; sites failing GQ / DP
  are dropped upstream.
- **Headline is Tier 1 LoF only.** The manuscript headline uses the
  high-confidence LoF tier (stop-gained, frameshift, start-lost,
  canonical splice donor/acceptor). Tier 2 (with validated splice
  Class A) is a robustness check, Tier 3 (with strong missense) is
  exploratory. An inversion that is POD-compatible only at Tier 3 is
  reported with a caveat — the signal depends on the
  model-dependent missense layer.
- **Splice validation gate (§1.9).** Tier 2 stays disabled until the
  splice module passes the six-check validation. Until then,
  `tier2_enabled = false` and table E's Tier 2 columns are null. The
  manuscript using only Tier 1 + Tier 3 is acceptable — it is honest
  about which splice variants are validated.
- **LoF-coverage limits.** Tier 1 captures the easy LoF cases. Less
  obvious LoF mechanisms — premature polyadenylation, large
  in-frame deletions covering critical domains, transcription start
  site disruption — are not in Tier 1 and may not be in Tier 3
  either. KBC's POD-compatibility classification is not a complete
  inventory of all loss-of-function variants in the inversion.
- **Reference bias:** acknowledged; not corrected.
- **Multiallelics:** must be split upstream; assert on entry.
- **Variant-density bias:** addressed by the synonymous-control parallel
  run (table D + §7 Step 2).
- **Local-ancestry confound:** if a candidate inversion is actually a
  local-ancestry block driven by population structure, the synonymous
  control should also show a delta. The signal classifier flags
  `failed_synonymous_control` accordingly.
- **Karyotype call uncertainty:** samples with PCAngsd K=3 posterior
  below threshold get `karyotype_class = NA` and are excluded from
  table C summaries.
- **ROH-driven hom_exposed inflation:** the §5 case-3-in-ROH rule
  promotes a single het damaging variant inside an ROH to hom_exposed.
  A diagnostic side-table reports the fraction of each cell's
  hom_exposed count coming from ROH-promotion vs called homozygotes.
- **Compound-het ambiguity:** `compound_het_unknown` is reported
  separately and **not** counted in hom_exposed. The HPP module
  resolves a subset of these for offspring with Stage 3 inheritance
  maps; KBC itself does not attempt resolution.
- **Cryptic relatedness:** mitigated by primary mode running on the
  NAToRA-pruned subset, and by the kinship-corrected GLM in secondary
  mode.
- **HWE deviation is not used as evidence** for anything — it's
  mechanically inevitable in a structured hatchery cohort.
- **No claim of balancing selection, true overdominance, or fitness.**
  Output is structural-mutational. Interpretation in the manuscript
  stays at "POD-compatible".
- **Three-cohort rule:** KBC runs only on the 226-sample pure
  *C. gariepinus* hatchery cohort. F1 hybrid and *C. macrocephalus*
  wild cohorts are not inputs.

---

## 12. Out of scope

- No haplotype reconstruction. (HPP handles per-individual
  inheritance projection where Stage 3 supports it.)
- No SnpEff / SIFT4G / VESM re-running.
- No EGO / GERP / phastCons / phyloP / orthology / CAFE inputs.
- **No dN/dS, ω, or any ratio-form normalisation as the headline
  statistic.** Synonymous variants are a parallel negative control
  (Δ damaging vs Δ synonymous), not a denominator. A dN/dS-style
  per-arrangement enrichment may appear as a supplementary diagnostic;
  it is not the headline. See §1.7.
- **No pooled raw-count tests across inversions.** Each inversion is
  one test unit; across-inversion summaries are descriptive
  (signal-class counts) or meta-analytic (inverse-variance weighted),
  never sum-of-raw-counts. See §1.6.
- No SV burden (lives in MODULE_4A–G).
- No claim of fitness, balancing selection, or overdominance.
- No use of HWE deviation as evidence.
- No family-hub-aggregated summaries — family hubs are confounds, not
  units of analysis.
- No conflation of cohorts.

---

## 13. Manuscript-facing language

> For each candidate inversion, we tested whether AA and BB homozygotes
> carried elevated hom-exposed deleterious-gene counts relative to AB
> heterozygotes, segment by segment (L / M / R for double-crossover
> PODs; whole interval for single-crossover candidates). Damaging
> variants were defined as HIGH-impact SnpEff calls, deleterious-class
> SIFT4G missense, VESM LLR ≤ −7, or Class A splice subclass calls from
> the splice module. For each (sample, gene) pair inside an inversion
> segment, a gene was classified as reference-like, het-masked,
> hom-exposed, or compound-het-unknown using the rules in [methods
> §X.Y]; only hom-exposed genes contributed to the headline burden
> count. Damaging variants were assigned to the A-private, B-private,
> or shared arrangement background by their frequency in PCAngsd-K=3
> AA-only and BB-only samples; the AB-class complementation index was
> defined as the fraction of damaging genes where the A and B
> arrangement backgrounds carried distinct damaging variants. The
> primary contrast was a Mann-Whitney U test of hom-exposed
> gene count, AA vs AB and BB vs AB, on the NAToRA-pruned subset of 81
> unrelated samples; a secondary kinship-corrected mixed-model GLM was
> run on the full 226-sample cohort using the ngsRelate kinship matrix
> as a random effect. The same contrast was run in parallel on
> synonymous variants as a neutral negative control; inversions where
> the synonymous-control delta reached more than half the deleterious
> delta in magnitude were classified as `failed_synonymous_control` and
> reported but not used as evidence. The interpretation level is
> POD-compatible — consistent with pseudo-overdominance maintaining
> the inversion polymorphism via gene-level complementation of
> arrangement-private recessive load — but the design does not, and
> cannot, demonstrate balancing selection or fitness; direct fitness
> measurement was not possible in this cohort.

---

## 14. Open questions for the audit chat

1. Is the `failed_synonymous_control` cutoff (`|syn delta| > 0.5 × |damaging delta|`) calibrated correctly, or do we need a more principled threshold (e.g. bootstrap-based)?
2. Should the kinship-corrected GLM use the ngsRelate kinship matrix directly, or the NAToRA-derived structure?
3. For double-CO PODs, is the L vs M secondary test better as Wilcoxon on the AB-referenced delta, or as a direct L-vs-M comparison within each karyotype class?
4. Variant assignment thresholds in §6 — 95 / 5 % for "high", 80 / 20 % for "medium". Reasonable, or too lenient given 9× coverage?
5. Is the `compound_het_unknown` policy (exclude from hom_exposed) the right default, or should we have a "best-case" and "worst-case" headline pair?
6. Should KBC consume the splice module's `SPLICE_SUBCLASS` directly, or via the `priority_class` already in `variant_master_scored.tsv`?

---

*End of KBC SPEC v0.5. SPEC ONLY — not implemented. Awaiting audit.*
