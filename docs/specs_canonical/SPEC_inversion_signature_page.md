# SPEC — relatedness-atlas `inversion_signature` page

**Status**: scaffold. Independent.

**Scaffolded in:** [`atlases/relatedness/pages/hub/inversion_signature.html`](../atlases/relatedness/pages/hub/inversion_signature.html) + `inversion_signature.js`.

---

## 1. Goal

Per the manifest tooltip: "Three stacked tracks for one chromosome
(NCO/Mb, CO/meiosis, resolution) plus per-candidate verdict cards.
Cross-layer rule: NCO ≈ flank + CO suppressed = consistent with active
inversion; CO not suppressed = reject; both low = ancient cold region;
NCO elevated = ambiguous. Karyotype matrix surfaced below."

This is the **synthesis page** for inversion signatures: rolls together
the `eligibility` (NCO/Mb), `resolution` (CO share), and a third
CO/meiosis track into one stacked view, then applies a cross-track
decision rule to classify each inversion candidate.

## 2. Three tracks

| track       | source                                              | what it shows                                |
|-------------|-----------------------------------------------------|----------------------------------------------|
| NCO/Mb      | same as [`eligibility`](SPEC_eligibility_page.md)   | DSB substrate density                        |
| CO/meiosis  | needs `chromosome_meiosis_events.v1` (adapter pending) | crossover count per meiosis per Mb         |
| resolution  | same as [`resolution`](SPEC_resolution_page.md)     | CO share = CO / (NCO + CO)                   |

All three rendered on the same x-axis (chromosome position), so the
user can visually correlate.

## 3. Verdict cards

Per inversion candidate on the chromosome, a card emits one of:

| verdict           | condition (rough)                                                         |
|-------------------|---------------------------------------------------------------------------|
| `ACTIVE_INVERSION` | NCO/Mb inside ≈ flanks AND CO suppressed inside                          |
| `REJECT`          | NCO/Mb inside ≈ flanks AND CO NOT suppressed inside                       |
| `ANCIENT_COLD`    | both NCO/Mb and CO low inside (substrate-poor region)                     |
| `AMBIGUOUS`       | NCO/Mb elevated above flanks (suggests something more than just inversion)|

Each card includes:
- inversion_id, chrom, span, length
- NCO/Mb inside vs flank (number + delta)
- CO/meiosis inside vs flank
- resolution inside vs flank
- verdict pill
- "Open in `mendelian`" button (same cross-page hook as the [`inversions`](SPEC_inversions_page.md) page)

## 4. Data dependencies

- `gene_conversion_tracts.v1` — NCO track (shipped adapter)
- `chromosome_meiosis_events.v1` — CO/meiosis track (adapter pending — see [meiosis-atlas SPEC_crossovers_page.md](../../meiosis-atlas/specs_todo/SPEC_crossovers_page.md) §3.1)
- `tract_classifications_v1` — resolution track (filter to CO + NCO)
- `inversion_candidates.v1` — span overlay + per-candidate cards
- `inversion_karyotypes.v1` — karyotype matrix below

## 5. Surface

```
#sigChromSelect      — chrom filter
#sigTracks           — three stacked tracks (top: NCO/Mb, middle: CO/meiosis, bottom: resolution)
#sigCardGrid         — per-candidate verdict cards below the tracks
#sigKaryoMatrix      — karyotype matrix at the bottom
#sigDataSource       — envelope status badge (multi-envelope; show per-source state)
```

## 6. Behaviour

`mount()`:
1. Probe 4 envelopes in parallel (fail-soft); render multi-source badge.
2. Filter all to active chrom.
3. Render 3 tracks (each with its own bin computation).
4. For each inversion candidate, compute inside vs flank stats; apply verdict rule; emit a card.
5. Render karyotype matrix below.

`unmount()`: detach listeners.

## 7. The decision rule (formalised)

```
def verdict(inv, tracks):
    inside_nco   = mean(tracks.nco_per_mb,  inv.start..inv.end)
    flank_nco    = mean(tracks.nco_per_mb,  inv.start-flank..inv.start) ++
                   mean(tracks.nco_per_mb,  inv.end..inv.end+flank)
    inside_co    = mean(tracks.co_per_meiosis, inv.start..inv.end)
    flank_co     = mean(tracks.co_per_meiosis, inv.start-flank..inv.start) ++ ...
    nco_ratio = inside_nco / flank_nco    # 1.0 means equal
    co_ratio  = inside_co  / flank_co
    nco_elevated   = nco_ratio > 1.5
    co_suppressed  = co_ratio  < 0.3
    nco_near_flank = 0.7 <= nco_ratio <= 1.3
    nco_low        = nco_ratio < 0.5
    co_low         = co_ratio  < 0.3
    if nco_elevated:
        return "AMBIGUOUS"
    if nco_low and co_low:
        return "ANCIENT_COLD"
    if nco_near_flank and co_suppressed:
        return "ACTIVE_INVERSION"
    if nco_near_flank and not co_suppressed:
        return "REJECT"
    return "AMBIGUOUS"  # fallback
```

Thresholds (`1.5`, `0.3`, `0.7`, `1.3`, `0.5`, `0.3`) need calibration
against real data; expose as `params.thresholds.{nco_elevated_ratio,
co_suppressed_ratio, ...}` so they can be tuned without code changes.

## 8. Promotion criteria

- [ ] 4 envelope probes wired
- [ ] All 3 tracks render with real data
- [ ] Verdict rule implemented
- [ ] Per-candidate cards render with correct verdict pill colours
- [ ] Smoke test with synthetic tracts + 4 inversion candidates spanning all 4 verdict cases
- [ ] Threshold calibration documented (post-real-data)
- [ ] Move SPEC to `specs_done/`

## 9. Open work

- **Per-karyotype tracks** — currently aggregated across all dyads. Stratifying by parent karyotype at the focal inversion is the canonical biology view but doubles the rendering surface.
- **Sex-stratified tracks** — same idea by parent sex (heterochiasmy). Particularly important in catfish (high sex bias in CO).
- **Cohort export of verdicts** — generates a TSV like Table S1 in the manuscript: one row per inversion, with NCO_ratio, CO_ratio, resolution_delta, verdict.
