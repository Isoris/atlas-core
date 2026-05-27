# SPEC — meiosis-atlas `nco_per_candidate` page

**Status**: scaffolded — page mounts, layer-registry chip renders
"⚪ not loaded" for `nco_gc_track`, the no-op
`renderNcoPerCandidate` stub returns immediately. No file load happens
yet. Phase C ships the producer pipeline + the actual two-view render.

**Implemented in:**

| file | role |
|---|---|
| [`pages/hub/nco_per_candidate.html`](../atlases/meiosis/pages/hub/nco_per_candidate.html) | static fragment with two card containers (tract ideogram, telomere curve) |
| [`pages/hub/nco_per_candidate.js`](../atlases/meiosis/pages/hub/nco_per_candidate.js) | mount / unmount lifecycle, exported `renderNcoPerCandidate(state)` stub |
| [`pages/hub/nco_per_candidate/_state.js`](../atlases/meiosis/pages/hub/nco_per_candidate/) | per-page state isolation |
| [meiosis manifest entry](../atlases/meiosis/manifest.json) | `stylesheet: atlases/genome/css/genome.css` — same cross-atlas CSS dependency as the sister page |

**Migration history**: this page was migrated from
`genome-atlas/pages/annotation/page12.{html,js}` on 2026-05-19, in the
same migration round as
[`crossovers_per_candidate`](SPEC_crossovers_per_candidate_page.md).
Reason: per-inversion-candidate NCO / gene-conversion tract views are
**meiotic** content, not genome-assembly content.

**Sister pages**:
- [`crossovers_per_candidate`](SPEC_crossovers_per_candidate_page.md) — same per-candidate keying, CO events instead of NCO/GC tracts
- [`nco`](SPEC_nco_page.md) — cohort-level NCO view (this page is the per-candidate zoom)

---

## 1. The biological hypothesis

> For one focal inversion candidate at a time, render the **spatial distribution of NCO and gene-conversion (GC) tracts** in the candidate's region. Where do they fall relative to the inversion's span? Are they concentrated near telomeres, or distributed uniformly? Is the inverted span enriched for short tracts (the MOSAIC_SHORT signal at per-candidate resolution)?

Three orthogonal pieces of biology this page surfaces:

1. **NCO vs GC class separation.** Short NCO (~1–10 kb) and longer GC (~50–200 kb) are different biology — NCO is the canonical short gene conversion at a DSB resolution event, GC (called MOSAIC_SHORT cohort-wide) is the inversion-region gene conversion that the legacy CO classifier would have miscalled. Seeing them as two distinct tracks (green vs yellow) is the visual cue.

2. **Telomere bias.** Same as the sister CO page: distributing tracts against `d_rel` ∈ [0, 1] (§4.3) makes the candidate-by-candidate comparison portable across chromosome lengths.

3. **In-span enrichment.** Inside an inversion's span, MOSAIC_SHORT / GC should be over-represented relative to NCO (per [`SPEC_nco_page.md` §1](SPEC_nco_page.md) biology). The per-candidate ideogram is the visual zoom of that signal — the [cohort `nco` page §3.4](SPEC_nco_page.md) tests the same signal as a statistical aggregate.

The page is **per-candidate by design** — the cohort-level NCO / GC view lives on the [`nco`](SPEC_nco_page.md) page. This page zooms into one candidate at a time so the reviewer can decide whether its gene-conversion pattern is consistent with active gene-conversion inside a meiotic-suppression region.

## 2. Data input — `nco_gc_track`

One layer declared in [`layers.registry.json`](../atlases/meiosis/registries/data/layers.registry.json):

### 2.1 `nco_gc_track` (file layer, cold tier)

Path: `data/nco_gc/<candidate_id>.json`

`<candidate_id>` interpolated from `state.shared.candidate`. Separate
file from `crossover_track` because the pedigree NCO / GC detector
(ngsTracts STEP_TRC_01) emits a distinct table from the CO call file.

```jsonc
{
  "candidate_id":  "INV_LG28_01",
  "candidate_span": {
    "chrom":    "C_gar_LG28",
    "start_bp": 12000000,
    "end_bp":   14000000
  },
  "flank_bp":      500000,
  "tracts": [
    { "chrom": "C_gar_LG28", "start_bp": 12150000, "end_bp": 12152300,
      "kind": "nco", "indiv": "P_HET_3", "in_span": true },
    { "chrom": "C_gar_LG28", "start_bp": 12480000, "end_bp": 12570000,
      "kind": "gc",  "indiv": "P_HET_1", "in_span": true },
    ...
  ],
  "telomere_curve": {
    "nco": { "d_rel": [...], "rate": [...], "ci_lo": [...], "ci_hi": [...] },
    "gc":  { "d_rel": [...], "rate": [...], "ci_lo": [...], "ci_hi": [...] }
  },
  "curve_params": {                          // LOESS settings used by the producer
    "bandwidth":   0.3,
    "degree":      2,
    "ci_alpha":    0.05,
    "ci_method":  "bootstrap" | "asymptotic"
  }
}
```

Notes:

- **`kind ∈ {nco, gc}`** is the per-tract class. Mapping to ngsTracts' canonical labels (per `tract_classifications_v1`):
  - `kind = nco` ↔ `class = NCO` (short, anywhere)
  - `kind = gc`  ↔ `class = MOSAIC_SHORT` (50–200 kb, inside / boundary of an inversion)
  - `MOSAIC_LONG` is **not** rendered here (it's a separate-class outlier; the cohort `nco` page handles it).
- **`start_bp` and `end_bp` (not just `pos_bp`)**: tracts are intervals, not points. The ideogram renders them as horizontal bars / ticks with width, not dots.

**Schema documented at**: [layers.registry.json](../atlases/meiosis/registries/data/layers.registry.json#L39).

## 3. The two views

### 3.1 Tract ideogram

A horizontal track spanning `[candidate_span.start_bp − flank_bp, candidate_span.end_bp + flank_bp]`. Within the track:

- The **inverted span** as a translucent block.
- One bar (or thin tick if the bp width is below the pixel-render threshold) per tract, positioned at `[start_bp, end_bp]`, coloured by `kind`:
  - **NCO** → green, lane LEFT (above the span band)
  - **GC** → yellow, lane RIGHT (below the span band)
- Hover tooltip: `indiv`, `start_bp`, `end_bp`, `span_bp = end_bp − start_bp`, `kind`, `in_span`.

Why split into two lanes (not interleaved): visual eye-load. Green-vs-yellow at the same vertical line is hard to disambiguate at scale. A reader scanning for "lots of GC inside the span" wants the yellow lane to read like one band; same for NCO above. v1 fix:

```
top    ──────●●─●────●──●────────  ← NCO (green)
        ╔══════════════════════╗
band    ║   ▓▓▓▓▓ inverted ▓▓▓▓║   ← span (translucent)
        ╚══════════════════════╝
bottom ────────▮▮──▮▮▮──▮──────  ← GC (yellow)
```

### 3.2 Tract rate vs relative-telomere-distance (with LOESS + 95% CI)

Same shape as the sister page's §3.2 telomere curve, but stratified by
`kind` (nco vs gc) rather than `sex`:

- Two LOESS curves, one per kind, with 95% CI bands.
- Same `d_rel ∈ [0, 1]` x-axis (§4.3 in
  [`SPEC_crossovers_per_candidate_page.md`](SPEC_crossovers_per_candidate_page.md)).
- Y-axis: tract rate (tracts/Mb of chromosome, or tract-bp/Mb when
  weighted by tract length — pick at producer time).

Two producer modes (same as sister page):
- Pre-computed: `telomere_curve.{nco,gc}` populated → renderer just plots
- Client-side: compute LOESS from `tracts[]` + `curve_params`

The math is identical to
[crossovers_per_candidate §4](SPEC_crossovers_per_candidate_page.md) —
LOESS smoothing, family-stratified bootstrap for the 95% CI. Reference
that SPEC; this page doesn't replicate the formulas.

**One difference**: tracts have width (`span_bp = end_bp − start_bp`). Two reasonable rate definitions, picker per producer:

```
1.  rate(window) = #{ tracts intersecting window } / window_size_bp
2.  rate(window) = Σ tract_bp_in_window / window_size_bp²
```

Definition 1 counts tract presence (a 200 kb tract counts the same as a
2 kb tract in any single window). Definition 2 weights by length (the
long tract contributes more to windows it overlaps). For
**enrichment-direction visualization**, definition 1 is cleaner (matches
intuition: "where do tracts occur"). For **biology-quantitative
comparison** (cm/Mb-equivalent units), definition 2. v1 default:
**definition 1** for the visual track; `curve_params.rate_mode` is the
override.

## 4. State + interaction model

- `state.shared.candidate` → drives the per-candidate file path
- `state.shared.activeChrom` → coincides with `candidate_span.chrom`; not separately read
- No page-local controls today (no kind filter, no sex stratification)

Per-candidate file load + caching: same as the sister page (per
[crossovers_per_candidate §6](SPEC_crossovers_per_candidate_page.md)).

## 5. Failure modes

Mirror [crossovers_per_candidate §7](SPEC_crossovers_per_candidate_page.md) with these differences:

### 5.1 No active candidate

Same hint as the sister page: "Pick a candidate from the Inversions table to begin."

### 5.2 File not found / malformed / parse error

Same fail-soft as the sister page.

### 5.3 `tracts` empty but file present

Render the span band only + a "no NCO/GC tracts in this candidate" hint. Telomere curves render empty per kind.

### 5.4 Only one kind present

If a candidate has only NCO tracts (no GC, or vice versa), render the present-kind lane normally and a "no `<missing-kind>` tracts in this candidate" annotation in the missing lane.

### 5.5 Tracts overlap the flank but not the span

That's biologically meaningful (gene conversion in the flank, not in the inversion proper) and is rendered normally — the flank zoom-out IS the point.

### 5.6 `in_span` mismatch with computed overlap

The page should validate that each tract's `in_span` field matches the geometric overlap with `candidate_span`. A mismatch is a producer-side bug. v1 stub doesn't validate; v2 should warn (console + small UI hint).

## 6. Cross-atlas / cross-page reads

This page shares the cross-atlas CSS dependency with the sister page
(`atlases/genome/css/genome.css`). No new cross-atlas data reads — the
`nco_gc_track` layer lives in this atlas and is consumed only by this
page.

The **per-tract counts** rendered here are a per-candidate slice of the
cohort-level data in [`tract_classifications_v1`](SPEC_tract_classifications_adapter.md).
Logically:

```
tracts on nco_per_candidate page  ⊆  payload.tracts in tract_classifications_v1
filtered to:                          tract.parent_id ∈ <inversion carriers>
                                       AND tract overlaps candidate_span ± flank_bp
                                       AND class ∈ {NCO, MOSAIC_SHORT}
                                       (rename MOSAIC_SHORT → gc; drop MOSAIC_LONG)
```

The producer pipeline applies this filter and emits the per-candidate
JSON. The per-page consumer doesn't re-derive. **If the per-candidate
file conflicts with the cohort envelope**, the cohort envelope is
canonical; the per-candidate file is a denormalized view.

## 7. What's currently NOT modelled

### 7.1 Per-tract confidence

`tract_classifications_v1` carries per-tract `confidence` (high / medium / low) and `manual_review_flag`. The per-candidate JSON doesn't propagate these today. v2 should include them so the reviewer can toggle "show high-confidence only" on the ideogram.

### 7.2 Length distribution by kind

A small histogram or violin plot of `span_bp` per `kind` would let the reviewer see whether the NCO and GC modes are well-separated (50 kb threshold validated) or muddy (threshold needs tuning). Phase D.

### 7.3 Sex stratification

Tracts don't carry `sex` today (the producer JSON shape). The cohort page has the same gap. Same fix on both sides: extend the producer pipeline to emit per-tract sex.

### 7.4 Multi-candidate overlay

Same gap as [crossovers_per_candidate §8.6](SPEC_crossovers_per_candidate_page.md).

### 7.5 Per-individual rate

Tracts inside the same individual share a meiosis. Per-individual-aggregated curves would be more rigorous than per-tract curves. v2.

### 7.6 In-span vs flank statistical test

The cohort `nco` page handles the cohort-level enrichment test (§4 of [`SPEC_nco_page.md`](SPEC_nco_page.md) — Fisher's exact). For a **per-candidate test** ("does THIS candidate show MOSAIC_SHORT enrichment inside its span?"), a Fisher's exact on the (kind × in_span) crosstab restricted to this candidate's tracts is the right tool. Out of scope for v1; phase C.

## 8. Promotion criteria

| criterion | v1 (today) | v2 (phase C) |
|-----------|------------|--------------|
| Page mounts cleanly | ✓ | ✓ |
| Layer registry chip shows "not loaded" status | ✓ | ✓ |
| File-load path `data/nco_gc/<candidate_id>.json` | ✗ | required |
| Tract ideogram view renders (NCO + GC lanes, span band, hover tooltip) | ✗ | required |
| Telomere curve view renders (LOESS + CI per kind) | ✗ | required |
| Family-stratified bootstrap for 95% CI | ✗ | required |
| Failure modes §5.1–§5.5 covered | ✗ | required |
| 30+ assertion JS smoke | ✗ | required when renderer ships |

v1 is a clean scaffold; v2 ships the actual two-view rendering once the
producer pipeline emits the per-candidate JSON files.

## 9. Open biological design questions

### 9.1 Rate definition (count vs length-weighted)

Per §3.2. Decision: ship both modes via `curve_params.rate_mode` and let the producer-side default settle after real-data feedback.

### 9.2 50 kb / 200 kb boundary tuning

The `MOSAIC_SHORT` length window (and therefore the `kind = gc` filter) is producer-defined. If the catfish gene-conversion distribution doesn't match the literature ranges, the kind boundary may need tuning. The cohort `nco` page exposes a length-histogram view that the reviewer can use to calibrate; per-candidate level should reflect that calibration once made.

### 9.3 What does an absence of NCO mean?

A candidate with **no NCO/GC tracts** is ambiguous: either (a) the
inversion really does suppress gene conversion (unusual but possible),
(b) the candidate is in a region where the producer pipeline lacks
informative SNPs to detect departures, or (c) the candidate isn't real
and is just an assembly artifact.

Disambiguation requires cross-page evidence (see the regimes /
inversion_signature pages in the relatedness atlas). The
per-candidate NCO page should not, by itself, conclude.

### 9.4 In-span overlay statistics

Per §7.6. v2 ships a simple Fisher's exact on the candidate's
(kind × in_span) crosstab. The cohort enrichment from
[`SPEC_nco_page.md` §4](SPEC_nco_page.md) is genome-wide; the
per-candidate test is its single-inversion zoom.

### 9.5 Symmetric vs asymmetric flank

The span ± `flank_bp` is symmetric. Some candidates may have biologically
asymmetric flanks (one side adjacent to a centromere, the other to a
telomere). v2 should expose per-side flank lengths, and the relative-
telomere-distance view §3.2 should annotate which side of the candidate
the rendered points come from.
