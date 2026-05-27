# SPEC — Local PCA Comparator (cross-evidence view)

**Status**: shipped 2026-05-20 (audit-sweep — Phases 1 + 2 confirmed
shipping; Phase 3 explicitly gated by the SPEC's own "only-if-needed"
rule). Promoted from `specs_todo/` after the per-slice audit below.
Original SPEC body is preserved verbatim below as design archive.

**Implemented in:**
- [`atlases/inversion/pages/discovery/pca_comparator.{html,js}`](../atlases/inversion/pages/discovery/) — page entry
- [`atlases/inversion/pages/discovery/pca_comparator/_state.js`](../atlases/inversion/pages/discovery/pca_comparator/_state.js) — per-page state
- [`atlases/inversion/pages/discovery/pca_comparator/renderer.js`](../atlases/inversion/pages/discovery/pca_comparator/renderer.js) — Phase 1 + 2 renderers:
  - `paintTrajectory(state, si)` at line 527 (per-sample (PC1, PC2) trajectory across the three evidence streams)
  - `computeConcordance(state, si)` at line 630 (fraction of windows where the three streams agree on the sample's L2 cluster)
- [`atlases/inversion/pages/discovery/pca_comparator/heatmap.js`](../atlases/inversion/pages/discovery/pca_comparator/heatmap.js) — supporting heatmap renderer
- Wired in: `pca_comparator.js#_refreshTrajectoryAndConcord` invokes the renderer pair
- Page registration: `manifest.json` + `pages.registry.json` ✓
- Test: [`tests/test_discovery_pca_comparator.js`](../tests/test_discovery_pca_comparator.js)
- Page contract: [`docs/generated/page_contracts/pca_comparator/`](../docs/generated/page_contracts/pca_comparator/) — manifest + canonical PAGE_CONTRACT.md

**Per-slice status:**

| slice | status | location |
|---|---|---|
| Phase 1: side-by-side comparator of 3 PCAs (z-blocks / θπ / GHSL) | ✅ shipped 2026-05-18 | `pca_comparator.{html,js}` + `_state.js` + `renderer.js` |
| Phase 2: per-sample trajectory across the 3 streams | ✅ shipped 2026-05-20 | `renderer.js#paintTrajectory(state, si)` (line 527) |
| Phase 2: per-sample concordance score | ✅ shipped 2026-05-20 | `renderer.js#computeConcordance(state, si)` (line 630) |
| Phase 2 wiring | ✅ shipped 2026-05-20 | `pca_comparator.js#_refreshTrajectoryAndConcord` |
| Page registration | ✅ shipped | `manifest.json` + `pages.registry.json` |
| Test coverage | ✅ shipped | `tests/test_discovery_pca_comparator.js` |
| Page contract docs | ✅ shipped | `docs/generated/page_contracts/pca_comparator/` |
| Phase 3: Procrustes-aligned overlay (3 PCAs into a single rotation-aligned scatter) | ⏳ deferred-by-design | SPEC's own §"Phase 3" gate: "only if there's a real use case AFTER Phase 1+2." Plus rotation-misreading risk: Procrustes alignment can make spurious patterns look like real concordance. Won't ship unless a concrete request arrives that Phases 1+2 can't answer. |

**Why archived now:** the SPEC explicitly stages itself in three
phases, of which Phases 1+2 are shipped (with the exact line-number
pointers and the page-contract docs to prove it). Phase 3 is
deferred-by-design — the SPEC author (Quentin) wrote in the gating
rule that Phase 3 must wait for a concrete use case AND that the
rotation-misreading risk makes shipping it speculatively a mistake.
Per the audit convention, a SPEC whose deferred slices are gated by
its own intentional design (not by missing dependencies) is shipped.

**User question**: "how could we try to have some sort of overlay of
the 3 pcas at once so we can compare ? or have them side by side ?
(for local PCA | local PCA theta pi | local PCA GHSL)"
**User question**: "how could we try to have some sort of overlay of
the 3 pcas at once so we can compare ? or have them side by side ?
(for local PCA | local PCA theta pi | local PCA GHSL)"

**Three evidence streams** (per `_handoff_docs/SPECS_AUDIT.md` + the
discovery stage docs):

| layer | source | page | data path |
|-------|--------|------|-----------|
| Dosage | per-window per-sample dosage K-means | local_pca_dosage | `state.data.windows[w].pc1[]`, `pc2[]` |
| θπ | per-sample nucleotide diversity local PCA | local_pca_theta_pi | `state.data.theta_pi_local_pca` |
| GHSL | haplotype-pair sequence divergence | local_pca_ghsl | `state.data.ghsl_panel.div_roll[scale][sample][window]` |

The three are **orthogonal evidence axes** per the discovery doctrine:
a candidate hit by all three is near-certainly real biology; one hit
by only θπ is a sweep / balancing selection invisible to dosage;
GHSL-only hits are haplotype-specific divergence invisible to
dosage-or-diversity. Today they live on **three separate pages** —
the user has to mentally cross-reference, which is fragile.

## Goal

Make cross-evidence comparison easy at a single window — "does this
fish position consistently in the candidate band across all 3
evidence axes, or is it discordant?"

## Three design options

### Option A — Side-by-side (3 mini panels, synchronized cursor)

```
┌────────────────────────────────────────────────────────────────┐
│  window 3340 — LG28:8.72-8.74 Mb                  [⏮ ⏭]      │
├────────────────────────────────────────────────────────────────┤
│  ┌────────────┬────────────┬────────────┐                       │
│  │   DOSAGE   │     θπ     │    GHSL    │                       │
│  │   PCA      │   PCA      │   PCA      │                       │
│  │            │            │            │                       │
│  │ ⬤ ⬤ ⬤       │ ⬤  ⬤ ⬤      │  ⬤⬤  ⬤      │  ← same colour    │
│  │  ⬤⬤  ⬤      │  ⬤⬤  ⬤      │ ⬤   ⬤ ⬤     │     palette per   │
│  │    ⬤        │   ⬤        │    ⬤        │     sample / K-band│
│  │            │            │            │                       │
│  └────────────┴────────────┴────────────┘                       │
│  hover CGA191 → highlights in all 3 panels                       │
└────────────────────────────────────────────────────────────────┘
```

**Pros**:
- Each layer uses its NATIVE coordinate system (PC1 of dosage stays
  on dosage's PC1 axis; no risk of misleading rotation)
- Visually clean — three small scatters, one per axis
- Implementation is straightforward: reuse `drawPCA()` 3× with
  different data sources + shared `state.cur` cursor
- Synchronized hover works via a single hovered-sample id

**Cons**:
- Visual real estate cost — 3 panels means each is small
- Doesn't show DIRECT correspondence between a sample's positions
  across axes (you have to mentally compare positions)

**Implementation sketch**:
- New page `page_pca_comparator` (stage `discovery_2`)
- Subdir: `_state.js`, `renderer.js` (3 canvas painters), `selection.js`
- Each painter: small adaptation of local_pca_dosage's `drawPCA`, parameterised
  on the data source (dosage / θπ / GHSL)
- Sync layer: shared `state.cur` (window) + `state.hoveredSample`
  drives all 3 simultaneously
- Color palette: K-means band from the **dosage** clustering (the
  user's primary reference); samples retain colour across all 3
  panels so "this fish is band g0 in dosage → also coloured g0 on
  θπ + GHSL panels regardless of where it physically sits there"

### Option B — Procrustes overlay (1 panel, 3 marker shapes)

```
┌────────────────────────────────────────────────────────────────┐
│  Cross-evidence PCA (Procrustes-aligned to dosage)              │
├────────────────────────────────────────────────────────────────┤
│  ⬤ = dosage    △ = θπ    □ = GHSL                              │
│                                                                  │
│        ⬤△□  ⬤△  ⬤                                              │
│         CGA001 ↔ CGA001 ↔ CGA001  (thin line connects markers)   │
│           ⬤                                                       │
│         △  □                                                       │
│        CGA042 — large drift between dosage and θπ                  │
│                                                                  │
└────────────────────────────────────────────────────────────────┘
```

**Pros**:
- Single panel — full visual real estate
- Direct correspondence: each sample is 3 markers connected by a
  thin line; drift = disagreement between axes
- Visually striking when there IS discordance

**Cons**:
- **Procrustes alignment is dangerous** — it ROTATES θπ and GHSL PCs
  onto dosage's coordinate system. The rotation is non-obvious to
  the user and can suggest spurious alignment.
- Requires implementation of Procrustes (existing JS libs available
  but verify they handle missing data correctly)
- Without Procrustes, the overlay is nonsense (PC1 of dosage and
  PC1 of θπ are different axes; raw overlay shows random positions)
- Visually noisy at n=226 × 3 markers + connecting lines

**Three-cohort discipline concern**: Procrustes is a fitting step.
The cohort doctrine (per multiple SPECs) requires that derived
metrics carry provenance. A Procrustes-aligned overlay would need
to clearly label the alignment as "dosage-anchored Procrustes" so
the user doesn't read it as a natural shared space.

### Option C — Per-sample trajectory in 3-axis space

For ONE selected sample, show its (PC1, PC2) trajectory across
windows in each layer's space. Like local_pca_dosage's PC1-lines but stacked
3-way.

**Pros**:
- Shows time-course (windows) of one sample across all 3 axes
- Useful for the "is this fish consistently band g0 throughout the
  candidate?" question
- Reuses local_pca_dosage's `drawLinesPanel` pattern

**Cons**:
- Only useful for ONE sample at a time — not a cohort-wide view
- Doesn't help the "where do the 3 evidence axes agree on the
  candidate footprint?" question

## Recommendation: ship Option A first (Phase 1), evaluate before Option B

### Phase 1 (1-2 days work):

- New page `page_pca_comparator`
- 3 synchronized mini-PCA panels at the active window (`state.cur`)
- K-band coloring inherited from dosage clustering (anchor on
  local_pca_dosage's K=3 H-system)
- Hover sample → highlight in all 3 panels
- ←/→ scrubs the window across all 3 simultaneously

### Phase 2 (if Phase 1 reveals patterns worth comparing more directly):

- Add a "drift" view per sample (Option C — per-sample 3-axis line
  panel)
- Add a "concordance score" badge per sample (how similar are its
  three positions relative to its K-band centroid in each layer?)

### Phase 3 (only if there's a real use case AFTER Phase 1+2):

- Procrustes-aligned overlay (Option B)
- Heavy labelling that the overlay is alignment-anchored on dosage

## What this comparator does NOT do

- It does NOT compute new clustering. K-band labels come from the
  dosage K-means already on local_pca_dosage (or whichever layer is the
  "anchor" — user-selectable).
- It does NOT claim cross-axis biological identity — the user reads
  the comparison; the page never says "this sample is dosage-band-A
  AND θπ-band-A".
- It does NOT replace local_pca_dosage/12/15 — those remain the per-axis
  scanners. The comparator is the side-by-side summary view.

## State surface

Reads:
- `state.cur` — active window (shared cursor)
- `state.data.windows[w].pc1[]`, `pc2[]` — dosage local PCA (local_pca_dosage source)
- `state.data.theta_pi_local_pca` — θπ local PCA (local_pca_theta_pi source)
- `state.data.ghsl_panel.div_roll[scale][sample][window]` — GHSL (local_pca_ghsl source)
- `state.tracked` — tracked samples (highlighted in all 3 panels)
- `state.k` — K-means K used by the dosage anchor
- `state.candidate` — optional; if set, draws the candidate's
  active_band shading in all 3 panels

Writes: nothing — read-only inspector page.

## Open questions

1. **Anchor selection**: should the K-color palette come from
   dosage (local_pca_dosage) always, or be user-selectable via a "anchor: ⊙ dosage  ○ θπ  ○ GHSL" toggle?
2. **Missing data**: if θπ layer is absent on a chrom, do all 3
   panels render with the dosage one alone, or do we hide the
   comparator entirely?
3. **Aggregation when slab-mode**: when L3 compareUnit is `win5`
   etc., do we aggregate across the slab in all 3 panels, or only
   in dosage (where the K-means lives)?
4. **Bp scale visibility**: should the title bar show the window's
   mb range, or just the window index?

## References

- `specs_done/SPEC_band_track_extraction_and_l3_single_band_rows.md`
  — the K-band semantics that drive the colouring
- `specs_done/SPEC_distant_band_concordance_fish_trajectory.md`
  — lineage / band-trace duo, similar cohort-wide compare concept
- `docs/generated/page_contracts/local_pca_dosage/PAGE_CONTRACT.md` — local_pca_dosage's
  drawPCA architecture, reusable for the dosage sub-panel
- `docs/generated/page_contracts/local_pca_theta_pi/PAGE_CONTRACT.md` — local_pca_theta_pi's
  per-window θπ panel (the 6 θπ helpers; `_drawThPcaPanel` is the
  closest analog)
- `docs/generated/page_contracts/local_pca_ghsl/PAGE_CONTRACT.md` — local_pca_ghsl
  (now with 4 panels post-2026-05-15 finish)
- `pages/discovery/local_pca_dosage/pca_panel.js#drawPCA` — the source panel
  to clone × 3

---

**Next step** (user decision needed):

- Should we ship Phase 1 (3 side-by-side panels) as a new page in
  `pages/discovery/page_pca_comparator/`?
- Or extend local_pca_dosage / local_pca_theta_pi / local_pca_ghsl with a "compare" mode that
  splits the existing PCA panel into 3 panes?

The new-page approach is cleaner (no risk of breaking the existing
scanners) but adds a 39th page to the manifest. The extend-existing
approach is denser but more fragile.
