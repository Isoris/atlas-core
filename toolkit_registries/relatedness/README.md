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
TOOLS     module_registry.tsv  one row per biomod module (mirror of `biomod status --json`)
```

The TOOLS row is the bridge to **biomod** — the conda-style module catalog
described in `BIOMOD_SPEC.md`. biomod owns the module / runs / install
state (under `~/.biomod/envs/<env>/`). atlas-core just reads a snapshot
of `biomod status --json` so the pages can show whether each
analysis_type's backing module is installed / ready / stale / failed.
`analysis_modes.tsv.module_name` is the FK from a mode to a module.

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
    ├── register_result.py
    ├── sync_biomod_status.py                  (refresh module_registry.tsv from `biomod status --json`)
    └── scan_results.py                        (walk a results dir, infer & propose analysis_results.tsv rows)
```

## Bulk-load existing results: `scan_results.py`

Pointing `register_result.py` at every existing `.res` by hand is
unworkable when you have dozens. `scan_results.py` walks a results
tree, infers `analysis_type` from path + `chromosome` from filename
tokens, looks up FKs in a small JSON defaults file, and proposes
`analysis_results.tsv` rows.

```bash
cd scripts

# Dry run — see what would be registered without writing
python3 scan_results.py \
  --results-dir ../04_results \
  --defaults    ../01_registry/scan_defaults.json

# Actually append (refuses rows with unresolved FKs)
python3 scan_results.py \
  --results-dir ../04_results \
  --defaults    ../01_registry/scan_defaults.json \
  --apply
```

The defaults file maps **chromosome tokens** (parsed from filenames:
`LG12`, `C_gar_LG28`, `global`, `whole_genome`) to existing registry
ids. Example:

```jsonc
{
  "sample_set_id": "samples_226_v1",
  "group_set_id":  "groups_main_v1",
  "method_id_by_analysis": {
    "ngsrelate": "ngsrelate_v2", "ngspedigree": "ngspedigree_v1", "mendelian": "mendelian_v1"
  },
  "interval_set_for_chrom":  { "global": "genome_all_v1", "C_gar_LG12": "C_gar_LG12_full_v1" },
  "site_set_for_chrom":      { "global": "sites_thin500_global_v1", "C_gar_LG12": "sites_LG12_thin500_v1" },
  "input_value_for_chrom":   { "global": "beagle_thin500_global_v1", "C_gar_LG12": "beagle_LG12_thin500_v1" }
}
```

File-pattern recognition (out of the box):

| File pattern             | analysis_type |
|---|---|
| `*.res`                  | `ngsrelate` |
| `pedigree*.tsv`          | `ngspedigree` |
| `*mendelian*.tsv`        | `mendelian` |
| `*.qopt`                 | `ngsadmix` |

Properties:

- **Idempotent.** Files whose `path` already appears in `analysis_results.tsv` are skipped.
- **Refuses to silently guess.** If a chromosome token doesn't map to a known interval / site / value in the defaults file, the row is BLOCKED and `--apply` refuses to write. Fix the defaults, re-run.
- **Computes sha256.** Each accepted row gets a real content hash in the `hash` column.
- **Auto-versioning.** `result_id` collisions auto-bump (`ngsrelate_LG28_v1` → `_v2` if `_v1` already taken).
- **Stdlib only.** No PyYAML / pandas / etc.

Smoke-tested end-to-end on the bundled synthetic data:

```
$ scan_results.py --results-dir ../04_results --defaults ../01_registry/scan_defaults.json
0 new · 4 already registered · 0 blocked            ← baseline (4 example rows already in)

$ # drop two new files (LG28.res, LG28.mendelian.tsv) into ../04_results
$ scan_results.py … --apply
✓ OK appended 2 row(s) → analysis_results.tsv

$ scan_results.py …                                  ← re-run
0 new · 6 already registered · 0 blocked            ← idempotent
```

## Biomod bridge — what backs each analysis

The atlas pages don't run modules; biomod does. `module_registry.tsv`
is the bridge: one row per biomod module, generated by
`sync_biomod_status.py`. Re-sync whenever the biomod state changes:

```bash
# Live (requires biomod on PATH)
python3 scripts/sync_biomod_status.py

# Or from a JSON dump
biomod status --json > /tmp/biomod.json
python3 scripts/sync_biomod_status.py --from-json /tmp/biomod.json

# Or use the bundled example payload to see the page wire up before biomod is installed
python3 scripts/sync_biomod_status.py --from-json 01_registry/biomod_status.example.json
```

Each row carries: `module_name`, `version`, `family`, `installed`,
`ready`, `stale`, `last_run_status`, `last_run_qc`, `conda_env_path`,
`biomod_env` — the same fields biomod emits.

Page 2 (Action) and Page 3 (Registries) both load this TSV and show a
**module status pill** alongside the data-readiness pill:

| Module pill | Meaning |
|---|---|
| `mod_ready`        | installed + last run succeeded + not stale |
| `mod_available`    | installed but never run (or no last_run info) |
| `mod_stale`        | installed but inputs have changed since last run |
| `mod_failed`       | installed but last run failed |
| `mod_not_installed`| analysis_mode references this module but biomod doesn't have it |
| `mod_conceptual`   | analysis_mode references a module name that's not in module_registry.tsv at all |

So a step on page 2 could show **`MISSING` + `mod_ready`** ("you have
the tool, you don't have the inputs") or **`RUN_READY` + `mod_failed`**
("inputs are all set, but the tool crashed last time — investigate
before rerunning").

## The dashboard — three pages, one nav

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

## The dashboard — three pages, one nav

The atlas-core dashboard. Open any of the three pages, click between
them via the top nav.

| Page | What it does | Status |
|---|---|---|
| **1. Conversation** (`page/conversation.html`) | LLM-driven request resolver: free-text request → cleaned decomposition → controlled vocabulary → registry contracts → action plan. | **stub** — design only; deferred |
| **2. Action** (`page/action.html`) | Readiness & routing dashboard. Pick a target analysis + scope; the page walks the chain backward through `analysis_modes.tsv` and shows each step's status: `RESULT_READY` (reuse), `RUN_READY`, `SPAWNABLE`, `BLOCKED`, `MISSING` (data side) + `mod_ready` / `mod_stale` / `mod_failed` / `mod_not_installed` / `mod_conceptual` (module side). **Does not run anything** — gatekeeper, not orchestrator. | **active** |
| **3. Registries** (`page/index.html`) | Chain compatibility view. Wired ngsRelate → ngsPedigree → mendelian chains with green-light contracts; orphan results flagged "ready for X". | **active** |
| **4. Catalogue** (`page/catalogue.html`) | Browse every module and every analysis the registry knows about. Two tabs — **Modules** (from `module_registry.tsv`) shows each biomod module with its readiness + lineage arrows (which module feeds into it, which it feeds into); **Analyses** (from `analysis_modes.tsv`) shows each analysis_type/mode with its module FK, policies, required dimensions, produces. | **active** |

Open them:

```bash
python3 -m http.server -d toolkit_registries/relatedness 8765
# → http://127.0.0.1:8765/page/action.html
# → http://127.0.0.1:8765/page/index.html
# → http://127.0.0.1:8765/page/conversation.html
```

### What page 2 (Action) shows

For the synthetic example, picking **mendelian / per_candidate** with
`samples_226_v1`, `chromosome=C_gar_LG12`, `candidate_id=LG12_INV_001`:

```
step 1 of 3   ngsrelate / per_chromosome    [RESULT_READY]  → ngsrelate_LG12_v1
                                            (reuse — output exists & matches contract)

step 2 of 3   ngspedigree / global          [RUN_READY]
                                            inputs all resolved; suggests register_result.py
                                            cmdline to register the new pedigree

step 3 of 3   mendelian / per_candidate     [MISSING]  no candidate_set, candidate_interval policy
                                            needs --candidate-id LG12_INV_001 → resolves
                                            (and the page UPDATES live as you tweak the form)
```

A summary row at the top shows the overall counts:
**1 RESULT_READY · 1 RUN_READY · 1 MISSING**.

### The readiness ladder (page 2 status vocabulary)

| Status | Meaning | Recommended action |
|---|---|---|
| `RESULT_READY`  | Output already exists, matches the requested contract  | REUSE — copy `result_id` |
| `RUN_READY`     | All inputs resolved, no existing output                | RUN — page emits the `register_result.py` command line |
| `SPAWNABLE`     | Inputs missing but derivable from registered sets       | SPAWN inputs first |
| `DATA_READY`    | Inputs exist but checks not yet run                     | run `check_*` scripts |
| `BLOCKED`       | A policy has multiple matches OR existing result conflicts | DISAMBIGUATE — page lists candidates |
| `MISSING`       | A required dimension or input is missing AND not spawnable | REGISTER the missing input |
| `CONCEPTUAL`    | Module known to LLM but not registered                  | wire the module |

The page does NOT run anything. It tells you what to reuse, what's
run-ready, and what's blocked.

## The page — open and see the chains

A single-file HTML viewer at `page/index.html`. Loads the six TSVs
directly (no Python build step), groups results into chains, and
highlights compatibility:

- **Wired chains** — every `analysis_results` row that points at an
  upstream via `input_result_id` is grouped with its upstream and
  downstream rows. The whole chain renders as a coloured row of
  cards with green arrows between them. Each cell is colour-coded by
  analysis type (ngsRelate green, ngsPedigree teal, mendelian
  purple). The header says **"contract: ✓ OK end-to-end"** when every
  step's FKs resolve.

- **Ready-for badges** — orphan results (no current consumer) get a
  blue **"ready for ngspedigree/global"** badge when their
  `produces` (looked up in `analysis_modes.tsv`) matches a downstream
  analysis's `required_dimensions`. So you immediately see *"this
  ngsRelate result has no pedigree downstream yet, but it could feed one"*.

- **Failed contracts** — any FK that doesn't resolve renders as a red
  badge so you spot stale rows at a glance.

Open it:

```bash
python3 -m http.server -d toolkit_registries/relatedness 8765
# → http://127.0.0.1:8765/page/
```

For the synthetic example the page shows two chains:

| Chain | Steps |
|---|---|
| ngsrelate → ngspedigree → mendelian | `ngsrelate_global_v1` → `ngspedigree_global_v1` → `mendelian_LG12_v1` (all green, contract OK end-to-end) |
| ngsrelate (alone) | `ngsrelate_LG12_v1` — flagged **"ready for ngspedigree/global"** |

Filter bar at the top: by sample_set or by interval.

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
