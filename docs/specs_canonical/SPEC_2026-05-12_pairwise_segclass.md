# SPEC — Pairwise θπ in het-inversion vs collinear segments (cross-atlas request)

**Date:** 2026-05-12
**Originating atlas:** diversity-atlas (request raised; placement deferred)
**Target atlas:** **population-atlas** (per cross-atlas boundary)
**Target page:** new — proposed `pairwise_segclass` (stage: pairwise / structure)
**Reference figure:** Fig. S22, Massilani et al. (archaic-introgression paper) —
absolute divergence (D<sub>XY</sub>) between non-African population pairs
measured in Neanderthal vs Denisovan segments. The catfish analog
substitutes inversion-class segmentation for archaic-class segmentation.

This is a **spec only**, not an implementation. It is written so a
population-atlas session can pick the work up cold without re-deriving
the design.

---

## 1. Scientific premise

Genome-wide pairwise diversity (θπ between sample pairs, or D<sub>XY</sub>)
averages over genome segments that may have very different evolutionary
histories. In the catfish cohort the most informative segment partition is
**heterozygous large inversions vs collinear background**, because:

1. Inversions suppress recombination → haplotypes within an inversion
   accumulate divergence independently of the collinear background.
2. The cohort already has annotated large-inversion candidates
   (inversion-atlas pages 1–6).
3. Inversion polymorphism is one of two mechanistic hypotheses behind
   the "mosaic-rich" sample class identified by DDI (page9 of the
   Diversity Atlas, this session); the other is recent introgression.
4. The hatchery cohort lacks any archaic-hominid analog — there is no
   pre-defined "ancient introgressed" segment class to stratify on.

The plot answers: **which sample pairs sit above the identity line?**
Those pairs are "more divergent in the inversion segments than the
collinear background predicts" — strong candidates for inversion-
mediated haplotype divergence. If those pairs are enriched for cross-K-
cluster comparisons, that confirms inversions as drivers of the broodline
structure observed in the K=8 ancestry partition.

---

## 2. The plot

- **x-axis:** mean pairwise θπ between samples *i* and *j*, computed
  *only* over collinear (non-inversion) windows.
- **y-axis:** mean pairwise θπ between samples *i* and *j*, computed
  *only* over heterozygous-inversion windows
  (windows overlapping a large-inversion BED entry where at least one of
  *i*, *j* is heterozygous for that inversion).
- **Each dot:** one sample pair (226 choose 2 = 25,425 pairs).
- **Dot colour:**
  - light grey: within-K-cluster pair
  - **highlight (cluster-pair palette):** cross-K-cluster pair —
    label by the unordered (K_i, K_j) pair, e.g. "K1×K7"
- **Dashed reference:** y = x (identity). Optional secondary
  reference: ordinary-least-squares fit through within-cluster pairs.
- **Marginal rugs:** y-density and x-density on the axes (the original
  figure had no marginals but they help compare to the per-class
  distribution).
- **Hover:** sample_i, sample_j, K_i, K_j, n_windows_inv, n_windows_col,
  θπ_inv, θπ_col, ratio.

### Display modes (toggle)

1. **All pairs** (25k dots, alpha-blended)
2. **Cross-K only** (≈ 18k dots if K=8 clusters are roughly balanced)
3. **One cluster pair at a time** (dropdown picker, ≈ 200–800 dots)
4. **Cluster-pair means** (collapses to 28 cluster-pair points + error
   bars; analogous to the figure's per-population-pair point density)

---

## 3. Data shape (file the page consumes)

Single payload, planned at
`atlases/population/data/pairwise_segclass.json`:

```jsonc
{
  "params": {
    "win_kb": 50,
    "step_kb": 50,
    "min_callable_per_window": 15000,
    "inversion_set": "large_inv_v3_2026-04",
    "het_definition": "at least one sample of the pair is het for the inversion call",
    "h_proxy": "pairwise θπ_ij_w = 2 * p_i * p_j over called sites in window w"
  },
  "cohort_summary": {
    "n_samples": 226,
    "n_pairs": 25425,
    "n_pairs_cross_K": null,
    "n_windows_inv": null,
    "n_windows_col": null,
    "rho_inv_col": null,         // Spearman ρ across pairs
    "pct_above_identity": null,
    "pct_above_identity_cross_K": null
  },
  "pairs": [
    {
      "i": "CGA009", "j": "CGA010",
      "k_i": "K1",   "k_j": "K3",
      "theta_pi_inv": 1.42e-4,
      "theta_pi_col": 8.30e-5,
      "n_win_inv": 312,
      "n_win_col": 13380,
      "cross_k": true,
      "k_pair": "K1×K3"
    }
    // ... 25,425 entries
  ],
  "cluster_pair_summary": [
    {
      "k_pair": "K1×K7",
      "n_pairs": 412,
      "theta_pi_inv_mean": null, "theta_pi_inv_sd": null,
      "theta_pi_col_mean": null, "theta_pi_col_sd": null,
      "above_identity_pct": null
    }
    // 28 K-pair rows (K=8 choose 2 = 28)
  ]
}
```

### Size estimate

25,425 pairs × ~10 floats = ~250k numbers. JSON-encoded ~ 4–6 MB.
Comfortably embeddable; no need for parquet/binary.

If the K-only display mode is the primary view, the page can lazily load
`pairs[]` only when the user toggles to all-pairs mode — first load
streams just the `cluster_pair_summary[]` (28 rows).

---

## 4. Pipeline (where the data comes from)

Belongs in **`catfish-population-analysis`** (not diversity-analysis, not
inversion-popgen-toolkit). New step, proposed:

`phase_3_pairwise/05_pairwise_theta_segclass.sh`

Substrate inputs:

1. Per-sample, per-window pestPG (already produced by
   `catfish-diversity-analysis/phase_2_discovery/02_run_heterozygosity.sh`).
   Need to derive *pairwise* θπ_ij per window, not per-sample θπ.
2. Large-inversion BEDs from
   `inversion-atlas/atlases/inversion/data/large_inversions_v3.bed`
   (canonical name TBC; check the inversion-atlas data registry).
3. Per-sample inversion genotypes (0/1/2) from
   `inversion-atlas/atlases/inversion/data/inversion_genotypes.tsv`
   (canonical name TBC).
4. K=8 ancestry labels — already in Diversity Atlas D.S1.k8.

Compute:

```
for each sample pair (i, j):
  for each large inversion I:
    is_het_pair = (i_geno_I in {1} or j_geno_I in {1}) and (i ≠ j)
    if is_het_pair:
      contribute window-set of I to "inv" bucket
  remaining windows = "col" bucket
  θπ_ij_inv = mean over inv-bucket windows of 2 * (het_i + het_j)/2
              (or proper IBS-based estimator; ANGSD has a per-pair option)
  θπ_ij_col = same over col-bucket windows
```

Pipeline detail beyond this spec belongs in the analysis repo, not here.

---

## 5. Cross-atlas dependencies summary

| Input | Source repo / file | Status |
|---|---|---|
| per-sample windowed pestPG | catfish-diversity-analysis | exists |
| large-inversion BEDs | inversion-atlas | exists |
| per-sample inversion genotypes | inversion-atlas | exists |
| K=8 ancestry labels | population-atlas (canonical), diversity-atlas (D.S1 mirror) | exists |
| **pairwise θπ per segment class** | **NEW — catfish-population-analysis** | **does not exist** |

The pipeline product is what gates this page. Everything else is already
available.

---

## 6. Why this lives in the Population Atlas (not Diversity)

Per `0_READ_ME_FIRST.md` cohort boundary:

| Concern | Atlas |
|---|---|
| per-sample H, θπ, F_ROH, ROH, DDI, χ_min | Diversity |
| **pairwise between-sample metrics, kinship, structure** | **Population** |
| inversion calls, breakpoints, genotypes | Inversion |

Pairwise θπ is per-pair, not per-sample. It is structurally a Population
Atlas concern, mirroring the page-3 kinship matrix that already sits there.
The split is enforced even though the *mechanistic* motivation (inversion-
mediated divergence between mosaic-rich samples) emerges from the
Diversity Atlas's DDI metric on page 9.

Cross-link policy: Diversity Atlas page 9 (texture) sample-detail panel
should, when the population-atlas page exists, include a "see pairs with
this sample" link that deep-links into the population-atlas pairwise
scatter filtered to this sample's pairs. That is a future cross-atlas
registry decision, not a round-2 deliverable.

---

## 7. Round-1 (population-atlas) plan when ready

Predicates: (a) population-atlas has had its round-1 migration to the
atlas-core architecture (currently it is still a flat 63 KB scaffold per
`KICKOFF_population_atlas.md`); (b) the pairwise pipeline above has run
and emitted `pairwise_segclass.json`.

Then:

1. Create `atlases/population/pages/pairwise/pageN.{html,js}` (page number
   TBD by the population-atlas page list).
2. Register in `manifest.json`, `pages.registry.json`,
   `files.registry.json` (mirror what was done for diversity-atlas page9
   this round — `_handoff_docs/HANDOFF_2026-05-12_round2_texture_done.md`
   is the template).
3. Renderer: scatter plot reusing `atlases/population/shared/plots.js`
   (or, if population-atlas doesn't yet have a shared plots module,
   port `atlases/diversity/shared/plots.js` and `svg.js` over).
4. Display modes (per §2 above) as pill-toggle.
5. Test stub: load the empty-stub file and verify the page renders the
   "data pending" path; load a populated file and verify ≥1 dot draws.

Estimated effort: 2-3 hours once data exists. Without data, the
data-pending scaffold alone is ~1 hour.

---

## 8. What the diversity-atlas does in the meantime

This round (2026-05-12):

- ✅ Page 8 (roadmap) gains a "Cross-atlas requests" card pointing at
  this spec.
- ✅ Spec file in `_handoff_docs/SPEC_2026-05-12_pairwise_segclass.md`.

Nothing else in the diversity-atlas changes. The pairwise scatter does
not, and should not, appear inside the Diversity Atlas.

---

## 9. Open design questions for the population-atlas session

(Distinct from §6 questions in the diversity round-2 handoff; those were
about DDI/χ_min and are settled by atlas-side defaults until pipeline
emits them.)

### 9.1 Pairwise θπ estimator — **deferred to pipeline session**

Simple per-site IBS-based 2pq estimator, or the ANGSD `-doPwTheta`-style
maximum-likelihood pairwise SAF? IBS is faster; ML is more correct
under low coverage. Pipeline-side decision; the page renders whatever
the upstream `pairwise_segclass.json` ships. Build session should
confirm the estimator and surface it in the methods card.

### 9.2 Inversion-segment definition — ✅ RESOLVED (2026-05-12)

**Decision:** **BED interval minus 50 kb breakpoint padding** on each
side. Drops the highest-mapping-artefact zones where read-depth and
genotype error spike. Standard practice in inversion-aware popgen
pipelines.

The 50 kb pad is configurable per inversion (some short inversions
may need a smaller pad to retain usable signal), exposed in the
upstream pipeline config as `breakpoint_pad_bp` with default 50000.
Atlas reads the trimmed segment definition from the BED that ships
with `pairwise_segclass.json` — no atlas-side toggle.

### 9.3 Het-inversion pair threshold — ✅ RESOLVED (2026-05-12)

**Decision:** **(1, 0) and (0, 1) only** — one carrier, one non-carrier.

Cleanest biology: a het inversion pair means one sample has the
inversion arrangement and the other doesn't, so the pairwise θπ
between them captures arrangement-vs-standard divergence. Matches
standard usage in the inversion popgen literature.

Excluded:
- **(1, 1) pairs (both het)** — possibly in *trans* haplotypes that
  separate inversion-internal lineages; mixes the arrangement-vs-
  standard signal with within-arrangement diversity. Statistical
  power gain is not worth the interpretation cost.
- **(0, 0) and (2, 2) pairs** — same arrangement on both sides;
  these are the *outside-inversion* baseline, not het-inversion
  pairs. They populate the collinear-segment distribution.

The pipeline emits two pair lists:
- `het_inversion_pairs[]` — (1,0)/(0,1) pairs only, feeds the
  het-segment θπ distribution.
- `collinear_pairs[]` — all pairs, used for the outside-inversion
  baseline.

### 9.4 Cluster-pair palette — ✅ RESOLVED (2026-05-12)

**Decision:** **midpoint blending of the existing K=8 palette.**

Each (G_i, G_j) pair gets the visual midpoint (Lab-space average)
of group i's and group j's colours from `shared/palette.js`'s K=8
ramp. Within-K pairs (G_i, G_i) keep the pure K colour.

Concrete:
```js
function pairColor(ki, kj, k8palette) {
  if (ki === kj) return k8palette[ki];
  const ci = d3.lab(k8palette[ki]);
  const cj = d3.lab(k8palette[kj]);
  return d3.lab((ci.l + cj.l) / 2, (ci.a + cj.a) / 2, (ci.b + cj.b) / 2).formatHex();
}
```

Maintains visual continuity with page 4's K=8 cluster boxes — the
reader can mentally decode (G_i, G_j) from the blend, no legend
required for the within-K pairs. Cross-K pair blends are still
better than a 28-class categorical palette because consecutive
K-pairs end up perceptually adjacent rather than randomly distributed.

Helper lives in `shared/palette.js` as `pairColor(ki, kj)`; legend
on the page shows the 8 K colours + a "cross-K = blend of pair" note.

### 9.5 Pair-density rendering — ✅ RESOLVED (2026-05-12)

**Decision:** **hex-bin density background + cross-K pair-points overlaid.**

Two-layer rendering:

1. **Background layer — within-K pair density** (where the bulk of
   the 25k points sits). 2D hex-bin over within-K pairs only,
   coloured by count on a perceptual sequential ramp (light grey
   → dark grey). Hex cells render with no stroke.
2. **Foreground layer — cross-K pairs as individual dots.** Plotted
   with the midpoint-blended palette from §9.4. These are the
   lower-density, biologically interesting subset (between-ancestry
   pairs); preserving per-point identity matters here so hover
   tooltips can name (sample_i, sample_j, K_i, K_j).

Best of both: density where it matters (within-K bulk), point
detail where the signal lives (cross-K outliers). Avoids the
"mush at the origin" failure mode of pure alpha-blended scatter.

Rendering knobs (exposed in the panel header):
- Hex bin radius: default 8 px, adjustable 4–16 px.
- Density colour ramp: default viridis-grey; pill toggle to magma
  if the user prefers high-contrast.
- Cross-K dot size: default 3 px, adjustable.

Implementation:
- D3 `d3-hexbin` for the background (already in the project per
  page-3 manhattan rendering — confirm at build time).
- Plain SVG circles for the cross-K overlay; ~1-3k points after
  filtering to cross-K only, well within SVG rendering budget.

---

**Status summary:** 4 of 5 §9 questions resolved this session; only
the upstream estimator choice (§9.1) remains, and that's pipeline-
side, not atlas-architecture. The page can be scaffolded now and
will render correctly whichever estimator the pipeline emits.

---

## 10. Provenance

- Reference figure: Fig. S22 (D<sub>XY</sub> in Neanderthal vs Denisova
  segments between non-African population pairs).
- Catfish-context analog proposed: 2026-05-12 (this session).
- Routing decision (Population Atlas vs Diversity Atlas):
  user-confirmed 2026-05-12.
- Originating chat session: continuation of the diversity-atlas round-2
  texture session (DDI / χ_min).
- Authors of upstream framework: Quentin Andres (cohort & inversion
  framework), Claude (atlas-side design).
- Status: **spec only**. No pipeline run. No atlas page.

---

## Implementation status (updated 2026-05-20)

- Diversity-atlas: **not registered here** (per Spec §6, this is a
  Population Atlas concern). The diversity-atlas's `MISSING_DATA.md` §7a
  carries a doc-only cross-atlas pointer naming this spec.
- Population-atlas: not yet implemented. When it lands, the wiring
  shape per Spec §3 is one JSON at `atlases/population/data/pairwise_segclass.json`
  with `params`, `cohort_summary`, `pairs[]` (25k entries), and
  `cluster_pair_summary[]` (28 K-pair rows).
- Cross-link policy (Spec §6 footnote): diversity-atlas's `texture`
  page sample-detail panel should eventually deep-link into the
  population-atlas pairwise scatter filtered to that sample's pairs.
