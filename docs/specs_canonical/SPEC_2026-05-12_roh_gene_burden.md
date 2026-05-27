# SPEC — ROH × gene-model views (page 5 extension)

**Date:** 2026-05-12
**Target atlas:** diversity-atlas (in-atlas — stays on page 5)
**Target page:** `atlases/diversity/pages/per_sample/page5.{html,js}` — *ROH composition*
**Status:** spec only. No pipeline run. No new page code.

> ## ⚠ Decision status (2026-05-12 round-1 session)
>
> 1. **Constraint proxy ("pLI > 0.9" analog).** Still **data-blocked**
>    — catfish has no pLI and no proxy table exists yet in genome-atlas.
>    Options on the table: single-copy BUSCO orthologs / OrthoFinder
>    strict / all protein-coding (no filter) / dN/dS < 0.1 / hybrid
>    (all four as switchable layers) / ohnolog status / low-dN/dS
>    teleost-conserved set. Decision deferred to the upstream
>    genome-atlas session. The atlas reads `constraint_score` from
>    the payload regardless of which proxy lands. See §6.2.
> 2. ✅ **Stratification axis** — resolved to **all modes selectable**:
>    pill toggle with K=8 (default) / per-family / per-sample
>    drill-down / F_ROH-quartile. Same pill set used by the new
>    Functional-Burden page (`SPEC_2026-05-12_functional_burden.md`
>    §6.6). Implement the pill renderer in `shared/` so both pages
>    share one component. See §6.3.
**Reference figures (provided by user, 2026-05-12):**

- **Plot A** — "Cumulative gene count (pLI > 0.9) vs ROH blocks", stacked-area
  by population (Afghani, Jordanian, Sudanese, Syrian, Qatari 1/2, Yoruban).
  Original is panel *f* of a consanguinity/ROH paper. Question answered:
  *as you add ROH blocks ranked by some criterion, how does the cumulative
  count of high-constraint genes captured scale, and how does that scaling
  differ across population/group strata?*
- **Plot B** — Gene-count heatmap-table indexed by gene **biotype** (rows)
  × selected ROH peak regions (columns), e.g. `ROH Chr 6 52.9 Mb` and
  `ROH Chr 12 37.6 Mb`. Cells are gene counts, coloured on a single-hue
  ramp (1 → 258). Companion view to Plot A — drills into *what's inside*
  the top ROH peaks rather than ranking blocks cohort-wide.

Per user decision (2026-05-12): record **all options** for the two open
design points below (constraint proxy, stratification) instead of
deciding now. Decisions are deferred to the build session for this page.

---

## 1. Why both plots share one data dependency

Both plots require the same upstream intersection:

```
ROH BEDs (per-sample, all 226) ∩ gene-model BED (canonical, genome-atlas)
  → per-block: { gene_ids[], biotype, constraint_score }
```

Once that intersection table exists, Plot A is a sort+cumsum+stack over
the block list, and Plot B is a groupby-biotype filter over the subset
of blocks falling inside the named peak regions.

Building either plot in isolation duplicates the upstream work, so the
spec treats them as a single data product with two render modes.

---

## 2. Cross-atlas dependency

This is **not** a cross-atlas request the way the pairwise-θπ spec was —
the plots live in the diversity-atlas (ROH is a per-sample diversity
concern). But the *gene model* lives in the genome-atlas, per the
boundary table:

| Concern | Atlas |
|---|---|
| ROH BEDs, F_ROH, ROH block list | Diversity (have) |
| K=8 ancestry labels | Diversity D.S1.k8 mirror (have) |
| **Gene model BED (loci + biotype)** | **Genome Atlas (canonical) — NOT YET IN DIVERSITY** |
| **BUSCO ortholog BED** | **Genome Atlas — NOT YET IN DIVERSITY** |
| **Constraint score TSV** (whatever proxy) | **Genome Atlas — DOES NOT YET EXIST** |

Mechanism: page 5 reads from a new diversity-atlas data slot
`ROH_GENE_OVERLAP` (loaded by `data_loader.js`) that ingests a JSON
emitted by a new pipeline step. That JSON's *inputs* are genome-atlas
files. The pipeline step is the cross-atlas boundary, not the atlas
page.

---

## 3. Plot A — cumulative gene burden across ROH blocks

### Axes & encoding

- **x-axis:** ROH blocks, ranked. Ranking criterion: see open question §6.1.
  Each tick = one ROH block. With 226 samples × average ~25 long-tract
  ROH per sample, that's O(5,000) blocks if "block" = per-sample tract;
  fewer if "block" = consensus peak across cohort.
- **y-axis:** cumulative count of *constraint-positive* genes captured
  by the union of the first *N* ranked blocks. "Constraint-positive"
  definition: see §6.2.
- **Stacking:** colour-stacked area by group. Each band's value at tick *N*
  is the per-group cumulative count. The total area at tick *N* = sum
  across groups = cohort-wide cumulative count.
- **Legend:** group labels (K1…K8 for K=8 stratification; or family IDs
  if family-stratification is enabled — see §6.3).

### Display modes (toggle, page-side)

1. **By K=8 group** (default per "by group for sure" 2026-05-12).
2. **By family / broodline** — if cohort metadata has those labels.
   May or may not be enabled (see §6.3).
3. **By sample** — drill-down for one sample, overlaid on cohort
   trajectory. Useful for "mosaic-rich" page-9 DDI samples.
4. **Single-stratum view** — pill-pick one group/family; renders just
   its band against the cohort total as a faint reference. Cleaner
   read for individual strata.

### Data slice (Plot A, per sample or per consensus block)

```jsonc
// flat array, sorted by rank criterion
"plot_a_blocks": [
  {
    "block_id": "blk_00001",
    "chrom": "NC_069531.1",   // or "1"
    "start": 12450000, "end": 14200000,
    "len_mb": 1.75,
    "rank_value": null,        // depends on §6.1 choice
    "sample_id": "CGA009",     // null if consensus
    "k_group": "K3",
    "family_id": null,         // populated if broodline labels exist
    "gene_ids": ["LOC108123456", "LOC108123457", ...],
    "n_genes_total": 12,
    "n_genes_constraint_pos": 4,  // depends on §6.2 choice
    "biotype_counts": { "protein_coding": 9, "pseudogene": 2, "lncRNA": 1 }
  }
  // ... O(5,000) entries
]
```

---

## 4. Plot B — biotype counts in selected ROH peaks

### Encoding

- **Rows:** gene biotype. **9-row canonical layout** (confirmed
  against user-provided reference figure, 2026-05-12):
  1. `Protein_coding`
  2. `Pseudogene`
  3. `lncRNA`
  4. `miRNA`
  5. `Transcribed_pseudogene`
  6. `snoRNA`
  7. `tRNA`
  8. `snRNA`
  9. `Antisense_RNA`

  Reference figure shows for two example peaks: `ROH Chr 6 52.9 Mb` →
  Protein_coding 258, Pseudogene 254, lncRNA 228, miRNA 17,
  Transcribed_pseudogene 12, snoRNA 20, tRNA 3, snRNA 1,
  Antisense_RNA 1; `ROH Chr 12 37.6 Mb` → 243, 195, 153, 12, 8, 8,
  (blank), 1, (blank). Catfish gene-model release may have a
  different subset (especially Transcribed_pseudogene and
  Antisense_RNA — confirm via genome-atlas GTF before build); rows
  with no genes anywhere in the selected peak set should be omitted.
  Additional rows (`rRNA`, `misc_RNA`) included if present in the
  annotation.
- **Columns:** named ROH peak regions, picked from a curated set —
  e.g. the top-N consensus ROH peaks across the cohort, or hand-picked
  candidate regions discussed in narrative pages. Each column carries
  a label like `ROH Chr 6 52.9 Mb` (chrom + start-rounded Mb). The
  reference figure uses **2 columns**; this should be the default,
  with a multi-select to add more.
- **Cells:** gene count for (biotype, peak). Coloured on a single-hue
  blue ramp from `min` (palest, count = 1) to `max` (deepest,
  reference figure max = 258). Empty cells: blank (no gene of that
  biotype in that peak — matches the reference figure's treatment).
- **Legend:** small horizontal colourbar above the table, label
  "Gene count", range "1 … max" (matches reference figure).

### Companion controls

- **Peak selector** — multi-select of named peaks (default: top-2 by
  total gene count, mirroring the reference figure's 2-column layout).
- **Biotype filter** — toggle to hide rows where all peaks are 0/1
  (declutters when most biotypes are empty).
- **Per-group toggle** *(optional, defers to §6.3)*: switches the cell
  value from "all-cohort gene count in peak" to "gene count in the
  subset of samples in group K=*k* who carry an ROH at this peak".
  Adds a per-peak per-group dimension to the data.

### Data slice (Plot B, per named peak)

```jsonc
"plot_b_peaks": [
  {
    "peak_id": "peak_chr6_52_9mb",
    "label": "ROH Chr 6 52.9 Mb",
    "chrom": "NC_069531.1",
    "start": 52400000, "end": 53400000,
    "cohort_sample_count": 87,   // n samples with ROH at this peak
    "biotype_counts": {
      "protein_coding": 258,
      "pseudogene": 254,
      "lncRNA": 228,
      "miRNA": 17,
      "transcribed_pseudogene": 12,
      "snoRNA": 20,
      "tRNA": 3,
      "snRNA": 1,
      "antisense_RNA": 1
    },
    "per_group_biotype_counts": null   // populated only if §6.3 enabled
  },
  { "peak_id": "peak_chr12_37_6mb", "label": "ROH Chr 12 37.6 Mb", ... }
]
```

---

## 5. Combined payload

Single file, planned at
`data/roh_gene_overlap.json`:

```jsonc
{
  "params": {
    "gene_model_release": "<genome-atlas canonical gene-model version>",
    "biotype_source": "<NCBI RefSeq vs Ensembl vs custom>",
    "constraint_proxy": "<see §6.2>",
    "rank_criterion": "<see §6.1>",
    "roh_set": "long_tracts_v3"  // matches S8c_long
  },
  "cohort_summary": {
    "n_samples": 226,
    "n_blocks_total": null,
    "n_peaks_named": null,
    "n_genes_total": null,
    "n_genes_constraint_pos": null
  },
  "plot_a_blocks": [ /* §3 */ ],
  "plot_b_peaks":  [ /* §4 */ ]
}
```

Size estimate: ~5,000 blocks × ~20 gene-ids each × ~12 chars
≈ 1.5 MB for the gene-id arrays, plus scalar fields. Comfortably JSON.
If gene-id arrays balloon, switch to a separate `block_gene_ids.json`
lazy-loaded on click-to-detail.

---

## 6. Open design questions (all to be decided at build time)

User instruction 2026-05-12: write all options to the spec, decide later.
Below is the option set for each.

### 6.1 Rank criterion for Plot A's x-axis

What ordering of ROH blocks produces the most informative cumulative
curve?

- **(A) ROH block size descending** — largest tracts first. Matches the
  intuition that the longest IBD-by-descent segments carry the most
  gene burden per block. Simplest. Risks: visually dominated by a few
  mega-tracts.
- **(B) Gene density descending** — most gene-rich blocks first. Drops
  gene-poor heterochromatic mega-tracts to the right tail. The original
  figure's curve shape (early-flat, late-steep) is closer to this
  ordering than (A).
- **(C) Per-block constraint-gene count descending** — packs the
  constraint-rich blocks at the left, makes the cumulative curve
  saturate fast. Best at answering "how few blocks explain most of
  the constraint burden?" Risks: circularity if the y-axis is also the
  same quantity (the curve becomes a pure rank-statistic).
- **(D) Cohort prevalence descending** — blocks ordered by how many
  samples carry an ROH overlapping that consensus locus. Highlights
  high-frequency / recurrent ROH peaks. Different question than the
  original figure but arguably more useful for the catfish cohort.
- **(E) Genomic order** — chrom1→chromN, position-sorted. Not a
  ranking; lets the reader see chromosome-level structure in the
  cumulative curve (step changes at recombination cold-spots,
  centromeres, large inversions). Visually closest to a per-chromosome
  ROH coverage plot.

### 6.2 Constraint proxy ("pLI > 0.9" analog) — **UNFINISHED**

Catfish has no native pLI. **No proxy chosen as of 2026-05-12.** Build
session must pick one of the following (or a hybrid).

- **(A) Single-copy BUSCO orthologs (actinopterygii_odb10)** — ~3,640
  genes by construction conserved across teleosts. Best off-the-shelf
  proxy; needs only the BUSCO output table (likely already in
  genome-atlas) and a join to gene IDs. Lowest upstream lift.
- **(B) OrthoFinder strict single-copy across ≥5 catfish-clade species** —
  more conservative than BUSCO. Requires running OrthoFinder against
  a panel of catfish-clade genomes if not already done. Tighter
  constraint signal; larger upstream lift.
- **(C) All protein-coding genes (no constraint filter)** — skip the
  "high-constraint" axis. Cumulative protein-coding gene burden inside
  ROH, stratified by group. Simplest; loses the *pLI > 0.9*
  selectivity that gave the original figure its punch.
- **(D) dN/dS < 0.1 from teleost multiple-sequence alignment** — most
  biologically defensible analog of pLI but requires a
  comparative-genomics pipeline (codeml/PAML across ≥3 catfish-clade
  species, or pre-computed teleost dN/dS tables if available).
- **(E) Ohnolog status (post-WGD retained pairs)** — teleost-specific
  dosage-sensitivity axis. Ohnologs from the catfish WGD are by nature
  dosage-balanced. Needs an ohnolog table from genome-atlas.
- **(F) Low-dN/dS teleost-conserved set** — variant of (D) using
  pre-computed cross-teleost dN/dS tables instead of running PAML in
  the project. Cheaper than (D) if a usable table exists upstream.
- **(G) Hybrid — emit all available proxies as switchable layers** —
  single pill-toggle on the page lets the reader compare proxies side
  by side. Needs every chosen proxy emitted by the pipeline. Most
  flexible, most data-heavy. Recommended hybrid set if going wide:
  (A) + (C) + (E).

### 6.3 Stratification — group vs family vs sample — ✅ RESOLVED (2026-05-12)

**Decision:** option (E) — **all modes selectable**. Pill toggle
with four states:
  1. **K=8** (default) — 8 ancestry-cluster cumulative-burden curves
  2. **per-family** — one curve per `family_id`; falls back to "no
     family labels available" if the metadata column is empty
  3. **per-sample drill-down** — overlay one sample's trajectory
     on the K=8 background
  4. **F_ROH quartile** — Q1–Q4 by genome-wide F_ROH; 4 curves

**Same pill set** is used by the new Functional-Burden page
(`SPEC_2026-05-12_functional_burden.md` §6.6, also resolved to
option E). Implement the pill renderer in `shared/` so both pages
share one component — avoids visual drift between burden pages.

---

## 7. Pipeline (where the data comes from)

Belongs in **`catfish-diversity-analysis`** (or **`genome-atlas-pipeline`**
depending on how the org draws the line — gene-model annotation is
genome-atlas's job, but the intersection product is consumed by the
diversity-atlas).

Proposed step: `phase_4_followups/01_roh_gene_overlap.sh`

Substrate inputs:

1. ROH BEDs (per-sample) from
   `catfish-diversity-analysis/phase_2_discovery/03_run_roh.sh` outputs.
2. Consensus ROH peaks — needs a peak-calling step over the per-sample
   BEDs (merge + min-prevalence filter). Output: `roh_peaks.bed`.
3. Gene-model BED with biotype column from the genome-atlas canonical
   release.
4. Constraint-proxy TSV (whichever proxy chosen per §6.2).
5. K=8 labels from D.S1.k8.
6. Family/broodline TSV (if §6.3 mode B or D chosen).

Compute (pseudocode):

```
peaks         = bedtools merge -d 100k per_sample_roh.bed | min_prevalence ≥ 5
block_list    = per_sample_roh.bed                                       # for Plot A
gene_hits     = bedtools intersect -wa -wb block_list gene_model.bed
constraint    = join gene_hits with constraint_proxy.tsv
emit roh_gene_overlap.json with plot_a_blocks, plot_b_peaks
```

Pipeline detail beyond this spec is up to the pipeline repo.

---

## 8. Diversity-atlas atlas-side work when data lands

Mirrors the page9 (texture) round-2 pattern:

1. Extend `atlases/diversity/shared/data_loader.js` with a
   `ROH_GENE_OVERLAP` slot, graceful no-data fallback (renders
   "data pending" pill, returns empty arrays — same shape as
   `WIN_METRICS` in this round).
2. Extend `atlases/diversity/pages/per_sample/page5.html` with two
   new panels:
   - `panel-roh-gene-cumulative` (Plot A)
   - `panel-roh-peak-biotype` (Plot B)
3. Extend `atlases/diversity/pages/per_sample/page5.js` with the two
   renderers reusing `shared/plots.js` (stacked area for A; existing
   heatmap helper or new mini-grid for B).
4. Update `manifest.json`, `pages.registry.json`, `files.registry.json`
   to reflect the new data dependency.
5. Test: load empty stub → "data pending" path renders; load populated
   stub → both panels render ≥1 element each.

Estimated effort: 3–4 hours once data exists.

---

## 9. Provenance

- Reference figures: user-provided 2026-05-12, panel *f* + a
  gene-biotype-by-ROH heatmap table from a consanguinity / ROH study.
- Stratification choice "by group for sure": user, 2026-05-12.
- Decision to write all options to the spec (no commitment now):
  user, 2026-05-12 (via AskUserQuestion both questions).
- Routing decision (stays in diversity-atlas, gene-model lives in
  genome-atlas): inferred from
  `0_READ_ME_FIRST.md` cross-atlas boundary table.
- Authors of upstream framework: Quentin Andres; atlas-side design:
  Claude.
- Status: **spec only**. No pipeline. No page code.

---

## Implementation status (updated 2026-05-20)

- Registry wiring: layer `roh_gene_overlap_payload` declared in
  [`../atlases/diversity/registries/data/layers.registry.json`](../atlases/diversity/registries/data/layers.registry.json)
  §8. Path `data/roh_gene_overlap.json` ships an empty-stub today.
- Schema: [`../atlases/diversity/registries/schemas/roh_gene_overlap_v1.schema.json`](../atlases/diversity/registries/schemas/roh_gene_overlap_v1.schema.json)
  — `blocks[]` (Plot A) + `peaks[]` (Plot B 9-row biotype set) +
  `per_group_cumulative['K=8']`. `schema_status: draft` until the
  constraint-proxy decision (§6.2) is resolved upstream and the pipeline
  ships a non-stub payload.
- Browser-side cross-check: no dedicated Mode-B probe today (the page
  `roh` is not in the 18 wired set — its ROH-substrate side is blocked at
  the empty `04_roh/` root, see `MISSING_DATA.md` §2). When the substrate
  lands, mirror the texture-page pattern in
  [`../atlases/diversity/pages/per_sample/texture.js`](../atlases/diversity/pages/per_sample/texture.js).
