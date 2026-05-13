# toolkit_registries — the librarian

The atlas registry's **method specifications, canonical schemas, and
4-role organizing logic**. No code, no data — contracts and rules.

The actual JS engine that *implements* these contracts lives in
`atlas-core/core/`. The actual data files the registry routes to live
wherever `master_config.yaml` says they live. This folder is the
contract layer between them.

---

## What's here

| File | Purpose | Status |
|---|---|---|
| **HIERARCHY_SPEC.md** | Definitive data model: species → genome → cohort → group hierarchy, combine rule, hybrid F1 case, FK chain | active, v1 (chat ~34 fifth pass) |
| **MASTER_CONFIG.md** | Spec for the master config — the one file that tells the registry where everything is on this machine | active, v1 |
| **DATABASE_DESIGN.md** | The 4-role mental model (samples / intervals / evidence / results) + FK discipline + integrity contract | active, canonical (refreshed chat ~34: R-API code preserved as illustrative; concepts canonical) |
| **SPEC_DEFERRED.md** | Forward-looking specs for compute features that originated in the LANTA-era pipeline | each spec's Status line was rewritten in atlas-registry terms; bodies kept as scientific reference |
| **schemas/registry_schemas/** | Core registry schemas. See breakdown below | active |
| **schemas/structured_block_schemas/** | 41 per-aspect schemas for evidence blocks (boundary_refined, gene_cargo, mendelian, etc.) + `BK_KEYS_EXPLAINED.md` | draft; polished per-page during atlas migration |
| **schemas/specs/** | 3 deeper specs: `INVERSION_REGISTRY_SPECIFICATION_v2.md`, `STRUCTURED_BLOCK_SCHEMAS.md`, `CHARACTERIZATION_CONVERGENCE_RULES.md` | canonical scientific contracts; no LANTA-API contamination |
| **LLM_FUNNEL_SPEC.md** | Design spec for page 1's staged LLM resolver: free-text request → cleaned decomposition → domain selection → controlled keyword mapping → refinement Q&A → registry contract resolution. Two LLM calls (stages 1 & 3), three deterministic stages (2, 4, 5). | v1 design; not implemented yet |
| **vocabulary/** | Controlled vocabulary for the LLM funnel — `domains.tsv` (Layer 0) + per-domain `keywords/*.tsv` (Layer 1) + `edges.tsv` (concept graph). 12 domains, ~90 starter terms across inheritance / relatedness / popgen / structural_variation / population_history / sample_filtering. | v1 data |

### registry_schemas/ breakdown

| Schema | Role in hierarchy | Status |
|---|---|---|
| `species.config.schema.json` | Taxonomic identity (v2: pure taxonomy, no operational fields) | active |
| `genome.config.schema.json` | Assembly file + species_composition + per-chrom subgenome tags | active |
| `cohort.config.schema.json` | BAM list × genome × metadata; combine rule encoded as constraint | active |
| `sample_master.schema.json` | Per-sample TSV row contract (referenced by cohort.samples_tsv) | active |
| `group_definition.schema.json` | Analytical subset of one cohort, append-only | active |
| `sample_group.schema.json` | LANTA-era TSV-row form of group; superseded by group_definition | back-compat |
| `candidate_interval.schema.json` | Candidate interval row | active |
| `evidence_key.schema.json` | Per-key evidence extraction contract | active |
| `result_row.schema.json` | Result manifest row | active |
| `master_config.schema.json` | The master_config.yaml shape | active |

---

## Reading order

1. **HIERARCHY_SPEC.md** — the data model. Species → genome → cohort →
   group hierarchy, combine rule, hybrid case, FK chain. Read first;
   everything else assumes you know this.
2. **MASTER_CONFIG.md** — how the registry loads species/genomes/cohorts
   and learns where data is on disk.
3. **DATABASE_DESIGN.md** §"The four roles" — the organizing logic
   every layer entry inherits (samples / intervals / evidence /
   results).
4. **schemas/registry_schemas/** — the 5 hierarchy schemas
   (species.config, genome.config, cohort.config, sample_master,
   group_definition) plus `master_config`, `candidate_interval`,
   `evidence_key`, `result_row`.
5. **schemas/structured_block_schemas/** — read these as needed;
   they're the per-aspect contracts the atlas registry validates
   writes against during analysis.

Skip SPEC_DEFERRED unless you're working on a deferred feature.

---

## What this folder does NOT contain

- **JS engine code** → `atlas-core/core/`
- **Per-atlas registry config** (layers, files, operations, pages,
  slots) → `<atlas>/registries/data/*.registry.json`
- **Atlas-specific schemas** (e.g. `arrangement_calls.schema.json`,
  `karyotype_assignment.schema.json`) → `<atlas>/registries/schemas/`
- **Data files** → wherever the master config says (`/mnt/e/`,
  `<atlas>/data/`, LANTA-mounted drives, etc.)

---

## Why "toolkit_registries"

Historical name from the LANTA-era `inversion-popgen-toolkit/registries/`
folder. Re-anchored 2026-05-06 (chat ~34) to mean: "the toolkit that
defines how atlas registries work." The 4-role organizing logic
(`samples` / `intervals` / `evidence` / `results`) survives unchanged.
What changed: the runtime is now JS in the browser instead of R on
LANTA, and data lives wherever `master_config.yaml` points.

If you're confused about which "registry" something refers to: the
**atlas registry** is the one runtime-resolved object pages call
(`registry.resolve(...)`). This folder defines what that object's
methods *mean*. There aren't two registries anymore.
