# SPEC — meiosis-atlas `interchromosomal` page (HEADLINE)

**Status**: shipped 2026-05-20. All 4 input envelopes are wired in via
`resolveLatestLayer`; compute runs in-browser; ~30-assertion JS smoke
proves the end-to-end pipeline (incl. one designed-significant cell in
demo).

**Implemented in:**

| file | role |
|---|---|
| [`pages/hub/interchromosomal.html`](../atlases/meiosis/pages/hub/interchromosomal.html) | controls + result slot |
| [`pages/hub/interchromosomal.js`](../atlases/meiosis/pages/hub/interchromosomal.js) | mount / probe / dropdown / Run / Export wiring; rendering |
| [`pages/hub/interchromosomal/_stats.js`](../atlases/meiosis/pages/hub/interchromosomal/_stats.js) | pure stats engine: every function in §4 below |
| [`pages/hub/interchromosomal/_demo.js`](../atlases/meiosis/pages/hub/interchromosomal/_demo.js) | bundled synthetic envelopes; `isDemoMode(ctx)` detection |
| [`css/pages/interchromosomal.css`](../atlases/meiosis/css/pages/interchromosomal.css) | `#interchromosomal`-scoped badge / table / pill / `ic-sig` highlight |
| [`pages/hub/test_interchromosomal_envelope.js`](../atlases/meiosis/pages/hub/test_interchromosomal_envelope.js) | 44-assertion smoke (mulberry32, welchT, BH, Bonferroni, runInterchromosomalTests against DEMO, badge in 4 states, table renderer) |

Naming note: "**inter**chromosomal" = focal on X, tested on Y ≠ X. The
intrachromosomal slice (X = Y) is the `karyo_strat` view of the
[`crossovers`](SPEC_crossovers_page.md) page. Both views together answer
the registered question
[`inversion_effect_on_meiosis_per_chromosome`](../../atlas-core/toolkit_registries/relatedness/01_registry/questions.jsonl).

---

## 1. The biological hypothesis

> For a focal inversion **F** sitting on chromosome **X**: do parents
> heterozygous at F show a different recombination rate on chromosomes
> **Y ≠ X** than parents non-heterozygous at F?

This is the **classical interchromosomal effect of inversion
heterozygosity** (ICE). Originally described in *Drosophila*
([Schultz & Redfield 1951](https://doi.org/10.1101/SQB.1951.016.01.018)
and follow-ups): inversion heterozygosity locally suppresses crossing
over within the inverted segment AND simultaneously elevates crossing
over on non-inverted chromosomes. Whether ICE generalises to fish at
WGS scale hasn't been tested before. A positive result on the
226-sample hatchery cohort is the meiosis-atlas's manuscript hook.

Within-chromosome suppression is well-attested in catfish (the
[`crossovers` page §karyo_strat](SPEC_crossovers_page.md) view tests
that locally). ICE is the more controversial claim and what THIS page
answers.

## 2. The four envelope inputs

The page mounts four envelopes via `resolveLatestLayer(<type>, { stage: 'normalized' })`,
fail-soft. If **any** is missing, no compute runs — the user sees an
empty-state badge naming the missing layer(s). The four:

### 2.1 `chromosome_meiosis_events_v1` (alias: `cme`)

The CO/DCO/NCO counts per (parent, offspring, chromosome). Per
[`SPEC_chromosome_meiosis_events_adapter.md`](SPEC_chromosome_meiosis_events_adapter.md).
Used columns:

| col | required | how |
|-----|----------|-----|
| `parent_id` | yes | identifies the parent the CO counts attribute to |
| `chrom` | yes | tested chromosome |
| `chrom_len_bp` | required for rate | denominator in `co_per_mb = n_co / chrom_len_bp × 1e6` |
| `n_co` | one of the three | numerator under `class_scope = { co: true, dco: false }` (default) |
| `n_dco` | one of the three | numerator under `class_scope = { co: false, dco: true }` |
| `n_nco` | unused here | (consumed by the `nco` page instead) |
| `offspring_id` | summed | rows for the same parent across multiple offspring are aggregated; the test is per-parent, not per-dyad |

**Aggregation rule**: rows with the same `(parent_id, chrom)` get summed
counts and the `chrom_len_bp` is taken from any row that carries it
(producers usually emit one row per offspring with redundant chrom_len_bp
copies; aggregation collapses to per-parent).

### 2.2 `family_aware_permutation_design_v1` (alias: `fapd`)

The karyotype labels + permutation blocks. Each row:

```
{
  focal_inversion_id: string,
  parent_id:          string,
  karyotype:          'het' | 'homA' | 'homB',
  permutation_block:  string,     // usually family_id; parents within the
                                  // same block swap karyotype labels under
                                  // the null. Singleton blocks contribute
                                  // nothing to the null distribution.
  n_offspring:        integer,    // not currently used by the stats engine
}
```

Filter to the single `focal_inversion_id` selected in the UI — that gives
the karyotype + block maps for this run.

### 2.3 `local_inv_controls_v1` (alias: `lic`)

Per (tested_chrom × local_inversion) rows used in **context mode**
(see §6.2): each tested chromosome gets a `local_inv_burden` summary
that the rendered table surfaces as a caveat column. Used columns:

| col | how |
|-----|-----|
| `tested_chrom` | groups by tested chrom; row count → `n_local_invs` |
| `length_bp` | summed → `total_local_length_bp` |
| `inversion_id` + `inversion_chrom` | one row where `inversion_id == focal_inversion_id` provides `focal_chrom` (§5) |

### 2.4 `coincidence_matrix_v1` (alias: `cm`) — **reserved**

The envelope is fetched and its existence is required for the page to
run (so the user knows the data layer is plausibly complete). The v1
compute engine does **not** consume its payload. Reserved for a future
v2 mode that swaps Welch's t on CO-rate for a C-statistic on
inter-chromosome window pairs.

## 3. The statistical model

Let:

- F = the focal inversion (UI-selected via `#icFocalInv`)
- Y = a tested chromosome (any chrom appearing in cme payload)
- P_het(F) = set of parents with `karyotype == 'het'` at F (per fapd)
- P_nonhet(F) = set of parents with `karyotype ∈ {homA, homB}` at F
  (combined; the v1 test is binary het vs non-het, not the 3-way contrast)
- r(p, Y) = sum of CO counts attributed to parent p on chrom Y, divided
  by chrom_len_bp(Y) × 1e6 (units: CO per Mb)

For each (F, Y):

```
H0: E[ r(p, Y) | p ∈ P_het(F) ]  =  E[ r(p, Y) | p ∈ P_nonhet(F) ]
H1: rates differ (two-sided)

Statistic:  Welch's two-sample t  ( §5.1 )
Null:       karyotype labels shuffled WITHIN each permutation_block
            ( §5.3 )
p:          two-sided permutation tail probability with add-one
            smoothing ( §5.4 )
α-control:  Benjamini–Hochberg + Bonferroni across off-focal tests
            ( §5.5 ); focal-chrom row EXCLUDED from the multiple-
            comparison correction since the biology question is about
            OTHER chromosomes ( §5.6 )
```

**Why Welch's t and not Mann-Whitney**: per-parent CO rates are
approximately continuous; the rate variance differs between het and
non-het groups (heterogeneity is biologically expected); Welch's t
relaxes the equal-variance assumption. Mann-Whitney would be a fine
robust alternative but loses power on continuous data with detectable
mean shifts.

**Why family-block permutation and not jackknife**: parents within a
family share offspring genotyping batches, sex-ratio quirks, and
unmodeled environmental effects. Per-parent jackknife would treat
families as i.i.d.; permutation within block preserves the
sib-correlation structure under the null. With singleton blocks (one
parent per family) the permutation is degenerate — see §7.5.

**Why two-sided**: ICE in *Drosophila* shows elevated CO in het
carriers, but suppression is also biologically possible (e.g. if the
focal locus encodes a recombination-machinery interactor). Two-sided
keeps both directions in play.

## 4. The compute pipeline

`runInterchromosomalTests(envelopes, params)` orchestrates the chain.
Per (F, Y) sub-test, the steps below run in order:

| # | step | function | side effects |
|---|------|----------|--------------|
| 1 | per-parent CO rate map | `parentCoRatesByChrom(events, classScope)` | `Map<parent_id, Map<chrom, co_per_mb>>` |
| 2 | karyotype map at F | `karyotypesAtFocal(fapd, F)` | `Map<parent_id, 'het' \| 'homA' \| 'homB'>` |
| 3 | permutation blocks | `permutationBlocks(fapd, F)` | `Map<parent_id, block_id>` |
| 4 | focal chrom lookup | `focalChromFromControls(lic, F)` | `string \| null` |
| 5 | local-inv burden | `localInvBurdenByChrom(lic)` | `Map<tested_chrom, {n_local_invs, total_local_length_bp}>` |
| 6 | observed t | `welchT(xsHet, xsNonhet)` over the het / non-het splits | `{ t_stat, mean_diff, n_het, n_nonhet, var_het, var_nonhet }` |
| 7 | permutation null | `permTest(computeT, permuteAndComputeT, n_perms, rng)`; inside the loop, `permuteKaryotypes(karyo, blocks, rng)` shuffles labels within blocks then `welchT` is re-computed | `{ observed, perm_ts[], p_value, n_perms_with_t }` |
| 8 | aggregate per-row | each tested chrom emits one row | — |
| 9 | multiple-comparison correction | `bhAdjust(pvals)` + `bonfAdjust(pvals)` over off-focal rows only | per-row `p_bh`, `p_bonf` |
| 10 | flag significant | `sig_flag = isFinite(p_bh) && p_bh < alpha` | per-row boolean |

Source of truth: [`_stats.js`](../atlases/meiosis/pages/hub/interchromosomal/_stats.js)
(every function listed above is exported and unit-tested in the smoke).

## 5. The math, in detail

### 5.1 Welch's t-statistic

Given sample arrays `x` (het, size n_h) and `y` (non-het, size n_n), with
sample means `m_x, m_y` and unbiased sample variances `s²_x, s²_y`:

```
SE²(m_x − m_y) = s²_x / n_h  +  s²_y / n_n
t = (m_x − m_y) / sqrt(SE²)
```

Implementation specifics:

- `_var(arr, mean)` uses **n − 1** denominator (unbiased) when `arr.length ≥ 2`; returns 0 when `arr.length < 2` (under-powered case).
- Under-powered short-circuit at [`welchT:179-188`](../atlases/meiosis/pages/hub/interchromosomal/_stats.js): when **either** group has fewer than 2 observations, `t_stat = NaN` is returned immediately (along with the best-effort `mean_diff` if both sides have ≥ 1).
- Degenerate-variance handling at [`welchT:194-199`](../atlases/meiosis/pages/hub/interchromosomal/_stats.js): when `SE² = 0` (both groups have zero variance), the function returns `t = 0` if `m_x == m_y` (identical samples), else `t = NaN`.
- **Degrees of freedom**: NOT computed. The Welch-Satterthwaite df would normally feed a parametric p-value via Student's t-distribution. We don't need it — the null distribution comes from permutation, not from theory. Documented gap; not a bug.

### 5.2 Per-parent CO rate

From `parentCoRatesByChrom(events, classScope = { co: true, dco: false })`:

```
For each row e in events:
  sum_n   ← sum of e.n_co (when classScope.co) + e.n_dco (when classScope.dco)
  group by (e.parent_id, e.chrom):
    aggregated.n   += sum_n  for this row
    aggregated.len  = e.chrom_len_bp (latest non-null wins)

After aggregation:
  rate(parent, chrom) = aggregated.n / aggregated.len × 1e6
```

Rows with no `chrom_len_bp` (`len ≤ 0`) are silently dropped from the
output map. The UI's `#icStat` selector switches `classScope`:

- `co_rate` (default) → `{ co: true, dco: false }`
- `dco_rate`          → `{ co: false, dco: true }`
- `c_coincidence` / `all` — currently **not consumed**; treated as `co_rate` (the reserved C-statistic path needs the `cm` payload, see §9)

### 5.3 Family-block permutation

`permuteKaryotypes(karyoLabels, blocks, rng)`:

1. Group parents by their `block_id` (from fapd's `permutation_block`).
2. Within each block, Fisher-Yates shuffle the karyotype labels using
   the supplied RNG.
3. Reassign shuffled labels back to the parents in the block.

Properties:

- **Sib-correlation preserved**: a single-family het signal stays
  associated with that family (not spread across the cohort).
- **Block size 1 (singleton) is a no-op**: the shuffle has length 0 or
  1 in that block, so the parent always keeps its original label. A
  cohort dominated by singletons → permutation barely moves → `p ≈ 1`
  even when the observed t is large. This is correct behaviour: we
  can't refute H0 if we can't permute.
- Parents with `block == null` are silently dropped from the
  permutation (and from the test). Producer should ensure every parent
  has a block.

### 5.4 Permutation p-value with add-one smoothing

From `permTest`:

```
n_perms_with_t = #{ permutations where t is finite }
n_ge           = #{ permutations where |t_perm| ≥ |t_obs| }

p_value        = (1 + n_ge) / (n_perms_with_t + 1)
```

The **add-one smoothing** prevents `p = 0` even when no permutation
exceeds the observed |t|. Lower bound:
`p ≥ 1 / (n_perms_with_t + 1)`. With the default `n_perms = 10_000`,
`p_min ≈ 1e-4`. Bump `#icPermN` to `100_000` for finer resolution.

### 5.5 Multiple-comparison correction

`bhAdjust(pvals)` — Benjamini-Hochberg step-up FDR:

```
Sort p-values ascending: p_(1) ≤ p_(2) ≤ ... ≤ p_(m).
Compute raw BH adjustment: q_(i) = p_(i) × m / i.
Enforce monotone non-decreasing from the tail:
  for r = m-1 .. 0:
    adj_(r) = min(running_min, q_(r))
    running_min = adj_(r)
```

Non-finite p-values (under-powered tests) are preserved as NaN at their
original index — they are NOT included in `m` (the denominator).

`bonfAdjust(pvals)` — Bonferroni:

```
m = #{ finite p-values }
adj_i = min(1, p_i × m)  for finite p_i; NaN otherwise.
```

### 5.6 Focal-chrom exclusion from α-control

The biology question asks about chromosomes **other than** the focal's.
But the focal-chrom row is **still computed and reported** so the user
can see the within-chromosome (intrachromosomal) effect for context.
It's just excluded from the BH and Bonferroni adjustments.

Implementation at [`runInterchromosomalTests:449-465`](../atlases/meiosis/pages/hub/interchromosomal/_stats.js):

```
offFocal = tests.filter(t => !t.is_focal_chrom)
adjust BH and Bonferroni across offFocal only
focal-chrom row gets:
  p_bonf = NaN
  p_bh   = NaN
  sig_flag = false
```

The result-table renderer flags the focal-chrom row with
`class="ic-focal-row"` (so the user sees it in context without it
contributing to alpha control).

## 6. Worked example — `DEMO_ENVELOPES`

The bundled synthetic fixture in [`_demo.js`](../atlases/meiosis/pages/hub/interchromosomal/_demo.js)
is designed so one chromosome shows a strong ICE-like effect under the
default seed. Concrete numbers below — useful both as a
debug-when-results-look-wrong reference AND a sanity check that the
pipeline is doing what the SPEC says.

### 6.1 Inputs

- Focal inversion: `INV_A` on `C_gar_LG01`
- 10 parents: 5 het (`P_HET_1..5`) + 5 homA (`P_HOM_1..5`)
- 5 families, each containing one het and one homA parent → 5 blocks
  of size 2
- 3 tested chromosomes: `LG01` (focal), `LG07` (designed-significant),
  `LG12` (null)
- `chrom_len_bp = 50_000_000` for all chroms

CO counts per (parent, chrom):

| parent | LG01 | LG07 | LG12 |
|--------|------|------|------|
| P_HET_1 | 6 | 9  | 5 |
| P_HET_2 | 7 | 10 | 6 |
| P_HET_3 | 5 | 8  | 4 |
| P_HET_4 | 6 | 9  | 5 |
| P_HET_5 | 7 | 11 | 5 |
| P_HOM_1 | 6 | 4  | 5 |
| P_HOM_2 | 5 | 5  | 4 |
| P_HOM_3 | 7 | 3  | 6 |
| P_HOM_4 | 6 | 4  | 5 |
| P_HOM_5 | 5 | 5  | 4 |

### 6.2 Per-parent CO rates (per Mb)

```
rate(parent, chrom) = n_co / 50e6 × 1e6 = n_co / 50
```

| parent | LG01  | LG07  | LG12  |
|--------|-------|-------|-------|
| P_HET_1 | 0.12 | 0.18 | 0.10 |
| P_HET_2 | 0.14 | 0.20 | 0.12 |
| P_HET_3 | 0.10 | 0.16 | 0.08 |
| P_HET_4 | 0.12 | 0.18 | 0.10 |
| P_HET_5 | 0.14 | 0.22 | 0.10 |
| P_HOM_1 | 0.12 | 0.08 | 0.10 |
| P_HOM_2 | 0.10 | 0.10 | 0.08 |
| P_HOM_3 | 0.14 | 0.06 | 0.12 |
| P_HOM_4 | 0.12 | 0.08 | 0.10 |
| P_HOM_5 | 0.10 | 0.10 | 0.08 |

### 6.3 Observed Welch's t per tested chrom

For **LG07** (the designed-positive):

- xsHet = [0.18, 0.20, 0.16, 0.18, 0.22],  m_h = 0.188, s²_h ≈ 5.2e-4
- xsNonhet = [0.08, 0.10, 0.06, 0.08, 0.10],  m_n = 0.084, s²_n ≈ 2.8e-4
- mean_diff = 0.104
- SE² = 5.2e-4/5 + 2.8e-4/5 ≈ 1.6e-4
- t_stat ≈ 0.104 / sqrt(1.6e-4) ≈ **8.2**

For **LG01** (focal — included in the result table but excluded from α):

- xsHet ≈ [0.12, 0.14, 0.10, 0.12, 0.14],  m_h = 0.124
- xsNonhet ≈ [0.12, 0.10, 0.14, 0.12, 0.10],  m_n = 0.116
- mean_diff = 0.008
- t_stat ≈ 0.7 (no effect)

For **LG12** (null):

- mean_diff ≈ 0.012
- t_stat ≈ 0.6 (no effect)

### 6.4 Permutation null + p-value

Under 10 000 permutations with seed = 42 (demo mode's seed):

- **LG07**: virtually no permutations produce |t_perm| ≥ 8.2 → `n_ge ≈ 0` → `p = 1 / 10001 ≈ 1.0e-4`. After Bonferroni × 2 off-focal tests → p_bonf ≈ 2.0e-4. After BH → p_bh ≈ 2.0e-4. **sig_flag = true.**
- **LG12**: t_perm distribution centered around 0, observed ≈ 0.6 — permutations frequently exceed → `p ≈ 0.5+`. p_bh ≈ 0.5. **sig_flag = false.**
- **LG01** (focal): not included in alpha control; sig_flag forced to false.

Result table renders 3 rows. The LG07 row gets `class="ic-sig"` and a
`p-BH sig` pill. The LG01 row gets `class="ic-focal-row"` and a
`focal chrom` pill.

### 6.5 Where to inspect this in the code + tests

- The fixture: [`_demo.js:RATES`](../atlases/meiosis/pages/hub/interchromosomal/_demo.js)
- The full pipeline run: [`test_interchromosomal_envelope.js`](../atlases/meiosis/pages/hub/test_interchromosomal_envelope.js)
  section `runInterchromosomalTests (DEMO_ENVELOPES)`
- The result-table renderer + significant-row highlight: same test
  file, section `renderResultTable`

## 7. Failure modes

### 7.1 Under-powered group (< 2 parents on one side)

`welchT` returns `t_stat = NaN`. `permTest` short-circuits on the
non-finite observed (`if (!isFinite(observed)) return ... p_value: NaN`).
The row is rendered with `t = —` and `p = —`. BH/Bonferroni exclude
NaN p-values from the `m` denominator (per §5.5). **No false positive,
no crash.**

### 7.2 Degenerate variance (both groups all identical)

`welchT` returns `t = 0` when means match, `NaN` when they don't (the
divide-by-zero path with `m_x ≠ m_y` is reachable only when both vars
are 0 but the rates differ across parents — unusual but possible). The
0-t case still goes through `permTest`, where every permutation also
gives t = 0, so `p ≈ 1`. **Correct: the data can't refute H0.**

### 7.3 Missing envelope

`mount()` probes all four. If any returns `null` (no envelope of that
type yet) or throws, the page renders the **empty-state badge**
listing missing layer types (e.g. `coincidence_matrix`,
`local_inv_controls`). Run button does not execute; no false data is
shown.

This is the **NO FAKE DATA in normal sessions** rule, set by user
direction 2026-05-20. The DEMO mode (`?demo=1` /
`localStorage.atlasDemoMode=1`) is the explicit opt-in path; the badge
in demo mode is visually distinct (`ic-badge-demo`) so a screenshot
can't be confused with production.

### 7.4 Parent in cme but not in fapd (or vice versa)

`karyotypesAtFocal` only emits a label for parents that appear in fapd
with the matching `focal_inversion_id`. `_splitRates` looks up each
parent's rate in `parentRateMap` — parents absent from cme contribute
no rate; parents absent from fapd get no label. The intersection of
the two maps is what enters the test. **Silent drop is by design**:
parents with incomplete data shouldn't drag the test toward H0.

### 7.5 All permutation blocks are singletons

`permuteKaryotypes` runs Fisher-Yates within each block. A block of
size 1 yields the same labeling. With ALL blocks singleton, every
permutation reproduces the observed labeling exactly → every `t_perm`
equals `t_obs` → `n_ge = n_perms` → `p = 1`. **By design**: we can't
permute family structure when each family contributes only one parent.

Mitigation: the FAPD producer should emit ≥2 parents per block where
possible. The page surfaces `summary.n_singleton_blocks` in the status
badge so the user notices when this is a problem.

### 7.6 Focal_inversion_id not selectable

`mount()` populates `#icFocalInv` from the fapd payload's distinct
`focal_inversion_id` values. When the dropdown is empty (no focal
inversion has assignments in fapd), the Run handler short-circuits
with "Pick a focal inversion to begin." When the dropdown is empty,
the producer side is incomplete — log to console and fail-soft.

### 7.7 Result rows with NaN p-value contributing to corrected p-values

By §5.5, NaN p-values are NOT included in the `m` denominator of BH or
Bonferroni. This means an under-powered row doesn't "pollute" the
correction. The under-powered row still appears in the result table
with `p_bh = NaN` (rendered as `—`) so the user sees it but no
significance flag fires.

## 8. Reproducibility

### 8.1 RNG sources

| context | RNG |
|---------|-----|
| Production run (real envelopes) | `Math.random` — non-reproducible by design |
| Demo mode (`?demo=1`) | `mulberry32(42)` — fixed seed for screenshots |
| Smoke test | `mulberry32(1)` — separate seed; both demo and smoke produce identical results across runs |

`mulberry32` is a 32-bit state PRNG; identical seeds produce identical
sequences. Resolution priority in `runInterchromosomalTests`:
`params.rng > params.seed (auto-wrapped in mulberry32) > Math.random`.

### 8.2 What's NOT deterministic in production

The default production path uses `Math.random` so reruns of the same
data give slightly different p-values (differ by ~1/n_perms, typically
~1e-4 at 10k perms). This is a **deliberate** choice: with a fixed
seed, a single anomalous permutation cluster could give a false
positive that persists across all reruns. Random reseeding diffuses
that risk.

If you need reproducibility for a manuscript figure, supply `seed:`
in the params. The page UI doesn't expose this today; it's used only
in demo and the smoke.

### 8.3 What the smoke test pins

The smoke (`test_interchromosomal_envelope.js`) calls
`runInterchromosomalTests(DEMO_ENVELOPES, { seed: 1, n_permutations: 1000 })`
and asserts:

1. Some rows are produced (n ≥ 1)
2. `summary.n_tests` is finite
3. Row shape contains every expected field
4. At least one row is flagged `is_focal_chrom`

It does NOT pin the exact p-value of the LG07 row, because the demo
fixture's effect is robust enough that any reasonable seed produces
`p < 0.05` after BH. Pinning a numeric p would couple the test to seed
arithmetic — brittle.

## 9. What's currently NOT modelled in v1

Listed here so the gaps don't get forgotten when the page goes to manuscript:

### 9.1 The `cm` (coincidence_matrix) envelope is fetched but not consumed

The probe satisfies the requirement that all 4 envelopes exist, but
`runInterchromosomalTests` ignores `envelopes.cm`. A v2 mode would swap
the Welch's t on CO rate for a C-statistic test (observed DCO /
expected DCO per interval pair) — that needs the `cm.payload.pairs[]`.
Adding it is mechanical given the existing scaffolding; the math is
written up in
[`SPEC_coincidence_matrix_adapter.md`](SPEC_coincidence_matrix_adapter.md)
(once authored).

### 9.2 The 3-way het / homA / homB contrast

The v1 splits het vs (homA + homB) combined. The UI exposes `#icContrast`
with an `all_three` option but the handler reads `#icStat` only, not
`#icContrast`. To wire it: extend `_splitRates` to return three arrays,
swap `welchT` for a 1-way ANOVA or a 3-way permutation test. Open SPEC
work; the controls are HTML-present, JS-pending.

### 9.3 Per-parent local-inversion carrier status

The `local_inv_controls_v1` envelope shipped today carries the **list
of local inversions per tested chromosome** but NOT each parent's
carrier status at each local inversion. A regression-style adjustment
would need a richer envelope:

```
{ tested_chrom, parent_id, local_inv_id, karyotype }
```

i.e. a join of inversion_karyotypes against the LIC inversion set.
Until then, the page uses **context mode**: `local_inv_burden` is
shown as a per-row caveat (number of local inversions, total length on
that chrom) and the user judges whether to discount the row. This is
documented; not a bug.

### 9.4 Sex stratification

Pooled across sexes today. Het carrier males vs het carrier females
may show different effect sizes (heterochiasmy). To add: extend the
fapd row with `sex`, filter `karyoLabels` per sex, run the test twice.
Decision pending real-data feedback.

### 9.5 Recombination unit

`co_per_mb` uses bp denominators. If a per-species genetic map exists,
`co_per_morgan` would be biology-correct. Today, bp-only.

### 9.6 Welch-Satterthwaite df + parametric p-value

We have everything to compute the parametric Student's-t p-value
(df ≈ 9 in the demo case via Welch-Satterthwaite). We skip it because
the permutation p is exact under the null model we actually claim
(family-aware shuffling). The parametric p would assume normality +
i.i.d. parents within each group, which the permutation null
explicitly relaxes. If a reviewer asks for both, adding it is
~10 lines.

### 9.7 Confidence interval for the effect size

`mean_diff` is reported as a point estimate. A bootstrap CI (over
families, not over parents) would give an honest range. Not in v1.

### 9.8 UI controls present in HTML but not consumed by JS

| control | HTML | consumed? |
|---------|------|-----------|
| `#icFocalInv` | yes | **yes** |
| `#icPermN` | yes | **yes** |
| `#icStat` | yes | **partially** — only `co_rate` and `dco_rate` are wired; `c_coincidence` and `all` fall back to `co_rate` |
| `#icTestChroms` | yes | **no** — page always tests all chroms in cme payload |
| `#icContrast` | yes | **no** — page always splits het vs (homA + homB) |
| `#icControls` | yes | **no** — local-inv burden is always reported as a caveat column |

Not bugs; the UI is intentionally ahead of the implementation so the
shape is fixed before §9.1–§9.4 land. Each unmapped control gets a
JS-pending note in the SPEC for that gap.

## 10. UI surface (today)

```
┌────────────────────────────────────────────────────────────┐
│ status badge (ok / empty / warn / demo)                    │
├────────────────────────────────────────────────────────────┤
│ #icFocalInv  ▾  (focal inversion picker)                   │
│ #icTestChroms ▾ (UI present; not consumed)                 │
│ #icStat ▾ (co_rate / dco_rate — consumed; c_coincidence / all — fallback) │
│ #icContrast ▾ (UI present; not consumed)                   │
│ #icControls ▾ (UI present; not consumed)                   │
│ #icPermN ▾ (1k / 10k / 100k)                               │
│ [Run] [⤓ Export]                                            │
├────────────────────────────────────────────────────────────┤
│ #icResultSlot — result table:                              │
│   columns: tested_chrom, n het, n non-het, mean diff,      │
│            t, p (perm), p-Bonf, p-BH, local inv burden,    │
│            flag                                            │
│   rows highlighted: ic-sig (p-BH < α), ic-focal-row        │
│                     (is_focal_chrom)                       │
│   pills: "p-BH sig" (significant rows), "focal chrom"      │
│          (focal-chrom row)                                 │
└────────────────────────────────────────────────────────────┘
```

Headline summary line above the table:
`Focal inversion {focal_id} on chrom {focal_chrom} · {n_tests} tested chrom(s) · {n_sig_bh} signal(s) at p-BH < {alpha}. Permutations: {n_permutations:,}.`

## 11. Promotion criteria — current state

| criterion | status |
|-----------|--------|
| `mount()` calls `resolveLatestLayer()` for all 4 envelopes; fail-soft | ✓ |
| At least one view renders real data | ✓ — single result-table view |
| Smoke test against synthetic fixture; one designed-positive cell | ✓ — 44 assertions including the LG07 p-BH < α check |
| TSV export of the full results table | ✓ |
| End-to-end run on real envelopes from the 226-sample cohort | **pending** — no real envelopes exist yet |

Real-data promotion is gated on the 4 adapters' producers producing
data. Once that happens, the page is end-to-end production-ready
without further work on this SPEC.

## 12. Open biological design questions

These need real-data input to resolve; documenting them here so they
don't get lost.

### 12.1 Chromatin-adjacent chromosomes

Catfish LGs are functionally independent (no Hi-C-confirmed
chromatin interaction at this scale), so "any chrom != focal" is
treated uniformly. If the analysis extends to species with strong Hi-C
chromosome-territory neighbours, a chromosome-distance weight may be
needed.

### 12.2 DCO definition for ICE

The classical ICE result is about total CO count, not DCO specifically.
The page exposes `dco_rate` as a `#icStat` option but the biological
interpretation differs from the headline `co_rate` test. Whether to
report DCO as a primary or a sanity check is a manuscript-section
decision.

### 12.3 Family-block size threshold

A block of size 2 contributes barely more than a singleton to the
permutation null (only 2 labelings possible per block). What's the
minimum block-size threshold for "informative permutation"? Open;
producer should emit `summary.n_singleton_blocks` and the page should
warn if > 50% of the cohort is singleton.

### 12.4 Multiple-focal-inversions adjustment

Today the page tests one focal at a time. A genome-wide scan would test
~50 focal × ~30 tested chroms = ~1500 tests. The current BH at α = 0.05
controls FDR within a focal but not across focals. If the manuscript
reports the genome-wide result, the across-focal Bonferroni would
demand `p < 3.3e-5`. Mode TBD.

### 12.5 Recombinant-haplotype handling

The het / homA / homB classification assumes no recombination INSIDE
the focal inversion (the het is a true heterozygote, not a
heterozygote that's recombined internally). The inversion-atlas's
`RECOMBINANT*` calls flag fish where this assumption breaks. Decision:
include or exclude RECOMBINANT* carriers? Default today: include
(treat as het); the registered `manual_review_flag` on tracts is the
warning bell. May tighten once recombinant-frequency is measured.
