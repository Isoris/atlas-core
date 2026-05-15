# Catalogue (page 4)

Two tabs: **Modules** (from `module_registry.tsv`) and **Analyses** (from `analysis_modes.tsv`).

## Reads

- `01_registry/module_registry.tsv` — biomod modules + readiness state + lineage
- `01_registry/analysis_modes.tsv` — every (analysis × mode) row

## What this page is for

Looking up: *which biomod module backs `ngsrelate / per_candidate`?* — or vice versa: *what does `region_popstats_v0_4` produce?*

## What to edit fast

- Re-run `scripts/sync_biomod_status.py` to refresh `module_registry.tsv` after a biomod state change
- Add a row to `analysis_modes.tsv` for a new (analysis × mode) pair; the catalogue picks it up automatically
