# SPEC — meiosis-atlas hub pages + missing builders

**Status**: pages scaffolded (mount/unmount lifecycle only); compute paths
pending real-data pipeline + 3 missing product builders. Not implemented
in the sense that no page renders real data yet.

**Scaffolded in:** [`atlases/meiosis/pages/hub/`](../atlases/meiosis/pages/hub/)
(5 pages, see §1 below).

**Wired in:**
[`atlases/meiosis/manifest.json`](../atlases/meiosis/manifest.json) +
[`atlases/meiosis/registries/data/pages.registry.json`](../atlases/meiosis/registries/data/pages.registry.json).

---

## 1. The 5 pages

Per `atlas-core/toolkit_registries/relatedness/01_registry/atlases.jsonl`, the
meiosis_atlas lead question is `inversion_effect_on_meiosis_per_chromosome`.
The 5 hub pages cover that lead + the interchromosomal stress-test question.

| page id                    | scope                                      | folds in products |
|----------------------------|--------------------------------------------|-------------------|
| `nco`                      | NCO + MOSAIC_SHORT + MOSAIC_LONG cohort view | `gene_conversion_tracts.v1` ✓ (adapter shipped) |
| `crossovers`               | CO + DCO cohort view, per-chrom × karyotype | `chromosome_meiosis_events.v1` (partial), intrachromosomal slice of `inversion_meiosis_effects.v1` |
| `interchromosomal`         | HEADLINE: focal inversion → meiosis on OTHER chroms | `coincidence_matrix.v1` ✗, `local_inv_controls.v1` ✗, `family_aware_permutation_design.v1` ✗, interchromosomal slice of `inversion_meiosis_effects.v1` |
| `crossovers_per_candidate` | per-inversion-candidate CO ideogram + telomere bias + PRDM9 logo | reads `crossover_track` + optional `prdm9_motif` layers (CONTRACT-ONLY stubs) |
| `nco_per_candidate`        | per-inversion-candidate NCO/GC tract ideogram + telomere bias | reads `nco_gc_track` layer (CONTRACT-ONLY stub) |

Migration history: `crossovers_per_candidate` and `nco_per_candidate`
moved from genome-atlas/pages/annotation/page11+page12 on 2026-05-19
because per-candidate CO/NCO views are meiosis content, not
genome-assembly content. The cross-atlas read is genome-atlas page3
(chromosome overview) — its CO-density sub-track reads
meiosis-atlas's `crossover_track` layer.

## 2. What each page needs

### 2.1 `nco` — **SHIPPED 2026-05-20**

Promoted to [`specs_done/SPEC_nco_page.md`](../specs_done/SPEC_nco_page.md).

Summary: `mount()` probes for `tract_classifications_v1`, fail-soft;
status badge always renders (3 states: ok / empty / warn); 4 views
(per-dyad, length histogram, per-chrom, in-vs-out crosstab) with
MOSAIC_SHORT × yes highlighted as the headline signal; TSV export of the
filtered tracts.

### 2.2 `crossovers`

Reads `chromosome_meiosis_events.v1` (14/29 chroms covered today per registry).

Needs a sibling adapter pair (`import_chromosome_meiosis_events` +
`normalize_chromosome_meiosis_events`) following the same pattern as
tract_classifications. Schema columns per §1 of this atlas's product entry
in `products.jsonl`: per-chromosome × per-dyad CO/DCO/NCO counts.

Also reads the intrachromosomal slice of `inversion_meiosis_effects.v1` for
the karyotype-stratified rate view (does het-inversion suppress local CO on
its own chromosome?).

### 2.3 `interchromosomal` (HEADLINE)

Blocked by **3 missing builders**:

- **`coincidence_matrix.v1`** — C = observed DCO / expected DCO per interval pair. Registry note: "missing — builder needed". The builder should: enumerate all (interval, interval) pairs (intra + inter chrom); compute observed DCO from `chromosome_meiosis_events.v1`; compute expected DCO from product of marginal CO rates; emit C per pair. Grain: `interval_pair`.
- **`local_inv_controls.v1`** — per (tested_chr × local_inv) covariate list. Registry note: "missing — needs a register-local-inversions step". Reads `inversion_candidates.v1`, filters to inversions on each tested chromosome by frequency / status, emits a covariate matrix.
- **`family_aware_permutation_design.v1`** — permutation scheme respecting family structure. Registry note: "missing — needs a design generator". Reads `family_hubs.v1` + `parent_offspring_edges.v1`, emits a JSON of permutation blocks (one block per family).

Implementation order: `local_inv_controls` first (it's the simplest — just filter inversion_candidates), then `coincidence_matrix` (needs the events product to land), then `family_aware_permutation_design` (it's a design step that depends on the relatedness atlas's family_hubs).

Each builder follows the same scaffold as the tract_classifications adapter:
runner + extractor + 2 schemas + registry entries. Estimated cost: 1-2 hours
per builder once the input product is producing real data.

### 2.4 `crossovers_per_candidate` and `nco_per_candidate`

Both pages mount cleanly today; their renderers are explicit no-ops until
Phase C wires the data fetch. The optional-card pattern (
`_maybeHideOptionalCards()` for the PRDM9 logo) is fail-soft —
`layers.prdm9_motif?.pwm?.length > 0` guards the card display.

Needed:
- Layer `crossover_track` populated for each candidate (`data/crossovers/<candidate_id>.json`)
- Layer `nco_gc_track` populated for each candidate (`data/nco_gc/<candidate_id>.json`)
- Optional layer `prdm9_motif` (per-candidate PWM)

Layer registry stubs are CONTRACT-ONLY today (see
[layers.registry.json](../atlases/meiosis/registries/data/layers.registry.json)
_round1_status); replace with real `auto_index` + `path` once a producer
emits the JSON.

## 3. Dependencies on other atlases

Per `atlases.jsonl`, meiosis_atlas depends on:
- **relatedness_atlas** — `parent_offspring_edges.v1`, `family_hubs.v1`, `pedigree_dyads.v1`
- **inversion_atlas** — `inversion_candidates.v1`, `inversion_karyotypes.v1`, `long_range_haplotype_regimes.v1`

Cross-atlas reads happen via the AtlasRouter's shared `state.shared.candidate` slot and the workspace-wide envelope inventory (`GET /api/layers`). No special wiring needed; pages just call the same `resolveLatestLayer()` helper regardless of which atlas produced the envelope.

## 4. Promotion criteria

A page moves from "scaffold" to "shipped" when:

1. `mount()` calls `resolveLatestLayer()` for its primary product.
2. At least one view renders real data (not the "Empty stub" placeholder).
3. A smoke test exists (following the pattern in
   `inversion-atlas/atlases/inversion/pages/.../test_*.js`) that mocks
   fetch and asserts the page renders against an envelope payload.
4. The corresponding section in this SPEC moves to `specs_done/`.

The 5 pages can promote independently. Recommended order: `nco` first (adapter is ready), then `crossovers_per_candidate` (genome-atlas migration is the immediate motivation), then `crossovers`, then `interchromosomal` (needs the 3 missing builders).
