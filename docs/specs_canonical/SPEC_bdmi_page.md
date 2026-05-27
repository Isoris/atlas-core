# SPEC — relatedness-atlas `bdmi` page (BDMI screen)

**Status**: scaffold. Independent of meiosis-atlas.

**Scaffolded in:** [`atlases/relatedness/pages/hub/bdmi.html`](../atlases/relatedness/pages/hub/bdmi.html) + `bdmi.js`.

---

## 1. Goal

Per the manifest tooltip: "Bateson–Dobzhansky–Muller incompatibility
screen. Runs six population-genetic tests per inversion candidate
(Mendelian distortion, missing class, het deficit, ancestry interaction,
long-range forbidden combinations, phenotype association) and assigns a
confidence ladder weak/moderate/strong/very-strong."

BDMI = pairs of loci where certain genotype combinations are depleted
or absent in the cohort, suggesting genetic incompatibility (the carrier
combos don't survive). The classical evolutionary signal for speciation
in progress.

## 2. The six tests

| # | test name                         | what it detects                                                          |
|---|-----------------------------------|--------------------------------------------------------------------------|
| 1 | Mendelian distortion              | per-inversion segregation deviation from 1:2:1 (overlaps with `mendelian` page) |
| 2 | Missing class                     | one karyotype-pair combination has 0 carriers in the cohort              |
| 3 | Het deficit                       | heterozygote frequency below Hardy-Weinberg expectation                  |
| 4 | Ancestry interaction              | karyotype distribution differs significantly across K=8 ancestry buckets |
| 5 | Long-range forbidden combinations | per-pair-of-inversions, certain combos are depleted across the cohort    |
| 6 | Phenotype association             | (if phenotype data exists) — karyotype is non-randomly distributed in cases vs controls |

Confidence ladder: each test contributes a partial score; the sum maps
to weak / moderate / strong / very-strong via thresholds.

## 3. Data dependencies

| envelope                       | role                                | source atlas |
|--------------------------------|-------------------------------------|--------------|
| `inversion_candidates.v1`      | enumerate inversions                | inversion    |
| `inversion_karyotypes.v1`      | per-sample × per-inversion calls    | inversion    |
| `mendelian_status.v1`          | per-inversion segregation results   | relatedness (registered, not yet built) |
| `cohort_ancestry.qK_v1`        | K=8 admixture Q matrix              | population   |
| `cohort_phenotype.v1`          | phenotype labels (if available)     | future       |

Test 5 (long-range forbidden combinations) needs **pair-of-inversion**
karyotype counts. Compute in-browser from per-sample × per-inversion
calls; for the 226-sample cohort with ~50 inversions, that's
~50 × 49 / 2 = 1225 pair tests, each over a 3×3 grid — tractable
in-browser.

## 4. Surface

```
#bdmiInvSelector       — focal inversion (or "all")
#bdmiTestFilter        — checkboxes: enable/disable each of 6 tests
#bdmiConfidenceFilter  — radio: weak+ / moderate+ / strong+ / very-strong only
#bdmiResultTable       — sortable table; one row per (inversion[, inversion_partner])
#bdmiDataSource        — envelope status badge
#bdmiExportBtn         — TSV download
```

Result table columns:
- inversion_id (or inversion_pair)
- per-test pill (×6) — pass/fail/inconclusive for each
- composite_score (sum)
- confidence_label (pill, colour-coded)
- p-value (combined, if applicable)

## 5. Behaviour

`mount()`:
1. Probe envelopes (4 sources, fail-soft).
2. Render status badge — green when all 4 envelopes present, amber/grey for missing ones.
3. Run the 6 tests in-browser; render result table.
4. Wire filters → re-render visible rows.

`unmount()`: detach listeners.

Compute is in-browser for now (no server endpoint). The cohort scan is
~1500 single-inversion-tests + ~1225 pair-tests = ~3000 tests; should
complete in <5 seconds on a typical laptop.

## 6. Promotion criteria

- [ ] All 4 envelope probes wired with fail-soft
- [ ] All 6 tests implemented in-browser
- [ ] At least one synthetic positive case in the smoke test (a fixture cohort where missing-class fires)
- [ ] Confidence ladder thresholds documented (in the SPEC) once tuned against real data
- [ ] Move SPEC to `specs_done/`

## 7. Open biological design questions

- **Test 5 multiple comparisons** — 1225 pair tests; Bonferroni at α=0.05 → p < 4e-5 per test, which kills almost everything. BH FDR or hierarchical (only test pairs where both inversions individually show distortion) is more practical. Decision pending.
- **Ancestry K choice** — K=8 is the "canonical" K; if a future analysis chooses K=2 or K=12, the test should be parameterised on K.
- **Phenotype data** — none registered today. Test 6 should fall back to "not enough data" status when no phenotype envelope is resolvable.
- **Linked-inversion handling** — two inversions on the same chromosome can show apparent pair-distortion because of linkage, not incompatibility. The [`regimes` page](SPEC_regimes_page.md) explicitly addresses this; BDMI screen should integrate that page's regime-coupling check before flagging strong/very-strong.
