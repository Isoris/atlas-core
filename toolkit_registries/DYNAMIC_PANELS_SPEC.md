# DYNAMIC_PANELS_SPEC — the UI composes itself from the registry

Status: **v0 (frozen).**  Schema version: `panel_v1`, `spawn_rule_v1`,
`layout_policy_v1`.

> The librarian resolves layer state.
> The manager classifies product readiness + estimability.
> The dispatcher proposes the next concrete action.
> **The Panel Conductor composes the UI from current state.**

The conductor is the fourth tier above the registry — and the LAST that
ever touches pixels.  It does NOT add registry entries, does NOT
execute analyses, does NOT decide scientific validity.  It picks which
**panels** to render, in which **slot**, in which **order**, based on
the current scope + registry state + chain-audit verdicts.

This preserves the §refusals from the lower tiers:
connect ≠ resolve ≠ run ≠ render.

---

## §1 The five-tier picture (updated)

```
  Registry (JSONL — librarian substrate)
      │
      ▼
  Manager (status / estimability)
      │
      ▼
  Dispatcher (proposes manifests)
      │
      ▼
  Chain Audit (one-step / multi-step / blocked tiers per chain)
      │
      ▼
  Panel Conductor (THIS SPEC) — picks panels, spawns into slots
      │
      ▼
  Pages (static skeletons with named slots — pages 1..12 today)
```

Pages stay the same — fixed URL, fixed nav, fixed top-level identity.
What changes is **what's INSIDE the page**: each page declares a set
of **slots**, the conductor decides which **panels** drop into each
slot, in what order, based on the current state.

---

## §2 What a Panel is (`panel_v1`)

A panel is the **smallest re-usable unit of UI**.  Schema:

```jsonc
{
  "panel_id":       "candidate_evidence_card",            // unique
  "schema_version": "panel_v1",
  "label":          "Candidate evidence card",
  "kind":           "card",                               // see §3
  "atlas":          "inversion_atlas",                    // for color stripe
  "data_source": {                                        // §4
    "kind":   "scope+registry",
    "scope":  ["candidate_id"],
    "reads":  ["products.jsonl", "questions.jsonl"]
  },
  "slot_affinity":  ["main", "rail-right"],               // §5
  "min_width_px":   320,
  "min_height_px":  180,
  "dismissable":    true,
  "describes":      "Per-candidate evidence summary: PCA, karyotype, relatedness, popstats, breakpoint."
}
```

The conductor never invents a panel.  Every panel is **registered**
in `01_registry/panels.jsonl`.  An unregistered `panel_id` is a
silent no-op (logged, never rendered).

### `kind` enum

| `kind`         | What it renders                                   |
|---|---|
| `card`         | A small summary block with key/value rows         |
| `table`        | A tabular view; rows from a layer or query        |
| `chart`        | A single chart (line / scatter / bar)             |
| `text`         | A markdown paragraph (e.g. a manuscript chunk)    |
| `form`         | A small input form (e.g. scope selector)          |
| `preview`      | A read-only JSON/TSV peek (truncated)             |
| `triage`       | A ranked candidate triage table                   |
| `chain`        | A chain-pipeline visualization                    |
| `bibliography` | A reference list (numbered, DOI-linked)           |
| `empty`        | An explanatory empty state (no data yet)          |

New `kind`s require a new spec version bump (`panel_v2`).

---

## §3 Where panels live — Slots

Each page declares a set of named **slots** in its HTML:

```html
<main data-slot="main"></main>
<aside data-slot="rail-right"></aside>
<section data-slot="footer-row"></section>
```

A slot has zero or more panels at any moment.  Slot inventory per
page is recorded in `01_registry/pages.jsonl` (extension of the
existing pages row):

```jsonc
{
  "page_id": "action",
  "slots": [
    {"slot_id": "main",       "label": "Primary",   "max_panels": 8},
    {"slot_id": "rail-right", "label": "Side rail", "max_panels": 4},
    {"slot_id": "footer-row", "label": "Footer",    "max_panels": 2}
  ]
}
```

Slots are **structural** — the page owns them.  The conductor only
fills them; it never creates new slots.

---

## §4 What a panel reads — Data Sources

Each panel declares its `data_source.kind`:

| `kind`             | Resolves from |
|---|---|
| `scope`            | `window.getScope()` — atlas / sample_set / interval_set / candidate_id |
| `registry`         | one or more registry JSONL files (`analysis_registry`, `module_registry`, …) |
| `layer`            | the data behind a specific `layer_id` (file or in-memory) |
| `analysis_result`  | the latest run's output for a given `analysis_id` |
| `chain_audit`      | the chain-audit verdict for a given chain |
| `manuscript_chunk` | a row from `manuscript_chunks.jsonl` (with placeholder hydration) |
| `scope+registry`   | scope keys + registry rows; the most common compound |

Panels NEVER mutate. A panel that needs a mutation (queue a manifest,
edit a placeholder) calls into a **shared action API** — never writes
JSONL directly.

---

## §5 Slot Affinity

A panel's `slot_affinity` is an **ordered preference list** — the
conductor tries each slot in order, falling back to the next if the
preferred slot is full.

```
candidate_evidence_card.slot_affinity = ["main", "rail-right"]
```

If `main` has room → drop there.  If full and `rail-right` has room →
drop there.  If both full → either evict the lowest-priority panel
already in `main` (see §7) or hold the new panel queued.

Affinity is a preference, not a binding.  A page that lacks any of a
panel's preferred slots silently won't host that panel.  This is by
design — a page-level skeleton override always wins.

---

## §6 When panels spawn — Spawn Rules (`spawn_rule_v1`)

Spawn rules live in `01_registry/spawn_rules.jsonl`.  Each row is a
**declarative IF/THEN**:

```jsonc
{
  "rule_id":  "candidate_picked_spawn_evidence",
  "schema_version": "spawn_rule_v1",
  "when": {
    "scope":     {"candidate_id": "*"},        // any non-empty candidate
    "page":      ["candidate_review", "action", "workspace_health"],
    "registry":  {"products_for_atlas": "*"}
  },
  "then": {
    "spawn": [
      {"panel_id": "candidate_evidence_card",  "priority": 80},
      {"panel_id": "candidate_chain_readiness","priority": 70},
      {"panel_id": "candidate_manuscript_chunks","priority": 60}
    ]
  },
  "describes": "When the scope ribbon names a candidate, drop its evidence card + chain readiness + manuscript chunks into the page."
}
```

### The `when` clause — match conditions

| Key | Matches against | Form |
|---|---|---|
| `scope`           | `getScope()` keys           | `{key: "*"}` (any non-empty) or `{key: "literal-value"}` |
| `page`            | current page_id             | array of page_ids |
| `registry`        | live registry counts        | named predicates (e.g. `chain_audit:has_one_step_chains`) |
| `chain_audit`     | per-chain verdict           | `{chain_id: "*", tier: ["one", "multi"]}` |
| `manuscript`      | manuscript_chunks selection | `{has_chunks: true}` |

Predicates are NAMED + REGISTERED (no eval, no regex of user input).
New predicates require a `spawn_rule_v2` bump.

### The `then` clause — what to spawn

- `spawn`: array of `{panel_id, priority}`.  Higher priority wins
  contested slots.
- `dismiss`: optional inverse — remove these panel_ids if present.
  Useful for scope-narrowing rules ("when no candidate is picked,
  dismiss `candidate_evidence_card`").

A rule's `then` is **declarative state**, not imperative.  The
conductor diffs the desired state against the current state and emits
spawn/dismiss events.  Idempotent re-evaluation is the norm.

---

## §7 Conductor lifecycle

```
  scope_change | page_load | registry_reload | chain_audit_refresh
                        │
                        ▼
  ┌─────────────────────────────────────┐
  │  1. Evaluate every spawn_rule      │
  │     against current state           │
  └─────────────────────────────────────┘
                        │
                        ▼
  ┌─────────────────────────────────────┐
  │  2. Compute DESIRED panel set       │
  │     (de-dup by panel_id;            │
  │      max(priority) wins ties)       │
  └─────────────────────────────────────┘
                        │
                        ▼
  ┌─────────────────────────────────────┐
  │  3. Diff vs CURRENT panel set       │
  │     → spawn_list + dismiss_list     │
  └─────────────────────────────────────┘
                        │
                        ▼
  ┌─────────────────────────────────────┐
  │  4. For each spawn: place into      │
  │     first-available slot_affinity   │
  │     (evict lowest-priority panel    │
  │      already there if slot full)    │
  └─────────────────────────────────────┘
                        │
                        ▼
  ┌─────────────────────────────────────┐
  │  5. Hydrate each new panel          │
  │     (load its data_source)          │
  └─────────────────────────────────────┘
                        │
                        ▼
  ┌─────────────────────────────────────┐
  │  6. Persist                         │
  │     (sticky panels + user dismissals│
  │      → localStorage)                │
  └─────────────────────────────────────┘
```

The lifecycle is **the same** for every trigger.  No special-case
codepaths for scope change vs page load — the conductor re-evaluates
the world and diffs.

---

## §8 User overrides (sticky)

A panel that the user manually **dismisses** is recorded in
`localStorage:atlas_panel_dismissals_v1` and the conductor will **not
re-spawn it on the same scope** until the user explicitly unblocks it
(via a "Restore all panels" affordance on each page).

A panel that the user manually **pins** (`atlas_panel_pins_v1`)
survives scope changes that would normally dismiss it — useful for
keeping a manuscript chunk on screen while the candidate ribbon
changes.

Per-panel placement (which slot, ordering within a slot) can be
dragged by the user; the override is stored as
`{page_id, panel_id, slot_id, idx}` in
`atlas_panel_placement_v1`.  Conductor honors the override unless the
panel is later dismissed.

---

## §9 Layout Policy (`layout_policy_v1`)

A `layout_policy_v1` row says **how** to arrange panels within a slot.
Default policy is `priority_desc` (higher priority first).  Other
policies:

| `policy_id`        | Ordering rule |
|---|---|
| `priority_desc`    | default; highest `priority` first |
| `atlas_grouped`    | group by panel.atlas (in atlas-card order from `atlases.jsonl`), within group sort by priority |
| `chain_order`      | when slot is hosting chain-pipeline panels, sort them by chain step index |
| `temporal_recent`  | most-recently-spawned first (good for `notification` slots) |

Each slot in `pages.jsonl` may declare its own `layout_policy`
(default: `priority_desc`).

---

## §10 Worked examples

### Example A — user picks a candidate in the scope ribbon

1. `scope.candidate_id` changes from "" → `inv_LG28_INV_001`.
2. Conductor re-evaluates all rules.
3. Three rules fire:
   - `candidate_picked_spawn_evidence` (§6 example)
   - `candidate_with_karyotype_calls_spawn_burden` (only if a `karyotype_calls` layer exists for that candidate)
   - `dismiss_global_summary` (the global summary panel is dismissed because a candidate is now in focus)
4. Conductor computes diff:
   - SPAWN: `candidate_evidence_card` (prio 80), `candidate_chain_readiness` (70), `candidate_manuscript_chunks` (60), `mendelian_burden_card` (75)
   - DISMISS: `global_evidence_summary`
5. Slots `main` and `rail-right` are filled; `candidate_manuscript_chunks` (lowest prio) goes to `rail-right` since `main` is full.
6. Each panel hydrates (`candidate_evidence_card` reads `products.jsonl + getScope().candidate_id`, etc.).

### Example B — chain becomes one-step on a new dataset

1. A producer's `last_run_status` flips to `success` in `module_registry.jsonl`.
2. Chain audit re-runs → `inversion_groupwise_popstats` was `multi-step`, now `one-step`.
3. Rule `chain_one_step_propose_action` matches:
   ```
   when:  chain_audit: {chain_id: "*", tier: ["one"]}
   then:  spawn [{panel_id: "next_action_proposal", priority: 90}]
   ```
4. `next_action_proposal` lands on page 2 (Action) — it lists the cheapest unblocking analysis and a one-click "queue manifest" affordance.
5. When the user queues the manifest (dispatcher writes `02_queue/<act>.json`), the chain's tier may drop further on the next refresh, and the proposal panel updates in-place (same `panel_id`).

### Example C — user opens page 12 (Manuscript) with no selection

1. Page loads; `getScope().atlas` is "all", no candidate.
2. Rule `manuscript_default_panels` fires:
   ```
   when:  page: ["manuscript"], manuscript: {has_chunks: false}
   then:  spawn [
     {panel_id: "manuscript_picker",       priority: 90, slot: "main"},
     {panel_id: "manuscript_preview",      priority: 80, slot: "rail-right"},
     {panel_id: "bibliography_preview",    priority: 60, slot: "footer-row"}
   ]
   ```
3. User picks two chunks → manuscript selection changes → `manuscript: {has_chunks: true}` predicate now true → rule `manuscript_chunks_picked` adds `chunk_editor` panels (one per selected chunk) to `main`.

---

## §11 The §refusals

1. **No execution.** A panel never runs an analysis.  Panels can
   *propose* a manifest via the shared action API; the dispatcher
   writes it to `02_queue/`; an external runner picks it up.
2. **No registry writes.** Panels are read-only over JSONL.  Mutations
   go through the existing librarian / dispatcher tier.
3. **No invented panels.** Every `panel_id` is registered in
   `panels.jsonl`.  An unknown panel id is a no-op (logged), never
   silently rendered as a fallback shape.
4. **No invented spawn predicates.** The `when` clause uses NAMED
   registered predicates only.  No `eval`, no user-string regex.
5. **No cross-cohort spawn.** A panel scoped to one cohort is never
   auto-spawned on a page whose scope is a different cohort.  The
   atlas tag and the scope atlas must match (or be "all").
6. **No autospawn from natural-language LLM input.** Until the LLM
   funnel (page 1) emits structured `spawn_rule_v1` outputs (which it
   does not yet — that's deferred), the LLM cannot directly trigger
   panel spawns.  It can only emit `funnel_stage_*` artifacts that the
   conductor reads as inputs.
7. **User overrides win.** A user dismissal beats any auto-spawn for
   the duration of the scope.  A user pin beats any auto-dismiss until
   manually unpinned.
8. **No silent layout drift.** Panel placement is fully determined by
   the rule set + the four override stores (dismissals, pins,
   placements, layout-policy choices) — replayable.

---

## §12 Files this spec adds (when v0 ships)

| File | Schema | Role |
|---|---|---|
| `01_registry/panels.jsonl`         | `panel_v1`         | every renderable panel |
| `01_registry/spawn_rules.jsonl`    | `spawn_rule_v1`    | when each panel spawns |
| `01_registry/layout_policies.jsonl`| `layout_policy_v1` | how panels arrange in a slot |
| `01_registry/pages.jsonl` (extended)| existing + slots[]| slot inventory per page |
| `lib/conductor.py` (later PR)      | —                  | the rule engine (server-side validation + dry-run) |
| `page/conductor.js` (later PR)     | —                  | the in-browser engine that diffs + renders |

Spec-only PR introduces NONE of these as live runtime — it freezes the
contracts.  Subsequent PRs add the rows (then the runtime).

---

## §13 The vertical slice to ship first

A minimum-viable conductor is **one rule + one panel** that proves the
diff/spawn/hydrate loop:

```
rule:  candidate_picked_spawn_evidence
panel: candidate_evidence_card
slot:  main on pages [candidate_review, action, workspace_health]
```

If that works end-to-end (scope change → spawn → hydrate → user
dismiss → no re-spawn on same scope), every subsequent panel is just a
JSONL row + a small renderer.  The architectural risk is the diff
engine, not the panel count.

---

## §14 What this is NOT

- **Not a layout framework.** Pages still own their HTML skeleton.
  The conductor only fills declared slots; it does not move the slots.
- **Not a workflow engine.** Workflow / chain orchestration lives in
  the dispatcher.  The conductor only *renders* what the dispatcher /
  chain audit already produce.
- **Not a notebook.** Panels are not arbitrary scratch code — they are
  registered, typed, idempotent renderers.  A user that needs custom
  scratch space uses the existing `text` panel kind, which is just a
  markdown body.
- **Not personalized.** The rule set is shared.  Per-user state lives
  ONLY in the four localStorage override stores.  No server-side user
  profile.

---

## §15 Relationship to existing specs

| Spec | Where it ends | Where the conductor begins |
|---|---|---|
| `LAYER_GRAPH_BUILDER_SPEC.md` | librarian resolves layer status | conductor reads `layer.status` to decide panel availability |
| `MANAGER_SPEC.md`             | manager classifies product readiness | conductor reads `product.status` for the `candidate_evidence_card` data |
| `DISPATCHER_SPEC.md`          | dispatcher writes `02_queue/<act>.json` | `next_action_proposal` panel renders the queued manifest; doesn't write |
| `ADAPTER_CONTRACT.md`         | adapter declares meta + run + preview | the `preview()` return value is a `panel_v1` payload (the renderable view of an analysis result) |
| `CROSS_SPECIES_BREAKPOINTS_WORKFLOW.md` | atlas-side bundles | each chain in the workflow can declare its own `chain` panel for `chain_pipeline_panel` rendering |

The conductor does NOT replace these tiers.  It composes them.

---

## §16 What's deferred

- **Conductor runtime** — `lib/conductor.py` + `page/conductor.js`.
  Spec-first; runtime PR later.
- **Panel registry seed** — the initial ~30 panels (one per atlas's
  marquee view, plus generic `table` / `chart` / `text` / `chain`
  primitives).  Ship in a follow-up "panel-seed" PR per atlas.
- **LLM-driven spawn** — page 1's LLM funnel emits structured action
  manifests today; once it also emits structured `spawn_rule_v1`
  outputs (deferred), the conductor can react to natural-language
  triggers ("show me LG28's Mendelian burden") with a deterministic
  spawn (not an LLM-decided rendering).
- **Per-user telemetry** — which panels spawn / dismiss most often.
  Useful for retiring noisy rules; deferred until there are >50 rules.
- **Cross-page panel migration** — a panel pinned on page A surfacing
  on page B when the user navigates.  Deferred; pin-per-page is the v0
  default.

---

_End of DYNAMIC_PANELS_SPEC.md (v0)._
