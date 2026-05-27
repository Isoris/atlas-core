# HANDOFF 5 — Inversion-core haplotype tree

**Goal**: build per-candidate haplotype trees that test whether
PCA/dosage bands form coherent phylogenetic clades, and distinguish
ladder-like divergence from parallel-clade divergence.

**Status**: not started. Builds on the multi-allelic mgl pipeline
(HANDOFFs 1-4) for sample/band assignment, and on existing infrastructure
(`region_popstats.c`, `region_stats_dispatcher.R`) for group-level stats.

**Audience**: a fresh chat where Claude implements the tree producer.

---

## Two complementary tree paths

The spec defines **two pipelines**. They answer related but distinct
questions and should both be available, though the primary deliverable
for the paper is Path B (the SNP alignment tree).

| Path | Input | Tree method | Best at |
|---|---|---|---|
| **A: dXY/dA NJ** | Band-level summary stats | NJ on distance matrix | Group-level clade structure; ladder vs parallel pattern |
| **B: SNP alignment** | Per-sample SNP genotypes (FASTA, IUPAC for hets) | IQ-TREE ML with GTR+ASC | Per-sample placement, branch lengths, bootstrap support |

Path A is fast, group-level. Path B is slower, sample-level, ML-based.
**The paper figure is Path B**: per-sample tree with leaves colored by
band, showing whether each band forms a coherent clade.

Path A complements as a quick pre-pass: if the band-level dXY tree shows
no inter-band divergence, the per-sample tree won't either, so you can
skip to investigating mosaic/recombination first.

---

## Background you need

### The scientific question (concise)

For a candidate inversion with multiple PCA bands, distinguish:

- **Model 1 (ladder)**: standard → recent → middle → old. Bands are
  stages of one lineage. Tree is laddered; derived alleles nested.
- **Model 2 (parallel clades)**: one inversion ancestor → A, B, C
  diverging in parallel. Tree is bushy; derived alleles private per clade.
- **Model 3 (multiple independent inversions)**: clades not sister to
  each other. Hard to prove without breakpoint evidence.
- **Model 4 (recombination mosaic)**: bands aren't true clades, just
  spatial mixtures. Tree from full interval is inconsistent; tree from
  clean core is.

Trees distinguish these by **topology** (laddered vs bushy vs scattered)
and **branch lengths** (relative divergence). Core-interval requirement
filters out Model 4 contamination.

### Honest framing for the paper

The tree is a **regional haplotype-clade map** over the inversion core,
not "the inversion phylogeny." Claims:

- "PCA bands form coherent haplotype clades" (concordance ARI/purity)
- "Bands diverged in parallel" / "consistent with stepwise divergence"
  (which model)
- "Tree branches colored by relative dXY divergence" (NOT "age" without
  calibration)

Avoid: "Band X is ancestral", "Inversion is N years old", "Tree resolves
species history."

### What "core" means

The candidate interval is usually 2-5 Mb. Inside it:
- **Breakpoint flanks** (~200 kb each end): high recombination; haplotype
  mixing destroys clade signal.
- **Common core** (middle 50-80%): where most samples carry pure
  arrangements without crossover.
- **Per-sample masks**: optional later — some samples may have local
  crossovers even in the core.

Default core selection: trim 200 kb flanks. More sophisticated masking
is a Phase 2 polish.

### Heterozygote handling — the key design decision

For diploid samples, encoding a heterozygote in a one-sequence-per-sample
FASTA forces a choice. The spec supports three modes, selected by
`--het_mode`:

| Mode | 0/1 → | Tree interpretation | Use when |
|---|---|---|---|
| `iupac` (default) | R / Y / W / S / K / M | Diploid genotype-similarity tree | All samples included; standard for first paper figure |
| `n` | N | HOM-only tree (HETs are uninformative N-strings) | Sanity check; should still place HOM bands well |
| `random` | one of REF/ALT randomly | Pseudo-haplotype tree | Comparison with iupac to test how much HET info matters |
| `phased` | hap1 / hap2 as separate leaves | True haplotype tree | If phased data is available — future extension |
| `hom_only` | (HETs excluded) | Cleanest haplotype tree | When you have enough HOM samples per band |

**Default for first paper figure: `iupac`**. Quentin's intuition is
correct that HETs retain resolution from their HOM sites — IUPAC
encoding preserves this. The spec also produces a `hom_only` tree as a
validation: if both trees give concordant clade structure, the
inclusion of HETs isn't biasing the topology.

A subtle issue: IQ-TREE's standard models treat ambiguity codes as
"compatible with any of these bases," not as a true diploid state. This
slightly weakens the signal for HETs but does not break the tree. For
the paper, present both `iupac` (full sample set) and `hom_only`
(strictest comparison) and note in methods that they agree.

---

## Pipeline architecture

```
              ┌────────────────────────────────────┐
              │  Candidate interval + band labels  │
              │  (sample → band from PCA)          │
              └─────────────────┬──────────────────┘
                                │
                                ▼
              ┌────────────────────────────────────┐
              │  Core selection                    │
              │  - Trim breakpoint flanks           │
              │  - Optionally drop crossover samples│
              │  - Output: core interval, samples  │
              └─────────────────┬──────────────────┘
                                │
                ┌───────────────┼───────────────┐
                ▼                               ▼
       ┌───────────────────────┐      ┌──────────────────────┐
       │   PATH A (group)       │      │   PATH B (sample)    │
       │                        │      │                      │
       │ Band-level dXY/dA      │      │ Per-sample SNP FASTA │
       │  (popstats engine)     │      │  (Beagle → IUPAC)    │
       │         │              │      │         │            │
       │  NJ tree (~5 leaves)   │      │  snp-sites           │
       │         │              │      │         │            │
       │  ape::nj()             │      │  IQ-TREE GTR+ASC     │
       │                        │      │  with bootstrap      │
       │   band_tree.json       │      │   sample_tree.nwk    │
       │   band_tree_dA.json    │      │   sample_tree.json   │
       └────────┬───────────────┘      └──────────┬───────────┘
                │                                 │
                └─────────────┬───────────────────┘
                              │
                              ▼
                ┌───────────────────────────┐
                │ Concordance assessment     │
                │ (band × clade table)       │
                │ ARI, Cramér's V, purity    │
                └───────────────┬───────────┘
                                │
                                ▼
                ┌───────────────────────────┐
                │ Divergence-pattern test    │
                │ (derived-allele sharing)   │
                │ ladder | parallel | amb    │
                └───────────────┬───────────┘
                                │
                                ▼
                ┌───────────────────────────┐
                │ Tree manifest + JSONs      │
                │ → atlas tree panel         │
                │ → paper figure             │
                └────────────────────────────┘
```

---

## Task 1: Core-interval selection

### Inputs
- Candidate interval (chrom, start, end)
- PCA results from HANDOFF 1 (per-window scores; band labels per sample)
- Optional: per-sample dosage matrix from HANDOFF 1's heatmap producer
  (for mosaic flagging)

### Default policy
- **Fixed flanks**: trim 200 kb (configurable) from each end.
- **Sample filter**: keep all samples for the first pass. Flag mosaic
  samples by computing per-sample dosage SD across 10 kb sub-windows;
  flag if SD > threshold. Flagged samples are kept by default but
  available for separate visualization.

### Output

```
core_interval.tsv:
  candidate_id   chrom   core_start   core_end   flanks_bp_each_side   n_samples_kept   n_samples_flagged_mosaic
  LG28_15.115_18.005   C_gar_LG28   15315000   17805000   200000   223   3

samples_kept.txt:    [list of sample IDs to use for tree]
samples_mosaic.txt:  [flagged samples — kept by default]
```

---

## Task 2: PATH A — band-level dXY/dA NJ tree

This is the fast group-level pre-pass. ~5 leaves; runs in seconds.

### Using the existing dispatcher

```r
source("region_stats_dispatcher.R")
configure_dispatcher(config_file = "00_ancestry_config.sh")

# Bands as groups (sample lists per band, from PCA cluster labels)
groups <- list(
  HOM1 = readLines("samples_band_HOM1.txt"),
  HET  = readLines("samples_band_HET.txt"),
  HOM2 = readLines("samples_band_HOM2.txt")
)

# Compute Fst, dXY, dA over the core interval as ONE big window
core_size <- 17805000 - 15315000   # 2,490,000 bp
result <- get_region_stats(
  chr = "C_gar_LG28", start = 15315000, end = 17805000,
  what = c("Fst", "dXY", "dA", "theta_pi"),
  groups = groups,
  popstats_opts = list(fixed_win = paste0(core_size, ":", core_size),
                       weighted = TRUE, downsample = 1, type = 2)
)

# result$dXY: named list — dXY_HOM1_HET, dXY_HOM1_HOM2, dXY_HET_HOM2
# result$dA:  same shape
# result$Fst: same shape
```

### Build distance matrix → NJ tree

```r
bands <- names(groups)
n <- length(bands)
D <- matrix(0, n, n, dimnames = list(bands, bands))
for (i in 1:(n-1)) for (j in (i+1):n) {
  key <- paste0("dXY_", bands[i], "_", bands[j])
  if (is.null(result$dXY[[key]])) key <- paste0("dXY_", bands[j], "_", bands[i])
  D[i, j] <- D[j, i] <- result$dXY[[key]]
}

library(ape)
tree_dXY <- nj(as.dist(D))
tree_dXY <- ladderize(tree_dXY)
write.tree(tree_dXY, "band_tree_dXY.nwk")
# Same for D_dA → tree_dA → band_tree_dA.nwk
```

### Why both dXY and dA

- **dXY** = total sequence divergence between groups
- **dA** = dXY − mean(within-group π)

For hatchery cohorts with high within-band relatedness (family
structure), dXY tree branches inflate. dA corrects for this.

If both trees have **same topology** → between-clade divergence
dominates, trust the topology. If **different topology** → within-band
diversity is distorting dXY; the dA tree is more honest. **The
agreement itself is a finding.**

### Output

```
band_tree.json:
{
  "candidate_id": "LG28_15.115_18.005",
  "core_interval": {"chrom": "C_gar_LG28", "start": 15315000, "end": 17805000},
  "method": "neighbor_joining",
  "distance_metric": "dXY",
  "n_bands": 3,
  "bands": ["HOM1", "HET", "HOM2"],
  "band_sizes": [60, 106, 60],
  "distance_matrix": [[0, 0.0021, 0.0048], [0.0021, 0, 0.0026], [0.0048, 0.0026, 0]],
  "newick": "((HOM1:0.001,HET:0.0008):0.0005,HOM2:0.002);",
  "internal_node_dxy": {"node_HOM1_HET": 0.0021, ...},
  "tree_dA_distance_matrix": [...],
  "tree_dA_newick": "...",
  "bootstrap_support": null
}
```

### Bootstrap (Phase 2 polish)

The popstats engine emits per-window values. Bootstrap by resampling
windows with replacement:
1. Sample N windows from the core (with replacement)
2. Recompute weighted-mean dXY/dA
3. Rebuild tree
4. Repeat 100-1000×; report consensus topology with support

---

## Task 3: PATH B — per-sample SNP alignment ML tree

This is the primary deliverable. Per-sample resolution, model-based
branch lengths, bootstrap support.

### Pipeline

```
core Beagle (from view) → genotype calls per sample → SNP FASTA →
snp-sites → IQ-TREE GTR+ASC → tree
```

### Step 3.1: Beagle → genotype calls per sample

For the chosen view (default `bi_baseline` for the canonical paper tree;
optionally `all_pairs` for multi-allelic-aware tree):

```r
# Read filtered Beagle in core interval
bgl <- read_beagle("bi_baseline.beagle.gz")
sc  <- fread("bi_baseline.beagle.pairs.tsv")

# Subset to core interval
in_core <- sc[chrom == CHR & pos >= CORE_START & pos < CORE_END]
markers <- in_core$marker

# Per-sample, per-marker hard call from GLs
# call = argmax over (AA, Aa, aa) with min posterior threshold
# 0/0 = REF/REF, 0/1 = REF/ALT, 1/1 = ALT/ALT
# missing if max posterior < threshold (e.g. 0.8)
calls <- call_genotypes(bgl, threshold = 0.8)
# matrix: n_samples × n_markers, values in {"0/0", "0/1", "1/1", "./."}
```

### Step 3.2: Genotype calls → IUPAC FASTA

For each sample, build a sequence string. For each marker, look up the
REF and ALT alleles from the marker name (encoded as
`<chrom>_<pos>_<role_a>_<role_b>_<allele_a>_<allele_b>`):

```r
encode <- function(call, ref, alt, het_mode = "iupac") {
  if (call == "./." || is.na(call)) return("N")
  if (call == "0/0") return(ref)
  if (call == "1/1") return(alt)
  # 0/1
  switch(het_mode,
    "iupac" = iupac_code(ref, alt),
    "n" = "N",
    "random" = sample(c(ref, alt), 1),
    "hom_only" = NA_character_)  # filtered out upstream
}

iupac_code <- function(a, b) {
  pair <- paste0(sort(c(a, b)), collapse = "")
  switch(pair,
    "AC" = "M", "AG" = "R", "AT" = "W",
    "CG" = "S", "CT" = "Y", "GT" = "K",
    "N")
}

# Build FASTA: one sequence per sample
fasta <- character(n_samples)
for (i in seq_len(n_samples)) {
  seq_chars <- character(length(markers))
  for (m in seq_along(markers)) {
    seq_chars[m] <- encode(calls[i, m],
                           in_core$allele_a[m], in_core$allele_b[m],
                           het_mode = opt$het_mode)
  }
  fasta[i] <- paste0(seq_chars, collapse = "")
}

# Write
writeLines(unlist(lapply(seq_len(n_samples), function(i) {
  c(paste0(">", samples[i]), fasta[i])
})), "core.fa")
```

### Step 3.3: snp-sites

`snp-sites` extracts variant columns and emits a clean alignment.

```bash
snp-sites -o core.snps.fa core.fa
```

This may be redundant since we built the FASTA from SNPs only; but
running it ensures invariant columns (e.g. all-N from missing) are
removed.

### Step 3.4: IQ-TREE with GTR+ASC

```bash
iqtree2 -s core.snps.fa \
        -m GTR+ASC \
        -B 1000 \
        -T AUTO \
        --prefix sample_tree
```

- `GTR+ASC`: GTR substitution model with ascertainment-bias correction
  (required for SNP-only data; otherwise branch lengths inflated)
- `-B 1000`: 1000 ultrafast bootstrap replicates
- `-T AUTO`: autodetect threads

Outputs: `sample_tree.treefile` (Newick), `sample_tree.iqtree` (log).

For 226 samples × ~50,000 SNPs in the core, runtime ~5-30 min.

### Step 3.5: Newick → JSON for atlas

```r
library(ape)
tree <- read.tree("sample_tree.treefile")
# Pre-compute leaf positions for atlas SVG/canvas rendering
layout <- ape::plot.phylo(tree, plot = FALSE)
# Save edges, leaf coordinates, internal node positions
```

### Output

```
sample_tree.json:
{
  "candidate_id": "LG28_15.115_18.005",
  "core_interval": {...},
  "method": "iqtree_GTR_ASC",
  "het_mode": "iupac",
  "view_used": "bi_baseline",
  "n_samples": 223,
  "n_snps_used": 47823,
  "samples": ["S0001", ...],
  "sample_bands": {"S0001": "HOM1", ...},
  "newick": "(((S0001:0.0021,S0023:0.0020):0.0011, ... );",
  "bootstrap_support": [98, 100, 87, ...],
  "leaf_x": [...],   // pre-computed for atlas
  "leaf_y": [...],
  "edges": [{"from": ..., "to": ..., "length": ..., "support": ...}, ...]
}
```

### Multiple het_mode runs

For paper figure, produce both `iupac` and `hom_only` trees. Compare
topologies. Methods text:

> "Per-sample trees were built using IQ-TREE 2 with GTR+ASC on SNP-only
> alignments derived from the inversion-core Beagle. Heterozygous
> genotypes were encoded with IUPAC ambiguity codes; a parallel
> homozygote-only tree confirmed that the topology was not driven by
> ambiguity-code placement of heterozygotes."

---

## Task 4: Concordance assessment (band ↔ clade)

### Cut sample tree at K clades

For each tree (Path A's band tree is trivial; Path B's per-sample tree
needs cutting):

```r
# Sample tree from Path B
tree_sample <- read.tree("sample_tree.treefile")

# Convert to hclust via midpoint rooting
library(phangorn)
tree_rooted <- midpoint(tree_sample)
hc <- as.hclust(tree_rooted)
clades <- cutree(hc, k = length(bands))
```

### Concordance metrics

```r
table_band_clade <- table(sample_bands, clades)

# Purity: each clade's largest band fraction
purity <- sum(apply(table_band_clade, 2, max)) / sum(table_band_clade)

# Cramér's V
chisq <- chisq.test(table_band_clade, simulate.p.value = TRUE)$statistic
cramers_v <- sqrt(chisq / (sum(table_band_clade) * (min(dim(table_band_clade)) - 1)))

# Adjusted Rand Index (preferred — chance-corrected)
ari <- mclust::adjustedRandIndex(sample_bands, clades)
```

### Output

```
concordance.json:
{
  "candidate_id": "LG28_15.115_18.005",
  "n_clades_tested": 3,
  "tree_source": "path_B_iqtree",
  "het_mode": "iupac",
  "contingency_table": {
    "HOM1": {"clade_1": 58, "clade_2": 2, "clade_3": 0},
    "HET":  {"clade_1": 4,  "clade_2": 99, "clade_3": 3},
    "HOM2": {"clade_1": 0,  "clade_2": 1, "clade_3": 59}
  },
  "purity": 0.972,
  "cramers_v": 0.94,
  "adjusted_rand_index": 0.918,
  "interpretation": "high_concordance"
}
```

`interpretation`: high if ARI > 0.7, medium if 0.4-0.7, low otherwise.

---

## Task 5: Divergence-pattern test (ladder vs parallel)

Distinguish Model 1 (ladder) from Model 2 (parallel) by **derived-allele
sharing**.

### Method

1. Designate reference clade (typically standard arrangement / lowest
   within-clade π proxy; or external outgroup if available).
2. For each non-reference clade, count:
   - **Private derived alleles**: derived state present in this clade,
     ancestral in others
   - **Shared derived alleles**: derived in 2+ non-ref clades
   - **Nested derived** (ladder marker): derived state exclusive to a
     "deeper" clade

3. Build sharing matrix:

   ```
                ClA   ClB   ClC
   ClA private  120     -     -
   ClB private    -    85     -
   ClC private    -     -    142
   ClA + ClB    34
   ClA + ClC    12
   ClB + ClC    98
   all 3        56
   ```

### Interpretation

| Pattern | Sharing matrix signature |
|---|---|
| **Parallel** (Model 2) | Many private per clade; symmetric pairwise sharing; few all-three sharing |
| **Ladder** (Model 1) | Strong nesting — ClA derived ⊂ ClB derived ⊂ ClC derived |
| **Scattered** (Model 4 contamination) | No clear pattern; suggests recombination contamination → re-check core |

### Pattern label

```r
private_fraction <- n_private / n_total_derived  # per clade

if (mean(private_fraction) > 0.6 && pairwise_sharing_symmetric) {
  pattern <- "parallel"
} else if (nested_evidence > 0.7) {
  pattern <- "ladder"
} else {
  pattern <- "ambiguous"
}
```

### Caveat

Needs an outgroup (or designated ancestral-like clade) to call derived
state. For first pass, use band with lowest within-clade π as proxy
ancestral. **Note this assumption explicitly in output.** Future
improvement: real outgroup from `C. macrocephalus` for `C. gariepinus`
candidates.

### Output

```
divergence_pattern.json:
{
  "candidate_id": "LG28_15.115_18.005",
  "reference_clade": "HOM1",
  "reference_basis": "lowest_within_clade_pi",
  "n_clades": 3,
  "private_fraction": {"HOM1": 0.78, "HET": 0.45, "HOM2": 0.81},
  "pairwise_sharing": {"HOM1_HET": 12, "HOM1_HOM2": 8, "HET_HOM2": 67},
  "all_three_sharing": 23,
  "pattern_label": "parallel",
  "confidence": "medium"
}
```

---

## Task 6: Tree producer driver

Single driver script ties Tasks 1-5:

```bash
bash run_tree_for_candidate.sh \
  --candidate LG28_15.115_18.005 \
  --bands_from pca_results/pca_bi_baseline_unweighted_bi_baseline.json \
  --beagle_view bi_baseline.beagle.gz \
  --beagle_view_sidecar bi_baseline.beagle.pairs.tsv \
  --beagle_master master_all_pairs.beagle.gz \
  --beagle_master_sidecar master_all_pairs.beagle.pairs.tsv \
  --het_mode iupac \
  --bootstrap 1000 \
  --out_dir trees/LG28_15.115_18.005/
```

Outputs:

```
trees/LG28_15.115_18.005/
├── core_interval.tsv
├── samples_kept.txt
├── samples_mosaic.txt
├── path_A/
│   ├── band_tree_dXY.json
│   ├── band_tree_dA.json
│   └── band_tree.pdf       # static plot for paper
├── path_B/
│   ├── core.fa             # IUPAC-encoded FASTA per sample
│   ├── core.snps.fa        # snp-sites cleaned
│   ├── sample_tree.treefile
│   ├── sample_tree.iqtree  # IQ-TREE log
│   ├── sample_tree.json
│   └── sample_tree.pdf     # ape::plot.phylo with band colors
├── path_B_hom_only/        # validation tree, HOMs only
│   └── ...
├── concordance.json
├── divergence_pattern.json
└── tree_manifest.json
```

The manifest:

```json
{
  "candidate_id": "LG28_15.115_18.005",
  "core_interval": {...},
  "n_samples": 223,
  "files": {
    "band_tree_dXY":     "path_A/band_tree_dXY.json",
    "band_tree_dA":      "path_A/band_tree_dA.json",
    "sample_tree":       "path_B/sample_tree.json",
    "sample_tree_hom":   "path_B_hom_only/sample_tree.json",
    "concordance":       "concordance.json",
    "divergence":        "divergence_pattern.json"
  },
  "summary": {
    "n_bands": 3,
    "ari": 0.918,
    "purity": 0.972,
    "pattern": "parallel",
    "iupac_vs_hom_topology_match": true
  }
}
```

---

## Task 7: Atlas tree panel

Third panel in Page-1 candidate mode (alongside PCA + heatmap from
HANDOFF 2).

### Panel layout

```
┌──────────────────────────────────────────────────────────────────┐
│ Top controls bar (shared with PCA + heatmap)                      │
├───────────────────────────┬──────────────────────────────────────┤
│ PCA panel                 │ Heatmap panel                         │
├───────────────────────────┴──────────────────────────────────────┤
│ Tree panel                                                        │
│  ┌──────────┬─────────────────────────────────────────────────┐  │
│  │ Band tree│ Sample tree (IQ-TREE) — leaves colored by band   │  │
│  │ (Path A) │                                                   │  │
│  │  HOM1 ─┐ │ ─── HOM1 ──┐                                      │  │
│  │        ├─┤ ─── HOM1 ──┤                                      │  │
│  │  HET ──┤ │ ─── HET ───┤   bootstrap shown on internal nodes  │  │
│  │        │ │            │                                      │  │
│  │  HOM2 ─┘ │ ─── HOM2 ──┘                                      │  │
│  │          │                                                   │  │
│  │  ARI:    │   het_mode: [iupac ▾] [hom_only]                  │  │
│  │  0.918   │                                                   │  │
│  │ pattern: │                                                   │  │
│  │ parallel │                                                   │  │
│  └──────────┴─────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
```

### Tree-panel-local controls

```
Tree distance: [dXY ▾ | dA]                  (Path A only)
het_mode:      [iupac ▾ | hom_only | n | random]   (Path B; reloads tree)
Show:          [☑ band tree] [☑ sample tree]
Sample tree:   [collapse to clades ▾ | full leaves]
Color edges:   [none ▾ | dXY to ref clade | clade]
```

### Linkage with other panels

- Hover sample in PCA → highlight leaf in sample tree
- Hover leaf in tree → highlight in PCA + heatmap
- Click clade in tree → select all clade samples → highlight everywhere
- Click branch in band tree → show split's stats (dXY, dA, n_samples)
- Click branch in sample tree → show bootstrap support, n_descendants

### Rendering

Producer outputs pre-computed `leaf_x`, `leaf_y`, `edges` in the JSON.
Atlas just draws SVG/canvas. ~100 lines of JS for basic render. Edge
coloring continuous (dXY scale) or categorical (clade).

---

## Implementation phases

### Phase 1: Path A band tree (1-2 days)
- Core selection script
- Band tree via `region_stats_dispatcher::get_region_stats()`
- NJ on dXY and dA matrices via `ape::nj()`
- Static PDF for paper via `ape::plot.phylo()`
- Output band_tree.json (both dXY and dA versions)

### Phase 2: Path B sample tree (2-3 days)
- Beagle → genotype calls (with min posterior threshold)
- IUPAC FASTA encoding (with mode selection)
- `snp-sites` → `iqtree2 -m GTR+ASC -B 1000`
- Both `iupac` and `hom_only` runs
- Newick → JSON with pre-computed layout
- Static PDF with leaves colored by band

### Phase 3: Concordance + divergence pattern (1 day)
- Sample tree → clade cuts
- ARI / Cramér's V / purity
- Derived-allele sharing matrix → pattern label

### Phase 4: Atlas integration (3-5 days)
- Tree panel SVG renderer (band + sample side-by-side)
- Linkage with PCA + heatmap (shared color, hover)
- Tree-panel-local controls (het_mode toggle reloads tree)
- Manifest loading

### Phase 5: Polish (1-2 days)
- Phase-A bootstrap (window resampling)
- `C. macrocephalus` outgroup integration when data available
- Per-sample mosaic flagging via dosage SD

Total ~2 weeks for full feature. **Phase 1 + 2 alone (no atlas) give
the paper figure** in 4-5 days.

---

## Validation checks

For LG28:15.115-18.005 (the known-positive control):

1. **Path A band tree**: HOM1 and HOM2 maximally divergent (highest
   dXY); HET intermediate. dXY tree and dA tree should have same
   topology — if not, hatchery family inflation is significant.

2. **Path B sample tree**: ARI vs PCA bands > 0.7. Bootstrap support
   on band-defining internal nodes ≥ 95.

3. **iupac vs hom_only topology match**: cluster assignments at the
   K=n_bands cut should agree on >95% of the HOM samples. If they
   disagree substantially, IUPAC encoding is masking real haplotype
   structure → flag in methods.

4. **Pattern label**: LG28 with 60/106/60 → expect "parallel" or
   "ambiguous." Strong ladder pattern would be unexpected for a balanced
   inversion.

5. **Sensitivity to flank size**: rerun with 0 / 200 / 500 kb flanks.
   Path A topology should be stable. Path B topology may shift at edges
   (some samples on the boundary).

6. **Sensitivity to view (Path B)**: build sample trees on
   `bi_baseline`, `tri_extras`, `all_pairs`. Topologies should agree on
   the major splits; differences at finer resolution indicate where
   multi-allelic information adds detail.

---

## What this answers conceptually

The tree panel completes the inversion confirmation triangle:

| Panel | Question |
|---|---|
| PCA | How do samples cluster in dimension-reduced variation? |
| Heatmap | What dosage patterns make up each cluster? |
| Tree (Path A) | Are clusters phylogenetically coherent groups? Ladder vs parallel? |
| Tree (Path B) | Where does each individual sample fall on the haplotype tree? |

For the paper, the strongest claim is multi-panel concordance:

> "PCA bands, dosage patterns, and inversion-core tree clades all agree.
> The inversion core diversified into N parallel haplotype clades."

---

## File map

```
mgl_adapter/                          (existing, HANDOFFs 0-4)
└── ...

trees/                                (this handoff)
├── core_select.R                     (Task 1)
├── path_A_band_tree.R                (Task 2 — popstats + NJ)
├── path_B_sample_tree.R              (Task 3 — Beagle → IUPAC FASTA + IQ-TREE)
├── compute_concordance.R             (Task 4)
├── divergence_pattern.R              (Task 5)
├── run_tree_for_candidate.sh         (driver)
└── tree_panel.js                     (atlas-side rendering)

specs/
└── HANDOFF_5_tree.md                 (this document)
```

---

## What you can ignore

- **Whole-genome trees**: out of scope. Per-candidate only.
- **Time-calibrated trees**: needs mutation rate + outgroup; future.
- **Bayesian methods (MrBayes, BEAST)**: NJ + IQ-TREE ML are sufficient.
- **Phasing**: hets handled via IUPAC or hom_only filter; phased haplotype
  trees are a future extension.

## Pointers to existing code

- `region_stats_dispatcher.R` (uploaded): see `get_region_stats()` and
  `route_to_c_popstats()` for dXY/dA query interface used by Path A.
- `region_popstats.c` (uploaded): per-site dXY, dA, π columns used by
  Path A. Note the dA invariant: must come from the same engine call.
- `LAUNCH_region_popstats.slurm`: existing whole-genome runner. For
  per-candidate trees, run with `--range` set to the core interval.
- `plot_fst_dxy_tracks.R`: existing Mérot-style track plotter; tree
  panel should match its visual style.
- HANDOFF 1 producer outputs: `pca_<view>_<weighting>_<anchor>.json`
  contains per-window cluster labels → band assignments.

## External tools required

- **`snp-sites`** (apt: `snp-sites`, conda: `bioconda::snp-sites`)
- **`iqtree2`** (conda: `bioconda::iqtree`, version ≥ 2.0)
- **R packages**: `ape`, `phangorn`, `mclust`, `data.table`

## Pointers to mgl_adapter

- `master_all_pairs.beagle.gz` + `.pairs.tsv`: source of multi-allelic
  Beagle when running Path B with the `all_pairs` view.
- `beagle_filter_pairs.R`: applies view filter before tree build.
- `beagle_weight_by_support.R`: NOT USED for trees — weighting is for
  PCA only, not for tree distance/encoding.
