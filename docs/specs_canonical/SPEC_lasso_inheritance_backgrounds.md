# SPEC — Lasso Inheritance Backgrounds (fish-set linkage)

**Status**: SHIPPED partially (Slices 1 + 3) — was SPEC ONLY
(referenced from `pages/discovery/local_pca_dosage.html` +
`handoff_docs/HANDOFF_2026-05-05_turn164_lasso_linkage.md` without an
on-disk doc) until 2026-05-15.
**Authored from shipped code + the turn-164 handoff** (recovery of a
missing SPEC).

**Implemented in (Slices 1 + 3)**:
- `legacy/Inversion_atlas.html` (turn 164, +528 LOC) — `_computeLassoLinkage`,
  `_lassoLinkageGetOrCompute`, `_lassoLinkageCacheKey`,
  `_invalidateLassoLinkageCache`, `_lassoLinkageToTSV`,
  `_lassoLinkageDownloadTSV`, `_openLassoLinkagePopover`,
  `_renderLassoLinkageTable`
- `linesBandTraceLinkageBtn` (`🔗 linkage`) in lines header
- Constants: `_LASSO_LINKAGE_DEFAULT_PURITY_THRESHOLD = 0.7`,
  `_LASSO_LINKAGE_DEFAULT_MIN_BAND_SIZE = 5`
- Hooked into `setBandTraceFishSet` (turn 161 — fish-set change
  invalidates linkage cache)

**Slices 2, 4, 5 deferred** (see §6 below).

**Page contract**: `docs/generated/page_contracts/local_pca_dosage/`
(linkage table is part of local_pca_dosage's lines panel header)

**Companion specs**:
- `specs_done/SPEC_band_track_extraction_and_l3_single_band_rows.md`
  (parent — `state.bandTraceFishSet` is the canonical fish-set input)
- `specs_done/SPEC_l2_sweep_inheritance.md` (defines
  `confirmed: true` discipline — only confirmed candidates are
  considered)
- `specs_done/SPEC_lines_panel_candidate_bands.md` (Slice 2 of THIS
  spec needs careful Z-order interaction with the turn 141
  candidate-bands feature)

---

## §1. Purpose

Given a **fish-set** (a Set or Array of integer sample indices that
the user has selected via the lasso, the band-trace 🔍 trace, or
some other source), compute and display **per-candidate purity** —
which band of each promoted candidate do these fish predominantly
land in?

This is the **inverse direction** of the band-trace pipeline:

| direction | operates on | asks |
|-----------|------------|------|
| Band-trace | every L2 envelope along the chromosome | "Where do these fish co-segregate?" |
| **Linkage (this SPEC)** | saved candidates (sparse, user-promoted) | "Which band of each promoted candidate do these fish predominantly land in?" |

Manuscript-relevant: feeds the inversion paper's "shared genetic
background" claim with a quantitative metric.

## §2. Slice plan

| slice | what ships | status |
|-------|-----------|--------|
| **Slice 1** | Pure compute `_computeLassoLinkage(fishSet, candidateList, opts)` + cache layer + TSV export | ✅ shipped (turn 164) |
| **Slice 2** | Alpha intervals on per-sample-lines (paint shaded bp ranges where strong links exist) | 🟡 deferred |
| **Slice 3** | Linkage-table sidebar / modal popover | ✅ shipped (turn 164) |
| **Slice 4** | Enlarged per-sample-lines page (whole new atlas page; multi-turn scope) | 🟡 deferred |
| **Slice 5** | Candidate-page integration (auto-lasso on band click + open modal) | 🟡 deferred (depends on Slice 2 + 4) |

## §3. Slice 1 — Pure compute

### §3.1 Signature

```js
_computeLassoLinkage(fishSet, candidateList, opts) → result | null
```

`opts`:
- `purity_threshold` — default `0.7`
- `min_band_size` — default `5`
- `chrom_filter` — optional; defaults to all chroms

### §3.2 Returns

```js
{
  n_fish_selected:      <int>,
  n_candidates_seen:    <int>,
  purity_threshold:     <float>,    // echoed for TSV header
  min_band_size:        <int>,      // echoed for TSV header
  per_candidate: {
    "<cid>": {
      id, chrom, start_bp, end_bp, K,
      best_band, best_purity, n_in_best_band,
      n_lasso_seen,                  // fish-set members assignable in this candidate
      per_band: [{band, n_in_lasso, fraction}],
      is_strong_link,                // best_purity ≥ threshold AND n_in_best_band ≥ min_band_size
    },
    ...
  },
  strong_links: ["<cid>", "<cid>", ...],   // sorted by purity desc, ties by n_in_best_band desc, then id asc
}
```

### §3.3 Skip rules

A candidate is skipped (not included in `per_candidate`) when:
- `!c.confirmed` (per `SPEC_l2_sweep_inheritance §6`)
- No `c.locked_labels`
- All fish-set members are out of range (`< 0` or `≥ locked_labels.length`)
- All fish-set members map to label `-1` or `≥ K` (no assignable
  band for any fish)

A fish-set member is treated as `n_lasso_seen += 1` for this
candidate when its locked label is in `[0, K)`.

### §3.4 Defensive returns

`null` is returned when:
- `fishSet` is null or empty
- `candidateList` is null or not an array

### §3.5 Headless-pure

The compute takes both inputs explicitly so tests can drive it
without building a state object. The state-aware wrapper is
`_lassoLinkageGetOrCompute()` (§3.6).

### §3.6 Cache layer

- `_lassoLinkageCacheKey(chromFilter, fishSet, candidateList)` —
  deterministic key. Order-insensitive in fish-set; sensitive to
  `chrom_filter`, fish-set fingerprint, and candidate-list
  fingerprint (computed from IDs of confirmed candidates with
  `locked_labels` — so add/remove/promote/demote all bust the cache
  without a separate version counter).
- `_lassoLinkageGetOrCompute(opts)` reads `state.bandTraceFishSet` +
  `state.candidateList`. Returns cached result on key match;
  otherwise recomputes. Caches on `state.lassoLinkageCache` +
  `state.lassoLinkageCacheKey`.
- `_invalidateLassoLinkageCache()` clears both slots.
- **Hooked into `setBandTraceFishSet`** (turn 161): any fish-set
  change auto-invalidates the linkage cache.

### §3.7 TSV export

- `_lassoLinkageToTSV(result, opts)` — pure serializer:
  - 4 comment lines: `# n_fish_selected`, `# n_candidates_seen`,
    `# purity_threshold`, `# min_band_size`
  - Header row + data rows
  - Sort: strong links first by `best_purity` desc, then weak by
    `best_purity` desc; ties broken by `n_in_best_band` desc, then
    `id` asc
  - Floats to 6 dp; NaN/null → empty
- `_lassoLinkageDownloadTSV()` — Blob/anchor download path with same
  headless-safe contract as turn 162's `_bandTraceDownloadTSV`.
  Filename: `lasso_linkage_<chrom>_n<n_fish>.tsv`. Returns the
  filename in headless environments without trying to call DOM APIs.

## §4. Slice 3 — Modal popover

`_openLassoLinkagePopover()` opens a fixed-position modal:

### §4.1 Structure

- **Title**: "Fish-set linkage" + summary stats line
  `n_fish=… · n_candidates=… · N strong link(s) (purity≥0.7)`
- **Status line** explaining sort order
- **Table** with columns:
  - candidate
  - chrom
  - span (Mb)
  - best band (with band-color swatch via `_gpKaryoColor`)
  - purity %
  - n in band / n lasso seen
  - strong?
- **Embedded `📊 TSV` button** → routes to `_lassoLinkageDownloadTSV()`
- **Close button** (`close ×`) + close-on-Esc + close-on-backdrop-click
- **Footer paragraph** reiterating the **observation-only framing**
  (we observe linkage; we don't claim mechanism)

### §4.2 Empty state

When no fish-set is active, the modal **still opens** but renders an
instructional empty state:

> Click 🔍 trace on the lines panel first

This is intentional — explaining the missing prerequisite is more
useful than a no-op.

### §4.3 Idempotent build

The modal HTML structure mirrors `openVShapePlot` (turn 156). First
open builds the DOM; subsequent opens reuse it and just call
`_renderLassoLinkageTable()` to refresh.

### §4.4 Lines header trigger

One new button next to `📊 runs`:

```
[ ] band trace    🔍 trace    [largest ▾]    📊 TSV    📊 runs    🔗 linkage
```

`#linesBandTraceLinkageBtn` has an informative title and routes its
click to `_openLassoLinkagePopover()` via try/catch.

## §5. Strong-link definition

A candidate qualifies as a `strong_link` when **both**:

- `best_purity ≥ purity_threshold` (default 0.7)
- `n_in_best_band ≥ min_band_size` (default 5)

Strong-link candidates are sorted to the top of the modal table and
TSV export.

## §6. Deferred slices (Slices 2 / 4 / 5)

### §6.1 Slice 2 — alpha intervals on per-sample-lines

Paint alpha-shaded bp ranges on the per-sample-lines panel for every
strong-link candidate. **Deferred** because:

- Visual layout on lines is already crowded — two strips (lineage +
  band-trace) + candidate band highlights (per
  `SPEC_lines_panel_candidate_bands`) occupy the upper area.
- Z-order with turn-141 candidate bands needs design:
  - Slice 2 alpha vs candidate-band fill — same colour space?
  - Different alpha to distinguish "strong link" from "any
    confirmed"?

### §6.2 Slice 4 — enlarged per-sample-lines page

A whole new atlas page dedicated to the lines view + linkage info.
Multi-turn scope. Should also include the genome-wide chromosome
navigator (out of scope for the current modal).

### §6.3 Slice 5 — candidate-page integration

Auto-lasso on band click in candidate_focus + open the modal showing other
candidates that share that band's fish-set. Depends on Slices 2 + 4
being further along.

## §7. What turn 164 explicitly did NOT build

Recorded for posterity (per the handoff):

- **Lasso surface itself** — `state.lassoSelection` doesn't exist
  yet; only `state.linesLassoRect` and committed-rectangle slots.
  The lasso → fish-set bridge is its own turn. For now,
  `state.bandTraceFishSet` is the canonical input source.
- **Filter-by-purity-threshold UI control** in the modal. The
  threshold is settable via
  `_computeLassoLinkage(.., {purity_threshold: 0.5})` from the
  console; a UI slider is deferred until Quentin asks.
- **Click-to-jump on table rows.** Spec mentions "Click any row →
  highlight that candidate on the chromosome strip." Deferred
  because the highlight target depends on which page the user is on
  and which chromosome is loaded — needs design.

## §8. Why "observation-only framing" matters

The modal footer reiterates that linkage is an **observation**, not
a mechanism claim. Two fish landing in the same band of multiple
candidates means their genotype patterns co-segregate at those
loci; it does NOT mean the loci share an evolutionary history,
co-inheritance, or any specific genetic mechanism.

Mechanism claims live downstream (page22 banding pipeline + the
evolution-stage cartridges).

## §9. Migration into atlas-core

When this SPEC's pieces migrate from `legacy/Inversion_atlas.html`
into the modular tree, they should land roughly:

- **Pure compute + cache layer + TSV** → `shared/lasso_linkage.js`
  (or `analysis/lasso_linkage/{compute, schema, adapter}.js` per
  the analysis-module recipe)
- **Modal popover** → `pages/discovery/local_pca_dosage/lasso_linkage_modal.js`
  (a new sibling to `band_trace_state.js`, `band_trace_tooltip.js`)
- **Lines header trigger** → wire from `pages/discovery/local_pca_dosage/sidebar.js`

## §10. References

- **Pure compute** (legacy lines TBD — written turn 164):
  `_computeLassoLinkage`, `_lassoLinkageCacheKey`,
  `_lassoLinkageToTSV`, `_lassoLinkageDownloadTSV`
- **State-aware wrapper**: `_lassoLinkageGetOrCompute`
- **Modal**: `_openLassoLinkagePopover`, `_renderLassoLinkageTable`
- **Constants**: `_LASSO_LINKAGE_DEFAULT_PURITY_THRESHOLD = 0.7`,
  `_LASSO_LINKAGE_DEFAULT_MIN_BAND_SIZE = 5`,
  `_LASSO_LINKAGE_MODAL_ID = 'lassoLinkageModal'`
- **Originating handoff**:
  `handoff_docs/HANDOFF_2026-05-05_turn164_lasso_linkage.md`
- **Companion**: `state.bandTraceFishSet` (turn 161 —
  `setBandTraceFishSet` invalidates linkage cache)
- **Slice 2 conflict**:
  `specs_done/SPEC_lines_panel_candidate_bands.md` (Z-order)

---

**Authored**: 2026-05-15 from `handoff_docs/HANDOFF_2026-05-05_turn164_lasso_linkage.md`
+ inline citations from `pages/discovery/local_pca_dosage.html`. One of the 8
SPECs identified as missing on disk in
`_handoff_docs/SPECS_AUDIT.md`. Slices 1 + 3 SHIPPED in legacy turn
164; migration into the modular tree is a follow-up task (§9).
