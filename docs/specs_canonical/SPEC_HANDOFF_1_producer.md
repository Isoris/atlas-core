# HANDOFF 1 — PCA + heatmap producer

**Goal**: write the script(s) that turn the multi-allelic Beagles into
per-window PCA JSONs and per-marker heatmap JSONs that the atlas Page-1
candidate mode will load.

**Status**: not started. All inputs exist (the mgl_adapter pipeline is
done and tested). No producer script yet.

**Audience for this handoff**: a fresh chat where Claude needs to build
the producer. Quentin already understands the architecture; this doc gets
the new chat oriented quickly.

---

## What you're building

Two output files per (view, weighting, anchor_mode) combination:

```
pca_<view>_<weighting>_<anchor_mode>.json   ← per-window PCA scores
heatmap_<view>_<weighting>_<centering>.json ← per-marker dosages
```

Plus genotype-state JSONs for tri+ allelic sites (optional first pass).

Inputs come from the existing `mgl_adapter` pipeline:
- `master_all_pairs.beagle.gz` + sidecar (from `mgl10_to_beagle.R`)
- Per-view filtered Beagles (from `beagle_filter_pairs.R`)
- Per-view weighted Beagles (from `beagle_weight_by_support.R`)
- A bamlist / sample list

---

## Background you need (from SPEC_0)

### The convention
Per site, alleles ranked by total cohort read count: MAJOR, MINOR1,
MINOR2 (tri+), MINOR3 (quad). Pairs are unordered combinations; one
Beagle row per pair. Marker name format:
```
<chrom>_<pos>_<ROLE_a>_<ROLE_b>_<allele_a>_<allele_b>
```

### The four canonical views
- `bi_baseline`: only `MAJOR_MINOR1` rows (biallelic-equivalent)
- `tri_extras`: `MAJOR_MINOR2` + `MINOR1_MINOR2`
- `quad_extras`: all MINOR2/MINOR3 pairs
- `all_pairs`: everything

Each has unweighted and weighted variants. Eight Beagles total per
candidate.

### The dosage primitive
For each Beagle row (a pair), per individual:
```
dosage_b = P(Aa) + 2*P(aa)   # expected count of allele_b (the rarer / MINOR side)
```
Continuous in [0, 2]. This is the per-sample, per-pair dosage. Both PCA
and heatmap consume it.

---

## Task 1: per-window PCA scores

### Inputs
- `<view>.beagle.gz` (or `.weighted.beagle.gz`) for the view being
  processed
- `<view>.beagle.pairs.tsv` sidecar
- `bi_baseline.beagle.gz` + sidecar (always needed for Anchor 1)
- Window definition: bp_span (default 50 kb, configurable) or n_pairs
- Sample list (n_samples)

### Per-window math

For window w spanning [start, end]:

1. **Subset to in-window pair-rows**: filter sidecar by `chrom == w.chrom
   && pos >= w.start && pos < w.end`. Get list of `markers_in_window`.

2. **Build dosage matrix** `X` (n_samples × n_markers_in_window):
   For each in-window pair-row, parse the 3 GLs per individual from the
   Beagle line, compute dosage. Stack as columns of X.

3. **Polarity flip per marker** (see Section 10.4 of SPEC_0): based on
   chosen polarity reference. For first pass, use `pc1_correlation`
   anchored on bi_baseline:
   - For markers in bi_baseline view, polarity is the canonical reference.
   - For markers in other views, flip if `cor(dosage, anchor_PC1) < 0`.
   - Track which markers were flipped in metadata.

4. **Center per marker** based on centering anchor. Default `all`:
   `X_centered[:, m] = X[:, m] - mean(X[:, m])`. Other anchors subset
   the rows used for the mean.

5. **Compute eigenvectors per anchor mode**:

   - **Anchor 1 (bi_baseline)**: Run PCA on bi_baseline rows in this
     window. Compute X_bi (n_samples × n_markers_bi_in_window),
     centered. Sample-sample covariance:
     ```
     C_bi = X_bi @ X_bi.T / n_markers_bi
     V_bi, lam_bi = eigen(C_bi)  # take top 2
     ```
     For the current view, project its data through V_bi:
     ```
     C_view = X_view @ X_view.T / n_markers_view
     pc_scores = C_view @ V_bi[:, :2]   # n_samples × 2
     # Eigenvalues for this view in the bi_baseline basis:
     lam_view_in_bi = sum(V_bi.T @ C_view @ V_bi, diagonal)
     ```
     Practically: PC scores in the bi_baseline basis are the columns of
     V_bi multiplied by appropriate eigenvalues. The bi_baseline view's
     `pc1`, `pc2` arrays are V_bi[:, 0] * sqrt(lam_bi[0]),
     V_bi[:, 1] * sqrt(lam_bi[1]). Other views: project through V_bi.

   - **Anchor 2 (view_self)**: For views without `MAJOR_MINOR1`, use the
     lowest-rank biallelic-equivalent pair available:
     - `bi_baseline` → `MAJOR_MINOR1` (= Anchor 1, same result)
     - `tri_extras` → `MAJOR_MINOR2`
     - `quad_extras` → `MAJOR_MINOR2` (lowest available)
     - `all_pairs` → `MAJOR_MINOR1` (= Anchor 1)
     Compute V_self from those rows; project view's data through V_self.

   - **Anchor `none`**: standard PCA on the view's own data.
     `V_view, lam_view = eigen(X_view @ X_view.T / n_markers_view)`.

6. **Sign convention**: apply deterministic sign rule on V (PC1 sign:
   +1 if mean of V[anchor_sample_idx, 0] >= 0). Match the existing
   `pca_panel.js` rule (look at `_data.js` once available; for now
   default to +1 sign on PC1 = sample at +PC1 end is sample with median
   ID or lowest sample number, whatever's standard).

7. **Emit window JSON** (Section 8 of SPEC_0):
   ```json
   {
     "idx": w_idx,
     "start": ..., "end": ...,
     "n_pair_rows": n_markers_in_window,
     "n_unique_sites": uniqueN(pos),
     "n_biallelic_sites": ..., "n_triallelic_sites": ..., "n_quadallelic_sites": ...,
     "lam1": lam[0], "lam2": lam[1],
     "pc1": [...], "pc2": [...],
     "mean_pair_count": ..., "median_pair_count": ...,
     "polarity_flips_applied": ...
   }
   ```
   For `--anchor_mode both`: include `pc1_self`, `pc2_self`,
   `lam1_self`, `lam2_self` alongside.

### Implementation notes

- **Direct eigendecomposition, not PCAngsd.** The PCAngsd HWE iteration
  is overkill at this scale; per-window R `eigen()` on a 226×226
  symmetric matrix is sub-millisecond.
- For 3 Mb candidate at 50 kb windows = 60 windows × (filter + dosage
  matrix build + eigen + project) = a few seconds total.
- **GL parsing**: the Beagle is gzipped TSV with 3 GLs per individual
  per row, in linear scale, summing to 1. Parse with `data.table::fread`
  or a custom reader for memory efficiency on large files.
- **Polarity is global per marker**, computed once across all windows
  containing that marker. So the polarity decision uses pooled cohort
  data, not just the in-window slice. Compute it after building the full
  dosage matrix for the view, before windowing.

### Tests on synthetic data

Use `make_test_data.R` to produce a tiny test, then verify:
- A sample with all-major-allele dosages should have PC1 = +1 extreme (or
  -1 if polarity flips)
- A sample with all-minor-allele dosages should have PC1 = -1 extreme
  (opposite)
- Eigenvalues should sum to total variance of the centered matrix

---

## Task 2: per-marker heatmap JSON

### Inputs
Same as Task 1 plus a centering anchor parameter.

### Per-marker output

For each pair-row in the view (after support filter):

```json
{
  "marker": "C_gar_LG28_15234521_MAJOR_MINOR1_A_G",
  "chrom": "C_gar_LG28", "pos": 15234521,
  "role_a": "MAJOR", "role_b": "MINOR1",
  "allele_a": "A", "allele_b": "G",
  "n_alleles_obs": 3,
  "pair_count": 1834,
  "polarity_flipped": false,
  "dosage": [1.02, 0.05, 1.94, ...],
  "dosage_centered": [-0.04, -1.01, 0.88, ...]
}
```

`dosage_centered = dosage - mean(dosage[centering_subset])`. Default
subset = all samples.

### Genotype-state JSON (optional, tri+ sites only)

For each site with `n_alleles_obs >= 3`:

```json
{
  "marker_site": "C_gar_LG28_15234521",
  "chrom": "C_gar_LG28", "pos": 15234521,
  "alleles_observed": ["A", "C", "G"],
  "n_alleles": 3,
  "states": ["AA", "AC", "AG", "AA", "CG", ...],
  "state_confidence": [0.99, 0.95, 0.91, ...]
}
```

For tri-allelic site, possible states: AA, AC, AG, CC, CG, GG. For
quad-allelic: 10 possible.

Compute states from the underlying GLF10 (need to thread through from
ANGSD output) — argmax over genotype likelihoods, with confidence =
posterior probability of the chosen state under flat prior.

This requires reading the GLF10 binary, not just the projected Beagle.
First pass: skip this output, add later.

---

## CLI design

```bash
Rscript producer_pca.R \
  --view_beagle    all_pairs.beagle.gz \
  --view_sidecar   all_pairs.beagle.pairs.tsv \
  --bi_beagle      bi_baseline.beagle.gz \
  --bi_sidecar     bi_baseline.beagle.pairs.tsv \
  --bamlist        bamlist.txt \
  --candidate_id   "LG28_15.115_18.005" \
  --chrom          C_gar_LG28 \
  --interval       15115000-18005000 \
  --window_kind    bp_span \
  --window_size    50000 \
  --window_step    50000 \
  --anchor_mode    both \
  --centering      all \
  --polarity_ref   pc1_correlation \
  --weighted       FALSE \
  --out            pca_all_pairs_unweighted_both.json
```

Same for heatmap:

```bash
Rscript producer_heatmap.R \
  --view_beagle    all_pairs.beagle.gz \
  --view_sidecar   all_pairs.beagle.pairs.tsv \
  --bamlist        bamlist.txt \
  --candidate_id   "LG28_15.115_18.005" \
  --centering      all \
  --polarity_ref   pc1_correlation \
  --polarity_anchor pca_all_pairs_unweighted_bi_baseline.json \
  --weighted       FALSE \
  --out            heatmap_all_pairs_unweighted_all.json
```

The heatmap producer reads the PCA JSON output to know per-marker
polarity decisions (so heatmap and PCA agree).

A driver script ties this all together:

```bash
bash run_producers.sh /scratch/.../mgl10/LG28_15.115_18.005
```

Producing all 8 PCA JSONs (4 views × 2 weights) × 2 anchor modes = 16
PCA JSONs and 4 heatmap JSONs (no weighting effect on heatmap; centering
options handled at render time from the same JSON).

---

## Estimated effort

- `producer_pca.R`: ~250 lines including IO, dosage parser,
  per-window math, anchor modes. 1–2 days for first version.
- `producer_heatmap.R`: ~150 lines, simpler math. Half a day.
- `run_producers.sh` driver: ~50 lines, orchestration.
- Total: 3–4 days of focused work to produce a tested first version
  ready for atlas integration.

## What you can ignore for now

- **HWE statistics**: not in this layer.
- **`best_per_site` mode**: explicitly rejected in the design.
- **Caching/serverless backend**: HANDOFF_4 covers this for custom views.
- **Atlas-side UI**: HANDOFF_2.

## Pointers to existing code

In `mgl_adapter/`:
- `mgl10_to_beagle.R` — read this to understand sidecar columns and how
  GLs are normalized.
- `beagle_weight_by_support.R` — read this to understand the GL
  transformation; the producer should NOT re-apply weighting (the
  weighted Beagle already has it baked in).
- `make_test_data.R` — gives you a synthetic test scenario.
