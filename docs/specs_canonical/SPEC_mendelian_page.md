# SPEC — relatedness-atlas `mendelian` page (HEADLINE FEATURE)

**Status**: extracted from legacy; in-browser compute works; **server-side
compute endpoints are registered but not yet implemented** on the
atlas_server side. Page is functional today against DEMO data.

**Scaffolded in:**
- [`atlases/relatedness/pages/hub/mendelian.html`](../atlases/relatedness/pages/hub/mendelian.html) — extracted from legacy `Relatedness_atlas.html` lines 1475–1535
- [`atlases/relatedness/pages/hub/mendelian.js`](../atlases/relatedness/pages/hub/mendelian.js) — extracted verbatim from `Relatedness_atlas.js` §9 (lines 1967–2575)
- [`atlases/relatedness/pages/hub/mendelian/_state.js`](../atlases/relatedness/pages/hub/mendelian/)
- Server-side endpoints contract: [`atlases/relatedness/server/RELATEDNESS_ENDPOINTS.md`](../atlases/relatedness/server/RELATEDNESS_ENDPOINTS.md)

---

## 1. Goal

Test Mendelian segregation for selected parent-offspring relationships
at every inversion candidate. **The atlas's headline analytical
feature**: the manuscript's primary QC + downstream-signal output.

Per the legacy comment block, four test modes:

| mode         | shape                                  | statistic                       |
|--------------|----------------------------------------|---------------------------------|
| `dyad`       | parent × offspring                     | binomial transmission test      |
| `triad`      | parent₁ × parent₂ → offspring          | multinomial / chi-square        |
| `all_dyads`  | every dyad in current hub              | Stouffer combination across hub |
| `all_triads` | every triad in current hub             | Stouffer combination across hub |

Two cohort-test variants combine per-dyad p-values into one whole-hub
Z-score via Stouffer's method; this is what catches the systemic
Mendelian-incompatibility signal (the "DRIVE_CANDIDATE" / "TRANSMISSION_SKEW"
buckets — see §3).

## 2. Controls

| control                      | options                                                                                |
|------------------------------|----------------------------------------------------------------------------------------|
| `#mendMode`                  | `dyad` \| `triad` \| `all_dyads` \| `all_triads`                                       |
| `#mendParent1`               | populated from `DEMO.families[active].members` (single-mode); hidden in cohort modes   |
| `#mendParent2`               | visible only in `triad` mode                                                           |
| `#mendOffspring`             | as above for offspring side                                                            |
| `#mendInvSubset`             | `all` \| `status_pass` \| `status_warn` \| `freq_high` (≥0.10) \| `chrom_only` (active)|
| `#mendAlpha`                 | `0.05` \| `0.01` \| `0.001` \| `bonferroni` (auto-correction by n_tests)               |
| `#mendRunBtn`                | execute the test                                                                       |
| `#mendResetBtn`              | clear selection                                                                        |
| `#mendExportBtn`             | download results TSV                                                                   |

## 3. Result categories

For each (inversion, dyad/triad) result the page emits one of:

| label             | meaning                                                              |
|-------------------|----------------------------------------------------------------------|
| `STRONG_PASS`     | p ≥ 0.5; no detectable distortion                                    |
| `PASS`            | α ≤ p < 0.5                                                          |
| `WARN`            | 0.01 ≤ p < α                                                         |
| `FAIL`            | p < 0.01 — single-call distortion                                    |
| `TRANSMISSION_SKEW`| consistent same-direction deviation across all dyads in the hub      |
| `DRIVE_CANDIDATE` | TRANSMISSION_SKEW + Stouffer Z exceeds threshold; manuscript-headline target |
| `NEEDS_CROSSES`   | one karyotype class absent in the hub; can't test segregation       |
| `FAMILY_SUSPECT`  | per-family p-values bimodal — family-id mis-assignment likely        |

The headline workflow:
1. Run `all_dyads` mode over `status_pass + freq_high`.
2. Filter to `DRIVE_CANDIDATE` rows.
3. For each, drill into per-family decomposition — the page renders a small
   per-family-Z barchart inline.
4. Export to TSV for the manuscript table.

## 4. Server fallback

Per [`RELATEDNESS_ENDPOINTS.md`](../atlases/relatedness/server/RELATEDNESS_ENDPOINTS.md),
4 server endpoints are registered for offloading the slow paths:

```js
const SERVER_ENDPOINTS = {
  dyad:       'relatedness_mendelian_dyad_test',
  triad:      'relatedness_mendelian_triad_test',
  all_dyads:  'relatedness_cohort_mendelian_scan',
  all_triads: 'relatedness_cohort_mendelian_scan',
};
```

`mount()` probes `isComputeAvailable(endpoint)` for each in parallel
(fire-and-forget). When the user clicks Run, the page routes to the
server if available; falls back to the in-browser compute otherwise.

Today: **no endpoints are registered server-side**. The probe always
returns `false`; everything runs in-browser. Status: per
[atlas-core/toolkit_registries/STATUS.md](../../atlas-core/toolkit_registries/STATUS.md)
§"Intentionally deferred", "real runners for ngsRelate / ngsPedigree /
mendelian engines" are pending.

## 5. Behaviour

`mount()`:
1. Populate parent + offspring selects from `DEMO.families[state.selected_family].members` (or the active family).
2. Update mode UI (show/hide selectors per mode).
3. Wire control change handlers.
4. Probe server endpoints in parallel (fire-and-forget).
5. If `state.mend._pendingMode` is set (from the [inversions page](SPEC_inversions_page.md)'s "open in Mendelian" action), apply it now.
6. Replay `state.mend.last_result` if present (re-render after page switch).
7. Subscribe to `'individual_changed'` — re-populate selects on focal change.

`unmount()`:
1. Unsubscribe from `'individual_changed'`.
2. Clear `_setActiveState(null)`.

State persistence:
- `state.mend.last_result` — last result table; replayed on remount
- `state.mend._pendingMode` / `_pendingFromInversion` — cross-page pre-seed from the inversions page
- `state.mend.parent1` / `parent2` / `offspring` — current selection

## 6. In-browser compute (per `runDyadTest`, `runTriadTest`, `runCohortScan` in mendelian.js)

### Dyad (binomial)

For each parent-het site:
- Count alt-allele transmissions
- Expected p = 0.5; binomial two-sided p-value
- Combine across inversion sites: Stouffer's Z

`binomialPValueTwoSided` lives in `shared/stats.js`.

### Triad (multinomial / chi-square)

For each parent₁ × parent₂ karyotype combination, look up the expected
offspring distribution from a 3×3 table:

```
            parent2: 0/0  0/1  1/1
parent1: 0/0  →  1/0/0  ½/½/0  0/1/0
         0/1  →  ½/½/0  ¼/½/¼  0/½/½
         1/1  →  0/1/0  0/½/½  0/0/1
```

Observed vs expected counts → chi-square (df = 2) or multinomial-exact
for small N. `chiSquarePValue` + `expectedOffspringPrior` live in
`shared/stats.js`.

### Cohort scans (Stouffer)

Run the matching per-dyad / per-triad test for every dyad/triad in the
active hub; combine p-values via Stouffer's Z:

```
Z = sum(z_i) / sqrt(n)   where z_i = invNormCdf(p_i)
combined_p = 2 * (1 - normCdf(|Z|))
```

`invNormCdf` and `normCdf` live in `mendelian.js` (not promoted to shared
because nothing else uses them; can be promoted later).

## 7. Result rendering

`renderMendResult(result)` builds:

1. Summary line: `N inversions tested · K significant at α=0.05 · M DRIVE_CANDIDATE`.
2. Categorical pill counts (one per category, coloured).
3. Per-inversion table, sortable. Rows colour-tagged by category.
4. (Cohort modes only) inline per-family Z barchart for the top-N DRIVE_CANDIDATE rows.

## 8. Promotion criteria

This is a complex page; promotion is per-feature:

### 8a. Envelope-aware probe (basic)

- [ ] `mount()` calls `resolveLatestLayer('ngsrelate_pairs', ...)` (already shipped on network/compatibility — reuse)
- [ ] Status badge above the form

### 8b. Server compute (offload)

- [ ] At least one server endpoint registered server-side (recommend `relatedness_mendelian_dyad_test` first — single-pair only)
- [ ] In-browser path remains; server is opt-in via probe
- [ ] Smoke test for the routing decision

### 8c. Envelope-aware result envelope

- [ ] Cohort-scan results emit a new envelope `mendelian_status_v1` (the registered product)
- [ ] Result envelope lineage points back to `ngsrelate_pairs_v1` + `inversion_karyotypes.v1` via `provenance.source_layer_ids`
- [ ] Adapter pair for this output (see [atlas-core's adapter cookbook](../../atlas-core/docs/SPEC_atlas_adapter_cookbook.md))

Each of 8a/8b/8c moves the SPEC closer to `specs_done/`. When all three
ship, move the file.

## 9. Open biological design questions

- **Family detection threshold** — `FAMILY_SUSPECT` fires on bimodal per-family p-distributions. The current heuristic uses a hard threshold; should be promoted to a statistical test (Hartigan's dip or similar).
- **DRIVE_CANDIDATE Z-threshold** — currently `|Z| > 4` (≈ p < 6e-5 single-test). With ~50 inversions × ~30 families this is ~1500 tests; Bonferroni at α=0.05 demands `|Z| > 4.65`. Pin the threshold once n_tests stabilises.
- **Recombinant calls** — the 3×3 expected table assumes no recombination inside the inversion. For inversions with detectable recombinant haplotypes (per the inversion-atlas's `RECOMBINANT*` calls), the prior must be relaxed. Open spec: handle recombinants as a 4th karyotype class with a partial-derivation prior.
- **Phasing-aware test** — when ngsPedigree has phased haplotypes available, the dyad test can use haplotype transmission instead of genotype, which has more power. Today's test is genotype-only.

## 10. Cross-page hooks

- `inversions.js` → mendelian.js: `state.mend._pendingMode + _pendingFromInversion` (see [SPEC_inversions_page.md §5](SPEC_inversions_page.md))
- mendelian.js → inspector / sidebar: result rows expose `data-inversion-id` so the right-column Inspector can re-scope
- mendelian.js → cohort export: the DRIVE_CANDIDATE filter feeds the manuscript Table S2 generator (out of scope here; lives in `scripts/`)
