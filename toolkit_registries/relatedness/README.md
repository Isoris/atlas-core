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
WHAT-KIND analysis_registry.tsv one row per analysis_id; the catalogue of analysis KINDS
TOOLS     module_registry.tsv  one row per biomod module (mirror of `biomod status --json`)
```

`analysis_registry.tsv` is the canonical catalogue: one row per analysis KIND
(`ngsrelate`, `ngspedigree`, `mendelian`, `popstats`, `fst_pairwise`, `theta_pi`,
`dxy`, …) declaring its `input_entity_types`, `input_layer_types`, `produces`,
`engine`, `endpoint`, `default_runner`, `status`, and `requires` (upstream
dependency hint). `analysis_modes.tsv.analysis_type` and
`analysis_results.tsv.analysis_type` both FK into `analysis_registry.analysis_id`.
Adding a new analysis kind is: add one row here + (one or more) rows in
`analysis_modes.tsv` + (when it has a biomod backing) one row in `module_registry.tsv`.
Validated by `scripts/check_analysis_registry.py`.

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
    ├── scan_results.py                        (walk a results dir, infer & propose analysis_results.tsv rows)
    └── scan_inputs.py                         (walk an inputs dir, infer & propose input_values.tsv rows — BEAGLE / dosage)
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

## Bulk-load existing inputs: `scan_inputs.py`

Symmetric counterpart to `scan_results.py` — walks an inputs tree
looking for BEAGLE / dosage / SAF / VCF files and proposes
`input_values.tsv` rows. Same dry-run-by-default semantics, same
defaults JSON (uses the `inputs` section).

```bash
python3 scan_inputs.py \
  --inputs-dir ../03_inputs \
  --defaults    ../01_registry/scan_defaults.json [--apply]
```

For each BEAGLE file the scanner ALSO opens it and reads:
- the **header row** → derives `n_sample_columns` (3 × n_samples for BEAGLE GL)
- the **data row count** → `n_rows`

so the proposed row is already shape-true before it lands. The
contract-checker on page 2 will agree with what's on disk because the
TSV was populated from the file itself.

| File pattern         | value_type   | id prefix |
|---|---|---|
| `*.beagle.gz`        | `BEAGLE_GL`  | `beagle`  |
| `*.beagle`           | `BEAGLE_GL`  | `beagle`  |
| `*.dosage.tsv.gz`    | `dosage`     | `dosage`  |
| `*.dosage.tsv`       | `dosage`     | `dosage`  |
| `*.saf.idx`          | `SAF`        | `saf`     |
| `*.vcf.gz`           | `VCF`        | `vcf`     |

The `inputs.site_tag_for_chrom` map in `scan_defaults.json` shapes the
`value_id`: a BEAGLE in `C_gar_LG28` with tag `LG28_thin500` becomes
`beagle_LG28_thin500_v1`. Pre-existing ids are respected — the scanner
auto-versions on collision.

Smoke-tested:

```
$ scan_inputs.py --inputs-dir ../03_inputs --defaults ../01_registry/scan_defaults.json
0 new · 2 already registered · 0 blocked            ← baseline

$ # drop LG28.thin500.beagle.gz into ../03_inputs/beagle/
$ scan_inputs.py … --apply
✓ OK appended 1 row(s) → input_values.tsv
                                              ← row populated with
                                                n_rows=6, n_sample_cols=18,
                                                sha256:ae642b238…

$ scan_inputs.py …
0 new · 3 already registered · 0 blocked            ← idempotent
```

Combined workflow for a fresh real workspace:

```bash
$EDITOR 01_registry/scan_defaults.json        # one-time wiring
python3 scripts/scan_inputs.py  --inputs-dir  /mnt/e/.../beagle  --defaults … --apply
python3 scripts/scan_results.py --results-dir /mnt/e/.../results --defaults … --apply
python3 scripts/sync_biomod_status.py         # if biomod is on PATH
python3 -m http.server -d . 8765              # → page 4 shows the live registry
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

## The two manuscript paths — end-to-end stress test

Both paths the manuscript needs are wired and exercised by
`scripts/stress_test_paths.py`. The test takes one candidate (default
`inv_LG28_INV_001`) + one sample set (`samples_226_v1`) and walks both
chains through the full resolver → cache-check → dispatcher → register
loop.

```
Path A — relatedness chain
  candidate + karyotype groups
       → ngsrelate / per_candidate     produces  relatedness_res
       → ngspedigree / global          consumes  relatedness_res
       → mendelian / per_candidate     consumes  pedigree_result + BEAGLE

Path B — popstats chain
  candidate + karyotype groups
       → popstats / per_candidate      FST / dxy / piN / piS between karyotype groups
```

Run:

```bash
cd scripts
python3 stress_test_paths.py              # dry walk-through (no execution)
python3 stress_test_paths.py --dispatch   # also run stub runners + register rows
```

After one `--dispatch`, re-running shows all four steps as CACHE hits
(`existing result_id = …`) — this is the "did we already do this?"
short-circuit the resolver design depends on.

What the stress test verifies, across both paths, in one run:

| Registry / Mechanism | Verified by |
|---|---|
| group_registry → sample subsets | `groups_karyotype_inv_LG28_INV_001_v1` row, resolved via `family_karyotype` policy |
| interval_registry → candidate scope | `inv_LG28_INV_001_v1`, resolved via `candidate_interval` policy |
| site_registry → candidate-scoped sites | `sites_inv_LG28_INV_001_v1`, resolved via `candidate_sites` policy (parent=thin500_global, operation=intersect) |
| input_values → matching BEAGLE | `beagle_inv_LG28_INV_001_v1`, resolved via `beagle_matching` policy |
| analysis_registry → mode-driven contract | every `analysis_modes.tsv` row exercised by the resolver |
| module_registry → biomod state | each step's required module shown by `module_registry.tsv` (page 4) |
| **cache check** | per-step "do we already have this?" via `(analysis_type, sample_set, interval, site)` |
| **chain inheritance** | step 2 of Path A pulls `input_result_id = ngsrelate_LG28_v2` from step 1's output |
| **dispatcher → action endpoint contract** | `dispatcher.py` at the workspace root satisfies PR #3's `dispatch_action(manifest, context)` |

## Runners (stubs today, swap for real binaries tomorrow)

`scripts/runners/` ships four thin wrappers that share a common harness
(`_base.py`). Each runner: reads the manifest's `target` to find input
ids, calls a real binary OR writes a contract-true synthetic file in
stub mode, then appends a row to `analysis_results.tsv`.

| Runner | manifest.type | Stub output |
|---|---|---|
| `run_ngsrelate.py` | `run_ngsrelate` | `.res` with `a/b/nSites/theta/IBS0/IBS1/IBS2/KING` |
| `run_ngspedigree.py` | `run_ngspedigree` | `.pedigree.tsv` with `offspring/parent1/parent2/likelihood` |
| `run_mendelian.py` | `run_mendelian` | `.mendelian.tsv` with per-trio error rates |
| `run_popstats.py` | `run_popstats` | `.popstats.tsv` with `chrom/start/end/n_sites/fst/dxy/piN/piS` |

When you wire real binaries: open the runner, replace
`real_executor=None` with a `subprocess.run([...])` call, and the
stress test starts producing real outputs. The contract checker
(`check_result_contract.py`) validates each new result identically.

`dispatcher.py` at the workspace root routes manifests to the right
runner by `manifest.type`. It satisfies the contract from PR #3 so the
atlas server's `POST /api/actions` calls it automatically — no more
"documentation mode" once you copy this folder into your real workspace.

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

## The analysis catalogue — `analysis_registry.tsv`

One row per analysis KIND. Schema:
`schemas/registry_schemas/analysis_registry_row_v1.schema.json`. Today's
catalogue:

| analysis_id | status | input_layer_types | produces | engine | requires |
|---|---|---|---|---|---|
| `ngsrelate`     | active       | `beagle_file,sites_file`             | `relatedness_res`     | ngsRelate       |              |
| `ngspedigree`   | active       | `relatedness_res`                    | `pedigree_result`     | ngsPedigree     | ngsrelate    |
| `mendelian`     | active       | `pedigree_result,beagle_file,sites_file` | `mendelian_result` | mendelian_trio  | ngspedigree  |
| `popstats`      | active       | `beagle_file,sites_file`             | `popstats_result`     | region_popstats |              |
| `fst_pairwise`  | experimental | `beagle_file`                        | `fst_windows`         | region_popstats | popstats     |
| `theta_pi`      | experimental | `beagle_file`                        | `theta_pi_windows`    | region_popstats | popstats     |
| `dxy`           | experimental | `beagle_file`                        | `dxy_windows`         | region_popstats | popstats     |

`analysis_modes.tsv.analysis_type` and `analysis_results.tsv.analysis_type` are
FKs into `analysis_registry.analysis_id`. Adding a new analysis kind is:

1. add one row to `analysis_registry.tsv` (declare `produces`, `input_*`, `engine`)
2. add (one or more) rows in `analysis_modes.tsv` with the policy fields
3. when it has a biomod backing, add the module to `module_registry.tsv`

Validate the FKs:

```bash
python3 scripts/check_analysis_registry.py
# OK    relatedness/: analysis_registry.tsv + FKs clean
```

Checks: schema-required columns, unique `analysis_id`, allowed `status`,
`analysis_modes.tsv.analysis_type` resolves to a row here,
`analysis_results.tsv.analysis_type` resolves to a row here,
each mode's `produces` is declared on its parent registry row,
each mode's `module_name` resolves to `module_registry.tsv`, and
`requires` upstream `analysis_id`s all resolve.

## The layer registry + hooks — APLR's librarian

**Layer is the abstraction.** Modules produce layers; pages consume layers;
APLR's librarian resolves whether each requested layer exists, is missing,
blocked, ready-to-run, complete, or failed.

```
01_registry/
├── layer_registry.tsv    one row per layer KIND (relatedness_res, mendelian_result, karyotype_calls, ...)
├── hook_registry.tsv     one row per page hook (mendelian_page_load, popstats_page_load, ...)
```

A layer is one of four `source_kind`s:

| source_kind | example | producer |
|---|---|---|
| `file`            | `beagle_file`, `sites_file`, `sample_set`, `karyotype_calls` | the underlying registry / external upload |
| `analysis_result` | `relatedness_res`, `pedigree_result`, `mendelian_result`, `popstats_result` | the matching row in `analysis_registry.produces` |
| `operation`       | computed on demand via an HTTP endpoint | the endpoint (not yet wired in the librarian) |
| `inline`          | literal payload embedded in a manifest | the manifest itself |

A hook declares which layers a page needs:

```
hook_id              page_id   requires_layers
mendelian_page_load  mendelian karyotype_calls,inversion_candidates,relatedness_res,pedigree_result,mendelian_result
popstats_page_load   popstats  karyotype_calls,inversion_candidates,popstats_result
```

### The librarian — `resolve_layer.py`

Pure read-only graph walk. Given a layer_id (+ scope), returns one of nine
states:

| state | meaning |
|---|---|
| `RESOLVED`         | file-kind layer present in the scope |
| `COMPLETE`         | analysis_result row exists in `analysis_results.tsv` matching scope, `status=active` |
| `READY_TO_RUN`     | analysis_result; every upstream input resolves to `RESOLVED` / `COMPLETE` |
| `BLOCKED_BY_INPUT` | analysis_result; at least one upstream is `KNOWN_MISSING` / `UNKNOWN_CONTRACT` / `FAILED` |
| `KNOWN_MISSING`    | contract registered, no product / file matches the scope |
| `UNKNOWN_CONTRACT` | `layer_id` not in `layer_registry.tsv` (or `source_kind` not implemented) |
| `STALE`            | reserved (hash-based invalidation; not yet implemented) |
| `FAILED`           | `analysis_results.tsv` row with `status=failed` |
| `PARTIAL`          | reserved (chunked / per-chrom outputs; not yet implemented) |

Use it:

```bash
# single layer in a scope
python3 scripts/resolve_layer.py --layer mendelian_result \
    --sample-set samples_226_v1 --interval-set inv_LG28_INV_001_v1
# → [COMPLETE] mendelian_result: analysis_results.tsv row 'mendelian_LG28_v2' matches scope

# unknown layer
python3 scripts/resolve_layer.py --layer bogus_layer
# → [UNKNOWN_CONTRACT] bogus_layer: layer_id not in layer_registry.tsv

# whole hook — walks every required layer
python3 scripts/resolve_layer.py --hook mendelian_page_load \
    --sample-set samples_226_v1 --interval-set inv_LG28_INV_001_v1
# hook: mendelian_page_load  state: BLOCKED_BY_INPUT  page: mendelian
#   [KNOWN_MISSING] karyotype_calls: ...
#   [KNOWN_MISSING] inversion_candidates: ...
#   [COMPLETE] relatedness_res: ...
#   [COMPLETE] pedigree_result: ...
#   [COMPLETE] mendelian_result: ...

# JSON form for the dashboard
python3 scripts/resolve_layer.py --layer mendelian_result \
    --sample-set samples_226_v1 --interval-set inv_LG28_INV_001_v1 --json
```

> **Librarian only.** `resolve_layer.py` never runs an analysis, never
> writes a file, never queues an action. That is the dispatcher / planner's
> job, which is intentionally a *separate concern*. The clean APLR split:
>
> > The librarian resolves layer identity and current state.
> > The dispatcher uses that resolved state to decide ready / blocked /
> > stale / reusable / run / queue.

## Page 5 — manual layer ↔ analysis connector (`page/layers.html`)

Open `page/layers.html` to see every layer (left column) and every analysis
(right column) with the **declared edges** from `analysis_registry.tsv`
(dashed grey, `input_layer_types` / `produces`) drawn between them. Click
a layer, then an analysis, to add a **manual edge** (solid blue). Toggle
between `input` / `output` edge type at the top. Click a manual edge to
delete it. Manual edges persist to `localStorage`; **Export JSON**
downloads the full edge set for sharing or committing into a workspace.

The page is the practical interface for the layer/analysis adjacency: when
the formal `analysis_registry.tsv` rows are wrong / incomplete / aspirational,
you can wire the missing connections by hand and export the result.

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
| **3. Registries** (`page/index.html`) | Chain compatibility view. Wired ngsRelate → ngsPedigree → mendelian chains with green-light contracts; orphan results flagged "ready for X". Click any brick → right sidebar slides in with the resolved contract, the backing biomod module, editable parameter overrides and a required `reason` → **Save as derivative** downloads a biomod recipe JSON (`schema_version: 0`, `parent: <name>@<version>`, `parent_overrides.{parameters, reason}`) ready for `biomod derive`. | **active** |
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
