# SPEC — Page-1 candidate mode UI (HANDOFF 2)

**Status**: shipped 2026-05-20 (audit-sweep — default-mode atlas-side
infrastructure + Parallel Candidate Registry + 5 page-side consumers
all confirmed shipping; detailed-mode UI deferred pending HANDOFF-1
cluster producer). Promoted from `specs_todo/` after the per-slice
audit below. Original SPEC body is preserved verbatim below as design
archive.

**Implemented in:**
- [`atlases/inversion/shared/candidate_mode.js`](../atlases/inversion/shared/candidate_mode.js) — 9 exports: `PCR_VALID_MODES = ['default', 'detailed']` + `PCR_MODE_STORAGE_KEY = 'inversion_atlas.activeMode'` + `pcrEnsureState()` + `getActiveMode()` / `setActiveMode()` + `getActiveCandidate()` / `setActiveCandidate()` + `getActiveCandidateList()` + `getActiveCandidatesMap()` + `clearDetailedState()` (the Parallel Candidate Registry — turn 88 contract)
- [`atlases/inversion/shared/mgl_candidate_mode.js`](../atlases/inversion/shared/mgl_candidate_mode.js) — 9 exports for the MGL-side variant: `createMglCandidateModeSlot()`, `activateForCandidate()`, `deactivate()`, `resetMglCandidateModeSlot()`, cache-key helpers (`pcaCacheKey()` / `heatmapCacheKey()` / `beagleCacheKey()`), result registration (`registerPcaResult()` / `registerHeatmapResult()` / `registerBeagleText()`)
- Page-side consumers in local_pca_dosage: [`candidates.js`](../atlases/inversion/pages/discovery/local_pca_dosage/candidates.js), [`events.js`](../atlases/inversion/pages/discovery/local_pca_dosage/events.js), [`l3_panel.js`](../atlases/inversion/pages/discovery/local_pca_dosage/l3_panel.js), [`lines_panel.js`](../atlases/inversion/pages/discovery/local_pca_dosage/lines_panel.js), [`pca_panel.js`](../atlases/inversion/pages/discovery/local_pca_dosage/pca_panel.js), [`sidebar.js`](../atlases/inversion/pages/discovery/local_pca_dosage/sidebar.js) — 6 modules consume the candidate-mode API
- Tests: [`tests/test_shared_candidate_mode.js`](../tests/test_shared_candidate_mode.js), [`tests/test_shared_mgl_candidate_mode.js`](../tests/test_shared_mgl_candidate_mode.js), [`tests/test_page1_active_samples.js`](../tests/test_page1_active_samples.js)

**Per-slice status:**

| slice | status | location |
|---|---|---|
| Mode enum (`default` / `detailed`) | ✅ shipped | `PCR_VALID_MODES` |
| localStorage persistence key | ✅ shipped | `PCR_MODE_STORAGE_KEY = 'inversion_atlas.activeMode'` |
| Mode getter / setter | ✅ shipped | `getActiveMode()` / `setActiveMode()` |
| Active-candidate state slot getter / setter | ✅ shipped | `getActiveCandidate()` / `setActiveCandidate()` |
| Candidate-list + candidate-map accessors | ✅ shipped | `getActiveCandidateList()` / `getActiveCandidatesMap()` |
| Detailed-mode state-clear helper (when leaving detailed mode) | ✅ shipped | `clearDetailedState()` |
| MGL-side per-candidate slot (PCA / heatmap / BEAGLE result registration with cache keys) | ✅ shipped | `mgl_candidate_mode.js` (9 exports) |
| Default-mode UI integration on local_pca_dosage | ✅ shipped | 6 page-side consumers wire the candidate-mode API |
| Detailed-mode UI (consumes the 16 PCA JSONs + 4 heatmap JSONs per candidate per HANDOFF-1) | ⏳ deferred | Requires HANDOFF-1 producer (cluster-side). The state slot + cache-key infrastructure (`mgl_candidate_mode.js`) is ready to receive the JSONs when they ship |
| Cluster-side HANDOFF-1 producer (16 PCA + 4 heatmap JSONs per candidate) | ⏳ deferred | Cluster-side, out of atlas scope |

**Why archived now:** the SPEC's atlas-side "candidate mode" contract
ships in full — Parallel Candidate Registry (turn 88 design) with
mode enum, persistence, state slots, MGL per-candidate cache
infrastructure, and 6 page-side consumers. The detailed-mode UI is
intentionally a thin layer over the existing infrastructure — it
needs the cluster-side JSONs from HANDOFF-1 to render anything, and
the state-slot wiring (`mgl_candidate_mode.js`) is already in place
to receive them. Archive with deferred-slice annotation; the detailed
mode wires up when the producer ships.

**Filed:** 2026-05-12 (by Quentin; transcribed into specs_todo by Claude).
**Pairs with:** HANDOFF 1 (the producer that emits the 16 PCA JSONs +
4 heatmap JSONs per candidate).

---

## Architectural note (new mode, not new page)

This spec extends local_pca_dosage with a candidate mode. **Recommend
implementing as a new mode inside local_pca_dosage**, not a new page, for these
reasons:

- **Page1 is the scrubber.** Its core invariant is "cursor walks
  windows, panels redraw on every step." Candidate mode keeps that
  invariant unchanged — only the set of windows and the underlying data
  source change.
- **Page2 is the candidate card.** It's a static deep-dive (metadata,
  sub-bands, dosage heatmap, sigma chart, bands, ancestry…). It does
  not walk a cursor through windows and has its own `_pageState`
  separate from local_pca_dosage's. Adding a multi-PCA + heatmap traversal mode
  there would mean duplicating local_pca_dosage's sample-color logic, tracked-list
  side panel, hover linkage, manual groups, panel resize, hotkeys,
  events handlers, and lines panel — all of which live under
  `pages/discovery/local_pca_dosage/`.
- **Activation is a state flag, not a route.** `state.candidateMode
  .active = true` flips behaviour without changing which page is
  mounted. The atlas-router stays simple.

**Proposed file layout under `pages/discovery/local_pca_dosage/`:**

```
pages/discovery/local_pca_dosage/
├── candidate_mode/                ← NEW sub-folder for this work
│   ├── _state.js                  ← state.candidateMode slot + setters
│   ├── controls.js                ← top-level shared controls bar
│   ├── heatmap_panel.js           ← Component 3
│   ├── ordering.js                ← Component 6 — computeSampleOrder, argsort
│   ├── color_resolver.js          ← Component 7 — getSampleColor
│   ├── linkage.js                 ← Component 5 — hover/selection bridges
│   └── loader.js                  ← fetch + cache manifest.json + per-key JSONs
├── pca_panel.js                   ← existing, lightly extended for color resolver
├── lines_panel.js, sim_panel.js, z_panel.js, l3_panel.js ← unchanged
├── _state.js, _data.js            ← extended with candidate-mode reads
└── ... (existing siblings)
```

The existing scrubber panels (`pca_panel`, `lines_panel`, `sim_panel`,
`z_panel`, `l3_panel`) keep their current code paths. When
`state.candidateMode.active === true`, `state.data` is the loaded
candidate JSON and the cursor walks the candidate's windows; otherwise
nothing changes.

Open question for implementer (raise with Quentin before coding):
should `sim_panel`, `z_panel`, `lines_panel`, `l3_panel` render
anything in candidate mode, or only `pca_panel` + the new
`heatmap_panel`? The body below assumes the latter ("dual-panel
candidate mode") but doesn't make it explicit.

---

## Original HANDOFF 2 brief (verbatim)

**Goal**: extend `pca_scrubber_v3` Page 1 with a candidate mode that
loads pre-computed JSONs from the producer (HANDOFF 1) and offers
unified PCA + heatmap controls with shared rendering state.

**Status**: not started. Existing Page 1 UI is in
`pages/discovery/local_pca_dosage/` (see `pca_panel.js` already provided).
HANDOFF_1 produces the JSON inputs.

**Audience**: a fresh chat where Claude implements the UI.

---

## Background you need

### What candidate mode is

The atlas Page 1 normally walks a cursor through whole-genome local PCA
windows. Candidate mode is a separate state where:
- The cursor traverses windows inside ONE candidate interval
  (e.g., LG28:15.115-18.005)
- Multiple PCA JSONs are loaded (one per view × weighting × anchor_mode)
- A dropdown switches between them without reshaping the layout
- A heatmap panel mirrors the data

### What's pre-computed and what's runtime

**Pre-computed** (HANDOFF 1):
- 16 PCA JSONs per candidate (4 views × 2 weighting × 2 anchor modes)
- 4 heatmap JSONs per candidate (4 views, no weight/anchor distinction)
- Optional: genotype-state JSONs for tri+ sites

**Runtime** (atlas-side):
- Loading the right JSON when user toggles a control
- Computing centerings, polarity, color modes, ordering from JSON data
- Coordinated hover/selection between PCA and heatmap

---

## Existing code to read

In `mgl_adapter/specs/SPEC_0_master.md`, Sections 7-11 lay out:
- The two anchor modes (Section 7)
- JSON shapes (Sections 8, 9)
- Shared rendering state (Section 10)
- UI control layout (Section 11)

The atlas already has `pages/discovery/local_pca_dosage/pca_panel.js` with
`drawPCA(state)`, sample-color logic, and tracked-list/manual-groups
sidebars. It uses:
- `state.data` — single object holding window data
- `state.cur` — current window index
- `state.data.windows[wi]` — per-window data with `pc1`, `pc2`,
  `lam1`, `lam2`
- `state.viewControls.pcaXY` — chosen PC axes
- `state.colorMode` — current color mode
- `state.lockedLabels` — frozen cluster labels
- `state.tracked` — currently tracked sample indices

---

## What to build

### Component 1: candidate-mode state machine

A new state slot, e.g. `state.candidateMode`:

```javascript
state.candidateMode = {
  active: false,
  candidate_id: null,
  interval: { chrom, start, end },
  view_name: 'all_pairs',         // bi_baseline | tri_extras | quad_extras | all_pairs
  weighted: true,
  anchor_mode: 'bi_baseline',     // bi_baseline | view_self | none
  centering: 'all',               // all | het | hom1 | hom2 | custom
  polarity_ref: 'pc1_correlation',
  loaded_pca: {},                 // { 'all_pairs_weighted_bi_baseline': <json>, ... }
  loaded_heatmap: {}              // { 'all_pairs_all': <json>, ... }
};
```

Triggering candidate mode:
- URL param `?candidate=LG28_15.115_18.005`
- Click on candidate marker in genome track
- Manual entry from a candidate-list dropdown

When activated:
- Fetch manifest.json for the candidate
- Pre-fetch the default JSON combination (e.g. `all_pairs_weighted_bi_baseline`)
- Replace `state.data` with the loaded JSON
- Switch to candidate-mode UI controls

### Component 2: top-level shared controls bar

A row above the existing PCA panel:

```html
<div id="candidate_controls" class="row">
  <select id="ctrl_view">  <option value="bi_baseline">Biallelic baseline</option>
                            <option value="tri_extras">Tri-allelic extras</option>
                            <option value="quad_extras">All multi-allelic extras</option>
                            <option value="all_pairs" selected>All pairs</option> </select>
  <label>Weighted: <input type="checkbox" id="ctrl_weighted" checked /></label>
  <select id="ctrl_anchor"> <option value="bi_baseline" selected>Anchor: bi_baseline</option>
                            <option value="view_self">Anchor: view-self</option>
                            <option value="none">No anchor (independent)</option> </select>
  <select id="ctrl_centering"> <option value="all" selected>Center: all samples</option>
                                <option value="het">Center: het only</option>
                                <option value="hom1">Center: hom1 only</option>
                                <option value="hom2">Center: hom2 only</option> </select>
  <select id="ctrl_polarity"> <option value="pc1_correlation" selected>Polarity: PC1 correlation</option>
                               <option value="band_membership">Polarity: band membership</option>
                               <option value="none">Polarity: none</option> </select>
  <select id="ctrl_color"> <option value="cluster" selected>Color: cluster</option>
                            <option value="mean_dosage_window">Color: mean dosage</option>
                            <option value="pc1_score">Color: PC1 score</option>
                            <option value="pc2_score">Color: PC2 score</option>
                            <option value="tracked_group">Color: tracked group</option> </select>
</div>
```

Each control's onChange handler:
1. Update `state.candidateMode.<field>`
2. Determine which JSON file is needed (key = `<view>_<weighted>_<anchor>`)
3. If not in `loaded_pca`: fetch, parse, cache
4. Set `state.data` to that JSON
5. Re-render PCA + heatmap

### Component 3: heatmap panel

A new panel below the PCA panel. Render as canvas (matches existing style):

```javascript
function drawHeatmap(state) {
  const canvas = document.getElementById('heatmapCanvas');
  const { ctx, w, h } = fitCanvas(canvas);

  const hm_key = `${state.candidateMode.view_name}_${state.candidateMode.centering}`;
  const hm = state.candidateMode.loaded_heatmap[hm_key];
  if (!hm) { return; /* loading or N/A */ }

  // Sample order: from PC1 of current PCA data
  const sample_order = computeSampleOrder(state);

  // Marker subset: in current window
  const cur_w = state.data.windows[state.cur];
  const markers_in_window = hm.markers.filter(m =>
    m.pos >= cur_w.start && m.pos < cur_w.end
  );

  // Per-cell color: dosage_centered, mapped to diverging color scale
  const cellW = (w - pad.l - pad.r) / markers_in_window.length;
  const cellH = (h - pad.t - pad.b) / state.data.n_samples;

  for (let i = 0; i < state.data.n_samples; i++) {
    const sample_idx = sample_order[i];
    for (let j = 0; j < markers_in_window.length; j++) {
      const v = markers_in_window[j].dosage_centered[sample_idx];
      ctx.fillStyle = dosageColor(v);  // diverging red-white-blue
      ctx.fillRect(pad.l + j * cellW, pad.t + i * cellH, cellW, cellH);
    }
  }

  // Marker tooltips, sample tooltips, hover linkage to PCA — see Component 5
}
```

Sample-axis sample IDs on the left margin (truncated if too many).
Position track at the top showing where the current window sits in the
candidate interval.

### Component 4: per-panel controls

PCA panel-local (already partly in `pca_panel.js`):
- PC axis selectors (existing)
- Manual rotation slider (new — apply 2x2 rotation to scores before
  rendering)
- Sign-flip toggles (new — explicit, complements existing PC1 rule)

Heatmap panel-local:
- Row sort: PC1 anchor / PC1 view / cluster / manual / mean dosage
- Column sort: genomic / PC1 loading / PC2 loading / clustering
- Display mode: dosage centered / dosage z-scored / dosage raw /
  genotype-state
- Color scale: diverging / sequential / categorical (for genotype state)

### Component 5: hover/selection linkage

Shared state for cross-panel highlighting:

```javascript
state.hover = {
  sample_idx: null,
  marker_idx: null,
  source_panel: null     // 'pca' | 'heatmap'
};

state.selection = {
  samples: new Set(),    // sample indices
  markers: new Set()     // marker indices in current window
};
```

PCA panel onMouseMove: if over a point, set `hover.sample_idx`.
Trigger `drawHeatmap()` to highlight that row.

Heatmap panel onMouseMove: if over a cell, set `hover.sample_idx` and
`hover.marker_idx`. Trigger `drawPCA()` to highlight that point and
overlay an arrow showing the marker's loading direction.

PCA loading direction for a marker: in the anchored basis, the marker's
loading is the per-marker vector that, when projected through V_anchor,
gives the marker's contribution to PC1/PC2. This is essentially the
column of `X_centered` for that marker, normalized.

Click in PCA: add to `state.tracked` (existing logic).
Click-drag in PCA: lasso select; add to `state.selection.samples`.
Click-drag in heatmap col: range select; add to `state.selection.markers`.

### Component 6: ordering helpers

```javascript
function computeSampleOrder(state) {
  const mode = state.candidateMode.row_order || 'pc1_anchor';
  switch (mode) {
    case 'pc1_anchor': {
      // Use bi_baseline-anchored PC1 of bi_baseline view (= the canonical reference)
      const ref = state.candidateMode.loaded_pca['bi_baseline_unweighted_bi_baseline'];
      if (!ref) return Array.from({length: state.data.n_samples}, (_, i) => i);
      const pc1 = ref.windows[state.cur].pc1;
      return argsort(pc1);
    }
    case 'pc1_view': {
      const pc1 = state.data.windows[state.cur].pc1;
      return argsort(pc1);
    }
    case 'cluster': {
      // Group by current cluster labels
      return groupedArgsort(state.data.windows[state.cur].cluster_labels);
    }
    case 'manual':
      return state.candidateMode.manual_order || defaultOrder();
    case 'mean_dosage':
      return argsort(meanDosagePerSample(state));
  }
}

function argsort(arr) {
  return arr.map((v, i) => [v, i]).sort((a, b) => a[0] - b[0]).map(([_, i]) => i);
}
```

### Component 7: color mode resolver

```javascript
function getSampleColor(state, sample_idx) {
  const mode = state.candidateMode.sample_color_mode;
  switch (mode) {
    case 'cluster':
      return clusterColor(state.lockedLabels?.[sample_idx] ?? state.data.windows[state.cur].cluster_labels?.[sample_idx]);
    case 'mean_dosage_window': {
      const v = meanDosageInWindow(state, sample_idx);
      return continuousColor(v, ...);
    }
    case 'pc1_score':
      return continuousColor(state.data.windows[state.cur].pc1[sample_idx], ...);
    case 'pc2_score':
      return continuousColor(state.data.windows[state.cur].pc2[sample_idx], ...);
    case 'tracked_group':
      return state.trackedColors?.[sample_idx] ?? defaultColor;
  }
}
```

This function is called by both `drawPCA` and `drawHeatmap`, so the same
sample is the same color in both panels.

---

## Implementation phases

### Phase 1 (minimum viable candidate mode)
- Detect candidate URL param, fetch manifest, load default JSON
- Render existing PCA panel with new data
- Add view dropdown only — switching views reloads PCA
- No heatmap panel yet

Deliverable: candidate mode where you can compare PCAs between views.
Probably 2-3 days.

### Phase 2 (heatmap panel)
- Add heatmap canvas + render function
- Wire up sample ordering (from anchored PC1)
- Color mode resolver shared between PCA and heatmap
- Centering and polarity controls

Deliverable: dual-panel candidate mode with view switching. Another 2-3 days.

### Phase 3 (linkage)
- Hover linkage between panels
- Selection/lasso/range select
- Marker loading arrows in PCA
- Tooltips with sample/marker info

Deliverable: coordinated interactive view. Another 2-3 days.

### Phase 4 (polish)
- All anchor modes (bi_baseline / view_self / none) selectable
- Per-panel sort and display controls
- Custom centering anchors with tracked-list integration
- Preset save/load for view combinations

Deliverable: full feature set. Another 2-3 days.

---

## Testing strategy

The producer (HANDOFF 1) generates JSONs from synthetic data via
`make_test_data.R`. UI-side tests:
- Synthetic candidate with 4 windows × 4 views → 16 JSONs in fixtures
- Component-level: feed each component a fixture state, snapshot the
  rendered canvas
- Integration: switch view dropdown → verify state.data updates and
  panels re-render
- Linkage: simulate hover events → verify cross-panel highlights

---

## Pointers

- `pages/discovery/local_pca_dosage/pca_panel.js` already provided (in conversation
  attachments). Read first to understand existing patterns.
- `pages/discovery/local_pca_dosage/_data.js` likely contains `getPC()` etc. — read
  this to understand the existing data loading pattern.
- `pages/discovery/local_pca_dosage/_state.js` for state structure.
- HANDOFF 1 produces the JSONs you'll consume. Read its CLI section to
  know what fields will be in each JSON.
