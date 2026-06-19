# Chapter 7. Long-range recombination-suppressed haplotypes in North African catfish broodstock

> **Provenance & scope.** All numbers, figures, and tables in this draft come
> from the synthetic demo under `04_results/candidates/LRR0{1,2,3}/`,
> generated deterministically by
> `toolkit_registries/relatedness/scripts/gen_candidate_demo.py`. They
> demonstrate the schema layout, the harvester, and the figure renderer
> end-to-end; **no value here is a measurement on real cohort data**. The
> chapter will read identically once the upstream pipelines (`long-range
> regime detector`, `karyotype caller`, `local-PCA`, `popstats`,
> `pedigree segregation`) write into the same per-candidate folder.
>
> **Cohort.** The 226-sample pure *Clarias gariepinus* hatchery broodstock
> cohort (`cohort_id = cgar_hatchery_226`). The F1 hybrid (the assembly
> cohort, *n* = 1) is **not** the subject of this chapter and is never used
> for any per-sample claim — coordinates may cross cohort boundaries; claims
> may not.

This chapter investigates long-range haplotype structure within the North
African catfish broodstock. Building on the population structure and
relatedness framework established in Chapter 6, local genomic windows were
used to identify intervals where individuals showed stable dosage-like
clustering across extended genomic regions. These intervals are interpreted
as candidate **recombination-suppressed haplotype blocks** rather than as
structurally confirmed inversions. The chapter tests three linked
hypotheses: first, that some regions form coherent long-range haplotype
blocks; second, that these blocks show population-genetic signatures
consistent with divergent haplotype maintenance or overdominance; and third,
that the haplotype states segregate as coherent units within inferred
families.

---

## 7.1 Long-range haplotype structure consistent with reduced recombination

Three candidate blocks were retained from the local-PCA scan and the
long-range regrouping analysis after requiring concordant support from
**long-range vote** (the fraction of windows in which the same individuals
re-clustered together) and **local continuity** (adjacent-window agreement
on the grouping). The retained blocks span 2.6–7.2 Mb on three different
linkage groups and are summarised in Table 7.1.

**Table 7.1.** Candidate long-range recombination-suppressed haplotype
blocks. *Major dosage classes* lists the karyotype-class labels detected
locally; *long-range vote* and *local continuity* are the two complementary
retention criteria. *Interpretation* is the block-level label written by
`harvest_candidates.py`.

| Block | Chrom | Start | End | Size (Mb) | n windows | Dosage classes | Long-range vote | Local continuity | Interpretation |
|-------|-------|-------|-----|-----------|-----------|----------------|-----------------|------------------|----------------|
| LRR01 | C_gar_LG28 | 1,200,000 | 8,400,000 | 7.2 | 72 | H1H1 / H1H2 / H2H2 | 86 % | 0.91 | candidate LRR |
| LRR02 | C_gar_LG14 | 22,400,000 | 26,900,000 | 4.5 | 45 | H1H1 / H1H2 / H2H2 | 71 % | 0.78 | candidate LRR |
| LRR03 | C_gar_LG07 | 11,100,000 | 13,700,000 | 2.6 | 26 | H1H1 / H1H2 / H2H2 | 58 % | 0.62 | weak / unresolved |

LRR01 (LG28, 7.2 Mb) is the clearest case: 86 % of windows return the same
sample partition, adjacent-window continuity is 0.91, and the local-PCA
trace separates three stable clusters cleanly across the full interval
(**Figure 7.1**, generated as `LRR01/figures/fig1_localpca_track.svg`). LRR02
shows the same qualitative pattern over a 4.5 Mb interval but with weaker
continuity (0.78), and LRR03 falls below the long-range vote threshold (58 %)
and is carried forward as a weak / unresolved case.

The dosage-like structure is characterised by two divergent homozygous
classes and an intermediate heterozygous class, consistent with the
presence of alternative long-range haplotypes. Because this signal reflects
haplotype behaviour rather than direct breakpoint orientation, these regions
are referred to as recombination-suppressed haplotype blocks rather than
confirmed inversions. Persistence of the same sample groupings across
consecutive windows indicates reduced effective recombination within the
intervals.

---

## 7.2 Population-genetic signatures consistent with overdominance and divergent haplotype maintenance

For each block, the 226 hatchery samples were assigned to one of the three
karyotype classes (H1H1 / H1H2 / H2H2) and the per-class counts compared
with Hardy–Weinberg expectation. Per-window summaries — nucleotide
diversity *π*, the H1-vs-H2 contrast `arrangement_FST_like`, the
inbreeding coefficient `HWE_FIS`, and observed vs expected heterozygosity —
were then averaged across each block (Table 7.2).

**Table 7.2.** Population-genetic summaries for the three candidate blocks.
Counts are observed; `HWE_p` is the 1-df chi-square p-value from
`math.erfc(√(χ²/2))`; `HWE_FIS = 1 − H_obs / H_exp` (negative values =
heterozygote excess); `arrangement_FST_like_mean` is the per-window mean
of the H1-vs-H2 contrast.

| Block | Chrom | n H1H1 | n H1H2 | n H2H2 | Heterozygote diversity | HWE p | HWE_FIS | arrangement_FST_like mean | Interpretation |
|-------|-------|-------:|-------:|-------:|------------------------|------:|--------:|--------------------------:|----------------|
| LRR01 | C_gar_LG28 | 64 | 114 | 48 | increased | 0.834 | −0.014 | 0.730 | divergent maintenance |
| LRR02 | C_gar_LG14 | 34 | 126 | 66 | increased | 0.038 | −0.138 | 0.477 | overdominance-like |
| LRR03 | C_gar_LG07 | 36 | 104 | 86 | increased | 0.627 | +0.032 | 0.304 | unresolved |

LRR02 is the most overdominance-like case: heterozygotes are present in
substantial excess (`HWE_FIS = −0.138`, p = 0.038 against
the Hardy–Weinberg null), and the H1-vs-H2 contrast averages 0.48 across
the interval. LRR01 passes HWE but its `arrangement_FST_like` is
considerably higher (0.73), supporting **divergent haplotype maintenance**
without a strong heterozygote excess. LRR03 is consistent with HWE but its
between-class differentiation is modest and is not interpreted further at
this stage.

The per-class count comparison and the per-window popstats trace are
shown for the LRR01 showcase candidate as **Figures 7.2–7.4**
(`LRR01/figures/fig2_karyotype_groups.svg`, `fig3_popstats_track.svg`,
`fig4_heterozygosity.svg`); the corresponding figures for LRR02 and LRR03
sit in their own candidate folders. The block-level frequency summary
(allele frequency, expected vs observed class counts, χ², p, FIS) is
written as a small info-card SVG (**Figure 7.5**,
`LRR01/figures/fig5_frequency_summary.svg`).

These patterns are consistent with overdominance, associative overdominance,
or linked-load sheltering, although they do not distinguish among these
mechanisms by themselves. Elevated `arrangement_FST_like` further indicates
that the alternative haplotypes carry differentiated genetic backgrounds
across the interval. Estimating the per-class deleterious burden (SIFT or
equivalent) is a future step required to test the sheltered-load scenario;
the column is reserved in Table 7.2 (`deleterious_burden_SIFT`) and
labelled `n/a (not in demo)`.

---

## 7.3 Mendelian segregation of recombination-suppressed haplotypes within inferred families

The inferred broodline (family) structure from Chapter 6 was used to test
whether the candidate haplotype blocks segregate as coherent inherited
units. For each of 18 informative families, parental and offspring
karyotype calls were compared across the block; offspring whose karyotype
was not explicable from any parental combination were counted as
inconsistent, and apparent within-block crossovers were counted as internal
switches (Table 7.3).

**Table 7.3.** Segregation consistency and apparent crossover depletion
within inferred families. Per-family counts are aggregated across the 18
families to a single block-level row.

| Block | Informative families | Informative offspring | Mendelian-consistent | Inconsistent | Apparent internal switches | Estimated recombinant rate | Interpretation |
|-------|---------------------:|----------------------:|---------------------:|-------------:|---------------------------:|---------------------------:|----------------|
| LRR01 | 18 | 103 | 101 | 2 | 0 | 0.000 | coherent inheritance |
| LRR02 | 18 |  88 |  79 | 9 | 6 | 0.068 | weak / unresolved |
| LRR03 | 18 |  72 |  64 | 8 | 8 | 0.111 | weak / unresolved |

LRR01 inherits as a coherent unit: 101/103 informative offspring are
Mendelian-consistent and **no** within-block internal switches are observed
across the 7.2 Mb interval, consistent with strong suppression of effective
recombination across the block. LRR02 shows partial coherence (89.8 %
consistent) with a small number of apparent internal switches (estimated
recombinant rate 0.068); LRR03 fails the segregation test (recombinant rate
0.111) and is downgraded.

This analysis tests the functional behaviour of the blocks rather than
their structural mechanism. Where recombination is suppressed across an
interval, offspring are expected to inherit long intact H1 or H2 haplotypes
with few apparent internal crossovers; Mendelian consistency together with
depletion of internal switches therefore provides independent support that
the candidate LRR intervals behave as inherited recombination-suppressed
haplotype blocks. LRR01 satisfies this expectation; LRR02 and LRR03 do not,
and are interpreted with corresponding caution.

---

## Conclusion

Together, these analyses show that the broodstock population carries
long-range haplotype blocks with signatures of reduced effective
recombination. The blocks were detected through stable short-range and
long-range sample grouping (Section 7.1), showed population-genetic
patterns consistent with divergent haplotype maintenance — and, for LRR02,
with explicit heterozygote excess — (Section 7.2), and, where informative
family structure was available, segregated as coherent haplotype units
(Section 7.3). Although some of these regions may correspond to polymorphic
inversions or other structural variants, the primary evidence presented
here supports their classification as **recombination-suppressed haplotype
blocks**. This distinction avoids overinterpreting short-read breakpoint
calls while preserving the central biological signal: major genomic
intervals in the broodstock population behave as long inherited haplotypes
that may be maintained by overdominance, associative overdominance, or
linked selection.

---

### Reproducibility

Every value above is regenerable end-to-end with three commands run from
the repository root:

```
python3 toolkit_registries/relatedness/scripts/gen_candidate_demo.py
python3 toolkit_registries/relatedness/scripts/harvest_candidates.py
python3 toolkit_registries/relatedness/scripts/render_candidate_figures.py
```

The first synthesises the per-candidate evidence files (deterministic,
seeded); the second writes `table_7_{1,2,3}.tsv`; the third writes five SVGs
per candidate into `<id>/figures/`. SVGs embed no timestamp and are
byte-identical across runs (verified by md5). Every JSON file validates
against its `*.schema.json` in
`toolkit_registries/schemas/structured_block_schemas/` (verified by
`jsonschema.Draft7Validator`).
