# SPEC — Cramér's V seed-merge auto-promote (alternative to L2-sweep)

**Status**: shipped 2026-05-20 (audit-sweep — both operating modes
confirmed shipping in `shared/cramers_v_merge.js`; the 2026-05-18
"Not implemented" status note was stale by the time the audit ran).
Promoted from `specs_todo/` after the per-slice audit below. Original
SPEC body is preserved verbatim below as design archive.

**Implemented in:**
- [`atlases/inversion/shared/cramers_v_merge.js`](../atlases/inversion/shared/cramers_v_merge.js) — 5 exports covering the SPEC's full surface:
  - `CRAMERS_V_MERGE_DEFAULTS` — frozen defaults block
  - `computeAdjacentSeedMerges(args)` — adjacent-seed-pair Cramér's V scoring
  - `chainsFromMergeVerdicts(verdicts, nSeeds, opts)` — chain-construction from per-pair verdicts
  - `runCramersVMergeLocal(args)` — **Mode 1** from SPEC §"Mode 1 — `insulated_local`"
  - `runCramersVMergeMacrostripe(args)` — **Mode 2** from SPEC §"Mode 2 — `post_long_range`"
- Page-side consumers: [`pages/discovery/haplotype_regimes.{html,js}`](../atlases/inversion/pages/discovery/haplotype_regimes.js) — invokes the merge pipeline alongside band-tracking + L2-sweep for the side-by-side comparison view (per SPEC §"Side-by-side comparison")

**Per-slice status:**

| slice | status | location |
|---|---|---|
| Default values (window-pair adjacency, Cramér's V threshold) | ✅ shipped | `CRAMERS_V_MERGE_DEFAULTS` |
| Adjacent-seed pairwise scoring | ✅ shipped | `computeAdjacentSeedMerges()` |
| Chain construction from merge verdicts | ✅ shipped | `chainsFromMergeVerdicts()` |
| Mode 1: `insulated_local` (no long-range regime input) | ✅ shipped | `runCramersVMergeLocal()` |
| Mode 2: `post_long_range` (uses macrostripe regimes from `SPEC_macrostripe_microgroup_hierarchy`) | ✅ shipped | `runCramersVMergeMacrostripe()` |
| Side-by-side comparison view (3-way: this + band-tracking + L2-sweep) | ✅ shipped | `pages/discovery/haplotype_regimes.{html,js}` consumers |
| Dedicated unit-test for `cramers_v_merge.js` | ⏳ deferred | No dedicated test file — the algorithm is exercised indirectly via `pages/discovery/haplotype_regimes` smoke; a `tests/test_shared_cramers_v_merge.js` should be added in a follow-up for the edge cases described in SPEC §Algorithm |

**Why archived now:** the SPEC's two-mode algorithm (insulated_local
vs post_long_range) ships verbatim in `cramers_v_merge.js` with both
entry points named exactly as the SPEC prescribes. The side-by-side
comparison consumer also ships in `haplotype_regimes`. The only
deferred item is a dedicated unit test — worth tracking but not a
foundational gap (page-level smoke covers the integration).

User direction (chat 2026-05-18): *"the Cramér's V seed-autopromote
must come after the long-range haplotype regime — otherwise it will
merge across windows — or it must be insulated locally. yeah you
can try to set up both modes so we can see by ourselves."*

## The two operating modes

Both modes start from the same input: **Stage 1 seeds** from
`shared/band_tracking/seed_discovery.js`.

### Mode 1 — `insulated_local`

Operates on adjacent-seed pairs ONLY. No cross-window leakage.

For each adjacent (seedᵢ, seedᵢ₊₁) pair:

1. Pull the per-sample K-means labels at seedᵢ + seedᵢ₊₁
   (from `state.l2GroupCache` if cached, else `clusterL2`).
2. Run `chiSquare` + `cramersV` on the K×K Hungarian-aligned
   contingency table (the same math the L3 panel already uses
   in `compareL2Pair`).
3. Verdict per pair: **MERGE** if `concord ≥ state.mergeThr` and
   `p_value ≤ state.alpha`; **SEPARATE** otherwise.
4. Walk the chain: consecutive MERGE pairs grow a run; SEPARATE
   verdicts split the chain.
5. Each chain → a candidate region. Auto-promote when the chain
   passes additional gates (silhouette, populated-band count,
   already-covered) — same gates as the existing L2-sweep.

**Why "insulated"**: the algorithm never compares non-adjacent
seeds. A spurious distant-window contingency match can't pull two
local regions together. Cost: misses long-range homology by design.

**Output**: candidates with `source='auto_cramers_v_local'`.

### Mode 2 — `post_long_range`

Same Cramér's V seed-pair merging, but operates **after**
band-tracking Stage 3 finishes and ONLY within macrostripes that
Stage 3 already grouped together.

For each macrostripe (i.e., each `stage3_loci[i]`):

1. Get the seeds INSIDE this macrostripe (the seeds that voted for
   this locus during Stage 2).
2. Run the same adjacent-seed Cramér's V merge from Mode 1, but
   bounded to within-macrostripe pairs.
3. Auto-promote chains that pass gates.

**Why "post-long-range"**: long-range voting (Stage 2) has already
established the macrostripe identity; this mode does the
finer-grained "where does the macrostripe START and STOP within
the chromosome" boundary refinement using a local Cramér's V test.

**Output**: candidates with `source='auto_cramers_v_macrostripe'`.

### Side-by-side comparison

Both modes run independently when their toggle is on. State slots:

- `state.cramersVMergeEnabled.local` — boolean
- `state.cramersVMergeEnabled.post_long_range` — boolean

Toggles live in the same sidebar group as `state.l2SweepEnabled`.
All three auto-promote sources (`auto_l2_sweep`,
`auto_cramers_v_local`, `auto_cramers_v_macrostripe`) coexist on
`state.candidateList` with distinct `source` tags. The candidate
catalogue and L3 panel surface the source per candidate (existing
chip pattern) so the user can compare which mode found which
candidates.

## Algorithm details

The Cramér's V threshold for MERGE is the same as the L3 panel:
`state.mergeThr` (default 0.85) + `state.alpha` (default 0.05). No
new tuning knobs in Phase 1.

The K used for the contingency is whichever K is active when the
pipeline runs (`state.k`, default 3). Future: allow per-mode K
override (e.g. always use K=3 for the macrostripe-bounded merge
even if user is exploring at K=6).

Cache: per-chromosome `state.cramersVMergeResult.{local,post_long_range}`.
Invalidates on `state.data.chrom` change OR on K change OR on
`state.mergeThr` / `state.alpha` change.

## Implementation surface (~150 LOC)

- New module: `shared/cramers_v_merge.js`
  - `computeAdjacentSeedMerges(state, seeds, opts)` — pure compute
  - `runCramersVMergeLocal(state, seeds)` — Mode 1 driver
  - `runCramersVMergeMacrostripe(state, seeds, stage3_loci)` — Mode 2 driver
- New gate helpers in `pages/discovery/local_pca_dosage/l2_sweep.js`
  (reuse the existing `silhouette` + `populated-band count` +
  `dedupe radius` + `already-covered` gates; just call the
  Cramér's V driver instead of `inheritanceGroupClustering` as the
  source).
- Sidebar toggles in `pages/discovery/local_pca_dosage/sidebar.js`:
  two checkboxes next to the existing `#l2SweepToggle`.
- Source chip in the L3 / candidate-list UI:
  `auto_cramers_v_local` → tag color matching the existing accent
  for L2-sweep, with a small "🅻" or "🅼" badge differentiating
  Mode 1 vs Mode 2.
- TSV export: candidate-list export gains a `source` column (or
  uses the existing one if it's already there).

## What this SPEC does NOT do

- It does NOT replace L2-sweep. The user wants both. L2-sweep
  source = `auto_l2_sweep`; Cramér's V seed-merge sources =
  `auto_cramers_v_local` and `auto_cramers_v_macrostripe`.
- It does NOT change the band-tracking pipeline. Cross-seed voting
  (Stage 2) and projection (Stage 4) stay untouched. Mode 2
  consumes Stage 3 output; Mode 1 doesn't.
- It does NOT introduce new statistics. The Cramér's V + chiSquare
  math already exists in `shared/contingency.js`.

## Open questions

1. **Adjacent definition** — for Mode 1, "adjacent seeds" by
   genomic order or by Stage-2 voting affinity? Default genomic
   order (simpler; what the user means by "insulated"). Mode 2
   uses the affinity-defined locus membership.
2. **Multi-K behaviour** — when the user has K=3 locked but a
   candidate region's seeds were discovered at K=6, do we re-cluster
   at K=3 for the merge test or use K=6? Default: use K=3 (the
   active K).
3. **Cache invalidation on candidate-list mutation** — promoting a
   candidate from one mode shouldn't invalidate the OTHER mode's
   compute. Phase 1: caches are independent (`state.cramersVMergeResult.local`
   vs `.post_long_range`); promotion only touches `candidateList`.
4. **UI affordance for "compare" mode** — should there be a
   visualization that highlights candidates promoted by Mode 1 but
   NOT Mode 2 (or vice versa)? Useful for the audit "which mode
   catches what" but a separate UI feature; not in this SPEC.

## Phase 1 deliverables

1. `shared/cramers_v_merge.js` — Mode 1 + Mode 2 driver + tests.
2. Sidebar toggles + state slots.
3. L3 / candidate-list source-tag chip.
4. Candidate-list TSV export with `source` column (verify; add if
   missing).

## Phase 2 deliverables

- A "compare modes" visualization on the catalogue page: 3-column
  Venn-style of (L2-sweep ∩ Cramér's V local ∩ Cramér's V
  macrostripe) candidates so the user can audit
  agreement / disagreement quickly.
- Optional: a "consensus auto-promote" mode that only promotes
  candidates that ALL three modes agree on (high-confidence
  filter).

## References

- `pages/discovery/local_pca_dosage/l2_sweep.js` — the existing
  auto-promote pipeline this SPEC sits alongside
- `shared/contingency.js` — `cramersV` + `chiSquare` math
- `shared/band_tracking/seed_discovery.js` — Stage 1 source of
  seeds for both modes
- `shared/band_tracking/locus_construction.js` — Stage 3 source of
  macrostripes for Mode 2
- `SPEC_macrostripe_microgroup_hierarchy.md` — the parent SPEC that
  defines the macrostripe / microgroup terminology
- `specs_done/SPEC_l2_sweep_inheritance.md` — the gates pattern
  this SPEC reuses
