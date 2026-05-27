# SPEC — Functional Burden / Selection Efficacy (new diversity-atlas page)

**Date:** 2026-05-12
**Target atlas:** diversity-atlas (new page — "main home" for functional burden)
**Target page:** **`atlases/diversity/pages/functional/page10.{html,js}`** —
  *Functional Burden / Selection Efficacy*. Dedicated new section
  `functional/`. User direction 2026-05-12: *"it should be on its own
  page — we have evolution of proteins + VESM + deleterious functional
  and per group of genes and many things"*.
**Companion overlay:** Inversion Atlas per-candidate consequence panel —
  small per-karyotype subset of the same layers (see §10). **Not** a new
  Inversion Atlas page; a panel inside the existing per-candidate view.
**Status:** spec only. No pipeline run. No new page code.

> ## ⚠ Resolved decisions (2026-05-12 round-1 session)
>
> Four of the six original UNFINISHED decisions were resolved
> interactively. Two remain.
>
> 1. ✅ **Page location:** new `functional/` section, dedicated
>    `page10.html` + `page10.js`. (§6.1 below — resolved.)
> 2. ✅ **πN/πS estimator:** deferred to the **unified ancestry
>    repo** dispatcher. The atlas does not pick the method; it
>    reads whatever the pipeline emits via the same dispatcher
>    pattern already used by `texture_metrics.json`. The unified
>    ancestry repo owns the method choice. (§6.2 below — resolved.)
> 3. **0-fold/4-fold degeneracy source.** Constrained by the
>    annotator pick (see (5) below). bcftools csq + snpEff give
>    per-site syn/missense/LOF tags but neither emits 0/4-fold
>    directly — a small custom degeneracy classifier from
>    genome-atlas CDS FASTA is still needed downstream. Decision
>    deferred to upstream pipeline session. (§6.3.)
> 4. **VESM payload source.** Still data-blocked — VESM-for-catfish
>    does not exist yet. The atlas reads `vesm_burden` from the
>    payload; the predictor choice (canonical VESM / on-the-fly /
>    AlphaMissense-fish substitute) is owned by the upstream
>    pipeline session. (§6.4.)
> 5. ✅ **Annotator tool:** **bcftools csq + snpEff** (both, cross-confirm).
>    csq is haplotype-aware (correct syn/nonsyn calls for MNPs and
>    adjacent variants); snpEff provides the HIGH-impact LOF tags
>    and broad annotation. Agreement between the two becomes a
>    confidence filter on the LOF set. (§6.5 below — resolved.)
> 6. ✅ **Stratification axis:** **all modes selectable** — pill
>    toggle with K=8 (default) / per-family / per-sample drill-down
>    / F_ROH-quartile. Same pill set is used by the ROH-burden page.
>    (§6.6 below — resolved.)
> 5. **LOF caller.** Options on the table: snpEff "HIGH" impact
>    (stop-gain / start-loss / splice-donor/acceptor / frameshift)
>    / LOFTEE (Ensembl VEP plugin) / custom rule set. See §6.5.
> 6. **Stratification axis.** Same question as the ROH-burden
>    spec (`SPEC_2026-05-12_roh_gene_burden.md` §6.3). Whatever
>    is picked there should match here for consistency. See §6.6.

**Motivation (verbatim from user, 2026-05-12):**

> "πN/πS or π0-fold/π4-fold belongs on the same page as VESM, because
> both are about functional burden / selection efficacy / deleterious
> variation. But they are not the same layer."
>
> User reference: Harrang et al. 2013; Lohmueller 2014; Do et al. 2015;
> Henn et al. 2015 — πN/πS and π0/π4 as common measures of selection
> efficacy *within species*.

The page answers, per fish / family / ancestry group / cohort:

**What is the functional genetic health of this stratum?**

Five layers, ordered from variant-effect prediction → population-genetic
signal → realised homozygous burden:

| # | Layer | What it measures | Interpretation |
|---|---|---|---|
| 1 | VESM / deleterious predictor | predicted-damaging variant count or score sum | direct functional-risk score |
| 2 | πN/πS | nonsynonymous π ÷ synonymous π | coding burden / selection-efficacy proxy |
| 3 | π0-fold/π4-fold | π at 0-fold degenerate sites ÷ π at 4-fold degenerate sites | codon-position version of (2); independent of transcript model quality |
| 4 | LOF burden | stop-gain + frameshift + splice-disrupting allele counts | high-confidence severe burden |
| 5 | ROH-overlap burden | fraction of (1)/(2)/(3)/(4) that falls inside ROH | inbreeding-realised burden |

Layers 1, 4, 5 are *counts* (deterministic given an annotation).
Layers 2, 3 are *ratios* (need a denominator and a confidence interval).

---

## 1. Why these belong on one page

All five layers describe **deleterious variation realised in this cohort**.
They differ in how they detect it:

- VESM and LOF say *"this variant is predicted to be damaging"* — sequence-
  level / per-variant.
- πN/πS and π0/π4 say *"this population is carrying more protein-changing
  diversity than its silent baseline predicts"* — population-genetic
  signal across all variants, no per-variant labelling required.
- ROH-overlap says *"and X% of that burden is homozygous"* — realised vs
  latent.

Putting them on separate pages forces the reader to assemble the
interpretation manually. Co-locating them lets the page answer the
composite question "is this stratum carrying more damaging variation
than expected, and is it being expressed?" in one read.

This is also where layers disagree, which is itself diagnostic
(quoting user wording):

> If INV/INV has high πN/πS **and** high VESM burden, the inversion
> arrangement may shelter protein-changing/deleterious variants.
>
> If πN/πS is high but VESM is not high, there is more coding variation,
> but not clearly predicted damaging.
>
> If VESM is high but πN/πS is normal, there may be a few strong-effect
> variants rather than broad coding burden.

The page is the place those three cases become visible side by side.

---

## 2. Cross-atlas dependency

This is **not** a cross-atlas request the way the pairwise-θπ spec was —
the burden statistics are per-cohort summaries that live in
diversity-atlas. But every layer pulls upstream products from
genome-atlas:

| Concern | Atlas |
|---|---|
| Per-sample VCF (genotypes) | Diversity (have) |
| K=8 ancestry labels | Diversity `D.S1.k8` (have) |
| ROH BEDs (per-sample, all 226) | Diversity (have) |
| **Gene model BED + CDS FASTA** | **Genome Atlas (canonical) — NOT YET IN DIVERSITY** |
| **0-fold/4-fold site partition** | **Genome Atlas — DOES NOT YET EXIST** |
| **Annotated VCF (snpEff or VEP, syn/missense/LOF)** | **Genome Atlas pipeline — NOT YET RUN for v2** |
| **VESM scores per site** | **Genome Atlas — DOES NOT YET EXIST for catfish** |
| **Inversion karyotype calls per sample per candidate** | **Inversion Atlas (for the overlay panel only)** |

Same boundary pattern as the ROH-burden spec: the data product is
generated upstream and surfaced into the diversity-atlas as one or
more JSON slots loaded by `shared/data_loader.js`.

---

## 3. Page layout

```
┌────────────────────────────────────────────────────────────────────┐
│ Stat strip (5 cells, cohort-wide):                                 │
│   π    πN/πS    π0/π4    VESM burden    LOF count                 │
│  (with sub-line: 226 samples · K=8 grouping · genome-wide)         │
├────────────────────────────────────────────────────────────────────┤
│ Variant-inventory panel (cohort-wide) — §3.1                       │
│   Horizontal bar chart, 19 mutation types × log10(N SNPs),         │
│   coloured by snpEff impact class (High/Moderate/Low/Modifier).    │
│   Reference: black-grouse Nature 2024 Fig 2c.                      │
├────────────────────────────────────────────────────────────────────┤
│ Stratification pill toggle: [K=8 ▼] [family] [F_ROH-quartile]      │
│                                                  [sample drill ▼]  │
├────────────────────────────────────────────────────────────────────┤
│ ┌──────────────────────┐ ┌──────────────────────┐                  │
│ │ πN/πS per group      │ │ π0/π4 per group      │                  │
│ │ (boxes + strip)      │ │ (boxes + strip)      │                  │
│ └──────────────────────┘ └──────────────────────┘                  │
│ ┌──────────────────────┐ ┌──────────────────────┐                  │
│ │ VESM burden per      │ │ LOF count per        │                  │
│ │ group (boxes + strip)│ │ group (boxes + strip)│                  │
│ └──────────────────────┘ └──────────────────────┘                  │
├────────────────────────────────────────────────────────────────────┤
│ Sortable table: per-sample, 226 rows                               │
│   sample · K=8 · F_ROH · π · πN · πS · πN/πS · π0/π4 ·             │
│   VESM_burden · LOF_count · splice_count · ROH_overlap_fraction    │
│   (CIs on πN/πS and π0/π4 via block-jackknife — see §6.2)          │
├────────────────────────────────────────────────────────────────────┤
│ ROH-overlap stripe (full-width):                                   │
│   For each group, what fraction of VESM/LOF variants falls inside  │
│   ROH? Stacked bar — "in ROH" vs "outside ROH"                     │
├────────────────────────────────────────────────────────────────────┤
│ Transcript-view panel (per-gene picker) — §13                      │
│   Gene structure track (exons/introns/UTRs), variant lollipops     │
│   coloured by effect class, splice gain/loss flags from the        │
│   custom splice module overlaid as ▲/▼ marks.                       │
├────────────────────────────────────────────────────────────────────┤
│ MSA panel (per-variant picker) — §14                               │
│   pyMSAviz-rendered SVG of catfish + ~6–10 teleost orthologs       │
│   ±30 aa around the selected missense variant. Consensus track,    │
│   variant-position marker, conservation colouring.                  │
├────────────────────────────────────────────────────────────────────┤
│ Interpretation card (§8)        │ πN/πS in context (§11)            │
│ — three-case text from §1 —     │   cohort value + 8-row table      │
└────────────────────────────────────────────────────────────────────┘
```

UI affordances (matching existing diversity-atlas page conventions):
- Stratification pill toggle (same set as ROH-burden — see §6.6).
- Plot-type pill toggle (boxes / boxes+strip / violin) — same as page 4.
- Sortable table with all-226 / outliers-only / search.
- Hover tooltips on every plot, showing the underlying counts behind
  each ratio (since a ratio with tiny denominators is noise).
- Click a sample row → drill-down panel like page 1.
- Click a group label → filter to that group across all plots
  (intra-page brushing, not implemented elsewhere yet — flag if
  out of scope for v1).
- **Click a variant lollipop in the transcript-view panel** → loads
  the MSA panel for that variant (§14).
- **Gene picker in the transcript-view panel** → defaults to the
  top-burden gene per K=8 group (one per group, 8-entry dropdown);
  also accepts free-text gene symbol / ENS ID search.

### 3.1 Variant-inventory panel — black-grouse Fig 2c style

Cohort-wide descriptive panel sitting above the stratified group
boxes. Reference: user-provided figure from the *Nature* 2024
black-grouse paper "Deleterious mutations and the architecture of
male reproductive success in a lekking bird", Fig 2c.

Visual:
- Horizontal bar chart.
- Y-axis: 19 mutation-type categories (sorted ascending by count):
  `Initiator codon variant`, `Stop codon retained`, `Stop codon lost`,
  `Start codon lost`, `5' UTR premature start codon`, `Splice acceptor
  variant`, `3' UTR variant`, `Splice donor variant`, `Nonsense
  mediated decay`, `5' UTR variant`, `Stop codon gained`, `Loss of
  function`, `Splice region variant`, `Synonymous variant`,
  `Missense variant`, `Downstream gene variant`, `Upstream gene
  variant`, `Intron variant`, `Intergenic region`.
- X-axis: log10(N SNPs).
- Colour: snpEff impact class — **High** (dark slate `#3F4D6A`),
  **Moderate** (light blue `#8FA8C8`), **Low** (mauve `#8F5577`),
  **Modifier** (yellow `#E6C26B`). Matches the published figure's
  palette closely enough for visual continuity.
- Bar labels: exact count at the bar end.
- Tooltip per bar: `mutation_type · impact class · N (raw) · N
  per Mb of relevant feature class`.

Source: snpEff output post-`bcftools csq` cross-check. The
pipeline writes one cohort-level summary row per `(mutation_type,
impact_class)` pair into `functional_burden.json` under a new
`variant_inventory` block:

```json
"variant_inventory": [
  { "type": "Missense variant", "impact": "Moderate", "n": null },
  { "type": "Loss of function", "impact": "High",     "n": null },
  ...
]
```

The panel is **cohort-wide**, not stratified. It answers the
descriptive question *"what does our cohort's variant set look like
by functional class?"* before the page dives into the group
comparisons below.

**Companion mini-panel — snpEff impact totals** (also from the
black-grouse paper, Fig 2 panel beside Fig 2c). A 4-row collapsed
roll-up of the same data: just High / Moderate / Low / Modifier
totals as a small 4-bar horizontal chart. Renders next to the full
inventory; gives a quick "how big is the High-impact set?" read
without scanning the 19-row chart. The High bar is highlighted
(dark slate) to anchor the eye on the LOF-relevant tier.

### 3.2 GERP constraint-score inventory panel — **OFF BY DEFAULT (no time)**

Sibling panel to §3.1, also cohort-wide. Reference: user-provided
figure from the same black-grouse *Nature* 2024 paper (Fig 2 GERP
panel). Bins variants by per-site GERP (Genomic Evolutionary Rate
Profiling) score — a multi-species-alignment-derived measure of
evolutionary constraint.

**Status (2026-05-12, user direction): off by default — no time to
compute the upstream teleost GERP track right now.** The panel
ships in the page scaffold but renders a "data pending — GERP track
not yet computed in genome-atlas" fallback card unless
`gerp_inventory` is non-null in the payload. A small pill toggle
on the variant-inventory area lets the user enable the panel if
the data lands later; default state is off.

Visual (when data lands):
- Horizontal bar chart.
- Y-axis: 6 GERP-score bins, sorted high-constraint at top:
  `≥4`, `3–4`, `2–3`, `1–2`, `0–1`, `<0`.
- X-axis: log10(N SNPs).
- Colour: uniform grey by default, with **GERP ≥ 4 highlighted**
  in salmon/coral (`#E89A8A`) — matches the published figure and
  flags the high-constraint bin where deleterious variants are
  expected to be enriched.
- Bar labels: exact count at the bar end.
- Tooltip: `GERP bin · N variants · fraction of total · fraction
  predicted LOF/missense in this bin`.

Source (eventually): per-site GERP++ scores from a teleost
multi-species alignment, computed upstream in `genome-atlas`.
Cross-tabulated with the variant call set to produce one count per
bin. The pipeline writes:

```json
"gerp_inventory": [
  { "bin": ">=4", "n": null, "n_lof": null, "n_missense": null },
  { "bin": "3-4", "n": null, ... },
  ...
]
```

**Cost note (why this is deferred).** Building a teleost GERP track
requires:
- A multi-species alignment across ≥10 teleost genomes
  (zebrafish + medaka + tilapia + stickleback + salmon + …, plus
  catfish itself);
- GERP++ run across the alignment to produce per-site RS scores;
- Per-variant intersection with the cohort VCF.

This is real upstream work that the user has correctly flagged as
out of scope for this round. The panel is in the page scaffold so
nothing changes when the data lands — just flip the toggle.

**Future implication for the ROH-burden spec.** If/when GERP lands,
it becomes the natural constraint proxy for the ROH-burden spec's
§6.2 (pLI analog). Until then, that question stays data-blocked.
**Do not flip ROH-burden §6.2 to resolved on this basis right
now** — the GERP track does not exist yet.

---

## 4. Pipeline product (data layer schema)

Goal: one JSON slot, two render modes (group-level + per-sample), with
all five layers in one payload so the page doesn't need to multiplex
fetches.

```json
{
  "_doc": "Functional burden / selection efficacy layers, per sample + per group. Single payload.",
  "version": "v1",
  "generated_at": "2026-05-12T00:00:00Z",
  "pipeline_steps": [
    "vcf annotation (snpEff or VEP) → syn/missense/LOF tags per site",
    "0-fold/4-fold site partition from CDS FASTA",
    "per-sample π, πN, πS, π0, π4 via ANGSD/realSFS or scikit-allel",
    "VESM scoring (or substitute — see §6.4) per site",
    "LOF tally per sample",
    "ROH × functional-site intersection (extends ROH-burden product)"
  ],
  "estimator": {
    "piN_piS_method": "TBD — see §6.2",
    "pi0_pi4_method": "TBD — see §6.3",
    "ci_method": "block-jackknife across chromosomes",
    "block_size_bp": 5000000
  },
  "per_sample": [
    {
      "sample_id": "FISH_0001",
      "k8": "G3",
      "family_id": null,
      "F_ROH": 0.18,
      "pi": null,
      "piN": null, "piS": null, "piN_piS": null, "piN_piS_ci": [null, null],
      "pi0": null, "pi4": null, "pi0_pi4": null, "pi0_pi4_ci": [null, null],
      "vesm_burden": null,
      "vesm_n_sites": null,
      "lof_count": null,
      "lof_in_roh": null,
      "vesm_in_roh_frac": null
    }
  ],
  "per_group": {
    "K=8": [
      {
        "group": "G1",
        "n_samples": null,
        "pi": null,
        "piN_piS": null, "piN_piS_ci": [null, null],
        "pi0_pi4": null, "pi0_pi4_ci": [null, null],
        "vesm_burden_mean": null,
        "lof_count_mean": null,
        "roh_overlap_frac": null
      }
    ]
  },
  "alternative_stratifications": {
    "family": [],
    "F_ROH_quartile": [],
    "karyotype": {}
  }
}
```

Size estimate: ~226 sample rows × ~15 numeric fields + 8 group rows ×
~12 numeric fields + alt stratifications ≈ small (low tens of kB).
Embed in `data/functional_burden.json`, load via
`shared/data_loader.js`.

Empty payload → page renders the same no-data fallback pattern as
page 9 (texture).

---

## 5. Pipeline (where the data comes from)

Pipeline steps in execution order. None of this lives in diversity-atlas;
all of it lives in catfish-diversity-analysis (population products) +
genome-atlas (annotation/CDS products).

1. **Annotate cohort VCF.** snpEff or VEP (decision: §6.5 — same tool
   for LOF and for syn/missense partition). Output: per-site
   functional class.
2. **Build 0-fold/4-fold partition.** From genome-atlas CDS FASTA;
   classify each CDS position by codon-degeneracy. Output: BED of
   0-fold sites and BED of 4-fold sites. Decision: §6.3.
3. **Compute π per class.** Per-sample π over (a) all sites, (b)
   missense, (c) synonymous, (d) 0-fold, (e) 4-fold. Estimator
   choice: §6.2.
4. **Score variants with VESM** (or substitute). Per-site score.
   Decision: §6.4.
5. **Tally LOF.** Per-sample count of high-impact alleles. Decision:
   §6.5.
6. **Intersect with ROH.** For VESM/LOF/missense — per-sample fraction
   inside an ROH call. Reuses the ROH × gene-model intersection
   product from `SPEC_2026-05-12_roh_gene_burden.md` if it lands first.
7. **Aggregate per group.** With block-jackknife CIs across
   chromosomes (default 5 Mb blocks).

Pipeline detail beyond this spec is up to the analysis repo.

---

## 6. Open design questions

### 6.1 Page location & number — ✅ RESOLVED (2026-05-12)

**Decision:** option (C) — new `functional/` section, dedicated
`page10.{html,js}`. User wording: *"it should be on its own page —
we have evolution of proteins + VESM + deleterious functional and
per group of genes and many things"*.

Concretely: create `atlases/diversity/pages/functional/page10.html`
and `page10.js`. Register in `manifest.json` as page 10 with a
new section label (proposed: "functional"). Tab tooltip:
"Functional burden / selection efficacy".

The section is sized for growth — protein-evolution layers beyond
the v1 five (e.g. per-gene-family burden tables, dN/dS heatmaps
once that pipeline exists) will land as additional pages in
`functional/`.

### 6.2 πN/πS estimator — ✅ RESOLVED (2026-05-12)

**Decision:** **deferred to the unified ancestry repo** (pipeline
side, not atlas side). User direction: *"it's in the unified
ancestry repo so just write() to a dispatcher or add to a file
so it will wire to the server later"*.

The atlas does **not** pick the estimator. It reads `piN`, `piS`,
`piN_piS`, and `piN_piS_ci` from the `functional_burden.json`
payload via a dispatcher in `shared/data_loader.js`, in exactly the
same pattern as the existing `texture_metrics.json` reader.

Concrete atlas-side wiring (to land at build time):

```js
// shared/data_loader.js — add to the parallel-fetch block:
const FUNCTIONAL_BURDEN_PATH =
  'data/functional_burden.json';
// ... in loadAll():
const fbResp = await fetch(FUNCTIONAL_BURDEN_PATH).catch(() => null);
ctx.FUNCTIONAL_BURDEN = fbResp && fbResp.ok ? await fbResp.json() : null;
```

`ctx.FUNCTIONAL_BURDEN === null` → page 10 renders the "data
pending" fallback card (same pattern as page 9). The unified
ancestry repo owns the method choice; whatever it writes into the
JSON, the page surfaces.

This keeps the atlas method-agnostic: if the pipeline changes from
site-count to Watterson-θ later, the atlas needs no changes — only
the JSON contents shift.

### 6.3 0-fold/4-fold degeneracy source — **UNFINISHED**

- **(A) snpEff CDS annotations + custom degeneracy classifier** —
  fits if snpEff is already in the annotation pipeline (§6.5).
- **(B) VEP + Ensembl degeneracy table** — fits if VEP wins §6.5.
- **(C) Custom from genome-atlas CDS FASTA** — Biopython
  three-codon enumeration. Tool-independent, slowest.
- **(D) dN/dS-pipeline by-product** — if the ROH-burden spec
  ends up picking dN/dS (option D in that spec's §6.2) for its
  constraint proxy, the 0-fold/4-fold partition falls out of
  that pipeline for free.

### 6.4 VESM payload source — **UNFINISHED**

- **(A) Pre-computed VESM scores from genome-atlas (canonical).**
  Assumes VESM-for-catfish is trained and tabled upstream.
- **(B) On-the-fly VESM prediction per-cohort.** Requires a VESM
  inference pipeline in catfish-diversity-analysis.
- **(C) Non-VESM substitute** (SIFT / PolyPhen-2 / MutPred /
  AlphaMissense fish-adapted). Pick if VESM-for-catfish isn't
  ready yet. The page label changes accordingly ("missense
  deleterious score" — agnostic to predictor).

### 6.5 Annotator stack — ✅ RESOLVED (2026-05-12)

**Decision:** **four-tool stack** — bcftools csq + snpEff + VESM
(missense) + custom splice module.

User direction (2026-05-12): *"csq and snpeff"*, then *"VESM is
also the annotator for missense. and we have a splice module too.
its custom… like snpeff but focus on splice so its a transcript
track showing splice sites gain and loss"*.

Each tool owns one slice of the annotation surface; outputs feed
the payload (§4) and the dedicated panels (§3 variant inventory,
§15 transcript view, §16 MSA).

| Tool | Role | Output used by |
|---|---|---|
| **bcftools csq** | Haplotype-aware syn/missense classification across MNPs and adjacent variants — the πN vs πS partition's source-of-truth | πN/πS, π0/π4 (§3 group boxplots; §11 mini-table) |
| **snpEff** | Impact-class inventory (High/Moderate/Low/Modifier) across all 19 mutation types — the inventory chart's source | §3 variant-inventory panel (new — see below); LOF count |
| **VESM** | Per-missense deleteriousness score AND missense-variant annotator. Replaces a separate missense-effect predictor — VESM does both labelling and scoring | §3 VESM-burden boxplot; §3 inversion-overlay; §11 mini-table |
| **Custom splice module** | Transcript-track style splice-site gain/loss caller (described by user as "like snpEff but focus on splice"). Owned by upstream pipeline; atlas reads its output | §15 transcript-view panel (new — see below) |

**Concrete LOF criterion (high-confidence, default `lof_count`):**
snpEff `IMPACT=HIGH` AND csq consequence in {`stop_gained`,
`start_lost`, `splice_acceptor`, `splice_donor`, `frameshift`}.

**Loose LOF (surfaced via pill toggle):** snpEff `IMPACT=HIGH` OR
csq `splice_region`/`stop_lost` OR custom splice module flagging
a high-disruption splice gain/loss event.

The payload carries `lof_count_strict`, `lof_count_loose`, and
`splice_disruption_count` per sample. Pill toggle switches the
LOF boxplot between strict and loose; splice-disruption count is
its own column in the per-sample table.

**Cross-tool confidence flag (per variant, in payload):**
`confidence_tier ∈ {high, medium, low}` where:
- **high** = csq + snpEff + (VESM if missense) all agree on
  deleterious / LOF
- **medium** = two of three agree
- **low** = only one tool flags

Variants flagged "high" by the cross-tool consensus are the ones
shown by default in the transcript view and the MSA panel.

### 6.5.1 Custom splice module — open spec question

User noted (2026-05-12) that this module is custom and earlier
chat history may describe it ("idk maybe you can add to the spec
or read previous chats"). Per build-session researcher: confirm
whether the upstream "splice module" is:

- **(A) SpliceAI-style deep-learning splice predictor** (per-base
  ΔPSI gain/loss scores), wrapped locally;
- **(B) Pangolin / MMSplice style splice-effect predictor**, locally
  wrapped;
- **(C) Fully custom rule-based splice-site annotator** producing
  per-variant `splice_gain` / `splice_loss` / `splice_disruption`
  flags;
- **(D) Hybrid** (deep predictor + rule-based confirmation).

The atlas does not depend on the choice — it reads
`splice_events[]` from the payload regardless. But the methods card
(§9) needs the real name + version, so confirm at build time.

**Payload addition (per variant included in transcript-view panel):**

```json
"splice_events": [
  {
    "variant_id": "chr07:12345678:A:G",
    "gene": "ENSCGA00000012345",
    "transcript": "ENSCGA00000012345-T1",
    "event": "splice_donor_loss",      // canonical: gain | loss | shift
    "delta_score": 0.83,               // [0, 1] — predictor-specific scale
    "tool": "<TBD — see 6.5.1 above>",
    "tool_version": "<TBD>"
  }
]
```

### 6.6 Stratification axis — ✅ RESOLVED (2026-05-12)

**Decision:** option (E) — **all modes selectable**. Pill toggle
with four states:
  1. **K=8** (default) — 8 ancestry-cluster boxes
  2. **per-family** — one box per `family_id` (only samples with
     metadata; falls back to "no family labels available" if the
     metadata column is empty)
  3. **per-sample drill-down** — table-row click overlays one
     sample's values on top of the K=8 view
  4. **F_ROH quartile** — Q1–Q4 by genome-wide F_ROH, 4 boxes

**Same pill set** must appear on the ROH-burden page
(`SPEC_2026-05-12_roh_gene_burden.md` §6.3, also resolved to
option E). Implement the pill renderer in `shared/` so both pages
share one component.

---

## 7. Sortable-table column set (concrete, no decisions deferred)

For the per-sample table (lower half of the page). 11 columns:

| col | header | source | sort default |
|---|---|---|---|
| 1 | sample | `per_sample[i].sample_id` | asc |
| 2 | K=8 | `per_sample[i].k8` | — |
| 3 | F_ROH | `per_sample[i].F_ROH` | desc (toggle) |
| 4 | π | `per_sample[i].pi` | desc |
| 5 | πN | `per_sample[i].piN` | desc |
| 6 | πS | `per_sample[i].piS` | desc |
| 7 | πN/πS | `per_sample[i].piN_piS` | desc |
| 8 | π0/π4 | `per_sample[i].pi0_pi4` | desc |
| 9 | VESM burden | `per_sample[i].vesm_burden` | desc |
| 10 | LOF count | `per_sample[i].lof_count` | desc |
| 11 | VESM in ROH | `per_sample[i].vesm_in_roh_frac` | desc |

Outlier classing (`outlier-hi`/`outlier-lo`, same convention as page 1):
flag πN/πS > group mean + 1.5σ, π0/π4 > group mean + 1.5σ, VESM burden
> cohort mean + 1.5σ, LOF count > cohort mean + 1.5σ. Notes column
("flag") generated from these.

---

## 8. Interpretation card (text block, lower-page)

Static prose explaining how to read disagreement between layers.
Three cases verbatim from user wording (see §1 above). One paragraph,
no plots, sits at the bottom of the page next to the methods bullets.

---

## 9. Methods card (bullet list)

- π / πN / πS definitions
- 0-fold / 4-fold definitions (link to §6.3 decision once made)
- VESM model version and training cohort (or substitute model — §6.4)
- LOF criterion (§6.5)
- ROH source: `D.S5` (have) — same as page 5
- Block-jackknife CI window size: 5 Mb (default; tunable in payload)
- K=8 source: `D.S1.k8` (have)

---

## 10. Inversion-atlas overlay (companion, NOT a new page)

The Inversion Atlas re-uses the same five layers but **per inversion
candidate, per karyotype group**. Not a full burden page — a small
overlay panel inside the existing per-candidate view.

Wording from user (2026-05-12):

> In the Inversion Atlas, you only show these values per inversion
> candidate. The question becomes: *does this inversion arrangement
> carry more functional burden?*

Panel content per candidate:

| Karyotype | πN/πS | π0/π4 | VESM burden | LOF count | interpretation hint |
|---|---|---|---|---|---|
| STD/STD | … | … | … | … | normal / sheltered / impoverished |
| HET     | … | … | … | … | mixed |
| INV/INV | … | … | … | … | inversion may shelter burden |

Three rows × five numeric columns. Tiny table. Lives in the existing
per-candidate Inversion Atlas page, **not** a new page. The diversity
atlas's pipeline product (§4 above) emits the karyotype stratification
into `alternative_stratifications.karyotype` keyed by inversion ID,
and the Inversion Atlas's per-candidate page reads from that same
JSON when it lands.

No separate spec needed for the overlay — it's the same data product,
different stratification axis. The Inversion-Atlas-side rendering
should be tracked in `KICKOFF_inversion_atlas.md` or the equivalent
sibling-atlas roadmap, not here.

---

## 11. πN/πS reporting in nearly-neutral context — single value, no log–log fit

**Rationale (user direction, 2026-05-12):** a log–log πN/πS-vs-πS
slope test requires **many species** (Romiguier et al. 2014 used
~76 animal species over ~10⁵-fold Ne range). With one species (this
catfish cohort) and ≤8 intraspecific groups spanning a tiny Ne range,
the slope is not estimable in any useful sense. **Therefore, no
scatter plot, no slope fit.** Report πN/πS as a value (cohort-wide
+ per-group mini-table) and let the literature anchor provide the
nearly-neutral context.

### 11.1 Theory (why πN/πS is meaningful at all)

Under the nearly-neutral theory (Kimura 1979) with a gamma-distributed
DFE of shape β, Welch, Eyre-Walker & Waxman (2008) show that the
expected πN/πS is approximately proportional to Ne<sup>−β</sup>.
Higher-Ne species purge slightly deleterious variants more efficiently,
so πN/πS falls. Romiguier et al. (2014) confirmed this empirically
across ~76 animal species: log(πN/πS) decreases linearly with
log(πS), slope ≈ −β (negative; the shape parameter of the DFE).

This is **the reason πN/πS is informative** in the first place — it
locates a population on the efficacy-of-selection axis. But the slope
itself can only be measured at the comparative-genomic scale, which
is not what we have here.

### 11.2 What the page shows instead

**(a) One headline value.** Cohort-wide πN/πS reported in the §3 stat
strip (already specced), with block-jackknife 95 % CI. One number.

**(b) Per-group mini-table.** A small 8-row table beneath the
cohort-wide value, no plot:

| Group | n samples | πS | πN | πN/πS | 95 % CI | rank |
|---|---|---|---|---|---|---|
| G1 | … | … | … | … | … | 1 |
| G2 | … | … | … | … | … | 2 |
| …  | … | … | … | … | … | … |
| G8 | … | … | … | … | … | 8 |

Sorted by πN/πS descending. Coloured cells: top πN/πS in red
(weakest purifying selection), bottom in blue (strongest).
This is a *descriptive* table — no fit, no test of the log–log
prediction.

**(c) Literature anchor card** (static text, no plot):

> **Where does this cohort sit?**
> Romiguier et al. (2014) reported animal πN/πS spanning roughly
> 0.05 (large-Ne marine invertebrates) to 0.30 (small-Ne vertebrates),
> median ≈ 0.17. The log–log slope of πN/πS on πS across those
> ~76 animals was negative (Welch et al. 2008 / Kimura 1979 prediction
> confirmed). Teleosts in that survey clustered around πN/πS ≈ 0.10–0.20.
>
> **This cohort:** πN/πS = `<value>` (95 % CI `<lo>` – `<hi>`).
> Interpretation: weaker / typical / stronger purifying selection
> relative to the animal median.

Three pre-written interpretations depending on whether the cohort
value sits above, near, or below the animal median.

**(d) Caveat sentence (must be on the page).**

> A formal test of the Kimura/Welch/Romiguier log–log relationship
> requires comparative data across many species and is not performed
> here — this cohort is one species. The values above are reported
> for context only.

### 11.3 Why not the scatter

Spelled out so a build-session reviewer doesn't re-add it:

- **Single species, low Ne dispersion.** Group-level πS values within
  one hatchery cohort span <2× — far too narrow to fit a slope that
  literature work measures across ~10⁵-fold Ne range.
- **n = 8 points.** Even if the x-range were adequate, a slope CI
  from 8 points would be near-uninformative.
- **The visual implies a test that isn't being performed.** A scatter
  + fitted line invites the reader to read off β; we cannot honestly
  provide a β from this design. Better to omit the plot than to
  caveat it after the fact.

If a multi-species catfish/teleost cohort ever becomes available,
the scatter belongs in a comparative-genomics atlas, not here.

### 11.4 Counter-evidence noted but out-of-scope here

The nearly-neutral / gamma-DFE framework is not universal:

- **Shifts in selective pressure across lineages.** Elyashiv et al.
  (2010) showed gene-specific selection shifts between two closely
  related yeast species — the DFE itself can vary across taxa.
- **FGM predicts DFE-Ne coupling depends on organism characteristics.**
  Martin & Lenormand (2006), Lourenço et al. (2011), Tenaillon
  (2014): under Fisher's Geometric Model the DFE depends on organism
  "complexity", pleiotropy, and Ne, so a single global slope is an
  approximation, not a theorem.
- **Plants vs animals.** Whether plants share the animal slope is
  still open.

None of this is testable from one cohort. Mentioned here so the
literature-anchor card doesn't overstate the universality of the
Romiguier reference value.

### 11.5 Pipeline product additions

None. The cohort-wide πN/πS and per-group πN/πS are already in §4's
payload (`per_group["K=8"][i].piN_piS` + CIs). No new fields needed.

### 11.6 Page layout (where the mini-table sits)

Bottom-right, beside the §8 interpretation card. ~40 % column width.
Three stacked blocks: headline value (large, bold), 8-row sorted
table, literature-anchor card with one-sentence verdict.

```
┌────────────────────────────────────────────────────────────────────┐
│ (stat strip + group boxplots + per-sample table + ROH stripe)      │
│ ... rest of page above ...                                         │
├────────────────────────────────────────────────────────────────────┤
│ Interpretation card (§8)        │ πN/πS in context (§11)           │
│ — three-case text from §1 —     │   cohort value (bold)             │
│                                 │   8-row sorted group table        │
│                                 │   "Romiguier 2014 median 0.17" │
└────────────────────────────────────────────────────────────────────┘
```

### 11.7 References (for the methods card)

- Kimura, M. (1979). Model of effectively neutral mutations in
  which selective constraint is incorporated. *PNAS* 76: 3440–3444.
- Welch, J. J., Eyre-Walker, A., & Waxman, D. (2008). Divergence and
  polymorphism under the nearly neutral theory of molecular evolution.
  *Journal of Molecular Evolution* 67: 418–426.
- Romiguier, J., et al. (2014). Comparative population genomics in
  animals uncovers the determinants of genetic diversity.
  *Nature* 515: 261–263. — empirical πN/πS–πS log–log slope across
  ~76 animal species.
- Elyashiv, E., et al. (2010). Shifts in the intensity of purifying
  selection: an analysis of genome-wide polymorphism data from two
  closely related yeast species. *Genome Research* 20: 1558–1573.
- Martin, G., & Lenormand, T. (2006). A general multivariate
  extension of Fisher's Geometric Model. *Evolution* 60: 893–907.
- Lourenço, J., Galtier, N., & Glémin, S. (2011). Complexity,
  pleiotropy, and the fitness effect of mutations. *Evolution*
  65: 1559–1571.
- Tenaillon, O. (2014). The utility of Fisher's Geometric Model in
  evolutionary genetics. *Annual Review of Ecology, Evolution, and
  Systematics* 45: 179–201.
- Harrang, E., et al. (2013); Lohmueller, K. E. (2014); Do, R., et al.
  (2015); Henn, B. M., et al. (2015) — πN/πS and π0/π4 as standard
  measures of within-species selection efficacy (cited in §1).

---

## 12. Statistical comparisons between groups — Kolmogorov–Smirnov

For every per-sample layer (πN/πS, π0/π4, VESM burden, LOF count,
ROH-overlap fraction), the page also reports **pairwise two-sample
Kolmogorov–Smirnov (K–S) test P values** between groups. The K–S
statistic compares the full empirical CDF of two distributions, so
it detects differences in shape (skew, tail) that a Kruskal–Wallis
or median test would miss — which matters here because the burden
distributions are heavy-tailed (a handful of high-burden samples
drive the differences we want to surface).

### 12.1 Where K–S goes on the page

For each of the four group-level boxplot panels (§3, rows 2–3):
add a small **pairwise K–S P-value matrix** beside the boxplot.
For K=8 groups → 28 pairs, rendered as an 8×8 lower-triangular
heatmap, BH-corrected, coloured by significance (white = ns,
gradient to red for P < 0.05). Click a cell → highlights those
two groups' samples on the strip overlay.

This mirrors the pairwise S2 table on page 4 (`pairwiseTable`) but
uses K–S in place of whatever pairwise test page 4 ships. Page 4
already does Kruskal–Wallis omnibus + pairwise rank-based tests;
the burden page adds K–S because the burden distributions are
shape-different in ways median-based tests don't capture.

### 12.2 Where K–S goes in the payload

Add a `pairwise_ks` block per stratification mode in §4's payload:

```json
"per_group": {
  "K=8": [ ... ],
  "pairwise_ks": {
    "piN_piS":     { "groups": ["G1", ...], "P_matrix": [[null, ...]], "P_BH": [[null, ...]] },
    "pi0_pi4":     { ... },
    "vesm_burden": { ... },
    "lof_count":   { ... },
    "roh_overlap": { ... }
  }
}
```

Each layer's `P_matrix` is the raw two-sided K–S P (`scipy.stats.ks_2samp`
or equivalent), `P_BH` is Benjamini–Hochberg-adjusted across the 28
pairs. The page reads `P_BH`; raw P is kept for tooltips.

### 12.3 Inversion-atlas overlay use case (the strong test)

In the per-candidate Inversion Atlas panel (§10), K–S is the natural
test of *"does this inversion shelter functional burden?"* — compare
the burden distribution of INV/INV-carriers to STD/STD-carriers per
candidate (pairwise, two distributions, fits K–S exactly). The
overlay panel's interpretation cell uses sign(median INV/INV − STD/STD)
+ K–S P value to populate the verdict.

### 12.4 Caveats

- **Sample-size sensitivity.** K–S is sensitive with ≥ ~20 samples
  per group. K=8 groups range from ~10–60 samples in this cohort
  (`D.S1.k8`) — usable but underpowered for the smallest groups.
  The matrix tooltip should always show `n1, n2` alongside P.
- **Ties.** Discrete layers (LOF count) have many ties; use the
  exact-method K–S or the bootstrap variant rather than the asymptotic
  approximation.
- **Multiplicity.** 28 pairs × 5 layers = 140 P values. BH within each
  layer; do **not** flag a single-layer single-pair significance
  without context.

### 12.5 Implementation note

`scipy.stats.ks_2samp` is the standard. The page just reads the
pre-computed matrix; the pipeline is responsible for the computation
and the BH correction. No client-side K–S.

---

## 13. Transcript-view panel — gene-track of what's affected

Per-gene panel showing the affected transcript anatomy: exon /
intron / UTR structure with variant lollipops overlaid, plus
splice-site gain/loss flags from the custom splice module (§6.5).
Answers the per-page question *"for this gene, where exactly do
the deleterious variants land?"*

User direction (2026-05-12): *"we need one panel for transcript
view too. like whats affected"*.

### 13.1 Visual

```
   gene: ENSCGA00000012345 (myh7-like)        K=8 group G3 drives this gene
   ──────────────────────────────────────────────────────────────────────
   5'UTR     exon1        intron1       exon2   intron2   exon3    3'UTR
   ──■■■■──████████──────────────────████──────────────████──────■■■■──
                  ●                       ●▲                ●
                  ↑ missense (VESM 0.82)   ↑ stop_gained     ↑ missense
                                          ↑ splice_donor_loss (Δ=0.83)
```

- Track 1: gene structure — boxes for exons (filled), lines for
  introns, hatched boxes for UTRs. Strand arrow at the right end.
- Track 2 (overlay): **variant lollipops** at variant positions.
  - Circle marker.
  - Marker fill colour: snpEff impact (High slate / Moderate light
    blue / Low mauve / Modifier yellow — same palette as §3.1).
  - Marker outline colour: VESM tier (dark red for VESM_score > 0.8,
    orange for 0.5–0.8, grey otherwise — for missense variants
    only; non-missense markers have no outline).
  - Lollipop height: VESM_score (missense) or fixed (LOF).
- Track 3 (overlay): **splice-event markers** — ▲ for splice gain,
  ▼ for splice loss, ⬥ for splice shift; coloured by `delta_score`
  from the custom splice module.
- Click a lollipop → loads the MSA panel (§14) for that variant.
- Hover → tooltip with `gene · transcript · cDNA pos · protein pos ·
  consequence · snpEff impact · VESM score · csq HGVSp · splice delta`.

### 13.2 Gene picker

The page's transcript view shows **one gene at a time**. Picker
options (default + user-driven):

- **Default selection:** top-burden gene per K=8 group — 8-entry
  dropdown labelled `G1: <gene_X>`, `G2: <gene_Y>`, etc. "Top-burden"
  = highest sum of (VESM_score × allele_count) across samples in
  that group. Pipeline emits one gene_id per group into
  `top_burden_genes_by_group` in the payload.
- **Free-text search box** for gene symbol or ENS ID — autocomplete
  against the gene-model loaded from the upstream payload.
- **"Top-N cohort-wide" pill** — alternative seeding: top 10 genes
  by total VESM burden across all 226 samples.

### 13.3 Data dependency

The atlas does not render the gene structure itself — it relies on
a `transcripts.json` slot emitted by the pipeline:

```json
"transcripts": {
  "ENSCGA00000012345-T1": {
    "gene_id": "ENSCGA00000012345",
    "gene_symbol": "myh7-like",
    "chrom": "chr07",
    "strand": "+",
    "tx_start": 12340000,
    "tx_end":   12360000,
    "exons":  [ {"start": 12340000, "end": 12340500, "type": "5UTR"},
                {"start": 12340500, "end": 12341200, "type": "CDS"},
                ... ],
    "variants": [
      {
        "pos": 12345678, "ref": "A", "alt": "G",
        "consequence": "missense_variant",
        "snpeff_impact": "Moderate",
        "vesm_score": 0.82,
        "csq_hgvsp": "p.Arg123Gly",
        "splice_event": null,
        "n_carriers": 12
      },
      ...
    ]
  },
  ...
}
```

**Size budget.** Loading transcripts for all ~25k catfish genes is
infeasible client-side. Pipeline emits **only the top-burden gene
set** by default (one per K=8 group + cohort-wide top 50 ≈ ~60
transcripts). Free-text search beyond that → lazy fetch on demand
from a per-gene endpoint (or a one-time bulk file if the upstream
team prefers).

### 13.4 Build-session decisions deferred

- **Lollipop collision strategy.** When 5+ variants share one
  exon, lollipops overlap. Stagger by row, or merge into a single
  fat-circle marker labelled `(5)` that explodes on click?
- **Domain track.** Should the transcript track also show Pfam /
  InterPro domain boundaries (when available)? Adds another row to
  the panel.
- **Multiple transcripts per gene.** Default to canonical only?
  Provide a transcript switcher? Drop down the rabbit hole?

These are page-build decisions; flag for the build session, don't
block the spec.

---

## 14. MSA panel — pyMSAviz-rendered teleost-ortholog alignment

Per-variant panel showing the multiple sequence alignment around
a selected missense variant. Standard variant-interpretation view —
conservation of the affected residue across teleost orthologs is
itself diagnostic. Pairs with the transcript view (§13): click a
missense lollipop in §13 → MSA panel loads the alignment window
centred on that variant.

User direction (2026-05-12): *"maybe one MSA panel aswell"* —
followed by a screenshot of [pyMSAviz](https://github.com/moshi4/pyMSAviz)
documentation showing primate-ortholog MSAs (Gorilla, Homo, Nomascus,
Pan, Pongo), residue colouring, consensus track, gap-region
annotations.

### 14.1 Tool: pyMSAviz

Decided on this session, 2026-05-12: **pyMSAviz**
(`moshi4/pyMSAviz`, Python 3.9+, BSD-licensed, MIT-style API
inspired by Jalview and ggmsa). The atlas does not render MSAs
client-side; instead the pipeline runs pyMSAviz and exports a
static SVG per variant. The atlas-side panel is a region-aware
image loader.

Reasons over the alternatives:
- **Pre-rendered SVG** is dramatically simpler than porting an MSA
  renderer to JS, and lets the build session use any features of
  pyMSAviz (markers, highlights, consensus bars, gap annotations)
  with no atlas-side code.
- **SVG (not PNG)** keeps the labels searchable / accessible /
  zoomable, and the file size for ~10 × 60 residue windows is tiny
  (a few KB per variant).
- **pyMSAviz's marker / annotation API** lets the pipeline mark the
  variant position explicitly (the `+` markers in pyMSAviz Fig 2
  customised example).

### 14.2 Visual

Rendered by pyMSAviz, embedded as `<img src="…svg">`:

```
   variant: chr07:12345678 A→G  (p.Arg123Gly, VESM 0.82)
   window: 30 aa upstream + 30 aa downstream
   ──────────────────────────────────────────────────────────────
                                          ↓ this position
   C.gariepinus    M F G L F G L W R T F D S V V F Y L T L I V …
   I.punctatus     M F G L F G L W R T F D S V V F Y L T L I V …
   D.rerio         M F G L F G L W R T F D S V V F Y L T L I V …
   O.latipes       M F G L F G L W R T F D S V V F Y L T L I V …
   O.niloticus     M F G L F G L W R T F D S V V F Y L T L I V …
   S.salar         M F G L F G L W R T F D S V V F Y L T L I V …
   G.aculeatus     M F G L F G L W R T F D S V V F Y L T L I V …
   ──────────────────────────────────────────────────────────────
   Consensus       ████████████████████████████████████ (bar chart)
```

- Catfish (*C. gariepinus*) always pinned at the top.
- 6–10 teleost orthologs below — proposed default set: *Ictalurus
  punctatus* (channel catfish, closest), *Danio rerio* (zebrafish),
  *Oryzias latipes* (medaka), *Oreochromis niloticus* (tilapia),
  *Salmo salar* (Atlantic salmon), *Gasterosteus aculeatus*
  (stickleback). Confirm the exact set at build time depending on
  ortholog-table availability from genome-atlas.
- Residue colouring: pyMSAviz default Clustal-style palette
  (matches the reference screenshot).
- Consensus track below the alignment (pyMSAviz built-in).
- Variant position marked with a downward arrow (pyMSAviz markers
  API).
- Window size: ±30 aa around the variant (configurable per variant
  in the payload).

### 14.3 Pipeline product

For each variant in the top-burden set (§13), the pipeline runs:

1. Look up the protein sequence of the affected transcript in
   catfish + each ortholog (via genome-atlas ortholog table).
2. Run a fast MSA (MAFFT or MUSCLE) over the 6–10 sequences,
   windowed to ±30 aa around the variant position.
3. Render with pyMSAviz, save as
   `data/msa/<variant_id>.svg`.

The functional_burden.json payload references these files:

```json
"msa_links": {
  "chr07:12345678:A:G": "data/msa/chr07_12345678_A_G.svg",
  ...
}
```

The atlas-side panel reads `msa_links[variant_id]` and renders
`<img>` or `<object>` pointing at the SVG. Missing key → "MSA
not available for this variant" fallback card.

### 14.4 Size budget

Pre-rendering ~60 variants (one per top-burden gene per group +
cohort-wide top 50) × ~5–10 KB per SVG = **~0.3–0.6 MB total** in
`data/msa/`. Acceptable on-disk; lazy-loaded
client-side so the page itself stays light.

If the user later wants on-demand MSA for arbitrary variants
beyond the pre-rendered set, the build session needs a server
endpoint that runs pyMSAviz on request. Out of scope for v1.

### 14.5 Build-session decisions deferred

- **Ortholog source.** genome-atlas's OrthoFinder vs Ensembl
  Compara teleost orthologs vs a custom BLAST-based map. Pipeline
  side, not atlas side.
- **Alignment tool.** MAFFT (faster, decent quality) vs MUSCLE
  (older but very stable). Pipeline side.
- **Window size.** ±30 aa default; build session may adjust.

---

## 15. Open questions for the next session

1. §6.1–§6.6 — six unfinished design decisions above.
2. Should the per-sample drill-down (table click) open a panel
   showing **which genes** drove this sample's VESM/LOF burden, or
   just the numeric breakdown? If the former, need a per-sample
   gene-level export from the upstream pipeline.
3. Should πN/πS be reported per-chromosome as well (extra heatmap
   row in the page), or only per-sample / per-group?
4. Should the page mirror the K-sweep panel from page 4 — i.e. show
   πN/πS at K=2, K=3, …, K=8 to verify the result isn't an artefact
   of the chosen K? Defer; probably overkill for v1.
5. Should the cross-atlas overlay (§10) be tracked as a sub-issue in
   this repo, or owned by the Inversion Atlas repo?

---

## 16. Summary

| What | Where |
|---|---|
| Main page — five-layer functional burden | new diversity-atlas page (location TBD §6.1) |
| Per-candidate burden overlay | Inversion Atlas, existing per-candidate panel |
| Pipeline product | one JSON (functional_burden.json), six pipeline steps |
| Cross-atlas data deps | genome-atlas: gene model, CDS, annotation, VESM, degeneracy |
| Open decisions | 6 (location, πN/πS estimator, 0/4-fold source, VESM source, LOF caller, stratification axis) |
| Sibling spec to align with | `SPEC_2026-05-12_roh_gene_burden.md` (shares ROH × functional intersection + stratification choice) |

- Status: **spec only**. No pipeline run. No atlas page.
- Decisions deferred per user direction.
- Pairs with `SPEC_2026-05-12_roh_gene_burden.md` — both should be
  resolved together to share the same stratification toggle and the
  same upstream ROH × functional-site intersection.

---

## Implementation status (updated 2026-05-20)

- Registry wiring: layer `functional_burden_payload` declared in
  [`../atlases/diversity/registries/data/layers.registry.json`](../atlases/diversity/registries/data/layers.registry.json)
  §8. Path `data/functional_burden.json` ships an empty-stub today.
- Schema: [`../atlases/diversity/registries/schemas/functional_burden_v1.schema.json`](../atlases/diversity/registries/schemas/functional_burden_v1.schema.json)
  — 13 top-level blocks (cohort_summary, variant_inventory, gerp_inventory,
  per_sample, per_group, pairwise_ks, alternative_stratifications,
  top_burden_genes_by_group, transcripts, splice_events, msa_links).
  `schema_status: draft` — flip to `validated` once upstream emits a non-stub
  payload.
- Browser-side cross-check: Mode-B probe wired on page `burden`
  ([`../atlases/diversity/pages/functional/burden.js`](../atlases/diversity/pages/functional/burden.js)).
  Today's badge reports `○ data pending` until the pipeline ships.
