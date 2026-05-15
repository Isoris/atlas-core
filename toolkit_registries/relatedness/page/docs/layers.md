# Layers (page 5)

Manual layer ↔ analysis connector. Two columns (layers / analyses), declared edges drawn in dashed grey from `analysis_registry.tsv`. Click a layer then an analysis to add a **manual edge** (solid blue).

## Reads

- `01_registry/layer_registry.tsv` — left column
- `01_registry/analysis_registry.tsv` — right column + the declared edges

## What you do here

- Drag-click to wire layers to analyses that aren't yet declared as `input_layer_types` / `produces`
- **Export JSON** → `{declared_edges, manual_edges}`. Useful when the formal `analysis_registry.tsv` is aspirational and you want to record the *real* wiring you intend.

## What to edit fast

- Add a row to `layer_registry.tsv` → it appears in the left column on reload
- Add a row to `analysis_registry.tsv` (with `input_layer_types` / `produces`) → declared edges appear automatically
