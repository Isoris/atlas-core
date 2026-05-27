# SPEC — Atlas Live Sim_Mat Navigator + Manual Boundary Annotation

**Status**: draft, two specs in one document. Spec A is near-term; Spec B is deferred.

**Source**: Quentin chat 2026-05-02. Idea: turn the atlas page-1 sim_mat into a live navigator over the chromosome, automate L1/L2/candidate detection into precomp so it just works, allow manual boundary annotation that cross-shows across pages 1, 12, and any future per-method discovery page.

**Scope split**: this proposal naturally separates into two features with different urgency and risk. I'm specifying both but flagging Spec B explicitly as last-priority so it doesn't block the win from Spec A.

---

## Spec A — Pan/zoom live sim_mat navigator + bake L1/L2 detection into precomp

### A.1 Motivation

Page-1 sim_mat currently renders the whole chromosome at fixed resolution. On a 4302-window chromosome (LG28) that's ~2 windows per pixel — readable but coarse for boundary inspection. Multi-scale smoothing (nn40/80/160/320) helps but doesn't substitute for actually zooming in.

Separately, L1/L2/candidate detection runs as a separate command-line step (the STEP_D17_multipass_L2_v8 family). The boundaries arrive at the atlas as a TSV that gets read at load. Quentin wants this folded into precomp so it's automatic.

These are two changes that compose naturally:
- **Bake detection into precomp** → boundaries always present, no separate command-line pass to remember
- **Pan/zoom navigator** → user inspects boundaries at the resolution they need, refines automatic detection by eye

### A.2 What changes

#### A.2.1 Precomp pipeline

Add a step to the per-chromosome precomp Snakefile that runs the L1/L2 multipass scan (v8) on the just-computed sim_mat and writes the envelope/candidate arrays into the same `.precomp.rds` (or a sidecar JSON the atlas already reads).

Specifically: `STEP_D17_multipass_L1_only_v7.R` for L1 envelopes, `STEP_D17_multipass_L2_v8.R` for L2 sub-blocks, both with the v8 anchor-shift fix already baked in. Output schema is the existing one — atlas already reads it. The change is purely "where does the boundary file get written" — moved from a separate pass into the precomp pipeline.

Side effect: parameter knobs for the v8 algorithm get fixed in the Snakefile config rather than passed at runtime. A change in detection threshold means re-running precomp for that chromosome. That's the right tradeoff for reproducibility.

#### A.2.2 Atlas viewport state

Add to `state`:
```
state.simMatView = {
  startMb: number,         // viewport left edge
  endMb: number,           // viewport right edge
  zoomLevel: int,          // 0 = full chrom, increments halve range
  smoothingMode: string    // existing: precomp/nn40/nn80/nn160/nn320
}
```

Persisted per chromosome in localStorage (key includes `chrom`). Default to `(0, chrom_length)` on first visit.

#### A.2.3 Pan/zoom interactions

On the page-1 sim_mat panel:
- **Drag** anywhere on the heatmap with the left mouse button to pan horizontally and vertically simultaneously (sim_mat axis is symmetric; both axes scroll together to stay on the diagonal)
- **Scroll wheel** zooms in/out around the cursor position. Zoom doubles or halves the visible range per click. Cap at "full chromosome" (zoom out) and "minimum 50 windows visible" (zoom in)
- **Double-click** centers on that position at the next zoom level
- **Esc / button** resets to full chromosome

L1/L2/candidate overlays render at all zoom levels. As you zoom in, automatic boundaries that were 1px wide become visible bands. Multi-scale smoothing toggle (nn40/nn80/etc.) stays orthogonal — user can pick smoothing scale + zoom level independently.

#### A.2.4 Cross-pane sync

When the user zooms/pans on page 1, the same viewport applies to:
- The |Z| waveform panel (already shares x-axis)
- Per-sample lines panel
- L3 contingency strip

All these already use the chromosome x-axis; they just need to read `state.simMatView.startMb/endMb` instead of the implicit chromosome bounds.

This is the existing chained-cursor / rendering pattern, just with mutable bounds instead of fixed.

#### A.2.5 Render strategy

**For zoomed-in views**: re-slice the sim_mat to `[start_window, end_window]` and render into the existing canvas at the canvas's pixel dimensions. The sim_mat data is already in memory — slicing is O(1) data lookup, render is O(visible_pixels²).

**For full-chromosome view**: behaves identically to current rendering. No regression.

**Smoothing**: precomputed multi-scale layers (nn40..nn320) apply at full chromosome scope. When zoomed in to <500 windows, drop smoothing automatically (raw is fine at high resolution) or let user override. When zoomed out to >2000 windows, default to nn80 or higher.

### A.3 What does NOT change

- L1/L2/candidate detection algorithm (STEP_D17_multipass_v8): unchanged, just moves into precomp Snakefile
- Sim_mat data: unchanged
- Per-sample lines panel data: unchanged
- L3 contingency: unchanged

This is purely an ergonomics + automation update. Zero algorithmic change.

### A.4 Cost estimate

- Precomp Snakefile addition: ~30 lines, 1 turn
- Atlas viewport state + pan/zoom handlers: ~150-200 JS lines, 2-3 turns
- Cross-pane sync (route `simMatView` through existing render functions): ~30-50 lines, 1 turn

**Total: 4-5 atlas turns** + 1 precomp Snakefile turn. Manageable.

### A.5 Risk

- Pan/zoom on a canvas-rendered heatmap is well-trodden territory; standard mouse-drag deltas + viewport math.
- L1/L2 detection moving into precomp risks "old precomp files don't have boundaries" — handle by checking for the boundaries field, falling back to no-overlay if absent. Atlas already does this for some optional layers.
- Performance: re-rendering the sim_mat panel on every drag-pixel is wasteful. Throttle to requestAnimationFrame, redraw on mouseup if needed.

### A.6 Acceptance

- User opens page 1 on any chromosome → full-chr sim_mat with L1/L2/candidate overlays renders (current behavior preserved)
- User scroll-wheel-zooms on a region → sim_mat re-renders showing that region at higher resolution, |Z| waveform and lines panel re-render to same x-range
- User pans by dragging → smooth horizontal scrolling; overlays stay anchored to genomic positions
- User reloads the page → returns to the same viewport (localStorage persistence)
- A regenerated precomp file produces L1/L2/candidate overlays identical to what the standalone STEP_D17 v8 pass produced

---

## Spec B — Manual boundary annotation cross-shown on pages 1/12/3 (DEFERRED, last priority)

### B.1 Motivation

Sometimes the automatic L1/L2 detection misses or misplaces a boundary. Currently the workaround is to re-run detection with different parameters, or note the disagreement in a TSV outside the atlas. Quentin wants to drop a boundary directly on the atlas sim_mat by clicking, and have that boundary persist + cross-show on every page that displays a position track for the same chromosome (page 1 dosage, page 12 θπ when it ships, future per-method pages).

This is meaningful because:
- The user can see things the algorithm misses (subtle texture changes, asymmetric edges)
- Cross-method consistency is the strongest validation: if manually placed boundaries on page 1 line up with auto-detected boundaries on page 12 (different signal), that's independent confirmation
- It enables a curation workflow: scan the chromosome → eyeball the algorithm's calls → add/remove/adjust → export the curated boundary set as the "paper-ready" call

This is bigger than Spec A. It's a real feature with multiple consequences. Hence the deferral.

### B.2 Open questions

These need answering before implementation. Listed honestly because some are non-trivial.

#### B.2.1 What is a "manual boundary"?

Three plausible levels:
- **L1 boundary**: a chromosome-scale boundary delimiting a long region of homogeneous structure
- **L2 boundary**: a sub-block boundary inside an L1 region
- **Candidate boundary** (the existing object): pair of left + right edges defining an inversion candidate

Are users placing all three independently? Or is the manual annotation always at one level (L2 or candidate), with L1 staying automatic?

I'd argue: only manual **candidate** boundaries are needed. L1 and L2 are intermediate scaffolding the user doesn't usually need to override directly; they just want to say "this is an inversion from here to here" or "this auto-detected candidate's right boundary is wrong, move it 200kb left." If that's right, the data model simplifies a lot.

#### B.2.2 Persistence and cohort-keying

Manual annotations must survive:
- Atlas page reloads → localStorage (already done for other settings)
- Precomp regenerations (window indices may shift) → store as Mb positions, not window indices
- Different cohorts → cohort-keyed localStorage, like the existing `_activeSamplesCohortKey`

Should they survive cross-machine? If so → JSON export/import (not just localStorage). Probably yes; user might curate at the desk and run the manuscript on the cluster.

#### B.2.3 Data model

Proposed:
```
state.manualAnnotations = {
  byChrom: {
    "C_gar_LG28": [
      {
        id: "manual_001",
        type: "candidate" | "l1" | "l2",
        leftMb: number,
        rightMb: number,
        note: string,             // free-text user note
        createdAt: timestamp,
        modifiedAt: timestamp,
        sourcePage: "page1" | "page12" | ...   // which page user placed it on
      },
      ...
    ]
  }
}
```

Persisted as cohort-keyed JSON in localStorage. Exportable to TSV with columns `chrom, type, left_mb, right_mb, note, created_at, source_page`.

#### B.2.4 Conflict resolution with auto-detected boundaries

When a manual annotation overlaps an auto-detected one:
- **Display**: render both, distinguishable (auto = solid, manual = dashed; or auto = grey, manual = orange)
- **Downstream contingency / classification**: which set drives K-means scope, σ-profile, fam_purity?

Two policies:
- **Auto wins, manual is annotation only** — simpler. Manual annotations are eyeball notes; the algorithm's calls drive everything downstream.
- **Manual overrides when present** — user explicitly says "this is the inversion." Downstream calculations re-scope.

I'd default to **auto wins, manual is annotation only** for v1. The "manual overrides" path opens a can of worms (now everything downstream depends on the user's localStorage state, which is invisible to anyone reviewing the manuscript). If users want to push manual calls into the analysis pipeline, they should export the TSV and re-run precomp with that TSV as input — making the override explicit and traceable.

Quentin: this is a real fork to think about. The "annotation only" path is much safer and aligned with how scientific tools handle user scribbles. The "override downstream" path is more powerful but breaks reproducibility.

#### B.2.5 Cross-page rendering

Every page that displays a chromosome-scale position track needs to render `state.manualAnnotations.byChrom[chrom]` for the current chromosome. Currently page 1 (sim_mat + |Z| + lines), page 12 (when it ships, θπ versions of the same), and probably page 7 (ancestry tracks).

Not trivial because each page has its own renderer. A shared overlay function (`renderManualAnnotations(canvasContext, viewport, annotations)`) reused by all pages keeps the work tractable.

#### B.2.6 UI for adding/editing/deleting

Click on the sim_mat at a position → modal asks "what do you want to mark? L1 / L2 / candidate / cancel". For candidates, expects a second click for the right boundary (or drag from left to right). Existing annotations get a small handle when hovered; drag to reposition, right-click for delete + edit-note menu.

Modeless add: "annotation mode" toggle in the page-1 toolbar; when on, clicks add annotations; when off, clicks select/edit existing ones.

This is real UI work. ~300-400 JS lines. Multiple turns.

### B.3 Cost estimate

- Data model + persistence + export: ~100 lines, 1-2 turns
- Add/edit/delete UI on page 1: ~300 lines, 2-3 turns
- Cross-page renderer (overlay function reusable across pages): ~80 lines, 1 turn
- Spec the conflict-resolution policy explicitly + document it in atlas help: 1 turn

**Total: 5-7 atlas turns**. Not huge but bigger than Spec A.

### B.4 Risk

- The "manual overrides downstream" policy choice has reproducibility implications. Get it right at v1.
- Annotations stored only in localStorage are fragile; users will lose them when clearing browser data. Export-to-JSON is essential, not optional.
- Cross-cohort: if the user changes the active cohort, are annotations from cohort A visible in cohort B? Default no (cohort-keyed), but the user might want a "universal" annotation set for known landmarks. Decide later.

### B.5 Acceptance

- User clicks on page-1 sim_mat at chr:X.X Mb → annotation modal opens, lets them place a candidate boundary
- The annotation appears as a dashed band on page 1 alongside auto-detected solid bands
- User reloads → annotation persists
- User opens page 12 (θπ method, when shipped) for the same chromosome → same dashed band appears at the same Mb position
- User exports → JSON file with all annotations across all chromosomes
- User imports JSON on a fresh atlas → annotations restored

---

## Cross-cutting decisions

### Should Spec A and Spec B be one feature or two?

**Two.** Spec A is a 4-5 turn ergonomics + automation win. Spec B is a 5-7 turn workflow feature with policy implications. Bundling them risks Spec A getting blocked on Spec B's design questions.

Ship A first. Use it for a few weeks. Then revisit B with real experience of "what do I actually want to annotate, and how often."

### Does this kill any existing scripts?

**Spec A**: kills the standalone command-line invocation of STEP_D17 multipass scans. The detection code itself stays — just runs from the precomp Snakefile.

**Spec B**: doesn't kill anything; adds a new feature.

### What does this NOT replace?

- `inversion-popgen-toolkit` modules outside the boundary-detection family
- The dosage server (still needed for popstats endpoints)
- The window_metrics / MDS / sim_mat-contrast-mode atlas additions (different feature surface)
- Manuscript figure generation R scripts (separate concern)
- D11a/b per-chr ngsRelate emit (separate evidence layer)

### Where does this fit in the salvage list

Atlas-side additions queue (across 5 audit phases consolidated):
1. window_metrics data layer reader (from C01a profiles audit)
2. MDS view (from C01a mds audit)
3. sim_mat contrast modes: raw / row-Z / row-quantile / dist-normalized + SVD-residual + axis toggle
4. Per-chr relatedness layer reader (from D11a/b emit)
5. AS2-AS5 active-samples extension (already on roadmap)
6. **Spec A — pan/zoom navigator + L1/L2 in precomp** (NEW, this spec)
7. **Spec B — manual boundary annotation, cross-page** (NEW, deferred)
8. Optional IGV.js panel
9. D03 artifact-dip badge
10. D09n masked_local_simmat primitive
11. D09n effect_class live mask badge

Spec A slots in after the contrast-modes work (#3) and pairs naturally with the multi-scale smoothing already on page 1. Spec B is the largest queued item by far; it deserves its own dedicated turn arc.

---

## What this turn shipped

- This document. No code, no precomp changes.

If the spec captures what you meant by "live atlas with right/left scroll, automatic + manual boundaries, cross-shown across pages," it's ready to slot into the consolidated SPEC document I keep flagging. If it doesn't capture what you meant, the gap is probably in **Spec B's data model** (B.2.1 — what level of boundary is manual?) or **B.2.4 conflict resolution** (annotation-only vs override-downstream). Tell me which side you'd land on, I'll update.

Quick recap of what I'm reading from your message and pushing back on lightly:

- "Just live" — yes for navigation, with the caveat that L1/L2 detection still has to run somewhere; it just moves into precomp.
- "Annotate boundaries ourselves" — yes but lower priority than nav, and it has a real policy choice (override vs annotate-only) that needs deciding before code.
- "Make L1 L2 boundary placement automatic then manual review" — yes; that's Spec A + Spec B together. Spec A alone gets you 80% of the value because the automatic detection is already good and you can re-run with different params if it's off.
- "Avoid running L1 and L2 by hand on the command line" — yes, baked into precomp.
- "While the manual boundaries can be set for L1 L2 later and are cross shown across page 1 2 3 methods. But that one its last priority" — agreed and reflected in the deferral.
