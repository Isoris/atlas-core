# inventory/ — click and see what the registry has

The "small page we click we see". Six tabs:

| Tab | Shows |
|---|---|
| **Results**     | One row per `analysis_result_v1` — `analysis × group × samples × interval`. Click a row to expand to full provenance. |
| **Sets**        | Every named set from the set_registry, grouped by entity_type. The Derivation column links to the matching row in the Derivations tab. |
| **Derivations** | One row per derivation recipe: `operation_type + parent_set + operation_params + filter_profile + analysis_purpose + software`. Links bidirectionally to Sets (parent + produces) and to Params. |
| **Params**      | The parameter bundles. Distinguishes e.g. `thin500_first_per_chrom_v1` (deterministic) from `thin500_random_seed123_v1` (random with seed) — same distance, different identity. Each row's expand shows which derivations use it. |
| **Analyses**    | The analysis vocabulary — what `ngsrelate`, `ngspedigree`, `mendelian`, `fst_pairwise`, `theta_pi`, … take as inputs, what they produce, what they require upstream. |
| **Chain**       | Local chain composer. Pick a target analysis + a sample set, the page walks `requires` backward, builds the ordered chain, and writes the **input contract** (action manifest) and the **output contract** (expected layer envelope) for each step. Marks each step **cached ✓** or **todo ⊳**. |

One JSON file feeds all four tabs (`example_data/inventory.json`,
written by `lib/registry_inventory.py`).

## Quickstart (synthetic data)

```bash
# 1. regenerate the inventory.json from the example registry
python toolkit_registries/lib/registry_inventory.py --example \
  --json toolkit_registries/inventory/example_data/inventory.json

# 2. serve and open
python -m http.server -d toolkit_registries/inventory 8000
# → http://127.0.0.1:8000/
```

## ASCII version (no browser)

```bash
python toolkit_registries/lib/registry_inventory.py --example --print
```

## Against a real registry

```bash
python toolkit_registries/lib/registry_inventory.py /mnt/e/atlas_workspace/registry \
  --json /tmp/inventory.json
```

Open with `?src=/tmp/inventory.json`, or copy the file into
`inventory/example_data/` and reload.

Expected layout under `<registry_root>/`:

```
<registry_root>/
├── analysis_results/*.json   ← analysis_result_v1 → Results tab
├── sample_sets/*.json        ← sample_set_v1
├── groups/*.json             ← group_definition (optional)
├── sets/<entity_type>/*.json ← set_v1            → Sets tab
├── analyses/*.json           ← analysis_v1       → Analyses tab + Chain composer
└── layers/**/*.json          ← layer envelopes
```

Missing folders are OK — each tab shows whatever exists.

## How groups are rendered (Results tab)

In order of preference:

1. `sample_set.label` if set.
2. Named group's `label` when `derived_from.op == "from_group"`.
3. `intersect` / `union` / `difference` rendered with `∩` / `∪` / `\`.
4. `(inline N samples)` for `from_inline`.
5. `parent | filter:predicate_tag` for `filter`.

## Chain composer — what it does

When you select a target analysis (e.g. `mendelian`) and a sample set:

1. **Walks `requires` backward** through the analysis_registry. For
   `mendelian` that's `mendelian ← ngspedigree ← ngsrelate`. Cycles
   are detected and rejected.
2. **Topological-sorts** the chain (deepest first → the chain runs in
   that order).
3. **For each step, generates two contracts:**
   - **Input contract:** an `action_manifest` skeleton with
     `target.input_artifacts` wired from upstream steps' `produces[*].layer_type`,
     ready for the user to fill in `<sample_set_id>` / `<beagle_layer_id>` etc.
   - **Output contract:** the expected `layer_envelope` shape — what
     the runner+extractor must emit, what schema_out it must validate against.
4. **Checks the cache.** For each step, compares
   `(analysis_id, sample_set_id)` against `analysis_results`. If a
   match exists, the step is marked **cached ✓** with the existing
   `layer_id`. Otherwise **todo ⊳**.
5. **Download chain.json.** Concatenates the action manifests in
   order so you can submit them via `POST /api/actions` one at a
   time, or batch them into a runner.

The cache check is a heuristic — it matches on
`analysis_id + sample_set_id` only. The real server-side lookup
(via `lib/set_algebra.plan()`) uses the full
`(analysis_id, sample_set_id, sorted(input_artifact_ids), params_hash)`
content hash, which is stricter. The page's heuristic is good enough to
plan against in the browser; the server has the final word at submit time.

## The point

Once the registry exists, you don't have to track anything by memory.

- **What do we have?** — Results tab.
- **What sets exist?** — Sets tab.
- **Which analyses are wired?** — Analyses tab.
- **What does it take to get a mendelian result for these samples?** — Chain tab.

Same lookup the dispatcher does internally with
`lib/set_algebra.plan()` — this page is the human-facing version.
