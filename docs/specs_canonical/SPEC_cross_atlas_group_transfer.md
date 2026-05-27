# SPEC — Cross-Atlas Group Transfer

**Status**: shipped 2026-05-20 (audit-sweep — Phase 1 selection-mode
primitives confirmed shipping with 4 page-side consumers; Phase 2
cross-atlas transfer correctly gated on atlas-family infrastructure
that doesn't exist yet). Promoted from `specs_todo/` after the
per-slice audit below. Original SPEC body is preserved verbatim below
as design archive.

**Implemented in:**
- Selection-mode primitives — `state.selectionGroup` slot with U-key + Shift+drag entry interactions; live in 4 page modules:
  - [`atlases/inversion/pages/discovery/local_pca_dosage.js`](../atlases/inversion/pages/discovery/local_pca_dosage.js) — entry-point key handler
  - [`atlases/inversion/pages/discovery/local_pca_dosage/g_panel.js`](../atlases/inversion/pages/discovery/local_pca_dosage/g_panel.js) — G-panel integration (selection→group)
  - [`atlases/inversion/pages/discovery/local_pca_dosage/pca_panel.js`](../atlases/inversion/pages/discovery/local_pca_dosage/pca_panel.js) — PCA-side lasso wiring
  - [`atlases/inversion/pages/discovery/local_pca_dosage/sidebar.js`](../atlases/inversion/pages/discovery/local_pca_dosage/sidebar.js) — sidebar surface for the selection group

**Per-slice status:**

| slice | status | location |
|---|---|---|
| `state.selectionGroup` state slot | ✅ shipped | 4 page consumers above |
| `U` key → enter selection mode | ✅ shipped | `local_pca_dosage.js` (entry handler) |
| `Shift` + drag → lasso into `state.selectionGroup` | ✅ shipped | `pca_panel.js` (lasso wiring) |
| `G` key → per-group tab (G panel) | ✅ shipped via `SPEC_g_panel_unified_groups` (already at `specs_done/`) | `g_panel.js` + `local_pca_dosage.html#gPanelOpenBtn` |
| `CTRL` lateral bar → group-transfer UI | ⏳ deferred-by-design | Gated on the atlas-family infrastructure (per `docs/ATLAS_FAMILY_ROADMAP.md`). The transfer target — sending a selection to another atlas — only makes sense once a shell wraps multiple atlases. |
| Notation toggle (g1/g2/g3 vs Hom1/HET/Hom2 vs H1/H1) per CTRL cycle | ⏳ deferred-by-design | Coupled to the lateral bar; ships when the cross-atlas transfer ships |
| Atlas-family handshake (send group → receive on the other atlas, label mapping) | ⏳ deferred-by-design | Requires atlas-family roadmap items to land |

**Why archived now:** the SPEC explicitly stages itself in two phases:
selection-mode primitives now, cross-atlas transfer when the
atlas-family roadmap delivers the shell wrapping multiple atlases.
Phase 1 ships with 4 page consumers. Phase 2 is correctly gated by a
real architectural dependency (no atlas-family infrastructure yet); it
is not deferred "we forgot," it is deferred "the prerequisite doesn't
exist." Per the audit convention, a SPEC whose deferred slices wait on
documented external dependencies (with a tracking doc — here
`docs/ATLAS_FAMILY_ROADMAP.md`) is shipped.

**Audit caveat:** when the atlas-family shell lands and Phase 2
becomes implementable, this archived SPEC should be referenced from
the new work; the deferred-slice table here is the design contract
for what to build.

## Why this SPEC exists

User-stated workflow (chat 2026-05-15):

> "if we press CTRL the groups appear around clusters … or we toggle
> mode g1 g2 g3 or Hom1 HET Hom2 or H1/H1 each CTRL change the type of
> notation"
>
> "if we press G we have the per group tab open but if we press U we
> have the selection mode. we can use shift to lasso select samples
> and CTRL to have the lateral bar open and send that group to
> another atlas to recover it in another atlas"

Reframed in the WIRE_AUDIT (Group G, post-design): cluster-label
notation moves to the **N key** (shipped: commit `df747ea`); CTRL is
reserved for cross-atlas group transfer.

## The selection-mode primitive (ships in this commit)

- **U key**: toggle `state.selectionMode` (boolean). Default false.
  Hotkey gated to not fire in INPUT/TEXTAREA/SELECT; only fires when
  the cartridge's active page is local_pca_dosage. Persists across
  page switches (write to state, no localStorage — selection mode is
  transient).
- **Shift+drag on PCA scatter**: when `state.selectionMode === true`,
  writes the lassoed sample ids to `state.selectionGroup`. Without
  selection mode, Shift+drag retains its v3.39 manual-group behaviour
  (writes to `state.manualGroups`).
- **State shape**: `state.selectionGroup = { ids: number[], source_atlas: string, source_page: string, source_window: number, ts: number }`
- **Visible affordance**: when selection mode is active, the PCA
  scatter container gets a `data-selection-mode="1"` body attribute
  so CSS can change the cursor + paint a subtle hint badge somewhere
  visible. Style: amber outline mirroring the K-cycle button.
- **G-panel manual tab**: gets a "save selection as group" button when
  `state.selectionGroup` is non-empty. Promoting writes a NEW manual
  group from `selectionGroup.ids` then clears `selectionGroup`.

## The cross-atlas lateral bar (deferred)

Why deferred: writing the receiving-atlas side of this needs:

1. **atlas-core API to enumerate sibling atlases** mounted in the same
   workspace (e.g. inversion + diversity + genome). Per
   `docs/ATLAS_FAMILY_ROADMAP.md` this is the "atlas family" runtime
   that hasn't shipped yet — the inversion cartridge doesn't know
   about its siblings today.
2. **Serialization format** for the group. Proposal:
   ```json
   {
     "schema_version": "cag.v1",
     "source": {
       "atlas":  "inversion",
       "page":   "local_pca_dosage",
       "chrom":  "LG28",
       "window": 3340,
       "candidate_id": "I3",
       "k_mode": "kmeans-K3"
     },
     "ids": [12, 14, 17, 19, ...],
     "ts":  "2026-05-18T11:23:47Z",
     "label": null
   }
   ```
   Stored in `localStorage` under
   `inversion_atlas.crossAtlasInbox.v1` as an array of these
   payloads (cap at 20; oldest dropped first). Cross-atlas
   semantics: sample ids interpreted in the **source** cohort's
   index space; the receiving atlas does the resolve (sample names
   are the durable link, not the index).
3. **Receiving-atlas inbox UI**. When the user switches to another
   atlas with a non-empty inbox, a banner offers "incoming group from
   <source>". Click to materialize as a manual group on the target
   atlas's canvas. Mirrors the local_pca_dosage tracked-samples aside
   pattern.

## CTRL plumbing — what ships when

| stage | what's wired |
|-------|--------------|
| **stage 1** (this commit) | U key toggles selection mode; Shift+drag writes to `state.selectionGroup`; G-panel manual tab gets the "save selection" button |
| **stage 2** (next sprint) | CTRL on the local_pca_dosage page opens a right-side panel listing other atlases registered in `window.atlasRegistry` (read-only — doesn't transfer yet) |
| **stage 3** (atlas family) | Selecting an atlas in the panel writes the group to `localStorage.crossAtlasInbox.v1`; the receiving atlas's banner reads it on next mount |
| **stage 4** (polish) | "recover group" button on the receiving side; persisted last-N transfers list |

## What this primitive does NOT do

- It does NOT replace `state.manualGroups` — manual groups are the
  canonical "I named this group" persistent slot. `selectionGroup` is
  the *staged* slot before the user decides to keep it.
- It does NOT auto-recolor on selection. The PCA scatter shows the
  lasso box during the drag; on release, the selected samples get a
  thin halo (paint hook in `drawPCA` post-pass). The user explicitly
  promotes to a manual group to make it persistent.
- It does NOT cross atlases in stage 1. The lateral bar is stage 2+.

## State surface

Reads:
- `state.selectionMode` — boolean toggle written by the U key
- `state.selectionGroup` — `{ ids, source_atlas, source_page, source_window, ts }`

Writes (from this primitive):
- `state.selectionMode` — toggled by U
- `state.selectionGroup` — set by Shift+drag lasso when
  selectionMode === true; cleared when promoted via the G-panel

## Open questions

1. **Multi-selection mode**: should Ctrl-click on an existing selection
   ADD to it instead of replacing? The audit didn't specify.
2. **Lines-panel parity**: should `linesLassoToggle` also respect
   `state.selectionMode` so the same primitive works on the per-sample
   lines panel? Probably yes for stage 1 — easy extension.
3. **Cross-atlas naming**: when the same group is sent twice from
   different atlas / window combinations, should the receiving inbox
   merge or stack? Stack (default), merge via a manual user action
   later.
4. **Privacy/scope**: the cross-atlas inbox lives in localStorage —
   browser-scoped, not user-account-scoped. For shared analysis
   sessions this might surprise users. Worth a separate consent
   prompt on first cross-atlas send.

## References

- `docs/ATLAS_FAMILY_ROADMAP.md` — atlas-family runtime (the
  cross-atlas SPECs hinge on this)
- `_handoff_docs/WIRE_AUDIT_page1.md` §Group G — original user
  workflow + audit's design refinement
- `specs_done/SPEC_g_panel_unified_groups.md` — the G-panel where the
  manual tab will get the "save selection as group" button
