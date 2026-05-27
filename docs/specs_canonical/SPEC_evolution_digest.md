# EVOLUTION specs — digest with reference anchors

The evolution science of MS_Inversions lives in a tight cluster of specs.
Below: each evolution spec, what it does, and the **literature anchor it
actually cites** (verified against the recovered full-text files, not from
memory). Ranked by how central evolution is to the spec.

## The core four (evolution is the whole point)

### SPEC_inversion_age_atlas_surface.md  (+ _AMENDMENT)
The main evolution surface. Two tasks: **between-inversion** age ordering
and **within-arrangement** age. Anchors:
- **Guerrero et al. 2012, MBE** — coalescent divergence-profile shape;
  basis for Tajima's-D-as-age-proxy classes (FLAT / U_SHAPE / CENTRAL_PEAK
  / BREAKPOINT_PEAKS / MIXED). Row C of the surface.
- **Berdan et al. 2023, J Evol Biol** — arrangement-specific load matrix
  (Row D); the INV-private-vs-REF-private burden prediction
  (`berdan_prediction_met`, `inv_private_fraction`).
- **Porubsky et al. 2022, Cell (Fig 3C/D)** — bimodality of pairwise
  divergence → recurrent vs single origin.
- **Corbett-Detig & Hartl 2012, Genetics** — why absolute-My dating is
  unrealistic at hatchery timescales (motivates the AMENDMENT).
- **AMENDMENT** drops absolute-My in favour of relative ordering + soft
  anchors only (catfish has no fossil calibration).

### ushape_evolution_class_rules.md
Plain-language class rules for the divergence-profile U-shape. Pure
Guerrero-2012 territory: U_SHAPE = old inversion with locally adapted
alleles; the diversity-vs-position curve is the coalescent-time signal
projected onto θπ. This is the interpretation key for Row C above.

### SPEC_inversion_age_origin_atlas.md  /  SPEC_age_origin_panel.md
The cheat30 GDS (genotype divergence score) surface on candidate focus.
Tier-1 anchored: **Porubsky 2022** (origin classification), **Hartigan
1985, Annals of Statistics** (dip test for uni-/bimodality of carrier GDS),
**Corbett-Detig & Hartl 2012** (age proxy). The two files overlap — index
flags "consolidate later."

### SPEC_busco_4d_age_brackets.md
The one place absolute age is attempted, done honestly: BUSCO 4-fold-
degenerate (neutral) sites + **three-μ bracketing** (low/mid/high mutation
rate) to bracket inversion age rather than point-estimate it. The
methodologically careful companion to the relative-age surface.

## Selection / divergence machinery (evolution-adjacent, method-anchored)

### SPEC_boundary_confirmation_5track.md
The "convicting" composite figure. Anchors: **Bhatia 2013** (Hudson F_ST
estimator) and **Crane 2015** (insulation score). Tracks: local-PCA |z|,
Hudson F_ST (HOM_REF vs HOM_INV), dXY, θπ by karyotype, repeat density.

### SPEC_xpehh_track.md
XP-EHH per-window selection scan. Anchor: **Sabeti et al. 2007** (the
XP-EHH method; also the n ≥ 30 effective-sample-size recommendation for
stability). Detects haplotype-based selection between arrangement classes.
Caveat baked in: underpowered at Ne~20, so framed as exploratory.

### SPEC_hypothesis_test_framework_atlas.md  /  SPEC_hypothesis_registry_and_multispecies.md
T1–T11 hypothesis tests with BH correction (Mendelian transmission,
ancestry jackknife, Clair3 indel concordance, theta-het prior). The
registry is where every per-candidate evolutionary verdict is catalogued.

## Cross-species / deep-time evolution

### SPEC_phylogenetic_tree_integration.md
**Dollo parsimony** for placing each inversion's gain/loss on the
Siluriformes tree. Branch-length / time context via **r8s (Sanderson
2003)**. This is the deep-time (between-species) evolution layer, distinct
from the within-cohort age work above.

### SPEC_comparative_te_breakpoint_fragility.md
TE enrichment at breakpoints → NAHR-mechanism / fragile-site reuse across
catfish lineages. Benchmarked against **Wang et al. 2023 (Nat. Commun.)**
inversion-rate / TE-enrichment figure idiom. Evolution of breakpoint
architecture, not of the polymorphism itself.

### SPEC_busco_anchors.md  /  SPEC_cross_species_dotplot.md  /  SPEC_OVERVIEW_multispecies_architecture.md
The synteny scaffolding the deep-time evolution sits on (wfmash alignment,
BUSCO single-copy anchors, the integration map). Method infrastructure
rather than evolution claims.

## The honest-limits doctrine running through all of them
- Tajima's D: **pooled-only, as a relative-age proxy (Guerrero 2012)**,
  NEVER as a selection test in this cohort. Per-arrangement D ruled out
  (Ne~20, ~30/class = uninterpretable).
- POD / pseudo-overdominance: minimal v20 claim = **differential
  deleterious burden across inversion subunits**, WITHOUT invoking
  balancing selection. "POD-compatible", never "POD found."
- Absolute dating avoided; relative ordering + soft anchors only.
- "compatible" not "found" wording for any mechanism inference.

## Full reference list (verified present in the recovered spec text)
- Berdan et al. 2023, J Evol Biol — inversion load / arrangement-specific
  burden framework.
- Guerrero et al. 2012, MBE — coalescent divergence-profile shape / age.
- Porubsky et al. 2022, Cell — recurrent-vs-single origin via pairwise
  divergence bimodality.
- Corbett-Detig & Hartl 2012, Genetics — inversion age inference limits.
- Hartigan 1985, Annals of Statistics — dip test (uni/bimodality).
- Bhatia 2013 — Hudson F_ST estimator.
- Hudson 1992 — F_ST / dXY foundations.
- Crane 2015 — insulation score.
- Sabeti et al. 2007 — XP-EHH selection scan.
- Sanderson 2003 — r8s molecular dating.
- Wang et al. 2023, Nat. Commun. — TE/inversion-rate comparative idiom.
- Dollo parsimony — inversion gain/loss on phylogeny (method, no single
  citation in-spec).

## Refs known from the manuscript/thesis side but NOT cited inside these
specs (add when writing prose — they're the conceptual backbone)
Kirkpatrick & Barton 2006 (local-adaptation model); Wellenreuther &
Bernatchez 2018 (review / Table 1 template); Faria et al. 2019 (evolving
inversions); Schwander et al. 2014 (supergenes); Charlesworth 1974 + Ohta
1971 (AOD / load-stabilised polymorphism); Charlesworth & Charlesworth
2000 (Y-degeneration mechanisms); Sturtevant & Mather 1938, Pálsson &
Pamilo 1999 (pseudo-heterozygote advantage); Nei et al. 1967 → Connallon &
Olito 2022 (mutational-load argument); Dobzhansky 1947, Yang et al. 2002
(rarer arrangements carry more load); Mérot et al. 2021 (Coelopa); Korunes
& Noor 2017 (gene conversion in inversions); Hardarson et al. 2023 (NCO
tract lengths); Koch et al. 2021, Durmaz et al. 2018 (inversion-as-QTL).
