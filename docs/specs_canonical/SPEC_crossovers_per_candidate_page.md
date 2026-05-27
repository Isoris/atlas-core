# SPEC — meiosis-atlas `crossovers_per_candidate` page

**Status**: scaffolded — page mounts, layer-registry chips render
"⚪ not loaded" for `crossover_track` and `prdm9_motif`, the no-op
`renderCrossoversPerCandidate` stub returns immediately. No envelope or
file load happens yet. Phase C ships the producer pipeline + the
actual three-view render.

**Implemented in:**

| file | role |
|---|---|
| [`pages/hub/crossovers_per_candidate.html`](../atlases/meiosis/pages/hub/crossovers_per_candidate.html) | static fragment with the three card containers (ideogram, telomere curve, optional PRDM9 logo) |
| [`pages/hub/crossovers_per_candidate.js`](../atlases/meiosis/pages/hub/crossovers_per_candidate.js) | mount / unmount lifecycle, the `_maybeHideOptionalCards` optional-PRDM9 toggle, exported `renderCrossoversPerCandidate(state)` stub |
| [`pages/hub/crossovers_per_candidate/_state.js`](../atlases/meiosis/pages/hub/crossovers_per_candidate/) | per-page state isolation, mirrors the legacy sister pages |
| [meiosis manifest entry](../atlases/meiosis/manifest.json) | `stylesheet: atlases/genome/css/genome.css` — cross-atlas CSS dependency (this page uses the `.ga-*` namespace inherited from its original genome-atlas home) |

**Migration history**: this page was migrated from
`genome-atlas/pages/annotation/page11.{html,js}` on 2026-05-19 because
per-inversion-candidate CO views are meiotic content (the offspring of
an inversion heterozygote), not genome-assembly content. The genome
atlas page3 (chromosome overview) still uses CO density via a
**cross-atlas read** of the meiosis-atlas's `crossover_track` layer.

**Sister page**: [`nco_per_candidate`](SPEC_nco_per_candidate_page.md) —
the same per-candidate keying applied to NCO / gene-conversion tracts.

---

## 1. The biological hypothesis

> For one focal inversion candidate at a time, render the **shape of crossing-over** around the candidate: where COs happen relative to the inversion's span, how that varies with parent sex, and (optionally) what motif might be acting as the recombination hotspot.

Three orthogonal pieces of evidence are stitched together on one page:

1. **Sex-specific positional pattern.** Where are the CO breakpoints along the chromosome? Inside the inverted span? In the flanks? Symmetric or skewed? Different in males vs females (heterochiasmy)?

2. **Telomere bias.** The biology: in many fish, crossing over is concentrated near telomeres in one sex (often males) and more uniform in the other (often females). A candidate inversion's CO pattern should follow the host chromosome's baseline unless something disrupts it. Plotting CO rate against **relative-telomere-distance** d_rel ∈ [0, 1] (§4.3) makes that contrast portable across chromosome lengths.

3. **PRDM9 motif.** If a sequence motif drives the CO hotspots in the candidate's flank, MEME / STREME on those regions should recover a position weight matrix (PWM). The page shows the logo when present and hides the card when absent.

The page is **per-candidate by design** — the cohort-level CO view lives on the [`crossovers`](SPEC_crossovers_page.md) page. This page zooms into one candidate at a time so the reviewer can decide whether its CO pattern is consistent with an active inversion (CO suppressed in the span; flanking elevation; sex-asymmetric).

## 2. Data input — `crossover_track` (+ optional `prdm9_motif`)

Two layers declared in [`layers.registry.json`](../atlases/meiosis/registries/data/layers.registry.json):

### 2.1 `crossover_track` (file layer, cold tier)

Path: `data/crossovers/<candidate_id>.json`

The renderer interpolates `<candidate_id>` from `state.shared.candidate` (set by the candidate picker on sibling pages). The layer registry never enumerates `data/crossovers/` — auto-indexing is **not** used because the per-candidate file load is on-demand.

```jsonc
{
  "candidate_id":  "INV_LG28_01",            // matches shared.candidate
  "candidate_span": {
    "chrom":    "C_gar_LG28",
    "start_bp": 12000000,
    "end_bp":   14000000
  },
  "flank_bp":      500000,                   // optional; rendering window = span ± flank
  "events": [
    { "chrom": "C_gar_LG28", "pos_bp": 11890000, "sex": "F", "indiv": "P_HET_3", "in_span": false },
    { "chrom": "C_gar_LG28", "pos_bp": 12480000, "sex": "M", "indiv": "P_HET_1", "in_span": true  },
    ...
  ],
  "telomere_curve": {                        // optional; producer may pre-compute or leave to client
    "F": { "d_rel": [0.02, 0.04, ...], "rate": [0.18, 0.22, ...], "ci_lo": [...], "ci_hi": [...] },
    "M": { "d_rel": [...], "rate": [...], "ci_lo": [...], "ci_hi": [...] }
  },
  "curve_params": {                          // LOESS settings used by the producer (when pre-computed)
    "bandwidth":   0.3,
    "degree":      2,
    "ci_alpha":    0.05,
    "ci_method":  "bootstrap" | "asymptotic"
  }
}
```

### 2.2 `prdm9_motif` (optional, embedded on the same JSON)

```jsonc
{
  "prdm9_motif": {
    "pwm":         [[0.10, 0.40, 0.35, 0.15], ...],   // N × 4 ACGT PWM, or null
    "tool":        "STREME",                          // or "MEME"
    "evalue":      1.2e-5,
    "n_hotspots":  9                                  // how many CO-flank windows were used as input
  }
}
```

When `prdm9_motif.pwm` is `null` (or the field is absent), the page hides the logo card. See §3.3.

**Schema documented at**: [layers.registry.json](../atlases/meiosis/registries/data/layers.registry.json#L17) — the `_schema` field on each layer entry.

## 3. The three views

### 3.1 Sex-specific CO ideogram

A horizontal track spanning `[candidate_span.start_bp − flank_bp, candidate_span.end_bp + flank_bp]`. Within the track:

- The **inverted span** rendered as a translucent block (the boundary cue).
- One dot per CO event at `pos_bp`, coloured by `sex` (red ♀ / blue ♂).
- Hover tooltip: `indiv`, `pos_bp`, `in_span`.

Implementation details (when the renderer ships in phase C):

- **X-axis**: bp coordinates, linear within the (span + flank) window.
- **Vertical jitter**: events at the same `pos_bp` get jittered y-offset within a lane width so they don't fully overlap; per-sex lanes (red lane above, blue lane below) or interleaved with sex-coloured dots.
- **Empty-state**: when `events.length === 0`, render the span band only and a "no CO calls in this candidate" hint.
- **Visual aside**: the rendered span is just the inverted region; the ±`flank_bp` zoom-out is what carries the biology (CO inside the span = suppression failure or recombinant call; CO in flank = expected baseline).

### 3.2 CO rate vs relative-telomere-distance (with LOESS + 95% CI)

A two-axis plot per sex, overlaid:

- **X-axis**: `d_rel`, the relative-telomere distance (see §4.3 for the definition). 0 = at a telomere; 1 = at the chromosome midpoint (or maximum chromosome-arm distance).
- **Y-axis**: per-window CO rate (events / bp, scaled — typical units cM/Mb if a recombination map exists, else events/Mb).
- Two LOESS curves, one per sex, with a 95% CI band shaded around each.

Two producer modes (the renderer accepts both):

- **Pre-computed mode**: `telomere_curve.{F,M}` is populated with `d_rel`, `rate`, `ci_lo`, `ci_hi` arrays. The renderer just plots them. This is the default for big cohorts where LOESS-on-the-fly is slow.
- **Client-side mode**: `telomere_curve` is absent; the renderer computes LOESS from `events[]` + the `curve_params`. Math in §4.

### 3.3 Optional PRDM9 sequence logo

When `prdm9_motif.pwm` is a non-null `N × 4` matrix:

- Render a stacked-letter logo. Letter height per position = information content × probability:
  ```
  IC(i) = 2 − H(i)        where H(i) = −Σ_b p(i,b) log2 p(i,b)
  letter height(i,b) = IC(i) × p(i,b)
  ```
- Caption below: `tool · e-value · n_hotspots` (so the reviewer sees the discovery context).

When `pwm` is `null` or the field is absent, the page hides the card entirely (`#data-ga-card="prdm9-motif"` → `display: none`). The hide is handled by `_maybeHideOptionalCards(root, state)` in `crossovers_per_candidate.js`. The optional-card pattern is generic — the same hook can be reused for any future optional cards on this page.

## 4. The math

### 4.1 Per-window CO rate

For LOESS input (and for the descriptive ideogram), CO events are first binned into windows along the chromosome:

```
window_size_bp = 100_000              // default; producer may override via curve_params
windows[i] = [start + i × window_size_bp, start + (i+1) × window_size_bp]
rate(window i, sex) = #{ events with pos_bp ∈ window i, event.sex == sex } / window_size_bp
```

`window_size_bp` is a producer-side parameter. Smaller windows give finer spatial resolution but noisier rates; larger smooth too much. Default 100 kb chosen to match typical pedigree-CO calling resolution.

### 4.2 LOESS smoothing

For each sex separately:

- Fit a locally-weighted linear or quadratic regression (`degree ∈ {1, 2}`, default 2) of `rate` against `d_rel` with bandwidth `bandwidth` (fraction of points in the local window).
- Default `bandwidth = 0.3`: each smoothed point uses the nearest 30% of data points, weighted by the tricube weight function:
  ```
  w(u) = (1 - |u|³)³   for |u| ≤ 1; 0 otherwise
  u = (d_rel_i - d_rel_center) / bandwidth_radius_in_data_units
  ```
- The fitted value at each evaluation point is the LOESS estimate.

### 4.3 Relative-telomere-distance

For a chromosome of length `L_chrom_bp`:

```
d_rel(pos) = min(pos, L_chrom_bp - pos) / (L_chrom_bp / 2)
```

- `d_rel = 0` → at one of the telomeres
- `d_rel = 1` → at the chromosome's midpoint (the metric is symmetric about the midpoint)

This **normalizes across chromosome lengths**: a 30 Mb LG and a 130 Mb LG can be compared on the same x-axis. Also handles per-arm asymmetry — telomere distance from EITHER telomere is what matters.

**Caveat**: this assumes a metacentric chromosome or, more weakly, that the centromere sits near the midpoint. Acrocentric chromosomes (centromere near one telomere) violate this. v2 should accept a `centromere_bp` field per chromosome and split `d_rel` into two: p-arm-telomere and q-arm-telomere relative distances. For catfish LGs, midpoint approximation is acceptable (assemblies are mostly metacentric or submetacentric).

### 4.4 95% CI for the LOESS curve

Two reasonable approaches; the producer picks one and signals via `curve_params.ci_method`:

**Method 1: Bootstrap (recommended).**

- For each bootstrap replicate b = 1..B (B ≥ 500):
  - Resample events with replacement, **stratified by family** (so each family appears with replacement at the family level, not the event level)
  - Recompute per-window rates
  - Refit LOESS
- The 95% CI at each evaluation point = 2.5th and 97.5th percentile of the B bootstrap fits.

**Method 2: Asymptotic (faster, less accurate).**

- For each LOESS-evaluated point, the local linear fit produces a standard error of the fitted value.
- `ci_lo = fit − 1.96 × SE; ci_hi = fit + 1.96 × SE`.
- Assumes residuals are Gaussian and the local fits are independent — both violated in practice. Used when bootstrap is too slow.

**Family-stratified bootstrap is the correct null** for the same reason the [`interchromosomal`](SPEC_interchromosomal_page.md) page uses family-block permutation: events from the same family share a parent, sex, and genetic background. Per-event bootstrap would treat them as i.i.d. and shrink the CI artificially.

### 4.5 Sex contrast

The two curves are NOT statistically compared on the page itself — the visual overlay invites the eye to spot heterochiasmy. A formal test would be:

```
H0: rate_M(d_rel) = rate_F(d_rel)  for all d_rel
```

For v2 (after the producer ships), a permutation test that shuffles `sex` labels across events (within-candidate, within-cohort) would give a p-value at each `d_rel` evaluation point. BH correction across the d_rel grid. Out of scope for v1 — visual inspection is the v1 review tool.

## 5. Cross-atlas read pattern

This page lives in the meiosis-atlas but its CSS namespace is `.ga-*` (inherited from its original genome-atlas home — see migration note at the top). The manifest entry sets `stylesheet: atlases/genome/css/genome.css`:

```jsonc
{
  "id": "crossovers_per_candidate",
  "fragment": "atlases/meiosis/pages/hub/crossovers_per_candidate.html",
  "module":   "atlases/meiosis/pages/hub/crossovers_per_candidate.js",
  "stylesheet": "atlases/genome/css/genome.css"
}
```

This is the **first cross-atlas stylesheet dependency** in the workspace. The atlas router fetches the cross-atlas file on mount; if `atlases/genome/` isn't in the assembled workspace, the page renders unstyled.

**Reciprocal cross-atlas read**: the genome-atlas's page3 (chromosome overview) reads the meiosis-atlas's `crossover_track` layer to add a CO-density sub-track. This is the **first cross-atlas layer read** in the workspace (per genome-atlas's `crossover_density_track` layer entry, which proxies through to this atlas's `crossover_track`).

Both crossings are documented at:
- [meiosis layers.registry.json](../atlases/meiosis/registries/data/layers.registry.json) (`_migration_note_2026_05_19` + `_feeds` field on `crossover_track`)
- [meiosis manifest.json](../atlases/meiosis/manifest.json) (the `_migration_note_2026_05_19` on the page entry)

## 6. State + interaction model

- `state.shared.candidate` → drives the per-candidate file path (`data/crossovers/<candidate_id>.json`)
- `state.shared.activeChrom` → coincides with `candidate_span.chrom` for the active candidate; not separately read
- No page-local controls today (no class filter, no sex toggle); the candidate picker on sibling pages (`inversions` table, `local_pca_dosage`) is the only handle

When the candidate changes:
- `mount()` → fetch the file → render the three views
- `unmount()` → tear down listeners; `_setActiveState(null)` clears the page-local state

Per-candidate file fetches are cached client-side via the registry's `tier: "cold"` setting (last-N evictable cache). The renderer caches LOESS fits keyed by `(candidate_id, sex, curve_params)` so re-rendering the same candidate is instant.

## 7. Failure modes

### 7.1 No active candidate

When `state.shared.candidate` is null (the user landed on the page without selecting a candidate from `inversions` or `local_pca_dosage`), `mount()` renders a "Pick a candidate from the Inversions table to begin" hint and skips the fetch.

### 7.2 File not found

`data/crossovers/<candidate_id>.json` returns 404. The page renders the layer-registry chip as `🟠 file not found`, hides the three view cards, and surfaces a console warning. No exception; the page stays mounted so the user can pick a different candidate.

### 7.3 Malformed JSON

`fetch().then(json)` throws. The page renders `🔴 parse error: <message>` on the layer chip. Same fail-soft pattern as §7.2.

### 7.4 `events` empty but file present

Render the span band + a "no CO calls in this candidate" hint. The telomere curve view shows the LOESS would need ≥ 1 event per sex to fit; renders an empty-state per sex.

### 7.5 Single sex represented

Fish cohorts with extreme sex bias. The renderer skips the missing-sex LOESS (no fit possible with 0 events). The ideogram lane for the missing sex is rendered empty (with a legend annotation).

### 7.6 `prdm9_motif.pwm` is null/missing

The PRDM9 card is hidden via `_maybeHideOptionalCards`. **Not** an error — the data simply isn't there (e.g. STREME ran and found no significant motif, or never ran). The other two views render normally.

### 7.7 PWM has unusual dimensions

Defensive: `_maybeHideOptionalCards` checks `Array.isArray(pwm) && pwm.length > 0`. A PWM with rows of length ≠ 4 (e.g. `[A, C, G, T, gap]` 5-column would be unusual) renders the card but lets the rendering layer fall back to a "malformed PWM" notice — phase C concern; v1 stub doesn't reach this code path.

### 7.8 `telomere_curve` field present but `d_rel` / `rate` arrays misaligned

The producer must emit arrays of equal length. The renderer should validate and fail-soft with a "curve data shape mismatch" warning, falling back to no curve. Out of scope for v1; phase C check.

## 8. What's currently NOT modelled

### 8.1 Inversion span overlap on the cohort-CO-density genome-atlas page

The genome-atlas page3 cross-atlas-reads this atlas's `crossover_track`. That page's overview-track aggregation across all candidates is **its** responsibility; this SPEC doesn't cover it.

### 8.2 Statistical test for sex × in_span interaction

Eyeball-only on v1. A v2 page could expose a chi-squared on the (sex × in_span) crosstab to test whether one sex drives the inside-inversion CO suppression more than the other. Useful when heterochiasmy is strong.

### 8.3 Per-individual CO call confidence

`events[i]` carries `indiv` but no confidence score. ngsTracts emits confidence on tracts (high / medium / low); per-event confidence on the producer side is currently coarse. A v2 viewer could filter the ideogram + curve by confidence.

### 8.4 Recombinant-haplotype handling

The inversion-atlas's `RECOMBINANT*` calls flag fish where the inversion homozygote/heterozygote assignment broke. CO events from these fish may need different treatment (the carrier-status itself is uncertain). Today this page renders all events uniformly; v2 should let the user filter on recombinant flags.

### 8.5 Centromere-aware d_rel

Per §4.3 caveat. v2 should accept per-chromosome centromere positions and compute p-arm vs q-arm relative distances separately. For catfish today the midpoint approximation is acceptable but documented.

### 8.6 Multi-candidate overlay

Today, one candidate at a time. A v2 view that overlays the telomere curves for multiple selected candidates (or compares the candidate to the chromosome's cohort-baseline LOESS) would let the reviewer spot anomalous candidates against the typical pattern.

## 9. Promotion criteria

| criterion | v1 (today) | v2 (phase C) |
|-----------|------------|--------------|
| Page mounts cleanly | ✓ | ✓ |
| Layer registry chips show "not loaded" status | ✓ | ✓ |
| Optional PRDM9 card hides when pwm absent | ✓ | ✓ |
| File-load path `data/crossovers/<candidate_id>.json` | ✗ | required |
| Ideogram view renders | ✗ | required |
| Telomere curve view renders (with LOESS + CI per sex) | ✗ | required |
| PRDM9 logo view renders when pwm present | ✗ | required |
| Per-event tooltip on ideogram | ✗ | required |
| Family-stratified bootstrap for 95% CI | ✗ | required (§4.4) |
| Failure modes §7.1–§7.6 covered | ✗ | required |
| 30+ assertion JS smoke | ✗ | required when renderer ships |

v1 is a clean scaffold; v2 ships the actual three-view rendering once the producer pipeline emits the per-candidate JSON files.

## 10. Open biological design questions

### 10.1 Pre-computed vs client-side LOESS

The page accepts both modes (§3.2). For real-data cohorts, **which should the producer default to?** Pre-computed loads instantly but locks the curve parameters; client-side lets the user tune `bandwidth` and `degree` at the cost of latency. Decision: ship producer-side pre-computed by default with `curve_params` documented, and add a "recompute with custom bandwidth" client-side override in v2.

### 10.2 LOESS bandwidth

`bandwidth = 0.3` is a typical default but candidate dependent — narrow inversions with sparse events need smaller windows; broad inversions with dense events tolerate larger. Per-candidate auto-bandwidth (e.g. AIC-minimising) is a phase-D nice-to-have.

### 10.3 Recombination units

Today the rate is events / window-bp. If a sex-specific recombination map exists (cM/Mb), the y-axis should be in cM/Mb. This is the same gap as [crossovers §9.5](SPEC_crossovers_page.md) and [interchromosomal §9.5](SPEC_interchromosomal_page.md).

### 10.4 Statistical comparison between sexes

Per §4.5 above. v2 phase D: add a per-d_rel permutation test of sex labels.

### 10.5 Per-individual baselines

When an individual contributes multiple events, those are not independent (they share a meiosis batch, a sex, a parent). Pre-aggregating events to per-individual rates and then fitting LOESS on individual-level rates would be more rigorous. Trade-off: smaller n, harder LOESS.
