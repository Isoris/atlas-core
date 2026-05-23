# Catalogue (page 4)

Two tabs: **Modules** (from `module_registry.tsv`) and **Analyses** (from `analysis_modes.tsv`).

## Reads

- `01_registry/module_registry.tsv` — biomod modules + readiness state + lineage
- `01_registry/analysis_modes.tsv` — every (analysis × mode) row
- `01_registry/atlases.jsonl` — atlas badge colors (each card carries an atlas badge tinted by `atlas.color`)

## What this page is for

Looking up: *which biomod module backs `ngsrelate / per_candidate`?* — or vice versa: *what does `region_popstats_v0_4` produce?*

## Atlas badges

Each module card and analysis card now carries an **atlas badge** with the atlas's icon + label, tinted by `atlases.color`. Modules declare their atlas via `module_registry.atlas`; analyses inherit from their module. Filter the page by typing an atlas id (e.g. `cross_species` → all orange cards).

## What to edit fast

- Re-run `scripts/sync_biomod_status.py` to refresh `module_registry.tsv` after a biomod state change
- Add a row to `analysis_modes.tsv` for a new (analysis × mode) pair; the catalogue picks it up automatically
- New module? Set `atlas: "<atlas_id>"` in its `module_registry` row so the badge shows up
- New atlas color? Edit `atlases.jsonl` `color: "#RRGGBB"` — both the card badge and the workspace_health stripe update on next load
