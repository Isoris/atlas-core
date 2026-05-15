# Registries (page 3)

Chain compatibility view. Renders the wired ngsRelate → ngsPedigree → mendelian + popstats chains as colored bricks; click a brick to open the right brick-edit sidebar.

## Reads

- `01_registry/analysis_results.tsv` — every result row becomes a brick
- `01_registry/analysis_modes.tsv` — chain-step metadata
- `01_registry/module_registry.tsv` — the brick's module color
- `01_registry/sample_sets.tsv` / `interval_sets.tsv` / `site_sets.tsv` / `input_values.tsv` — hover-preview data

## Brick-edit sidebar

Click a brick → slide-in sidebar shows the resolved contract + editable parameter overrides + a required `reason`. **Save as derivative** downloads a biomod-recipe JSON (`schema_version: 0`, `parent: <name>@<version>`, `parent_overrides.{parameters, reason}`).

## What to edit fast

- Add a new result row to `analysis_results.tsv` — it appears as a new brick on reload
- Color a new analysis_type — extend `.step.<name>` CSS in `index.html`
