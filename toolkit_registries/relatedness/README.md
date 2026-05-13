# relatedness/ — minimum infrastructure that unstucks ngsRelate → ngsPedigree → mendelian

Six flat TSV registries + four contract checkers + one register tool.
Stdlib Python only (no pandas, no extra deps). Copy this folder into
your real workspace, replace the synthetic example data with your real
files, and the contract checker tells you whether each result is
ready for downstream use.

## The dependency order

```
WHO       sample_sets.tsv      one row per sample set (catflist)
LABELS    group_sets.tsv       one row per family/population/batch table
WHERE     interval_sets.tsv    one row per coordinate scope
WHICH     site_sets.tsv        one row per variant-site list (thinned, filtered)
WHAT-IN   input_values.tsv     one row per BEAGLE / dosage / SAF / VCF
WHAT-OUT  analysis_results.tsv one row per ngsRelate / ngsPedigree / mendelian / … run
HOW       analysis_modes.tsv   one row per (analysis × mode); the resolver's brain
```

Every WHAT-OUT row points at WHO + LABELS + WHERE + WHICH + WHAT-IN
(and optionally an upstream WHAT-OUT). A row is **valid** only when
every FK resolves AND the input contract holds (BEAGLE samples in the
right order, BEAGLE rows match sites, group samples ⊆ sample set).

## Folder layout

```
relatedness/
├── 01_registry/                 ← the six TSVs (this is where you look)
│   ├── sample_sets.tsv
│   ├── group_sets.tsv
│   ├── interval_sets.tsv
│   ├── site_sets.tsv
│   ├── input_values.tsv
│   └── analysis_results.tsv
├── 02_sets/                     ← the actual set files referenced from above
│   ├── samples/broodstock226.samples.tsv
│   ├── groups/groups_main.tsv
│   ├── intervals/{genome_all,C_gar_LG12}.tsv
│   └── sites/{thin500.global,LG12.thin500}.sites.tsv.gz
├── 03_inputs/                   ← BEAGLE / dosage matrices
│   └── beagle/{thin500.global,LG12.thin500}.beagle.gz
├── 04_results/                  ← outputs
│   ├── ngsrelate/{global,LG12}.res
│   ├── ngspedigree/pedigree.tsv
│   └── mendelian/LG12.mendelian.tsv
├── schemas/                     ← per-TSV row schemas (column order pinned)
│   ├── sample_sets_row.schema.json
│   ├── group_sets_row.schema.json
│   ├── interval_sets_row.schema.json
│   ├── site_sets_row.schema.json
│   ├── input_values_row.schema.json
│   └── analysis_results_row.schema.json
└── scripts/
    ├── io_helpers.py                          (shared TSV/BEAGLE loaders)
    ├── check_beagle_header_vs_samples.py
    ├── check_beagle_rows_vs_sites.py
    ├── check_group_samples_vs_sample_set.py
    ├── check_result_contract.py               (the master check)
    ├── resolve.py                             (mode-driven contract resolver)
    └── register_result.py
```

## The most important command

```bash
cd relatedness/scripts
python3 check_result_contract.py --result mendelian_LG12_v1
```

For the synthetic example, this prints (3 levels deep, recursive):

```
RESULT: mendelian_LG12_v1  (mendelian)
  ✓ OK sample_set_id: samples_226_v1
  ✓ OK group_set_id: groups_main_v1
  ✓ OK interval_set_id: C_gar_LG12_full_v1
  ✓ OK site_set_id: sites_LG12_thin500_v1
  ✓ OK input_value_id: beagle_LG12_thin500_v1
  ✓ OK input_result_id: ngspedigree_global_v1
  ✓ OK result file exists: 04_results/mendelian/LG12.mendelian.tsv
  ✓ OK BEAGLE header vs samples (6 samples in canonical order)
  ✓ OK BEAGLE rows vs sites (6 rows)
  ✓ OK group_set samples ⊆ sample_set
  upstream check:
    RESULT: ngspedigree_global_v1  (ngspedigree)
      … all checks ✓ …
      upstream check:
        RESULT: ngsrelate_global_v1  (ngsrelate)
          … all checks ✓ …

OVERALL: ✓ OK
READY FOR:
  • family-QC summary tables
  • trio reliability flags
```

If any check fails, you see exactly which contract broke and where.

## The other four scripts

```bash
# Just the BEAGLE header / sample order
python3 check_beagle_header_vs_samples.py --value beagle_thin500_global_v1

# Just the BEAGLE row count vs site_set (use --strict-marker to also
# verify each row's marker matches the corresponding sites row)
python3 check_beagle_rows_vs_sites.py --value beagle_thin500_global_v1 --strict-marker

# Just the group_set ⊆ sample_set check
python3 check_group_samples_vs_sample_set.py --group groups_main_v1

# Append a new analysis_results row (refuses to write if the contract fails)
python3 register_result.py \
  --result-id        ngsrelate_LG28_v1 \
  --analysis-type    ngsrelate \
  --path             04_results/ngsrelate/LG28.res \
  --sample-set-id    samples_226_v1 \
  --group-set-id     groups_main_v1 \
  --interval-set-id  C_gar_LG28_full_v1 \
  --site-set-id      sites_LG28_thin500_v1 \
  --input-value-id   beagle_LG28_thin500_v1 \
  --method-id        ngsrelate_v2
```

Every script accepts `--registry-root <PATH>` to override; otherwise
they walk upward looking for `01_registry/`.

## The resolver — let the registry do the thinking

You don't want to remember which sample_set + which thin500 + which BEAGLE
goes with which chromosome. `analysis_modes.tsv` + `resolve.py` do that:

```bash
# "Run ngsRelate on chromosome 12 for the 226 samples."
python3 resolve.py --analysis ngsrelate --mode per_chromosome \
                   --sample-set samples_226_v1 --chromosome C_gar_LG12
```

Output:

```
=== contract ===
  analysis_type       ngsrelate
  mode                per_chromosome
  sample_set_id       samples_226_v1
  group_set_id        groups_main_v1
  interval_set_id     C_gar_LG12_full_v1
  site_set_id         sites_LG12_thin500_v1
  input_value_id      beagle_LG12_thin500_v1
  produces            relatedness_res

STATUS: ✓ OK  ready to run
```

The resolver walked `analysis_modes.tsv` to find the row for
`ngsrelate / per_chromosome`, then applied its policies:

| policy            | tag                | how it resolves |
|---|---|---|
| `interval_policy` | `chromosome_full`  | finds an interval_set with `interval_type=chromosome` containing the requested chrom |
| `site_policy`     | `thin500_per_chr`  | finds the site_set whose name contains `thin500` AND whose `interval_set_id` matches |
| `group_policy`    | `family_population`| finds the group_set whose `group_columns` contain both `family` and `population` |
| `value_policy`    | `beagle_matching`  | finds the BEAGLE input_value whose `(sample_set_id, site_set_id, interval_set_id)` triple matches |

Add `--explain` to see each step. Add `--emit-register-cmd` to also
print a `register_result.py` invocation skeleton.

When a policy has multiple valid matches, the resolver REFUSES to guess —
it lists the candidates and asks you to pick:

```
STATUS: ⚠ WARN  ambiguous policy match — pick one explicitly:
  • site_policy='thin500_per_chr': … — candidates: [sites_LG12_thin500_v1, sites_LG12_thin1000_v1]
```

When a required dimension is missing, it fails fast:

```
STATUS: ✗ FAIL  missing inputs:
  • required dimension 'chromosome' not provided (use --chromosome)
```

Modes wired today (`01_registry/analysis_modes.tsv`):

| analysis_type | mode             | required             | produces           |
|---|---|---|---|
| ngsrelate     | genome_wide      | sample_set           | relatedness_res    |
| ngsrelate     | per_chromosome   | sample_set,chromosome| relatedness_res    |
| ngsrelate     | per_candidate    | sample_set,candidate_id | relatedness_res |
| ngspedigree   | global           | ngsrelate_result     | pedigree_result    |
| mendelian     | per_candidate    | candidate_id,pedigree_result | mendelian_result |

For chained analyses (ngspedigree consumes a relatedness_res), use
`--ngsrelate-result <id>` and the resolver INHERITS the contract
(sample_set, group_set, interval_set, site_set) from the upstream row.
No re-typing.

## How to use this in your real workspace

1. **Copy the folder** (or just `01_registry/` + `scripts/`) into your
   actual data root.
2. **Replace the example rows in the six TSVs** with real ones —
   point `path` at your real samples TSV, real groups TSV, real
   sites file, real BEAGLE, real `.res`.
3. **Run `check_result_contract.py --result <yours>`** for each
   existing result. Fix anything red.
4. **For new runs**, call `register_result.py` after the run finishes.
   It refuses to register a row whose contract doesn't pass, so you
   never accumulate orphans or mismatched-sample-order results.

## What this is NOT

- **Not the LLM resolver.** That's deferred. When you build it later,
  it reads the same six TSVs.
- **Not a workflow engine.** The scripts just check contracts; you
  still run ngsRelate / ngsPedigree / mendelian yourself. The contract
  check tells you whether the result is safe to use downstream.
- **Not coupled to `toolkit_registries/`.** The folder is
  self-contained. Stdlib only. Move it anywhere; rename `relatedness/`
  if you want.
- **Not the rich registry** (`toolkit_registries/schemas/registry_schemas/`).
  That's the long-term shape with per-record JSONs, content-hash
  identity, set algebra, action manifests, the inventory page. THIS
  folder is the unblocker for tomorrow; the rich registry is for
  later, and they're compatible by design — every concept in here
  has a richer counterpart there.
