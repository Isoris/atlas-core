# REGIME_ANNOTATION_SPEC — annotation layer for long-range haplotype regimes

**Status**: PARTIAL — Layers 1 + 2 shipped 2026-05-21 (audit). Layers 3
+ 4 (POD-aware, underdominance-aware) await real cohort data to validate
the math. SPEC body below is preserved verbatim from the 2026-05-08 chat origin.

**Implemented in (Layers 1 + 2):**
- [`atlases/inversion/shared/regime_annotation/index.js`](../atlases/inversion/shared/regime_annotation/index.js) — public re-exports
- [`atlases/inversion/shared/regime_annotation/positional.js`](../atlases/inversion/shared/regime_annotation/positional.js) — 183 lines (Layer 1)
- [`atlases/inversion/shared/regime_annotation/structure.js`](../atlases/inversion/shared/regime_annotation/structure.js) — 174 lines (Layer 2)
- [`tests/test_shared_regime_annotation.js`](../tests/test_shared_regime_annotation.js) — 272-line unit-test suite
- Consumer: [`atlases/inversion/pages/discovery/haplotype_regimes.js`](../atlases/inversion/pages/discovery/haplotype_regimes.js) calls both annotators per regime
- Consumer: [`atlases/inversion/shared/inversion_classification.js`](../atlases/inversion/shared/inversion_classification.js) — joins the two annotation outputs into the per-candidate classification record

**Public surface (shipped):**
- `annotateRegimePosition(regime, opts)` + `annotateRegimePositions(regimes[], opts)` — emits positional labels (centromere-proximal / pericentromeric / arm-interstitial / subtelomeric / arm-scale band) using configurable telomere + centromere fractions
- `annotateRegimeStructure(regime, opts)` + `annotateRegimeStructures(regimes[], opts)` — emits structural labels (band count, sharpness, nesting depth, M-regime kind)
- `REGIME_POSITIONAL_LABELS`, `REGIME_POSITIONAL_DEFAULTS`, `REGIME_STRUCTURE_LABELS`, `REGIME_STRUCTURE_DEFAULTS` — frozen vocab + tunable thresholds

**Per-layer status matrix:**

| layer | scope                                              | status |
|-------|----------------------------------------------------|--------|
| 1     | Positional annotation (where on the chrom?)        | ✅ shipped — `annotateRegimePosition` |
| 2     | Regime-structure annotation (band count + sharpness + nesting + M-regime kind) | ✅ shipped — `annotateRegimeStructure` |
| 2b    | Biological-mechanism classification (skeleton)     | ⏳ deferred — skeleton in SPEC §"Layer 2b", consumer not yet wired |
| 3     | POD-aware annotation (3-level evidence: variant / load / fitness) | ⏳ data-bound — needs cohort variant + load + fitness data the catfish dataset doesn't yet have |
| 4     | Underdominance-aware annotation                     | ⏳ data-bound — same blocker as Layer 3 (needs het-fitness signal) |

**Audit summary (2026-05-21):**

The two pure-compute annotation layers (positional + structure) are
fully shipped, with 272-line test coverage spanning all five positional
labels and all four structure labels, plus tunable-threshold edge cases.
The "discovery ≠ mechanism" / "compatible not confirmed" wording mandated
by the SPEC §"Critical caveat" is preserved in the label vocabulary
(`POD-compatible` / `POD-not-supported` style, not `POD-found`).

Layers 3 + 4 are deferred for the same upstream reason: they need
per-regime fitness + load + variant context that the catfish 226-sample
cohort doesn't expose at the resolution the SPEC requires. When that
data arrives, the existing index.js will export the new annotators
without changing the established (regime → annotation) shape.

**Source**: user-provided text, 2026-05-08 chat.
**Position in pipeline**: Stage 5.5 — sits between the regimes-page
visualization (Stage 5) and dosage overlay (Stage 6), or runs as a
post-hoc batch over the bruteforce results.

## What this layer does

The Stage 4 bruteforce + regimes panels **discover** long-range
inherited haplotype regimes — extended regions where samples inherit
blocks together more than expected from local noise.

This annotation layer **explains** each discovered regime: what kind
of biological mechanism could plausibly account for it?

The discovery layer is mechanism-agnostic. The annotation layer asks
four questions per regime:

1. **Where is it?** (positional annotation)
2. **What does it look like?** (regime-structure annotation)
3. **Does it behave like pseudo-overdominance?** (POD-aware annotation)
4. **Does it behave like underdominance?** (underdominance-aware annotation)

Critical caveat: **discovery ≠ mechanism**. A regime discovered by the
bruteforce can be many things. The annotation layer never says "POD
found"; it says "POD-compatible" if and only if the evidence pattern
matches, and "POD-not-supported" otherwise.

## Detection vs interpretation — the load-bearing distinction

This is the conceptual frame the whole spec rests on. Every claim
this layer produces falls into one of two categories:

> **Detection.** Our method (Stages 1–4) finds long-range haplotype
> regimes: intervals where individuals inherit stable, repeated
> haplotype-regime states across long distances. These regimes are
> the **observed object**.
>
> **Interpretation.** Annotation asks why each regime exists.
> Centromere proximity, inversion-like boundaries, POD-compatible
> load masking, underdominance-compatible HET deficit, and ancestry
> association are different **mechanism hypotheses** about the
> observed regime.

The phrasing trap to avoid:

> ❌ "We discovered POD regions."

The correct phrasing:

> ✅ "We discovered long-range haplotype regimes and annotated them
>     for POD-compatible genetic architecture."

This frame matters because POD, underdominance, and centromere
effects are **not the same kind of claim** as the regime detection.
The regime is something the data shows; the interpretations are
hypothesis rankings about why the data shows it.

### The three POD-evidence levels (do not conflate)

POD is a *genotype-regime pattern*, not a single-variant property.
Evidence for POD-compatibility comes in three separable levels,
which must stay distinguished in every output table and every
manuscript sentence:

| level     | what it measures                                          | required upstream     |
|-----------|-----------------------------------------------------------|-----------------------|
| variant   | individual candidate recessive deleterious alleles        | annotated variants    |
| load      | sum of *exposed homozygous* deleterious burden per group  | per-variant + GLs     |
| fitness   | phenotype, fertility, survival, transmission distortion   | broodstock or pedigree data |

The fitness level is usually **missing** for population-genomic
cohorts (including the 226-sample C. gariepinus hatchery cohort
unless growth/survival/fertility records are linked). Without
fitness data, the strongest claim available is:

> "POD-compatible genetic architecture"

not:

> "POD proven"

Because the regime might also be maintained by centromere-linked low
recombination alone, ancestry, or balancing selection at one or two
loci — all of which can mimic the variant + load signature.

### What a regime is and what it is not

| this regime is                                                | this regime is NOT                                |
|---------------------------------------------------------------|---------------------------------------------------|
| an interval of stable, long-range inheritance                 | a proven inversion                                |
| something that can be centromeric, inversion-like, or         | an automatic POD candidate just because it is     |
|   ancestry-linked, depending on annotation                    |   long and stable                                 |
| a place to test for POD-compatible and underdominance-        | proof of any of those mechanisms                  |
|   compatible patterns                                          |                                                   |
| compatible with multiple mechanisms simultaneously            | the result of one mechanism unless evidence pins  |
|   (e.g. centromeric AND POD-compatible)                       |   it down                                         |



## Layer 1 — Positional annotation

For each regime, compute:

| field                              | type   | source                          |
|------------------------------------|--------|---------------------------------|
| `chrom`                            | str    | regime metadata                 |
| `start_bp`                         | int    | regime metadata                 |
| `end_bp`                           | int    | regime metadata                 |
| `length_bp`                        | int    | derived                         |
| `nearest_centromere_distance_bp`   | int    | upstream centromere call        |
| `overlaps_inferred_centromere`     | bool   | upstream centromere call        |
| `overlaps_pericentromeric_window`  | bool   | upstream centromere call        |
| `distance_to_telomere_left_bp`     | int    | derived                         |
| `distance_to_telomere_right_bp`    | int    | derived                         |
| `subtelomeric`                     | bool   | derived (within X Mb of an end) |

**Defaults to confirm during audit**:
- Pericentromeric window: typically ±5 Mb around centromere midpoint
  (but should be set per-cohort / per-assembly).
- Subtelomeric threshold: typically within 2 Mb of chromosome end.
- These are *assembly-specific*. The C. gariepinus assembly (Gar
  haplotype, 28 LGs) has its own centromere calls — those need to be
  resolved before this layer runs.

**Output label** (one of):

| label                  | criterion                                              |
|------------------------|--------------------------------------------------------|
| `centromeric`          | overlaps inferred centromere                           |
| `pericentromeric`      | within pericentromeric window but does not overlap     |
| `subtelomeric`         | within 2 Mb of a chromosome end                        |
| `arm-scale`            | length ≥ 30% of chromosome arm length                  |
| `interstitial`         | none of the above — typical inversion-like position    |

**Interpretation guide** (not a label, just for the annotator's notes):

- **overlaps centromere** → possible centromere-assisted low
  recombination. **Do not conflate with POD.** A centromeric regime
  can be many things (see "Important logic" below).
- **near centromere** → possible pericentromeric regime.
- **far from centromere** → likely inversion / structural / ancestry-
  linked regime.
- **near telomere** → possible subtelomeric recombination / assembly
  / repeat effect (and possibly false signal — repeat regions are
  assembly-noisy).

## Layer 2 — Regime structure annotation

From the long-range proxy (Stage 4 output), compute:

| field                       | type   | source                                |
|-----------------------------|--------|---------------------------------------|
| `number_of_haplotype_regimes` | int    | consensus_partition.M (macro-band count) |
| `band_count`                | int    | stage3_locus.K                        |
| `regime_sharpness`          | float  | boundary-detection score (existing pipeline) |
| `regime_length_bp`          | int    | end_bp - start_bp                     |
| `internal_nesting`          | bool   | derived from sub-resolution detection |
| `transition_width_bp`       | int    | derived from boundary detector        |
| `sample_switching_rate`     | float  | per-window sample-set turnover        |

**Output label** (one of):

| pattern              | label                          |
|----------------------|--------------------------------|
| 2 regimes (M=2)      | `simple_haplotype_split`       |
| 3 regimes (M=3)      | `inversion_dosage_like`        |
| 4–6 regimes          | `nested_or_compound`           |
| sharp boundaries     | `structural_block_like`        |
| diffuse boundaries   | `recombination_gradient_like`  |
| nested blocks        | `compound_inversion_like`      |
| chromosome-arm scale | `arm_scale_block`              |

**Interpretation**: see the table in the original spec. Note that
COHERENT_SPLIT regimes from Stage 4 (nested inversions with stable
daughters) should produce `nested_or_compound` here. RANDOM_FAN
should NOT produce a regime annotation at all — it's the discovery
layer telling us "no real structure" — but if one slips through,
flag it as `noise_or_recombinant`.

## Layer 2b — Biological-mechanism classification (skeleton, not yet populated)

**Status**: scaffold. The classification table is documented here so
the next chat / audit chat / future-Quentin knows these alternative
mechanisms exist and have been considered. The current spec does NOT
require the implementation to *evaluate* each candidate against every
mechanism — that work comes later, when per-mechanism evidence
criteria are operationalized. For now, the table exists as a known-
options reference. Most candidates in the catfish manuscript will
likely use only `inversion-like_regime` or `unresolved_complex_regime`
until more mechanism-specific tests are added.

### The core point

A clean bounded multi-band regime ("fan → coherent regime → fan")
is very inversion-like, especially with three dosage-like groups and
recombination suppression. But inversions are **not** the only
biological mechanism that can produce this shape. Several other
processes generate bounded haplotype regimes that look similar in
the Stage 4 output. The annotation layer should be aware of these
alternatives even when it can't fully discriminate between them.

### Manuscript-style label hierarchy

For the MS_Inversions manuscript, use a two-level label structure:

```
localized haplotype regime
├── inversion-like
├── ancestry-linked (introgressed)
├── selection/balancing-like
├── low-recombination LD block
└── unresolved complex haplotype regime
```

The top-level label `localized haplotype regime` is always safe — it
describes the data without claiming a mechanism. The sub-labels are
hypothesis tiers; pick the most-supported sub-label when evidence
warrants, otherwise default to `unresolved_complex_regime`.

### Mechanism classification table

For each candidate, the layer emits one or more compatibility flags
from this table. A regime can match multiple mechanisms (e.g.
inversion-like + ancestry-linked when an inversion segregates with
introgressed ancestry).

| mechanism                              | distinguishing pattern                                                  | distinguishing evidence (when available)                                |
|----------------------------------------|-------------------------------------------------------------------------|-------------------------------------------------------------------------|
| `inversion-like_regime`                | bounded, 3-band dosage-like (HOM/HET/HOM), recombination-suppressed     | breakpoint evidence; DELLY/Manta INV calls; dosage cluster matches band |
| `ancestry-linked_haplotype_block`      | bounded; fish carrying introgressed haplotype cluster together inside the block; high local \|ΔQ\| | strong local Q shift; elevated cross-population differentiation; high divergence from background; long divergent haplotypes |
| `balanced_haplotype_regime`            | fish split into stable haplotype classes; two+ divergent haplotypes at intermediate frequency | trans-population polymorphism; high local heterozygosity sustained over evolutionary time; supergene-like signature without single inversion |
| `selected_haplotype_sweep_like_regime` | one carried long haplotype vs background; reduced diversity within carriers; fewer clean bands than inversion | extended haplotype homozygosity (EHH / iHS / xpEHH); recent-sweep signature; no clear breakpoint evidence |
| `supergene_like_complex_regime`        | multi-locus co-segregating haplotypes; complex local architecture (multiple SVs / duplications / suppressed recombination) without a single clean inversion | multiple co-adapted genes; complex SV pattern; trait-linked haplotype maintenance |
| `low_recombination_LD_block`           | broad LD block with diffuse but persistent haplotype classes; boundaries less sharp than inversion-like | aligns with recombination landscape; centromeric/pericentromeric position; no SV breakpoint evidence |
| `incompatibility_linked_block`         | unusual ancestry/haplotype structure attributable to epistatic incompatibility | hybrid fertility/viability evidence; transmission distortion in crosses (**do NOT use this label without hybrid evidence**) |
| `hyperdivergent_haplotype_regime`      | real, old, very divergent haplotypes; mechanism unsolved among introgression / balancing / suppressed-recombination | mechanism-ambiguous (Moya et al. 2024 explicitly notes these can be hard to distinguish) |
| `unresolved_complex_regime`            | bounded regime with no clear mechanism evidence                          | default for candidates that don't match any specific mechanism          |

**Compatibility, not exclusivity.** As with `POD-compatible`,
mechanism labels are written `*-compatible` and accumulated as flags:

```
INV001  flags = [inversion-like_compatible, ancestry-linked_compatible]
INV002  flags = [low_recombination_LD_block_compatible]
INV003  flags = [unresolved_complex_regime]
```

Implementations should never collapse this to a single forced choice.

### What this layer does NOT do (yet)

- Decide between mechanisms automatically. Each mechanism has its
  own evidence-criterion set (EHH/iHS for sweeps, Q-shift + LD
  decay for ancestry, hybrid-cross data for incompatibility, etc.)
  that are not all implemented yet. The table exists so future-Quentin
  can add per-mechanism evaluation modules one at a time without
  re-discovering the alternatives.
- Replace the discovery layer (Stage 4). The Stage 4 output is
  still what tells us "there's a bounded regime here at all." This
  table interprets that bounded regime.
- Produce mechanism *proof*. Same restraint as POD: the label is
  always `*-compatible`, never `*-confirmed`.

### Manuscript phrasing

The safest framing is:

> A bounded multi-band haplotype regime is consistent with an
> inversion-like structural haplotype, but is also compatible with
> introgressed ancestry tracts, balanced/selected haplotype blocks,
> or low-recombination LD blocks. We classified each candidate
> regime by which mechanisms its evidence pattern is compatible
> with, and reserved the `inversion-like` label for candidates with
> additional structural support (breakpoint evidence, dosage cluster
> consistency, recombination suppression localised to the block).

### References for this layer

- **Sunflower massive haplotype blocks (introgression + structural
  variation):** Todesco, M. et al. (2020). Massive haplotypes
  underlie ecotypic differentiation in sunflowers. *Nature* **584**:
  602–607. doi:10.1038/s41586-020-2467-6. The canonical demonstration
  that 1–100 Mb non-recombining haplotype blocks can be introgressions
  from related species.
- **Hyperdivergent regions review (mechanism ambiguity):** Moya, N. D.
  et al. (2024). The long and short of hyperdivergent regions.
  *Trends in Genetics*. Reviews how introgression, balancing
  selection, hypermutability, and suppressed recombination produce
  similar genomic signatures and explicitly notes they can be hard
  to distinguish.
- **Hyperdivergent haplotypes in *C. elegans* (empirical):** Lee, D.
  et al. (2021). Balancing selection maintains hyper-divergent
  haplotypes in *Caenorhabditis elegans*. *Nature Ecology & Evolution*
  **5**: 794–807.
- **Extended haplotype homozygosity (sweep detection):** Sabeti, P. C.
  et al. (2002). Detecting recent positive selection in the human
  genome from haplotype structure. *Nature* **419**: 832–837. The
  foundational EHH paper. Follow-ups: Voight et al. 2006 (iHS),
  Sabeti et al. 2007 (xpEHH).
- **POD and low-recombination context:** see Waller 2021, Abu-Awad &
  Waller 2023, Salson et al. 2025 in the main References section
  below — these also cover the LD-block / centromere-effect
  scenarios.

## Layer 3 — POD-aware annotation

**Three levels, do not collapse them.** This layer produces three
nested outputs, in order of evidence strength:

| sub-layer | level    | section                                       |
|-----------|----------|-----------------------------------------------|
| Layer 3a  | variant  | per-variant candidate enumeration (was 3b)    |
| Layer 3b  | load     | per-arrangement-group exposed-homozygous burden |
| Layer 3c  | fitness  | phenotype/fertility/segregation (usually absent) |

Layer 3a feeds 3b feeds 3c. The supplementary table is 3a, the
main figure is 3b, the strong claim requires 3c.

### Layer 3a — Variant level: candidate enumeration

(Moved up from the old Layer 3b. Same content, same wording rules.
See below in the per-variant section for full details.)

### Layer 3b — Load level: per-arrangement exposed burden

This is the **headline POD-compatibility test**. For each inversion,
compare exposed-homozygous deleterious load across HOM_A / HET /
HOM_B classes. The POD-compatible signature:

```
HOM_A exposed load  =  HIGH
HET   exposed load  =  LOW
HOM_B exposed load  =  HIGH
```

Or at minimum, HET lower than at least one HOM class. This is the
load-masking pattern.

The strongest case is **complementary load**: HOM_A exposes
deleterious set A, HOM_B exposes deleterious set B, HET carries
both A and B mostly heterozygously. Different variants on each
arrangement, both masked in HET. This is the textbook
*associative-overdominance* configuration (Gilbert et al. 2020;
Waller 2021; Salson et al. 2025).

### Layer 3c — Fitness level (usually missing)

The strong POD claim requires HET to be measurably fitter than both
HOM classes. Possible fitness proxies in this cohort:

- Growth rate per genotype class (if measured)
- Survival to broodstock age per class
- Fertility / offspring count per cross
- Transmission ratios in HET × HOM crosses
- Disease resistance / phenotype scores if available

Without these, the spec produces `POD_compatible_*` labels and never
`POD_proven`. The audit chat should check whether Quentin's cohort
has any linked phenotype data — if yes, this layer becomes the
manuscript's strongest paragraph; if no, it stays a documented gap.

### Old Layer 3 content — load metrics and scoring (now part of Layer 3b)

**Core hypothesis**: HOM regimes show higher deleterious burden or
lower fitness proxy, while HET/mixed regime hides load.

**Data source — use BEAGLE GLs, not hard genotype calls.** The cohort
is sequenced at coverage where probabilistic genotypes are the
correct currency. POD's signature lives in the *heterozygote class*
(load present but masked); hardcalling forces a single best genotype
per sample and throws away exactly the dosage uncertainty that
matters at HET. All burden metrics in this layer should be computed
from BEAGLE-phased GL output (the same input the existing
popstats_server consumes for Hudson Fst / HoverE / θπ).

Operationally this means: per-sample contribution to a burden metric
is the **expected dosage of the deleterious allele** under the GL
posterior, not 0/1/2 from a hard call. For a per-arrangement burden
sum, sum these expected dosages across the samples in that
arrangement group.

Required per-arrangement metrics:

| field                                       | type   | source                              |
|---------------------------------------------|--------|-------------------------------------|
| `deleterious_burden_per_haplotype_group`    | float  | SnpEff / SIFT / VESM / GERP × BEAGLE GLs |
| `LOF_count_per_group`                       | float  | SnpEff HIGH-impact, expected counts under GLs |
| `missense_count_per_group`                  | float  | SnpEff MODERATE-impact, expected counts |
| `private_deleterious_variants_per_arrangement` | int  | private-allele scan per group       |
| `ROH_overlap_per_group`                     | float  | ngsF-HMM, FROH                      |
| `heterozygosity_in_HET_group`               | float  | ANGSD HoverE for HET sample-set     |
| `HOM1_HET_HOM2_load_contrast`               | float  | derived                             |

(LOF and missense counts are *expected counts* because each variant
contributes its posterior probability of being non-reference per
sample, not a binary indicator. The integer column type from the
earlier draft was wrong for GL-based work.)

**Evidence rules**:

| evidence                                          | POD score |
|---------------------------------------------------|-----------|
| HOM1 has private deleterious load                 | +1        |
| HOM2 has different private deleterious load       | +1        |
| HET has lower exposed homozygous deleterious count | +2        |
| HET has higher observed fitness / lower bad phenotype | +2     |
| region is low-recombination / centromeric / inversion-like | +1   |
| no load contrast                                  | 0         |
| HET deficit                                       | −2        |
| inversion-like sharp boundaries                   | +1        |

**Cutoffs**:

| sum   | label                       |
|-------|-----------------------------|
| 0–1   | `POD_weak`                  |
| 2–3   | `POD_compatible_medium`     |
| 4+    | `POD_compatible_high`       |
| sum < 0 | `POD_not_supported`       |
| missing metrics | `POD_untested`      |

**Critical wording rule**: never say "POD found." Always
"POD-compatible." Even at high score, the call is a *hypothesis
ranking*, not a conclusion.

## Layer 3a — Per-variant candidate enumeration (detail)

(This section was previously labelled "Layer 3b". Renumbered to 3a
because variant evidence feeds load evidence, not the other way
around. Same content, same wording rules.)

**Purpose**: enumerate the specific variants contributing to a
POD-compatible regime. The variants themselves are *candidates*, not
proven causal — POD is a regime-level mechanism, not a single-variant
label.

**Critical wording rule**: never write "POD variant." Use:
- `POD_candidate_variant` (short)
- `POD_compatible_recessive_load_variant` (manuscript-safe)

The variant alone is not POD. The *pattern across genotypes* is
POD-compatible.

### Per-variant table — one row per candidate variant per inversion

```
inversion_id     INV001
arrangement      STD                (or INV — which arrangement carries
                                     the deleterious allele in homozygous form)
variant_id       LG28:15234567:G:A
gene             ndufa9
effect           missense           (or LoF / splice / frameshift)
deleterious_score 0.92              (SIFT / PolyPhen / VEP / CADD / VESM / GERP)
genotype_pattern HOM_alt in arrangement homozygotes;
                 HET in heterokaryotypes
exposed_in       HOM_STD            (or HOM_INV)
masked_in        HET
freq_HOM_STD     0.83               (allele frequency under GL posterior)
freq_HET         0.45
freq_HOM_INV     0.07
evidence_level   high
```

### Required columns

| field               | type   | meaning                                          |
|---------------------|--------|--------------------------------------------------|
| `inversion_id`      | str    | candidate from Stage 4 / regime annotation       |
| `arrangement`       | str    | STD or INV — which arrangement carries it homo   |
| `variant_id`        | str    | `chr:pos:ref:alt`                                |
| `gene`              | str    | affected gene from SnpEff/VEP                    |
| `effect`            | str    | missense / LoF / splice / frameshift / synon     |
| `deleterious_score` | float  | SIFT or VESM or CADD-equivalent in [0,1]         |
| `genotype_pattern`  | str    | summary string                                   |
| `exposed_in`        | str    | which homozygous group has it exposed            |
| `masked_in`         | str    | typically HET                                    |
| `freq_HOM_STD`      | float  | AF under BEAGLE GLs in HOM_STD samples           |
| `freq_HET`          | float  | AF under BEAGLE GLs in HET samples               |
| `freq_HOM_INV`      | float  | AF under BEAGLE GLs in HOM_INV samples           |
| `evidence_level`    | str    | high / medium / low                              |

### What counts as a good candidate

**Strong pattern A** (one-sided load on HOM_INV):

| group   | dominant genotype |
|---------|-------------------|
| HOM_STD | ref/ref           |
| HET     | ref/alt           |
| HOM_INV | alt/alt           |

**Strong pattern B** (one-sided load on HOM_STD — reverse polarity):

| group   | dominant genotype |
|---------|-------------------|
| HOM_STD | alt/alt           |
| HET     | ref/alt           |
| HOM_INV | ref/ref           |

Either pattern says: *one arrangement carries the deleterious allele;
it becomes exposed only when that arrangement is homozygous.*

**Stronger POD** has both arrangements carrying *different*
deleterious variants:

> Arrangement A carries bad variants `a, b, c` (exposed in HOM_A);
> Arrangement B carries bad variants `d, e, f` (exposed in HOM_B);
> HET carries all six mostly heterozygous → all six masked.

This is the textbook *associative overdominance* configuration. The
per-variant table should make this readable at a glance.

### Filtering rules to avoid noise

A candidate row must pass all of these to be emitted:

1. **Polarisation**: `|freq_HOM_STD − freq_HOM_INV| ≥ 0.6` under
   BEAGLE GL posteriors. One arrangement essentially fixed for ref,
   the other essentially fixed for alt. (Threshold to confirm in
   audit — 0.6 is a starting value, may need raising on noisy data.)
2. **HET intermediate**: `min(freq_HOM_STD, freq_HOM_INV) ≤
   freq_HET ≤ max(freq_HOM_STD, freq_HOM_INV)`. The HET group's AF
   sits between the two HOM groups' AFs — confirms the variant
   tracks the arrangement axis.
3. **Deleterious classification**: `deleterious_score ≥ 0.7` (SIFT-
   style) OR effect ∈ {LoF, splice_acceptor, splice_donor,
   stop_gained, frameshift, start_lost}.
4. **Coverage / GL confidence**: per-sample GL must have a peak
   ≥ 0.85 in the dominant genotype for ≥ 80% of samples in each
   group. Avoids noise from uncertain GLs.
5. **Sample-size floor**: each of the three groups must have ≥ 5
   samples called. (Same floor as `dosage_overlay.js`'s
   `min_samples_for_class`.)

### evidence_level assignment

| condition                                                    | level    |
|--------------------------------------------------------------|----------|
| polarisation ≥ 0.8, score ≥ 0.9, LoF or splice               | `high`   |
| polarisation ≥ 0.7, score ≥ 0.8                              | `medium` |
| meets minimum filters but below medium thresholds            | `low`    |

### Main-figure summary table — one row per inversion

This is what goes in the paper. Per-inversion aggregate of the
per-variant table:

```
inversion_id  HOM_STD_exposed_load  HET_exposed_load  HOM_INV_exposed_load
                                                       POD_compatible
INV001        high                  low               high     strong
INV002        high                  medium            low      weak/one-sided
INV003        low                   low               low      no_evidence
```

Where "exposed load" = sum of deleterious scores of all variants
homozygous-alt in that group (under BEAGLE GL posterior dosages,
not hard calls).

### Supplementary table

The full per-variant table from above — all `POD_candidate_variant`
rows across all inversions, with all metadata. This is the
reproducibility artefact.

### Manuscript-style sentence

> For each inversion, we catalogued arrangement-specific deleterious
> variants that were homozygous in one arrangement class but
> heterozygous or absent in heterokaryotypes. Variants were called
> from BEAGLE genotype likelihoods rather than hard genotype calls,
> preserving dosage uncertainty in the heterozygote class where the
> POD signature is most diagnostic. These variants were treated as
> candidate contributors to a POD-compatible recessive-load pattern
> rather than as individually causal POD variants.

## Naming convention — heterozygosity, differentiation, and the I/S collision

This spec defines statistics that quantify heterozygosity excess/
deficit and differentiation between arrangement classes. In a
manuscript about inversions, the **standard population-genetics
abbreviation `FIS`** creates a naming collision: readers see
`FIS_STD_vs_INV` and have to disambiguate "I = inversion-side" from
"I = Inbreeding-coefficient" on every line.

The spec resolves this by mandating disambiguating prefixes for
every column, figure caption, code identifier, and table header
that derives from these statistics.

**Rule 1 — heterozygosity excess/deficit statistic.**

Use `HWE_FIS` rather than bare `FIS`. The `HWE_` prefix makes
explicit that the statistic compares observed-to-expected
heterozygosity under Hardy–Weinberg.

| name                          | use                                              |
|-------------------------------|--------------------------------------------------|
| `HWE_Hobs`                    | observed heterozygosity in the cohort/group      |
| `HWE_Hexp`                    | expected heterozygosity under HWE                |
| `HWE_FIS`                     | `1 − HWE_Hobs / HWE_Hexp` — the standard FIS, named explicitly |
| `HWE_pvalue`                  | HWE departure p-value (exact or chi-square)      |
| `HWE_HET_excess_deficit`      | categorical: HET_excess / HWE_like / HET_deficit |

**Sign convention** (must be preserved everywhere):

```
HWE_FIS < 0   →  HET_excess     (Hobs > Hexp)
HWE_FIS = 0   →  HWE_like
HWE_FIS > 0   →  HET_deficit    (Hobs < Hexp)
```

**Rule 2 — arrangement differentiation statistic.**

Use a visibly distinct prefix so the differentiation statistic is
never confused with the heterozygosity statistic. The spec mandates
one of:

- `arrangement_FST_like`  (verbose, manuscript-safe)
- `FAT_arrangement`       (compact, for code identifiers)

Both are acceptable; pick one per artefact and stick with it. The
prefix `FAT` is intended to read as "F_AT" (between-arrangement) by
analogy with the standard `F_ST` (between-population) — visually
distinct from `HWE_FIS`.

**Rule 3 — never bare `FIS` or `FST` in spec-owned columns.**

In existing references to upstream pipelines (popstats_server,
ANGSD, Hudson Fst, etc.), the standard names stay because those are
published-metric names from external tools. Inside the annotation
layer's own output tables and figures, use the prefixed names.

**Why this matters.** A manuscript line that reads
"HOM_INV vs HET FIS = -0.42" is ambiguous about whether F is between
arrangements or within. A line that reads "HOM_INV vs HET HWE_FIS =
-0.42" is unambiguous: it's the within-group heterozygosity statistic.
Same for `arrangement_FST_like`. Reviewers will catch the bare-name
ambiguity; the spec catches it first.

## Per-regime HWE / arrangement-frequency table (schema)

Each annotated regime emits one row in `regime_hwe_table.tsv` with
the following columns (all using the disambiguated naming convention):

| column                      | type   | meaning                                       |
|-----------------------------|--------|-----------------------------------------------|
| `regime_id`                 | str    | candidate from Stage 4 / regime annotation    |
| `chr`                       | str    | chromosome                                    |
| `start_bp`                  | int    | regime start                                  |
| `end_bp`                    | int    | regime end                                    |
| `HOM_A_count`               | float  | expected count of HOM_A under BEAGLE GLs      |
| `HET_count`                 | float  | expected count of HET under BEAGLE GLs        |
| `HOM_B_count`               | float  | expected count of HOM_B under BEAGLE GLs      |
| `arrangement_A_freq`        | float  | derived from group counts                     |
| `arrangement_B_freq`        | float  | `1 − arrangement_A_freq`                      |
| `HWE_Hobs`                  | float  | observed HET frequency under GL posteriors    |
| `HWE_Hexp`                  | float  | `2 · arrangement_A_freq · arrangement_B_freq` |
| `HWE_FIS`                   | float  | `1 − HWE_Hobs / HWE_Hexp`                     |
| `HWE_pvalue`                | float  | HWE departure significance                    |
| `HWE_HET_excess_deficit`    | str    | HET_excess / HWE_like / HET_deficit           |
| `arrangement_FST_like`      | float  | between-arrangement differentiation           |
| `HWE_flag`                  | str    | summary flag for the categorical interpretation |

The HWE_flag is the categorical column that downstream code reads;
the float `HWE_FIS` is the continuous column that the figure code
plots. Both are emitted for every regime.

**Counts are expected counts under GL posteriors, not hard-call
counts.** The same BEAGLE-GL rule that Layer 3 enforces applies
here. A regime's HET count is `Σ_samples P(HET | GL)`, not the
number of samples whose maximum-posterior genotype is HET. At
breakpoint regions where genotyping accuracy is lowest, this
distinction is the difference between a true HET deficit and a
genotyping artefact.

## Layer 4 — Underdominance-aware annotation

**Core hypothesis**: HET / mixed-regime individuals look worse than
both homozygous regimes.

**Data source**: same principle as Layer 3 — use BEAGLE GL posteriors
for all genotype-frequency comparisons (HET deficit, HWE test, missing
heterokaryotype count). Hard-calling at the breakpoint region — where
genotyping accuracy is lowest and where the underdominance signature
is most diagnostic — would systematically bias HET counts downward
and create *false* underdominance signals. Use GL-derived expected
genotype frequencies throughout.

**Naming**: this layer's HWE-based metrics use the disambiguated
names from the "Naming convention" section above. `HWE_FIS` and
`HWE_pvalue` are the primary signals; `arrangement_FST_like` is the
between-arrangement differentiation companion.

Required metrics:

| field                                  | type   | source                       |
|----------------------------------------|--------|------------------------------|
| `HWE_FIS`                              | float  | per-regime, derived from BEAGLE GLs |
| `HWE_pvalue`                           | float  | per-regime HWE test          |
| `HWE_HET_excess_deficit`               | str    | categorical flag             |
| `missing_heterokaryotypes_count`       | float  | `HWE_Hexp · N − HWE_Hobs · N` |
| `arrangement_FST_like`                 | float  | between-arrangement differentiation |
| `pedigree_transmission_distortion`     | float  | if pedigree available        |
| `excess_non_transmitted_haplotypes`    | int    | if pedigree available        |
| `recombinant_or_gene_conversion_switches` | int | per-trio switch counter     |
| `reduced_fertility_proxy`              | float  | optional, often unavailable  |
| `offspring_genotype_ratio_deviation`   | float  | if crosses available         |

**Expected Mendelian ratios** (for reference, in simple crosses):

| cross           | expected ratio              |
|-----------------|----------------------------|
| HOM1 × HOM2     | all HET                    |
| HET × HOM1      | 1:1 HET:HOM1               |
| HET × HET       | 1:2:1 HOM1:HET:HOM2        |

**Evidence rules**:

| evidence                                              | UNDERDOM score |
|-------------------------------------------------------|----------------|
| HET deficit                                           | +2             |
| distorted offspring ratios                            | +2             |
| recombinant haplotypes missing or depleted            | +2             |
| inversion-like sharp boundaries                       | +1             |
| fertility / viability proxy worse in HET              | +1             |
| HET excess                                            | −2             |
| HET masks deleterious load                            | −1             |

**Cutoffs** (same as POD):

| sum   | label                          |
|-------|--------------------------------|
| 0–1   | `UNDERDOM_weak`                |
| 2–3   | `UNDERDOM_compatible_medium`   |
| 4+    | `UNDERDOM_compatible_high`     |
| sum < 0 | `UNDERDOM_not_supported`     |
| missing metrics | `UNDERDOM_untested`  |

## Interpretation traps — three failure modes to refuse

These are warnings about what NOT to conclude. The implementation
must enforce these as guardrails in the output table; the audit chat
must verify they are.

### Trap 1 — high deleterious count in HET does not mean bad

A heterozygote sample can carry many deleterious variants in total.
What matters for POD evaluation is whether those variants are
**homozygous-exposed**, not whether they are present.

The metric the spec uses is **exposed homozygous deleterious burden**
(sum of deleterious scores for alleles that are homozygous-alt in
the sample under BEAGLE GL posterior dosages), NOT total deleterious
burden carried.

A HET sample with 200 heterozygous deleterious variants and 0
homozygous-deleterious genotypes has *zero* exposed burden and
*supports* POD-compatibility. Total burden carried is irrelevant to
this question.

### Trap 2 — HET excess and HET deficit have opposite meanings

| pattern                                         | interpretation                              |
|-------------------------------------------------|---------------------------------------------|
| HET has *lower* exposed load than both HOMs     | POD-compatible                              |
| HET is *more frequent* than expected (excess)   | POD-compatible / balancing-selection-compatible |
| HET is *missing or rare* (deficit)              | underdominance-compatible                   |
| HET has *worse* phenotype (when measurable)     | underdominance-compatible                   |
| HOMs have high exposed load, HET masks it       | POD-compatible                              |
| one HOM class is missing entirely               | possible lethality, selection, sampling bias, or ancestry artefact |

These patterns must be reported as independent axes in the output
table. The same regime can show *both* POD-compatible variant
patterns AND HET deficit — at which point the regime is
"ambiguous / both mechanisms compatible" and the annotation must
say so, not pick one.

### Trap 3 — centromere overlap is not POD evidence

This trap is repeated for emphasis because it is the most common
mis-claim. Centromere proximity tells you:

> Low recombination MAY preserve haplotype blocks in this region.

It does NOT tell you:

> Those haplotype blocks carry complementary recessive load.

POD-compatibility is a *separate question* from centromere
proximity. A centromere-overlapping regime can be:
- POD-compatible (centromere helps maintain the load contrast)
- ancestry-associated (centromere has the ancestry-resolution
  weakness, not POD)
- structural-variant-driven (centromere-proximal inversion or
  duplication)
- pure assembly artefact (centromeric repeats can mismap)

The annotation table must keep `centromere_relation` and
`POD_score` as independent columns. Never derive POD score from
centromere proximity alone.

## Measurement specifics — operational details

### Centromere proximity (Layer 1 detail)

Required input: a centromere annotation BED for the C. gariepinus
Gar haplotype assembly.

```
chr     cent_start    cent_end
LG01    43000000      45500000
LG02     1200000       2800000
...
```

Per regime, compute:

```
inv_chr
inv_start
inv_end
inv_mid = (inv_start + inv_end) / 2

distance_to_centromere_bp =
    0  if regime overlaps centromere interval
    else  min(|inv_end − cent_start|, |inv_start − cent_end|)
```

Output classes (multiple flags — the audit chat should decide which
becomes the primary label, recommendation is the most-restrictive
flag that fires):

| class                | rule                                       |
|----------------------|--------------------------------------------|
| centromeric          | overlaps centromere interval               |
| pericentromeric_1Mb  | within 1 Mb of centromere                  |
| pericentromeric_5Mb  | within 5 Mb of centromere                  |
| pericentromeric_10Mb | within 5–10 Mb of centromere               |
| interstitial         | > 10 Mb from centromere                    |
| unknown              | centromere not annotated for this chrom    |

The 1/5/10 Mb thresholds are intentionally fish-appropriate
defaults. Mammalian or plant centromere-effect ranges (Pazhayam
et al. 2024 in *Drosophila*) do not transfer directly. The audit
chat should consult the C. gariepinus recombination landscape
before committing to thresholds.

**Output file**: `centromere_regime_annotation.tsv` with columns:
`candidate_id`, `chr`, `start_bp`, `end_bp`, `length_bp`,
`cent_start`, `cent_end`, `distance_to_centromere_bp`,
`overlaps_centromere`, `within_1Mb`, `within_5Mb`, `within_10Mb`,
`centromere_relation`.

### Low-recombination / long-range linkage

For each regime, compute these metrics (some come from the existing
Stage 4 pipeline, others need separate computation):

| metric                  | meaning                                       | source                |
|-------------------------|-----------------------------------------------|-----------------------|
| `mean_LD_inside`        | r² inside the regime                          | per-cohort LD scan    |
| `LD_flank_ratio`        | `mean_r2_inside / mean_r2_flanks`             | derived               |
| `regime_persistence`    | fraction of windows where samples keep their  | Stage 4 vote tracks   |
|                          | regime-band membership                        |                       |
| `switch_rate`           | per-sample window-to-window band changes      | Stage 4               |
| `rho_inside`            | per-window ρ if pyrho or LDhat available      | upstream pipeline     |
| `rho_fold_reduction`    | `mean_rho_flanks / mean_rho_inside`           | derived               |
| `boundary_sharpness`    | from existing boundary detector               | Stage 4 / banding     |

A regime that is genuinely a long-range haplotype block should
have:
- High `mean_LD_inside`
- `LD_flank_ratio` >> 1
- High `regime_persistence` (closer to 1.0 than to 1/K)
- Low `switch_rate`
- `rho_fold_reduction` >> 1 (when ρ is available)
- Sharp boundaries (structural-block-like)

### Score breakdown (separate from POD score)

The score system needs **explicit separation between context and
mechanism**. The user's preferred decomposition:

```
centromere_score:
  0 = far (> 10 Mb)
  1 = within 5–10 Mb
  2 = within 1–5 Mb
  3 = overlaps centromere

linkage_score:
  0 = weak block
  1 = moderate block
  2 = strong long-range inheritance
  3 = strong + sharp boundaries

load_masking_score:
  0 = no contrast
  1 = HET lower than one HOM
  2 = HET lower than both HOMs
  3 = complementary load on both arrangements

HET_frequency_score:
  -2 = strong HET deficit
  -1 = moderate HET deficit
   0 = HET frequency near expected
  +1 = moderate HET excess
  +2 = strong HET excess
```

**Combined scores** — keep these as separate columns, do not collapse:

```
POD_genetic_score = linkage_score + load_masking_score
                    range: 0..6

centromere_context = centromeric / pericentromeric_1Mb /
                     pericentromeric_5Mb / pericentromeric_10Mb /
                     interstitial / unknown
                     (NOT added into POD_genetic_score)

underdominance_score = (linkage_score / 2) +
                       max(0, -HET_frequency_score) +
                       (HET_phenotype_penalty if available)
                       range: 0..6
```

The centromere score is reported as **context**, not folded into
POD score. This is the trap-3 enforcement at the column level.

### Final interpretation labels — produced by the score combination

| label                                              | rule                                          |
|----------------------------------------------------|-----------------------------------------------|
| `POD-compatible, centromere-associated`            | POD_genetic_score ≥ 4 AND centromere within 5 Mb |
| `POD-compatible, non-centromeric`                  | POD_genetic_score ≥ 4 AND centromere > 10 Mb  |
| `centromere-linked regime, POD untested`           | centromere overlap + linkage ≥ 2, but load_masking_score not computable (missing variant data) |
| `low-recombination regime, no POD evidence`        | linkage_score ≥ 2 AND load_masking_score = 0  |
| `underdominance-compatible`                        | underdominance_score ≥ 3                      |
| `ambiguous / ancestry-associated`                  | strong correlation with population Q AND weak load evidence |

Output file: `inversion_pod_underdominance_scores.tsv`.

## Output files (user's preferred names)

| file                                       | content                                  |
|--------------------------------------------|------------------------------------------|
| `inversion_load_summary.tsv`               | main figure data: HOM_A / HET / HOM_B exposed loads per inversion |
| `pod_compatible_variants.tsv`              | all `POD_candidate_variant` rows         |
| `inversion_pod_underdominance_scores.tsv`  | per-inversion scores + interpretation labels |
| `centromere_regime_annotation.tsv`         | per-regime centromere proximity table    |
| `regime_hwe_table.tsv`                     | per-regime HWE / arrangement-frequency table (HWE_FIS, arrangement_FST_like, etc.) |

The main figure plot is straightforward: per inversion, bar chart of
exposed homozygous deleterious load in HOM_A / HET / HOM_B classes.
POD-compatible shape:

```
load
 |
 |  ████        ████
 |  ████  ░░░░  ████
 |  ████  ░░░░  ████
 +─────────────────────
    HOM_A  HET   HOM_B
```

Underdominance-compatible HET frequency shape (separate plot):

```
freq
 |
 |  ████        ████
 |  ████  ░░░░  ████
 |  ████        ████
 +─────────────────────
    HOM_A  HET   HOM_B    (HET deficit)
```

## References

The following peer-reviewed papers should be cited when this layer
goes into a manuscript. References verified via search; URLs and
DOIs current as of 2026-05.

**POD / linked recessive load**:

1. Waller, D. M. (2021). Addressing Darwin's dilemma: Can pseudo-
   overdominance explain persistent inbreeding depression and load?
   *Evolution* **75**: 779–793. doi:10.1111/evo.14189. Establishes
   that POD blocks are more likely in low-recombination regions and
   lists expected signatures: heterozygosity hotspots, distinct
   haplotypes at intermediate frequency, high LD around POD regions.

2. Abu-Awad, D. & Waller, D. (2023). Conditions for maintaining
   and eroding pseudo-overdominance and its contribution to
   inbreeding depression. *Peer Community Journal* **3**: e8.
   doi:10.24072/pcjournal.224. Theoretical framework for the
   conditions that maintain or erode POD zones; tight linkage is
   key; centromeric regions and inversions favor POD emergence.

3. Salson, M., Duranton, M., Huynh, S., Mariac, C., et al. (2025).
   Interplay between large low-recombining regions and pseudo-
   overdominance in a plant genome. *Nature Communications*
   **16**: 6458. doi:10.1038/s41467-025-61529-z. Empirical study
   in pearl millet linking LLR regions, pericentromeric position,
   inversions, heterozygote excess, and POD signatures. Directly
   relevant template for this catfish analysis. Companion code:
   https://github.com/msalson/low-recombining_regions_study.

4. Gilbert, K. J., Pouyet, F., Excoffier, L. & Peischl, S. (2020).
   Transition from background selection to associative overdominance
   promotes diversity in regions of low recombination. *Current
   Biology* **30**: 101–107.e3. Establishes the BGS→AOD transition
   that underlies POD-compatible signals.

**Centromere effect on recombination**:

5. Pazhayam, N. M., Frazier, L. K. & Sekelsky, J. (2024).
   Centromere-proximal suppression of meiotic crossovers in
   *Drosophila* is robust to changes in centromere number, repetitive
   DNA content, and centromere-clustering. *Genetics* **226**:
   iyad216. doi:10.1093/genetics/iyad216. Empirical demonstration
   that the centromere effect (CO suppression near centromeres) is
   widespread and genetically controlled.

6. Vincenten, N., Kuhl, L.-M., Lam, I., Oke, A., et al. (2015).
   The kinetochore prevents centromere-proximal crossover
   recombination during meiosis. *eLife* **4**: e10850. Shows
   layered kinetochore/centromere-associated suppression of
   pericentromeric recombination.

7. Pazhayam, N. M., Sagar, S. & Sekelsky, J. (2025). Suppression
   of meiotic crossovers in pericentromeric heterochromatin
   requires synaptonemal complex and meiotic recombination factors
   in *Drosophila melanogaster*. *Genetics* **229**: iyaf029.
   doi:10.1093/genetics/iyaf029. Mechanistic follow-up on the
   centromere effect.

**Alternative mechanisms producing bounded haplotype regimes (Layer 2b)**:

8. Todesco, M. et al. (2020). Massive haplotypes underlie ecotypic
   differentiation in sunflowers. *Nature* **584**: 602–607.
   doi:10.1038/s41586-020-2467-6. Canonical demonstration that
   1–100 Mb non-recombining haplotype blocks can be introgressions
   from related (possibly extinct) congeners. The reference for
   `ancestry-linked_haplotype_block` and `hyperdivergent_haplotype_
   regime` mechanism labels.

9. Moya, N. D. et al. (2024). The long and short of hyperdivergent
   regions. *Trends in Genetics*. Reviews how introgression,
   balancing selection, hypermutability, and suppressed recombination
   produce similar genomic signatures and explicitly notes they can
   be hard to distinguish. The reference for the
   "mechanism-ambiguous" caveat that motivates the `unresolved_
   complex_regime` default label.

10. Lee, D. et al. (2021). Balancing selection maintains hyper-
    divergent haplotypes in *Caenorhabditis elegans*. *Nature
    Ecology & Evolution* **5**: 794–807. Empirical demonstration
    that hyperdivergent regions can be maintained by long-term
    balancing selection — supports the `balanced_haplotype_regime`
    mechanism label.

11. Sabeti, P. C. et al. (2002). Detecting recent positive selection
    in the human genome from haplotype structure. *Nature* **419**:
    832–837. Foundational EHH paper. With Voight et al. 2006 (iHS)
    and Sabeti et al. 2007 (xpEHH), provides the canonical evidence
    method for `selected_haplotype_sweep_like_regime`.

**Citation note for the manuscript**: the C. gariepinus cohort is
analogous to the pearl millet system in Salson et al. 2025
(diploid, outcrossing, hatchery population with known pedigree
structure). That paper is the closest empirical template; its
methods section should be the reference point for which metrics
to compute and how to report them.

## Safest manuscript paragraph (use this exact framing)

> We measured centromere proximity as the distance between each
> long-range inheritance regime and inferred centromeric intervals.
> This positional feature was analyzed separately from POD-
> compatible genetic architecture, which was quantified using
> arrangement-specific recessive deleterious variants and the
> exposed homozygous deleterious burden in HOM_A, HET, and HOM_B
> classes. Centromere proximity was therefore interpreted as a
> low-recombination context that may preserve linked haplotype
> blocks, rather than as direct evidence of pseudo-overdominance.
> We did not infer pseudo-overdominance from variant presence alone;
> instead, we scored each inversion for POD-compatible genetic
> architecture based on arrangement-specific recessive load,
> exposed homozygous deleterious burden, heterokaryotype masking,
> centromere proximity, and segregation patterns.

## Final annotation table — one row per regime

```
candidate_id          LG28_regime_001
chr                   LG28
start_bp              15,115,000
end_bp                18,005,000
length_mb             2.89
regime_class          interstitial_inversion_like
band_count            3
boundary_type         sharp
nesting               no
centromere_relation   far
telomere_relation     internal
recombination_proxy   suppressed
POD_score             medium
POD_reason            HET masks arrangement-specific deleterious variants
UNDERDOM_score        weak
UNDERDOM_reason       no strong HET deficit
best_interpretation   inversion-like inherited haplotype regime
confidence            high / medium / low
```

This corresponds to **one row per long-range regime in a per-chromosome
table**, attached as JSON / TSV alongside the existing per-chromosome
result registries.

## Important logic — centromeres are not POD

Centromere overlap **is not** evidence for POD. Centromeres can produce:

| centromere effect              | could cause                              |
|--------------------------------|------------------------------------------|
| low recombination              | long haplotype blocks (any mechanism)    |
| linked deleterious load        | POD-compatible pattern                   |
| distorted segregation / drive  | underdominance-like or transmission distortion |
| assembly / repeat complexity   | false signal                             |
| ancestry blocks                | population-structure signal              |

**Correct annotation wording**:

> "Centromere-assisted long-range inheritance regime."

This is independent of:

> "POD-compatible", "underdominance-compatible", "ancestry-compatible",
> "inversion-compatible".

A regime can be **both** centromeric AND POD-compatible. Or centromeric
AND ancestry-associated. The annotation layer must keep these axes
independent.

## Vocabulary the annotation layer should use

**Discovery layer output** (what Stage 4 produces):
- "long-range inheritance regime"
- "extended haplotype inheritance regime" (manuscript-style)

**Positional classes**:
- `centromeric_regime`
- `pericentromeric_regime`
- `interstitial_regime`
- `subtelomeric_regime`
- `arm_scale_regime`

**Mechanistic annotations** (independent axes, can co-occur):
- `POD_compatible_regime`
- `underdominance_compatible_regime`
- `recombination_suppressed_regime`
- `inversion_like_regime`
- `ancestry_associated_regime`
- `nested_compound_regime`

## Manuscript-style sentence (canonical)

> We annotated each long-range inheritance regime according to
> genomic position, boundary sharpness, haplotype structure,
> centromere proximity, deleterious-load contrast, and segregation
> behavior. This allowed regimes to be classified as centromeric,
> pericentromeric, interstitial, or subtelomeric, and further scored
> for compatibility with pseudo-overdominance, underdominance,
> inversion-like suppression, or ancestry-associated inheritance.

## Direct-style description

> The long-range proxy discovers the regime; the annotation layer
> explains whether it behaves like a centromere-linked block,
> POD-compatible haplotype system, underdominant inversion, nested
> inversion, or ancestry block.

---

## Implementation plan (DO NOT IMPLEMENT YET — AUDIT FIRST)

When the next chat is ready to implement:

1. **Confirm centromere/telomere calls exist** for the C. gariepinus
   reference assembly (Gar haplotype, 28 LGs). If not, the positional
   layer can't run.
2. **Confirm deleterious-burden pipeline outputs** are available per
   sample (the existing MODULE_CONSERVATION outputs: VESM_650M,
   SIFT4G, SnpEff HIGH+MODERATE counts, GERP++/phastCons). The POD
   layer requires these.
3. **Decide where the annotation runs**: in-browser as part of the
   atlas, or as a post-hoc R/Python batch script over Stage 4 output.
   Recommendation: post-hoc batch, results saved as
   `<chrom>.regime_annotation.json`, loaded by the atlas at startup.
4. **Build a fixture** with a known POD-compatible regime, a known
   underdominance-compatible regime, and a centromere-overlap-but-
   neither regime. Verify the scoring system gets all three right.
5. **Wire annotation into the regimes page** as a tooltip /
   side-panel that appears when the user selects a focal voter
   whose seed locus overlaps an annotated regime.

## Audit questions for the next chat

1. **Are the scoring weights right?** +2 for HET-load-hiding, +2 for
   HET deficit (underdom), −2 for HET deficit (POD). Where do these
   numbers come from? Are they peer-reviewed, or are they reasonable
   guesses? They need a defensible source before the manuscript.
2. **Is the 0/1/2/3/4 → weak/medium/high cutoff defensible?** Why
   not 0/2/4/6/8? The cutoffs determine how many regimes get flagged
   "compatible_high" — that's a manuscript-relevant decision.
3. **What about additive evidence weights?** A regime with +1 from
   five independent sources (total 5) is different from a regime
   with +2 from one strong source (total 2). The current scoring
   collapses them. Is that right?
4. **HET-load-hiding (POD +2) and HET-load-masking (UNDERDOM −1)
   look like the same evidence with opposite signs.** That's correct
   (they're competing hypotheses), but the auditor should verify
   no double-counting in marginal cases.
5. **What about "recombination_proxy = suppressed"?** That's listed
   in the output table but the method to compute it isn't specified
   above. Probably comes from existing local LD / lostruct Z-plateau
   detection. Confirm pipeline.
6. **Nesting interaction with POD**. A nested compound regime
   (Layer 2 = nested) where the inner regime is POD-compatible and
   the outer is not — how does the table represent this? One row?
   Two rows? Hierarchical?
7. **BEAGLE GL pipeline confirmation**. Layer 3 and Layer 4 both
   specify BEAGLE GLs as the data source instead of hard calls.
   The auditor should verify:
   - The existing BEAGLE-phased GL output for the 226-sample cohort
     is the right input. (popstats_server already consumes this for
     Fst/HoverE — same pipeline, same BEAGLE output.)
   - Burden metrics correctly use *expected dosages* under the GL
     posterior, not 0/1/2 from a hard call.
   - HWE test in Layer 4 uses GL-derived expected genotype counts,
     not hard-called counts — at breakpoint regions where genotyping
     accuracy is worst (and where the underdominance signal is most
     diagnostic), hard-calling biases HET counts downward and
     produces *false* underdominance signals. This is a known
     failure mode the auditor must check.
8. **Per-variant filtering thresholds (Layer 3a)**. Polarisation
   ≥ 0.6, deleterious score ≥ 0.7, GL peak ≥ 0.85 in ≥ 80% of
   samples, ≥ 5 samples per group. These are starting values.
   The audit chat should look at typical deleterious-variant
   density and GL-quality in the 226-sample BEAGLE output and
   recommend cohort-appropriate thresholds.
9. **Reverse-polarity handling in Layer 3a**. The "good candidate"
   patterns include both `alt-fixed-on-INV` and `alt-fixed-on-STD`
   directions. The implementation must enumerate variants in both
   polarities and never assume one direction is "the" arrangement.
   The auditor should verify the spec's polarisation filter is
   symmetric (it uses `|freq_HOM_STD − freq_HOM_INV|` — absolute
   value — which is correct).
10. **Wording-rule enforcement**. The spec mandates several
   disambiguating identifiers. The audit chat should grep all
   downstream code, scripts, and figure captions for violations:
   - `POD_candidate_variant` / `POD_compatible_recessive_load_variant`
     required; bare `POD_variant` forbidden.
   - `HWE_FIS` required; bare `FIS` forbidden in spec-owned columns
     (existing references to upstream popstats_server Hudson Fst /
     ANGSD HoverE / etc. stay because those are published-metric
     names from external tools).
   - `arrangement_FST_like` or `FAT_arrangement` required for
     between-arrangement differentiation; bare `FST` forbidden in
     spec-owned columns.
   Flag every occurrence. These are manuscript-correctness issues
   that grow the longer the project runs. The I-collision (I =
   Inversion vs I = Inbreeding) is the specific failure mode the
   `HWE_` prefix prevents.
11. **Three-level POD evidence (variant / load / fitness)**. The
    spec mandates the three levels stay distinguished. The audit
    chat should:
    - Verify the manuscript can produce variant + load tables
      without claiming fitness-level evidence.
    - Decide whether Quentin has any linked phenotype data
      (growth, survival, fertility, broodstock success). If yes,
      Layer 3c becomes the headline result; if no, the spec's
      `POD_compatible_*` ceiling stands.
12. **Score-breakdown independence**. The spec keeps
    `centromere_score` and `POD_genetic_score` as **independent
    columns**, never summing them. The audit chat should verify
    no implementation collapses them into a single composite
    "POD score" — that would re-introduce the Trap 3 (centromere
    overlap as POD evidence).
13. **Centromere proximity thresholds for fish**. The spec offers
    1 / 5 / 10 Mb pericentromeric bands as defaults. Mammalian and
    plant centromere effects (Pazhayam et al. 2024; Salson et al.
    2025) use different ranges. The audit chat should consult the
    C. gariepinus recombination landscape (if any pyrho/LDhat data
    exist) before committing to these thresholds.
14. **Centromere annotation availability**. The whole positional
    layer requires a centromere BED for the Gar haplotype. If this
    doesn't exist yet, the audit chat must escalate — without it,
    Layer 1 cannot run. Options: use synteny-based centromere
    inference from a closely related species (zebrafish, channel
    catfish) as a fallback, or commit to producing a centromere
    annotation pipeline.
15. **Pearl millet template (Salson et al. 2025) as the methods
    reference**. The pearl millet study is the closest empirical
    analogue: diploid, outcrossing, hatchery/cultivated population,
    LLR regions with POD signatures. The audit chat should read
    that paper's methods section in full and verify the spec's
    metrics (LD enrichment, ρ_fold_reduction, regime_persistence,
    exposed homozygous load, HET frequency) align with what the
    pearl millet authors did. Their companion code repo is at
    https://github.com/msalson/low-recombining_regions_study.
16. **HWE_FIS and arrangement_FST_like naming consistency**. The
    spec mandates the disambiguated names to resolve the I/S
    collision in inversion-context manuscripts. The audit chat
    should:
    - Verify the implementation emits `HWE_FIS`, `HWE_Hobs`,
      `HWE_Hexp`, `HWE_pvalue`, `HWE_HET_excess_deficit` as
      column names — not bare `FIS`, `Hobs`, `Hexp`.
    - Verify the differentiation column is named
      `arrangement_FST_like` (verbose) or `FAT_arrangement`
      (compact), never bare `FST`.
    - Verify the sign convention: `HWE_FIS < 0` → HET_excess,
      `HWE_FIS > 0` → HET_deficit. Implementations sometimes
      invert this; the audit chat should test on a synthetic
      fixture where the sign is known.
    - Verify the counts in `regime_hwe_table.tsv` are expected
      counts under BEAGLE GL posteriors, not hard-call counts.
      The same GL rule from Layer 3 applies.
17. **Layer 2b mechanism table (skeleton).** Layer 2b documents nine
    biological mechanisms that can produce bounded multi-band
    haplotype regimes (inversion-like, ancestry-linked, balanced,
    selected/sweep-like, supergene-like, low-recombination LD,
    incompatibility-linked, hyperdivergent, unresolved-complex). The
    current spec only scaffolds the table — per-mechanism evaluation
    modules are not implemented. The audit chat should:
    - Decide whether to populate any specific mechanism rule beyond
      `inversion-like_compatible` for the v20 manuscript, or keep
      everything else as `unresolved_complex_regime` until
      mechanism-specific tests exist.
    - Verify the spec's `*-compatible` flag accumulation rule (a
      regime can carry multiple compatibility flags) is preserved
      — never collapse to a single forced mechanism choice.
    - Verify `incompatibility_linked_block` is never assigned
      without explicit hybrid fertility/viability data. The spec
      flags this; the implementation must enforce it.
    - Cross-reference the manuscript's discussion of mechanism
      alternatives — the bibliography should cite Todesco 2020 for
      ancestry-linked sunflower haplotypes, Moya 2024 for the
      mechanism-ambiguity review, Lee 2021 for empirical
      hyperdivergent haplotypes in *C. elegans*, and Sabeti 2002 /
      Voight 2006 for sweep-haplotype detection methods.

## What this spec does NOT cover

- Implementation: see "Implementation plan" above. No code yet.
- Statistical significance: the scoring system produces ordinal
  labels (weak/medium/high). It does not produce p-values. If
  manuscript-grade significance is needed, an additional layer of
  permutation testing or empirical-null calibration is required.
- Multiple-testing correction: when annotating many regimes, the
  weak/medium/high labels are not adjusted for the number of
  regimes annotated. The next chat should decide if this matters.
- Cross-species / cross-cohort transfer: the scoring weights are
  tuned for the 226-sample C. gariepinus hatchery cohort. They may
  not transfer to wild C. macrocephalus or to F1 hybrids
  (different cohorts the user is studying).

## Appendix — suggested paper-section structure

For the MS_Inversions manuscript, the spec recommends three sequential
Results sections that mirror the detection-vs-interpretation frame:

### Section 1 — Detection of long-range haplotype regimes

> We developed a long-range inheritance proxy to identify genomic
> intervals where samples retained stable haplotype-regime membership
> across extended genomic distances.

(This is the Stage 1–4 pipeline output. No mechanism claims yet.)

### Section 2 — Positional annotation of regimes

> Regimes were annotated by centromere distance, telomere distance,
> repeat density, and segmental-duplication overlap to distinguish
> pericentromeric, subtelomeric, and interstitial regimes.

(This is Layer 1. Reports on **where** without yet asking why.)

### Section 3 — POD- and underdominance-aware interpretation

> We then tested whether each regime showed genetic signatures
> compatible with pseudo-overdominance or underdominance.

(This is Layers 3 + 4. Reports on **why-compatible**, not why-proven.
Cite Waller 2021, Abu-Awad & Waller 2023, Salson et al. 2025,
Gilbert et al. 2020.)

### The bridge table between method and biology

The headline data object: one row per regime in
`inversion_pod_underdominance_scores.tsv`:

| regime_id | chr   | start_bp   | end_bp     | regime_class       | centromere_relation | regime_pattern | POD_score | underdom_score | interpretation                          |
|-----------|-------|------------|------------|--------------------|---------------------|----------------|-----------|----------------|-----------------------------------------|
| R001      | LG28  | 15,115,000 | 18,005,000 | interstitial       | far                 | 3-state sharp  | high      | low            | POD-compatible inversion-like regime    |
| R002      | LG05  |  2,100,000 |  8,400,000 | pericentromeric    | near                | diffuse 2-state| untested  | low            | centromere-linked regime                |
| R003      | LG12  | 30,200,000 | 39,800,000 | interstitial       | far                 | 6-state nested | medium    | medium         | compound haplotype regime               |

This table is the bridge between the method (regime_id, regime_pattern)
and the biology (interpretation).

### The sentence that should appear in every relevant section

> "We distinguish regime detection from regime interpretation."

This signposts the conceptual frame to reviewers. It says: the
regime is data; the mechanism label is hypothesis ranking. Repeating
this in Methods, Results, and Discussion is the most reliable way to
keep the manuscript safe from over-claiming.

### Simple-version paragraph (for talks or short-format venues)

> Our method finds where the genome is inherited as a long block.
> Centromere annotation asks: is the block long because recombination
> is naturally low there? POD annotation asks: does heterozygosity in
> this block hide recessive deleterious load? Underdominance
> annotation asks: are heterozygotes in this block missing or
> disadvantaged? Long-range haplotype regime = discovered structure.
> Centromere = linkage context. POD/underdominance = evolutionary
> /fitness interpretation.

