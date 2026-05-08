# Atlas family roadmap

This document explains the **biology-driven order** in which atlas
packages are expected to ship, why inversion-atlas is being built
first despite being last in the analytical pipeline, and how the
registry handles incremental growth.

Read this AFTER `README_PAIRING.md` and BEFORE designing a new
atlas package.

---

## 1. The breeding-program order

In a standard aquaculture genomics breeding program, the analytical
pipeline runs in this order:

```
   genome           population         diversity         inversion
   ──────           ──────────         ─────────         ─────────
   reference        cohort             θπ, F_ROH         karyotyping
   assembly         structure          relatedness       Mendelian
   annotation       admixture          ancestry          marker assays
   synteny          PCA / NGSadmix     ROH               selection
                    NAToRA pruning     het rate
```

Each step depends on the previous:

- **Population structure** assumes a reference genome exists
  (where to map reads) and an annotation (what regions to skip).
- **Diversity metrics** (θπ, F_ROH, ROH intervals) need population
  groups defined first, otherwise pooling samples mixes broodlines
  and corrupts the estimates.
- **Inversion detection** needs the diversity baseline to know what
  background variation looks like, the population groupings to
  control for family structure, and the reference to compute
  positions on.

So in production, you build the four atlases in order: genome →
population → diversity → inversion.

## 2. Why this project is doing it backwards

This project is building **inversion-atlas first** because the
upstream outputs already exist as files on disk, produced by ad-hoc
pipelines on the LANTA HPC cluster:

- `data/cohort/sample_groups.tsv` — population groups (NGSadmix K=8,
  NAToRA-pruned set of 81 unrelated samples)
- `data/cohort/cohort_diversity_v1.json` — diversity baseline
- `data/cohort/sample_froh.json` — F_ROH per sample
- `data/cohort/relatedness.json` — KING/Manichaikul relatedness
- `data/precomp/<chrom>.json` — per-chromosome scrubber data
  including local PCA on dosage
- `data/comparative/synteny_multispecies_v1.json` — synteny across
  9–11 catfish genomes

All of these are inputs to inversion analysis but conceptually
**belong to atlases that don't exist yet**. The inversion atlas
declares them in its `layers.registry.json` because someone has to,
and inversion is the only atlas being built right now.

## 3. The succession model

When the population, diversity, and genome atlases eventually land,
the cohort and comparative layers should move to them — without
breaking inversion, without a migration step, without code changes.

The registry supports this through three meta-schema fields:

- `provisional: true` — the declaring atlas knows this layer
  semantically belongs elsewhere
- `owned_by: <atlas_id>` — names the future owner
- `schema_status: "pending"` — the schema may not exist yet,
  validate as `any` until it lands

When a new atlas registers a layer that already exists:

| Incumbent state | Result |
|---|---|
| Identical config | silent merge (idempotent) |
| `provisional: true` | NEW atlas wins, log "succession" |
| `owned_by: <new_atlas_id>` | NEW atlas wins, log "ownership transfer" |
| Neither marker | throw at register_atlas time |

So when population-atlas eventually declares `cohort_relatedness`,
the registry sees inversion-atlas's incumbent has
`owned_by: "population"` and silently transfers ownership. Inversion's
pages keep working because the layer key is the same; only the
declaring atlas changed.

## 4. What inversion-atlas owns vs. squats on

### Owned by inversion-atlas (permanent)

These are inversion-specific and will stay in inversion-atlas
forever:

- All `scrubber_main` and per-chromosome layers (the local-PCA
  output is inversion-specific even though the chromosome scope
  is not)
- All band_tracking layers (`band_nodes`, `band_edges`,
  `transition_events`, `band_trajectories`, etc.) — pure inversion
  detection
- All `candidate_*` layers — inversions ARE the candidates
- `arrangement_calls` — inversion-specific
- `te_fragility` — TE-driven inversion formation (not generic
  comparative)
- All operations (FST, θπ, dxy, coverage, BEAGLE) — inversion-
  specific compute calls
- All analysis modules (mendelian, karyotype assignment, etc.)

### Squatting (provisional, will transfer)

These are declared in inversion-atlas today but `owned_by` somewhere
else:

| Layer | Will move to | Reason |
|---|---|---|
| `cohort_relatedness` | population | Cohort-level fact, not inversion-specific |
| `cohort_sample_manifest` | population | ditto |
| `cohort_sample_groups` | population | ditto |
| `cohort_natora_pruned` | population | ditto |
| `cohort_diversity` | diversity | Diversity baseline, not inversion-specific |
| `cohort_sample_froh` | diversity | F_ROH is a diversity metric |
| `cs_breakpoints` | genome | Synteny breakpoints are genome-level |
| `synteny_multispecies` | genome | ditto |
| `phylo_tree` | genome | ditto |

When the future atlases land, none of inversion's pages need to
change. The succession rule handles the hand-off declaratively.

## 5. Why we're not waiting

The temptation: "wait until population/diversity/genome atlases
exist, then build inversion correctly."

The reason we're not: the manuscript (v19→v20, Nature Communications
target) needs the inversion atlas working NOW. The upstream files
already exist on disk. Building three atlases that nobody is
currently using would be over-engineering.

The compromise: build inversion-atlas correctly, mark its squatted
layers as provisional, document the succession path. If the other
atlases never get built, inversion still works. If they do, the
hand-off is clean.

## 6. Incremental schema growth

Most of the layer entries today reference `schemas/<thing>.schema.json`
files that are placeholders — they validate as `type: object` and
accept anything. The schemas will be tightened layer-by-layer as
the data shapes stabilize.

The convention:

- `schema_status: "validated"` — schema exists and is enforced
- `schema_status: "pending"` — placeholder, accepts any object
- `schema_status: "any"` — explicitly skip validation

The registry refuses to load layers without a schema field at all
(this would be ambiguous: did the author forget, or do they not
care?). But pending schemas are first-class: the contract intent
is captured, and the validator just doesn't enforce it yet.

This lets analysis modules be wired up before their result schemas
are formalized, which is exactly the order we want for incremental
work.

## 7. The four atlases (when they all exist)

```
genome-atlas/
└── atlases/genome/
    ├── manifest.json
    ├── pages/
    │   ├── overview/         (chromosome map, gene density)
    │   ├── synteny/          (multi-species)
    │   ├── annotation/       (gene tracks)
    │   └── repeats/          (TE landscape)
    ├── analysis/
    │   ├── busco_completeness.js
    │   └── synteny_breakpoint_finder.js
    ├── registries/data/      (declares: gene_track, repeat_density,
    │                                     synteny_*, phylo_tree, cs_breakpoints)
    └── data/

population-atlas/
└── atlases/population/
    ├── manifest.json
    ├── pages/
    │   ├── pca/
    │   ├── admixture/
    │   ├── relatedness/
    │   └── pruning/
    ├── analysis/
    │   ├── ngsadmix_k_selector.js
    │   ├── natora_pruner.js
    │   └── relatedness_classifier.js
    ├── registries/data/      (declares: cohort_relatedness, cohort_sample_*,
    │                                     ngsadmix_q, pca_coords, natora_*)
    └── data/

diversity-atlas/
└── atlases/diversity/
    ├── manifest.json
    ├── pages/
    │   ├── theta_pi/
    │   ├── roh/
    │   ├── ancestry/
    │   └── het_rate/
    ├── analysis/
    │   ├── theta_pi_per_window.js
    │   ├── roh_caller.js
    │   └── ancestry_q_decomposer.js
    ├── registries/data/      (declares: cohort_diversity, cohort_sample_froh,
    │                                     roh_intervals, theta_pi_*, ancestry_*)
    └── data/

inversion-atlas/             ← what we're building now
└── atlases/inversion/
    ├── manifest.json
    ├── pages/                (23 pages: discovery, review, catalogue, comparative)
    ├── analysis/             (mendelian.js, karyotype_assignment.js, ...)
    ├── registries/data/      (declares: scrubber_*, band_*, candidate_*,
    │                                     fst_*, theta_pi_by_invgt, arrangement_calls;
    │                                     SQUATTING: cohort_*, synteny_*, phylo_*)
    └── data/
```

## 8. The composable workspace

In a fully-built deployment, the assembly step combines all four:

```bash
rsync -av atlas-core/             atlas-workspace/
rsync -av genome-atlas/atlases/   atlas-workspace/atlases/
rsync -av population-atlas/atlases/ atlas-workspace/atlases/
rsync -av diversity-atlas/atlases/  atlas-workspace/atlases/
rsync -av inversion-atlas/atlases/  atlas-workspace/atlases/
```

Boot order at startup:

1. core discovers all four atlases.
2. core registers genome-atlas first (alphabetical, no dependencies).
3. core registers population-atlas — its layers may collide with
   inversion's squats, but inversion isn't loaded yet so no conflict.
4. core registers diversity-atlas.
5. core registers inversion-atlas LAST. When it tries to declare
   `cohort_relatedness`, the registry sees population already owns
   it and skips inversion's provisional declaration silently.
6. All four atlases' pages appear in the topbar; the user navigates
   freely.

Today, only step 5's declarations actually run. The output is the
same — inversion works — and tomorrow, when the other atlases land,
the existing inversion code requires zero changes.

## 9. The one-sentence rule

> Build for the future, but ship the present.

Every layer inversion declares today either belongs to inversion
permanently, or is marked `provisional` with `owned_by` pointing at
its eventual home. No layer is left in an undecided state. That's
how incremental growth stays clean.
