# SPEC — meiosis-atlas `crossovers` page (CO + DCO cohort view)

**Status**: shipped 2026-05-20 as v1 (envelope-aware, 4 views, 41-assertion
smoke). v2 promotion criteria documented in §6: the `karyo_strat` view
needs a proper statistical null (currently a per-row ratio + heuristic
threshold; the correct math is the same family-block permutation as the
interchromosomal page, restricted to the focal chrom).

**Implemented in:**

| file | role |
|---|---|
| [`pages/hub/crossovers.html`](../atlases/meiosis/pages/hub/crossovers.html) | controls + result slot |
| [`pages/hub/crossovers.js`](../atlases/meiosis/pages/hub/crossovers.js) | mount / probe / chrom dropdown populate / Run / Export wiring; 5 exported renderers |
| [`css/pages/crossovers.css`](../atlases/meiosis/css/pages/crossovers.css) | `#crossovers`-scoped badge / table / `co-cell-low` highlight |
| [`pages/hub/test_crossovers_envelope.js`](../atlases/meiosis/pages/hub/test_crossovers_envelope.js) | 41-assertion smoke (filterEvents, classPred, chromList, 4 renderers, status badge) |

**Sister pages**:
- [`nco`](SPEC_nco_page.md) — same scaffolding pattern for NCO/GC events
- [`interchromosomal`](SPEC_interchromosomal_page.md) — the **inter**chromosomal companion test; this page handles the **intra**chromosomal side

Together the two pages answer the registered question
[`inversion_effect_on_meiosis_per_chromosome`](../../atlas-core/toolkit_registries/relatedness/01_registry/questions.jsonl).

---

## 1. The biological hypothesis

> Inversion heterozygotes show **suppressed crossing-over within the
> inverted segment** (and adjacent regions to a lesser extent). Does
> the focal inversion in this cohort show that suppression on its
> **own chromosome**, separately from any **inter**chromosomal effect?

Intrachromosomal CO suppression is the well-attested biology; the
[`interchromosomal`](SPEC_interchromosomal_page.md) page handles the
more controversial off-chromosome claim. Crossovers page rolls up both
the descriptive cohort-level CO counts (views §3.1–§3.2) AND the
intrachromosomal-effect test (view §3.4, `karyo_strat`).

## 2. Data input — `chromosome_meiosis_events_v1`

Single envelope, fetched via
`resolveLatestLayer('chromosome_meiosis_events', { stage: 'normalized' })`
in `mount()`. Per
[`SPEC_chromosome_meiosis_events_adapter.md`](SPEC_chromosome_meiosis_events_adapter.md)
the typed payload exposes:

```
payload.events[i] = {
  parent_id, offspring_id, chrom,
  chrom_len_bp,        // bp — denominator for rate views
  n_co, n_dco, n_nco,  // counts; n_co + n_dco are the CO-like classes
  co_per_mb, dco_per_mb,
  mean_co_position_bp, median_co_position_bp,
  karyotype_at_focal_inv: 'homA' | 'het' | 'homB' | null,
}
```

Optional but consumed when present:
- `karyotype_at_focal_inv` — required for the `karyo_strat` view; rows
  with `null` are dropped from that view (page emits "No
  karyotype_at_focal_inv data on the loaded envelope" empty-state).

What's **not** in this envelope today (and where it would come from):
- Per-parent sex — needed for heterochiasmy stratification; would
  extend the envelope row or join against an external samples envelope.
- Family block id — the karyo_strat view's proper null model (§3.4.3
  below) needs this; today it's also absent from the envelope.

## 3. The four views

UI selects view via `#coDisplay`. Class scope via `#coClass` —
`CO_LIKE_ALL` (default, both CO and DCO counters), `CO_ONLY`, or
`DCO_ONLY`. Chrom filter via `#coChrom`.

### 3.1 `count` — raw event counts per (dyad × chrom)

`renderPerDyadChrom(events, classScope)` in
[`crossovers.js:75`](../atlases/meiosis/pages/hub/crossovers.js).

Pivots events into a `dyad × chrom` matrix. Per cell:

```
cell[dyad, chrom] = Σ (n_co + n_dco)  over events matching that (parent, offspring, chrom)
                   when classScope.{co,dco} are set
```

Empty cells render as blank; non-zero cells right-aligned. No
statistical test — this is the descriptive view.

### 3.2 `rate_per_mb` — events per Mb of chromosome

`renderRatePerMb(events, classScope)` at
[`crossovers.js:103`](../atlases/meiosis/pages/hub/crossovers.js).

Same pivot as §3.1 but reads `co_per_mb` + `dco_per_mb` directly from
each row (the adapter pre-computes `rate = n / chrom_len_bp × 1e6`;
see [adapter §4](SPEC_chromosome_meiosis_events_adapter.md)). When
`classScope.co && classScope.dco` (the default), the cell value is the
**sum** of the two rates. Hint line clarifies this.

### 3.3 `position` — STUB

`renderBreakpointTrack` returns an empty-state message:

> Breakpoint-position view requires the `traversal_breakpoints` envelope
> (ngsTracts STEP_TRC_02). Not yet wired — see §7.

Phase C target: track-style render of refined CO breakpoint positions
along the chromosome. Producer is ngsTracts STEP_TRC_02; the envelope
contract isn't authored yet (open SPEC, mentioned in §7 below).

### 3.4 `karyo_strat` — intrachromosomal effect view (HEADLINE)

`renderKaryotypeRate(events, classScope)` at
[`crossovers.js:156`](../atlases/meiosis/pages/hub/crossovers.js).

This is the page's manuscript-grade output: **does the focal inversion
suppress CO on its own chromosome?** It answers the same biological
question as the interchromosomal page's focal-chrom row, but presents
multiple chromosomes side-by-side so the user can see het vs non-het
rate comparisons across the whole karyotyped subset of chroms.

#### 3.4.1 What the v1 implementation does (current)

```
Filter events to those with karyotype_at_focal_inv != null.
For each row:
  bucket = (karyotype_at_focal_inv == 'het') ? 'het' : 'nonhet'
  rate   = co_per_mb (+ dco_per_mb when classScope.dco)
  accumulator[chrom, bucket].sum += rate
  accumulator[chrom, bucket].n   += 1

Per chrom output row:
  mean_het    = accumulator[chrom, 'het'].sum / .n
  mean_nonhet = accumulator[chrom, 'nonhet'].sum / .n
  ratio       = mean_het / mean_nonhet
  flag        = (ratio < 0.7) → CSS class 'co-cell-low' (var(--bad))
```

#### 3.4.2 What's wrong with that (honest)

**Two real defects in v1**, both documented as v2 work:

1. **Per-row aggregation, not per-parent.** Each (parent, offspring,
   chrom) row contributes one rate observation to its bucket. A parent
   with 4 offspring gets weighted 4× a parent with 1 offspring in the
   group mean. The interchromosomal page handles this correctly by
   aggregating per-parent first (see
   [interchromosomal §4 step 1](SPEC_interchromosomal_page.md)).
   Karyo_strat should do the same.
2. **No null model.** The 0.7 threshold is a *heuristic*; it has no
   statistical interpretation. A small cohort with high variance can
   land below 0.7 by chance; a large effect on a chromosome with low
   karyotype-stratified coverage can fail to render at all. The user
   sees a binary highlight without a p-value.

#### 3.4.3 The correct null model for the intrachromosomal test

**Same family-block permutation as the interchromosomal page**
(see [interchromosomal §3 and §5.3](SPEC_interchromosomal_page.md)) —
the only differences are:

1. **Restriction**: the test runs only on the focal chromosome (X),
   not on chroms Y ≠ X.
2. **Effect direction expectation**: the intrachromosomal alternative is
   directional (`H1: CO_rate(het) < CO_rate(non-het)` — suppression). A
   one-sided permutation p-value is biologically motivated, but the
   smoke + interchromosomal page use two-sided for uniformity. v2
   should make the side configurable.

Why the **same null** is correct here as in interchromosomal: in both
cases we're asking "if karyotype labels were assigned at random within
families, how often would we see a per-parent CO-rate gap this large?"
The answer doesn't depend on which chrom we're testing; only on the
parent-CO-rate distribution and the family structure.

#### 3.4.4 The v2 wire-up plan

When the user picks a focal inversion in the interchromosomal page,
the focal-chrom row is computed but excluded from α-control there. The
crossovers page karyo_strat view should consume the **same computed
row** for the focal chrom plus extend it to all karyotyped chroms in
the envelope.

Concretely:

```js
import { runInterchromosomalTests }
  from '../interchromosomal/_stats.js';

// In renderKaryotypeRate (v2):
const result = runInterchromosomalTests(
  { cme: envelope, lic: <fapd's focal_chrom>, fapd, cm: stub },
  { focal_inversion_id, n_permutations: 10000, p_bh_alpha: 0.05 }
);
// Then: render result.rows directly. Each row already has
// t_stat, p_value, p_bh, p_bonf, mean_diff, n_het, n_nonhet.
// The crossovers page just adds chrom_len_bp + rate columns
// for context.
```

This reuses the validated stats engine + smoke fixture from
interchromosomal. The crossovers page becomes a thin presentation
layer over the same compute.

**Why this isn't done in v1**: fapd + lic envelopes weren't a hard
mount() dependency for crossovers (the v1 page works with only
chromosome_meiosis_events_v1 present). v2 needs to either probe all
four or accept a degraded-mode rendering. Decision deferred.

## 4. Per-view math summary

| view | aggregation | denominator | statistic | null model |
|------|-------------|-------------|-----------|------------|
| `count` | sum n_co + n_dco per (dyad, chrom) | — | none (descriptive) | — |
| `rate_per_mb` | sum co_per_mb + dco_per_mb per (dyad, chrom) | — (already a rate) | none (descriptive) | — |
| `position` | (stub) | — | — | — |
| `karyo_strat` **v1** | mean of co_per_mb (+ dco_per_mb) over rows in each (chrom, het\|non-het) bucket | rows | ratio = mean_het / mean_nonhet | none (heuristic threshold 0.7) |
| `karyo_strat` **v2** target | mean of per-parent CO rate over parents in each (chrom, het\|non-het) bucket | parents | Welch's t | family-block permutation (§3.4.3) |

The descriptive views (count, rate_per_mb) are not p-valued by design —
they're context for the karyo_strat view, not standalone tests.

## 5. Worked example — `karyo_strat` on the interchromosomal demo fixture

The interchromosomal demo fixture
([`_demo.js`](../atlases/meiosis/pages/hub/interchromosomal/_demo.js))
also makes a useful crossovers fixture because the cme envelope is
shared. **However**: the demo fixture omits `karyotype_at_focal_inv`
on the cme rows. So the v1 karyo_strat view on the demo would emit the
empty-state message ("No karyotype_at_focal_inv data").

To actually exercise karyo_strat in a fixture, the cme rows need the
karyotype field populated. Recommended fixture extension (not yet in
demo):

```js
// Add to each event in _buildCmeEvents():
karyotype_at_focal_inv: HET_PARENTS.includes(parent) ? 'het' : 'homA'
```

With that, the v1 implementation on `LG07` (the demo's
designed-significant chrom) would produce:

```
mean CO/Mb (het)     = mean([0.18, 0.20, 0.16, 0.18, 0.22]) = 0.188
mean CO/Mb (non-het) = mean([0.08, 0.10, 0.06, 0.08, 0.10]) = 0.084
ratio                = 0.188 / 0.084 = 2.24
```

A ratio of 2.24 is **not** < 0.7 → no red highlight. This is
*biologically correct* for the demo (LG07 is the interchromosomal-effect
chrom, not the intrachromosomal-suppression chrom). On a real catfish
cohort, an inversion that suppresses local CO would produce a ratio
< 1.0 on its own chrom (and the demo doesn't model that).

This illustrates a v1 documentation limitation: the karyo_strat fixture
is currently only exercised by manual eyeball. **A proper smoke test
for the v2 karyo_strat needs its own designed-significant fixture
where one chrom shows ratio < 1.0 with statistical significance under
the family-block permutation.**

## 6. Promotion criteria

| criterion | v1 | v2 |
|-----------|----|----|
| `mount()` calls `resolveLatestLayer()` with fail-soft | ✓ | ✓ |
| Status badge in 3 states (ok / empty / warn) | ✓ | ✓ |
| `count`, `rate_per_mb` views render | ✓ | ✓ |
| `karyo_strat` ratio + heuristic threshold | ✓ | (replaced by §3.4.3) |
| `karyo_strat` per-parent aggregation | ✗ | required |
| `karyo_strat` permutation p-value + BH correction | ✗ | required |
| `karyo_strat` smoke fixture with one designed-positive cell | ✗ | required |
| `position` view (traversal_breakpoints envelope) | ✗ | open |
| TSV export | ✓ | ✓ |
| 30+ assertion JS smoke | ✓ (41) | ≥ 41 |

v1 is shipped under "useful but flagged". v2 promotion blocks on (a)
fapd envelope having focal-chrom labels for the crossovers consumer,
(b) the per-parent + permutation refactor of `renderKaryotypeRate`,
(c) a fixture for the new test.

## 7. Failure modes

### 7.1 No envelope yet on this workspace

`mount()` shows the empty-state badge: "No `chromosome_meiosis_events_v1`
envelope in this workspace yet. Submit `import_chromosome_meiosis_events`
+ `normalize_chromosome_meiosis_events` to populate". Render handler
short-circuits with "Nothing to render — no envelope."

### 7.2 Envelope present but no karyotype-stratified rows

The `karyo_strat` view's `filter(e => e.karyotype_at_focal_inv)`
removes every row → empty-state message points the user at the
producer side (the adapter accepts the field as optional; the producer
needs to emit it).

The other 3 views render normally — they don't depend on
`karyotype_at_focal_inv`.

### 7.3 Envelope present but missing `chrom_len_bp`

`rate_per_mb` and `karyo_strat` rely on the adapter having pre-computed
`co_per_mb` from `n_co / chrom_len_bp × 1e6`. The adapter's
[normalize step](SPEC_chromosome_meiosis_events_adapter.md) handles the
null-derivation case — when both n_co and chrom_len_bp are present but
co_per_mb is missing, it derives. When chrom_len_bp itself is missing,
co_per_mb stays null. In that case the cell renders `—`.

### 7.4 One karyotype bucket has 0 rows on a chromosome

`mean_het` or `mean_nonhet` is `null`. The cell renders `—` for the
mean and `—` for the ratio. The chrom row still appears in the table
(so the user sees the gap), but no red highlight can fire (ratio = null
< 0.7 is false).

In v2 with the permutation test, this becomes a `t_stat = NaN`
short-circuit (per
[interchromosomal §5.1](SPEC_interchromosomal_page.md)) → p_value = NaN
→ no significance flag.

### 7.5 Ratio threshold edge cases (v1 only)

The 0.7 threshold has documented failure modes:
- A chromosome with 1 het and 1 non-het row, mean_het = 0.05, mean_nonhet = 0.10 → ratio = 0.5 → flagged red even though n = 2 has no statistical power
- A chromosome with 200 rows per bucket, mean_het = 0.069, mean_nonhet = 0.072 → ratio = 0.96 → not flagged even though the difference is statistically significant in a real test

These are why v2 needs an actual p-value — they're not bugs in v1, they're a known limitation of the heuristic.

## 8. Reproducibility

v1 has no permutation step → fully deterministic (sums + means + a
threshold compare). Identical envelope → identical render every time.

v2 will inherit the interchromosomal page's RNG conventions
([interchromosomal §8](SPEC_interchromosomal_page.md)) — production
uses `Math.random`, smoke uses `mulberry32(seed)`.

## 9. What's currently NOT modelled

### 9.1 Per-parent aggregation in `karyo_strat`

Per §3.4.2 above. Each row is one (parent, offspring) — parents with
many offspring dominate the group mean. v2 fix: aggregate per-parent
first (sum n_co across offspring, divide by chrom_len_bp once), then
take group means over the per-parent rate.

### 9.2 Statistical test for `karyo_strat`

Per §3.4.3 above. v1 has only a ratio + heuristic threshold; v2 needs
Welch's t + family-block permutation + BH/Bonferroni, identical to the
interchromosomal page's compute pipeline (so much so that v2 should
literally call `runInterchromosomalTests` and present its focal-chrom
row plus an extension to all karyotyped chroms).

### 9.3 Sex stratification

Pooled across sexes today. Heterochiasmy means male and female carriers
may show different effect sizes. Same gap as the interchromosomal page
([interchromosomal §9.4](SPEC_interchromosomal_page.md)).

### 9.4 The `position` view

`renderBreakpointTrack` is an empty-state stub. Phase C target: read
refined CO positions from the `traversal_breakpoints` envelope (ngsTracts
STEP_TRC_02) and draw a track per chromosome. The envelope contract is
not yet authored.

### 9.5 UI control `#coRefined` is HTML-present but JS-pending

The HTML has a refined-breakpoints toggle (`yes` / `no`). The JS doesn't
read it today. Wiring it depends on §9.4 (the envelope existing).

### 9.6 Cross-atlas read for `inversion_karyotypes.v1`

The karyo_strat view today reads `karyotype_at_focal_inv` from the cme
envelope itself (the adapter copies it through from the producer TSV).
The cleaner long-term wire is to read `inversion_karyotypes.v1` from
the inversion-atlas (cross-atlas) and join against the cme envelope's
(parent_id × chrom × focal_inversion_id). Today the cme envelope acts
as a denormalized join — works for v1, not great for normalization.

## 10. UI surface

```
┌────────────────────────────────────────────────────────────┐
│ status badge (ok / empty / warn)                           │
│   ok: layer_id · N rows · K dyads · L chroms ·             │
│       ΣCO: a · ΣDCO: b · ΣNCO: c · karyo-strat rows: d     │
├────────────────────────────────────────────────────────────┤
│ #coClass ▾ (CO / DCO / ALL_CO_LIKE)                        │
│ #coDisplay ▾ (count / rate_per_mb / position / karyo_strat)│
│ #coChrom ▾ (all / per-chrom from envelope)                 │
│ #coRefined ▾ (yes / no — UI present; JS pending; §9.5)     │
│ [Render] [⤓ Export]                                         │
├────────────────────────────────────────────────────────────┤
│ #coResultSlot — depends on #coDisplay:                     │
│   count: (dyad × chrom) integer table                      │
│   rate_per_mb: (dyad × chrom) float table + hint           │
│   position: stub message                                   │
│   karyo_strat: (chrom × het / non-het / ratio) table       │
│                + co-cell-low red highlight                 │
└────────────────────────────────────────────────────────────┘
```

## 11. Open biological design questions

### 11.1 One-sided vs two-sided for `karyo_strat`

The intrachromosomal alternative is directional: inversion heterozygotes
should show **suppressed** CO (`ratio < 1`). A one-sided permutation
p-value would have more power than two-sided. The interchromosomal page
is two-sided because ICE direction is uncertain. v2 decision: expose a
`#coTestSide` control? Default one-sided for karyo_strat, two-sided for
the interchromosomal page?

### 11.2 Effect-size reporting

Today: ratio = `mean_het / mean_nonhet`. Alternatives:
- Log-ratio `log2(mean_het / mean_nonhet)` — symmetric around 0,
  natural for "fold-change"
- Difference `mean_het − mean_nonhet` — same units as the rate (per Mb)
- Standardized effect `(mean_het − mean_nonhet) / sd_pooled`

v2 should report at least mean_diff (per Mb) + a CI alongside the
p-value, so the user knows whether a significant result is large or
just well-measured.

### 11.3 What counts as "suppression"?

The 0.7 threshold is a guess. *Drosophila* literature suggests CO
suppression of 60–95% inside long inversions; ratios of 0.05–0.40.
Catfish inversions may differ. A v2 fixed threshold should be informed
by the cohort's real distribution under H0 (i.e. the BH-adjusted
significance line, not an a priori cutoff).
