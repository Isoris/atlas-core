# Readiness — Manager (page 8)

The Manager's clickable readiness map. Left column = biological-object products. Right column = research questions + the Estimability Manager output per question.

## Reads

- `01_registry/products.jsonl` — biological-object products
- `01_registry/questions.jsonl` — research questions
- `01_registry/estimands.jsonl` — per-claim estimability preconditions
- `01_registry/sample_attributes.jsonl` — cohort metadata coverage
- `01_registry/layer_registry.jsonl` + `analysis_registry.jsonl` + `analysis_results.jsonl` — the librarian's substrate

## The two-pill display

Each question shows **two** pills:

- **Status Manager** (`ready_to_run` / `partial` / `blocked` / `unknown`) — *is the data ready?*
- **Estimability Manager** (`fully_estimable` / `partially_estimable` / `limited` / `needs_extra_data`) — *what can we claim from the data?*

A question can be `ready_to_run` and still have `not_estimable` estimands. **Same word "missing", different recovery paths**.

## What you do here

- Click any product → adds to scope (LS-persisted)
- Click a question → detail pane shows per-required status + per-estimand status + next actions
- "What's around the scope" → nearby products that share `sample_scope` or `coordinate_scope`

## What to edit fast

- Add a product: append a row to `products.jsonl`
- Add a question: append a row to `questions.jsonl`
- Add an estimand: append a row to `estimands.jsonl` (per `MANAGER_SPEC.md` §3.5)
- Record a sample-attribute: append a row to `sample_attributes.jsonl`
