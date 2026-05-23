# CROSS_SPECIES_BREAKPOINTS_WORKFLOW — comparative breakpoint atlas

Status: **v0 (experimental)**. Source: tarball
`COMPARATIVE_BREAKPOINTS_MASTER_20260522` (Q. Andres, 2026-05-23).

> This is the THIRD experimental atlas (after inversion + relatedness +
> meiosis). It owns the comparative cohort (18 catfish genomes + hybrid
> subgenomes). It is **strictly coordinate-only**: it hands genome
> coordinates to the hatchery 226-cohort work; it never makes claims
> about hatchery samples.

---

## §1 The 4-atlas split

The original `inversion_atlas` was bloated — it owned candidate
detection AND popstats AND cross-species questions. As of PR #28 it is
split into four sibling atlases:

```
inversion_atlas       discovery + karyotyping + pair-relation (manuscript)
cross_species_atlas   comparative breakpoint detection, 18 species   ← NEW
popstats_atlas        FST / dxy / piN / piS between karyotype groups ← NEW
evolution_atlas       arrangement origin, selection, evolution     ← PROMOTED
```

`genome_synteny_atlas` is folded INTO `cross_species_atlas` and
deprecated. `meiosis_atlas`, `relatedness_atlas`, `marker_design`,
`atlas_core` are unchanged.

The four atlases NEVER share a product; cross-atlas product use goes
through `depends_on_atlases` (declarative dependency, no write
permission).

---

## §2 What the cross-species pipeline does

Two **independent method families**:

| Family | Tool | Scope | Notes |
|---|---|---|---|
| `gene_order` | BUSCO single-copy ortholog walk | Full phylogeny | `synteny18`, `synteny5`, `genejson` are all gene-order — ONE correlated family |
| `sequence`   | `wfmash` whole-genome alignment | ≤~Clariidae @ p90 / Cranoglanis @ p85 / mid @ p80 | Deep outgroups: skip wfmash entirely |

A breakpoint is **cross-method validated** iff TWO INDEPENDENT method
families agree within `--tol-kb`. Multiple gene-order sources agreeing
is `recurrent`, NOT cross-method.

BP_ATLAS adds **BP3c reciprocity**: a zone is strongest when the same
event appears anchored from BOTH the Cgar and Cmac frames.

---

## §3 Headline (verified 2026-05-23)

Tier 1 — **cross-method validated** (gene_order AND sequence agree):
- **LG27 @ 12.43 Mb** (span 123 kb) — `genejson` + `wfmash`
- **LG27 @ 16.50 Mb** (span 1 kb) — `genejson` + `wfmash` — STRONGEST
- LG23 @ 4.04 Mb (span 200 kb) — `synteny5` + `wfmash`

⇒ **LG27 is a bounded inversion** (both edges cross-method corroborated).
Prime POD target for the hatchery chat.

Tier 2 — **recurrent, single-method-family** (real, but only ONE family):
- LG28 @ 15-19 Mb — gene-order recurrent (synteny18 + synteny5 + genejson);
  NOT sequence-corroborated at p90. Report as karyotype-level fusion.

---

## §4 Parameters (locked)

```
wfmash:        -X -p 90 -s 50000
STEP_CS01:     --min-mapq 1 (wfmash MAPQ is 1-5, NOT 40 like minimap2)
               --min-block-bp 50000 --cluster-radius-bp 50000
               --flank-bp 100000
BP_ATLAS:      Pass A -s 100000, Pass B -s 500000
cluster:       --tol-kb 500 (swept 500→1, stable; proves real not binning)
edge-merge:    200 kb
divergence tiers (BUSCO timetree → wfmash -p):
   Clarias (~15-20My)  → p90
   Cranoglanis (~40My) → p85
   Siluroidei (~55-65My) → p80
   Plotosus (~85My), Trichomycterus (~100My) → SKIP wfmash
```

---

## §5 How it plugs into atlas-core

```
products (cross_species_atlas)
├── breakpoint_clusters.v1                  // headline; cluster_breakpoints.py
├── cross_method_validated_breakpoints.v1   // Tier 1 subset
├── recurrent_breakpoints.v1                // Tier 2 subset
├── reciprocity_table.v1                    // BP3c, BOTH-anchor validated
└── pairwise_summary.v1                     // per (edge × species)

layers (cross_species_atlas)
├── wfmash_paf                              // input — alignment PAF
├── busco_ortholog_table                    // input — wide ortholog table
├── breakpoint_clusters                     // cluster_breakpoints.py output
├── cross_method_validated_breakpoints
├── recurrent_breakpoints
├── reciprocity_table
└── pairwise_summary

analysis_registry
└── cross_species_breakpoint_detection      // engine=subprocess
                                            // adapter: analysis/cross_species_breakpoints/
```

The adapter's `compute.js` does NOT reimplement the pipeline. It
returns a SUBPROCESS recipe: scripts + args. The real pipeline lives in
`analysis/cross_species_breakpoints/legacy_scripts/` and is the user's
hand-tuned chain (preserved as-is).

---

## §6 Cohort discipline (read first)

Three catfish cohorts, NEVER conflate:

1. **F1 hybrid** (C. gariepinus × C. macrocephalus) — assembly paper only.
2. **226-sample pure C. gariepinus hatchery** on LANTA — MS_Inversions
   manuscript; K=broodline.
3. **Pure C. macrocephalus wild** — future paper.

`cross_species_atlas` works on the **comparative cohort** (18 genomes +
hybrid subgenomes). The hatchery LG01 × LG28 work is a SEPARATE atlas
(`inversion_atlas`) and a SEPARATE cohort. Coordinates flow across the
atlas boundary; claims do not.

---

## §7 §refusals

1. **No execution.** The adapter is a recipe, not a runner. Subprocess
   plans go to `02_queue/<action_id>.json`; an external runner picks
   them up.
2. **No cross-cohort claims.** A breakpoint discovered in
   `cross_species_atlas` is a coordinate. To use it on hatchery samples,
   go through `inversion_atlas` and re-validate.
3. **No method-family conflation.** wfmash-vs-wfmash on two pairs is
   recurrent, NOT cross-method. cluster_breakpoints.py enforces this in
   the `n_families` column.
4. **No silent MAPQ defaults.** `--min-mapq 1` is REQUIRED for wfmash
   PAFs (wfmash MAPQ ∈ [1,5]; minimap2 default of 5/40 would filter
   everything).

---

## §8 What's deferred

- **BP4 population overlap** (intersect with 226-cohort haploblocks) —
  next chat, scoped to the hatchery cohort with strict cohort boundary.
- **BP5 figures** (R ribbons, dotplots, montages) — figure chat.
- **C. macrocephalus wild cohort** — future paper.

---

_End of CROSS_SPECIES_BREAKPOINTS_WORKFLOW.md (v0)._
