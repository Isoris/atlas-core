# SPEC — diversity-atlas `about` page (methods + glossary + headline numbers + data lineage)

**Status**: scaffold. Meta-page; renders mostly static content with a
few dynamic headline-number tiles.

**Scaffolded in:**

| file | role |
|---|---|
| [`pages/meta/about.html`](../atlases/diversity/pages/meta/about.html) | static markdown-style fragment with methods sections + glossary + headline tiles + lineage diagram |
| [`pages/meta/about.js`](../atlases/diversity/pages/meta/about.js) | mount lifecycle; reads cohort numbers from `state.shared.cohortSummary` (or fetches from `data/diversity/cohort_summary.json`) |

---

## 1. Goal

A single page surfacing **what this atlas computes and how**. Target
audience: a reviewer or collaborator who needs to understand what the
cohort numbers mean before trusting them. Includes:

1. **Methods sections** (SD1–SD8) — one section per pipeline stage,
   each with a paragraph of plain-English explanation + a reference
   to the producer script or paper.
2. **Glossary** — terms with their canonical definitions (θπ, F_ROH,
   πN/πS, NAToRA, K=8, MOSAIC_SHORT, etc.)
3. **Headline numbers tile grid** — cohort_n, n_chroms,
   n_unrelated_after_NAToRA, median F_ROH, median θπ. Live values
   pulled from the cohort summary envelope.
4. **Data lineage diagram** — visual flow from raw FASTQ → BAM →
   ANGSD pestPG → diversity envelopes → atlas page consumers.

## 2. Data input

**v1 today** (mostly static):
- HTML fragment contains the methods + glossary text inline
- Dynamic headline numbers from `data/diversity/cohort_summary.json`
- Lineage diagram is a static SVG/CSS asset

**v2 target** (envelope-aware): the headline numbers should come from
a `diversity_cohort_summary_v1` envelope, with the producer's pipeline
versions + run dates so the page can render "as of <date>" annotations.

## 3. The four sections

### 3.1 Methods (SD1–SD8)

Per-stage explanation. Each "SD" stage has:

- A title (e.g. "SD3: per-chromosome θπ via ANGSD")
- A 1–2 paragraph plain-English summary
- A code/script reference (e.g. "producer: `Module_03_theta_pi/run.sh`")
- A version line ("ANGSD 0.940, --doThetas, win=10kb step=10kb")

Stages:

| SD# | what it covers |
|---|---|
| SD1 | Sample QC + ascertainment |
| SD2 | Variant calling + filtering |
| SD3 | Per-chromosome / per-window θπ via ANGSD |
| SD4 | Heterozygosity bundle |
| SD5 | ROH calling (ngsF-HMM, length-class binning) |
| SD6 | Ancestry decomposition (NGSadmix K-sweep) |
| SD7 | NAToRA pruning |
| SD8 | Cross-module rollups (cohort summary, divergence) |

### 3.2 Glossary

Alphabetical list of terms. Each entry: term + 1-sentence definition
+ pointer to the producing pipeline. Example:

> **F_ROH** — Fraction of an individual's genome covered by Runs of
> Homozygosity (ROH segments ≥ 1 Mb). Computed in SD5 by ngsF-HMM with
> default transition prior and 0.95 emission threshold.

Approximately 30 entries cover the cohort's full vocabulary.

### 3.3 Headline numbers tile grid

A 2×4 grid of large-font tiles:

| tile | value | source |
|---|---|---|
| Cohort n | 226 | summary |
| Chromosomes | 28 (Chr01–Chr28) | reference |
| NAToRA-pruned subset | 81 (or whatever) | producer (SD7) |
| Median θπ (genome-wide) | 0.0034 (or whatever) | producer (SD8) |
| Median F_ROH | 0.07 | producer (SD5) |
| Median H | 0.0008 | producer (SD4) |
| Hotspots above 99th pctl | 19 | producer (SD8) |
| Genes scored | 12_400 | producer (burden builder) |

Each tile links to the page where the number is computed (e.g.
"NAToRA-pruned subset" link → `pruning_qc` page).

### 3.4 Data lineage diagram

A simple boxed-arrow diagram:

```
FASTQ → BWA → BAM/CRAM
           ↓
       ANGSD → per-window θπ ────→ diversity envelopes
           ↓                              ↓
       ngsF-HMM → F values           atlas pages
           ↓
       NAToRA → unrelated set
           ↓
       NGSadmix → Q vectors
```

Rendered as SVG; nodes link to the methods stage that produces them.

## 4. State + interaction

- `state.shared.cohortSummary` — pulled on mount; refreshed if the
  cohort version changes (rare)
- Hover any glossary term elsewhere in the atlas (when v2 tooltip-link
  patterns ship) routes to this page's glossary section

## 5. Failure modes

| # | condition | behaviour |
|---|---|---|
| 5.1 | `cohort_summary.json` missing | headline tiles render placeholder "—"; rest of the page works |
| 5.2 | A methods stage's version chip is stale | renderer uses whatever's in the envelope; manual refresh required |
| 5.3 | Glossary references a page that doesn't exist yet | the inline link is broken; not fatal |

## 6. What's currently NOT modelled

- **Versioned methods** — when the producer pipeline bumps a version (e.g. ANGSD 0.940 → 1.0), the SD page should track that. v2 envelope.
- **Run dates** — when was each producer last run? v2 should expose timestamps.
- **Per-chromosome SD diagram** — the lineage is rendered cohort-wide; a per-chromosome variant could surface chrom-specific producer outputs. Out of scope.

## 7. Cross-page links

- Every headline tile is a deep-link into the relevant atlas page
- Glossary entries link to canonical sources

## 8. UI surface

```
┌────────────────────────────────────────────────────────────┐
│ Header: "About — Diversity Atlas"                          │
├────────────────────────────────────────────────────────────┤
│ Headline tile grid (2 × 4)                                 │
│   [Cohort n: 226]  [Chroms: 28]  [Pruned: 81]  [Hotspots: 19]│
│   [Median θπ: ...]  [Median F_ROH: ...]  [Median H: ...]  [Genes: 12400]│
├────────────────────────────────────────────────────────────┤
│ Methods sections (SD1–SD8)                                 │
│   Each with title, paragraph, code reference, version chip  │
├────────────────────────────────────────────────────────────┤
│ Glossary (alphabetical, ~30 terms)                         │
├────────────────────────────────────────────────────────────┤
│ Data lineage diagram (SVG)                                 │
└────────────────────────────────────────────────────────────┘
```

## 9. Promotion criteria

| criterion | v1 | v2 |
|-----------|----|----|
| Methods sections render (static text) | ✓ | ✓ |
| Glossary renders | ✓ | ✓ |
| Headline tile grid (dynamic numbers) | ✓ | ✓ |
| Lineage diagram | ✓ | ✓ |
| Versioned producer metadata | ✗ | required |
| Glossary terms cross-linked from other pages | ✗ | nice-to-have |
| Per-chrom SD diagram | ✗ | future |

This is a documentation page — not a statistical one. Promotion is
mostly content-completeness, not algorithmic correctness.
