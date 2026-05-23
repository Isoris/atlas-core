# Manuscript (page 12)

A blocnotes for assembling manuscript text from registered modules and chains. Each chunk is a generic paragraph template (markdown) with `{{placeholder}}` slots; pick the chunks you want, edit the body, fill in the placeholders, and the manuscript drops out on the right.

## Reads

- `01_registry/manuscript_chunks.jsonl` — the seeded templates (one row per chunk)
- `01_registry/references.jsonl` — bibliography with DOI / URL (referenced by `ref_id`)
- `01_registry/atlases.jsonl` — atlas badge colors
- `01_registry/module_registry.jsonl` — version / n_samples / etc. for placeholders sourced from `module`
- `01_registry/analysis_registry.jsonl` — labels / descriptions / version for placeholders sourced from `registry`

## Layout

| pane | what |
|---|---|
| **left (picker)**   | tabs for `methods / results / discussion`; list of chunks with atlas badge + checkbox; pick the ones you want |
| **middle (cards)**  | one editable card per selected chunk: textarea for the template body, table of placeholders (name / value / source), reorder + delete buttons |
| **right (preview)** | live manuscript rendered as you edit. Unfilled `{{slots}}` are highlighted yellow. Copy markdown / Download .md / Reset overrides |

## Placeholder sources

Each placeholder in `manuscript_chunks.jsonl` declares where its value comes from:

| `source`               | resolves from |
|---|---|
| `literal`              | `default` field in the chunk |
| `scope`                | `window.getScope()` — atlas / sample_set / interval_set / candidate_id |
| `scope_or_literal`     | scope first, falls back to `default` |
| `module`               | `module_registry[module_name][path]` (e.g. version, n_samples) |
| `registry`             | `analysis_registry[analysis_id][path]` (label, description, analysis_version) |
| user typed inline      | always wins, persists in `localStorage` as `atlas_manuscript_overrides_v1` |

Set the scope ribbon to a real candidate / sample_set and `{{candidate_id}}` chunks fill in automatically.

## References / DOI

Citations are written in the template body as `[@RefId]` (Pandoc-style) — they expand to numbered superscript links in the preview, in order of first appearance across all selected chunks. The bibliography is appended automatically at the end of the manuscript.

| where references come from | how |
|---|---|
| Declared on the chunk row | `"references": ["Manichaikul2010", "Hudson1992"]` in `manuscript_chunks.jsonl`. These always appear, even if the body doesn't cite them inline (trailing citation before the final period). |
| Inline in the template body | Any `[@RefId]` in the text; auto-detected and indexed. |
| Added on the page | `+ ref` button on each chunk card — persists in `localStorage` as part of the per-chunk override. |
| Resolved from | `references.jsonl` (citation + DOI + URL). Missing keys render with a yellow "not in references.jsonl" warning. |

DOI links resolve to `https://doi.org/<doi>`; if a row lacks a DOI, the `url` field is used instead.

## What persists

- **selection + order**: `atlas_manuscript_selection_v1` (localStorage)
- **per-chunk template + placeholder edits**: `atlas_manuscript_overrides_v1` (localStorage)
- **ship templates** (the seed): `manuscript_chunks.jsonl` (in git)

Editing the body of a chunk on page 12 does NOT touch `manuscript_chunks.jsonl` — your edits live in localStorage only. If you want a chunk edit shared with the team, update the JSONL row.

## What to edit fast

- New paragraph for a module? Add a row to `manuscript_chunks.jsonl`:
  ```json
  {"chunk_id":"methods.<id>","section":"methods","atlas":"<atlas_id>",
   "analysis_id":"<analysis_id>","label":"<short label>",
   "template":"... {{placeholder}} [@RefId] ...","placeholders":{...},
   "references":["RefId"]}
  ```
- New placeholder on an existing chunk? Either edit the JSONL `placeholders` map, or use the `+ add placeholder` button on the card (override-only, won't ship).
- New reference? Add a row to `references.jsonl`:
  ```json
  {"ref_id":"YourKey2024","citation":"Author A, ... (2024) ...","doi":"10.xxx/xxx","url":"https://doi.org/10.xxx/xxx","tags":["..."]}
  ```
  Then cite it inline with `[@YourKey2024]` or attach it to a chunk's `references` array.
- Want a placeholder to autofill from scope? Set `"source":"scope","path":"candidate_id"`.

## §refusals

1. **No execution.** Page 12 never runs an analysis. It composes text from registered chunks. To run the underlying analyses, use page 11 (Queue) or the dispatcher.
2. **No write-back to JSONL.** All on-page edits are localStorage only. Promote to JSONL by hand if you want the team to inherit them.
3. **Unfilled placeholders stay yellow.** The preview highlights `{{placeholder}}` slots that resolved to nothing — never silently drops them. Either fill the value or add a `default`.
