# SPEC — relatedness-atlas `compatibility` page

**Status**: shipped. Envelope-aware migration landed as commit 26 of the
toolkit_registries action-pipeline branch (per
[atlas-core/toolkit_registries/STATUS.md](../../atlas-core/toolkit_registries/STATUS.md)
§1 commit 26). 14-assertion smoke test green; wired into the umbrella as
"relatedness-atlas compatibility page (envelope-aware)".

**Implemented in:**
- [`atlases/relatedness/pages/hub/compatibility.html`](../atlases/relatedness/pages/hub/compatibility.html) — extracted from legacy `Relatedness_atlas.html` lines 1537–1601
- [`atlases/relatedness/pages/hub/compatibility.js`](../atlases/relatedness/pages/hub/compatibility.js)
- [`atlases/relatedness/pages/hub/test_compatibility_data_source.js`](../atlases/relatedness/pages/hub/test_compatibility_data_source.js)

---

## 1. Goal

Breeding-partner finder. Given a focal individual + a target offspring
karyotype + a scope (one candidate / one chromosome / all candidates),
list every other individual whose cross with the focal would produce the
target karyotype.

Practical purpose: planning **reciprocal crosses**, **fixing haplotypes**,
or **producing diagnostic trios** for downstream confirmation.

## 2. Controls

| control                     | options                                                                  |
|-----------------------------|--------------------------------------------------------------------------|
| Focal individual            | populated from `state.shared.activeFamily`                               |
| Target offspring karyotype  | `0/0` \| `0/1` \| `1/1`                                                  |
| Inversion scope             | `one candidate` \| `all candidates on one chrom` \| `all candidates`     |
| Sex-aware                   | checkbox — restrict to opposite-sex partners                             |
| Exclude close kin           | checkbox — exclude PO + FS edges                                         |
| Exclude ambiguous karyotypes | checkbox — drop samples with `?/?` calls at scope                       |

Run button → results table:
- rows: candidate partners
- cols: partner_id, sex, karyotype at scope, expected offspring distribution,
  relatedness theta to focal, exclusion flag (if filtered out — for visibility)

## 3. Envelope-aware data source

`mount()` probes for `ngsrelate_pairs_v1` (same envelope the network page
reads):

```js
const env = await resolveLatestLayer('ngsrelate_pairs', {
  dataset_id: 'main_226_hatchery',
});
```

The envelope state drives **the badge text on the "Exclude close kin"
checkbox label**:

- envelope present → label includes `(N pairs, median θ = 0.0234)` showing real distribution stats
- envelope absent → label shows `(DEMO data — close-kin θ threshold = 0.10)` (the demo fallback)
- fetch error → silently falls back to DEMO (no console error)

The actual filter logic still runs against `DEMO.relatedness_edges` for
now — the **advertise** stage. **Consume** stage (using real envelope
pairs for the theta-based exclusion) is pending the threshold-convention
SPEC (`specs_todo/SPEC_relatedness_threshold_calibration.md`, to be
authored).

## 4. Algorithm (per inversion candidate in scope)

For each partner P ≠ focal:

1. Look up `kfocal = karyotype(focal, candidate)`, `kP = karyotype(P, candidate)`.
2. Skip if `kfocal` or `kP` is missing (or `exclude_ambiguous = true` and either is `?/?`).
3. Skip if `sex_aware = true` and `sex(P) == sex(focal)`.
4. Skip if `exclude_close_kin = true` and `relatedness(focal, P) > θ_threshold` (currently 0.10 in DEMO; configurable when consume lands).
5. Compute expected offspring distribution given (kfocal, kP) under Mendelian segregation.
6. If `target_karyotype` ∈ expected with non-zero prob, emit row.

Multi-candidate scope = the same loop per candidate; partners are deduplicated by id.

## 5. Surface

```
#compFocalSelect              — focal individual dropdown
#compTargetKaryo              — 3-way <select> for 0/0, 0/1, 1/1
#compScope                    — radio group: candidate / chrom / all
#compCandidateSelect          — visible only when scope = candidate
#compChromSelect              — visible only when scope = chrom
#compSexAware                 — checkbox
#compExcludeKin               — checkbox (label updated by envelope state)
#compExcludeAmbig             — checkbox
#compRunBtn                   — run
#compResults                  — results table (or "no compatible partners found")
#compDataSource               — envelope status badge (top of the page)
```

## 6. Tested paths

The 14-assertion smoke (see
[`test_compatibility_data_source.js`](../atlases/relatedness/pages/hub/test_compatibility_data_source.js))
covers:

- envelope present → checkbox label updated with n_pairs + median theta
- envelope absent → label says DEMO fallback
- fetch error → silently falls back to DEMO
- title attribute carries the underlying layer_id (for click-to-trace)
- both checkboxes (kin + ambig) co-render correctly

Algorithm correctness is NOT in the smoke (would need a fixture cohort);
relies on the legacy compute being byte-equivalent to the extracted body.

## 7. Open work

- **Switch from advertise → consume** for the close-kin filter once a threshold convention is decided (see `specs_todo/SPEC_relatedness_threshold_calibration.md`, to be authored).
- **Server-side compute** for "all candidates" scope on a 226-sample cohort — that's ~50 candidates × ~226 partners × ~225 focal options = several million pair-evaluations. Today runs in-browser (slow on first click); a `POST /compute/relatedness_compatibility_search` endpoint is registered in [the relatedness manifest](../atlases/relatedness/manifest.json) as the future replacement.
- **Per-trio expected segregation** when scope = "all candidates on one chrom" — the page currently shows per-candidate expected distributions; a chrom-scoped roll-up would be a nice headline.
- **Cross-atlas read** — partner karyotypes come from inversion_karyotypes.v1 (inversion-atlas). Today via DEMO; with consume, via the typed envelope.
