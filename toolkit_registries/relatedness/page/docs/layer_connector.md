# Layer Connector — Atlas Manager (page 9)

Per the screenshot spec: every page / layer / atlas shows IN (consumed) and OUT (produced) connectors. The page is the practical wiring tool — *"a few hours to click like layer to layer and connect the IN and OUT"*.

## Reads

- `01_registry/atlases.jsonl` — drives the dark-navy sidebar + global readiness cards (data-driven since PR #18)
- `01_registry/products.jsonl` — every biological-object product
- `01_registry/questions.jsonl` — the central card content
- `01_registry/layer_registry.jsonl` — backed_by_layers resolution
- `01_registry/analysis_registry.jsonl` + `analysis_results.jsonl` — producer chain
- `01_registry/panels.jsonl` + `pages.jsonl` + `hook_registry.jsonl` — Used-by edges
- `01_registry/estimands.jsonl` + `sample_attributes.jsonl` — secondary

## The four zones

1. **Sidebar** — atlases rendered from `atlases.jsonl` with live status dots
2. **Global readiness bar** — one card per atlas + 3 infra cards (Samples / Reference / Intervals)
3. **3-column workspace** — Selector + INPUTS→LAYER→OUTPUTS→USED-BY graph + Readiness Report
4. **Bottom Layer/Product table** — 8 columns including `Used by` and `Next action`

## The drawer (right side, slides in)

Tabs: **Overview / IN / OUT / Used by**. Each IN or OUT slot is clickable; **"Connect this IN/OUT to another product…"** enters connect-mode. Manual edges save to `localStorage` and export as JSON.

## What to edit fast

- Add a new atlas: append a row to `atlases.jsonl` (then tag products with `atlas: <atlas_id>`)
- Re-wire dependencies: edit `products.jsonl` `depends_on` / `valid_for` fields
- Update primary products for an atlas: edit `atlases.jsonl` `primary_products[]`
- Add a new question to an atlas: append a question with the right tag → connection map picks it up automatically

For atlases beyond this repo: paste `ATLAS_INTEGRATION_PROMPT.md` into the target atlas project's Claude session.
