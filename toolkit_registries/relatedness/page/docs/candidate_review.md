# Candidate review (page 6)

The first **vertical-slice page** of `LAYER_GRAPH_BUILDER_SPEC.md` §11. Renders the output of `resolve_layer.py --compose candidate_review_hook` — one panel per layer the hook requires / optionally consumes.

## Reads

- `01_registry/hook_registry.tsv` — `candidate_review_hook` row (its `requires_layers` + `optional_layers` + `panels`)
- `01_registry/layer_registry.tsv` — layer source_kind / default_path
- `01_registry/analysis_results.tsv` — matching result rows
- `02_sets/candidates/inversion_candidates.tsv` — candidate dropdown
- `02_sets/karyotype/karyotype_calls.tsv` — karyotype data

## Panel states

| state | render |
|---|---|
| `VISIBLE_COMPLETE` | full panel + 6-row TSV preview |
| `VISIBLE_PARTIAL`  | full panel + stale / partial badge |
| `VISIBLE_BLOCKED`  | red card listing `missing_layers[]` + Inspect button |
| `READY_TO_RUN`     | blue card + manual **Run** button (does NOT run) |
| `HIDDEN_OPTIONAL`  | hidden; toggle "show HIDDEN_OPTIONAL" to reveal |

## What to edit fast

- Add a panel: edit `hook_registry.tsv` → append to `optional_layers` + `panels`
- Change a candidate: edit `02_sets/candidates/inversion_candidates.tsv`
- Add karyotype data: edit `02_sets/karyotype/karyotype_calls.tsv`
