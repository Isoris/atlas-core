# SPEC — Per-Sample Heterozygosity Precompute → Atlas Coloring

**Status**: new spec. Specifically scoped to your question: "How can het (dosage) be precomputed and added as a JSON to the atlas to have the coloring of the bands in PCA?"

**Conclusion up front**: You're asking three or four conflated questions. Two of the answers are "the atlas already does this if `ghsl_panel` is loaded — just emit it." One is a real new precompute. One is a band-relabeling problem, not a coloring problem. I'll separate them and answer each.

---

## 1. What the atlas already has (the part I missed in earlier specs)

I went into the atlas to verify before answering. Here's what's actually there for het coloring, surprised me:

### `data_status.het` is wired and equals `data_status.ghsl`

From line 12881-12883 of the atlas:
```js
const data_status = {
  ghsl:     !!(ghslPanel && ghslPanel.div_roll && ghslPanel.start_bp && ghslPanel.end_bp),
  theta_pi: !!(tpiPanel  && tpiPanel.div_roll  && tpiPanel.start_bp  && tpiPanel.end_bp),
  het:      !!(ghslPanel && ghslPanel.div_roll && ghslPanel.start_bp && ghslPanel.end_bp),
  ...
};
```

The atlas treats `het` as available **whenever GHSL is loaded**. The comment at line 12997-12998 explains:
> "Heterozygosity uses the same GHSL primary scale per the comment in `_getLinesValuesAtPanel` — phased-snp het rate by construction."

GHSL = unified-ancestry Engine A's per-sample within-sample haplotype divergence. By construction this equals a phased-SNP het rate computed from the same dosage data. **They're the same signal under two names.**

So when `ghsl_panel` is loaded:
- Page 2 het-shape sub-module activates (per-band het distribution + support_ratio middle/flanks)
- Heterozygosity boxplots populate
- `_hetOfSample(chunkSi)` returns real values per sample (line 14028)
- `support_ratio = bands[1].het_median / mean(bands[0].het_median, bands[2].het_median)` triggers the HET-class detection at ratio ≥ 1.5 (line 13169)

### The color-mode dropdown UI is live but the renderer is a stub

Line 7152, 7465: there's a `state.linesColorMode` with eight options (`kmeans / dosage / ghsl / het / θπ / F_ROH / family / ⚠ confounder`). Validator runs on every JSON load, falls back to `kmeans` when source layer absent. **But** `_resolveSampleColorByMode(si, gi, mode)` and `_resolveSampleScopeColor(si, mode)` are **stubs returning null sentinel** (line 24692-24724). Callers fall back to K-means coloring.

Translation: clicking "het" in the dropdown today silently falls back to K-means. The UI is wired; the renderer body isn't.

### The dosage heatmap renderer takes `sample_het` as an input

Line 14130: `sample_het: lk._hetOfSample` is passed into `drawDosageHeatmap`. The renderer can already color the left annotation track by per-sample het value (line 13739: `const v = opts.sample_het ? opts.sample_het(si) : NaN`).

**So the dosage heatmap path is the most-wired of the lot.** When `ghsl_panel` is loaded, the dosage heatmap's left "het" annotation track populates automatically.

---

## 2. The four questions your message conflates, separated

**Q-A: Color samples by het on per-sample lines panel (page 1).**
Status: UI wired (dropdown), renderer stubbed. Needs `_resolveSampleScopeColor(si, 'het')` body filled in. ~30 JS lines. Reads from `state.data.ghsl_panel.div_roll`. **No new R-side emit needed — already covered by GHSL emit.**

**Q-B: Color samples by het on the PCA scatter (page 1 K-means).**
Status: similar to Q-A but uses `_resolveSampleScopeColor(si, mode)` for dot colors. Same fix, same data source, ~20 JS lines. **No new R-side emit needed.**

**Q-C: Color samples by het on the v3.94 dosage heatmap (left annotation track).**
Status: **already works** when `ghsl_panel` is loaded. The track wires `sample_het: lk._hetOfSample` and renders per-sample. **No code needed; just load the GHSL panel JSON.**

**Q-D: Color samples by *per-candidate-specific* het (so a sample's color changes when you switch focal candidate, like K=3 K-means already does).**
Status: this is the genuinely different one. The current `_hetOfSample` already does this — it averages GHSL over the *candidate's bp range* (line 14041-14051). So Q-D is also already in place, *per-candidate*. **No new R-side emit needed.**

So the answer to your literal question — "How can het be precomputed and added as a JSON" — is **emit the GHSL panel as JSON, and the atlas's existing het machinery activates everywhere.** This is not a new precompute; it's a script that already exists (`STEP_C04c/C04d/export_ghsl_to_json_v3`, atlas line 4108) that needs to be run if it hasn't been.

---

## 3. The thing I think you actually want (and why the literal question is misleading)

Looking at the figures you posted (Image 1/2/3) and what your manuscript needs, I don't think "color by het" is the actual goal. The actual goal is:

> "Make the band labels reflect *which band is the HET class*, not just the K-means-arbitrary band 1/2/3 ordering by PC1 median."

In Image 1/2 (chr15, chr18), the top heterozygosity boxplot identifies cluster 2 as the HET class because its H is highest. In your atlas right now, the K-means K=3 produces three bands ordered by PC1 median, and the **detailed-mode** label resolver (line 4373: H1/H1 / H1/H2 / H2/H2 ordering by PC1) labels them, **but does not check the het-shape support_ratio to confirm which band is actually the HET-class**.

The atlas's own help text (line 6847) flags this:
> "Per-sample heterozygosity is part of pages 2 (θπ) and is being added; until it ships, the detailed labels are operational only."

And again (line 6869):
> "PCA is a projection — observed band order can be (e.g.) H1/H1, H1/H2, H2/H2, H1/H3 even though biologically H2/H3 might be expected to fall between H2/H2 and H3/H3. The detailed labels assigned by the resolver use the most parsimonious sub-pattern from the 3-haplotype model, ordered by median PC1; sub-pattern correctness has to be confirmed against heterozygosity evidence."

So **the missing piece** is: when a band's support_ratio test passes (middle band is hetier than flanks), the atlas should:
1. Confirm the middle band IS the HET class (not just "the one ordered second by PC1")
2. Lock in the labels: outer bands → HOM_REF / HOM_INV (or H1H1 / H2H2), middle band → HET (H1H2)
3. Color the bands accordingly across **every panel** that uses K-means coloring (lines, PCA, sim_mat, dosage heatmap, etc.)

This is what your literature figures show. **Cluster 2 in image 1's heterozygosity panel is colored differently from clusters 1 and 3 because the het evidence makes it the HET class, not because PC1 ordering arbitrarily chose it.**

This is a **labeling/relabeling problem**, not a coloring problem. The colors come from the labels. The atlas already has the data and the test (support_ratio); it's just not promoting the test result into the band labels.

---

## 4. The right precompute architecture

Given the above, here's what I'd actually recommend, three layers:

### Layer 1 — emit GHSL panel JSON (if not already emitted)

**Goal**: activate all the existing het-derived atlas surfaces (het-shape, ridgeline, support_ratio, het pill, dosage-heatmap left track).

**Script**: `STEP_C04c/C04d/export_ghsl_to_json_v3` per atlas docs (line 4108). I haven't seen these audited; they may already exist in the codebase. **Action: check if they exist; run them on LG28 if so.**

**JSON shape** (atlas reads from `state.data.ghsl_panel`):
```json
{
  "ghsl_panel": {
    "primary_scale": "win50000.step10000",
    "scales": ["win50000.step10000", "win10000.step2000"],
    "start_bp": [0, 10000, 20000, ...],
    "end_bp":   [50000, 60000, 70000, ...],
    "div_roll": {
      "win50000.step10000": [
        // sample 0: array of n_windows values
        [0.42, 0.43, 0.51, ...],
        // sample 1: ...
        [0.38, 0.41, 0.49, ...],
        ...
      ],
      "win10000.step2000": [...]
    }
  }
}
```

Drop on page 4 → all het surfaces activate.

**Effort**: probably already exists; ~0-1 turns to run.

### Layer 2 — fill the renderer stubs

**Goal**: make the color-mode dropdown actually work for `het` (and `ghsl`, `θπ`, `dosage`) modes.

**Atlas-side change**: replace stubs at line 24692 (`_resolveSampleColorByMode`) and 24719 (`_resolveSampleScopeColor`) with per-mode bodies. Each body resolves a per-sample value and maps it through a continuous color ramp (e.g. viridis for het rate, diverging blue-white-red for dosage).

**Effort**: ~80 JS lines for all four modes (het, ghsl, θπ, dosage), 1-2 turns.

### Layer 3 — promote support_ratio into band labels (the architectural one)

**Goal**: when the het support_ratio test passes for K=3, lock in the three bands as HOM_LOW / HET / HOM_HIGH labels (instead of arbitrary band 1/2/3), and use those labels for coloring across ALL panels.

**Atlas-side change**: extend `state.bands[].label_role ∈ {hom_low, het, hom_high, ambiguous, indeterminate}` derived from het support_ratio + flanks-comparison logic. Color palette keyed on `label_role` instead of band index.

This integrates with your **grouping framework** (Chat 2): each band becomes a `state.groups[id]` with `source_type: 'kmeans_band'` and a derived `role` field. When grouped consumers (popstats, LD heatmap) ask "which group is HOM_REF / HOM_INV", they read `role` not band index.

**Effort**: ~150 JS lines + integration with the grouping framework. 2-3 turns. **This is the work that actually changes the atlas to match the literature figures.**

---

## 5. What about the per-candidate-specific het value?

The literature figures show heterozygosity **per cluster, per candidate**. Your atlas's existing `_hetOfSample(chunkSi)` already does this — it averages GHSL over the *candidate's bp range* when `cand` is set (line 14041-14051), or over `state.cur ± WINDOW_RADIUS` in cursor mode.

This is per-candidate-specific by construction. The aggregation runs live in the browser at ~30 samples × ~50 windows = ~1500 ops per redraw, sub-millisecond.

**What you might want that ISN'T there**: the per-candidate aggregated het as a **stable value** for each (sample × candidate) pair, so it can be used in tooltips, exports, and registries without reaggregating live every time. This is a small thing — ~100 JS lines to compute and cache `state.candidateList[ci].per_sample_het[si]` once per K-means recompute, then read from cache. Optional polish.

---

## 6. Additionally — `per_sample_het` as an explicit JSON layer (if you want it independent of GHSL)

The atlas docs at line 28302 mention a planned `per_sample_het: Float32Array of length n_samples` cache, suggesting at some point a top-level genome-wide-mean-het-per-sample layer was envisioned. This is one number per sample, useful for genome-wide-het-quantile filtering ("flag samples in the top 5% het rate" — likely contamination signal).

**Shape**:
```json
{
  "per_sample_het": [0.421, 0.398, 0.512, ..., 0.387]
}
```

Where each entry is the genome-wide mean het rate for that sample. Computed per sample by averaging GHSL across all chromosomes. ~5-line R script if GHSL panels exist for all chroms.

**Use cases**:
- Genome-wide het quantile coloring (orthogonal to per-candidate het)
- Outlier detection (samples with anomalous genome-wide het = contamination flag)
- Cohort-level stats reporting

**Effort**: ~50 R lines + ~30 JS lines for the renderer hook.

I'd consider this a *nice-to-have*, not a manuscript blocker. The per-candidate het signal that drives the band-role labeling is the manuscript-critical one.

---

## 7. Honest pushbacks

**Pushback 1**: the literal answer to your question is "you don't need a new precompute — the GHSL panel JSON is the het JSON, already." If `ghsl_panel` isn't loaded yet, that's a "run the export script" problem, not a "design new architecture" problem.

**Pushback 2**: the actually-useful thing isn't "color by het" — it's **"label bands by het role and color by label."** That's a band-labeling layer derived from het, and it's what the literature figures show. The atlas color-mode dropdown's `het` option (continuous color ramp keyed on per-sample het value) is a different visualization than what the literature shows. Both have value, but the band-role labeling is the manuscript-critical one.

**Pushback 3**: there are TWO separate band-color systems in the atlas right now and they aren't synchronized:
- K-means band index (1, 2, 3) → `groupColor(idx)` palette
- Detailed-mode H-system labels (H1/H1, H1/H2, H2/H2) → ordered by PC1 median, NOT by het role

When you "color by het," you'd rationally want consistency: bands are labeled by role (HOM_LOW / HET / HOM_HIGH from het support_ratio), and that role drives coloring across ALL panels (lines, PCA scatter, sim_mat, dosage heatmap, popstats). **That requires the relabeling work in Layer 3 above.** Without Layer 3, "color by het" gives you a continuous ramp that's pretty but doesn't match the discrete-cluster story your manuscript tells.

---

## 8. Where this fits in the roadmap

The HANDOFF document had Chat 2 = "grouping framework." This spec adds three sub-deliverables to Chat 2 (or possibly Chat 1.5):

- **1.5a** (cheap, do first): run `STEP_C04c/C04d/export_ghsl_to_json_v3` on LG28 (if not already), drop GHSL JSON onto atlas. ~0-1 turn. **Activates all existing het surfaces.**
- **1.5b** (small): fill `_resolveSampleColorByMode` / `_resolveSampleScopeColor` stubs for `het` / `ghsl` / `dosage` / `θπ` modes. ~1-2 turns. **Color-mode dropdown actually works.**
- **2.x** (architectural): band-role labeling via support_ratio, integrated with grouping framework. ~2-3 turns within Chat 2. **Bands get HOM_LOW / HET / HOM_HIGH semantics; coloring becomes consistent across all panels.**

Step 1.5a is genuinely cheap and might be worth doing immediately as another "validate the existing pipeline" exercise (similar to running Q10 → 📦). It tests whether the GHSL emit pipeline produces atlas-compatible JSON.

Step 1.5b is the small engineering fix that makes the color-mode UI deliver on what it promises.

Step 2.x is the architectural piece that aligns your atlas labeling with the literature's heterozygosity-class semantics. Worth doing inside the grouping framework chat.

---

## 9. Updated salvage queue

Adding to the queue from previous turn (one numbered slot per item):

26. **`STEP_C04c/C04d/export_ghsl_to_json_v3`** — emit GHSL panel JSON. Likely exists; needs to be run. **Activates all atlas het surfaces with no new code.**
27. **Renderer stubs fill** for `_resolveSampleColorByMode` / `_resolveSampleScopeColor` — modes `het`, `ghsl`, `θπ`, `dosage`. ~80 JS lines, 1-2 turns.
28. **Band-role labeling** from het support_ratio — integrate with grouping framework so `state.bands[].label_role` drives coloring across all panels. ~150 JS lines, 2-3 turns within Chat 2.
29. **Per-candidate per-sample het cache** — optional polish, store `state.candidateList[ci].per_sample_het[si]` for tooltip / export / registry use. ~100 JS lines.
30. **`per_sample_het.json` (genome-wide-mean)** — optional, for outlier detection and cohort-level reporting. ~50 R lines + 30 JS lines.

---

## 10. The closing reflection

I want to be transparent about something. Earlier in the session I kept saying "the atlas was waiting for these scripts." This spec discovers another instance of the same pattern: **the atlas has the het machinery already built and stubbed.** The dropdown works. The renderer takes `sample_het`. The het-shape subview computes support_ratio. The data flows from `ghsl_panel.div_roll` to band diagnostics to histograms.

**What's not connected** is the final mile: stubs return null sentinels (so the dropdown selection is silent), and the support_ratio test passes/fails but doesn't promote into band labels. Both are solvable in the existing atlas code with no new R-side data.

So the literal answer to "how can het be precomputed and added as a JSON" is: **for almost everything you want, you don't need a new precompute. You need (a) to run the existing GHSL export, and (b) to fill in atlas-side renderer stubs.** The new precompute (genome-wide `per_sample_het.json`) is only needed for genome-wide-mean reporting, which is optional.

The interesting work is the **band-role labeling** in Layer 3 — that's the architectural change that makes your atlas's discrete-cluster story match the literature's HOM/HET/HOM coloring convention, and it integrates naturally with the grouping framework.
