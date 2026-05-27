# SPEC — relatedness-atlas `regimes` page (regime inheritance)

**Status**: scaffold. Independent.

**Scaffolded in:** [`atlases/relatedness/pages/hub/regimes.html`](../atlases/relatedness/pages/hub/regimes.html) + `regimes.js`.

---

## 1. Goal

Per the manifest tooltip: "Chromosome regime inheritance — tests whether
a focal inversion's distortion is explained by linkage to another
inversion on the same chromosome (haplotype-regime coupling), then
classifies the residual signal as meiotic-drive-like vs underdominance-like
via cross-type comparison. Prevents over-calling BDMI / drive /
underdominance from coupled inversions."

This is a confounding-control page: before declaring an inversion has a
direct biological effect (drive / underdominance / BDMI), check whether
the apparent signal is just hitchhiking on a linked inversion's signal.

## 2. The test

For each focal inversion F on chromosome C:

1. Enumerate all other inversions {I₁, I₂, …} on the same chromosome C.
2. For each Iₖ, test whether F's distortion is **conditional on** Iₖ
   karyotype (stratify cohort by Iₖ karyotype, recompute F's
   distortion within each stratum).
3. If F's distortion **disappears** when stratified by some Iₖ → F is
   coupled to Iₖ; the apparent F signal is hitchhiking. Tag as `COUPLED`.
4. If F's distortion **persists** in all strata → residual signal.
   Classify by symmetry:
   - **Drive-like** — distortion preserves a direction (one allele
     transmitted more than expected, consistently)
   - **Underdominance-like** — distortion is heterozygote-deficit
     (het frequency below HW, but homozygotes balanced)
   - **Other** — residual that fits neither

Outputs a per-(inversion, candidate-coupler) table + a per-inversion
verdict pill (`COUPLED-to-Iₖ` / `DRIVE-LIKE` / `UNDERDOMINANCE-LIKE` /
`MIXED` / `INSUFFICIENT-DATA`).

## 3. Data dependencies

- `inversion_candidates.v1` from inversion-atlas — enumerate inversions on each chrom
- `inversion_karyotypes.v1` from inversion-atlas — per-sample × per-inversion calls
- `long_range_haplotype_regimes.v1` from inversion-atlas (registry says "no producing analysis registered yet — will be missing") — extended inheritance blocks
- `mendelian_status.v1` from relatedness-atlas — per-inversion baseline distortion (not yet built)

When `long_range_haplotype_regimes.v1` is missing, the page falls back
to using `inversion_karyotypes.v1` directly — coarser-grained but
sufficient to detect strong coupling.

## 4. Surface

```
#regimeChromSelect    — chromosome filter
#regimeFocalInv       — focal inversion (or "all on this chrom")
#regimeResultTable    — per-focal-inversion verdict + per-coupler stratification
#regimeStratPanel     — slide-out for clicked focal — shows stratum-by-stratum p-values
#regimeDataSource     — envelope status badge
```

## 5. Behaviour

`mount()`:
1. Probe envelopes (4, fail-soft).
2. Filter inversions by active chrom.
3. For each focal inversion, run the conditional-distortion test against every other inversion on the chromosome.
4. Apply classification rules → verdict pill.
5. Render result table.

`unmount()`: detach listeners.

In-browser compute: 28 chroms × ~2 inversions per chrom × ~2 couplers
each = ~100 sub-tests. Tractable.

## 6. Why this page is critical

Without this check, the BDMI / mendelian / drive screens will produce
many false positives — every inversion linked to a single "true cause"
will inherit that cause's signal. The regime check is the de-confounding
layer.

Recommended workflow: run `mendelian` cohort scan first → flag
DRIVE_CANDIDATE inversions → re-test each through this page → only the
ones that survive stratification are reported in the manuscript.

## 7. Promotion criteria

- [ ] Envelope probes wired with fail-soft
- [ ] Conditional-distortion test implemented in-browser
- [ ] Verdict pills render with theme-aware colours (DRIVE-LIKE → var(--bad), UNDERDOMINANCE-LIKE → var(--warn), COUPLED → var(--muted))
- [ ] Smoke test with a synthetic two-inversion-linked fixture; expect COUPLED for both, then a synthetic standalone DRIVE-LIKE
- [ ] Move SPEC to `specs_done/`

## 8. Open biological design questions

- **Stratification minimum N** — when a stratum has < 10 individuals, the conditional test has insufficient power. Threshold should be configurable.
- **Multiple couplers** — when 3 inversions on the same chrom are mutually coupled, the test order matters (testing F | I₁ first vs F | I₂ first). Per the literature, a joint test (logistic regression on all couplers) is more rigorous but harder to interpret. Decision: ship the pairwise version first.
- **Per-arm vs per-chrom** — for metacentric chromosomes, two inversions on different arms are effectively independent; same-arm pairs are not. Need to know arm structure from the assembly. Out of scope for round 1.
