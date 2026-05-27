# SPEC — relatedness IN/OUT JSON adapters (retrospective)

**Status**: shipped. Landed as commits 14–23 of the toolkit_registries
action-pipeline branch (per
[atlas-core/toolkit_registries/STATUS.md](../../atlas-core/toolkit_registries/STATUS.md)
§1). This SPEC is **retrospective** — the code shipped before the SPEC
was written.

**Implemented in:**
- [`atlases/relatedness/registries/dispatcher.py`](../atlases/relatedness/registries/dispatcher.py)
- [`atlases/relatedness/registries/runners/import_tsv.py`](../atlases/relatedness/registries/runners/import_tsv.py)
- [`atlases/relatedness/registries/runners/normalize_relatedness.py`](../atlases/relatedness/registries/runners/normalize_relatedness.py)
- [`atlases/relatedness/registries/extractors/relatedness_tsv.py`](../atlases/relatedness/registries/extractors/relatedness_tsv.py)
- [`atlases/relatedness/registries/extractors/normalize_relatedness.py`](../atlases/relatedness/registries/extractors/normalize_relatedness.py)
- 4 schemas under `registries/schemas/{schema_in,schema_out}/`
- 2 registry files under `registries/data/`

This is the **canonical reference implementation** for the
[atlas-core adapter cookbook](../../atlas-core/docs/SPEC_atlas_adapter_cookbook.md).

---

## 1. Goal

Bridge ngsRelate / ngsPedigree / mendelian / NAToRA / evalAdmix TSV
outputs into the atlas action-pipeline envelope contract, so any
relatedness-atlas page can call
`resolveLatestLayer('ngsrelate_pairs', { stage: 'normalized' })` instead
of `fetch('atlases/relatedness/data/relatedness.tsv')`.

## 2. Two-action flow

```
TSV (any of ngsRelate / ngsPedigree / mendelian / NAToRA / evalAdmix)
    │
    ▼ POST /api/actions { type: "import_relatedness_tsv", ... }
    │   → staging_relatedness_v0 (loose: {analysis, columns, rows})
    │
    ▼ POST /api/actions { type: "normalize_relatedness",
    │                     target.source_layer_id: <staging id> }
    │   → ngsrelate_pairs_v1 (typed: {pairs[], summary})
```

Layer type for both stages: `relatedness_result` (staging) or
`ngsrelate_pairs` (normalized). The analysis discriminator
(`ngsrelate | ngspedigree | mendelian | natora | evaladmix`) is captured
in the staging envelope's payload and propagated into the normalized
output's column-map handling.

## 3. Canonical columns (ngsrelate_pairs_v1)

Per row:
- `ind1` (string) — first sample id (ngsRelate column `a`)
- `ind2` (string) — second sample id (column `b`)
- `n_sites` (int) — informative sites
- `theta` (float) — pairwise relatedness estimate
- `king` (float) — KING-robust kinship coefficient
- `rab` (float) — ngsRelate R statistic
- `ibs0` / `ibs1` / `ibs2` (float) — identity-by-state proportions

Default column map (raw ngsRelate → canonical):
- `a → ind1`, `b → ind2`, `KING → king`, `R → rab`, `nSites → n_sites`,
  `IBS0/1/2 → ibs0/1/2`, `theta → theta` (identity)

Overridable via `manifest.params.column_map` for the ngsPedigree /
mendelian / NAToRA / evalAdmix variants (which use different raw names).

## 4. Type coercion

Per [`extractors/normalize_relatedness.py`](../atlases/relatedness/registries/extractors/normalize_relatedness.py):

- `n_sites` → integer (handles `"12345.0"` from ngsRelate's float-int output)
- `theta`, `king`, `rab`, `ibs0/1/2` → float (`"NaN"`, `"NA"`, `""` → null)
- `ind1`, `ind2` → string (str() coerced)

Null-tolerant: any unparseable cell becomes `None` rather than raising.

## 5. Summary block

`ngsrelate_pairs_v1.summary`:
- `n_pairs` — total
- `n_samples` — distinct ids across `ind1 ∪ ind2`
- `median_theta` — null if no pairs

Drives the [`network`](SPEC_network_page.md) and
[`compatibility`](SPEC_compatibility_page.md) status badges.

## 6. Why looser v1 than meiosis-atlas

Compared to the [meiosis tract_classifications_v1
schema](../../meiosis-atlas/specs_done/SPEC_tract_classifications_adapter.md):

- Relatedness's `pairs[].items` is `additionalProperties: true` — handles 5
  different per-tool column sets behind one schema.
- Meiosis's `tracts[].items` is strict, matches ngsTracts METHODOLOGY §5.1
  verbatim.

The looser shape was the right call for relatedness because the producer
landscape is heterogeneous (5 tools). For a single-producer adapter
(meiosis ↔ ngsTracts), strict is preferable.

## 7. Reference for new adapters

Use this adapter as the reference for any new adapter pair. The 12-file
scaffold in [atlas-core's cookbook](../../atlas-core/docs/SPEC_atlas_adapter_cookbook.md)
was distilled from this implementation + meiosis-atlas's.
