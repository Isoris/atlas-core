# SETS_AND_ANALYSES — two registries that generalize the rest

**Status:** v1, drafted 2026-05-12. Companion to REGISTRY_LOOKUP.md.

The existing sample / group / interval registries are special cases of
**one general pattern**:

> An entity is one object. A set is a named collection of entities of
> one type. A registry catalogues sets.

This doc introduces the two registries that complete the picture:

1. **set_registry** — all named entity sets, regardless of entity_type.
2. **analysis_registry** — the canonical vocabulary of analysis kinds
   (ngsRelate, ngsPedigree, mendelian, fst_pairwise, theta_pi, …).

Both follow the same shape as the rest of the toolkit: one JSON file
per record under `<registry_root>/sets/<entity_type>/<set_id>.json`
or `<registry_root>/analyses/<analysis_id>.json`. The flat TSV
catalogues `set_registry.tsv` and `analysis_registry.tsv` are
generated from those by `lib/registry_index.py` — easy to grep,
easy to load in pandas / R.

---

## Vocabulary

| Term | Meaning |
|---|---|
| entity      | one object (one sample, one variant site, one window, one gene, …) |
| entity_type | the KIND of object (`sample`, `variant_site`, `window`, `gene`, …). Controlled vocabulary in `entity_type_v1.schema.json`. |
| set         | a named collection of entities of one type |
| registry    | a catalogue of sets |

Same pattern, every entity type:

| entity_type            | one is        | a set is                              |
|---|---|---|
| `sample`               | CGA001        | a sample group (the "all 226")        |
| `variant_site`         | LG28:15000123 | a sites file (LG28 SNPs, MAF≥0.05)    |
| `window`               | LG28:1.5–1.6M | a tiling (50 kb windows on LG28)      |
| `inversion_candidate`  | LG28_INV_001  | the D17 PASS candidate list           |
| `breakpoint`           | LG28:15115023 | breakpoints of D17 PASS candidates    |
| `gene`                 | claGar_LG28_g00451 | genes within 50 kb of breakpoints |

---

## How the new registries relate to what already exists

| Existing registry | What it is | Where it fits |
|---|---|---|
| `sample_master.schema.json`       | per-sample metadata row (per cohort)      | the ATOMIC sample registry — one row per entity |
| `group_definition.schema.json`    | named subset of samples (karyotype, ancestry, family, …) | a SAMPLE SET — set_v1 with entity_type='sample' is structurally equivalent |
| `sample_set_v1.schema.json`       | content-hashed sample set (set algebra)   | a SAMPLE SET — same as set_v1 with entity_type='sample', specialized for the lookup hashing |
| `candidate_interval.schema.json`  | candidate interval row                    | an ATOMIC interval registry (one row per entity) |
| `analysis_result_v1.schema.json`  | per-result lookup row → output_layer_id    | one row per ACTUAL COMPUTATION; references analysis_id, sample_set_id, artifacts, params |

The new registries fill two gaps:

- **No registry for sets of other entity types.** Sites files, window
  tilings, candidate lists, gene lists, breakpoint lists — each is a
  set but had no shared catalogue. `set_v1` + `set_registry.tsv` is
  that catalogue.
- **No vocabulary for analysis kinds.** `analysis_result_v1` records
  per-result rows, but there was no source-of-truth for "what is
  `ngsrelate`? what does it take? what does it produce?". `analysis_v1`
  + `analysis_registry.tsv` is the dictionary.

---

## The set registry

### `set_v1.schema.json` — one set per JSON file

Stored at `<registry_root>/sets/<entity_type>/<set_id>.json`.

Required fields: `set_id`, `entity_type`, `status`, `created_at`.

Common optional fields (see schema for the full list):

- `label` — display label
- `path` — relative path to the members file (TSV / TSV.gz)
- `n_entities` — member count
- `hash` — sha256 of canonical members (sorted, '\n'-joined)
- `parent_set_id` — single-parent FK (when there's exactly one parent)
- `derived_from` — set algebra lineage (intersect / union / difference / filter)
- `filter_profile_id` — optional filter-profile FK
- `coordinate_system` — assembly id for coordinate-aware entity types
- `intended_use` — free-form note

### Set algebra is the same as for sample sets

The `derived_from` block in `set_v1` has the same shape as in
`sample_set_v1`:

```json
{
  "op":        "intersect" | "union" | "difference" | "filter" | "from_set" | "from_inline",
  "parents":   [ "set_id_or_group_id", ... ],
  "predicate": "tag-for-filter-op (optional)"
}
```

`lib/set_algebra.py` is **generic over entity_type**: the same
`materialize(expr, resolver)` works on sets of samples, sets of sites,
sets of genes, etc. The only thing that changes is the resolver — for
samples it consults `group_definition` / `sample_set_v1` records; for
other entity types it consults the corresponding `set_v1` records.

### `set_registry.tsv` — flat catalogue

One row per registered set. Columns in order (pinned by
`set_registry_row_v1.schema.json`):

```
set_id  entity_type  label  path  n_entities  hash
parent_set_id  filter_profile_id  coordinate_system
intended_use  status  created_at  definition_path
```

`definition_path` is non-empty when the set has a complex
`derived_from` (multi-parent intersect/union, filter predicate, …)
that doesn't fit in TSV cells — the cell points at the JSON file.

Example row (rendered, tabs replaced with `│` for readability):

```
sites_LG28_localpca_v1 │ variant_site │ LG28 sites — MAF≥0.05, thinned to 1 SNP/kb │
sets/variant_site/LG28.localpca.sites.tsv.gz │ 48211 │ sha256:42a8… │
snps_maf005_v1 │ maf005_thin1k_v1 │ fClaHyb_Gar_LG_v1 │
local PCA, scrubber landscape │ active │ 2026-04-10T12:00:00Z │ 
```

Regenerate with:

```bash
python toolkit_registries/lib/registry_index.py <registry_root>
```

---

## The analysis registry

### `analysis_v1.schema.json` — one analysis kind per JSON

Stored at `<registry_root>/analyses/<analysis_id>.json`.

Captures: what the analysis IS, what entity-type sets and what
artifact layer types it consumes, what layer type it produces, the
engine binary tag, the optional HTTP endpoint, the default runner
module, and the dependency hint (which other analyses it requires
upstream).

```jsonc
{
  "analysis_id":      "ngsrelate",
  "analysis_version": "v1",
  "description":      "Pairwise relatedness from genotype likelihoods.",
  "inputs": {
    "sets":      [ { "role": "samples", "entity_type": "sample" } ],
    "artifacts": [
      { "role": "beagle", "layer_type": "beagle_file", "schema_version": "beagle_file_v1" },
      { "role": "sites",  "layer_type": "sites_file",  "schema_version": "sites_file_v1"  }
    ]
  },
  "produces": [
    { "layer_type": "ngsrelate_result", "schema_version": "ngsrelate_result_v1" }
  ],
  "engine":         "ngsRelate",
  "default_runner": "runners.ngsrelate.run",
  "status":         "active"
}
```

### `analysis_registry.tsv` — flat catalogue

Columns (pinned by `analysis_registry_row_v1.schema.json`):

```
analysis_id  analysis_version  label  description
input_entity_types  input_layer_types  produces
engine  endpoint  default_runner
status  requires  intended_use  definition_path
```

Nested arrays in the JSON (`inputs.sets`, `inputs.artifacts`,
`produces`, `requires`) flatten to comma-separated cells:

```
ngsrelate │ v1 │ ngsRelate — pairwise relatedness from genotype likelihoods │
Estimates pairwise relatedness coefficients (theta, IBS0/1/2, KING) from a BEAGLE genotype-likelihood file restricted to a sites file. │
sample │ beagle_file,sites_file │ ngsrelate_result │
ngsRelate │ │ runners.ngsrelate.run │
active │ │ kinship QC, family detection, pedigree input │ analyses/ngsrelate.json
```

When `inputs.sets` has multiple roles or `inputs.artifacts` has more
than one entry, `definition_path` is populated so a reader who needs
the full structure can `cat` the JSON.

---

## Where the TSV catalogues live

In the workspace registry root, alongside the other indices:

```
<registry_root>/
├── set_registry.tsv             ← flat catalogue of every set
├── analysis_registry.tsv        ← flat catalogue of every analysis_id
├── sets/
│   ├── sample/<set_id>.json
│   ├── variant_site/<set_id>.json
│   ├── window/<set_id>.json
│   ├── inversion_candidate/<set_id>.json
│   ├── gene/<set_id>.json
│   ├── breakpoint/<set_id>.json
│   └── …                        ← one folder per entity_type
├── analyses/<analysis_id>.json
├── analysis_results/<result_id>.json     ← per-computation lookup
├── sample_sets/<sample_set_id>.json      ← content-hashed sample sets
├── groups/<group_id>.json                ← named sample groups
└── layers/**/*.json                      ← layer envelopes (the actual outputs)
```

The TSV files are **derived** — regenerate after adding / changing
any JSON record. The JSONs are the source of truth.

---

## Worked example — the relatedness pipeline at a glance

The user's pipeline (`beagle.gz → ngsRelate → .res → ngsPedigree →
ngsTract / mendelian`) becomes:

1. **Register the inputs as sets**:
   - `samples_broodstock226_v1` (entity_type=sample) — sample set
   - `sites_wholegenome_thin1k_v1` (entity_type=variant_site) — sites file
2. **Register the analyses** (one-time):
   - `ngsrelate` — wants a sample set + a sites set + a beagle artifact, produces `ngsrelate_result_v1`.
   - `ngspedigree` — wants a sample set + an `ngsrelate_result_v1` artifact, produces `ngspedigree_result_v1`. Requires upstream `ngsrelate`.
   - `mendelian` — wants a sample set + a `ngspedigree_result_v1` artifact + a `beagle_file_v1` artifact, produces `mendelian_result_v1`. Requires upstream `ngspedigree`.
3. **Ask the registry** (Python or the inventory page) "do we already have an `ngsrelate` result for samples_broodstock226_v1 × sites_wholegenome_thin1k_v1 × beagle X with params P?"
4. **If miss**, submit an action manifest → runner produces `.res` → extractor parses → layer envelope written → `analysis_result_v1` row appended → cached forever.
5. **Inventory page** shows the new row immediately.

All four registries (sets, analyses, sample-sets-for-the-content-hash,
analysis-results) compose. No (groups × analyses × samples ×
intervals) explosion because identity collapses on content hash; no
bookkeeping in the user's head because the inventory page is one
click.

---

## What this does NOT do

- **Does not deprecate the existing schemas.** `group_definition`,
  `sample_set_v1`, and `candidate_interval` stay as-is. The new
  `set_v1` is a generalization; existing schemas remain the
  specialized forms that downstream code already uses.
- **Does not impose a database.** TSVs are flat files; JSONs are flat
  files. The whole registry is filesystem-readable and `grep`-able.
- **Does not invent new endpoints.** This is metadata + helpers; the
  action / extractor pipeline from `PIPELINE_FLOW.md` is what runs
  things.
- **Does not freeze entity_type.** Atlases may define new entity types
  in their own `entity_type_v1` files (e.g. `pedigree_trio`,
  `recombination_hotspot`) and the helper will scan them transparently.
