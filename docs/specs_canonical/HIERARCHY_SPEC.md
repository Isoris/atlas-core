# HIERARCHY_SPEC — species, genomes, cohorts, groups

**Status:** v1, drafted 2026-05-06 (chat ~34, fifth pass).
**Companion schemas** (in `schemas/registry_schemas/`):
- `species.config.schema.json` — taxonomic identity
- `genome.config.schema.json` — assembly file + species composition
- `cohort.config.schema.json` — BAM list × genome × metadata
- `sample_master.schema.json` — per-sample metadata TSV row contract
- `group_definition.schema.json` — analytical subset of one cohort

This doc explains the four-level hierarchy, the combine rule for
cohorts, where the hybrid F1 case fits, and what FK chains look like
across the registry.

---

## The four levels

```
┌──────────────────────────────────────────────────────────────┐
│  SPECIES (taxonomic tag, ~5 entries ever)                    │
│  Operationally non-functional — never the unit a query runs. │
│  Tags genomes (which species' DNA?) and samples (which        │
│  species is this individual?).                                │
└─────────────────────┬────────────────────────────────────────┘
                      │ tagged on
                      ▼
┌──────────────────────────────────────────────────────────────┐
│  GENOME (assembly file, 1-3 per species)                     │
│  One .fa = one genome_id. Coordinates live here. Carries     │
│  species_composition (often size 1; size ≥2 for hybrids)     │
│  and per-chromosome subgenome_of tags.                        │
└─────────────────────┬────────────────────────────────────────┘
                      │ FK genome_id
                      ▼
┌──────────────────────────────────────────────────────────────┐
│  COHORT (BAM list × genome × metadata)                        │
│  THE OPERATIONAL UNIT. Engines run on a cohort.               │
│  Cohort_id is the folder slug for results.                    │
│  Has: genome_id (FK), samples_tsv path,                       │
│       species_composition (derived from samples_tsv),         │
│       parent_cohort_ids[] (lineage).                          │
└────────────┬───────────────────────────┬──────────────────────┘
             │ FK cohort_id              │ FK cohort_id
             ▼                           ▼
┌──────────────────────────────┐  ┌──────────────────────────┐
│  GROUP (analytical subset)   │  │  CANDIDATE / RESULT /    │
│  Subset of ONE cohort,        │  │  EVIDENCE                │
│  defined for a question.      │  │  All cohort-scoped.      │
│  Append-only.                 │  │                           │
└──────────────────────────────┘  └──────────────────────────┘
```

**One sentence per level:**

- **Species** — taxonomic tag. Never the unit anything runs against;
  just metadata you put on genomes and samples.
- **Genome** — one .fa file. Coordinates only mean something within
  a genome. Re-assembly produces a NEW genome_id; coordinates do not
  cross.
- **Cohort** — one BAM list aligned to one genome plus per-sample
  metadata. The unit engines run on, the unit results belong to.
- **Group** — named subset of ONE cohort, defined ad-hoc for an
  analytical question. Append-only.

---

## Cohort as the operational unit

The cohort is what engines (ANGSD, NGSadmix, ngsRelate, popstats)
expect: one BAM list, one reference. That's the cohort.

Cohort entry fields:

- `cohort_id` — stable name, used as folder slug, used as FK target.
- `genome_id` — which assembly the BAMs are aligned to. FK.
- `samples_tsv` — path (relative to a configured root) to the
  per-sample metadata TSV. Schema: `sample_master.schema.json`.
  Columns include `sample_id`, `species`, `origin`, `phenotype`,
  `family_id`, `bam`.
- `species_composition` — set of species present in the cohort.
  **Derived from samples_tsv** (the unique set of `species` values
  across rows) — declared at write time, validated against the TSV.
- `parent_cohort_ids[]` — optional; lineage for derived cohorts
  (subset / combine).
- `metadata` — short summary fields: collection_year,
  sequencing_batch, description.

Sample-level metadata lives in **a separate TSV**, not inlined in
YAML. Reasons: hundreds-to-thousands of rows; editable in Excel;
same physical sample can appear in two cohorts via separate rows or
a shared sample_master with cohort filters.

---

## Group as the analytical subset

A group is a named subset of ONE cohort, defined when an analysis
needs it. Groups express:

- "HOM_INV carriers for candidate LG28_INV_001" (karyotype)
- "samples in NGSadmix cluster 3" (ancestry)
- "hatchery batch A" (origin)
- "samples where phenotype = white-flesh" (phenotype)
- "samples in family CGA042's pedigree" (family)

Group entry fields:

- `group_id` — stable name following the convention from
  DATABASE_DESIGN.md §"Sample group naming".
- `cohort_id` — which cohort this group is a subset of. FK.
- `members` — sample_ids in the group (inline list or members file
  path). All must be present in the cohort's samples_tsv.
- `dimension` — what kind of subset: `karyotype`, `ancestry`,
  `family`, `phenotype`, `origin`, `intersect`, `subcluster`,
  `manual`.
- `parent_group_id` — optional FK for sub-groups inside a parent
  group.
- `source_methods[]` — how the group was defined.
- `status` — `active` | `deprecated` | `experimental`. Append-only:
  redefinition adds a new group with a new id; old one stays
  readable for reproducibility.

---

## Subset (cohort → smaller cohort)

When a group is important enough to warrant its own engine runs,
promote it to a derived cohort:

```yaml
cohort_id:          "gariepinus_pure_only_v1"
genome_id:          "fClaHyb_Gar_LG_v1"
samples_tsv:        "cohorts/gariepinus_pure_only_v1/samples.tsv"
species_composition: ["gariepinus"]
parent_cohort_ids:  ["main_226_hatchery"]
metadata:
  derivation:       "subset where samples_tsv.species == 'gariepinus'"
```

The new cohort gets its own folder under `data/cohorts/{cohort_id}/`
where engines run independently. Original cohort is unchanged.

**Subset vs group — when to use which:**

- Use a **group** if the analysis can express the subset on the
  fly: "give me this filter on cohort A's samples." Cheap. Ad-hoc.
- Use a **derived cohort** if the analysis needs its own engine
  binaries run on its own BAM list. Heavyweight. Long-lived.

In practice: "all 200 fish I'll cite in figure 3" → cohort.
"HOM_INV carriers within that cohort" → group.

---

## Combine (multiple cohorts → one cohort)

Two cohorts can be combined into one new cohort **only if both of
these hold**:

```
cohort_A.genome_id == cohort_B.genome_id
            AND
set(cohort_A.species_composition) == set(cohort_B.species_composition)
```

Same genome alone is not enough. Same species composition alone is
not enough. Both must hold.

Why both:

- Same genome → coordinates are compatible (a position on `LG28`
  means the same thing).
- Same species composition → biology is compatible (you're
  combining like with like, not silently mixing pure-parent samples
  into a hybrid analysis).

Examples:

| A | B | Combinable? | Why |
|---|---|---|---|
| Hatchery gariepinus, genome G1 | Wild gariepinus, genome G1 | YES | Same genome, same species composition `{gariepinus}` |
| Hatchery gariepinus, genome G1 | Hatchery gariepinus, genome G2 | NO | Different genome (re-assembly invalidates coordinates) |
| Hatchery gariepinus, genome G_hybrid | F1 hybrids, genome G_hybrid | NO | Same genome but different composition: `{gariepinus}` vs `{F1_hybrid}` |
| F1 hybrids, genome G_hybrid (cohort A) | F1 hybrids, genome G_hybrid (cohort B, different farm) | YES | Same genome, same composition `{F1_hybrid}` |
| Shrimp cohort | Tilapia cohort | NO | Different species. Comparative-layer work, not cohort-combine. |

The combined entry:

```yaml
cohort_id:          "gariepinus_combined_v1"
genome_id:          "fClaHyb_Gar_LG_v1"
samples_tsv:        "cohorts/gariepinus_combined_v1/samples.tsv"
species_composition: ["gariepinus"]
parent_cohort_ids:  ["main_226_hatchery", "wild_collection_2027"]
metadata:
  derivation:       "union of hatchery + wild gariepinus cohorts"
```

The schema validates both rules at write time. Try to combine
cohorts that violate either rule → validation rejects. This
prevents the failure mode "FST computed across cohorts that don't
share coordinates or biology."

`samples_tsv` for the combined cohort is the union of the parents'
TSVs. Same physical sample appearing in both parents is deduplicated
on `sample_id`.

---

## Cross-species work is NOT cohort-combine

What about comparing shrimp with tilapia, or gariepinus with
macrocephalus across separate cohorts?

That's **comparative-layer work**. Different concept, different
machinery, different data root.

The atlas registry has a `comparative` root (in `master_config.yaml`)
that holds inherently multi-species data: synteny blocks, breakpoint
reuse maps, phylogenies, TE fragility tracks. Each comparative file
references multiple species_ids as fields inside the data, not as
parent cohorts.

The registry's posture: **cohort = species-coherent unit; comparative
= cross-species surface**. Don't try to use one for the other.

---

## The hybrid F1 case (worked example)

A hybrid F1 organism has DNA from two parental species. When
sequenced and aligned to a hybrid assembly that contains both
parental subgenomes, the model handles it without special cases.

**Genome record** for the hybrid assembly:

```yaml
genome_id:          "fClaHyb_Gar_LG_v1"
fasta:              "fClaHyb_Gar_LG.fa"
fai:                "fClaHyb_Gar_LG.fa.fai"
species_composition: ["gariepinus", "macrocephalus"]
n_chromosomes:      28
chromosomes:
  - name: "C_gar_LG01"
    length_bp: 35000000
    subgenome_of: "gariepinus"
  # ...
  - name: "C_mac_LG01"
    length_bp: 33000000
    subgenome_of: "macrocephalus"
  # ...
```

**Cohort options** (depends on the experiment):

*Option 1 — F1-only cohort, aligned to the hybrid genome:*

```yaml
cohort_id:          "f1_validation_v1"
genome_id:          "fClaHyb_Gar_LG_v1"
samples_tsv:        "cohorts/f1_validation_v1/samples.tsv"
species_composition: ["F1_hybrid"]
```

samples.tsv rows: all `species: F1_hybrid`. Combinable with another
F1-only cohort against the same genome.

*Option 2 — pure parents-only cohort, aligned to the hybrid genome
(useful for validating subgenome separation):*

```yaml
cohort_id:          "pure_parents_validation_v1"
genome_id:          "fClaHyb_Gar_LG_v1"
samples_tsv:        "cohorts/pure_parents_validation_v1/samples.tsv"
species_composition: ["gariepinus", "macrocephalus"]
```

samples.tsv rows: mixed `species: gariepinus` and `species:
macrocephalus`. Combinable only with another cohort of the same
composition.

*NOT combinable with each other:* options 1 and 2 share genome but
have different species_composition. They live in separate cohort
folders.

**Filtering analyses to one subgenome** is per-engine: the genome's
`chromosomes[*].subgenome_of` tags expose the metadata; analysis
modules iterate the chromosome list and respect the subgenome filter
where it matters. The registry doesn't bake subgenome filtering into
a layer.

---

## FK chain — what the integrity check verifies

Every result, candidate, evidence block, and group sits at a known
position:

```
SPECIES.species_id ←─── GENOME.species_composition[]
                            ↑
                            │
                       GENOME.genome_id ←─── COHORT.genome_id
                                                 ↑
                                                 │
                                            COHORT.cohort_id ←─── GROUP.cohort_id
                                                              ←─── CANDIDATE.cohort_id
                                                              ←─── RESULT.cohort_id
                                                              ←─── EVIDENCE.cohort_id
```

The integrity check (DATABASE_DESIGN.md §"Integrity check") verifies
end-to-end:

1. Every `species_id` referenced by a genome exists in species configs.
2. Every `genome_id` referenced by a cohort exists in genome configs.
3. Every `cohort_id` referenced by a group / candidate / result /
   evidence exists in cohort configs.
4. Every cohort's declared `species_composition` matches the unique
   set of `species` values in its `samples_tsv`.
5. Every derived cohort's `parent_cohort_ids[*]` reference existing
   cohorts AND those parents satisfy the combine rule (same
   genome_id, same species_composition).
6. Every sub-group's `parent_group_id` references an existing group
   AND that parent shares `cohort_id`.
7. Every group's `members[]` are all in the cohort's samples_tsv.
8. Every candidate's `chrom` is one of its `cohort_id → genome_id →
   chromosomes[*].name`.
9. (Existing) Every result row's `who_*.group_id` exists; group
   versions match.

Any violation flags the offending row.

---

## Where data physically lives (per Quentin chat ~34 Q2)

Decision: **all results, candidates, evidence go under
`data/cohorts/{cohort_id}/...`**.

```
data/
├── species/                      ← species.config.yaml files
│   ├── gariepinus.config.yaml
│   └── macrocephalus.config.yaml
├── genomes/                      ← genome.config.yaml files
│   ├── fClaHyb_Gar_LG_v1.config.yaml
│   └── ...
│   └── <genome_id>/              ← per-genome data (precomp, dosage)
│       ├── precomp/
│       └── dosage/
├── cohorts/
│   ├── main_226_hatchery/
│   │   ├── cohort.config.yaml
│   │   ├── samples.tsv
│   │   ├── relatedness/
│   │   │   ├── ngsrelate_run_2026_04_30/
│   │   │   │   ├── _manifest.json
│   │   │   │   ├── relatedness.tsv
│   │   │   │   └── samples.txt
│   │   │   └── ...
│   │   ├── ancestry/
│   │   │   └── ngsadmix/K8/...
│   │   ├── popstats/
│   │   ├── candidates/
│   │   │   ├── LG28_INV_001/
│   │   │   │   ├── lineage.json
│   │   │   │   └── v2_theta_refined/
│   │   │   │       ├── boundaries_refined.json
│   │   │   │       └── ...
│   │   ├── groups/
│   │   │   ├── inv_LG28_INV_001_HOM_REF.json
│   │   │   ├── inv_LG28_INV_001_HOM_INV.json
│   │   │   └── ...
│   │   └── arrangement_calls/
│   ├── gariepinus_pure_only_v1/      ← derived cohort (subset)
│   │   └── ... (same shape; engine results live here)
│   └── gariepinus_combined_v1/        ← derived cohort (combine)
│       └── ...
├── comparative/                  ← cross-species, NOT a cohort
│   ├── synteny/
│   ├── breakpoint_reuse/
│   └── phylogeny/
├── working_dir/                  ← persistent atlas-side outputs
└── _cache/                       ← ephemeral; safe to delete
    └── server_results/{op_id}/{hash}.json
```

The earlier `species_scoped: true` flag on roots in
`master_config.yaml` is **superseded** by this layout. The new
master_config (when refactored, next session) uses:

- `genome_scoped: true` for roots like `precomp` and `dosage` (one
  per genome).
- `cohort_scoped: true` for roots like `relatedness`, `ancestry`,
  `popstats`, `candidates`, `groups` (one per cohort).
- Flat for `comparative`, `working_dir`, `cache`.

The current `master_config.example.yaml` keeps `species_scoped` for
back-compat until a page1 migration step touches a layer that
benefits from the cohort/genome split. Refactor is per-page, not
all-at-once.

---

## What this hierarchy does NOT support (intentionally)

- **Mixed-species cohorts.** A cohort is species-coherent (one
  composition). Cross-species work happens at the comparative layer.
- **Cross-cohort groups.** A group belongs to one cohort. To
  express "samples across cohorts", first combine the cohorts (if
  the combine rule allows), then define a group inside the combined
  cohort.
- **Combining cohorts with different genome_id.** Different
  assemblies = different coordinate systems = no shared meaning.
  Use a comparative-layer surface (synteny, lift-over) instead.
- **Combining cohorts with different species_composition.** Same
  genome but different composition = different biology. Same
  reasoning as above.
- **Automatic species/cohort/group inference from data files.**
  All four levels are declared in config. Data files trust the
  declarations.
- **Cohort hierarchy beyond parent/child.** parent_cohort_ids[] is
  a flat lineage list, not a tree of trees. Sufficient for
  subset/combine; not modeling species phylogeny or experimental
  design DAGs.

These constraints are deliberate. They keep the model small enough
to reason about and prevent failure modes that have bitten
bioinformatics pipelines in the past.

---

## Migration path from the current state

The atlas today still uses `species_scoped` in `master_config.yaml`
and a single-cohort assumption. Migration is per-page during page1+
work:

1. **When page1 migration touches a layer that needs cohort
   awareness** (e.g. relatedness, ancestry, popstats), that layer's
   path template is rewritten from
   `data/{species_id}/cohort/relatedness/...` to
   `data/cohorts/{cohort_id}/relatedness/...`.
2. **When page1 migration touches a layer that needs genome
   awareness** (e.g. precomp, dosage), that layer's path is
   rewritten from
   `data/{species_id}/precomp/...` to
   `data/genomes/{genome_id}/precomp/...`.
3. The `cohort_id` and `genome_id` resolved from the active cohort
   (master_config has an `active_cohort:` field; the active cohort
   determines the active genome via FK).
4. Existing layer entries that don't need cohort awareness (the
   `comparative`, `working_dir`, `cache` roots) stay flat.
5. After all 22 pages migrate, every layer is rebased on the new
   model. No big-bang.

The five schemas in `schemas/registry_schemas/` are written now so
that step 1-2 are straightforward when reached.

---

## Schemas written this round

All five exist as draft contracts in
`schemas/registry_schemas/`:

| Schema | Purpose | Required fields |
|---|---|---|
| `species.config` | Taxonomic identity | species_id, label |
| `genome.config` | Assembly metadata | genome_id, fasta, species_composition |
| `cohort.config` | BAM list × genome × metadata | cohort_id, genome_id, samples_tsv, species_composition |
| `sample_master` | Per-sample TSV row | sample_id, species, bam |
| `group_definition` | Analytical subset | group_id, cohort_id, members, dimension, status |

Each schema has a `_examples` section showing one filled-in case.
The combine rule is encoded as a documented constraint on
`cohort.config`'s `parent_cohort_ids[]` (the engine validates at
write time; the schema declares the constraint for human readers).

---

## Reading order

For a contributor seeing this for the first time:

1. **This file** — the data model.
2. **`MASTER_CONFIG.md`** — how the atlas loads species/genomes/cohorts/groups.
3. **`DATABASE_DESIGN.md`** §"Multi-species" + §"Sample group naming" —
   the 4-role mental model now consumes this hierarchy.
4. **The five schemas in `schemas/registry_schemas/`** — formal contracts.

That's the chain. Hierarchy → loading → role consumption → formal
schemas.
