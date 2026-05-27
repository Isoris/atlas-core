# SPEC 0 — Master reference

This is the full architectural reference for the multi-allelic inversion
atlas project. Sub-specs (HANDOFF_1 through HANDOFF_4) excerpt portions
of this for use in fresh chats; this document is the canonical source.

**What's done**: Sections 1–6 (master Beagle, filter, weighter, scanner,
driver). Implemented and tested in `mgl_adapter/` v5.

**What's specified but not built**: Sections 7–11 (PCA producer with
anchor modes, heatmap producer, atlas Page-1 candidate mode integration,
shared rendering state).

---

## 1. Convention: roles and pairs

Every analysis hangs on this one convention. **Per site, alleles are
ranked by total cohort read count.**

| Role     | Definition                          | Defined when           |
|----------|-------------------------------------|------------------------|
| `MAJOR`  | Allele with highest cohort total    | n_alleles ≥ 1          |
| `MINOR1` | 2nd highest cohort total            | n_alleles ≥ 2          |
| `MINOR2` | 3rd highest cohort total            | n_alleles ≥ 3 (tri+)   |
| `MINOR3` | 4th highest cohort total            | n_alleles = 4 (quad)   |

- Definition is **per-site, by cohort read count**, not by ANGSD's
  `-doMajorMinor` GL inference. Stable, deterministic.
- Independent of REF/ALT and ancestral state.
- Ties resolved by lower allele code (A < C < G < T).
- Same convention at biallelic, tri-allelic, and quad-allelic sites.

**Pairs** are unordered combinations of roles. Per site, all unordered
pairs of *observed* alleles are emitted:

| Site type     | Pairs emitted                                                | # rows |
|---------------|--------------------------------------------------------------|--------|
| Biallelic     | `MAJOR_MINOR1`                                               | 1      |
| Tri-allelic   | `MAJOR_MINOR1`, `MAJOR_MINOR2`, `MINOR1_MINOR2`              | 3      |
| Quad-allelic  | All 6 pairs of {MAJOR, MINOR1, MINOR2, MINOR3}               | 6      |

Marker name format:
```
<chrom>_<pos>_<ROLE_a>_<ROLE_b>_<allele_a>_<allele_b>
```
Example: `C_gar_LG28_15234521_MINOR1_MINOR2_G_C`

---

## 2. The three layers

| Layer | Question | Default | Where |
|---|---|---|---|
| **Master** | Is this pair observable? | yes if ≥ 1 read for each allele | `mgl10_to_beagle.R` |
| **View** | Is it trustworthy enough to enter analysis? | configurable (filters off by default) | `beagle_filter_pairs.R` |
| **Weight** | How much should it count in PCA? | `sqrt(pair_count / max_pair_count)` | `beagle_weight_by_support.R` |

Master is unfiltered. Views and weights are downstream operations on
copies. Same master serves many threshold choices; re-filtering never
requires re-running ANGSD or the adapter.

---

## 3. Format: master Beagle + sidecar

### 3.1 Master Beagle

Standard PCAngsd Beagle layout. **One row per (site, allele-pair).**
PCAngsd, NGSadmix, evalAdmix, ngsRelate read it without modification.

```
marker  allele1  allele2  ind0_AA  ind0_Aa  ind0_aa  ind1_AA  ind1_Aa  ind1_aa  ...
```

- `allele1`, `allele2`: integer codes (A=0, C=1, G=2, T=3)
- 3 likelihoods per individual, normalized per-row to sum to 1 per sample
- Tri-allelic sites contribute 3 rows; quad sites 6 rows

Generated from ANGSD `-doGlf 1` by projecting the relevant 3 of 10 GLs:

```
For pair (allele a, allele b) at one site, one individual:
  L_aa = L10[idx(a,a)]
  L_ab = L10[idx(a,b)]
  L_bb = L10[idx(b,b)]
  P    = exp(L) / sum(exp(L))   [linear-scale normalize]
```

### 3.2 Sidecar (`.pairs.tsv`)

One row per Beagle row.

| Column | Meaning |
|---|---|
| `marker` | matches Beagle col 1 |
| `chrom`, `pos` | site coordinates |
| `n_alleles_obs` | 2, 3, or 4 |
| `site_total_count` | sum of observed allele cohort counts |
| `role_a`, `role_b` | `MAJOR`, `MINOR1`, `MINOR2`, `MINOR3` |
| `allele_a`, `allele_b` | nucleotides |
| `count_a`, `count_b` | cohort read counts |
| `pair_count` | `count_a + count_b` |
| `pair_fraction` | `pair_count / site_total_count` |
| `min_pair_allele_count` | `min(count_a, count_b)` — bottleneck |
| `n_samples_with_a` | individuals with ≥1 read of allele a |
| `n_samples_with_b` | same for b |
| `n_samples_with_either` | individuals with ≥1 read of a or b |
| `maf_pair` | `min(count_a,count_b) / pair_count` |

Every filter and weighting decision reads from these columns.

---

## 4. ANGSD inputs

Per candidate interval, run ANGSD once:

```bash
angsd -b ${BAMLIST} -ref ${REF} \
  -GL 1 -doGlf 1 \
  -doMajorMinor 1 -doMaf 1 \
  -doCounts 1 -dumpCounts 3 \
  -SNP_pval 1e-6 -minMaf 0.02 \
  -skipTriallelic 0 \
  -minQ 20 -minMapQ 30 -baq 1 -C 50 \
  -setMinDepthInd 3 -setMaxDepthInd 30 -minInd N \
  -remove_bads 1 -uniqueOnly 1 -only_proper_pairs 1 \
  -rf interval.rf.txt -r chrom:start-end \
  -sites ${CALLABLE_SITES} \
  -P 16 -out interval_glf10
```

Critical flags:
- **`-doGlf 1`**, not `2`. Outputs full 10 GLs per site.
- **`-skipTriallelic 0`**. Multi-allelic must survive into GLF10.
- **`-dumpCounts 3`**. Required. Per-individual A/C/G/T counts per site.

**One ANGSD run per candidate interval, never whole-genome.**

Outputs:
- `OUT.glf.gz` — binary, n_sites × n_ind × 10 doubles
- `OUT.glf.pos.gz` — chrom, pos, major_angsd, minor_angsd
- `OUT.mafs.gz` — site-level MAFs (informational)
- `OUT.counts.gz` — per-ind A,C,G,T counts

---

## 5. Implemented scripts

### 5.1 `mgl10_to_beagle.R` — master converter
Reads ANGSD outputs, writes master Beagle + sidecar. No filtering. See
Section 3 for output format.

Key option: `--gl_log_base natural|log10` (verify against ANGSD build).

### 5.2 `beagle_filter_pairs.R` — view producer
Reads master, writes filtered Beagle + filtered sidecar.

| Flag | Default | Effect |
|---|---|---|
| `--pairs ROLE_PAIR[,...]` | unset | role allowlist |
| `--min_pair_allele_count` | 0 | min(count_a, count_b) |
| `--min_pair_count_total` | 0 | count_a + count_b |
| `--min_pair_fraction` | 0 | pair_count / site_total |
| `--min_maf_pair` | 0 | within-pair MAF |
| `--min_n_samples_with_minor` | 0 | inds carrying rarer allele |
| `--min_n_alleles_obs` / `--max_n_alleles_obs` | 0 / 4 | site allele-count window |

All AND-combined.

### 5.3 `beagle_weight_by_support.R` — PCA-only re-weighter
Per row: `gl' = (gl - 1/3) * sqrt(w) + 1/3` then renormalize.

| Mode | `w` |
|---|---|
| `max` (default) | `support / max(support)` |
| `median` | `support / median(support)` |
| `fixed` | `support / fixed_value` |
| `none` | `w = 1` |

Support stat (`--weight_stat`): `pair_count` | `min_pair_allele_count` |
`n_samples_with_either`. `--power P` exponent (default 1).
`--cap_at_one TRUE` (default) prevents up-weighting.

**Weighted Beagle is for PCAngsd only.** Not proper P(reads|GT)
likelihoods; biases NGSadmix/ngsRelate.

### 5.4 `scan_rare_pairs.R` — discovery scanner
Reads master sidecar only. Writes `rare_pair_windows.tsv`. Flags windows
enriched for MINOR2/MINOR3 pairs with small-but-coherent carrier counts.
Pre-PCA discovery: tells you where to look on minor PCs of `all_pairs`.

### 5.5 `run_pair_pca_matrix.sh` — driver
End-to-end per candidate. Produces:
- Master Beagle + sidecar
- 4 filtered views: `bi_baseline`, `tri_extras`, `quad_extras`, `all_pairs`
- 4 weighted variants (one per view, mode=max, stat=pair_count)
- 8 PCAngsd runs (one per Beagle)
- Rare-pair scanner output
- `manifest.json`

---

## 6. Canonical views and the experiment matrix

| View name | Pairs included | Purpose |
|---|---|---|
| `bi_baseline` | `MAJOR_MINOR1` only | Baseline; ≈ existing biallelic pipeline |
| `tri_extras` | `MAJOR_MINOR2`, `MINOR1_MINOR2` | Tri-allelic-only contrasts |
| `quad_extras` | All MINOR2/MINOR3 pairs | All multi-allelic extras |
| `all_pairs` | (no role filter) | Full multi-allelic |

For each view: unweighted + weighted variant. Eight Beagles, eight PCAngsd
runs.

**Why no `best_per_site` mode**: pre-collapsing to one pair per site does
PCA's job badly. PCA finds variance axes on its own; pre-selecting a pair
forces a projection. A rare-inversion signal lives in MINOR2/MINOR3 rows;
"best pair" rules based on support stats discard exactly those rows.

---

## 7. PCA basis anchoring (NEW — to be implemented in producer)

### 7.1 The two anchor modes

PCA finds eigenvectors of the covariance matrix; eigenvectors orient
themselves to maximize explained variance. Different views give different
covariance matrices, so their PCAs are in *different rotations of sample
space*. Cross-view comparison is awkward.

**Anchor mode** fixes the basis using one view's eigenvectors and projects
all other views into that basis.

| Mode | Anchor source per window | Purpose |
|---|---|---|
| `bi_baseline` (default) | `MAJOR_MINOR1` rows of `bi_baseline` view | All views in same axes; multi-allelic adds *displacement* relative to biallelic |
| `view_self` | Lowest-rank biallelic-equivalent rows of the view itself | Internal coherence of the view's contrasts |
| `none` (independent) | each view computes its own basis | Standard local-PCA per view |

For Anchor 2 with views that have no `MAJOR_MINOR1`:

| View | Anchor 2 basis pair |
|---|---|
| `bi_baseline` | `MAJOR_MINOR1` (= same as Anchor 1) |
| `tri_extras` | `MAJOR_MINOR2` |
| `quad_extras` | `MAJOR_MINOR2` |
| `all_pairs` | `MAJOR_MINOR1` (= same as Anchor 1 if filters match) |

### 7.2 Math

Per window:

```
1. Run PCA on bi_baseline rows in this window:
     X_bi   = dosage matrix (n_samples × n_markers_bi), centered per marker
     C_bi   = (1/n_markers_bi) * X_bi @ X_bi.T   →  n_samples × n_samples
     V_bi, lam_bi = eigen(C_bi); take top 2

2. For each view in {bi_baseline, tri_extras, quad_extras, all_pairs}:
     X_view = dosage matrix for the view, centered per marker
     # Anchor 1: bi_baseline basis
     scores_anchor_bi = X_view.T @ V_bi            # n_markers × 2  -> avg over markers? or per-sample?
     # Actually: project sample positions into V_bi
     # Sample scores on PC k = sample i's coord = sum_j X_view[i,j] * loading_j
     # For PCA: V are eigenvectors of sample-sample covariance, so
     # sample scores = V_bi[:, 1:2]   directly (these ARE the per-sample PC coords)
     # We're computing it FROM the view's data, anchored on bi's basis:
     scores = (X_view @ X_view.T / n_markers_view) @ V_bi
     # equivalently: project the view's covariance matrix through V_bi
```

Concretely for the producer: compute `C_view` (sample-sample covariance
from the view's dosage matrix), then `scores = C_view @ V_bi[:, 1:2]`.
This gives n_samples × 2 scores in the bi_baseline basis.

```
3. Anchor 2 (view_self):
     basis_pair = (MAJOR_MINOR1 if view has it else MAJOR_MINOR2)
     X_basis    = dosage matrix from rows matching basis_pair in this view
     C_basis    = (1/n_markers_basis) * X_basis @ X_basis.T
     V_self     = eigen(C_basis); top 2
     scores_anchor_self = C_view @ V_self
```

### 7.3 Cost

Per window: 1 eigendecomposition for `bi_baseline` (Anchor 1), 1 for each
non-bi view's self-basis (Anchor 2 mode), 4 cheap projections per anchor
mode. Eigendecomposition of 226×226 is ~ms; projection is one matrix
multiply. Total per window: well under a second.

### 7.4 Sign convention

PCA eigenvectors have arbitrary sign. To keep axes consistent across
windows and across views, apply a deterministic sign rule **on the anchor
basis**:
- PC1 sign: +1 if `mean(V[anchor_sample_idx, 1]) >= 0`, else flip
- PC2 sign: similar with anchor_sample_idx_2

`anchor_sample_idx` is a configurable sample (or set of samples) chosen
to be at the +PC1 end. Existing `pca_panel.js` has its own PC1 sign-flip
rule already; producer should match.

---

## 8. Producer JSON shape

Per (view, anchor_mode, weighting) combination, one JSON:

```json
{
  "candidate_id": "LG28_15.115_18.005",
  "chrom": "C_gar_LG28",
  "interval_start": 15115000,
  "interval_end":   18005000,
  "view": {
    "name": "all_pairs",
    "pairs_included": "ALL",
    "weighted": true,
    "weight_mode": "max",
    "weight_stat": "pair_count",
    "filter_thresholds": { "min_pair_allele_count": 6, "min_maf_pair": 0.02, "min_n_samples_with_minor": 3 },
    "anchor_mode": "bi_baseline",
    "anchor_self_basis_pair": null
  },
  "n_samples": 226,
  "samples": ["S0001", "S0002", ...],
  "window_def": { "kind": "bp_span", "size_bp": 50000, "step_bp": 50000 },
  "n_windows": 60,
  "windows": [
    {
      "idx": 0,
      "start": 15115000, "end": 15165000,
      "n_pair_rows": 3421,
      "n_unique_sites": 1187,
      "n_biallelic_sites": 1102,
      "n_triallelic_sites": 78,
      "n_quadallelic_sites": 7,
      "lam1": 0.847, "lam2": 0.052,
      "pc1": [0.12, -0.34, 0.08, ...],
      "pc2": [-0.05, 0.21, -0.18, ...],
      "mean_pair_count": 142,
      "median_pair_count": 138,
      "polarity_flips_applied": 23
    },
    ...
  ]
}
```

For `--anchor_mode both`, fields `pc1`, `pc2`, `lam1`, `lam2` carry the
default (bi_baseline-anchored) values, and additional fields
`pc1_self`, `pc2_self`, `lam1_self`, `lam2_self` carry view-self-anchored
values.

Naming convention for output JSONs:
```
pca_<view>_<weighting>_<anchor_mode>.json
e.g. pca_all_pairs_weighted_bi_baseline.json
     pca_tri_extras_unweighted_view_self.json
```

`bi_baseline` view's `view_self` and `bi_baseline` anchor variants are
identical by definition; produced once and symlinked.

---

## 9. Heatmap producer JSON shape (NEW)

Parallel to the PCA JSON, per (view, weighting, centering) combination:

```json
{
  "candidate_id": "LG28_15.115_18.005",
  "view_name": "all_pairs",
  "weighted": false,
  "centering": {
    "anchor": "all",
    "polarity_reference": "pc1_correlation",
    "polarity_anchor_view": "bi_baseline"
  },
  "n_samples": 226,
  "samples": ["S0001", ...],
  "n_markers": 3421,
  "markers": [
    {
      "marker": "C_gar_LG28_15234521_MAJOR_MINOR1_A_G",
      "chrom": "C_gar_LG28", "pos": 15234521,
      "role_a": "MAJOR", "role_b": "MINOR1",
      "allele_a": "A", "allele_b": "G",
      "n_alleles_obs": 3,
      "pair_count": 1834,
      "polarity_flipped": false,
      "dosage": [1.02, 0.05, 1.94, 1.01, ...],
      "dosage_centered": [-0.04, -1.01, 0.88, -0.05, ...]
    }
  ]
}
```

`dosage` is the per-sample posterior dosage of `allele_b`:
`E[copies of allele_b] = P_ab + 2 × P_bb` (continuous, not just 0/1/2).

`dosage_centered` is `dosage − mean(dosage[centering_subset])`.

Display-time transformations (centering anchor, z-scoring, color scale)
are applied client-side from these two arrays; the JSON carries the
canonical centered values plus the raw values for re-deriving alternative
centerings if needed.

For categorical genotype-state mode, an alternative JSON keyed per *site*
(not per pair):

```json
{
  "marker_site": "C_gar_LG28_15234521",
  "alleles_observed": ["A", "C", "G"],
  "n_alleles": 3,
  "states": ["AA", "AC", "AG", "AA", "CG", "GG", ...],
  "state_confidence": [0.99, 0.95, 0.91, ...]
}
```

Only emitted for tri+ allelic sites where genotype-state is meaningful.

---

## 10. The shared rendering state (NEW — atlas integration concept)

PCA and heatmap originate from the same dosage matrix. They should share
a coordinated rendering state so the two panels feel like views of one
object, not two unrelated plots.

```
            ┌────────────────────────────────────┐
            │  filtered + weighted Beagle        │
            │  for chosen view                    │
            └────────────┬───────────────────────┘
                         │
            ┌────────────▼───────────────────────┐
            │  Per-marker dosage matrix D         │
            │  (n_samples × n_markers, continuous)│
            │  + per-marker polarity              │
            │  + per-marker centering on chosen   │
            │    sample subset                    │
            └────────────┬───────────────────────┘
                         │
                ┌────────┴────────┐
                ▼                 ▼
       ┌──────────────┐    ┌─────────────────┐
       │ PCA reduction│    │ Heatmap (full D)│
       └──────┬───────┘    └────────┬────────┘
              │                     │
              │  ┌───────────────┐  │
              └─▶│ Shared state  │◀─┘
                 │ - sample_order│
                 │ - sample_color│
                 │ - hover_sample│
                 │ - hover_marker│
                 │ - selection   │
                 └───────────────┘
```

### 10.1 Shared state fields

| Field | Source / written by | Read by |
|---|---|---|
| `view_name` | UI dropdown | PCA, heatmap, both reload data |
| `weighting` | UI toggle | PCA, heatmap |
| `anchor_mode` | UI toggle | PCA only |
| `centering_anchor` | UI dropdown | PCA, heatmap |
| `polarity_reference` | UI control | PCA, heatmap |
| `sample_order` | derived from PCA scores or manual | heatmap row order |
| `sample_color_mode` | UI dropdown | both |
| `sample_colors` | derived from sample_color_mode | both |
| `marker_order` | UI control (genomic / clustering / loading) | heatmap col order |
| `hover_sample` | mouse over either panel | both highlight |
| `hover_marker` | mouse over heatmap | PCA highlights loading direction |
| `selected_samples` | click-drag in either panel | both highlight |
| `selected_markers` | click-drag in heatmap | PCA highlights direction |

### 10.2 Color modes (shared between PCA and heatmap)

| Mode | Color source | Variable type |
|---|---|---|
| `cluster` (default) | Current K-means / locked / anchor labels | Categorical |
| `mean_dosage_window` | Per-sample mean dosage in current window | Continuous |
| `pc1_score` | Per-sample PC1 in current window | Continuous |
| `pc2_score` | Per-sample PC2 in current window | Continuous |
| `tracked_group` | Manually-assigned tracking groups | Categorical |
| `external_annotation` | Loaded from TSV | Categorical |

Switching color mode does not recompute anything — render-time only.

### 10.3 Centering anchor (shared)

| Anchor | Centering subset for per-marker mean |
|---|---|
| `all` (default) | All n_samples |
| `het` | Samples in heterozygous-arrangement band (PC1 cluster ≈ middle) |
| `hom1` | Samples in major-arrangement homozygous band |
| `hom2` | Samples in minor-arrangement homozygous band |
| `custom` | User-specified sample list |

Same setting applied to both panels. Affects `dosage_centered` for
heatmap and per-marker centering before PCA covariance computation.

### 10.4 Polarity flipping (shared)

Per-marker sign decision. Reference options:

| Reference | Rule |
|---|---|
| `pc1_correlation` | flip if cor(dosage, PC1_anchor_view) < 0 |
| `band_membership` | flip if mean(dosage[hom2]) < mean(dosage[hom1]) |
| `fixed_sample` | flip if dosage[chosen_sample] < median(dosage) |
| `none` | no flipping |

Polarity is computed once based on a reference view (typically
`bi_baseline` PCA scores) and applied identically in PCA and heatmap.

### 10.5 Sample ordering (heatmap rows)

| Order | Rule |
|---|---|
| `pc1_anchor` (default) | Ascending PC1 score in the anchor view |
| `pc1_view` | Ascending PC1 in the current view |
| `cluster` | Group by cluster label |
| `manual` | User drag-reorder |
| `mean_dosage` | Ascending per-sample mean dosage in window |

PCA panel doesn't have a "sample order" per se — points are positioned
by PC scores. But hover linkage with the heatmap means heatmap row
position should be derivable from sample identity in O(1).

### 10.6 Marker ordering (heatmap columns)

| Order | Rule |
|---|---|
| `genomic` (default) | By chrom, pos |
| `pc1_loading` | Sort by absolute PC1 loading |
| `pc2_loading` | Sort by absolute PC2 loading |
| `clustering` | Hierarchical clustering on dosage similarity |

Genomic order is the visual default — preserves the spatial intuition of
the inversion interval.

---

## 11. Atlas Page-1 candidate mode UI

### 11.1 Triggering candidate mode

Page 1 already does whole-genome local PCA along the genome. Candidate
mode is a separate state activated when:
- User selects a candidate from a dropdown
- URL parameter `?candidate=LG28_15.115_18.005`
- Click-zoom into a candidate interval on the genome track

In candidate mode, the cursor traverses windows inside the candidate
interval only. Per-window data loaded from candidate-specific JSONs.

### 11.2 Top-level controls (single bar across PCA + heatmap)

```
┌─────────────────────────────────────────────────────────────────────┐
│ View: [all_pairs ▾]  Weight: [☑weighted]  Anchor: [bi_baseline ▾]   │
│ Centering: [all ▾]   Polarity: [pc1_corr ▾ from bi_baseline]        │
│ Color samples by: [cluster ▾]                                        │
└─────────────────────────────────────────────────────────────────────┘
```

These are the shared-state controls. Both panels respond.

### 11.3 PCA panel controls (panel-local)

```
┌──────────────────────────────────────────────┐
│ Axes: PC[1▾] × PC[2▾]                         │
│ Rotation: [─────●────────] 0°  [ Auto-align ] │
│ Sign flip: [☑ PC1] [☐ PC2]                    │
│ Show: [☑ trail] [☑ tracked] [☑ anchor]        │
└──────────────────────────────────────────────┘
```

### 11.4 Heatmap panel controls (panel-local)

```
┌──────────────────────────────────────────────┐
│ Sort rows: [pc1_anchor ▾]   Sort cols: [genomic ▾] │
│ Display mode: [centered ▾]  Color scale: [diverging] │
│ Mode: [dosage ▾ | genotype-state]                    │
└──────────────────────────────────────────────┘
```

### 11.5 Linkage interactions

- Hover sample in PCA → highlight row in heatmap, show sample ID and
  cluster
- Hover sample in heatmap → highlight point in PCA
- Hover marker in heatmap → show marker info (role pair, alleles, support)
  + draw arrow on PCA showing loading direction
- Click sample in either panel → add to tracked
- Click-drag in PCA → lasso select samples → highlight rows in heatmap
- Click-drag in heatmap col-axis → select marker range → highlight in
  PCA via summed loading direction

### 11.6 What this looks like across views

Switching the **View** dropdown reloads the PCA scores and heatmap data
but keeps:
- sample_order (samples in same row positions)
- sample_color (same colors)
- hover/selection state
- anchor_mode and centering settings

So switching from `bi_baseline` to `all_pairs` shouldn't reshape the
layout — points should move along the same axes (because of anchor mode),
heatmap rows stay in the same order, only column count changes (more
markers in `all_pairs`).

This is the "normal thing that works" — a single coordinated view of the
data with controls that change *what's shown* without scrambling
*how it's organized*.

---

## 11.5 Tree panel — inversion-core haplotype clades (NEW)

The third panel completes the inversion-confirmation triangle. PCA shows
clusters; heatmap shows dosage patterns; **tree shows whether clusters
are phylogenetic clades and what divergence pattern relates them**.

### Two complementary tree paths

| Path | Input | Method | Best at |
|---|---|---|---|
| **A: dXY/dA NJ** | Band-level summary stats from popstats | NJ on distance matrix | Group-level clade structure; ladder vs parallel |
| **B: SNP alignment** | Per-sample IUPAC-encoded SNP FASTA | IQ-TREE ML with GTR+ASC | Per-sample placement, branch lengths, bootstrap support |

Path A is fast (~seconds) and gives clean group-level clade
relationships using `region_popstats.c` and `region_stats_dispatcher.R`.
Path B is the **primary paper figure**: per-sample tree with leaves
colored by band, showing whether each band forms a coherent clade with
bootstrap support.

### Heterozygote handling

Path B forces a choice on how to encode 0/1 in a one-sequence-per-sample
FASTA. Spec supports four modes:

| Mode | 0/1 → | Use case |
|---|---|---|
| `iupac` (default) | R / Y / W / S / K / M | All samples included; primary paper tree |
| `hom_only` | (HETs excluded) | Cleanest haplotype tree; validation comparison |
| `n` | N | Sanity check |
| `random` | random REF/ALT | Pseudo-haplotype comparison |

**Default**: produce both `iupac` and `hom_only` trees. If their
topologies agree on the major splits, the IUPAC encoding isn't biasing
the result, and you can publish the full-sample tree confidently.

### Inputs
- Candidate interval + PCA band assignments (sample → band)
- Filtered Beagle for chosen view (`bi_baseline` for paper default)
- For Path A: `region_stats_dispatcher.R` to query band-pair dXY/dA

### Outputs (per candidate)

```
trees/<candidate_id>/
├── core_interval.tsv
├── path_A/
│   ├── band_tree_dXY.json   (NJ on dXY between bands)
│   └── band_tree_dA.json    (NJ on dA — corrects for within-clade π)
├── path_B/
│   ├── core.fa              (IUPAC FASTA per sample)
│   ├── core.snps.fa         (snp-sites cleaned)
│   ├── sample_tree.treefile (IQ-TREE Newick with bootstrap)
│   └── sample_tree.json     (atlas-ready with pre-computed layout)
├── path_B_hom_only/         (validation tree, HETs excluded)
├── concordance.json         (ARI / Cramér's V / purity, per tree path)
├── divergence_pattern.json  (ladder vs parallel via derived-allele sharing)
└── tree_manifest.json       (atlas index)
```

### Distinct contribution of Path A vs Path B

| Question | Tool |
|---|---|
| Are samples grouped into N clusters? | PCA |
| What dosage patterns characterize each cluster? | Heatmap |
| Is the band-level divergence pattern ladder, parallel, or scattered? | Tree Path A |
| Where does each individual sample fall? Are clades well-supported? | Tree Path B |

### Honest framing for the paper

Trees are a **regional haplotype-clade map over the inversion core**,
not a complete inversion phylogeny. Claims:

- "PCA bands form coherent clades" (concordance ARI/purity from Path B)
- "Bands diverged in parallel" / "consistent with stepwise divergence"
  (Path A topology + derived-allele sharing matrix)
- "Tree colored by relative dXY divergence to the standard arrangement"
  (NOT "age" without calibration)

### Atlas integration

Third panel below PCA + heatmap. Shares rendering state from Section
10.1 — same color scheme, same hover linkage, same view selection.

Tree-panel-local controls: tree distance metric (dXY | dA for Path A),
het_mode toggle (Path B), show band tree / sample tree / both, edge
coloring, sample-tree collapse-to-clade toggle.

Hover/click linkage:
- Hover sample in PCA → highlight leaf in tree
- Hover leaf in tree → highlight in PCA + heatmap
- Click clade in tree → select all clade samples → highlight everywhere
- Click branch in band tree → show split's stats (dXY, dA, n_samples)
- Click branch in sample tree → show bootstrap support, n_descendants

### Validation checks (LG28 control)

1. Path A band tree: HOM1↔HOM2 maximally divergent; HET intermediate
2. Path A dXY tree and dA tree have same topology (else family inflation)
3. Path B sample tree: ARI vs PCA bands > 0.7; bootstrap support on
   band-defining internal nodes ≥ 95
4. Path B `iupac` and `hom_only` trees: agree on >95% of HOM samples
5. Pattern label: LG28 60/106/60 → expect "parallel" or "ambiguous"

### Minimum first-pass implementation for paper

- **Phase 1 (1-2 days)**: Path A only. Single `get_region_stats()` call
  + `ape::nj()` + static PDF. Sufficient for group-level clade figure.
- **Phase 2 (2-3 days)**: Path B. Beagle → IUPAC FASTA → snp-sites →
  IQ-TREE GTR+ASC. Static PDF with leaves colored by band.

Phases 1+2 alone (no atlas integration) deliver the paper figure in
~5 days.

---

## 11.6 Fragment fingerprinter — regime detection and recombinant tracts (NEW)

The fingerprinter is the **architecture diagnostic**. PCA/heatmap/tree
all assume the candidate is one coherent block; the fingerprinter tests
that assumption.

### What it answers

| Question | Tool |
|---|---|
| How are samples clustered overall? | PCA |
| What dosage patterns characterize each cluster? | Heatmap |
| Are clusters phylogenetic clades? | Tree |
| **Does the diversity pattern stay the same across the candidate, or switch in places?** | **Fingerprinter** |
| **Is this one inversion, two adjacent inversions, or one inversion with a recombinant tract?** | **Fingerprinter** |

### The four scenarios it discriminates

Per-window diversity-profile vector:
`[π_per_band, dXY/dA/Fst pairwise, Tajima_D, rare/singleton fractions, age_proxy_per_band_pair]`
~25 features for a 3-band candidate. The age proxy is `dA / (2*μ)`,
reported with explicit μ assumption (default 1e-9).

Think of the candidate as a path of fragments:
`Fragment A → Fragment B → (boundary) → Fragment B' → Fragment A'`.
The four scenarios:

| Pattern | Verdict |
|---|---|
| All fragments same fingerprint | `stable_inversion` |
| Outer match, middle differs, fingerprint **returns** | `one_inversion_with_recombinant_tract` (double crossover) |
| Two halves with different fingerprints, no return | `two_adjacent_inversions` (consider splitting) |
| A-B-B'-A' symmetric repeats: fp(A)≈fp(A') AND fp(B)≈fp(B') | `nested_rearrangement` |

### Three analysis stages

- **Stage 2 — rank-based regime equivalence**: do two windows have the
  same ranking of (π, dXY, Fst)? Discrete same/different decision.
- **Stage 2.5 — fragment-pair similarity matrix**: N×N matrix of
  fragment-vs-fragment similarity, combining cosine similarity on
  z-scored profiles, rank equivalence, and age-proxy compatibility.
  **This is the test for the A-B-B'-A' signature** — symmetric repeat
  pairs with similar age proxies are the diagnostic.
- **Stage 3 — clustering + switch detection**: continuous (Method A,
  hierarchical Ward.D2) and discrete (Method B, rank equivalence)
  regime IDs per window; walk genomic order to detect return switches
  (double-crossover signature) and terminal switches (adjacent
  inversion boundary).

### Fragment definition (NOT a fixed size)

Fragments are emergent from regime boundaries, not chosen a priori.
A run of consecutive same-regime windows is one fragment. Sizes range
from 1 window (50 kb at default settings) to the full candidate.

This contrasts with the *Drosophila subobscura* pattern (named
fragments at molecularly mapped breakpoints like 58D|59A, 64B|64C):
those analyses are *known-breakpoint comparisons*. Our setting is
*discovery* — regime boundaries serve as the analogous fragmentation,
and Stage 2.5 can be re-run with named fragments once breakpoint maps
are available from long-read assembly.

### Reliability tiers

Each fragment is annotated with a reliability tier based on its total
SNP count:

| Tier | SNPs | Trustworthy stats |
|---|---|---|
| `high` | ≥ 500 | All (π, dXY, dA, Fst, Tajima_D, fractions, age proxy) |
| `medium` | 100-499 | π, dXY, dA, age proxy; Fst marginal; Tajima_D and fractions flagged |
| `low` | 50-99 | dXY only; downweighted in similarity matrix |
| `unreliable` | < 50 | Excluded from similarity matrix |

Fingerprint similarity uses only features both fragments support
reliably; for low-tier fragments, comparison falls back to dXY-only
cosine similarity. Default minimum-SNP thresholds are configurable.

### Why age is one component, not the whole evidence

Same fingerprint + similar age = strong support.
Same age only = weak (chance similar divergence).
Same fingerprint, different age = recombination/selection/rate variation.
Different fingerprint, same age = probably not the same block.

So Stage 2.5's combined score weights cosine similarity (0.5),
rank equivalence (0.3), and age compatibility (0.2). Tunable.

### Per-sample recombinant carrier identification

For each return-switch tract, compare per-sample state assignment outside
vs inside the tract. Samples whose state differs are the **recombinant
carriers**. Output as a per-sample mask used by HANDOFF 5 (tree) as
`--exclude_samples` for the clean-core tree.

### Inputs

- Band assignments (from HANDOFF 1's PCA)
- Beagle for the chromosome (biallelic baseline; or `all_pairs` from
  HANDOFF 1 for multi-allelic-aware fingerprints)
- Candidate interval

### Outputs

```
fingerprints/<candidate_id>/
├── window_profiles.tsv             # raw and z-scored, incl. age proxies
├── ranking_signatures.tsv          # per-window pi/dXY/Fst ranks (Method B)
├── regime_assignments.tsv          # method A and B regime IDs
├── fragment_similarity_matrix.tsv  # Stage 2.5 N×N fingerprint similarity
├── symmetric_repeat_pairs.tsv      # Stage 2.5 matched A↔A' / B↔B' pairs
├── switches.tsv                    # detected regime switches
├── recombinant_carriers.tsv        # per-sample recombinant flags
└── fingerprint.json                # everything for atlas
```

### Atlas integration

Fingerprint **track** above the heatmap panel (not a separate full
panel). Hover a switch → highlight recombinant carriers in PCA + heatmap
+ tree (shared rendering state from Section 10.1).

### Expected performance (honest calibration)

The fingerprinter summarizes the recombination landscape of an
inversion candidate. Its reliability depends on signal strength.

**Will work**: stable inversion (single regime), two adjacent inversions
with distinct band assignments (terminal switch, no return), obvious
double crossover with a sizable carrier set (return switch). These are
the "two different bands along the genome" cases.

**Probably work, with care**: small-carrier-set recombinant tracts
(1-3 samples — Stage 4 per-sample painting more reliable than Stage 3
regime detection here), slight nested rearrangements, moderate
within-arrangement diversity.

**Honestly uncertain**: A-B-B'-A' nested mosaic with subtle
fingerprint differences (matrix may not show clean off-diagonal
blocks), very old inversions with homogenized diversity, severe
hatchery family inflation (regimes become family-driven), very small
inversions (<200 kb at default windows).

**Use as first-pass diagnostic, not final arbiter**. Output should be
cross-checked against per-sample heatmap (HANDOFF 1) and tree
(HANDOFF 5). The most robust output is the per-sample recombinant
carrier list (Stage 4), because it's based on per-sample dosage state
directly rather than on cohort-level statistics.

### Why this matters

For hatchery cohorts with possible double crossovers in the middle of
inversions, the regime track + recombinant carrier list lets you make
the strong paper claim:

> "Window-level diversity profiles supported a single regime across 95%
> of the candidate (114/116 windows; 2 windows showed a putative
> recombinant tract carried by 3 individuals)."

Stronger than "PCA shows three bands." But only when the signal
actually supports the claim — see HANDOFF 6's "Honest expected
performance" section for case-by-case calibration.

### Minimum first-pass implementation

- **Phase 1 (1-2 days)**: profiles + clustering + switch detection
- **Phase 2.5 (1 day)**: fragment similarity matrix + age-proxy +
  A-B-B'-A' detection
- **Phase 3 (1-2 days)**: per-sample carrier identification

Phases 1+2.5+3 (~5 days) deliver the headline diagnostic — regime
track, fragment similarity matrix, and recombinant carrier list —
without atlas integration.

---

## 11.7 Nested inversion detection (NEW)

The fingerprinter (11.6) detects regime *transitions along the genome*
(the inversion changes through space). The nested-inversion detector
asks a different question: **does the candidate contain a second,
independent karyotype axis nested inside it?**

### The conceptual core

A normal inversion gives one large coherent haplotype block.
A nested inversion gives a large block, plus a second independent
split among carriers — visible only when the parent karyotype is
controlled for.

The diagnostic rule:

> **A true nested inversion appears within one parent arrangement
> background, not just when all samples are mixed.**

### The three primary methods

- **Method 1 — conditional local PCA per stratum**: stratify samples
  by parent karyotype (HOM1 / HET / HOM2) and re-run windowed local PCA
  on *only* each stratum's samples. Look for emergent 3-band structure
  on PC1-PC5 within a stratum.
- **Method 8 — multi-PC scan**: nested signals often hide on PC2-PC3
  rather than PC1 (PC1 of the stratum is usually population structure
  or family LD; the nested arrangement is the next-strongest axis).
- **Method 9 — peel filter**: re-run analysis after dropping one
  parent stratum. A real nested inversion persists when relevant
  samples remain; family LD typically does not.

Plus 4 secondary cross-validation methods (residualization,
conditional Cramér's V, hierarchical clustering, AF contrast within
strata) and integration with HANDOFFs 5 (tree within stratum) and 6
(boundary recurrence vs. DCO disambiguation).

### Distinct contribution

| Question | Tool |
|---|---|
| How are samples clustered overall? | PCA |
| What dosage patterns characterize each cluster? | Heatmap |
| Are clusters phylogenetic clades? | Tree (HANDOFF 5) |
| Does the diversity pattern switch along the genome? | Fingerprinter (HANDOFF 6) |
| **Is there a second karyotype axis nested inside this candidate?** | **Nested detector (HANDOFF 7)** |

### Classification

Each candidate gets one of:
- `simple_inversion`
- `nested_inversion_strong` (3 primary methods agree, plus secondary)
- `nested_inversion_likely` (2 primary methods agree)
- `family_LD_artifact_candidate` (signal disappears under peel filter)
- `hidden_pc3_signal_inspect` (signal only on PC3+)
- `shared_recombinant_haplotype` (boundaries shared but no within-
  stratum 3-band)
- `complex_inspect_manually`

### Use case: hatchery cohorts with possible internal arrangements

For your *C. gariepinus* cohort, the peel filter is the critical
component — hatchery family structure can produce internal-block
signals that look like nested inversions. The peel filter discriminates
(real nested signal persists across relevant peels; family LD
typically does not).

### Minimum first-pass implementation

- **Phase 1+2 (3-4 days)**: Method 1 (conditional PCA) + Method 9
  (peel filter). The headline diagnostic; sufficient for paper claims
  in clean cases.
- **Phase 3 (2-3 days)**: secondary methods for cross-validation.
- **Phases 4-5 (2-3 days)**: classification logic + visualization.

Phases 1+2 alone deliver the strongest method and are sufficient for
LG28-style validation (where the expected verdict is `simple_inversion`
— a negative-control test of the pipeline).

---

## 11.8 Adaptive interval dosage clustering (NEW)

A self-defining visualization tool: cluster samples by their
dosage-profile shape across an interval, with adaptive K selection from
the data. Produces Stickleback Fig. 2-style curves where curves are
**defined by the data itself**, not by population labels or PCA bands.

### What it is

For each scope (per-chromosome or per-candidate), build a samples ×
windows dosage matrix, select K adaptively (smallest stable K from
silhouette + bootstrap stability + min cluster size + spatial
coherence), and produce per-cluster mean/median dosage curves across
the interval.

The curve plot directly shows dosage-cluster shapes — a simple
inversion gives 3 horizontally-flat curves at low/mid/high dosage; a
nested arrangement gives 5-6 curves with shape variation in the
nested region.

### Distinct contribution

| Question | Tool |
|---|---|
| What's the population structure? | PCA |
| What dosage patterns make up each cluster? | Heatmap |
| Are clusters phylogenetic clades? | Tree (HANDOFF 5) |
| Does the diversity pattern switch along the genome? | Fingerprinter (HANDOFF 6) |
| Is there a second karyotype axis nested? | Nested detector (HANDOFF 7) |
| **What does the dosage landscape itself look like, with no K=3 assumption?** | **Adaptive dosage clustering (HANDOFF 8)** |

### Two scopes

- **Per-chromosome**: large windows (~10k SNPs), Stickleback-style
  multi-panel summary across all chromosomes; identifies inversion-
  candidate intervals as regions of dosage-curve divergence
- **Per-candidate**: small windows (~50 kb), adaptive K typically 3
  for simple inversions or 5-6 for nested/compound; with hierarchical
  refinement, reveals nested architecture

### Why adaptive K matters

PCA implicitly forces K=3. Dosage clustering with K_max=6 + decision
rule "smallest stable K" lets the data speak: K=1 (no structure) /
K=2 (biallelic two-arrangement) / K=3 (simple inversion) / K=5-6
(compound/nested) emerge from the data without imposing prior
expectations.

### Concordance with PCA bands as the diagnostic

After dosage clustering, compute ARI / Cramér's V against PCA bands.
- ARI > 0.8: agreement → simple structure both methods see
- ARI 0.5-0.8: partial → finer structure in dosage; investigate
- ARI < 0.5: disagreement → trust the disagreement; cross-reference
  with HANDOFFs 6, 7

### Output

```
dosage_clustering/<scope>/<id>/
├── dosage_matrix_*.tsv              (mean and median window dosage)
├── adaptive_K_selection.tsv          (per-K silhouette/stability/etc.)
├── cluster_assignments.tsv
├── hierarchy.json                    (recursive refinement tree)
├── per_cluster_curves.tsv
├── concordance_with_PCA.json
├── classification.json
└── plot_panel_A_curves.pdf           (paper figure)
```

### Minimum first-pass implementation

- **Phase 1+2 (2-3 days)**: dosage matrix + adaptive K. Output curves.
- **Phase 4+5 (2-3 days)**: concordance + visualization (panels A-D).
- **Phase 3 (optional, 1 day)**: hierarchical refinement for nested
  detection.

Phases 1+2+4+5 (4-5 days) deliver the headline output — adaptive
curves, concordance, publication figure — without hierarchical
refinement.

### Polarity-correction modes (added)

The dosage matrix has a per-marker polarity issue: each Beagle marker's
direction (which allele is "b") is set by cohort-count ranking but is
not aligned with any biological axis. Four polarity modes available:

- `raw_scan`: no correction, use absolute Pearson correlation for
  similarity. First-pass discovery.
- `polarity_corrected_outer`: flip markers to align with the major
  outer contrast. Cleanest plots for simple inversions.
- `polarity_corrected_inner`: flip markers to align with the inner
  contrast within one outer stratum. Implementation has open questions
  noted in HANDOFF 8 Stage 1.5.
- `hierarchical_u_v`: two-axis correction; markers assigned to outer
  (u) or inner (v) axis based on which contrast they correlate with.
  Publication-grade for nested cases. Open implementation questions
  noted in HANDOFF 8 Stage 1.5.

The pipeline runs `raw_scan` always, others conditionally as upstream
analysis confirms the existence of outer / inner reference groups.
This is a deliberate guard against using inner-group definitions to
manufacture a clean nested signal before independent confirmation.

### Synchronized scrubbing with HANDOFF 10 (atlas mode)

When run in atlas mode, the dosage curves and the similarity matrix
panel share a genome cursor and a scale-suggestion track that hints
when to switch scale (100 kb / 250 kb / 500 kb / 1 Mb) at the current
position. See HANDOFF 8 Stage 7.5 and HANDOFF 10 Stage 7.5 for the
shared design.

### Pairwise cluster contrast and driver segments (added)

After clusters are identified (Stages 3-5), pairwise contrast curves
identify *which genomic interval separates each cluster pair*. For
clusters A and B, the contrast curve `Δ_AB(x) = mean_A(x) - mean_B(x)`
spikes where they differ; the shape of this spike tells the
architecture:

- **High across whole interval** → outer arrangement difference
- **High only in middle** → inner / nested segment difference
- **High only at edge** → boundary or adjacent event
- **Weak everywhere** → not a real cluster separation

For K clusters, all K(K-1)/2 pairwise contrast curves form a matrix
that directly reveals architecture: outer pairs show wide contrasts;
inner pairs show narrow contrasts; mixed pairs show both. Driver
segments (contiguous high-effect regions) are validated by leave-
segment-out re-clustering: if removing the suspected driver makes the
cluster disappear, the driver is confirmed.

This is the **mechanistic interpretation step** that turns "K
clusters exist" into "the architecture is outer K=3 with inner K=2
nested inside cluster C3 at 16.4-16.7 Mb." See HANDOFF 8 Stage 5.5
for the full method, and HANDOFF 10 Stage 9.5 for the live UI version
where the user clicks block pairs to see contrasts in real time.

### Per-candidate and genome-wide architecture summaries (added)

After per-candidate driver-segment identification, two roll-up
reports answer cohort-level questions:

- **Per-candidate inner-interval table**: for each candidate, lists
  the nested intervals found (with coordinates, widths, parent
  cluster), how many there are, and what percentage of the candidate
  is nested
- **Genome-wide architecture summary**: counts simple vs nested
  candidates across the cohort, distribution of inner-interval counts
  per candidate, median sizes, and the manuscript-grade "X% of
  inversions are nested" number

Multi-event detection (e.g., two nested inversions inside one outer
candidate) is supported automatically: the smoothed-effect contiguous-
runs approach in Stage 5.5c returns multiple driver segments when
there are multiple spikes, and Stage 5.5h tallies them. No KDE / mode-
finding is used — the smoothed effect-size curve already provides the
detection; second-order density estimation on noisy curves would just
add unreliability. See HANDOFF 8 Stage 5.5h.

---

## 11.9 Dosage similarity matrix + outer/inner block separation (NEW)

The population-level diagnostic for nested architecture: per-window
**catfish × catfish similarity matrices** computed across a candidate
inversion plus modest flanks, with block detection and contingency-
table tests for asymmetric subdivision.

### What it answers

> At the single-fish level, a nested inversion looks normal — each
> catfish carries just two haplotypes. The nested architecture only
> emerges when many catfish are compared together as
> dosage-defined haplotype groups.

This handoff implements that population-level view directly.

### Scope: candidate + flanks, NOT whole genome

For each candidate, run on extended interval = candidate ± flanks
(default 20% of candidate width, capped 1 Mb). Flanks provide:
- Reference baseline (no-structure null)
- Boundary refinement (similarity transitions are sharper than PCA-
  based candidate boundaries)
- Honest comparison region from the same chromosome neighborhood

Independent runs per candidate. Adjacent-inversion detection is
HANDOFF 6's job (genome-wide regime scanner).

### The headline diagnostic: contingency-table asymmetry

Compare block assignments between an outer-only window and an
inner-region window. Three patterns:

| Pattern | Verdict |
|---|---|
| One outer block subdivides; others stay intact | **Nested inversion** |
| All outer blocks subdivide simultaneously | Two adjacent inversions |
| Subdivision crosses outer block assignments | Independent overlapping event (could be ancestry/family LD) |

The asymmetric subdivision (one outer block contains the inner event;
others don't) is the unambiguous nesting signature.

### How HANDOFF 9 differs from HANDOFFs 7 and 8

| Method | Angle |
|---|---|
| HANDOFF 7 | Top-down: stratify by parent karyotype, re-run PCA per stratum |
| HANDOFF 8 | Sample-shape: cluster sample dosage profile vectors |
| **HANDOFF 9** | **Pairwise: who does each fish pair with at each window?** |

Same biology, three independent angles. They cross-validate.

### Naming: avoid "IBD" until phased data is available

True IBD = inherited from common ancestor. We compute **dosage
similarity** (Pearson correlation of per-marker dosage vectors), which
captures haplotype sharing without claiming inheritance. In hatchery
cohorts, true IBD is genuinely confounded with family structure;
dosage similarity is the more honest term.

### Three-output pipeline

1. Per-window similarity matrix (n_samples × n_samples per window)
2. Per-window block detection via hierarchical clustering with
   adaptive K cut + silhouette filter
3. Block-transition track + boundary identification (outer left/right,
   inner left/right)
4. Contingency-table test → three-way classification

Plus visualization: 4-panel paper figure (similarity-matrix mosaic,
block-transition track, per-block dosage curves, contingency heatmap).

### Cross-validation integration (Stage 7)

A confident `nested_inversion` requires ≥3 of 5 methods agreeing
(HANDOFFs 5, 6, 7, 8, 9). When fewer methods agree, the verdict is
"weak; inspect manually."

### Minimum first-pass implementation

- **Phase 1+2+3 (4-6 days)**: similarity matrices + block detection +
  contingency test. Headline classification + paper figure.
- **Phase 4 (0.5-1 day)**: cross-validation integration with HANDOFFs
  5-8.
- **Phase 5 (1-2 days)**: visualization polish.

Phases 1+2+3 alone deliver a publishable per-candidate analysis
without atlas integration.

---

## 11.10 Interactive scrubbable similarity matrix panel (NEW)

The atlas-side companion to HANDOFF 9's static analysis: a scrollable
per-chromosome **catfish × catfish dosage similarity matrix** that
updates in real time as the user scrubs the genome cursor. The
visualization complement that lets users see nested architecture
form, dissolve, and reform as they scroll across a candidate.

### Distinct contribution

| Tool | What it produces |
|---|---|
| HANDOFF 9 | Per-candidate static analysis + classification + paper figure |
| **HANDOFF 10** | **Interactive atlas panel for live exploration** |

Same math (Pearson correlation of dosage vectors per window), same
block-detection logic. Different deliverable: live exploration vs.
publication artifact.

### Key design choice: client-side computation

For real-time scrubbing without server round-trip latency, similarity
matrices compute on demand in the browser. Per chromosome, the server
ships ~11 MB of dosage data as a binary blob; the client holds it in
typed arrays and computes per-window similarity in ~50 ms when the
scrubber moves.

Pre-computing all (window × scale) combinations would cost ~10 GB per
chromosome (rejected). Computing server-side per request would add
network latency (rejected). Client-side fits in browser memory and
gives sub-perception response times.

### User-controllable parameters

| Parameter | Options |
|---|---|
| Scale | 100 kb / 250 kb / 500 kb / 1 Mb |
| Sample subset | Lasso in PCA panel, click on matrix axes, TSV upload |
| Genome position | Drag cursor / keyboard arrows / click on position track |
| Block detection overlay | Toggle on/off; auto-detects K_blocks per window |
| Chromosome | Dropdown selector |

### Live-feedback workflow (the exploration story)

1. User selects chromosome → 11 MB fetch (~1 s)
2. Cursor at chromosome start → matrix shows uniform low values
   (no structure)
3. Cursor scrolls into a candidate inversion → matrix forms 3 blocks
4. Cursor scrolls inside an inner-event subregion → one block
   subdivides; status line shows K_blocks: 4
5. Cursor scrolls past inner region → returns to 3 blocks
6. Cursor scrolls past candidate → matrix dissolves to flank
   baseline

This makes nested architecture **visible by eye in seconds** —
the algorithmic confirmation comes from HANDOFFs 7, 9.

### Cross-panel coordination

Plugs into HANDOFF 2's shared rendering state. The genome cursor
position propagates from any panel to all others; selected_samples
(from lasso, click, or upload) propagates everywhere; hover linkage
shows the same sample highlighted in PCA, heatmap, similarity matrix,
and tree simultaneously.

### Minimum first-pass implementation

- **Phase 1+2+5 (4-5 days)**: data preprocessing + client loading +
  matrix rendering. Sufficient for a static-cursor demo.
- **Phase 3+6 (3-5 days)**: real-time computation + scrubber controls.
  Delivers the interactive feature.
- **Phase 4+7 (2-3 days)**: block detection overlay + cross-panel
  coordination.
- **Phase 8 (1-2 days)**: polish.

Total ~10-12 days for full feature. Phases 1-3+5+6 deliver the core
scrubbable matrix; subsequent phases add polish and integration.

### Polarity modes and synchronized scrubbing (added)

The panel supports the same four polarity modes as HANDOFF 8 Stage 1.5
(`raw_scan`, `polarity_corrected_outer`, `polarity_corrected_inner`,
`hierarchical_u_v`). Switching modes invalidates the matrix cache and
recomputes the current window's matrix (~50 ms). Modes 2-4 are gated
behind reference-group definitions (PCA bands, lasso, or TSV upload).

A scale-suggestion track sits between the panel's matrix and HANDOFF
8's dosage curves, showing per-scale block-count × silhouette across
the chromosome. Lets the user click directly on (scale, position) to
jump there. The cursor is shared between both panels via the existing
shared rendering state. See HANDOFF 10 Stage 7.5.

### Pairwise contrast overlay (added)

When blocks are detected on the matrix, the user can click two block
IDs to compute and display their pairwise dosage contrast curve in
real time, with driver segments highlighted. Lets the user explore
"which genomic interval separates these two clusters?" interactively.
Same math as HANDOFF 8 Stage 5.5, but on-demand for the current
view. The K × K full contrast matrix can also be rendered live as a
sparkline grid. See HANDOFF 10 Stage 9.5.

---

## 12. Validation checks (run on real data first)

For LG28:15.115-18.005, before trusting any view:

1. **`bi_baseline` matches existing biallelic pipeline.** PC1/PC2 shapes
   should be near-identical. Convention is by-cohort-count; existing
   pipeline may differ slightly.
2. **Unweighted vs weighted `all_pairs`.** Close → row-count inflation
   isn't driver. Different → weighting matters.
3. **`tri_extras` reproduces structure seen in `all_pairs` but not
   `bi_baseline`.** Yes → multi-allelic doing real work.
4. **Rare-pair scanner output matches biology.** Should not flag the
   60/106/60 main inversion body; should flag elsewhere.
5. **Dosage heatmap consistency across pair sets.** A sample HOM1 in
   `bi_baseline` should not flip to HOM2 in `all_pairs` unless polarity
   is documented.
6. **F = 1 - obs_het/exp_het** at LG28 inversion sites should be
   systematically positive (heterozygote deficit).
7. **Anchor 1 vs Anchor 2 for `tri_extras`.** Anchor 1 says where extras
   place samples on biallelic axes; Anchor 2 says where MINOR1_MINOR2
   places samples on MAJOR_MINOR2 axes. Both should give *some* structure
   if the multi-allelic information is real.

---

## 13. File map

```
mgl_adapter/
├── README.md                         (overview)
├── SLURM_A05_glf10_interval.sh       (ANGSD per candidate)         ✅
├── mgl10_to_beagle.R                 (master adapter)                ✅
├── beagle_filter_pairs.R             (filter)                        ✅
├── beagle_weight_by_support.R        (weighter)                      ✅
├── scan_rare_pairs.R                 (rare-pair scanner)             ✅
├── run_pair_pca_matrix.sh            (driver)                        ✅
├── make_test_data.R                  (synthetic test)                ✅
└── specs/
    ├── SPEC_0_master.md              (this document)
    ├── HANDOFF_1_producer.md         (PCA + heatmap producer build)
    ├── HANDOFF_2_atlas_ui.md         (Page-1 candidate mode UI)
    ├── HANDOFF_3_validation.md       (real-data validation checks)
    ├── HANDOFF_4_caching_custom.md   (custom user views + cache backend)
    ├── HANDOFF_5_tree.md             (inversion-core haplotype tree)
    ├── HANDOFF_6_fingerprinter.md    (regime detection + recombinant tracts)
    ├── HANDOFF_7_nested_inversion.md (nested inversion via conditional re-scanning)
    ├── HANDOFF_8_dosage_clustering.md (adaptive dosage-profile clustering)
    ├── HANDOFF_9_dosage_similarity.md (dosage similarity matrix + outer/inner block separation)
    └── HANDOFF_10_atlas_similarity.md (interactive scrubbable similarity matrix panel)
```

Tree integrates with existing infrastructure (`region_popstats.c`,
`region_stats_dispatcher.R`) — see HANDOFF 5.

Fingerprinter uses the same infrastructure but in windowed mode — see
HANDOFF 6. Architecture diagnostic; output feeds into HANDOFF 5 for
clean-core sample exclusion.

Nested inversion detector consumes HANDOFF 1's parent karyotype labels
and re-runs local PCA / Cramér's V / sample clustering within each
parent stratum. Optionally invokes HANDOFF 5 within stratum for tree-
based confirmation. See HANDOFF 7.

Adaptive dosage clustering provides a data-defined visualization that
doesn't assume K=3. Per-chromosome and per-candidate curves complement
PCA bands as cross-validation. See HANDOFF 8.

Dosage similarity matrix runs per candidate plus modest flanks,
computing per-window catfish × catfish similarity matrices, detecting
block structure, and classifying via contingency-table asymmetry. See
HANDOFF 9.

Interactive similarity matrix panel is the atlas UI version of HANDOFF
9: scrollable per-chromosome matrix with real-time updates as user
scrubs cursor. Configurable scale (100 kb to 1 Mb), sample subsetting
via lasso/click/upload, optional block-detection overlay. Same math
as HANDOFF 9, different deliverable. See HANDOFF 10.

---

## 14. Open decisions deferred

- Window size default for candidate mode: 50 kb is a reasonable starting
  point; needs empirical tuning on real LG28 data.
- Whether the producer also emits the genotype-state JSON for tri+
  allelic sites. Initial pass: yes, only at sites with `n_alleles_obs ≥ 3`.
- HWE per-pair statistics. **Decision: not in this layer.** PCAngsd
  handles HWE; weighting handles support.
- Custom-view caching backend (HANDOFF_4): R script + filesystem cache vs
  serverless API endpoint. Decision likely depends on atlas hosting model.
