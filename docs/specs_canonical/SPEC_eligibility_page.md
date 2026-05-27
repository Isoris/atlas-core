# SPEC — relatedness-atlas `eligibility` page (NCO/Mb p map)

**Status**: scaffold. Independent.

**Scaffolded in:** [`atlases/relatedness/pages/hub/eligibility.html`](../atlases/relatedness/pages/hub/eligibility.html) + `eligibility.js`.

---

## 1. Goal

Per the manifest tooltip: "Eligibility (p map) — per-window NCO/Mb
across one chromosome. NCO traces the precondition / DSB substrate
layer; high NCO = plentiful substrate, low NCO = ancient cold region.
Inversion footprints overlaid. Karyotype matrix surfaced below so you
can see who carries which arrangement."

Renders the **p map** of a chromosome: where DSBs (double-strand breaks,
the substrate for meiotic recombination) are happening. NCO rate is a
proxy because NCO events trace DSB resolutions that didn't form a
crossover.

## 2. Data dependencies

| envelope                                | role                                     | source atlas |
|-----------------------------------------|------------------------------------------|--------------|
| `gene_conversion_tracts.v1`             | NCO events per (parent, offspring, chrom)| meiosis (shipped — see [SPEC_tract_classifications_adapter.md](../../meiosis-atlas/specs_done/SPEC_tract_classifications_adapter.md)) |
| `inversion_candidates.v1`               | inversion footprints overlay              | inversion    |
| `inversion_karyotypes.v1`               | per-sample matrix below                   | inversion    |

The per-window NCO rate is computed in-browser from the
`gene_conversion_tracts.v1` envelope's `tracts[]` array:

```js
const window_bp = 1_000_000;  // 1 Mb default
const counts_by_window = bin(tracts.filter(t => t.chrom === activeChrom &&
                                                  (t.class === 'NCO' || t.class === 'MOSAIC_SHORT')),
                              start, end, window_bp);
const rate_per_mb = counts_by_window.map(n => n / (window_bp / 1e6));
```

Aggregated across all dyads in the cohort. Per-karyotype-stratified
rate is a future view.

## 3. Surface

```
#eligibChromSelect    — chrom filter (cross-tab)
#eligibWinSize        — window size: 100kb / 500kb / 1Mb (default) / 5Mb
#eligibTrack          — horizontal track: x = chrom position, y = NCO/Mb (line plot)
#eligibInvOverlay     — translucent bars on the track showing inversion candidate spans
#eligibKaryoMatrix    — full karyotype matrix below the track (cross-chrom or chrom-only)
#eligibDataSource     — envelope status badge
```

## 4. Behaviour

`mount()`:
1. Probe envelopes (3, fail-soft).
2. Render status badge.
3. Filter tracts to active chrom.
4. Bin into windows; compute NCO/Mb per window.
5. Render track + inversion overlay + karyotype matrix below.

`unmount()`: detach listeners.

## 5. Visual cues

- **High NCO/Mb** windows → light colour (substrate-rich)
- **Low NCO/Mb** windows → dark colour (substrate-poor / cold)
- **Inversion span overlay** → translucent amber bar, label = inversion_id on hover
- **Cold region inside inversion** → green tick = expected (suppression confirmed); red tick = unexpected (substrate persists despite carrier-het — investigate)

## 6. Cross-page hook

The companion page is [`resolution`](SPEC_resolution_page.md) (the x map
— CO/(NCO+CO)). The pair (p, x) maps to the d/x identifiability problem
flagged in the meiosis-page tooltip. Best viewed side-by-side.

Future enhancement: allow eligibility + resolution as a stacked two-track
view on the same page (multi-track mode flag).

## 7. Promotion criteria

- [ ] `gene_conversion_tracts.v1` envelope probe wired (adapter is shipped, just needs data)
- [ ] Track renders real data when envelope present
- [ ] Inversion overlay positioned correctly against the chromosome coordinate system
- [ ] Karyotype matrix below renders (reuse the [`karyotypes` page](SPEC_karyotypes_page.md) renderer via shared module)
- [ ] Smoke test with synthetic tracts + 1 inversion overlay
- [ ] Move SPEC to `specs_done/`

## 8. Open work

- **Karyotype-stratified rate** — split the track by parent karyotype at a focal inversion. Useful for confirming local suppression. Out of scope for v1.
- **Sex-stratified rate** — same idea by parent sex.
- **DSB-marker overlay** — when a histone-modification or PRDM9-motif track exists, overlay it. Maps to the [meiosis-atlas `crossovers_per_candidate`](../../meiosis-atlas/specs_todo/SPEC_crossovers_per_candidate_page.md) page's optional PRDM9 logo.
- **Window-size auto-pick** — for short chromosomes (≤ 30 Mb), default to 100 kb; for long, 1 Mb. Currently fixed at 1 Mb.
