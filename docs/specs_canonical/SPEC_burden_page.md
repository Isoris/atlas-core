# SPEC — diversity-atlas `burden` page (functional burden / selection efficacy)

**Status**: scaffold. Builds on the legacy
[_handoff_docs/SPEC_2026-05-12_functional_burden.md](../_handoff_docs/SPEC_2026-05-12_functional_burden.md)
design doc. Single most complex page in the diversity atlas — folds
5 functional-burden layers + 4 stratification modes + variant inventory.

**Scaffolded in:**

| file | role |
|---|---|
| [`pages/functional/burden.html`](../atlases/diversity/pages/functional/burden.html) | static fragment with 5-layer toggle, stratification pill, variant inventory table, optional GERP panel, transcript view, MSA panel |
| [`pages/functional/burden.js`](../atlases/diversity/pages/functional/burden.js) | mount lifecycle, layer/stratification routing, table renders |

**Sister page**: [`roh`](SPEC_roh_page.md) — shares the stratification pill (per `roh.html` UI design)

---

## 1. The biological hypothesis

> The 226-sample cohort experiences selection: harmful variants (LOF,
> missense, regulatory) should be **depleted** in fish with longer
> generations of cumulative selection, and **enriched** in
> hatchery-bottlenecked / inbred fish. The strength of this depletion
> measures the cohort's **selection efficacy** — how well it has
> cleared its mutational load.

This page lets the reviewer answer five related questions about that:

1. **Deleterious burden** (VESM): are there fewer / more
   deleterious-predicted missense variants than expected? Is the
   ratio different across cohort strata?

2. **πN / πS**: per-gene ratio of non-synonymous to synonymous diversity
   — the classical molecular-evolution proxy for selection strength.

3. **π0 / π4**: per-gene ratio of diversity at zero-fold (always-coding)
   to four-fold (silent) sites — same idea, alternative degeneracy
   classification.

4. **LOF count**: per-gene count of high-confidence
   loss-of-function variants — direct burden indicator.

5. **ROH overlap fraction**: per-gene fraction of cohort F_ROH
   overlapping the gene — high overlap suggests historical purifying
   selection (deleterious variants purged via inbreeding-load
   purification) OR low-recombination region.

Each of these is a **continuous per-gene metric**. The page surfaces
all 5 simultaneously, lets the user stratify the cohort 4 ways, and
provides drill-downs (variant inventory by snpEff impact class, GERP
panel, transcript view, MSA panel) for specific genes.

The legacy [_handoff_docs/SPEC_2026-05-12_functional_burden.md](../_handoff_docs/SPEC_2026-05-12_functional_burden.md)
covers the per-stat biology in depth. This SPEC focuses on the
atlas-side contract + UI behaviour.

## 2. Data input

**v1 today** (static):
- `data/diversity/burden_per_gene.tsv` — per-gene rows with the 5 layers
- `data/diversity/variant_inventory.tsv` — per-variant rows for the inventory drill-down
- `data/diversity/gerp_per_position.tsv` — optional; off by default
- `data/diversity/transcripts.tsv` — for the transcript view
- `data/diversity/msa_per_gene/<gene_id>.fasta` — for the MSA panel (per-gene fetch)

**v2 target** (envelope-aware): a typed `diversity_functional_burden_v1` envelope. The 5 layers + the variant inventory live in one envelope; the GERP + transcript + MSA are auxiliary cold-tier file fetches keyed by gene.

```
payload.genes[i] = {
  gene_id, gene_name, chrom, start_bp, end_bp,
  vesm_burden:         number | null,    // mean VESM score across deleterious-predicted variants in this gene
  pi_n:                number | null,    // nonsynonymous nucleotide diversity
  pi_s:                number | null,    // synonymous nucleotide diversity
  pi_n_over_pi_s:      number | null,    // pi_n / pi_s
  pi_0:                number | null,    // 0-fold degenerate
  pi_4:                number | null,    // 4-fold degenerate
  pi_0_over_pi_4:      number | null,
  n_lof:               integer | null,
  roh_overlap_fraction: number | null,   // fraction of cohort F_ROH overlapping this gene's bp span
  // Per-stratum slices when stratification is requested:
  per_K_cluster?:      [ { cluster: int, vesm_burden, pi_n, ...}, ... ],
  per_F_ROH_quartile?: [ ... ],
  per_family?:         [ ... ],
  per_sex?:            [ ... ],
}
```

Producer: cross-atlas pipeline reading from `/mnt/e/results_diversity/05_aggregated/`
+ snpEff annotation + ROH overlap join. Adapter pattern follows the cookbook.

## 3. The 5 layers

### 3.1 VESM deleterious burden

Per gene, mean VESM (Variant Effect Score Model) across variants
predicted deleterious (typically `vesm_score < -2.0` threshold). High
VESM burden = many deleterious variants surviving in the cohort.

### 3.2 πN / πS

Per gene:

```
pi_n  = pairwise nucleotide diversity at nonsynonymous sites only
pi_s  = pairwise nucleotide diversity at synonymous sites only
ratio = pi_n / pi_s
```

Interpretation:
- `ratio < 1` → purifying selection on nonsynonymous variants (typical)
- `ratio ≈ 1` → neutral evolution
- `ratio > 1` → positive selection (rare; check signal)

### 3.3 π0 / π4

Same idea, different degeneracy:
- π0: diversity at zero-fold degenerate sites (any change is non-synonymous)
- π4: diversity at four-fold degenerate sites (any change is synonymous)

The π0/π4 ratio is sometimes preferred over πN/πS because the
degeneracy class is unambiguous (not dependent on the genetic code's
preferred-AA logic).

### 3.4 LOF count

Per gene, count of high-confidence loss-of-function variants
(stop-gained, frameshift, essential-splice-disrupting). snpEff impact
class HIGH. Cohort-level count.

### 3.5 ROH overlap fraction

Per gene:

```
overlap_fraction = #{ samples with ROH overlapping the gene's span } / cohort_n
```

High overlap suggests:
- The gene sits in a region commonly inbred (recent demographic event)
- OR the gene is under strong purifying selection (selection drove
  deleterious-allele-carrying samples to F_ROH = 1 at this locus)

The two interpretations are not separable from this stat alone;
cross-page (`roh` + `ancestry`) context is needed.

## 4. The 4 stratifications (shared pill)

Per the manifest tooltip, the stratification pill has 5 options:

| value | meaning | source |
|---|---|---|
| `all` (default) | cohort-wide | no stratification |
| `K=8 cluster` | per-K=8-cluster slice | `state.shared.activeQK` + per-cluster Q assignment |
| `family` | per-family-hub slice | family_hubs envelope (cross-atlas: relatedness) |
| `per-sample` | one row per sample | individual-level breakdown |
| `F_ROH quartile` | Q1..Q4 by per-sample F_ROH | computed in-browser from F_ROH values |

When the pill is set to anything other than `all`, the burden table
shows N additional columns — one per stratum value. E.g. with `K=8 cluster`,
each row has 1 `all-cohort` column + 8 per-cluster columns for each of the
5 burden layers.

The pill state is **shared with the `roh` page** via
`state.shared.diversityStratification`.

## 5. The variant inventory drill-down

When the user clicks a gene row, a side panel opens with:

### 5.1 Variant inventory table

One row per variant in the gene's span. Columns:
- Position, ref, alt, AF (allele freq in cohort)
- snpEff impact: HIGH | MODERATE | LOW | MODIFIER (colour-coded)
- VESM score (when missense)
- LOF flag

### 5.2 GERP panel (optional, off by default)

Per-position GERP score (vertebrate conservation). High GERP =
deeply-conserved position = stronger evidence the variant is functional.

Off by default because the per-position GERP track is bandwidth-heavy
(per-bp; tens of MB per chrom). User opts in via a toggle.

### 5.3 Transcript view

Gene's transcripts laid out as a track with exon/intron/UTR boxes.
Variants overlaid as ticks colour-coded by impact. The standard
"variant browser" view.

### 5.4 MSA panel

For the protein product of the canonical transcript: multiple sequence
alignment of orthologs (typically pre-computed against vertebrate
reference set). Highlights conservation per residue; positions of
variant amino-acid changes annotated.

MSA fetch is **per-gene cold-tier** — only loaded when the user expands
the panel.

## 6. The math (per-layer + stratification)

### 6.1 πN / πS bootstrap CI

Per gene, the πN/πS ratio is a noisy small-n statistic. Producer
should ship per-stat bootstrap CIs:

```
For b = 1..B (B ≥ 1000):
  Resample SNPs in the gene WITH replacement
  Recompute pi_n_b, pi_s_b → ratio_b
ratio_CI = [2.5th, 97.5th percentile] of ratio_b
```

Renderer shows ratio as `value [CI_lo, CI_hi]` when the producer ships
CIs; falls back to point estimate alone otherwise.

### 6.2 Per-stratum statistics

For the K=8 cluster slice:

```
For each cluster c:
  vesm_burden_c = mean VESM across deleterious variants in samples ∈ cluster c
                  (variants whose carriers are in cluster c)
  pi_n_c, pi_s_c → same formula but using only cluster c samples
```

Some samples are admixed (hard_call = -1) and contribute to no
cluster. Producer-side decision: drop admixed from per-cluster stats,
OR weight by q-vector. Default: hard-call (drop admixed).

### 6.3 KW omnibus across strata

When stratification is on, the page can run a KW test across strata:

```
For each gene, KW test on (vesm_burden_c) across c = 1..K
                          (each cluster contributes one value)
With K=8, df = 7; gene-level KW per layer.
```

This identifies genes whose burden is significantly stratum-dependent.
The natural manuscript-grade test for "this gene shows ancestry-specific
selection" / "this gene's burden differs by inbreeding level".

Multiple-comparison: across ~20_000 genes, Bonferroni at α = 0.05 →
p < 2.5e-6. BH-FDR more practical.

Out of scope for v1 page — but the data is there once stratification is
on. v2 should add a "KW per gene" column to the table.

## 7. State + interaction

- `state.shared.diversityStratification` — shared with `roh` page; toggled via the pill
- `state.shared.activeGene` — set on row click; opens the inventory drill-down
- `state.shared.activeQK` — read; determines the K for K-cluster stratification

## 8. Failure modes

| # | condition | behaviour |
|---|---|---|
| 8.1 | πS = 0 (no synonymous variants in a small gene) | πN/πS undefined; render `—`; flag the row |
| 8.2 | π4 = 0 (no 4-fold sites in a tiny gene) | π0/π4 undefined; render `—` |
| 8.3 | VESM scores missing for some variants | mean-over-non-null; if all-null, the layer renders `—` |
| 8.4 | Gene span overlaps an assembly gap | producer-side decision; if shipped, render a warning chip |
| 8.5 | ROH overlap = 1 (every sample has ROH spanning gene) | shown as 1.0; cross-link to `roh` page recommended |
| 8.6 | Stratum-pill value invalid (e.g. user passes a K that's not in available_K) | default back to `all`; render a toast |
| 8.7 | Per-K stratification but K = 1 (no actual structure) | stratification table has one column; matches `all` view |
| 8.8 | GERP file missing on toggle-on | render "GERP data not available" in the panel |
| 8.9 | MSA file missing for active gene | render "MSA not available" in the panel; other panels still work |

## 9. What's currently NOT modelled

### 9.1 Envelope-aware data source

Producer pipeline + adapter pair pending. v2.

### 9.2 Per-gene KW test for stratum dependence (§6.3)

The data is there once stratification is on; the test is the next step. Manuscript-grade extension.

### 9.3 Polarization (ancestral / derived)

The 5 burden layers use folded site frequency spectra (no
ancestral-state inference). When an outgroup is available (e.g. another
*Clarias* species), polarising the SFS lets you separate "this allele is
old / ancestral" from "this allele is new / derived" — the derived
allele frequency is the cleaner deleteriousness proxy. Out of scope
for v1.

### 9.4 Long-range LD adjustment

Per-gene stats are biased when the gene sits in a long-LD block (the
SNPs aren't independent). A v2 BH-FDR-aware test should weight by
effective number of independent tests, computed from LD. Hard problem;
out of scope.

### 9.5 Cross-atlas cross-gene rank

A gene's burden in this cohort is interesting if it's also high in
other catfish cohorts (population convergence) or specifically high
in this one (cohort-specific). Cross-atlas cross-cohort comparison is
a future evolution-atlas feature, not this page's scope.

### 9.6 Drug-target / disease-gene annotation overlay

For prioritization, annotating each gene with "is this a known drug
target / human-disease gene / fish-aquaculture-trait gene" would help
the reviewer focus on the relevant subset. Annotation join; out of
scope for v1.

## 10. Cross-page links

- Row click → `state.shared.activeGene`
- Stratification pill state shared with [`roh` page](SPEC_roh_page.md)
- Active gene's chromosome → routes [`chromosomes` page](SPEC_chromosomes_page.md) + [`hotspots` page](SPEC_hotspots_page.md) to that chrom
- Active gene's span overlapping a hotspot → flag visually

## 11. UI surface

```
┌────────────────────────────────────────────────────────────┐
│ status badge — n_genes · layers shown · stratification     │
│   "12_400 genes · 5 layers · stratified by K=8 (8 strata)" │
├────────────────────────────────────────────────────────────┤
│ Stratification pill: [all] K=8 | family | per-sample | F_ROH-quart│
│ Layer toggle:        VESM | πN/πS | π0/π4 | LOF count | ROH overlap│
├────────────────────────────────────────────────────────────┤
│ Per-gene burden table (sortable)                           │
│   gene_id · chrom · start · end · <selected layer columns> │
│   row click → activeGene + open drill-down                 │
├────────────────────────────────────────────────────────────┤
│ Drill-down side panel (slides out when a gene is clicked)  │
│   - Variant inventory table (by snpEff impact)             │
│   - GERP panel (toggle; off by default)                    │
│   - Transcript view (exon/intron/UTR + variants)           │
│   - MSA panel (per-gene fetch)                             │
├────────────────────────────────────────────────────────────┤
│ [Export TSV: gene table] [Export VCF: variant inventory]   │
└────────────────────────────────────────────────────────────┘
```

## 12. Promotion criteria

| criterion | v1 | v2 |
|-----------|----|----|
| Per-gene burden table renders with 5 layers | ✓ | ✓ |
| Stratification pill works (4 modes) | ✓ | ✓ |
| Variant inventory drill-down | ✓ | ✓ |
| GERP panel (toggle) | ✓ | ✓ |
| Transcript view | ✓ | ✓ |
| MSA panel (per-gene cold fetch) | ✓ | ✓ |
| Envelope-aware (`diversity_functional_burden_v1`) | ✗ | required |
| Adapter pair shipped | ✗ | required |
| Bootstrap CIs for πN/πS, π0/π4 | ✗ | required (§6.1) |
| Per-gene KW test column (§6.3) | ✗ | nice-to-have |
| 30+ assertion JS smoke | ✗ | required |

## 13. Open biological design questions

### 13.1 VESM threshold

`vesm_score < -2.0` is a reasonable deleterious cutoff (common in
fish-genomics literature). Stricter thresholds reduce false-positives
but also reduce power. v2 should expose the threshold as a per-page
slider.

### 13.2 Stratification weighting

When stratification is `K=8 cluster`, admixed samples (q < 0.7 for any
cluster) are excluded. Alternative: weight each sample by their
q-vector, treating each sample as a partial member of each cluster.
The second is more biologically accurate; the first is simpler. v2
choice.

### 13.3 Per-stratum πN / πS normalization

When comparing πN/πS across strata, the denominator differences matter:
a small stratum has high noise. Producer should ship per-stratum
n_synonymous_sites_used; renderer should grey out cells where the
stratum has < 100 synonymous sites.

### 13.4 LOF curation

snpEff impact = HIGH is a coarse filter. Some HIGH-impact variants are
benign (alternative-isoform skipping, NMD-escape). Curation against
LOFTEE-style rules would refine; out of scope for v1.

### 13.5 Cross-stratum effect-size reporting

Beyond p-values, the manuscript-grade output is **fold-change of
burden between strata**. v2 should report `(burden_max_stratum −
burden_min_stratum) / mean_burden` alongside the KW p-value, so the
user sees both significance and magnitude.
