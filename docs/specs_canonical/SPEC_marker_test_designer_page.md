# SPEC — relatedness-atlas `marker_test_designer` page

**Status**: scaffold. Independent. Cross-references the future
`marker_design` atlas (registered as a stub in atlases.jsonl with
`status: "stub"`, `depends_on_atlases: ["inversion_atlas", "meiosis_atlas"]`).

**Scaffolded in:** [`atlases/relatedness/pages/hub/marker_test_designer/`](../atlases/relatedness/pages/hub/marker_test_designer/) (separate sub-directory pattern; main entry `marker_test_designer.html` + `.js`).

---

## 1. Goal

Per the manifest tooltip: "Interchromosomal Marker Test Designer —
converts a candidate interchromosomal meiosis effect into a practical
marker panel: focal inversion classifier markers in parents +
transmission/recombination markers on tested chromosomes for offspring
panels (CO/DCO/coincidence)."

Bridges the WGS-based discovery side (this atlas + meiosis-atlas) to
the high-throughput marker-assay side. Given a manuscript-grade signal
("focal inversion X causes interchromosomal effect on chrom Y"), this
page designs the minimal assay that confirms the effect at 10k-50k-fish
scale.

## 2. The design problem

Inputs (per focal-inversion × tested-chrom pair):

- The focal inversion's structural span — to design classifier markers
  for parents (n = ~3-6 SNPs spanning the inversion)
- The tested chromosome — to design recombination markers spaced along
  its length (n = ~10-30 SNPs depending on chrom length)
- Existing marker density in the cohort's WGS data — to know what's
  available without re-genotyping

Outputs:

- A panel JSON: `{ focal_inv_markers: [...], tested_chrom_markers: [...], assay_n_markers, estimated_cost }`
- Per-marker design details: position, alleles, expected MAF, primer
  candidates (from a flanking-sequence lookup against the reference)
- A simulation: given the panel, how many offspring per dyad are needed
  to confirm the effect at α = 0.05 with power 0.8?

## 3. Data dependencies

- `inversion_candidates.v1` — focal inversion structure
- `inversion_meiosis_effects.v1` — effect magnitude (drives the
  required-N calculation); missing builder
- `chromosome_meiosis_events.v1` — expected CO rate on tested chrom
  (drives marker spacing); missing builder
- a marker-density layer (TBD; not yet registered) — existing WGS SNPs
  per Mb
- reference FASTA segments — for primer design (out of scope on the
  atlas side; this page emits regions, an external tool designs primers)

## 4. Surface

```
#mtdFocalInv         — focal inversion picker
#mtdTestedChrom      — tested chromosome picker (defaults from interchromosomal page result)
#mtdEffectInput      — manual override: enter expected effect magnitude (or auto-fill from inversion_meiosis_effects.v1)
#mtdAssayBudget      — number input: max markers in the panel (cost constraint)
#mtdDesignBtn        — compute optimal panel
#mtdPanelResult      — table: per-marker rows (position, allele, MAF, role)
#mtdPowerCurve       — power vs N-offspring-per-dyad chart for the designed panel
#mtdExportBtn        — JSON download of the panel + power simulation
#mtdDataSource       — multi-envelope status badge
```

## 5. Algorithm (sketch)

```
def design_panel(focal_inv, tested_chrom, expected_effect, budget):
    # 1. Pick focal markers — uniformly distributed across the inversion
    focal_markers = pick_uniform(focal_inv.start, focal_inv.end,
                                 n = min(budget * 0.3, 6),
                                 maf_min = 0.20,
                                 from = wgs_markers_in_inv)
    # 2. Pick tested-chrom markers — biased to high-CO regions
    co_density = density(crossover_envelope.tracts, tested_chrom, win=1Mb)
    tested_markers = pick_weighted(tested_chrom.length, co_density,
                                   n = budget - len(focal_markers),
                                   maf_min = 0.20,
                                   spacing_min = 5Mb)
    # 3. Simulate power
    power = simulate_power(focal_markers, tested_markers, expected_effect, n_offspring_range=[10, 200])
    return { focal_markers, tested_markers, power_curve: power }
```

The simulation is the slow part; in-browser feasible at budget ≤ 30
markers, otherwise needs a server endpoint.

## 6. Cross-atlas concern

The `marker_design` atlas is registered as a stub (atlas-core's
toolkit_registries/atlases.jsonl) — eventually this page should migrate
there. Until that atlas exists with actual scaffolding, the relatedness
atlas hosts it as a relatedness-adjacent convenience.

When `marker_design` atlas is built:
- Move this page to `marker-atlas/atlases/marker_design/pages/hub/test_designer.html`
- Replace this SPEC with a `Migrated to:` block pointing at the new home
- Add a redirect from `#/relatedness/marker_test_designer` to the new
  hash

Timing: blocked on the `marker_design` atlas being scaffolded (no
schedule yet).

## 7. Promotion criteria

- [ ] All input envelopes probed; status-badge per source
- [ ] Picking algorithms implemented (focal: uniform-MAF-filtered;
      tested: CO-density-weighted)
- [ ] Power simulation in-browser for budget ≤ 30
- [ ] JSON export contains everything the downstream primer-design
      tool needs
- [ ] Smoke test against a fixture
- [ ] Move SPEC to `specs_done/`

## 8. Open work

- **Primer-design hand-off** — currently emits regions; an external tool
  (Primer3 etc.) does primer design. Eventually integrate via a server
  endpoint that wraps Primer3.
- **Cost model** — the budget field is just a marker count today; should
  encode per-marker assay cost (which differs by chemistry — TaqMan
  vs MIP vs amplicon-seq).
- **Multi-focal panels** — design a single panel that tests N focal
  inversions simultaneously. Combinatorial; needs the optimisation step
  flagged in [`inversion_priority` §8](SPEC_inversion_priority_page.md).
- **Validation feedback loop** — once a Pass-2 run produces results,
  the panel design can be evaluated retrospectively (did it have power
  for the observed effect?). Out of scope for round 1.
