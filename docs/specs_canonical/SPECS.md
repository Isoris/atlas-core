# SPECS — master index

Cross-cutting index of every specification in the repo. Pair with
`_handoff_docs/SPECS_AUDIT.md` (provenance) and
`_handoff_docs/ATLAS_PAGES_MAP.md` (consumer inventory).

## The folder convention (locked in 2026-05-15)

```
specs_todo/     — design backlog (authored, not yet implemented)
specs_done/     — shipped (implementation matches the SPEC)
specs_todo/mgl_adapter/  — self-contained spec sub-tree for the mgl
                           adapter library; has its own SPEC_0_master
                           + 5 numbered HANDOFFs + 2 READMEs
```

**Rule**: a SPEC never gets deleted. If the code ships, move the SPEC
from `specs_todo/` to `specs_done/`, update its status line, and add
an `Implemented in:` block at the top. See
`specs_done/README.md` for the workflow.

This rule exists because we lost a `specs_done/` folder at tarball
import time (see `_handoff_docs/SPECS_AUDIT.md` for the forensics).
That doesn't happen again.

## All SPECs at a glance

### Shipped — `specs_done/`

| SPEC | what it covers | implementation |
|------|----------------|----------------|
| `SPEC_registry_v2.md` | 9-item registry v2 design (versioning + write contract + cache invalidation) | `atlases/inversion/registries/data/*.registry.json` + atlas-core registry runtime |
| `SPEC_band_track_extraction_and_l3_single_band_rows.md` | het-anchored band-track skeleton + L3 single-band-rows contingency view | `shared/band_tracking/` (32 modules) + `pages/discovery/local_pca_dosage/l3_panel.js` + `local_pca_dosage/band_diagnostics.js` |
| `SPEC_sv_evidence_page.md` | SV evidence page + producer pipeline | `pages/review/sv_evidence.js` + `js/atlas_sv_evidence.js` + `engines/producers/sv_evidence/` |
| `SPEC_l2_sweep_inheritance.md` | L2-sweep auto-promote pipeline (local_pca_dosage candidate discovery: 6 gates) | `pages/discovery/local_pca_dosage/l2_sweep.js` |
| `SPEC_g_panel_unified_groups.md` | G-panel unified-groups popup (Karyotype / Inheritance / Manual tabs; Slice 1 shipped) | `pages/discovery/local_pca_dosage/{pca_panel.js, manual_groups.js}` + `local_pca_dosage.html#gPanelOpenBtn` |
| `SPEC_lines_panel_candidate_bands.md` | Per-candidate vertical band highlights on lines panel (confirmed-only, palette stable across zoom, default-ON) | `pages/discovery/local_pca_dosage/{lines_panel.js, candidates.js}` |
| `SPEC_lasso_inheritance_backgrounds.md` | Fish-set linkage table (Slices 1 + 3 shipped: pure compute + cache + TSV + modal; Slices 2/4/5 deferred) | legacy turn 164 (migration to modular tree TBD) |
| `SPEC_l3_het_dosage_coloring.md` | L3 mini-PCA dot fill by per-sample het rate (cold blue → warm red); halo stays K-coloured | `pages/discovery/local_pca_dosage/l3_panel.js` + `shared/het_rate.js` + `local_pca_dosage.html#l3HetToggle` |
| `SPEC_review_surfaces_auto_and_lineages.md` | Review surfaces for L2-sweep auto-promoted candidates (Slices 0-2 shipped: dashed CSS + filter pipelines + G-panel auto tab; Slice 3 lineages tab deferred) | `css/inversion.css` + legacy turn 130 + turn 165 (G-panel auto tab) |
| `SPEC_distant_band_concordance_fish_trajectory.md` | Fish-paths dual of band-track (Slices 1-5 shipped: lineage compute, lines color mode, \|Z\| strip, band-trace UI, TSV; Slice 6 cross-strip chaining deferred) | `pages/discovery/local_pca_dosage/{lineage.js, band_trace_*.js}` + `shared/{band_trace.js, clustering.js}` |
| `SCHEMA.md` | Prose schema reference — resolves all "SCHEMA §N" / "SCHEMA_V2.md §N" cross-refs from code; carries §9 cluster-emit, §10 marker columns, §13 evidence framework, §19 14-axis tier, §22 structural scaffold, §26 axis_topology vocab, §27 scale_stability verdicts; reserves §0-§30 for future | `registries/schemas/*.schema.json` (26 files) + `registries/data/*.registry.json` (5 files) + `pages/review/karyotype_tier/tier_axes.js#TIER_AXES` |
| `SPEC_inversion_divergence_network_v1.md` | Candidate-scoped node-link diagnostic: nodes = karyotype groups (STD/HET/INV or arr_0..N) labelled with within-group π, edges = pairwise FST (Nei for dosage, variance-ratio for pc1) or Euclidean distance; flagged weak/strong/low_power for renderer hints. Pure-data layer only (panel wiring deferred). | `shared/divergence_network.js` (compute + render hints with circular layout) + `tests/test_shared_divergence_network.js` (412-line smoke) + referenced from `pages/catalogue/stats_profile.js` |
| `SPEC_inversion_age_atlas_surface.md` | Reconstructed turn-117 parent of the `_AMENDMENT`: per-candidate age + divergence surface. Compute primitives ship; the AMENDMENT's row layout (Page-3 Rows A/B/C/D, Page-5 "rel age" column) carries per-slice shipped/deferred status. | `shared/mgl_inversion_divergence.js` (computeDivergence + age_class) + `shared/age_model_suggester.js` + `shared/busco_4d_age.js` (Method 3 brackets) + `pages/evolution/age_divergence.{html,js}` (four-bar surface + verdict) + `tests/smoke_evolution_age_divergence_round5.mjs` |
| `SPEC_arrangement_color_mode_and_arrangement_calls_v1.md` | Atlas-side decoder + palette + per-sample voting + JSON validator for `arrangement_calls_v1.json` + sample-color-mode dispatcher. Producer-side JSON emitter remains deferred (out-of-atlas scope per §6). Archived 2026-05-20 with per-slice status. | `shared/arrangement_calls.js` (9 exports: schema-version + palette + `decodeArrangementsFromPartition` + `assignArrangementPerSample` + `tabulateArrangementSizes` + `validateArrangementCallsJson`) + `shared/sample_color.js` (mode dispatcher) + `tests/test_shared_arrangement_calls.js` |
| `SPEC_busco_4d_age_brackets.md` | Method 3 absolute-age compute: 3 frozen μ values, dXY → age_my with CI propagation, `busco_4d_age_brackets` JSON block builder + validator + cross-check + Row-C formatters. LANTA producer `STEP_C01f_e_emit_busco_4d_age.py` remains a cluster-side deliverable; Row-C UI consumer remains a page task tracked by the age-surface SPEC §3. Archived 2026-05-20 with per-slice status. | `shared/busco_4d_age.js` (12 exports incl. `BUSCO_4D_MUS` + `computeAllThreeAges` + `buildBuscoAgeBracketsBlock` + `validateBuscoAgeBracketsBlock` + `verifyAgeMatchesDxy` + 2 formatters) + `tests/test_shared_busco_4d_age.js`; cited from the age-surface SPEC pair |
| `SPEC_busco_anchors_v1.md` | BUSCO single-copy cross-species anchors: schema validator, per-species indexing, homology-pair derivation, window count / density / depletion, synteny score, architecture-class auto-suggest. Page-16 ribbon-plot ticks + Page-14 architecture-class auto-suggest integrations remain deferred page tasks. Archived 2026-05-20 with per-slice status. | `shared/busco_anchors.js` (8 functions + 5 constants incl. `BUSCO_ARCHITECTURE_CLASSES` + `buscoCountInWindow` / `buscoDensityInWindow` / `buscoDepletionVsFlank` + `buscoSyntenyScore` + `suggestArchitectureClass`) + `tests/test_shared_busco_anchors.js` |
| `SPEC_mendelian_inheritance_para_vs_peri_v1.md` | Stage-1 per-family Mendelian goodness-of-fit + Stage-2 cohort 2×2 contingency comparing paracentric vs pericentric segregation distortion frequency. Generic family math in `mendelian_family_test.js`; type-aware contingency in `mendelian_para_vs_peri.js`. All v1 slices ship with page-side consumers. Archived 2026-05-20 — no deferred slices. | `shared/mendelian_family_test.js` (vocabulary + cross expectations + χ² + reliability tier + effect direction + `testFamilyCandidate`) + `shared/mendelian_para_vs_peri.js` (`cohortParaPeriContingency` + `cohortEffectDirectionBreakdown`) + `shared/mendelian_segregation.js` + 5 tests + 3 downstream consumers (`inversion_classification`, `inversion_classification_axes`, `recombination_suppression`) |
| `SPEC_fish_ancestry_scroller.md` | Ancestry-aware inversion browser page. F-based label-switching alignment (with Q-fallback restricted to flanks; FAIL=grey discipline), regime-aware smoothing, per-fish ancestry bricks with metric labels (RARE_ANCESTRY / HIGH_HET / REGIME_DISCORDANT — NOT a discovery system). Page + 4 submodules + 2 shared modules + 4 tests + manifest registration all ship. Cluster-side `instant_q` (Engine B) producer remains the only deferred slice. Archived 2026-05-20. | `pages/review/fish_ancestry_scroller.{html,js}` + 4-module subdir + `shared/ancestry_alignment.js` (10 exports) + `shared/ancestry_bricks.js` (6+ exports) + manifest.json + pages.registry.json + 4 tests |
| `SPEC_functional_burden_per_candidate_v1.md` | Per-candidate functional / deleterious-mutation burden compute: per-sample aggregation within candidate span, per-karyotype-group summarisation, pairwise Wilcoxon across STD/STD / HET / INV/INV, per-metric verdict classifier, composite tag, homokaryotype-vs-all comparison + subsample control, end-to-end `summarizeCandidateFunctionalBurden()` entry point. Module's own version constant matches the SPEC name. Per-candidate overlay-panel UI + cluster-side producer JSON schema deferred. Archived 2026-05-20. | `shared/functional_burden.js` (15 exports incl. version stamp `functional_burden_per_candidate_v1.0`) + `shared/wilcoxon.js` + `shared/sigma_profile.js` + `shared/inheritance_compute.js` + 3 tests + downstream `stats_profile.js` (7 `derive_from:` references) |
| `SPEC_page1_candidate_mode_ui.md` | Parallel Candidate Registry (turn 88 contract): mode enum (`default` / `detailed`), localStorage persistence, active-candidate state slots, list + map accessors, detailed-state clear helper. MGL-side per-candidate cache infrastructure (PCA + heatmap + BEAGLE result registration with cache keys). 6 page-side consumers in local_pca_dosage. Detailed-mode UI + HANDOFF-1 cluster producer (16 PCA + 4 heatmap JSONs per candidate) deferred. Archived 2026-05-20. | `shared/candidate_mode.js` (9 exports) + `shared/mgl_candidate_mode.js` (9 exports) + 6 page-side consumers in `local_pca_dosage/` + 3 tests |
| `SPEC_xpehh_per_window_track.md` | XP-EHH per-window selection-scan track. Atlas-side: `xpehh_per_window_v1` schema + validator + state I/O + per-chrom / range / point query helpers + outlier selection (Z or percentile) + track-header summary + cross-track alignment check. Downstream consumer: `inversion_classification_axes.js` defines the XPEHH_SELECTION_SIGNAL axis using `xpehhValuesInRange()`. Page-8 popstats / ancestry track UI + cluster-side producer deferred. Archived 2026-05-20. | `shared/xpehh_per_window.js` (15 exports) + `tests/test_shared_xpehh_per_window.js` + downstream `inversion_classification_axes.js` (XPEHH_SELECTION_SIGNAL axis) |
| `SPEC_registry_write_and_page_isolation.md` | Companion SPEC to `SPEC_registry_v2.md` (already in `specs_done/`). Cartridge-side page-isolation discipline: pages may not import from each other. Audit-confirmed 2026-05-20 by `grep -rEn "from '[\./]*pages/" atlases/inversion/pages/` → empty. Registry.write half defers entirely to `SPEC_registry_v2.md`. The SPEC is companion-not-parallel — no deferred work specific to this file. Archived 2026-05-20. | Commit `4e695f7` enforces zero cross-page imports (re-grep clean as of 2026-05-20); Registry.write contract → `specs_done/SPEC_registry_v2.md`; cartridge config → `registries/data/*.registry.json` (writable-layer flag) |
| `SPEC_local_pca_comparator.md` | Cross-evidence comparator: 3-PCA side-by-side (z-blocks / θπ / GHSL) + per-sample trajectory + concordance score. Phases 1+2 shipped per SPEC's own status line; Phase 3 (Procrustes overlay) deferred-by-design via SPEC's own gate ("only if a real use case AFTER Phase 1+2") + rotation-misreading risk. Archived 2026-05-20. | `pages/discovery/pca_comparator.{html,js}` + `pca_comparator/{_state,renderer,heatmap}.js` + `renderer.js#paintTrajectory` (line 527) + `renderer.js#computeConcordance` (line 630) + `tests/test_discovery_pca_comparator.js` + page contract docs |
| `SPEC_cross_atlas_group_transfer.md` | Phase 1 selection-mode primitives (`U` key + Shift+drag → `state.selectionGroup`) shipping with 4 page-side consumers. Phase 2 (CTRL lateral bar + cross-atlas transfer) deferred-by-design — gated on the atlas-family infrastructure that doesn't exist yet (per `docs/ATLAS_FAMILY_ROADMAP.md`). Archived 2026-05-20 with explicit Phase 2 dependency tracking. | `state.selectionGroup` slot + 4 page consumers in `local_pca_dosage.js` + `g_panel.js` + `pca_panel.js` + `sidebar.js`; G-panel integration via the already-archived `SPEC_g_panel_unified_groups` |
| `SPEC_macrostripe_microgroup_hierarchy.md` | Three-level label scheme (microgroup_id / macrostripe_id / regime_block_id) shipping as first-class state vocabulary. `shared/macrostripe.js` (4 exports — runtime + color + cache) + `shared/lineage_clustering.js` (5 exports + 4 constants — the SPEC's Steps A-F algorithm) + `shared/karyotype_lineage.js` (persistence). 7 page-side consumers. 4 tests. Co-travel badge polish + cohort-wide TSV export (via `SPEC_haplotype_burden_coloring` Phase 2) remain follow-ups. Archived 2026-05-20. | `shared/macrostripe.js` + `shared/lineage_clustering.js` + `shared/karyotype_lineage.js` + 7 consumers across `local_pca_dosage/` and `candidate_focus.js` + 4 tests (`test_shared_macrostripe.js`, `test_shared_lineage_clustering.js`, `test_shared_karyotype_lineage.js`, `test_page1_lineage.js`) |
| `SPEC_cramers_v_seed_merge.md` | Two-mode Cramér's V seed-merge auto-promote alternative to L2-sweep. `shared/cramers_v_merge.js` ships 5 exports including both SPEC-named entry points (`runCramersVMergeLocal` for `insulated_local` mode + `runCramersVMergeMacrostripe` for `post_long_range` mode) and the chain-construction helper. Side-by-side comparison view shipping in `haplotype_regimes.{html,js}`. Dedicated unit test deferred. Archived 2026-05-20. | `shared/cramers_v_merge.js` (5 exports: `computeAdjacentSeedMerges`, `chainsFromMergeVerdicts`, `runCramersVMergeLocal`, `runCramersVMergeMacrostripe`, `CRAMERS_V_MERGE_DEFAULTS`) + consumers in `pages/discovery/haplotype_regimes.{html,js}` |
| `SPEC_haplotype_burden_coloring.md` | Schema-in / color-out pattern for attaching per-sample or per-group burden data to macrostripe/microgroup labels. Phase 1 deliverable #3 (per-sample group-label TSV export with `microgroup_id` + `macrostripe_id` columns) shipped 2026-05-20 with explicit dated inline citation in `candidate_focus.js` line 367 + `_html_builders.js` line 157. Phase 2 (per-candidate burden-join TSV + cohort-wide group export) + Phase 3 deliverables deferred per SPEC's own staging. Archived 2026-05-20 with per-phase status. | `pages/discovery/candidate_focus.js` line 367 (Phase 1 deliverable #3 inline cite) + `candidate_focus/_html_builders.js` line 157 (matching HTML scaffold) + companion `shared/macrostripe.js` (label source, from the already-archived `SPEC_macrostripe_microgroup_hierarchy.md`) |
| `SPEC_copy_origin_painting.md` | Paralogue-ancestry painting for SD-breakpoint mechanism inference. Steps D + E ship as pure-JS primitives: `classifyBreakpointMechanism` (NAHR / TE-mediated / NHEJ/MMEJ / complex / replication-based / no-mosaic) + `partitionPaintingByArrangement` + `interpretCopyOriginPattern`. Steps A–C (paralogue copy discovery, PSV calling, per-window paint) remain data-bound on the PSV pipeline. Step F (`05_breakpoint_switches.tsv` writer) is producer-side. Archived 2026-05-21 with per-step status matrix. | `shared/copy_origin_painting.js` (421 lines, six-label `COPY_ORIGIN_MECHANISMS` vocab matching SPEC wording rules verbatim) + `tests/test_shared_copy_origin_painting.js` (250-line suite) + downstream consumer `shared/inversion_classification.js` (`origin_mechanism` + `copy_origin_verdict` fields) |
| `SPEC_regime_annotation_v34.md` | Annotation layer (Stage 5.5) sitting between haplotype-regime discovery and dosage overlay. Layers 1 (positional: centromeric / pericentromeric / arm-interstitial / subtelomeric / arm-scale) and 2 (structure: band count + sharpness + nesting + M-regime kind) ship as pure-JS annotators. Layers 2b (mechanism skeleton), 3 (POD-aware), and 4 (underdominance-aware) remain data-bound on per-regime fitness/load/variant evidence the catfish 226-sample cohort doesn't yet expose. Wording rule "compatible not confirmed" preserved in shipped vocab. Archived 2026-05-21 with per-layer status matrix. | `shared/regime_annotation/{index,positional,structure}.js` (391 lines total) + `tests/test_shared_regime_annotation.js` (272-line suite) + consumers `pages/discovery/haplotype_regimes.js` + `shared/inversion_classification.js` |

### Pending — `specs_todo/`

See `specs_todo/README.md` for the per-SPEC status table.
Highlights:
- 1 SPEC ONLY (confirmed unimplemented; depends on cluster-side primitives that don't exist): `SPEC_msmc_per_founder_background.md` — 2026-05-21 audit documented in-SPEC with a 5-step blocker matrix; recommended sequencing (Step 1 regime-sharing matrix first as standalone deliverable)
- 1 AMENDMENT to a parent at `specs_done/`: `SPEC_inversion_age_atlas_surface_AMENDMENT.md` (most prescribed slices still deferred per the parent SPEC's §3 status matrix)
- 1 superseded: `SPEC_registry_v1.md` (superseded by `specs_done/SPEC_registry_v2.md`; kept for historical reference)
- 1 sub-library: `mgl_adapter/` (self-contained spec sub-tree; moves between todo/done as a unit)
- **Audit-sweep 2026-05-20 + 2026-05-21 archived 16 SPECs total**:
  - 2026-05-20 morning (4): `SPEC_arrangement_color_mode_and_arrangement_calls_v1`, `SPEC_busco_4d_age_brackets`, `SPEC_busco_anchors_v1`, `SPEC_mendelian_inheritance_para_vs_peri_v1`
  - 2026-05-20 afternoon 1 (5): `SPEC_fish_ancestry_scroller`, `SPEC_functional_burden_per_candidate_v1`, `SPEC_page1_candidate_mode_ui`, `SPEC_xpehh_per_window_track`, `SPEC_registry_write_and_page_isolation`
  - 2026-05-20 afternoon 2 (5): `SPEC_local_pca_comparator`, `SPEC_cross_atlas_group_transfer`, `SPEC_macrostripe_microgroup_hierarchy`, `SPEC_cramers_v_seed_merge`, `SPEC_haplotype_burden_coloring`
  - 2026-05-21 final (2): `SPEC_copy_origin_painting` (Steps D+E shipped; A–C data-bound), `SPEC_regime_annotation_v34` (Layers 1+2 shipped; 2b/3/4 data-bound)
  - Per-slice status matrices in each archived SPEC track follow-up work. Bodies preserved verbatim ("don't delete the SPEC, archive it" rule).

### Sub-library — `specs_todo/mgl_adapter/`

- `SPEC_0_master.md` — the master MGL adapter spec
- `README.md`, `README_specs.md` — entry points
- 10 numbered HANDOFFs (1, 2, 3, 4, 5, 6, 7, 8, 9, 10) — completed 2026-05-15 from the `mgl_adapter_v22_dragdrop_fixed` bundle
- The same 5 page-keyed HANDOFFs are duplicated at `specs_todo/pages_{candidate_mode,custom_views,fingerprint_track,similarity_panel,tree_panel}/_to_do/HANDOFF_*.md` (these duplicates are byte-identical to the canonical mgl_adapter copies)

This sub-tree is treated as a single self-contained library — moves
between `specs_todo/` and `specs_done/` would happen as a unit, not
file-by-file.

### Bundle museum — `specs_done/_bundles/`

Verbatim drop-bundle snapshots that preserve **bundle-level meta-docs**
(pipeline diagrams, audit checklists, drag-drop instructions). The
individual SPECs from these bundles were imported into the canonical
locations above; the bundle READMEs / HANDOFFs were not, and would
otherwise be lost. See `specs_done/_bundles/README.md` for the
per-bundle inventory.

Current contents:
- `inversion_atlas_v3.4_DROP/` — 2026-05-08 v3.4 banding-pipeline drop (README + HANDOFF only; code already shipped to `shared/band_tracking/`)
- `banding_unified_v3.4_AUDIT_BUNDLE/` — 2026-05-08 audit-revision of same (README + HANDOFF + SERVER_README)
- `mgl_adapter_v22_dragdrop_fixed/` — full extracted tree (mgl_adapter v22 multi-repo drop)
- `HOW_TO_USE_haplotype_regimes.md` — user guide for page22 (only end-user docs for any page right now)

## SPECs **referenced in shipping code but missing from disk**

**RESOLVED 2026-05-20.** Detail at `_handoff_docs/SPECS_AUDIT.md` (§"STATUS UPDATE 2026-05-20"). Summary:
- The 8 SPECs missing as of the original audit (2026-05-15) were authored from shipped code → `specs_done/SPEC_<name>.md`. See `SPECS_AUDIT.md` for the full status table.
- The 9th — `SPEC_inversion_age_atlas_surface.md` (turn-117 parent of the `_AMENDMENT`) — was authored 2026-05-20 from `shared/mgl_inversion_divergence.js` + `busco_4d_age.js` + `age_model_suggester.js` + `pages/evolution/age_divergence.{html,js}` → `specs_done/SPEC_inversion_age_atlas_surface.md`.
- `SPEC_DEFERRED.md` is **retired** as a target — it was a register of deferred decisions, now expressed inline via per-slice `Status: deferred` annotations on the individual SPECs (see e.g. `SPEC_inversion_age_atlas_surface.md` §3).
- `HANDOFF_BATCH_3.md` / `HANDOFF_BATCH_5.md` references are **retired by design** — phantom handoffs that were never authored; the citations are corrective notes flagging mislabels (canonical record is the on-disk `pages/<stage>/BATCH_*_NOTES.md` files).

## Working-doc folders (NOT specs — handoffs, audits, plans)

| folder | purpose |
|--------|---------|
| `_handoff_docs/` | newer turn-by-turn handoffs + audits + plans (chat 34/35/36/2026-05-12..14) |
| `handoff_docs/` | older Atlas_round166-era handoffs (pre-import) |
| `docs/` | migration tracking + family roadmap + TODO inventories |
| `atlases/inversion/*/README.md` | per-subsystem READMEs (10 of them: analysis/, data/, engines/, etc.) |

These are deliberately distinct from the SPEC folders. A SPEC is a
*design contract*; a handoff is a *narrative of a session*. Don't
collapse them — but do make sure each handoff that introduces a new
SPEC files the SPEC under `specs_todo/`.

## Building the manual from this material

Eventually we'll write a user-facing manual. The plan:

1. **Source of truth = `specs_done/`** + per-page `_doc` fields in
   `atlases/inversion/registries/data/pages.registry.json`
2. **Page chapter** = `ATLAS_PAGES_MAP.md` (per-page narrative)
3. **Layer chapter** = the 26 schemas in `atlases/inversion/registries/schemas/` + a prose `SCHEMA.md` to be written
4. **Pipeline chapter** = stage-by-stage walkthrough from the SPECs in `specs_done/` (band-tracking SPEC has the v3.4 pipeline diagram; we should also recover the `inversion_atlas_v3.4_DROP` README which had the full diagram — currently not in the repo)

When the manual gets written, it cites SPECs by their canonical path
(`specs_done/SPEC_*.md`) — so don't rename or move them after that.
