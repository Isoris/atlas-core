# Plans (page 14)

Pre-flight research-plan review per **DYNAMIC_PANELS_SPEC §27** (`panel_plan_v1`). The UI equivalent of `dispatcher_plan_v1`: rather than "what action manifests should I queue?", it answers "what UI does my research plan need + which gates do I still have to satisfy?"

## Reads

- `02_queue/plans/index.json` — manifest listing every plan file present (mirrors `02_queue/index.json` for dispatcher manifests)
- `02_queue/plans/<plan_id>.json` — one per accepted plan, `panel_plan_v1` shape
- Falls back to `index.example.json` + the shipped example seed when no live index exists

## What you see per plan

| element | what |
|---|---|
| **goal** | the natural-language target the plan is trying to satisfy |
| **scope strip** | atlas / cohort / sample_set / candidate the plan requires |
| **summary** | n_steps / n_ready / n_blocked / n_actions_enabled + first_unblocking_action |
| **phase strip** | 4-column layout: stage → render → propose → narrate. One step card per registered panel each phase needs. Each step shows `panel_id ← from_analysis` + per-gate pass/fail pills. |
| **actions** | Accept (mark accepted in localStorage), Dismiss (toggle visibility locally), Copy JSON |

## Phase semantics (from §24 of the spec)

| phase | role |
|---|---|
| `stage` | scope_input panels needed BEFORE the analysis can run |
| `render` | primary_result + drill_down panels for the output |
| `propose` | action panels (queue manifest, dispatch follow-up) |
| `narrate` | manuscript chunks tied to this analysis |

## Gate pills

Each step's `gates_status` resolves to colored pills:
- **green `pass`** — gate satisfied
- **red `fail`** — gate not satisfied; tooltip shows `graph · node · expected_state`

This is the same discipline as page 12's yellow placeholders + page 13's dashed missing-file chips: visible failure beats invisible omission.

## What persists

- **`atlas_plan_accepted_v1`** (localStorage) — plan_id → ISO timestamp when accepted
- **`atlas_plan_dismissed_v1`** (localStorage) — plan_id → ISO timestamp when dismissed (toggle)

Accept does NOT execute the plan on its own (no runtime conductor for plans yet); it records intent. Once the conductor's full lifecycle lands (§27.4), accept will trigger the spawn loop.

## What to edit fast

- **Regenerate all plans from the live registry:**
  ```
  python3 -m toolkit_registries.relatedness.lib.plan_generator
  ```
  Walks every registered chain, infers panel_plan_v1 stage/render/propose/narrate steps from required_dimensions + produces + manuscript chunks, writes one `plan_auto_<chain>.json` per chain to `02_queue/plans/` and rewrites `index.json`. The example seed (`plan_*.example.json`) is preserved.

- Dry-run first: `--list` prints what would be written.
- Clear auto-plans: `--clear` removes everything except `*.example.*`.
- New manual plan? Drop a `panel_plan_v1` JSON under `02_queue/plans/` and re-run the generator (it rebuilds the index over every `plan_*.json` present).
- Reset acceptance state? `localStorage.removeItem('atlas_plan_accepted_v1')` in devtools.

## §refusals

1. **No execution.** Page 14 never runs an analysis or queues a manifest. Accept persists intent only.
2. **No write-back to disk.** All on-page actions are localStorage; the plan files on disk are read-only.
3. **No invented gates.** Each gate's `graph` must be one of the registered five (`vocab_graph`, `layer_graph`, `chain_graph`, `scope_graph`, `atlas_dependency_graph`) per spec §18.
