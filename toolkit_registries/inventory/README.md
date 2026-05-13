# inventory/ — click and see what the registry has

The "small page we click we see". One sentence:

> Every distinct computation in the registry is one row: `analysis | group | samples | interval`.

## What's here

| File | What it does |
|---|---|
| `index.html` | Single-file vanilla-JS viewer. Open in a browser. Sort by clicking column headers, filter via the toolbar, click a row to expand provenance. |
| `example_data/registry/` | Synthetic registry (4 groups, 5 sample sets, 7 analysis results, 7 layers). Demonstrates the content-hash collapse: row 6 and 7 below share `sample_set_id 2f17041e` (same `ALL` sample list) but have different intervals (LG28 vs whole-genome), so they're two distinct results. |
| `example_data/inventory.json` | The flat table the page reads, produced by `lib/registry_inventory.py`. |

## Quickstart (with the synthetic data)

```bash
# regenerate the inventory.json from the example registry
python toolkit_registries/lib/registry_inventory.py --example \
  --json toolkit_registries/inventory/example_data/inventory.json

# open the page locally (any static server works)
python -m http.server -d toolkit_registries/inventory 8000
# → http://127.0.0.1:8000/
```

## ASCII version (no browser)

```bash
python toolkit_registries/lib/registry_inventory.py --example --print
```

Output:

```
Analysis    │ Group                             │ N   │ Interval                         │ Status │ Layer
────────────┼───────────────────────────────────┼─────┼──────────────────────────────────┼────────┼────────────────────────────────
theta_pi    │ HOM_INV carriers for LG28_INV_001 │ 8   │ C_gar_LG28:14_815_000-18_305_000 │ active │ theta_pi_…_C_gar_LG28_v1
ngspedigree │ ALL \ family_F042 (unrelateds)    │ 222 │ whole-genome                     │ active │ ngspedigree_…_wg_v1
mendelian   │ Family F042 (CGA042 + offspring)  │ 4   │ whole-genome                     │ active │ mendelian_…_wg_v1
ngsrelate   │ HOM_INV ∩ ancestry_K8_cluster3    │ 3   │ C_gar_LG28                       │ active │ ngsrelate_…_C_gar_LG28_v1
ngsrelate   │ HOM_INV carriers for LG28_INV_001 │ 8   │ C_gar_LG28                       │ active │ ngsrelate_…_C_gar_LG28_v1
ngsrelate   │ All 226 samples                   │ 226 │ whole-genome                     │ active │ ngsrelate_…_wg_v1
ngsrelate   │ All 226 samples                   │ 226 │ C_gar_LG28                       │ active │ ngsrelate_…_C_gar_LG28_v1
```

## Against a real registry

Point the scanner at your actual registry root:

```bash
python toolkit_registries/lib/registry_inventory.py /mnt/e/atlas_workspace/registry \
  --json /tmp/inventory.json
```

Then open the viewer with `?src=/tmp/inventory.json` (or copy the file
into `inventory/example_data/` and refresh).

Expected layout under `<registry_root>/`:

```
<registry_root>/
├── analysis_results/*.json   ← one analysis_result_v1 per file
├── sample_sets/*.json        ← one sample_set_v1 per file
├── groups/*.json             ← one group_definition per file (optional)
└── layers/**/*.json          ← layer envelopes, any depth
```

Missing folders are OK — the scanner returns rows for whatever exists.

## How groups are rendered

The "Group" column tries to be the most human-readable thing available,
in this order:

1. `sample_set.label` if set.
2. If the set is `from_group`, the named group's `label` (or `group_id`).
3. If the set is `intersect` / `union` / `difference`, the operation
   rendered with the proper glyph (`∩` / `∪` / `\`).
4. If the set is `from_inline`, `(inline N samples)`.
5. If `filter`, `parent | filter:predicate_tag`.

## The point

Once the registry exists, you don't have to track results by memory.
You see the seven (or seven hundred) rows, you click the one that
matches what you want, and you get its `layer_id`. Same thing the
dispatcher does internally with `lib/set_algebra.plan()` — this page is
just the human-facing version of the same lookup.
