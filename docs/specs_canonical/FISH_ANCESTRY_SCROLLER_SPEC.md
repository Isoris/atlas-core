# FISH_ANCESTRY_SCROLLER_SPEC — ancestry-aware inversion browser page

**Status**: SPEC ONLY. Not yet implemented. Awaiting audit.
**Source**: user mockup + accompanying design text, 2026-05-08 chat.
**Position in pipeline**: a new atlas page that consumes Stage 4
regime calls + per-RF `instant_q` (Engine B) output. Sibling page to
the regimes-page (which is the discovery/discrimination view); this
page is the **ancestry-interpretation view**.

## Identity check — this page is generic, the catfish manuscript is one user

The user's mockup illustrates the page with **Atlantic Salmon
(*S. salar*)** + SALMONv2 (2024) sample data. That is a
demonstration dataset, not the active project. The spec defines a
generic page that any species can plug into.

For the MS_Inversions_North_african_catfish manuscript, the inputs
come from the **226-sample pure C. gariepinus hatchery cohort**
(cohort 2 in the three-cohort separation; never the F1 hybrid, never
wild C. macrocephalus). The mockup's "Atlantic Salmon Atlas" project
card and "1,248 fish" sample count are placeholders; the catfish
instance will read "Catfish Atlas" and "226 fish."

## Core idea — one question this page exists to answer

> For each inversion block, do fish keep the same ancestry painting
> as the genome-wide background, or does the region switch to
> another ancestry/regime?

The page makes this comparison visible at every level:

- genome-wide (cohort average): global Q vs local Q bar chart
- per-RF-window (across the chromosome): local ancestry painting
- per-fish (inside the block): mini local-ancestry bar + |ΔQ|

The headline diagnostic is **mean |ΔQ|** — how different local
ancestry inside the block is from each fish's global ancestry. High
|ΔQ| means "this region is painted differently."

## CRITICAL FIRST — the label-switching problem

**This is the load-bearing technical content of the spec.** If
implementation skips this, the page produces fake biological stories.
Every reviewer who knows NGSadmix will catch it.

### The problem

NGSadmix (and any K-component EM admixture caller) is **label-
invariant** within a run. The model output is a Q matrix and an F
matrix; the column ordering of K components is arbitrary up to
permutation. Two independent runs of NGSadmix on overlapping data
with the same K produce two valid solutions whose columns may be
permuted relative to each other.

In the global run on the whole genome:

```
K1 = blue (e.g. North Atlantic)
K2 = orange (e.g. Baltic)
K3 = teal (e.g. Arctic)
```

In a per-RF/per-window run on a 50 kb chunk, NGSadmix may emit:

```
local_column_1 = (what was) global K2
local_column_2 = (what was) global K3
local_column_3 = (what was) global K1
```

Reading the local `.qopt` file naively produces a per-RF Q vector
that **looks like** ancestry has changed across windows, but the
biological state has not — only the column ordering has.

**If the scroller displays raw per-RF Q without alignment, the
ancestry painting will appear to flip between windows in a way that
is purely numerical artefact.** Scrolling left-right across the
chromosome will show fake "ancestry switches" at every window
boundary.

### The displayed track must always be `Q_aligned`, never `Q_raw`

The data path the scroller consumes:

```
global Q / F (whole-genome reference)
                  ↓
per-RF NGSadmix runs (instant_q / Engine B)
                  ↓
component alignment — match local K columns to global K columns
                  ↓
alignment-confidence scoring per RF
                  ↓
regime-aware neighbor smoothing
                  ↓
Q_aligned matrix (RF × fish × global_K)
                  ↓
UI ancestry painting
```

The UI **only reads `Q_aligned`**. Raw `.qopt` colors are never
exposed in the main view (debug-only toggle, off by default).

### Alignment pipeline — three levels

**Level 1: F-based alignment (preferred when local F is stable).**

The `.fopt` matrix is SNP × K allele frequencies. For each RF, take
the SNPs that have both local F estimates and global F values, then
compute the K × K correlation matrix:

```
           global_K1   global_K2   global_K3
local_1    0.12        0.91        0.20
local_2    0.10        0.22        0.88
local_3    0.95        0.15        0.18
```

Find the permutation of local columns that maximises total
correlation. Hungarian assignment over the K × K matrix is the
canonical solution; with K ≤ 6 a brute-force K! enumeration is fine
(K=3: 6 permutations; K=6: 720). The codebase already has a
`hungarian.js` helper from the band-tracking modules — reuse it.

In the example above, the best permutation is:

```
local_1 → global_K2
local_2 → global_K3
local_3 → global_K1
```

Reorder the per-RF Q columns accordingly: `Q_aligned[:, k] =
Q_raw[:, perm⁻¹[k]]`.

**Level 2: Q-based alignment fallback (when local F is unreliable).**

If the local RF has too few SNPs for stable F estimation (the
NGSadmix `.fopt` is noisy), align by comparing local Q columns to
global Q columns across fish:

```
align_score = max over permutations σ of
              Σ_k cor(local_Q[:, σ(k)], global_Q[:, k])
```

**Caveat from the user**: Q-alignment is risky for inversion
regions specifically. The whole reason this page exists is that
local Q *should* differ from global Q inside inversions — but
Q-alignment will then snap the inversion's distinctive local Q back
to the global pattern, hiding the very signal we want to see.

Q-alignment is therefore a fallback for flanking regions only.
Inside the inversion-block window range, F-alignment must succeed
or the RF is flagged ambiguous.

**Level 3: mark RF as ambiguous / unstable.**

When neither F-alignment nor Q-alignment produces a high-confidence
match (alignment score below threshold, or two permutations score
nearly equal):

```
status = FAIL
display = grey hatching (not coloured)
```

### Alignment-confidence output table

For each RF, the alignment pipeline produces a row:

```
RF_ID     perm_raw_to_global    align_method    align_score    status
RF_001    [1, 2, 3]             F-based         0.94           PASS
RF_002    [2, 3, 1]             F-based         0.89           PASS
RF_003    [3, 1, 2]             Q-based         0.71           WARN
RF_004    [NA]                  ambiguous       0.42           FAIL
```

Thresholds (audit chat to confirm against cohort data):

| score range  | status | display              |
|--------------|--------|----------------------|
| ≥ 0.85       | PASS   | solid colour         |
| 0.70 – 0.85  | WARN   | hatched colour       |
| < 0.70       | FAIL   | grey, no colour      |

### Regime-aware neighbour smoothing

After per-RF alignment, examine neighbours. If RF_n has a different
permutation than RF_{n−1} and RF_{n+1}, but those neighbours agree
with each other and have higher align_score, it is more likely that
RF_n suffered numerical instability than that biology genuinely
swapped components within a single window. Flag RF_n for review,
and (with `regime_aware_mode` ON in the toolbar) replace its
permutation with the neighbour-consensus permutation.

This is exactly the kind of guard the user calls for:

> If RF_003 alone flips but neighbours do not, it is probably label
> instability, not biology.

The regime-aware smoothing rule:

```
if  RF_n.permutation != RF_{n-1}.permutation
and RF_n.permutation != RF_{n+1}.permutation
and RF_{n-1}.permutation == RF_{n+1}.permutation
and RF_n.align_score < min(RF_{n-1}, RF_{n+1}).align_score - 0.10
then  override RF_n.permutation with neighbour consensus
      mark RF_n.status as SMOOTHED
```

### Two new UI elements driven by this layer

1. **Label-alignment confidence track** (insertable above or below
   the local-ancestry painting): per-RF colour-coded confidence
   (green = PASS, yellow = WARN, grey = FAIL/SMOOTHED).
2. **Right-panel alignment summary**:

```
Label alignment
  Method:           F-based
  Mean score:       0.91
  PASS:             94.1%
  WARN:             4.2%
  FAIL / SMOOTHED:  1.7%
```

3. **Toolbar toggle**: `Show raw labels` (debug only, off by default).

## UI layout v2 — the three numbered layers (CANONICAL, mockup v2)

Reference image: `plots/ancestry_atlas_mockup_v2.png`. This is the
canonical UI design — the previous 8-track horizontal-scroller
sketch (preserved below as "UI layout v1") was an earlier
iteration. When v1 and v2 conflict, **v2 wins**.

The page is organised as **three numbered conceptual layers** plus a
brick-metrics multi-heatmap section and a cohort-summary footer.
Each layer answers one specific question. The right side panel is
the always-on context: an explainer card, view-mode controls, the
selected-brick card, and a link to the genome view.

This section is a UI specification only. The label-switching pipeline,
brick construction rules, status flags, and operational definitions
described in the earlier sections of this spec carry over unchanged.

### Atlas-level tab routing

The page is one tab in a larger "Fish Atlas" tab strip:

```
Overview | Candidates | Ancestry | Pop Stats | Regimes | Markers | Breakpoints
```

| tab           | content                                                |
|---------------|--------------------------------------------------------|
| `Overview`    | landing page / project summary                         |
| `Candidates`  | list of inversion candidates from Stage 4 / regimes    |
| `Ancestry`    | **this spec** — ancestry-aware inversion browser       |
| `Pop Stats`   | popstats_server output (Fst / θπ / HoverE / Tajima's D)|
| `Regimes`     | the existing regimes-page (lanes + PC1 panels)         |
| `Markers`     | copy-origin painting — see `COPY_ORIGIN_PAINTING_SPEC.md` |
| `Breakpoints` | breakpoint refinement — separate spec (LG28 prototype) |

`Markers` and `Breakpoints` are out of scope for this spec but
share navigation state (selected candidate, chromosome, sample
filters).

### Page header

```
LG28: 14.20 – 18.60 Mb              [Show inversion ●]  [Show breakpoints ●]
[K = 3 ▼]  [Global Ancestry (Q)]  [How to interpret]
```

- Chromosome + viewport range as a heading.
- `Show inversion` toggle (default ON) — draws the dashed vertical
  guide lines at the inversion endpoints (15.03 Mb and 17.89 Mb in
  the mockup) across every layer.
- `Show breakpoints` toggle (default ON) — draws the breakpoint
  anchor markers (purple diamonds in the mockup) on the inversion-
  breakpoints reference row.
- `K = 3 ▼` — K-value selector (locked per dataset; the mockup
  shows K=3, the catfish cohort also uses K=3).
- `Global Ancestry (Q)` — read-only badge indicating the reference
  Q being compared against (the whole-genome `instant_q` run).
- `How to interpret` — link to documentation.

Top-right cluster:

```
[🔍] [🔍−] [🔍+]  [1.2 Mb ▼]  [◀] [▶]
```

- Zoom controls.
- Window-size selector (default 1.2 Mb visible, options to widen
  or narrow).
- Pan arrows (scroll left/right along the chromosome).

### Genome reference row

A single thin row at the top showing:

- **Genome** — the chromosome position scale (14.5 Mb, 15.0 Mb,
  15.5 Mb, ...) with light tick marks.
- **Inversion breakpoints** — the inversion interval drawn as a
  purple bar with labelled endpoints and diamond markers at the
  exact breakpoints (`15.03 Mb`, `17.89 Mb`). Labelled with the
  candidate name: `Inversion LG28-Inv1 (15.03–17.89 Mb)`.

The dashed vertical guides at the breakpoint positions extend
downward through every layer in the page. This is the visual anchor
that lets the reader see "this brick / this metric / this fish row
sits inside vs outside the inversion."

### ① Layer 1 — PC1 Band / Regime (per fish)

**Tagline**: "What local structural pattern is present? (from PCA)"
**Scope**: per-fish row × per-RF-window column.
**Data source**: Stage 4 banding pipeline output (the same data
that the regimes-page lanes panel consumes).
**Colour encoding**: PC1 band membership per fish per window.

Legend categories (`PC1 Regime`):

| colour      | band label              |
|-------------|-------------------------|
| blue        | Band 1 (Std Hom)        |
| amber       | Band 2 (Het)            |
| red         | Band 3 (Inv Hom)        |
| grey        | Mixed / Uncertain       |

Each fish (Fish_0234, Fish_0451, Fish_0789, ...) gets one row. Each
column is one RF window (50 kb in the mockup; configurable).
Inside the inversion the dominant colour pattern is the karyotype
signature: blue = Std/Std, red = Inv/Inv, amber = heterokaryotype.
Outside the inversion the rows go back to blue (the rest of the
genome's standard arrangement).

This layer is the karyotype-per-fish view. It answers "which fish
carry which arrangement, and where do the arrangement edges fall?"

A "..." row at the bottom of the visible list indicates that more
fish exist below the viewport (full cohort accessible via scroll).

### ② Layer 2 — Ancestry Bricks (per fish)

**Tagline**: "What ancestry is present locally (Q)? (aligned to global K)"
**Scope**: per-fish row × merged brick segments.
**Data source**: aligned-Q matrix (output of the label-switching
alignment pipeline) merged into bricks (per the brick-construction
rule earlier in this spec).
**Colour encoding**: brick fill is the dominant aligned-K
component; overlays per the view-mode dropdown.

Legend categories (`Ancestry (K=3)`):

| colour      | K           |
|-------------|-------------|
| blue        | K1          |
| orange      | K2          |
| teal        | K3          |
| grey        | Ambiguous / Low conf. |

Same fish rows as Layer 1 (aligned vertically so the reader can
compare arrangement and ancestry for the same fish at the same
window). Cells are merged bricks, not raw RFs — this is the
simplification layer. Brick borders are visible when `Show brick
borders` is ON (default).

Status icons render at the right edge of bricks that carry status
flags (visible in the mockup):

| icon  | meaning                  |
|-------|--------------------------|
| `▲`   | Low confidence brick      |
| `▢`   | High ΔQ (outlier)         |
| `⚠`   | Regime discordant         |
| `⊗`   | Dosage discordant         |

Multiple icons can appear on one brick. Icon rendering is governed
by the `Show warnings` toggle in the right panel (default ON).

This layer is the headline interactive layer. Clicking a brick
populates the "Selected brick" card in the right panel.

### Brick metrics — five stacked heatmap rows

Below the bricks layer, five horizontal heatmap rows visualise the
per-brick metrics across all fish × all windows. Each row uses the
same fish ordering as Layer 2 above. This is the "metric matrix"
view: each metric is shown as a dedicated heatmap, not as an overlay
on the bricks.

```
Brick metrics                            (overlays / color modes)
  ΔQ (local vs global)                purple gradient   [0 .. 1]
  Heterozygosity (π) (relative z)     diverging green/red [-2 .. +2]
  Entropy (ancestry uncertainty)      orange gradient    [0 .. 1]
  Confidence (alignment)              green gradient     [0 .. 1]
  Dosage concordance (with regime)    categorical: green / amber / red
```

Detail per row:

| metric              | encoding                            | range / categories         |
|---------------------|-------------------------------------|----------------------------|
| `ΔQ (mean abs)`     | sequential purple, white → deep     | 0 to 1                     |
| `Het. z-score`      | diverging red ↔ neutral ↔ green     | −2 to +2                   |
| `Entropy`           | sequential orange, pale → saturated | 0 to 1                     |
| `Confidence`        | sequential green, pale → saturated  | 0 to 1                     |
| `Dosage concordance`| categorical                         | Concordant / Partial / Discordant |

The heatmap rows are visible when `Show metrics heatmaps` is ON in
the right panel (default ON). When OFF, the section collapses and
the page shows only the three numbered layers.

The categorical mapping for Dosage concordance:

- **Concordant** (green): brick's dominant K matches the cohort's
  per-dosage-state expected K for this fish.
- **Partial** (amber): brick's Q vector is closer to expected
  but mean_delta_Q above the Partial threshold (audit chat to
  define exact cutoffs).
- **Discordant** (red): explicit DOSAGE_DISCORDANT flag (per the
  operational rule defined earlier in this spec).

A small status-icon legend strip sits at the bottom of the brick-
metrics block:

```
Each column = RF window (50 kb)
  [▢] Low confidence brick
  [▢] High ΔQ (outlier)
  [▢] High het.
  [⚠] Regime discordant
  [⊗] Dosage discordant
```

(The 50 kb window size is the mockup default. Real window sizes
are project-configurable; see the implementation notes earlier.)

### ③ Layer 3 — Brick summary (cohort view)

**Tagline**: "Majority ancestry across fish + Fraction agreement (cohort)"
**Scope**: cohort-level, per-window summary. Two stacked tracks.

#### Track 3a — Majority ancestry across fish

Horizontal bar coloured by the cohort's majority K at each window:

```
[ K1 (blue) ] [ K2 (orange) ] [ K3 (teal) ] [ K2 (orange) ] [ K1 (blue) ]
```

Formula:

```
majority_K[w] = argmax_K  Σ_fish  1(brick_dominant_K[fish, w] == K)
```

Single-row track running the full chromosome viewport. Tells the
reader at a glance "this region of the chromosome is K1-majority,
this region is K2-majority." The transitions usually align with
the inversion boundaries when the inversion carries an
arrangement-specific ancestry signal.

Legend (`Majority ancestry`):

| colour | K   |
|--------|-----|
| blue   | K1  |
| orange | K2  |
| teal   | K3  |

#### Track 3b — Fraction agreement (cohort)

Area chart with y-axis 0..1, showing what fraction of the cohort
shares the majority K assignment at each window:

```
fraction_agreement[w] = (1 / N_fish) · Σ_fish  1(brick_dominant_K[fish, w] == majority_K[w])
```

Values near 1.0 → almost the entire cohort agrees on the majority K
at this window (very coherent). Values near 1/K (0.33 for K=3) →
the cohort is split (no clear majority). Dips in this chart
typically appear at boundary regions and at windows where the
cohort is genuinely heterogeneous.

Legend: a grey-to-black gradient bar labelled "Agreement
(fraction)" from 0 to 1.

Together, Tracks 3a + 3b answer "is the cohort coherent at this
window, and which ancestry does the majority carry?" This is the
single most useful cohort-level summary the page produces — it
lets the user judge whether per-fish discordance signals are
real (cohort agrees, this fish is the outlier) or noise (cohort
is split, no clear background to be discordant against).

### Right side panel — context + controls + selection

The right side panel is divided into four blocks, top to bottom.

#### Block 1 — Context explainer card

A small explainer card that documents the three layers in plain
language. Visible by default; collapsible via a `?` toggle.

```
Context: What do these layers mean?

① PC1 Band / Regime
    Local structural pattern (from PCA). Shows bands that
    correspond to standard / heterozygote / inversion patterns.

② Ancestry Bricks
    Local ancestry composition (Q) aligned to global K. Bricks are
    merged segments of coherent ancestry.

③ Brick metrics
    Quantify how unusual or uncertain each brick is (ΔQ,
    heterozygosity, entropy, confidence, concordance).
```

Note that the explainer numbers the *brick metrics* row as "③" in
the panel; this is a labelling convention for the context card,
not a layer-numbering conflict with Layer 3 (Brick summary). The
implementation should pick one numbering scheme and use it
consistently. **Recommendation**: keep the three-layer numbering as
the source of truth (PC1 Band = ①, Ancestry Bricks = ②, Brick
summary = ③), and label the brick-metrics row as "Brick metrics"
without a circled number to avoid confusion. The audit chat should
verify this is consistent across the spec, the explainer card, and
any code identifiers.

#### Block 2 — View-mode + overlay controls

```
View mode (brick color)
  [Ancestry (K) ▼]

Overlay
  [✓] Show metrics heatmaps
  [✓] Show brick borders
  [✓] Show warnings
```

`View mode (brick color)` is the dropdown that swaps what the
brick fill encodes. Same six options as defined in the brick
section above:

```
Ancestry (K)        (default — fill = dominant K)
Heterozygosity      (fill = het z-score)
ΔQ                  (fill = mean_delta_Q)
Entropy             (fill = mean_entropy)
Confidence          (fill = alignment_confidence)
Discordance         (fill = REGIME_/DOSAGE_DISCORDANT highlight)
```

When the view mode is anything other than `Ancestry (K)`, Layer 2
becomes a single-metric visualisation. The K-ancestry legend in
the upper right swaps to show the relevant colour scale.

Overlay toggles:

- `Show metrics heatmaps` (default ON) — show the five-row
  metrics block between Layer 2 and Layer 3.
- `Show brick borders` (default ON) — draw thin lines between
  adjacent bricks in Layer 2.
- `Show warnings` (default ON) — render the status icons
  (▲, ▢, ⚠, ⊗) on flagged bricks.

#### Block 3 — Selected brick card

Click a brick in Layer 2 → this card populates. Mockup example:

```
Selected brick                                    (click in track)
Fish:                Fish_1012
Interval:            16.40 – 16.82 Mb (420 kb)
Dominant ancestry:   K2 (0.78)
ΔQ (mean abs):       0.62
Heterozygosity z:    +1.74
Entropy:             0.21
Confidence:          0.87
Regime (PC1 band):   Band 3 (Inv Hom)
Dosage state:        Het (↥)

Status:
  [▢] High ΔQ    [▢] High het.    —

[ ↗ Open in genome view ]
```

The status row uses badge-style flags showing only the flags that
fire. The trailing "—" is a placeholder for an empty status (no
flags fire). The "Open in genome view" link sends the user to a
genome-browser view focused on this brick's interval.

The card never says "strange," "weird," or "interesting." Every
field is a measurable value or a defined label.

#### Block 4 — Implicit (always present)

The colour-scale legends (`ΔQ (mean abs)`, `Het. z-score`, `Entropy`,
`Confidence`, `Concordance`) appear in their own column to the right
of the metrics heatmap rows, mid-page. These are not in the side
panel proper but are visually grouped with the right side because
they describe the heatmap encodings.

### Footer

A small explainer line at the bottom of the page:

```
ⓘ Ancestry bricks are aligned to the global ancestry model (K=3).
   Colors show dominant ancestry. Overlays show deviation,
   heterozygosity, uncertainty, and concordance with local
   regime/dosage.
```

This is the single-line manuscript-safe description of what the
page shows. The implementation should keep this line visible at all
zoom levels — it's the page's running disclaimer about what the
colours mean.

### Cross-layer alignment guarantees

The three layers and the metrics heatmap rows must share:

- **Identical fish row ordering** across Layer 1, Layer 2, and the
  five metrics rows. Sorting by any column resorts all of them.
- **Identical RF window column ordering** across all per-fish
  layers AND the cohort summary tracks.
- **Identical horizontal coordinate system** — the dashed inversion
  guides at 15.03 Mb and 17.89 Mb must hit the same pixel column
  on every track. The chromosome scale at the top is the source
  of truth.

Violating any of these turns the page from a diagnostic tool into
a misleading visual. The audit chat must verify the implementation
enforces these alignment guarantees.

## UI layout v1 — the eight tracks and four panels (early sketch — superseded)

This was the first mockup sketch (ancestry_scroller_mockup.png), an
8-track horizontal-scroller design with a chromosome bar + 7 data
tracks + a per-fish detail table below. **Superseded by the v2
canonical layout above** but preserved here because parts of the
spec (alignment-pipeline references, per-RF Track 2 colour rules,
switch-rate formula) refer to its track numbering.

The v1 layout is structured as five regions: top bar, left sidebar,
central browser, right side panel, bottom fish table.

### Top bar — biological context

Species → Chromosome / LG → Candidate inversion block.

Three independent dropdowns. The first sets the species (which
chooses the dataset, sample list, K value, and reference assembly);
the second narrows to one chromosome; the third selects one
candidate inversion block within that chromosome. The selected
block name (e.g. "LG28:15.1–18.0 Mb") propagates into every track
and panel below.

Tabs: `Overview | Ancestry | Regimes | Dosage | Markers`. This
spec covers only the Ancestry tab. The Regimes tab is the existing
regimes-page from the previous specs; Dosage will be the
dosage-overlay page (per `dosage_overlay.js`); Markers will be
copy-origin painting (per `COPY_ORIGIN_PAINTING_SPEC.md`).

### Left sidebar — navigation + filters

**Project card** — dataset name, sample count, SNP count. Generated
from the species selection.

**Candidates (Inversion Blocks)** — scrollable list with search and
filter icon. Each entry:

```
LG28:15.1–18.0 Mb
Span: 2.9 Mb     High shift
```

Plus a coloured dot indicating shift tier (red = high, amber =
moderate, green = low). Shift tier is derived from `mean_abs_dQ` —
see scoring section below. The dot lets the user scan many
candidates quickly.

**Filters / Modes** — five toggles:

| toggle                       | default | effect                                                 |
|------------------------------|---------|--------------------------------------------------------|
| `Show only high-shift blocks`| ON      | filter the candidates list to mean_abs_dQ ≥ threshold  |
| `Regime aware mode`          | ON      | use neighbour-consensus alignment smoothing            |
| `Linked neighboring RFs`     | ON      | when scrolling, prefetch ±N RFs around the viewport    |
| `Show genes`                 | OFF     | overlay a gene track (when annotation is available)    |
| `Show recombination rate`    | OFF     | overlay ρ if pyrho/LDhat results are available         |

**Reset filters** — button. Restores defaults.

### Central browser — the eight tracks (top to bottom)

#### Track 1 — chromosome bar

Full chromosome with the selected inversion block highlighted in
the chromosome's coordinate space. Arrows on either side scroll
the viewport left/right along the chromosome. The block highlight
is the navigational anchor — clicking it recenters the viewport
on the block.

Reference: the existing "Inversion block: 15.1–18.0 Mb" indicator
in the mockup.

#### Track 2 — local ancestry painting

The headline track. Each row is one fish; each cell is one RF
window; the cell colour is the dominant aligned-K component (K1
blue, K2 orange, K3 teal in the K=3 case). Within a cell, the
colour saturation/opacity encodes the dominant-K probability (full
saturation = ≥ 0.8, partial = mixed).

Rendering rules:
- Use **aligned Q only**. Never raw.
- Cells with status FAIL render as grey hatched (the "Unassigned /
  Missing" legend entry in the mockup).
- Cells with status WARN render at reduced alpha so the user can
  see they are uncertain without losing the colour signal entirely.
- Fish rows are sorted by Q1-similarity-to-cohort-mean by default;
  alternate sorts (by |ΔQ|, by inversion state, by switch count)
  are toolbar options.

For 226 fish in the catfish instance, the track is 226 rows tall;
for 1,248 in the salmon mockup, more rows. Adaptive row height
based on viewport; minimum 1 px per row.

#### Track 3 — regime (state)

Categorical band running the chromosome's length, showing the
Stage-4 regime call per RF (Regime A / Regime B / Regime C / ...).
This consumes the existing regimes-page Stage-4 output — the same
`pattern_class` and `consensus_partition` data that the lanes and
PC1 panels show.

The "Regime A" inside the inversion + "Regime B" / "Regime C"
flanking is exactly the shape that motivates this view: a clean
regime block aligned with the inversion's structural boundaries.

#### Track 4 — switch rate (per window)

Bar chart, one bar per RF, showing the fraction of fish that
change their dominant-aligned-K assignment between this RF and the
previous one. Peaks indicate boundaries — the user expects these
at the inversion edges, and (sometimes) at internal sub-block
transitions for nested or COHERENT_SPLIT regimes.

Formula:

```
switch_rate[w] = (1 / N_fish) · Σ_fish  1(argmax K[fish, w] ≠ argmax K[fish, w-1])
```

Compute on **aligned Q**. Raw Q switch rates are dominated by
label-switching noise and are biologically meaningless.

#### Track 5 — entropy

Line plot, one value per RF, showing Shannon entropy of the cohort-
average aligned Q at that window:

```
H[w] = − Σ_k  mean_fish(Q_aligned[fish, w, k]) · log2(...)
```

Low entropy → cohort is cleanly assigned to one (or few) components
at this window. High entropy → mixed / uncertain.

For inversion analysis, a clean inversion block should have
**coherent** (low-ish) entropy inside, with potentially elevated
entropy at the boundaries. Whole-block high entropy is a red flag
— either the block is genuinely mosaic, or alignment is failing
inside it.

#### Track 6 — dosage / band pattern heatmap

Per-RF dosage classification heatmap, sourced from
`dosage_overlay.js` and the dosage_bridge endpoint. Each cell is
coloured by the band's dosage class (HOM_REF blue / HET white /
HOM_INV red / AMBIGUOUS grey — same palette as
`DOSAGE_CLASS_COLOURS` from regimes_panel.js).

This track is the *cross-check* against ancestry: if the ancestry
shift inside the inversion matches a dosage cluster pattern, that's
strong evidence the region carries arrangement-specific structural
haplotypes. If the ancestry shift exists but dosage is uniform, the
shift is probably population structure or family LD, not an
inversion-specific signal.

#### Track 7 (optional) — label-alignment confidence

The new track introduced above. Per-RF green/yellow/grey stripe
showing alignment status. Off by default; toolbar toggle
`Show alignment confidence`.

#### Track 8 (optional) — gene track / recombination rate track

Standard genome-browser overlay tracks. Off by default; toggled
from the sidebar.

### Right side panel — selected inversion summary

The persistent info panel for the currently selected block. Mockup
shows:

```
Selected Inversion Block                          [pinned] [High shift]
  Chromosome:        LG28
  Start:             15.1 Mb
  End:               18.0 Mb
  Span:              2.9 Mb
  Dominant regime:   Regime A
  Switch rate (mean):     0.128
  Mean |ΔQ|:              0.342
  Entropy (mean):         0.62 bits
```

Below that, the **Global Q vs Local Q** bar chart — the bridge
between cohort-level genome-wide ancestry and within-block
ancestry. Per-K bars showing both values:

```
       Global Q (whole genome)    Local Q (in block)
K1     43%                        71%
K2     37%                        19%
K3     20%                        10%
```

Interpretation in the mockup example: the block is K1-enriched and
K2/K3-depleted relative to the genome-wide average. This is the
"painted differently" signal in numeric form.

Below the bar chart, the **Top Fish That Switch in This Block**
table:

```
Fish ID    Switches    |ΔQ|     Regime
RF_0137    7           0.68     A
RF_0589    6           0.62     A
RF_0921    6           0.60     A
RF_0204    5           0.56     A
RF_1108    5           0.54     A
```

Sorted by `|ΔQ|` descending. "View all switching fish →" link
expands the bottom table.

### Bottom panel — Selected Fish table

Per-fish detail rows for fish currently in the selection (when no
filter is active, this shows all fish; when the user clicks bars in
the right panel, the selection narrows). Columns:

- **Fish ID** (with star icon = bookmark)
- **Global Q (K1 / K2 / K3)** — three values from the whole-genome run
- **Local ancestry across 15.1–18.0 Mb (mini view)** — per-fish
  horizontal mini painting using aligned Q
- **Dominant regime** — Regime A/B/C badge
- **Inversion state** — Heterozygous / Homozygous (inv) / Homozygous
  (std) — pulled from dosage/karyotype caller
- **|ΔQ|**
- **Switches** — count of dominant-K transitions within the block
- **Entropy** — mean Shannon entropy across the block for this fish
- **Sparkline (switch rate)** — tiny per-window switch indicator

Sort dropdown: `|ΔQ| (desc)` default; alternatives are
`Switches (desc)`, `Entropy (desc)`, `Inversion state`. Export to
TSV available.

## Ancestry bricks — derived simplification layer (Layer 2 detail)

This section is the expanded detail for **Layer 2** in the v2 UI
layout above. The brick layer is the headline interactive layer
of the canonical page. Construction rules, status flags, and the
operational definitions of REGIME_DISCORDANT and DOSAGE_DISCORDANT
live here.

### What bricks are and what they are NOT

A **brick** is a contiguous run of RF windows where local ancestry is
coherent after label-switch correction. Bricks are a **simplification
layer on top of the per-RF aligned-Q painting**. They are not a
separate discovery system, not a new biological object, and never
the headline result.

The framing matters:

> ✅ "Ancestry bricks are local-ancestry summaries used to interpret
>     inversion candidates. They are supporting evidence, not the
>     main result."
>
> ❌ "We discovered 500 ancestry bricks."

Calling a count of bricks a "discovery" would turn this layer into
the same kind of fake biological object the project carefully avoids
elsewhere (cf. "POD found" vs "POD-compatible" in
`REGIME_ANNOTATION_SPEC.md`). The same restraint applies here.

### What bricks are useful for

Exactly four things:

1. **Visual simplification.** Replace thousands of RF cells with a
   handful of merged segments. Cleaner page, faster to read.
2. **Brick-vs-inversion boundary comparison.** Does the ancestry
   brick boundary match the inversion block boundary?
   - Brick = inversion → strong arrangement-specific haplotype signal
   - Brick larger than inversion → introgressed haplotype containing
     the inversion
   - Brick smaller than inversion → nested / partial signal
   - Brick unrelated to inversion → ancestry background, not
     inversion-specific
3. **Fish-level QC and discovery.** A fish with one anomalous brick
   inside a cohort-coherent region may be recombinant, mislabelled,
   structurally different, a rare-haplotype carrier, or a bad sample.
4. **Manuscript summary statements.** "The candidate contained a
   2.1 Mb K1-enriched ancestry brick overlapping 72% of the
   inversion interval, with sharp transitions near both inferred
   breakpoints" reads much better than "local Q varied across many
   RF windows."

### Brick construction — operational rule

Bricks are constructed per-fish from the aligned-Q matrix. The
merging rule:

```
For each fish, walk RFs in genomic order.
  RF_n joins the current brick iff:
    1.  argmax(Q_aligned[fish, n]) == current_brick.dominant_K
    2.  Q_aligned[fish, n, dominant_K] >= min_purity (default 0.6)
    3.  RF_n.alignment_status in {PASS, WARN, SMOOTHED}
    4.  No Stage-4 regime boundary lies between RF_n and RF_{n-1}
        (regime-aware merging)

  Otherwise, close the current brick and start a new one.

  RFs with alignment_status == FAIL break bricks (they are gap
  markers, not joined to anything).
```

Constants (audit chat to confirm against cohort data):

| name              | default | meaning                                       |
|-------------------|---------|-----------------------------------------------|
| `min_purity`      | 0.6     | minimum dominant-K probability per RF to join |
| `min_brick_length`| 3 RFs   | bricks shorter than this are tagged FRAGMENT  |
| `min_brick_bp`    | 50 kb   | bricks shorter than this (in bp) are FRAGMENT |

Bricks tagged FRAGMENT are rendered with reduced opacity and not
counted in aggregate statistics — they're below the resolution
threshold for confident interpretation.

### Per-brick metrics

Each brick stores the following:

| field                     | type   | meaning                                  |
|---------------------------|--------|------------------------------------------|
| `brick_id`                | str    | `<fish_id>__<chrom>__<start_bp>__<end_bp>` |
| `fish_id`                 | str    |                                          |
| `chrom`                   | str    |                                          |
| `start_bp`                | int    |                                          |
| `end_bp`                  | int    |                                          |
| `length_bp`               | int    |                                          |
| `n_RF_windows`            | int    | how many RFs were merged                 |
| `dominant_K`              | int    | the aligned-K id                         |
| `mean_local_Q`            | float[]| K-length vector, mean per-component Q    |
| `global_Q`                | float[]| K-length vector, fish's whole-genome Q   |
| `mean_delta_Q`            | float  | mean abs diff between local and global Q |
| `mean_entropy`            | float  | Shannon entropy of mean_local_Q          |
| `heterozygosity`          | float  | per-fish per-brick observed HET fraction |
| `heterozygosity_z`        | float  | z-score vs cohort median at same windows |
| `ROH_overlap_fraction`    | float  | overlap with ngsF-HMM ROH calls          |
| `alignment_confidence`    | float  | min align_score across constituent RFs   |
| `boundary_sharpness`      | float  | from existing boundary detector at this  |
|                           |        | brick's edges                            |
| `overlap_with_inversion`  | float  | fraction of brick inside the inversion   |
|                           |        | block window range                       |
| `overlap_with_regime`     | str    | Stage-4 regime A/B/C that overlaps most  |
| `cohort_majority_K`       | int    | most common dominant_K among other fish  |
|                           |        | at these windows                         |
| `rarity_score`            | float  | fraction of cohort with dominant_K != this brick's K |
| `dosage_state`            | str    | HOM_REF / HET / HOM_INV / AMBIGUOUS at this brick |
| `regime_state_fish`       | str    | fish-specific regime pattern in this brick |
| `status_flags`            | str[]  | list of annotation labels (see below)    |

`heterozygosity_z` definition: for each RF in the brick, get the
cohort median HET at that RF; mean those medians for the brick's
"expected H"; z-score the fish's observed brick H against the cohort
SD. This is the per-brick analog of cohort-baseline anomaly scoring.

### Per-brick annotation labels (NOT "strange")

> "Different brick ≠ strange." A brick is interesting only when it
> differs from the cohort expectation in a **specific measurable
> way**. The UI uses neutral, measurable labels — never "weird" or
> "strange."

The label vocabulary:

| label                 | trigger condition                                       |
|-----------------------|---------------------------------------------------------|
| `COMMON`              | `rarity_score < 0.10` (brick's K matches cohort majority) |
| `RARE_ANCESTRY`       | `rarity_score >= 0.80` (≤20% of cohort share this K here) |
| `HIGH_HET`            | `heterozygosity_z >= +2.0`                             |
| `LOW_HET`             | `heterozygosity_z <= −2.0` (potentially ROH-like)      |
| `ROH_LIKE`            | `ROH_overlap_fraction >= 0.5` AND `heterozygosity_z <= −1.0` |
| `HIGH_DELTA_Q`        | `mean_delta_Q >= 0.30`                                  |
| `LOW_CONFIDENCE`      | `alignment_confidence < 0.70`                           |
| `REGIME_DISCORDANT`   | brick's regime_state_fish disagrees with cohort consensus regime at this position |
| `DOSAGE_DISCORDANT`   | brick's dominant_K is inconsistent with the fish's dosage_state at this block (rule defined below) |
| `BOUNDARY_BRICK`      | brick spans an inversion breakpoint (within ±1 RF)      |
| `RECOMBINANT_LIKE`    | brick starts AND ends within the inversion AND is sandwiched between two bricks of a different K |
| `FRAGMENT`            | brick shorter than `min_brick_length` or `min_brick_bp` |

A brick can carry multiple labels simultaneously. The status_flags
field is an unordered set.

### REGIME_DISCORDANT definition

The Stage-4 pipeline emits a `consensus_regime` per inversion block
(Regime A, B, C, ...). Each regime is associated with a characteristic
ancestry profile across the cohort. For a fish's brick at position
(chrom, start, end):

```
cohort_consensus_K_at_brick = argmax_K  Σ_fish  Q_aligned[fish, brick, K]
                              (excluding this fish)
brick.regime_state_fish     = labelled by which regime's typical K
                              profile this brick best matches

REGIME_DISCORDANT iff brick.regime_state_fish disagrees with the
                     cohort_consensus_regime at this block
```

The audit chat should verify the regime → ancestry-profile mapping
is well-defined (a regime is currently a Stage-4 partition over
target bands; pairing it with an ancestry profile requires a
cohort-level summary).

### DOSAGE_DISCORDANT definition

If the dosage classifier (from `dosage_overlay.js`) labels a fish's
arrangement state as HOM_INV at this block, and the regime-aware
ancestry expectation is that HOM_INV fish should be K1-dominant
(say) at this block, but this fish's brick is K2-dominant, the
brick is DOSAGE_DISCORDANT.

Operational rule:

```
For each block, the cohort yields three mean Q profiles:
  E_HOM_REF[K]   = mean Q across fish in HOM_REF dosage state
  E_HET[K]       = mean Q across fish in HET dosage state
  E_HOM_INV[K]   = mean Q across fish in HOM_INV dosage state

For a fish with dosage_state D and brick mean_local_Q L:
  expected_K = argmax_K  E_D[K]
  fish_dominant_K = brick.dominant_K
  DOSAGE_DISCORDANT iff expected_K != fish_dominant_K
                       AND mean_delta_Q >= 0.20
                       (i.e. genuinely off, not just borderline)
```

This is one of the most interesting flags — it's the candidate
filter for fish whose ancestry doesn't match their structural
karyotype. Possible explanations: heterokaryotype-with-recombination,
introgressed haplotype, dosage call error, ancestry call error.
The UI does not adjudicate — it just flags.

### Color modes — same bricks, swappable encoding

The brick layer has **six color modes**, swappable via a toolbar
dropdown. The brick geometry stays the same; only the encoded
metric changes.

| mode                       | fill encodes                                          |
|----------------------------|-------------------------------------------------------|
| `ancestry` (default)       | dominant_K → K1 blue / K2 orange / K3 teal / ...      |
| `heterozygosity`           | dark = low H, bright = high H                         |
| `delta_Q`                  | pale = local≈global, strong = local≠global            |
| `entropy`                  | clean = low entropy, messy = high entropy             |
| `discordance`              | grey = concordant, red = REGIME_/DOSAGE_DISCORDANT    |
| `confidence`               | solid = PASS, hatched = WARN, grey = FAIL/FRAGMENT    |

Each mode answers one question:
- `ancestry`: which K?
- `heterozygosity`: diverse or homozygous?
- `delta_Q`: locally shifted from global?
- `entropy`: assignment confident?
- `discordance`: which bricks need inspection?
- `confidence`: where did alignment work?

### Default composite encoding (no mode change)

In the default `ancestry` mode, additional channels carry secondary
information without switching modes:

| channel    | encodes                                                  |
|------------|----------------------------------------------------------|
| fill color | dominant_K (the ancestry component)                      |
| opacity    | alignment_confidence (high = solid, low = translucent)   |
| border     | heterozygosity (yellow border = HIGH_HET, normal = none) |
| icon       | discordance flags (⚠ for REGIME_/DOSAGE_DISCORDANT)      |

This is information-dense. A simpler "ancestry-only" view (fill
only, no overlays) is one click away via a toolbar toggle
`Show overlays`.

### Brick-click detail card

Clicking a brick opens a side card:

```
Brick: LG28:15.84–16.22 Mb        (380 kb, 8 RFs)
Fish: RF_0137
Dominant ancestry: K2  (Baltic)
Cohort majority here: K1  (rarity_score 0.84)
Mean local Q: [K1: 0.18, K2: 0.71, K3: 0.11]
Global Q:     [K1: 0.41, K2: 0.36, K3: 0.23]
Mean |ΔQ|: 0.48
Heterozygosity: 0.39  (z = +2.1)
Mean entropy: 0.62 bits
Alignment confidence: 0.91 (PASS)
Boundary sharpness (left/right): 0.78 / 0.92
Overlap with inversion: 100%
Regime (cohort): A
Regime (this fish here): B
Dosage state: heterozygous inversion
Status flags: RARE_ANCESTRY, HIGH_HET, REGIME_DISCORDANT
```

The card never says "weird" or "strange." It states the measurable
deviations and lets the user decide what they mean.

### Three layers for one inversion candidate

The page's central browser, with bricks enabled, shows three
related layers stacked vertically:

```
Layer A — RF-level local ancestry painting
          (existing Track 2 — raw aligned-Q cells)

Layer B — merged ancestry bricks
          (NEW — same fish rows, but cells merged into bricks
           with optional borders/icons/opacity)

Layer C — inversion / regime / dosage block bar
          (existing Track 3 — cohort-level regime call)
```

The user can toggle Layer B with `Show ancestry bricks`. When ON,
Layer A renders at 30% opacity behind the bricks (so the RF detail
is still visible) and Layer B sits on top. When OFF, only Layer A
is rendered.

The headline biological question the three layers answer together:

> Do ancestry bricks align with inversion regimes?

If the brick layer reproduces the inversion regime boundaries
cleanly, the inversion is carrying an arrangement-specific
ancestry-distinguishable haplotype. If the brick layer is unrelated
to the regime boundaries, the inversion is not the same object as
the ancestry signal.

### Per-brick output files

Two new TSV files extend the offline output:

```
06_ancestry_bricks.tsv             one row per fish-brick
07_brick_annotations.tsv           expanded status_flags + computed
                                   discordance details
```

`06_ancestry_bricks.tsv` columns: all per-brick metrics listed
above, one row per (fish_id, chrom, start_bp).

`07_brick_annotations.tsv` columns: brick_id, status_flag,
trigger_metric, trigger_value, comparison_baseline. Designed so the
table can be filtered to "all bricks with REGIME_DISCORDANT in
LG28:15.1–18.0 Mb" with one SQL-style query.

### What this layer does NOT do

- Discover new inversions. Bricks summarise ancestry inside
  known candidates; they don't propose new candidates.
- Decide whether a fish is "good" or "bad." Discordant bricks are
  flags for inspection, not exclusions.
- Replace the per-RF painting. The RF layer is the ground-truth
  data; bricks are derived. When in doubt, look at the RFs.
- Count as biological findings on their own. The manuscript-safe
  language is "the inversion is associated with a K1-enriched
  ancestry brick," not "this brick is a discovery."

## Metrics produced — the diagnostic numbers

Per inversion block:

| metric                    | meaning                                          |
|---------------------------|--------------------------------------------------|
| `mean_abs_dQ`             | mean across fish and K of \|local_Q − global_Q\| |
| `mean_switch_rate`        | mean per-RF dominant-K switch fraction           |
| `mean_entropy`            | mean Shannon entropy of per-RF cohort-average Q  |
| `dominant_regime`         | from Stage 4 (Regime A / B / C / ...)            |
| `shift_tier`              | derived label: high / moderate / low             |
| `n_bricks_total`          | total bricks across cohort in this block (info only — not a discovery count) |
| `n_fish_with_brick_overlap` | fish whose dominant brick overlaps the block ≥ 50% |
| `n_discordant_bricks`     | bricks flagged REGIME_DISCORDANT or DOSAGE_DISCORDANT |
| `cohort_majority_K_block` | most common dominant_K among cohort bricks inside the block |

Shift tier thresholds (audit chat to confirm against cohort data):

| mean_abs_dQ range | label    |
|-------------------|----------|
| ≥ 0.25            | high     |
| 0.10 – 0.25       | moderate |
| < 0.10            | low      |

Per fish per block:

| metric                    | meaning                                          |
|---------------------------|--------------------------------------------------|
| `abs_dQ_fish`             | mean across K of \|local_Q − global_Q\| for this fish |
| `n_switches_fish`         | count of dominant-K transitions across the block |
| `mean_entropy_fish`       | mean per-RF Shannon entropy for this fish        |
| `n_bricks_fish`           | bricks this fish has inside the block            |
| `longest_brick_bp`        | longest brick this fish has inside the block     |
| `brick_status_flags_fish` | union of all status_flags across this fish's bricks |

## Output files

```
01_alignment_summary.tsv            per-RF alignment table (perm, method, score, status)
02_aligned_Q_matrix.tsv.gz          RF × fish × K (long-format, aligned only)
03_local_vs_global_dQ.tsv           per-fish-per-block |ΔQ| stats
04_block_metrics.tsv                per-block summary (mean_abs_dQ, switch_rate, etc.)
05_top_switching_fish.tsv           ranked per-block fish list
06_ancestry_bricks.tsv              one row per fish-brick (all metrics from
                                    "Per-brick metrics" section)
07_brick_annotations.tsv            expanded status_flags + computed
                                    discordance details
```

These are precomputed offline (e.g. on LANTA via a R/Python batch)
and served to the atlas by the `popstats_server` pattern. A new
endpoint:

```
GET /api/ancestry_scroller/blocks?chrom=...
GET /api/ancestry_scroller/block?id=LG28_15.1_18.0
GET /api/ancestry_scroller/alignment_summary?chrom=...
GET /api/ancestry_scroller/bricks?chrom=...&block_id=...
GET /api/ancestry_scroller/brick_annotations?brick_id=...
```

The atlas-side scroller code consumes only the precomputed
`aligned_Q_matrix` + `block_metrics` + `alignment_summary`. It does
NOT run NGSadmix at request time, and it does NOT do alignment
in-browser. Alignment is a server-side / batch step.

## Naming convention — applies here too

This page consumes heterozygosity-related statistics in the
right-panel summary and the per-fish table. The naming convention
from `REGIME_ANNOTATION_SPEC.md` applies:

- `HWE_FIS` (not bare `FIS`) for any heterozygosity-excess statistic
  shown in the per-block summary.
- `arrangement_FST_like` (not bare `FST`) for any between-
  arrangement differentiation statistic.
- The I/S collision rationale: in an inversion-context atlas, "FIS"
  near "STD/INV" is ambiguous (I = Inversion vs I = Inbreeding).
  The `HWE_` prefix forces the correct reading.

## Audit questions for the next chat

1. **Label-alignment validation**. The whole spec depends on the
   alignment pipeline working. The audit chat should:
   - Verify the F-based correlation method is appropriate for the
     C. gariepinus instant_q output. (NGSadmix .fopt format,
     SNP overlap between local and global runs.)
   - Test alignment confidence on a known-stable region and on a
     known-unstable region (sparse SNP coverage). Confirm thresholds.
   - Verify Hungarian assignment is used (or that K! brute force
     is appropriate for the project's K range — K ≤ 6).
2. **Q-alignment fallback safety in inversion regions**. The user
   flagged this explicitly: Q-alignment will hide the very signal
   the page is built to show. Verify that the implementation does
   NOT fall back to Q-alignment inside the inversion block window
   range, only in flanking regions.
3. **Regime-aware smoothing rule**. The 0.10 score-gap threshold
   in the smoothing rule is a starting value. Test on a cohort
   with known label-switching events.
4. **Per-RF NGSadmix stability for small RFs**. The user notes:
   "Per-RF NGSadmix may not estimate ancestry components well if
   the RF has too few SNPs." What's the minimum SNP count per RF
   for stable estimation in the catfish cohort? This determines
   the page's effective resolution.
5. **`mean_abs_dQ` calculation polarity**. After alignment, |ΔQ|
   should be invariant to which K is "K1." But the per-K
   contributions (K1 enriched, K2 depleted) DO depend on the
   alignment being correct. Sanity-check that the per-K bar chart
   in the right panel uses aligned-K values, never raw.
6. **Shift-tier thresholds**. 0.10 / 0.25 are starting values.
   The audit chat should compute the empirical distribution of
   `mean_abs_dQ` across all candidate blocks in the cohort and
   propose cohort-appropriate thresholds.
7. **Performance budget**. 226 fish × ~30,000 RFs × K=3 → ~20 MB
   of aligned-Q data per chromosome. Streaming this to the browser
   on chromosome change should be fast. The 1,248-fish salmon
   mockup is ~100 MB per chromosome — already at the edge of
   in-browser viability. The audit chat should decide whether
   row-streaming or progressive-resolution loading is needed.
8. **Cohort identity**. The mockup uses salmon for illustration.
   The implementation must never mix species. The dataset
   selector at the top must be the single source of truth, and
   the project card must reflect that selection. For the
   MS_Inversions manuscript, this is always the
   226-sample pure C. gariepinus cohort. Cross-cohort comparison
   (e.g. catfish vs salmon) is out of scope.
9. **Connection to instant_q**. `instant_q` is the existing
   Engine B C++ ancestry caller in MODULE_2B. The page consumes
   its output. Verify:
   - The `.qopt` and `.fopt` file paths for per-RF runs are
     documented and available.
   - The global Q/F reference is the same `instant_q` run that
     produced the genome-wide ancestry call used elsewhere in
     the project (not a separate run with different settings).
   - The K value used per-RF matches the global K.
10. **What if K varies between species?** The salmon mockup uses
    K=3. The catfish cohort uses what K (also 3, per the existing
    MODULE_2B analysis)? Verify K is fixed per-species and that
    the UI legend updates accordingly.
11. **Dosage track cross-check**. The dosage / band-pattern
    heatmap (Track 6) is the cross-check against ancestry. Verify
    that:
    - The dosage data source is the same as the regimes-page
      uses (`dosage_overlay.js` + `dosage_bridge.py`).
    - The colour palette matches (`DOSAGE_CLASS_COLOURS`).
    - The atlas-side getMacroDosage callback is reused, not
      duplicated.
12. **"Top switching fish" interpretation traps**. The user notes
    these fish may be:
    - heterozygous inversion carriers (biologically interesting)
    - mosaic / introgressed individuals (biologically interesting)
    - recombinant individuals (biologically interesting)
    - bad / noisy samples (artefact)
    - structural-haplotype carriers (biologically interesting)
    The page should NOT auto-label these — it should let the user
    inspect each. Verify the per-fish detail view exists.
13. **Brick layer is a simplification, not a discovery system.**
    Audit chat must verify:
    - The `n_bricks_total` field is labelled "info only, not a
      discovery count" in any UI tooltip.
    - The manuscript draft (if one references bricks) phrases them
      as "the inversion is associated with a K1-enriched ancestry
      brick," never as "we discovered N bricks." This is the same
      restraint as "POD-compatible" vs "POD found."
14. **Brick merging thresholds.** `min_purity = 0.6`, `min_brick_length
    = 3 RFs`, `min_brick_bp = 50 kb`. Starting values; audit chat
    should test against the empirical distribution of per-fish
    aligned-Q coherence in the catfish cohort.
15. **REGIME_DISCORDANT operational rule depends on a regime →
    ancestry-profile mapping** that is currently under-specified.
    The audit chat should define how Stage 4's `consensus_regime`
    pairs with a characteristic cohort ancestry profile, and verify
    REGIME_DISCORDANT is computed against that, not against a
    proxy.
16. **DOSAGE_DISCORDANT computation requires per-block expected
    ancestry profiles** E_HOM_REF / E_HET / E_HOM_INV. These come
    from the cohort; the audit chat must confirm that small group
    sizes (e.g. only 2 HOM_INV fish for a rare arrangement) don't
    produce unstable expected profiles. Set a minimum group size
    of ~5 fish before E_*[K] is trusted; otherwise mark the block's
    DOSAGE_DISCORDANT column as `untested`.
17. **Heterozygosity z-score baseline.** `heterozygosity_z` compares
    a fish's per-brick HET to cohort median at the same windows.
    Confirm this is the right baseline (vs. genome-wide HET for
    that sample). Different baselines produce different signals;
    cohort-position baseline catches local outliers, sample-genome
    baseline catches ROH-like patterns.
18. **Brick discordance flags as filters, not exclusions.** The user
    explicitly says discordant bricks are flags for inspection, not
    exclusions. Confirm that no implementation downstream silently
    drops a fish or a brick because it has REGIME_DISCORDANT or
    DOSAGE_DISCORDANT flags.
19. **v1 vs v2 reconciliation.** Two UI mockups exist:
    `ancestry_scroller_mockup.png` (v1, 8-track horizontal scroller)
    and `ancestry_atlas_mockup_v2.png` (v2, three numbered layers).
    The spec marks v2 as canonical. The audit chat should:
    - Confirm v2 is the intended final design.
    - Decide whether any v1 elements should be ported to v2.
      Candidates for porting include: the bottom per-fish detail
      table (v1 has it explicitly; v2 puts per-fish detail in the
      right-panel "Selected brick" card — these are different UX
      patterns). The audit may want both.
    - Verify the spec's references to "Track 2" (v1) and "Layer 2"
      (v2) don't create cross-numbering confusion in any
      implementation file.
20. **The double-③ labelling.** v2's context-explainer card numbers
    the brick-metrics row as "③" but the actual Layer 3 is the
    Brick summary (cohort view). The spec recommends labelling
    brick-metrics without a circled number to avoid the conflict.
    The audit chat should confirm the implementation picks one
    numbering and uses it consistently across the page, the
    explainer card, code identifiers, and any documentation.
21. **PC1 Band per-fish data source.** v2's Layer 1 shows
    per-fish PC1 band assignments. Verify this comes from the
    Stage 4 banding pipeline (the same data the regimes-page lanes
    panel consumes) — not a separate PC1 run. Same source of truth
    means the regimes page and the ancestry page will never disagree
    on which fish is in which band.
22. **Cross-layer alignment guarantees.** v2 mandates that the fish
    row ordering, RF window column ordering, and horizontal
    coordinate system are identical across Layer 1, Layer 2, and
    all five metrics-heatmap rows. The dashed inversion guides at
    the breakpoint positions must hit the same pixel column on
    every track. Audit chat should confirm the implementation
    enforces these as a single shared coordinate system, not as
    per-track local layout.
23. **Cohort summary tracks (Layer 3).** v2's Layer 3a (Majority
    ancestry) and 3b (Fraction agreement) are cohort-level
    summaries. Their formulas are simple but verify:
    - `majority_K[w] = argmax_K Σ_fish 1(brick_dominant_K[fish, w]
      == K)`. Uses brick dominant_K (post-merge), not raw RF
      dominant_K.
    - `fraction_agreement[w]` uses the same brick-derived K.
    - When the cohort splits 50/50 between two K values, the
      majority is arbitrary — the implementation should either
      tie-break consistently (e.g. by K index) or render the bar
      hatched to indicate the tie. Same for the agreement chart
      at ~1/K values.
24. **Window size in the legend.** The mockup says "Each column =
    RF window (50 kb)." This is a project-configurable parameter,
    not a fixed UI element. The legend must reflect the actual
    project's window size at render time, not hard-code 50 kb.
25. **Status-icon vocabulary completeness.** v2's status-icon
    legend lists 5 icons: Low confidence brick (▢), High ΔQ
    outlier (▢), High het. (yellow border), Regime discordant
    (⚠), Dosage discordant (⊗). The spec's brick-label vocabulary
    (Layer 2 detail) has 12 labels. Confirm which labels render
    as icons vs which only appear in the per-brick status_flags
    list (not all 12 need an icon — FRAGMENT, RECOMBINANT_LIKE,
    BOUNDARY_BRICK are not in the legend).

## Critical caveats summary

These are the warnings the implementation must enforce, in order
of severity:

1. **Never display raw per-RF Q.** The label-switching pipeline is
   mandatory.
2. **Inside the inversion block, F-alignment must succeed.**
   Q-alignment fallback in the inversion region will hide the
   signal.
3. **Aligned Q only feeds switch_rate, entropy, and |ΔQ| metrics.**
   Computing any of these on raw Q produces noise.
4. **FAIL-status RFs render grey, not coloured.** A failed RF in
   the middle of an otherwise-clean block is informative
   ("alignment broke here"); papering over it with a plausible-
   looking colour is dishonest.
5. **Cohort identity is fixed by the dataset selector.** Never mix
   species. The salmon mockup is illustration only; the catfish
   manuscript uses the 226-pure-gariepinus cohort exclusively.
6. **Naming convention applies**: `HWE_FIS` / `arrangement_FST_like`
   over bare `FIS` / `FST` in any heterozygosity statistic.
7. **Bricks are a simplification layer, not a discovery.** The
   manuscript-safe phrasing is "the inversion is associated with
   a K-enriched ancestry brick," never "we discovered N bricks."
   Same restraint as "POD-compatible" vs "POD found."
8. **Brick labels are measurable deviations, not subjective
   judgements.** The UI uses RARE_ANCESTRY / HIGH_HET / HIGH_DELTA_Q
   / LOW_CONFIDENCE / REGIME_DISCORDANT / DOSAGE_DISCORDANT —
   never "strange" or "weird" or "interesting." Each label
   corresponds to a defined metric crossing a defined threshold.
9. **Cross-layer alignment is a single shared coordinate system.**
   v2's three layers + five metrics rows + cohort summary share
   one horizontal coordinate system (chromosome position) and one
   vertical fish ordering. Per-track local layout is not
   permitted. The dashed inversion guides must hit the same pixel
   column on every track. Without this, the page becomes
   misleading rather than diagnostic.
10. **Status icons render only when warnings are enabled.** v2's
    `Show warnings` toggle in the right panel (default ON) controls
    the visibility of ▢/▲/⚠/⊗ icons on bricks. When OFF, the
    underlying status_flags fields are still populated in the
    output TSVs — the toggle is visual only, not data-suppressing.

## Status checklist for implementation (DO NOT BEGIN YET)

When the audit chat has approved this spec, implementation order:

- [ ] Build the offline alignment pipeline (F-based with Q fallback,
      regime-aware smoothing, confidence scoring). Output as
      precomputed TSVs.
- [ ] Validate alignment on a known-easy chromosome (one with no
      inversions and stable ancestry). Manually inspect 50 RFs.
- [ ] Validate alignment on a known-hard region (LG28 15.1–18.0 Mb).
      Verify the inversion's K-shift signal is preserved, not
      suppressed by Q-alignment.
- [ ] Build the offline brick-construction pass: walk aligned Q,
      emit `06_ancestry_bricks.tsv` and `07_brick_annotations.tsv`.
      Validate brick count against expected order-of-magnitude
      (226 fish × ~5 bricks/chromosome on average ≈ ~1k bricks/chrom,
      not 100k).
- [ ] Build the new ancestry atlas page (`pages/discovery/
      ancestry_atlas/` — name TBD). Same DOM-contract pattern as
      the regimes page. Implements v2 canonical layout.
- [ ] Build the shared horizontal coordinate system: one chromosome
      scale, one set of dashed inversion guides, propagated to
      every track. This is the cross-layer alignment guarantee.
- [ ] Build Layer 1 (PC1 Band / Regime per fish) reading from the
      Stage 4 banding pipeline output (same source as regimes-page).
- [ ] Build Layer 2 (Ancestry Bricks per fish) reading the
      precomputed bricks TSVs. Implement the view-mode dropdown
      (six modes: Ancestry / Heterozygosity / ΔQ / Entropy /
      Confidence / Discordance).
- [ ] Build the brick-metrics multi-heatmap section (five rows:
      ΔQ / Het z / Entropy / Confidence / Dosage concordance) with
      their colour-scale legends. Default ON via `Show metrics
      heatmaps`.
- [ ] Build Layer 3 (Brick summary cohort view) — two stacked
      tracks: majority ancestry bar + fraction agreement area
      chart.
- [ ] Build the right side panel: explainer card (Block 1), view-
      mode + overlay controls (Block 2), Selected brick card
      (Block 3). Verify the Selected brick card never contains
      "strange," "weird," or "interesting."
- [ ] Implement the page header toggles (`Show inversion`,
      `Show breakpoints`, zoom controls, window-size selector,
      pan arrows).
- [ ] Add the cohort identity guard: the page header must show the
      species and sample count from the dataset selector at all
      times.
- [ ] Integration test: switch from one dataset to another and
      verify ALL tracks rerender with the new cohort, no state
      leaking through.
- [ ] Integration test: verify the dashed inversion guides hit
      the same pixel column on every track at every zoom level.

## What this spec does NOT cover

- Running NGSadmix or any admixture caller. The page consumes
  precomputed output.
- Choosing K. K is a project-level decision (the catfish cohort
  uses K=3 from existing MODULE_2B work).
- Cross-species comparison (out of scope).
- Phenotype linkage (different spec — `REGIME_ANNOTATION_SPEC.md`
  Layer 3c).
- Inversion calling itself. The "candidate inversion blocks" list
  comes from Stage 4 / regimes-page output, not from this page.
- Implementation: no code yet.

## References

The closest published analogue for ancestry-aware inversion
browsing in a fish cohort is:

- Mérot, C. et al. (2020). A roadmap for understanding the
  evolutionary significance of structural genomic variation.
  *Trends in Ecology & Evolution* **35**(7): 561–572.
  Reviews the population-genomics framework for detecting
  inversion-associated local ancestry shifts.
- The pearl millet study (Salson et al. 2025, Nature
  Communications 16:6458) — already cited in
  `REGIME_ANNOTATION_SPEC.md` — uses a related framework on a
  plant cohort and is the closest methodological template.

Existing tools that overlap functionally (the audit chat should
check whether the scroller adds enough beyond these to justify a
custom implementation):

- `loter` — local ancestry inference, primary input not a viewer.
- `RFMix` — ancestry inference for phased data.
- `bcftools view` + IGV — manual local browsing but no alignment
  guard.

The scroller's unique contribution is the **alignment-aware
display layer** built on top of per-RF NGSadmix output, with
explicit handling of the label-switching problem and the
ancestry-vs-dosage cross-check.
