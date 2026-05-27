# SPEC — diversity-atlas `chromosomes` page (per-chromosome diversity)

**Status**: scaffold — page exists in the manifest but envelope-aware
wiring is pending. v1 reads from static `DEMO` data or the legacy TSVs
under `data/diversity/`; v2 should consume a typed
`diversity_per_chromosome_v1` envelope (adapter not yet authored).

**Scaffolded in:**

| file | role |
|---|---|
| [`pages/per_chromosome/chromosomes.html`](../atlases/diversity/pages/per_chromosome/chromosomes.html) | static fragment with per-chrom table + KW-test result panel |
| [`pages/per_chromosome/chromosomes.js`](../atlases/diversity/pages/per_chromosome/chromosomes.js) | mount lifecycle, table render, KW test compute |

**Sister pages**:
- [`samples`](SPEC_samples_page.md) — per-sample roll-up of the same metrics
- [`hotspots`](SPEC_hotspots_page.md) — within-chromosome outlier windows (this page is the chromosome-level aggregate)

---

## 1. The biological hypothesis

> Per chromosome, summarise the cohort's nucleotide diversity (θπ) and
> homozygosity burden (F_ROH). Test whether chromosomes differ
> significantly in their diversity profile — a signal that one or more
> chromosomes carry unusual demographic / selective history.

Catfish chromosomes vary by ~30 Mb to ~130 Mb in this cohort. Per-chrom
diversity differences are biologically expected (sex chromosomes,
chromosomes carrying old inversions, recent hybridisation regions).
The page surfaces those differences in one table and tests their
significance via a Kruskal-Wallis rank test across chromosomes.

## 2. Data input

**v1 today** (static + legacy TSVs):

- `data/diversity/per_chromosome.tsv` — one row per chromosome with `theta_pi_mean`, `theta_pi_sd`, `f_roh_mean`, `f_roh_sd`, `n_samples`
- `data/diversity/per_sample_per_chromosome.tsv` — long form (sample × chrom) feeding the KW test

**v2 target** (envelope-aware): a typed `diversity_per_chromosome_v1` envelope joining:

- ANGSD pestPG outputs (`/mnt/e/results_diversity/03_theta_pi/` per the master_config root `diversity_theta_pi`)
- ROH bundle outputs (`/mnt/e/results_diversity/04_roh/`)
- Cohort genome-wide rollups (`/mnt/e/results_diversity/05_aggregated/`)

The adapter would emit per-(sample × chrom) rows with the canonical columns the v1 TSV ships plus per-stat 95% CIs from the producer.

## 3. The two views

### 3.1 Per-chromosome summary table

Columns:

| col | source | units |
|---|---|---|
| `chrom` | input | string (e.g. `C_gar_LG07`) |
| `n_samples` | producer | count of samples with valid θπ/F_ROH on this chrom |
| `chrom_len_bp` | reference | bp from the FAI; not strictly needed for the test |
| `mean_theta_pi` | producer | θπ averaged over samples (or windows when only per-window values exist) |
| `sd_theta_pi` | producer | sample-level standard deviation |
| `mean_f_roh` | producer | per-sample F_ROH averaged over samples |
| `sd_f_roh` | producer | sample-level SD |
| `kw_p_theta_pi` | client-computed | KW test p-value for this chrom's θπ vs the genome-wide distribution (per §4) |
| `kw_p_f_roh` | client-computed | same for F_ROH |

Sortable by any column. Default sort: `chrom` ascending. Bonferroni-corrected p-values are highlighted in red when below `α/28` (the cohort has 28 LGs → Bonferroni divisor).

### 3.2 KW omnibus test

Above the table, a one-line summary:

> "Kruskal-Wallis test across 28 chromosomes — θπ: H = 47.3, p = 1.4e-3. F_ROH: H = 31.2, p = 0.052."

The omnibus test asks: **are the per-chrom medians of θπ (or F_ROH) different at all**, across the 28-chromosome panel? When significant, the per-chrom Bonferroni-corrected p-values in the table identify which chromosomes drive the signal.

## 4. The math

### 4.1 Per-chromosome statistics

For each chrom c:

```
samples_c     = { samples with valid θπ on chrom c }
mean_theta_pi_c = (1 / |samples_c|) × Σ_{s ∈ samples_c} theta_pi(s, c)
sd_theta_pi_c   = sqrt( (1/(|samples_c|−1)) × Σ (theta_pi(s, c) − mean_theta_pi_c)² )
```

Same for F_ROH.

### 4.2 Kruskal-Wallis omnibus

For metric M ∈ {θπ, F_ROH}:

- Pool all (sample, chrom) values into one long array; assign rank within the pool (average rank for ties).
- Per chrom c, compute the sum of ranks R_c assigned to that chrom's values.
- KW test statistic:

```
N         = total number of (sample, chrom) observations
n_c       = number of observations in chrom c
H         = (12 / (N × (N+1))) × Σ_c (R_c² / n_c) − 3 × (N+1)
df        = (n_chroms − 1)
p_value   = 1 − Chi²_df_CDF(H)  (asymptotic)
```

For n_chroms = 28 and the typical N ≈ 6_000 (28 chroms × ~226 samples,
minus missing), the chi-squared approximation is reliable.

### 4.3 Per-chrom contribution to the KW result

When the omnibus p is significant, each chrom's contribution to the
overall H statistic gives a per-chrom rank-based effect:

```
contrib_c = (R_c² / n_c) − (n_c × (N+1)² / 4)  (deviation from expected under H0)
```

The page renders `contrib_c` as a small bar to the right of `mean_theta_pi_c` in the table — visual cue to which chrom is driving the signal.

A formal **per-chrom test** (the page's `kw_p_*` column):

- For each chrom c, run a one-vs-all Mann-Whitney U test: chrom c's values vs the pool of all other chroms.
- Bonferroni-correct the n_chroms p-values: `p_bonf_c = min(1, p_c × n_chroms)`.

This is the right multiple-comparison correction for "which of the 28 chroms is unusual?" — Bonferroni at α/28 controls family-wise error rate.

## 5. State + interaction

- `state.shared.activeChrom` — clicking a row sets this to scope sibling pages (`samples`, `roh`, `texture`) to that chromosome.
- No page-local controls today; the KW test runs on mount and the table renders the result.

v2 should expose:
- A metric toggle: θπ / F_ROH / both
- Stratification: cohort / per-K=8 cluster / per-sex / per-F_ROH-quartile (the same shared stratification pill the `roh` and `burden` pages will share)

## 6. Failure modes

| # | condition | behaviour |
|---|---|---|
| 6.1 | A chrom has fewer than 3 samples with valid θπ | KW excludes that chrom from the omnibus (and the per-chrom test); table shows the row but greys out the p-value cell |
| 6.2 | All chroms have identical median θπ | KW H ≈ 0, p ≈ 1; no chrom is flagged — correct null behaviour |
| 6.3 | Severe outlier sample (one fish with θπ 10× cohort) | rank-based test is robust to magnitude; the outlier moves rank by 1 not by 10× |
| 6.4 | Missing F_ROH but present θπ | per-row: F_ROH column blank, θπ column populated; KW for F_ROH excludes the missing values |
| 6.5 | One chrom has n_samples ≪ others (e.g. sex chrom) | rank-based test handles unequal n; the per-chrom Mann-Whitney is still valid |
| 6.6 | Negative θπ or F_ROH (data error) | flag + drop with a console warning; downstream stats unaffected |
| 6.7 | Bonferroni divisor (28) hard-coded | producer should ship `n_chroms` in the summary; v2 should use that count, not hard-code |

## 7. What's currently NOT modelled

### 7.1 Envelope-aware data source

The page reads from static TSVs today. v2: a `diversity_per_chromosome_v1` adapter (mirror the meiosis-atlas pattern from `SPEC_chromosome_meiosis_events_adapter.md` — same 12-file scaffold).

### 7.2 KW + Mann-Whitney aren't explicit nulls about HW expectation

Both tests are non-parametric — they test "are these distributions different from each other" rather than "are these values different from a population-genetic null". A null based on θπ-expected-under-neutrality (4Nμ) or F_ROH-expected-under-pedigree-inbreeding would give a different (and biologically more interesting) test. Out of scope for v1; the page is descriptive cohort-comparison, not absolute-deviation.

### 7.3 Recombination-rate-aware

θπ varies systematically with recombination rate (low-recombination regions have less effective Ne via background selection). A v2 KW-residual test could regress θπ on local recombination rate first, then KW the residuals. Out of scope today.

### 7.4 Per-arm stratification

For metacentric chromosomes, p-arm vs q-arm θπ differs because of centromere proximity. The page currently treats each chrom as one unit. Future: split by arm when chromosome assembly is arm-aware.

### 7.5 Sex stratification

Sex chromosomes (or PAR regions, in fish where they exist) need separate treatment. Today pooled.

## 8. Cross-page links

Clicking a row in the table:
- Sets `state.shared.activeChrom = chrom`
- The sibling [`samples` page](SPEC_samples_page.md) filters its per-sample table to that chrom
- The [`hotspots` page](SPEC_hotspots_page.md) loads that chrom's θπ outlier windows
- The [`roh` page](SPEC_roh_page.md) heatmap shows that chrom's column highlighted

## 9. UI surface

```
┌────────────────────────────────────────────────────────────┐
│ status badge — n_chroms · n_samples · KW summary line      │
│   "KW(θπ) H = 47.3 p = 1.4e-3 · KW(F_ROH) H = 31.2 p = .052"│
├────────────────────────────────────────────────────────────┤
│ per-chromosome table (sortable)                            │
│   columns: chrom · n_samples · mean_θπ · sd_θπ · KW(θπ)    │
│            mean_F_ROH · sd_F_ROH · KW(F_ROH) · contrib_bar │
│   row click → state.shared.activeChrom                     │
│   Bonferroni-significant rows highlighted red              │
├────────────────────────────────────────────────────────────┤
│ [Export TSV]                                                │
└────────────────────────────────────────────────────────────┘
```

## 10. Promotion criteria

| criterion | v1 | v2 |
|-----------|----|----|
| Per-chrom table renders from static data | ✓ | ✓ |
| KW omnibus computes + renders | ✓ | ✓ |
| Per-chrom Bonferroni-corrected p | ✓ | ✓ |
| Click-row → state.shared.activeChrom | ✓ | ✓ |
| Envelope-aware (`diversity_per_chromosome_v1`) | ✗ | required |
| Adapter pair shipped | ✗ | required |
| Stratification pill (cohort / K=8 / sex / F_ROH-quartile) | ✗ | required (per [SPEC_roh_page.md §3](SPEC_roh_page.md)) |
| Smoke test | ✗ | required |
| 25+ assertion JS smoke | ✗ | required |

## 11. Open biological design questions

### 11.1 KW vs Welch's ANOVA

The page uses Kruskal-Wallis (non-parametric). Welch's ANOVA on log-transformed θπ would be more powerful if the underlying distribution is approximately log-normal. Decision needed: stick with KW for distribution-free guarantee, or switch when θπ distributions look log-normal in real data.

### 11.2 Which F_ROH definition

`F_ROH` comes in flavors: F_ROH_short (<1 Mb), F_ROH_medium (1–10 Mb), F_ROH_long (>10 Mb), F_ROH_total. The page uses `F_ROH_total` today. Different length classes index different demographic events (recent inbreeding vs ancient bottleneck). v2 should expose a length-class toggle.

### 11.3 Permutation null

A more principled null than KW's asymptotic chi-squared: permute the chrom labels across (sample, chrom) values 10k times, recompute H, get an empirical p. Useful when n is small. Out of scope for v1 where N ≈ 6_000 makes the asymptotic reliable.
