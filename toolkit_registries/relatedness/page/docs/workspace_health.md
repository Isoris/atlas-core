# Workspace Health (page 10)

One-glance overview of every registered atlas. Surfaces the **bottlenecks** — the missing biological objects that block the most downstream products / questions / estimands — and a workspace-wide readiness ladder.

## Reads

- `01_registry/atlases.jsonl` — the atlas cards + their roll-ups
- `01_registry/products.jsonl` — bottleneck ranking + KPI counts
- `01_registry/questions.jsonl` — questions-closest-to-ready table
- `01_registry/estimands.jsonl` + `sample_attributes.jsonl` — estimability summary
- `01_registry/layer_registry.jsonl` + `analysis_registry.jsonl` + `analysis_results.jsonl` — the librarian's substrate

## What the page surfaces

| Pane | What it computes |
|---|---|
| **KPI row**         | total biological objects + questions + estimands + atlases + bottleneck count |
| **Atlases**         | per-atlas roll-up: # products ready / partial / missing + lead-question state + depends-on chain |
| **Top bottlenecks** | top 10 missing products ranked by *downstream fan-out* (how many products + questions + estimands depend on this product) |
| **Closest to ready**| questions sorted by `n_ready / n_total` |
| **Estimability**    | every question with at least one estimand, sorted by `fully_estimable > partial > needs_extra_data > limited` |

## The bottleneck score

```
downstreamFanout(product_id) =
    count of products with depends_on containing product_id
  + count of questions with requires.product_id == product_id
  + count of estimands with preconditions.product_id == product_id
```

Click a row → opens the relevant detail page (readiness for products / questions, layer_connector for atlases).

## What to edit fast

- The five-card KPI row reads live from JSONL — no edits needed; just add rows to the underlying registries
- Want a new atlas card? Add to `atlases.jsonl` + tag at least one product with `atlas: <atlas_id>`
- Want to change the ranking weights? Edit `downstreamFanout()` in this page's inline script

This is **read-only**. Per `MANAGER_SPEC.md`: status is recomputed live on every load.

## Universal search (every page)

Hit `Cmd/Ctrl+K` from any page to open the universal search modal. Type any product / question / layer / atlas / estimand / hook id — Enter jumps to the right page with the item pre-selected (or flashed). The "🔎 Search" floating button does the same.
