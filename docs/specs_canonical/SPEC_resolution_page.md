# SPEC — relatedness-atlas `resolution` page (CO share x map)

**Status**: scaffold. Independent. Companion to
[`eligibility`](SPEC_eligibility_page.md).

**Scaffolded in:** [`atlases/relatedness/pages/hub/resolution.html`](../atlases/relatedness/pages/hub/resolution.html) + `resolution.js`.

---

## 1. Goal

Per the manifest tooltip: "Resolution (x map) — per-window CO/(NCO+CO)
share. Closest visible proxy for the latent exchange probability x.
Windows with too few events are greyed out. Inside an active
heterokaryotypic inversion: resolution drops sharply while NCO is
preserved (Eligibility page). Karyotype matrix surfaced below."

The **x map** complements the **p map** ([`eligibility`](SPEC_eligibility_page.md)).
Together they characterise the d/x identifiability problem: from
offspring genotype data you can compute p (NCO rate) and x (CO share),
but not d (DSB precondition) and x separately.

Biological signal: inside an active het-inversion, COs are suppressed
but DSBs / NCOs are not. So resolution drops sharply while eligibility
(NCO rate) stays similar to flanking regions. The pair of maps
diagnoses this pattern visually.

## 2. Data dependencies

| envelope                                  | role                                          | source atlas |
|-------------------------------------------|-----------------------------------------------|--------------|
| `tract_classifications_v1`                | filter to {NCO, CO, DCO}; compute share        | meiosis (shipped) |
| `inversion_candidates.v1`                 | inversion footprint overlay                   | inversion    |
| `inversion_karyotypes.v1`                 | karyotype matrix below                        | inversion    |

Per-window resolution:

```js
const win = bin(tracts.filter(t => t.chrom === activeChrom), start, end, win_bp);
const nco = win.map(w => count(w, t => t.class === 'NCO' || t.class === 'MOSAIC_SHORT'));
const co  = win.map(w => count(w, t => t.class === 'CO' || t.class === 'DCO'));
const resolution = win.map((_, i) => (co[i] + nco[i] < min_events) ? null : co[i] / (co[i] + nco[i]));
```

`min_events` defaults to 5 per window. Below-threshold windows render
greyed-out (the "not enough events" state).

## 3. Surface

```
#resoChromSelect    — chrom filter
#resoWinSize        — 100kb / 500kb / 1Mb (default) / 5Mb
#resoMinEvents      — number input: minimum events per window before computing share
#resoTrack          — horizontal track: x = chrom position, y = CO share (0–1)
#resoInvOverlay     — inversion candidate spans
#resoKaryoMatrix    — full karyotype matrix below
#resoDataSource     — envelope status badge
```

## 4. Behaviour

`mount()`:
1. Probe `tract_classifications_v1` envelope (fail-soft).
2. Render status badge.
3. Filter tracts to active chrom; bin into windows.
4. Compute per-window CO share; grey out under-threshold windows.
5. Render track + inversion overlay + karyotype matrix below.

`unmount()`: detach listeners.

## 5. Visual cues

- **High resolution (CO share)** windows → green colour
- **Low resolution** windows → red colour (suppression indicator)
- **Greyed windows** → too few events; rendered with a hatch pattern
- **Inversion span overlay** → translucent amber bar
- **Inside-inversion low-resolution** → highlighted green tick on the overlay (expected pattern confirmed); high-resolution = red tick (unexpected — investigate)

## 6. Cross-page hook

Co-renders with `eligibility` when the user enables "stack tracks"
mode. Both consume the same envelope; the only differences are the
filter classes (`eligibility`: NCO-like; `resolution`: CO-share) and
the window-stat shape.

## 7. Promotion criteria

Mirrors [`eligibility`](SPEC_eligibility_page.md) promotion list:

- [ ] `tract_classifications_v1` envelope probe wired
- [ ] Track + inversion overlay renders
- [ ] Under-threshold windows greyed-out correctly
- [ ] Karyotype matrix below renders
- [ ] Smoke test
- [ ] Move SPEC to `specs_done/`

## 8. Open work

- **Karyotype-stratified resolution** — split the track by parent karyotype at a focal inversion. The biological headline: inside-inv resolution drops sharply only for hets, not for homs. Out of scope for v1.
- **Sex-stratified resolution** — would expose sex-specific recombination rate differences (heterochiasmy). Important for fish where one sex often has zero / much lower CO.
- **Confidence interval shading** — bootstrap CI for each window; render as translucent band around the line.
- **Click-to-inspect window** — clicking a window opens a side panel with the underlying tracts, sample-level breakdown, etc.
