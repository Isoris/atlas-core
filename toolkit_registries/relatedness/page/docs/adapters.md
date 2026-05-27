# Adapters (page 13)

Per-analysis in/out contract viewer. For every adapter folder under `toolkit_registries/analysis/<analysis_id>/`, the page reads the meta row from `analysis_registry.jsonl` and probes the folder for its shipped contract files.

## Reads

- `01_registry/analysis_registry.jsonl` — meta (input_layer_types, produces, requires, version, engine, status)
- `01_registry/atlases.jsonl` — atlas color/icon for the badge
- `../../analysis/<analysis_id>/adapter_atlas.js` — presence-probed
- `../../analysis/<analysis_id>/compute.js` — presence-probed
- `../../analysis/<analysis_id>/schema_in.json` — fetched + JSON-pretty-printed
- `../../analysis/<analysis_id>/schema_out.json` — fetched + JSON-pretty-printed
- `../../analysis/<analysis_id>/example_input.json` — fetched, collapsible
- `../../analysis/<analysis_id>/example_output.json` — fetched, collapsible

The page never executes the adapter. It only reads the contract files.

## Layout

| pane | what |
|---|---|
| **left (picker)** | One row per adapter folder; id + label + 5 file-presence dots (schema_in · schema_out · example_in · example_out · compute) |
| **right (detail)** | Three collapsible cards: **meta** (analysis_registry row + completeness pill + shipped-files chips), **schema (in/out)** (side-by-side pretty JSON), **example (in/out)** (collapsed by default) |

## Completeness scoring

Each adapter is scored over 5 file slots:
`schema_in · schema_out · example_input · example_output · compute`.

- 5/5 → green `complete` pill
- 3-4/5 → blue `N/5` pill
- ≤2/5 → amber `N/5` pill

Lets the user see at a glance which adapters are still skeletons. Today: 3/5 adapters are 5/5 complete (`cross_species_breakpoints`, `inversion_pair_incompatibility`, `iv_candidate_promoter`), 2/5 ship only `adapter_atlas.js` (`karyotype_auto_caller`, `karyotype_polarizer`).

## What to edit fast

- Add a new adapter? Drop a folder under `toolkit_registries/analysis/<analysis_id>/` with at least `adapter_atlas.js` and register the analysis_id in `analysis_registry.jsonl` with `definition_path: "analysis/<analysis_id>/adapter_atlas.js"`. The page picks it up on next reload.
- Fill out an adapter? Add `schema_in.json`, `schema_out.json`, `example_input.json`, `example_output.json`. The completeness dots flip green incrementally.
- Update meta? Edit the `analysis_registry.jsonl` row.

## §refusals

1. **No execution.** Page 13 never runs an adapter. The compute.js + adapter_atlas.js files are read-only here.
2. **No write-back to the adapter folder.** Edits go via git, not via the page.
3. **Missing files are visible.** A `schema_in.json` that isn't shipped renders as a yellow `○` dot in the picker + a dashed "no schema_in.json shipped" message in the detail. Never silently absent.
