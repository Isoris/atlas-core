# vocabulary/ — controlled vocabulary for the LLM funnel

Layer 0 (domains) + Layer 1 (concepts, in per-domain banks) + Layer 2
(registry-vocab targets, declared in `maps_to_kind` / `maps_to`).
Layer 3 (live registry instances) is resolved at runtime by
`relatedness/scripts/resolve.py` and friends.

See **`../LLM_FUNNEL_SPEC.md`** for the full design.

## Files

| File | Layer | What |
|---|---|---|
| `domains.tsv`   | 0 | The controlled menu of high-level domains (one row per domain). Stage 2 picks ≤4 of these. |
| `keywords/<domain>.tsv` | 1 | One bank per domain. Each row maps a human term to a registry concept. Pinned by `keyword_bank_row_v1.schema.json`. |
| `edges.tsv`     | 1/cross | Concept ↔ concept edges across domains: aliases, is_a, requires. |

## How to add a new domain

1. Append a row to `domains.tsv` with the domain id and one-line description.
2. Create `keywords/<domain>.tsv` with the canonical 6-column header
   (`term, level, maps_to_kind, maps_to, aliases, notes`).
3. Optionally add `is_a` / `requires` edges in `edges.tsv` so the
   matcher knows how this domain relates to existing ones.

## How to add a new term

Append a row to the appropriate `keywords/<domain>.tsv` with:

- `term` — the canonical human word, lowercase preferred
- `level` — `keyword` / `concept` / `registry_entry`
- `maps_to_kind` — one of: `entity_type`, `analysis_id`, `set_filter`,
  `set_id_pattern`, `operation_type`, `metric`, `concept`
- `maps_to` — the target id / pattern
- `aliases` — comma-separated alternates (queried by the matcher)
- `notes` — free text

## Bank file format (TSV, pinned)

```
term	level	maps_to_kind	maps_to	aliases	notes
```

Empty cells are zero-length strings (NOT `NA` / `.`). All 6 columns
must be present even if empty.

## Reproducibility

Bank updates are deliberate, reviewed, and version-bumped. Per-session
corrections are NOT folded back into the banks automatically (that
would invalidate prior session JSONs that depended on the old
mapping). When a bank changes meaningfully, bump
`keyword_bank_row_v1.schema.json`'s `$id` to `_v2`.
