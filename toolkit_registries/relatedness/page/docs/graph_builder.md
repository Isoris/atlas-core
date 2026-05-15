# Graph Builder (page 7)

Five-column node-canvas (sets / filters / layers / analyses / hooks) — Phase B + C of `LAYER_GRAPH_BUILDER_SPEC.md`. Click a node to add it to the graph; click two in-graph nodes to draw an edge; edges are validated live against the §6 rule table.

## Reads

- `01_registry/layer_registry.jsonl`
- `01_registry/analysis_registry.jsonl`
- `01_registry/hook_registry.jsonl`
- `01_registry/sample_sets.jsonl` / `interval_sets.jsonl`
- `../../vocabulary/edge_rules.tsv` — the §6 type-validation rules

## Interaction

| Action | Result |
|---|---|
| Click a registry node | toggles in/out of graph (`IN GRAPH` pill) |
| Click two in-graph nodes | draws an edge with selected `edge_type` |
| Click an edge | confirms + deletes |
| Shift+click | removes a node from graph |

## What to edit fast

- Edge rules: `toolkit_registries/vocabulary/edge_rules.tsv` (7 constraint expressions: `always`, `entity_type_match`, `layer_in_inputs`, `layer_in_produces`, `layer_in_requires_or_optional`, …)
- Persistence: manual graph saved to `localStorage` (`atlas_graph_builder_v1`); **Export JSON** downloads `layer_graph_v1` JSON.
