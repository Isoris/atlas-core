# SPEC — relatedness-atlas `inversion_priority` page

**Status**: scaffold. Independent.

**Scaffolded in:** [`atlases/relatedness/pages/hub/inversion_priority.html`](../atlases/relatedness/pages/hub/inversion_priority.html) + `inversion_priority.js`.

---

## 1. Goal

Per the manifest tooltip: "Inversion priority table — Pass-1 (WGS
discovery) → Pass-2 (marker validation at scale) bridge. One row per
inversion with composite priority_score and SHIP / HOLD / DROP bucket.
Use to pick the 5–20 inversions to take into the next 10k–50k-fish
marker round."

This page operationalises the "which inversions go to the next pass"
decision. Pass-1 = WGS-based discovery (this atlas's current state).
Pass-2 = high-throughput marker assay on a larger fish cohort. Going to
Pass-2 is expensive; the priority page is the gate.

## 2. The composite score

Combines several per-inversion signals into a single rank:

| signal                   | source                                                      | weight (default) |
|--------------------------|-------------------------------------------------------------|------------------|
| frequency                | `inversion_candidates.v1`                                   | + (moderate)     |
| status                   | `inversion_candidates.v1` (PASS/WARN/FAIL)                  | + (PASS only)    |
| Mendelian distortion Z   | `mendelian_status.v1` (registered, not yet built)           | + (large)        |
| BDMI confidence ladder   | [`bdmi` page](SPEC_bdmi_page.md) output                     | + (large)        |
| meiosis-effect Z         | `inversion_meiosis_effects.v1` (missing — builder needed)   | + (large)        |
| regime-uncoupled bonus   | [`regimes` page](SPEC_regimes_page.md) verdict              | × (multiplier — kills the score for `COUPLED`) |
| inversion size           | `inversion_candidates.v1`                                   | + (small — bigger inversions are easier to assay) |
| flanking marker density  | (TBD)                                                       | + (assayability) |

Weights are configurable via `params.weights.<signal_name>`; UI exposes
sliders so the user can rebalance and instantly see the SHIP/HOLD/DROP
shuffle.

## 3. Buckets

- **SHIP** — composite score above a fixed-N or fixed-fraction cutoff (default: top 10)
- **HOLD** — middle band; revisit after Pass-1.5 refinement
- **DROP** — bottom band; explicitly de-prioritise

Cutoffs configurable (`params.bucket_thresholds`).

## 4. Surface

```
#priWeightSliders   — one slider per signal (with locked baseline + user override)
#priBucketCounts    — pill showing N SHIP / M HOLD / K DROP
#priResultTable     — one row per inversion; sortable by composite_score; per-signal columns visible (off by default for clarity)
#priExportBtn       — TSV download (the manuscript Table S3 generator)
#priDataSource      — multi-envelope status badge
```

Each row shows:
- inversion_id, chrom, length, frequency
- composite_score (numeric, with progress-bar visual)
- bucket pill (SHIP green / HOLD amber / DROP grey)
- "expand" toggle → per-signal contributions in a sub-row

## 5. Behaviour

`mount()`:
1. Probe envelopes (4-5, fail-soft).
2. Render multi-source status badge.
3. Compute composite scores in-browser; apply bucket thresholds.
4. Render table.
5. Wire sliders → recompute composite on input.

`unmount()`: detach listeners.

## 6. The score formula (default weights, illustrative)

```
status_pass_factor = 1.0 if status == "PASS" else 0.5 if "WARN" else 0.1
regime_factor      = 0.0 if regime_verdict == "COUPLED" else 1.0

raw_score =
  0.20 * normalize(frequency, range=[0.05, 0.5]) +
  0.30 * normalize(mendelian_Z_abs, cap=10) +
  0.20 * normalize(bdmi_confidence_int, max=4) +    # weak=1, very-strong=4
  0.10 * normalize(meiosis_effect_Z_abs, cap=10) +
  0.10 * normalize(log10(inv_length_bp), range=[5, 8]) +
  0.10 * normalize(flank_marker_density, range=[0, 100])  # markers per Mb in flank

composite_score = raw_score * status_pass_factor * regime_factor
```

`composite_score ∈ [0, 1]`. Bucket thresholds default: SHIP ≥ 0.7,
DROP < 0.3, HOLD middle.

## 7. Promotion criteria

- [ ] All input envelopes probed; missing ones contribute 0 to composite (not undefined)
- [ ] Per-signal columns + composite render
- [ ] Bucket pills colour-coded
- [ ] Slider sliders re-compute live (debounced ~100ms)
- [ ] TSV export works
- [ ] Smoke test with synthetic fixture covering all 3 buckets
- [ ] Move SPEC to `specs_done/`

## 8. Open work

- **Persisted weight profiles** — let the user save "my weights" presets (e.g. "drive-screen-focus", "manuscript-table-S3") under unique names in localStorage.
- **Per-bucket export buttons** — separate SHIP/HOLD/DROP TSVs.
- **Trace to evidence pages** — clicking an inversion row should navigate to a unified "evidence" view (inversion details + mendelian results + BDMI results + signature verdict). Cross-page wiring decision pending.
- **Pass-2 cost integration** — once marker-assay cost data exists, weight by 1/cost to optimise the SHIP set under a budget constraint. Optimisation lives in [`marker_test_designer`](SPEC_marker_test_designer_page.md); this page should link to it.
