# SPEC — relatedness-atlas `focal_meiosis_scan` page (label "inv × meiosis")

**Status**: scaffold. **Overlaps with [meiosis-atlas `interchromosomal`
page](../../meiosis-atlas/specs_todo/SPEC_interchromosomal_page.md)**.
Manifest tooltip explicitly calls it "Transient home: seed page of the
future Meiosis Atlas" — i.e. the meiosis-atlas now exists, so this
page's role is open.

**Scaffolded in:** [`atlases/relatedness/pages/hub/focal_meiosis_scan.html`](../atlases/relatedness/pages/hub/focal_meiosis_scan.html) + `focal_meiosis_scan.js`.

---

## 1. Goal

Per the manifest tooltip: "Focal inversion × meiosis coincidence scan.
For each focal inversion, compares the coefficient of coincidence on
every tested chromosome between carriers and matched non-carriers, using
a family-aware permutation null. Per-row intra/inter relation tag +
status pill (strong / moderate / weak / no effect / FAMILY CONFOUNDED)."

This is **identical in purpose** to meiosis-atlas's
[`interchromosomal` page](../../meiosis-atlas/specs_todo/SPEC_interchromosomal_page.md).
The relatedness-atlas comment ("Transient home: seed page of the future
Meiosis Atlas") confirms it was always intended as a temporary home.

## 2. The overlap

100% overlap with meiosis-atlas's `interchromosomal` page. Same
biological hypothesis, same statistical machinery (family-aware
permutation), same result-table shape.

The minor difference: this page might use slightly different result-row
status pills (strong / moderate / weak / no effect / FAMILY CONFOUNDED
per the tooltip), versus the meiosis-atlas page's planned shape. That's
a UI difference, not a contract difference.

## 3. Recommendation: DELETE from relatedness-atlas once meiosis-atlas page ships

Per the manifest's own "transient home" language, this page was always
meant to migrate. Now that the meiosis-atlas exists with a registered
`interchromosomal` page entry, the migration target is concrete.

Sequence:

1. **Wait** until meiosis-atlas's `interchromosomal` page is wired (i.e. the 4 missing builders ship, the page consumes them).
2. **Confirm** the relatedness-atlas page's UI choices (status pills, family-confounded flag, intra/inter tag column) all moved over.
3. **Delete** the relatedness-atlas page entry from manifest, fragment, module, registry.
4. **Add** a redirect — when a user lands on `#/relatedness/focal_meiosis_scan`, redirect to `#/meiosis/interchromosomal`. Implement in the AtlasRouter or via a tiny stub fragment that calls `window.location.hash = '#/meiosis/interchromosomal'`.

## 4. Until then

The page can stay as-is, useful as a working prototype that informs
meiosis-atlas's `interchromosomal` page design. Specifically:

- **Status pills** — strong / moderate / weak / no effect / FAMILY CONFOUNDED — should be reflected in meiosis-atlas's SPEC.
- **Intra/inter relation tag** — every result row gets tagged intra (same-chrom-as-focal, but the focal inversion is on chrom X so this is unusual) or inter (different chrom). Useful in the meiosis-atlas SPEC.
- **Family-confounded handling** — the FAMILY CONFOUNDED pill captures the case where the signal disappears after family-aware permutation. The meiosis-atlas page should emit the same.

I will copy these UI design decisions into
[meiosis-atlas's SPEC](../../meiosis-atlas/specs_todo/SPEC_interchromosomal_page.md)
when the meiosis-atlas page is actually being built.

## 5. Decision required

Same shape as [SPEC_meiosis_page.md §5](SPEC_meiosis_page.md): mark
`Decided: <DATE>` once the deletion happens. Until then, this page
exists as a working prototype; specs_done/ entry will be a `Removed in:`
block when the deletion lands.
