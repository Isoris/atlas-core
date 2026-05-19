# Action (page 2)

Readiness & routing dashboard. Pick a target analysis + scope; the page walks the chain backward through `analysis_modes.tsv` and shows each step's status.

## Reads

- `01_registry/analysis_modes.tsv` — mode rows (analysis × mode, policies)
- `01_registry/analysis_results.tsv` — existing results
- `01_registry/module_registry.tsv` — biomod module readiness

## States it surfaces

- `RESULT_READY` (reuse)
- `RUN_READY` (inputs there)
- `SPAWNABLE` (can create the missing inputs from existing data)
- `BLOCKED` (data side missing)
- `MISSING` (no path)
- Plus module states: `MOD_READY` / `MOD_STALE` / `MOD_FAILED` / `MOD_NOT_INSTALLED` / `MOD_CONCEPTUAL`

## What to edit fast

- `01_registry/analysis_modes.tsv` to change the policies / produces of a mode
- `01_registry/module_registry.tsv` to update biomod state (or re-run `scripts/sync_biomod_status.py`)

**This page never runs anything.** It's a gatekeeper, not an orchestrator.
