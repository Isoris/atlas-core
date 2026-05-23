# HANDOFF 3 — Real-data validation on LG28

**Goal**: run the mgl_adapter pipeline on the real LG28:15.115-18.005
inversion candidate, run the validation checks from SPEC_0 Section 12,
and decide whether the multi-allelic path is worth the producer + atlas
work in HANDOFF 1 / 2.

**Status**: not started. The pipeline exists (`mgl_adapter/` v5).
Validation is the empirical step that confirms whether anything new is
visible in real data.

**Audience**: a fresh chat where Claude helps with the validation runs.
The chat should be focused on the validation outcomes, not on rebuilding
the pipeline.

---

## What you're testing

The LG28 candidate is a well-characterized inversion at 15.115-18.005
Mb on `C_gar_LG28`:
- Karyotype: 60 / 106 / 60 (HOM1 / HET / HOM2)
- HWE-perfect at the inversion locus (p ≈ 0.5)
- Shelf Fst_Hom1_Hom2 = 0.308 vs flanking 0.032-0.055
- Already shown clean structure on biallelic-only PCA

So this candidate is a **known-positive control** for biallelic analysis.
The questions for multi-allelic:

1. Does the multi-allelic adapter reproduce the same 60/106/60 structure?
   (If not, something's broken.)
2. Does multi-allelic add anything beyond what biallelic already shows?
   (If not, the adapter is reproducing existing results, not advancing
   them.)
3. Is there nested haplotype structure within the inversion that
   biallelic missed? (The big question — multi-allelic discovery.)
4. Are there rare-inversion signatures elsewhere in this candidate or in
   adjacent regions that biallelic missed?

---

## What to run

### Step 0: ANGSD GLF10 dump

```bash
sbatch SLURM_A05_glf10_interval.sh \
  C_gar_LG28 15115000 18005000 \
  /scratch/lt200308-agbsci/Quentin_project_KEEP_2026-02-04/mgl10/LG28_15.115_18.005
```

Expected runtime: a few hours, depending on cluster load. Output ~1-2 GB
of binary GLF10.

### Step 1: Verify GL log base before processing

```bash
od -An -t fD /scratch/.../mgl10/LG28_15.115_18.005.glf.gz | head -20
```

Values mostly in `[-30, 0]` → natural log (default).
Values mostly in `[-13, 0]` → log10 (use `--gl_log_base log10` in adapter).

### Step 2: Master conversion

```bash
bash run_pair_pca_matrix.sh \
  /scratch/.../mgl10/LG28_15.115_18.005
```

Expected: master Beagle of ~50k pair-rows for 226 samples, ~150 MB.
Master sidecar shows distribution of `pair_count`, `n_alleles_obs`,
`n_samples_with_minor`. **This is the first sanity check** — look at the
sidecar:

```bash
head -1 master_all_pairs.beagle.pairs.tsv
awk 'NR>1 {print $4}' master_all_pairs.beagle.pairs.tsv | sort | uniq -c
# Expected: most rows from biallelic sites (n_alleles_obs=2),
# some from tri-allelic (3), few from quad (4).

awk 'NR>1 {print $12}' master_all_pairs.beagle.pairs.tsv | \
  awk '{a[int(log($1+1)/log(10))]++} END {for(b in a) print b, a[b]}'
# Distribution of pair_count on log scale; expect bulk in 100-1000 range.
```

### Step 3: Run all 8 PCAngsd combos

The driver does this. Expected outputs:
```
pca_bi_baseline.cov         pca_bi_baseline_weighted.cov
pca_tri_extras.cov          pca_tri_extras_weighted.cov
pca_quad_extras.cov         pca_quad_extras_weighted.cov
pca_all_pairs.cov           pca_all_pairs_weighted.cov
```

Each is a 226×226 covariance matrix. Eigendecompose in R for top 2 PCs.

---

## The validation checks

### Check 1: bi_baseline matches existing biallelic pipeline

Quick R script:
```r
library(data.table)
cov_new <- as.matrix(fread("pca_bi_baseline.cov"))
e_new <- eigen(cov_new)
pc1_new <- e_new$vectors[, 1]
pc2_new <- e_new$vectors[, 2]

# Load existing biallelic-pipeline PCA (from your existing inversion
# detection codebase output for this candidate)
cov_old <- as.matrix(fread("/path/to/existing/pca_LG28.cov"))
e_old <- eigen(cov_old)
pc1_old <- e_old$vectors[, 1]
pc2_old <- e_old$vectors[, 2]

# Procrustes-align (or just check correlation magnitude, since signs
# are arbitrary)
cor1 <- abs(cor(pc1_new, pc1_old))
cor2 <- abs(cor(pc2_new, pc2_old))
cat("PC1 correlation:", round(cor1, 3), "\n")
cat("PC2 correlation:", round(cor2, 3), "\n")

# Plot side by side
par(mfrow=c(1,2))
plot(pc1_new, pc2_new, main=paste0("New (cor=", round(cor1,2), ")"))
plot(pc1_old, pc2_old, main="Old")
```

**Pass criterion**: |cor(PC1)| > 0.95, |cor(PC2)| > 0.85. Top samples in
each cluster should match.

**If fails**: the role-by-cohort-count convention is producing a
different basis from your existing biallelic pipeline. Investigate
which marker subset differs.

### Check 2: Unweighted vs weighted all_pairs

```r
plot_pca_pair("pca_all_pairs.cov", "pca_all_pairs_weighted.cov",
              titles=c("All pairs unweighted", "All pairs weighted"))
```

**Pass criterion (case A)**: visually similar PC1×PC2 → row-count
inflation isn't driving differences vs bi_baseline.

**Pass criterion (case B)**: visually different → weighting matters.
Weighted version is the more honest one. Use weighted as default.

### Check 3: tri_extras alone

```r
plot_pca("pca_tri_extras.cov")
```

**Pass criterion**: shows *some* coherent structure (not random
confetti). Ideally reproduces the 60/106/60 split or a related one.

If tri_extras alone shows nothing, the multi-allelic information at
this candidate isn't doing real work — it's just noise added on top of
biallelic. Multi-allelic is a curiosity here, not a discovery tool.

If tri_extras alone shows the same 60/106/60 → multi-allelic markers
inside the inversion segregate on the same axis as biallelic. Good.
Multi-allelic is reinforcing the biallelic signal.

If tri_extras shows a *different* clustering → multi-allelic markers
inside the inversion encode different information (sub-haplotype
structure?). This is the discovery case.

### Check 4: Rare-pair scanner output

```bash
cat rare_pair_windows.tsv
```

**Pass criterion**: should NOT flag the inversion main body
(15.115-18.005). Should flag flanks, other regions of the chromosome,
or be empty.

If the inversion main body is flagged → unexpected. Could mean nested
haplotype structure (interesting!) or paralog contamination (concerning).
Worth investigating per-window details.

### Check 5: Heatmap consistency (after producer is built — defer)

This is a producer-output check; skip until HANDOFF 1 is done.

### Check 6: F = 1 - obs_het / exp_het inside inversion

```r
# Compute per-marker F from the master sidecar's MAJOR_MINOR1 pairs
# inside the inversion interval
sc <- fread("master_all_pairs.beagle.pairs.tsv")
inversion_bi <- sc[role_a == "MAJOR" & role_b == "MINOR1" &
                   pos >= 15115000 & pos < 18005000]

# Compute observed het frequency from the Beagle GLs
# (need to read the Beagle and average P(Aa) across samples per marker)
beagle <- read_beagle("master_all_pairs.beagle.gz")
# For each marker, mean P(Aa) across samples = obs_het_freq

# Expected het from MAFs (from .mafs.gz output of ANGSD):
# exp_het = 2 * maf * (1 - maf)

F_inv <- 1 - obs_het / exp_het
hist(F_inv, breaks=50)
abline(v=0, col="red")
mean(F_inv > 0)   # should be much > 0.5
```

**Pass criterion**: positive median F at inversion sites (heterozygote
deficit relative to global allele frequencies). Negative F is a
red flag — paralog contamination.

### Check 7: Anchor 1 vs Anchor 2 for tri_extras (after producer is built)

Producer dependency; skip for now.

---

## After validation — go/no-go decision

Decision tree:

```
Check 1 fails (bi_baseline doesn't match existing pipeline):
  → Stop. Investigate role-by-cohort-count convention vs ANGSD's
    -doMajorMinor before doing anything else.

Check 1 passes, Check 2 shows large unweighted-vs-weighted difference:
  → Always use weighted variants in production. Note this finding for
    methods. Continue to Check 3.

Check 1 passes, Check 3 shows tri_extras = bi_baseline:
  → Multi-allelic is reinforcing, not discovering. Useful for
    statistical power but no new biology. Producer + atlas atlas
    integration still worth building, but with lower priority.

Check 1 passes, Check 3 shows tri_extras DIFFERENT from bi_baseline,
shape is interpretable:
  → Multi-allelic is doing real work. Build producer + atlas (HANDOFF 1
    + HANDOFF 2). This is the discovery case.

Check 4 flags inversion body:
  → Investigate before building atlas. Could be substructure (good)
    or paralog (bad). Either way, important to understand.

Check 6 fails (negative F at inversion sites):
  → Investigate alignment / paralog issues before trusting any of these
    results.
```

---

## What to report back

After running, summarize:

1. Sidecar distribution (n_alleles_obs counts, pair_count distribution)
2. Check 1 result: PC1/PC2 correlation between new and existing pipeline
3. Check 2 result: side-by-side PCA plots (unweighted vs weighted)
4. Check 3 result: tri_extras PCA plot
5. Check 4 result: rare-pair scanner table
6. Check 6 result: F distribution at inversion sites
7. Go/no-go on producer + atlas build

If go: HANDOFF 1 starts. If no-go: document why and pause.

---

## Pointers

- `mgl_adapter/run_pair_pca_matrix.sh` does steps 0-3.
- `mgl_adapter/SPEC_0_master.md` Section 12 has the canonical validation
  list this handoff expands.
- Quentin's existing biallelic LG28 PCA output: should be in his
  inversion_codebase_v8.5 results for the candidate. Locate path before
  starting Check 1.
