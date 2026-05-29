# DYNAMIC_PANELS_SPEC — the UI composes itself from the registry

Status: **v0.2 (frozen contracts).**
Schema versions: `panel_v1`, `spawn_rule_v1`, `layout_policy_v1`,
`fluidity_v1`, `graph_gate_v1`, `panel_event_v1`,
`panel_requirement_v1` (added §24), `panel_plan_v1` (added §27).

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

The 10 registered panel kinds, mirrored across both specs:

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

The **canonical live catalogue** — including the typical
`data_source.kind` for each kind, registered example panels, and
the 3-step promotion process for adding a new kind — lives in
[`ADDON_SPEC.md`](ADDON_SPEC.md) §2. This table is the kind-enum
contract; ADDON_SPEC §2 is the operator's reference. Both must
agree; when adding a new kind, update ADDON_SPEC §2 first (with
the worked example), then mirror the row here. **No `panel_v2`
spec bump is required** — adding a kind is additive within
`panel_v1` so long as it lands in both tables and a renderer
exists in `page/conductor.js`'s `RENDERERS` dispatch map.

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

---

## §17 Fluidity & resize policy (`fluidity_v1`)

Panels are **size-class adaptive**, not pixel-fixed. Every `panel_v1`
row carries a `fluidity` block:

```jsonc
"fluidity": {
  "size_classes":  ["compact", "comfortable", "expanded"],
  "min_width_px":   { "compact": 220, "comfortable": 320, "expanded": 520 },
  "preferred_px":   { "compact": 260, "comfortable": 380, "expanded": 720 },
  "max_width_px":   { "compact": 320, "comfortable": 520, "expanded": 9999 },
  "min_height_px":  120,
  "collapsible":    true,         // can fold to a single-line summary
  "tearoff":        false,        // can leave its slot and float as overlay
  "reflow_policy":  "soft_wrap"   // soft_wrap | hard_wrap | tabify | dismiss
}
```

### §17.1 Breakpoint adaptation

The conductor watches viewport + slot width (debounced 120 ms) and
picks the **largest** size_class a panel fits into. If the slot
narrows below `min_width_px.compact`, the conductor consults
`reflow_policy`:

| `reflow_policy` | What happens at sub-compact width |
|---|---|
| `soft_wrap` | Panel collapses to a single-line summary (label + key stat); click expands |
| `hard_wrap` | Panel jumps to the next slot down (if any) |
| `tabify`    | Panel joins a `tab_group` panel sharing the same slot; user picks which tab is active |
| `dismiss`   | Panel is auto-dismissed (logged); re-spawns when width recovers |

Reflow is **never** a re-render of the panel from scratch — the same
`panel_id` instance is preserved across size_class transitions so
in-panel state (form input, scroll position, selected row) survives.

### §17.2 Slot flow policy

Each slot in `pages.jsonl` declares a `flow_policy`:

| `flow_policy` | Arrangement |
|---|---|
| `row`     | Panels side-by-side, wrap to next row at slot-width overflow |
| `column`  | Panels stacked top-to-bottom (default for rails) |
| `grid`    | CSS grid with `auto-fill, minmax(min_width_px.compact, 1fr)` |
| `tabs`    | Only one panel visible; tab strip lists the rest |
| `stack`   | Z-axis overlay; useful for modals / takeovers |

The slot's `flow_policy` and each panel's `reflow_policy` compose:
the slot owns the *between*-panel rules, the panel owns the
*within*-panel adaptation.

### §17.3 Stable invariants

Even under resize storms, three invariants hold:

1. **Identity preserved** — a panel keeps its `panel_id` across all
   reflows; in-panel state survives.
2. **Order preserved** — a slot's panel ordering doesn't shuffle on
   resize. New panels can land; existing panels stay in their relative
   position.
3. **No reflow loops** — the conductor's diff loop is single-pass per
   trigger; a resize that causes one reflow does not retrigger another
   resize event. (Achieved by computing the size_class **after** the
   reflow has settled, against the *post-reflow* slot width.)

---

## §18 Multi-graph gating (`graph_gate_v1`)

The conductor reasons over **five registered graphs**. Each graph is a
precondition layer that gates which panels can spawn and which actions
panels can offer. A spawn_rule or an in-panel action can declare
`gates: [...]` — ALL gates must be satisfied for the rule to fire / the
action to enable.

### §18.1 The five graphs (v0.1)

| `graph_id`              | Nodes | Edges | Built from |
|---|---|---|---|
| `vocab_graph`           | domains / concepts / registry-vocab targets / instances (4-layer; from `LLM_FUNNEL_SPEC.md`) | `alias / is_a / requires / belongs_to` | `vocabulary/*.tsv` + `vocabulary/edges.tsv` |
| `layer_graph`           | layer_ids | `consumed_by / produced_by` | `layer_registry.jsonl` + `analysis_modes.jsonl` (`required_dimensions` / `produces`) |
| `chain_graph`           | analysis_ids flagged as chains | required → producer edges | derived from chain audit (§14 of MANAGER_SPEC) |
| `scope_graph`           | atlas → cohort → sample_set → interval_set → candidate_id | `contains / scoped_to` | `atlases.jsonl` + `sample_sets.jsonl` + `interval_sets.jsonl` + scope ribbon |
| `atlas_dependency_graph`| atlas_ids | `depends_on_atlases` | `atlases.jsonl` |

Graphs are **declared**, not derived ad-hoc — each has a
`01_registry/graphs/<graph_id>.json` cache (rebuilt by a librarian
sub-task on registry reload). The conductor never walks the underlying
JSONL itself; it walks the cached graphs.

### §18.2 The `graph_gate_v1` shape

```jsonc
"gates": [
  {
    "graph":    "layer_graph",
    "node":     "karyotype_calls",
    "state":    "ready",          // ready | producer_not_run | no_producer
    "describes":"don't spawn the burden panel until karyotype calls exist"
  },
  {
    "graph":    "vocab_graph",
    "level":    "concept",        // domain | concept | registry-vocab | instance
    "any_of":   ["mendelian", "inheritance", "burden"],
    "describes":"only when the user has activated an inheritance-flavored concept on page 1"
  },
  {
    "graph":    "scope_graph",
    "path":     "atlas/cohort/candidate_id",
    "state":    "all_set",
    "describes":"a fully-specified scope chain"
  },
  {
    "graph":    "chain_graph",
    "node":     "inversion_groupwise_popstats",
    "tier":     ["one", "ready"],
    "describes":"chain is at most one step from running"
  },
  {
    "graph":    "atlas_dependency_graph",
    "from":     "evolution_atlas",
    "to":       "cross_species_atlas",
    "state":    "satisfied"
  }
]
```

### §18.3 Gate evaluator semantics

- All gates are AND-ed. No `or:` at gate level; use repeated rules for
  alternatives.
- A gate over a graph the conductor does NOT know is a **hard fail**
  (logged, the rule does not fire). No silent pass-through.
- Gate evaluation is **pure**: same graph state + same gate spec →
  same verdict. No randomness, no time-dependent predicates.
- Gates can be **negated** by appending `"negate": true` (rare; reserved
  for explicit dismiss rules).

### §18.4 Why graph gating, not free predicates

Earlier (§6.1) the `when` clause used named registered predicates.
Multi-graph gating is the **typed** evolution of that pattern: instead
of opaque predicate names like `has_one_step_chains`, gates name a
graph + node + expected state. The conductor can show the user
*exactly* which gate failed and which graph said so — a debuggable
spawn decision, not a black-box yes/no.

---

## §19 Event triggers & action gating (`panel_event_v1`)

The conductor's diff loop is driven by a fixed set of events. Each
event is typed; no `kind: "other"`, no free-form payload.

### §19.1 The v0.1 event catalogue

| `event_kind`              | Emitted by | Payload |
|---|---|---|
| `scope_change`            | scope ribbon | `{from, to, changed_keys[]}` |
| `page_load`               | page chrome | `{page_id}` |
| `registry_reload`         | registry watcher | `{files[], registry_version}` |
| `chain_audit_refresh`     | chain audit | `{summary, per_chain_tier{}}` |
| `vocab_concept_picked`    | LLM funnel stage 3 | `{level, concept_ids[], domain_ids[]}` |
| `goal_set`                | LLM funnel stage 1 | `{goal, targets[], exclusions[]}` |
| `manifest_ready`          | LLM funnel stage 5 | `{action_id, manifest}` |
| `analysis_proposed`       | dispatcher | `{action_id, analysis_id, expected_outputs[]}` |
| `analysis_started`        | runner | `{action_id, started_at}` |
| `analysis_succeeded`      | runner | `{action_id, produced_layers[]}` |
| `analysis_failed`         | runner | `{action_id, reason, retryable}` |
| `layer_landed`            | librarian | `{layer_id, registered_at}` |
| `user_dismissed_panel`    | UI | `{panel_id, scope_snapshot}` |
| `user_pinned_panel`       | UI | `{panel_id, scope_snapshot}` |
| `resize`                  | page chrome | `{viewport_px, per_slot_px{}}` |

New event_kinds require a `panel_event_v2` bump.

### §19.2 How events feed the diff loop

```
event → conductor.handle(event)
            │
            ▼
        re-evaluate ALL spawn_rules
            │
            ▼
        compute desired panel set
            │
            ▼
        diff vs current → spawn / dismiss / reflow
```

The conductor never does anything event-specific in `handle()`. Every
event takes the same path: **mark state dirty, re-evaluate rules**.
This guarantees that a rule that *could* react to event X but also to
event Y will react identically to both — no "rule registered for
event_kind" coupling.

### §19.3 Actions gated on graphs

A `panel_v1` row can declare `actions: [...]` — the set of buttons /
menu items the panel offers. Each action carries its own gates:

```jsonc
"actions": [
  {
    "action_id": "queue_chain",
    "label":     "Queue chain manifest",
    "kind":      "dispatch",
    "gates": [
      { "graph": "chain_graph",
        "node":  "{{this_panel.chain_id}}",
        "tier":  ["one", "ready"] },
      { "graph": "scope_graph",
        "path":  "atlas/cohort",
        "state": "all_set" }
    ],
    "describes": "Enabled only when the chain is one-step-or-ready AND a cohort is locked in the scope."
  },
  {
    "action_id": "copy_to_manuscript",
    "label":     "Copy to manuscript chunk",
    "kind":      "local",
    "gates": [
      { "graph": "vocab_graph",
        "level": "concept",
        "any_of": ["results", "interpretation", "burden"] }
    ]
  }
]
```

Actions render in all three states:

| State | Render |
|---|---|
| Allowed (all gates pass) | clickable button |
| Blocked (≥1 gate fails)  | grayed button + tooltip: "blocked by gate `<graph>:<node>` (current state: `<state>`)" |
| Hidden                   | only when the `kind` itself isn't supported on this page (rare) |

The conductor NEVER silently strips a blocked action — the user must
be able to see *what is possible in principle*, and *why it isn't
available right now*. This is the same discipline as the unfilled
manuscript placeholder rendering yellow on page 12: visible failure
beats invisible omission.

### §19.4 Conditional spawn = gate at rule level + gate at action level

The two-level gating is intentional:

- **Rule-level gates** decide IF a panel spawns at all.
- **Action-level gates** decide WHICH buttons the panel offers once it's
  spawned.

So a panel can spawn (because the chain is registered) yet present a
disabled "Queue manifest" button (because the chain is multi-step,
not one-step). The user sees the panel, understands the gap, can
remediate (run a producer) and watches the button enable.

---

## §20 LLM funnel integration (page 1 → conductor)

The page-1 funnel (specified in `LLM_FUNNEL_SPEC.md`) has 5 stages.
Each emits a typed artifact; the conductor consumes those artifacts via
named events (§19.1), never via free-text.

### §20.1 Per-stage event map

| Funnel stage | Output | Event the conductor receives |
|---|---|---|
| 1. Decompose          | `funnel_stage_1_decomposition`  | `goal_set`               |
| 2. Domain selection   | `funnel_stage_2_domain_selection` | `vocab_concept_picked` at `level: domain` |
| 3. Keyword mapping    | `funnel_stage_3_keyword_mapping` | `vocab_concept_picked` at `level: concept` + at `level: registry-vocab` |
| 4. Refinement Q&A     | `funnel_stage_4_refinement_*`   | `scope_change` (proposed scope edits) |
| 5. Resolution         | `funnel_stage_5_contract_resolution` | `manifest_ready` |

### §20.2 Multi-level vocabulary gating in practice

The vocab_graph (§18.1) has four levels. The conductor uses level as a
**resolution filter** for spawn rules — a rule that only makes sense
once the user has narrowed to a specific registry-vocab term should
gate at `level: registry-vocab`, not at `level: domain`.

Example progression for the question *"Does this LG28 inversion
follow Mendelian inheritance?"*:

```
Stage 1 → goal_set { targets:[LG28, inversion candidate], goal: validation }
   ↓
Stage 2 → vocab_concept_picked { level: domain,
                                  domain_ids: [inheritance, structural_variation] }
   ↓ Conductor: rules gated at level: domain may fire
   ↓ → Spawns: inheritance_domain_overview_card
              structural_variation_domain_overview_card
   ↓
Stage 3 → vocab_concept_picked { level: concept,
                                  concept_ids: [mendelian, karyotype, inversion_candidate] }
   ↓ Conductor: rules gated at level: concept may now fire
   ↓ → Spawns: candidate_evidence_card (was waiting on this concept)
              chain_readiness_panel filtered to inheritance chains
   ↓ vocab_concept_picked { level: registry-vocab,
                             concepts: [analysis_id:mendelian,
                                        entity_type:inversion_candidate,
                                        set_id_pattern:*LG28*] }
   ↓ Conductor: rules gated at level: registry-vocab may now fire
   ↓ → Spawns: mendelian_burden_card (needs analysis_id:mendelian binding)
              hpp_kbc_crosscheck_card (needs entity_type:inversion_candidate)
   ↓
Stage 4 → scope_change { candidate_id: inv_LG28_INV_001 }
   ↓ Conductor: scope_graph fully satisfied for the candidate path
   ↓ → existing panels re-hydrate with the locked candidate
   ↓ → "Queue manifest" actions on chain panels become enabled
       (chain_graph + scope_graph gates both pass)
   ↓
Stage 5 → manifest_ready { action_id, manifest }
   ↓ → Spawns: manifest_review_card (priority 95, slot:main, takeover)
   ↓ → Shows the dispatcher proposal; user reviews → confirms → dispatch
```

Every spawn here is the conductor reacting to a typed event against
typed gates against typed graphs. The LLM **never** chooses panels.
It chooses **vocabulary**; the vocab choice activates gate nodes;
gate-passing rules fire deterministic spawns.

### §20.3 Why this preserves the §refusals

The LLM is, in this architecture:

- a **classifier** (free text → registered vocab nodes)
- a **dialogue manager** (refinement Q&A in stage 4)
- a **renderer** (the final manuscript-sentence paraphrase in stage 5,
  if exposed)

The LLM is NOT:

- a panel chooser
- a rule writer
- an action runner
- a vocabulary inventor (stage 3 maps to existing nodes; unknown
  free-text goes to a `low_confidence` bucket and triggers stage-4
  Q&A, not a registry write)

This is the same discipline at the UI tier as the
`LLM_FUNNEL_SPEC.md` §9 refusals at the funnel tier: the LLM proposes,
deterministic registries dispose.

---

## §21 What §17–§20 add to the §11 refusals

Carried + extended:

9. **No reflow-loop instability.** §17.3 invariants hold; resize never
   destabilizes the diff loop.
10. **No untyped events.** Every `panel_event_v1` event has a fixed
    schema in §19.1. Anything outside the catalogue is dropped, logged.
11. **No unnamed graphs in gates.** §18.3: a gate over an unknown
    graph is a hard fail. The five graphs in §18.1 are the v0.1
    universe; new ones require a `graph_gate_v2` bump.
12. **No silently-stripped actions.** §19.3: blocked actions render
    as disabled with a tooltip naming the failed gate. The user
    always sees what is possible in principle.
13. **No LLM-driven rendering.** §20.3: the LLM picks vocabulary; the
    vocab activates graph nodes; graph gates pass; rules fire; panels
    spawn. Four indirections between free text and any pixel.

---

## §22 Files added in v0.1 (still spec-only)

| File | Schema | Role |
|---|---|---|
| `01_registry/graphs/vocab_graph.json`            | derived cache | nodes + edges from `vocabulary/*.tsv` |
| `01_registry/graphs/layer_graph.json`            | derived cache | from `layer_registry.jsonl` + `analysis_modes.jsonl` |
| `01_registry/graphs/chain_graph.json`            | derived cache | from chain audit |
| `01_registry/graphs/scope_graph.json`            | derived cache | from atlases + sample_sets + interval_sets |
| `01_registry/graphs/atlas_dependency_graph.json` | derived cache | from `atlases.jsonl` |
| `01_registry/events.example.jsonl`               | `panel_event_v1` examples | one valid event per kind, for tests |

All caches are produced by a librarian sub-task on registry reload —
they're not authored by hand. The conductor reads only the caches.

---

## §23 What's deferred (after v0.1)

Carried forward from §16, plus new:

- **Conductor runtime** — `lib/conductor.py` + `page/conductor.js`.
- **Panel registry seed** — initial ~30 panels.
- **Graph builders** — `lib/graphs/build_*.py`, one per `graph_id`
  in §18.1.
- **Event bus runtime** — a small in-browser pub/sub plus a server-side
  webhook receiver for runner events (`analysis_succeeded` etc).
- **LLM stage 3 → vocab_graph integration** — the conductor needs to
  receive `vocab_concept_picked` events; today the funnel doesn't yet
  emit those typed events (only the stage artifacts in spec form). PR
  pending in funnel.
- **Resize debounce tuning** — the 120 ms in §17.1 is a default; later
  may be slot-class-specific.
- **Cross-page panel migration** (still deferred from §16).

---

---

## §24 Per-analysis panel requirements (`panel_requirement_v1`)

Every chain and every atomic analysis can declare a `panel_requirements`
block on its `analysis_registry` row (additive — old rows without the
block remain valid; the conductor treats absence as "no declared
requirements", same as today).

The block names the panels the analysis needs to **stage** inputs,
**render** outputs, **propose** actions, and **narrate** results.
This makes the analysis the source of truth for "what UI does this
analysis want?" — not a separate spawn rule.

### §24.1 The shape

```jsonc
"panel_requirements": {
  "schema_version": "panel_requirement_v1",
  "stage": [
    { "panel_id": "candidate_picker",
      "role": "scope_input",
      "required": true,
      "gates": [ {"graph":"scope_graph","path":"atlas/cohort","state":"all_set"} ] }
  ],
  "render": [
    { "panel_id": "mendelian_burden_card",
      "role": "primary_result",
      "required": true,
      "expects_layers": ["hpp_offspring_gene_status"] },
    { "panel_id": "contradiction_table",
      "role": "drill_down",
      "required": false }
  ],
  "propose": [
    { "panel_id": "next_action_proposal",
      "role": "action",
      "required": false,
      "gates": [ {"graph":"chain_graph","node":"{{self}}","tier":["one","ready"]} ] }
  ],
  "narrate": [
    { "panel_id": "manuscript_chunks_panel",
      "role": "writeup",
      "required": false,
      "filter": { "manuscript_chunks.analysis_id": "{{self}}" } }
  ],
  "notes": "{{self}} is substituted with this analysis_id at evaluation time."
}
```

### §24.2 The four roles

| `role`            | When the panel matters |
|---|---|
| `scope_input`     | Before the analysis can run — gathers the parameters / scope it needs |
| `primary_result`  | The headline output rendering once the analysis has run |
| `drill_down`      | Optional secondary views (contradictions, per-sample tables, residuals) |
| `action`          | "What can the user DO next" — dispatch a follow-up, copy a sentence, queue a manifest |
| `writeup`         | Manuscript chunks tied to this analysis (page-12-style) |

The roles are descriptive (helps the conductor's layout policy decide
slot affinity) — not a hard contract on what the panel renders.

### §24.3 Why declare requirements on the analysis, not in a separate spawn rule

Three reasons:

1. **Single source of truth.** A new analysis lands → its row declares
   the panels it wants. No second JSONL to update, no risk of drift
   between "what the analysis produces" and "what the UI knows to show".
2. **Composable plans.** A chain that runs analyses A → B → C can union
   the panel_requirements of A, B, and C automatically. The conductor
   builds the spawn plan from the analysis-side declarations.
3. **Audit-friendly.** "Why did this panel spawn?" → walk back to the
   analysis that declared it. The provenance is one hop, not a
   debugging session through generic spawn rules.

Spawn rules (§6) still exist for **page-level** spawn decisions
(dismiss-on-no-scope, default panels per page). Analysis-level panel
requirements handle the **what-does-this-analysis-need** dimension.

---

## §25 The panel coverage graph (`panel_coverage_graph`)

A sixth registered graph, derived from §24 declarations:

| Node kind | Edges |
|---|---|
| `analysis` (analysis_id)     | `requires →` panels (per §24 stage/render/propose/narrate role) |
| `panel` (panel_id)           | `serves ←` analyses; `belongs_to →` atlas |
| `chain` (analysis_id, chain) | `composes →` member analyses |

The graph answers four questions:

| Question | Walk |
|---|---|
| "What panels does analysis X need?" | from `analysis:X` outward |
| "What analyses does panel Y serve?" | from `panel:Y` inward |
| "What's the union of panels for chain Z?" | from `chain:Z` → composed analyses → unioned panel set |
| "Which atlases share panel Y?" | from `panel:Y` via `belongs_to` |

This is the bridge between the **operation registry** and the **UI
registry**. The conductor reads it for pre-flight planning (§27);
page 4 (Catalogue) reads it to show which panels back each module
card; page 12 (Manuscript) reads it to filter chunks per atlas.

Like all graphs in §18, this one is a CACHE — rebuilt by a librarian
sub-task on registry reload. The conductor never walks the analysis
JSONL directly.

---

## §26 Vocabulary-level panel routing

The vocab_graph (§18.1) has four levels. Panel requirements can be
declared at **any level** — the conductor matches them against the
LLM funnel's stage-3 activation events.

| vocab level         | Example panel binding                       |
|---|---|
| `domain`            | `panel:inheritance_domain_overview`         |
| `concept`           | `panel:mendelian_burden_card`               |
| `registry-vocab`    | `panel:mendelian_per_candidate_card` (binds analysis_id=mendelian) |
| `instance`          | `panel:trio_F042_F043_F088_detail` (binds specific samples) |

A `panel_requirement_v1` row can carry an optional
`vocab_binding` field:

```jsonc
{ "panel_id": "mendelian_burden_card",
  "role": "primary_result",
  "vocab_binding": {
    "level": "concept",
    "concept_ids": ["mendelian", "burden", "transmission"]
  }
}
```

The panel becomes spawn-eligible once **any** of those concept_ids
appears in a `vocab_concept_picked` event (§19.1). This is the
mechanism that gives the LLM funnel a **progressive panel surface**:
domain-level panels spawn early (stage 2), concept-level panels join
in (stage 3), registry-vocab-level panels narrow further (still
stage 3), and instance-level panels lock in at stage 4 once the user
confirms a specific candidate / sample / trio.

§20.2's worked example walks all four levels for the
"Does LG28 follow Mendelian inheritance?" question; §26 is the
formalisation that lets the same logic apply to any future question
without writing new spawn rules.

---

## §27 Research plans (`panel_plan_v1`)

Pre-flight orchestration. Before any analysis runs, the conductor can
produce a **panel plan** — the ordered, gated set of panels that
will spawn as the plan executes. The plan is reviewable, dismissable,
diffable; it's the UI equivalent of `dispatcher_plan_v1` (see
DISPATCHER_SPEC §2).

### §27.1 Plan generation

```
research goal (text or chain selection)
        │
        ▼
LLM funnel resolves to a chain or analysis set
        │
        ▼
Conductor walks panel_coverage_graph from each analysis
        │
        ▼
Unions panel_requirements (stage / render / propose / narrate)
        │
        ▼
Sorts by role: scope_input first, render next, propose last
        │
        ▼
Annotates each panel with: gates status, required scope keys,
                            expected_layers, atlas
        │
        ▼
Emits panel_plan_v1
```

### §27.2 The shape

```jsonc
{
  "schema_version": "panel_plan_v1",
  "plan_id":        "plan_1779495013_lg28_mendelian",
  "generated_at":   "2026-05-23T14:00:00Z",
  "goal":           "Validate Mendelian inheritance of inv_LG28_INV_001",
  "source": {
    "kind":         "funnel",                            // funnel | chain_pick | manual
    "funnel_session": "fnl_…",
    "vocab_activated": [
      {"level": "domain",  "id": "inheritance"},
      {"level": "concept", "id": "mendelian"},
      {"level": "registry-vocab", "kind": "analysis_id", "id": "mendelian"},
      {"level": "instance", "kind": "candidate_id", "id": "inv_LG28_INV_001"}
    ]
  },
  "scope_required": {
    "atlas":         "inversion_atlas",
    "cohort":        "cgar_hatchery_226",
    "sample_set":    "qcpass_226",
    "candidate_id":  "inv_LG28_INV_001"
  },
  "steps": [
    {
      "phase":      "stage",
      "panel_id":   "candidate_picker",
      "role":       "scope_input",
      "from_analysis": "mendelian",
      "gates_status": [ {"graph":"scope_graph","node":"candidate_id","state":"all_set","passes":true} ]
    },
    {
      "phase":      "render",
      "panel_id":   "mendelian_burden_card",
      "role":       "primary_result",
      "from_analysis": "mendelian",
      "expects_layers": ["mendelian_result"],
      "gates_status": [ {"graph":"layer_graph","node":"mendelian_result","state":"producer_not_run","passes":false} ]
    },
    {
      "phase":      "propose",
      "panel_id":   "next_action_proposal",
      "role":       "action",
      "from_analysis": "mendelian",
      "actions": [
        { "action_id": "queue_chain",
          "gates_status": [ {"graph":"chain_graph","node":"mendelian","tier":"one","passes":true} ],
          "enabled": true }
      ]
    },
    {
      "phase":      "narrate",
      "panel_id":   "manuscript_chunks_panel",
      "role":       "writeup",
      "from_analysis": "mendelian",
      "filter": { "manuscript_chunks.analysis_id": "mendelian" }
    }
  ],
  "summary": {
    "n_steps":          4,
    "n_ready":          1,
    "n_gated_blocked":  1,
    "n_actions_enabled":1,
    "first_unblocking_action": "run_mendelian_module"
  },
  "_provenance": {
    "from_dispatcher_plan_id": "disp_plan_…",
    "atlas":                    "inversion_atlas",
    "cohort":                   "cgar_hatchery_226"
  }
}
```

### §27.3 What the plan is for

1. **Pre-flight review.** User sees, before any analysis runs,
   exactly which panels will spawn and which actions will be
   available. No surprise UI.
2. **Bottleneck surfacing.** `n_gated_blocked` + `first_unblocking_action`
   answer "what's the cheapest move to make this plan executable?" —
   same as chain audit, but at the *plan* (multi-chain) granularity.
3. **Manuscript pre-population.** The `narrate` phase steps list the
   manuscript chunks tied to the analyses in the plan; page 12 can
   pre-select them so the writeup grows alongside the analysis run.
4. **Diff-against-current.** A plan can be diffed against the current
   panel state to know which spawns are pending vs already present —
   useful for "resume" affordances after a refresh.

### §27.4 Plan lifecycle

```
generate → review → (edit | accept | dismiss) → execute
   │           │            │           │
   │           │            │           ▼
   │           │            │     spawn the steps as gates clear
   │           │            │     emit panel_event for each spawn
   │           │            │     update plan.summary live
   │           │            ▼
   │           │     plan is discarded; no panel state changed
   │           ▼
   │     user can pin / unpin individual steps before accept;
   │     edits are recorded as a delta on the plan
   ▼
   plan is persisted as 02_queue/plans/<plan_id>.json
   (mirrors the dispatcher's 02_queue/<action_id>.json convention)
```

Plans live alongside dispatcher manifests in `02_queue/plans/`.
Same browser-readable index pattern (`02_queue/plans/index.json`).
Same runtime-state directory: gitignored, conductor writes, page UI
reads.

### §27.5 Why plans, not just rules

Spawn rules are **reactive** — they fire on an event. Plans are
**deliberative** — they pre-compute the full panel arc for a chosen
goal. Both coexist:

| | Spawn rules (§6) | Panel plans (§27) |
|---|---|---|
| Trigger | event (scope change, vocab pick, …) | explicit goal / chain selection / funnel resolution |
| Granularity | one rule, zero-or-more panels | one plan, ordered multi-phase arc |
| Visible to user before fire? | no (panels appear) | yes (review before execute) |
| Persisted? | no (rule lives in registry) | yes (02_queue/plans/<id>.json) |
| Idempotent? | yes, on every re-eval | yes, accept-once; re-accept re-spawns |

A typical session: spawn rules carry the moment-to-moment UI; a panel
plan handles the "I want to validate this candidate end-to-end"
moments.

---

## §28 §refusals extended again (+5 → 18 total)

Carrying forward §11 (1-8) and §21 (9-13):

14. **No panel requirement on the panel side.** A panel CANNOT
    declare "I should spawn for analysis X" — only the analysis can
    declare "I need panel X". Prevents reverse dependencies and
    keeps the operation registry as the single source of truth for
    coverage (§24.3).
15. **No plan execution without scope satisfaction.** Plans require
    `scope_required` to be satisfied before any non-`stage` step
    spawns. A plan cannot rush through scope by guessing.
16. **No silent plan rewrites.** Once accepted, a plan is immutable
    in `02_queue/plans/<plan_id>.json`. Updates produce a NEW
    plan_id; the old one's state is preserved for audit.
17. **No vocab_binding above the resolution it claims.** A
    requirement bound at `level: registry-vocab` cannot spawn from a
    domain-level activation. The conductor verifies the level chain
    matches before granting eligibility.
18. **No analysis-side panel that mutates the analysis.** Panels
    surfaced for an analysis can NEVER edit that analysis's
    registry row, parameters, or results. Edits go through the
    dispatcher (params) or the librarian (registration) — not via
    the panel.

---

## §29 Files added in v0.2 (still spec-only)

Carried from §22, plus:

| File | Schema | Role |
|---|---|---|
| `01_registry/graphs/panel_coverage_graph.json` | derived cache | sixth graph; analysis↔panel edges (§25) |
| `02_queue/plans/<plan_id>.json`                | `panel_plan_v1` | one per accepted plan (§27) |
| `02_queue/plans/index.json`                    | derived index | browser-readable plan list, mirrors `02_queue/index.json` |

Plus the analysis_registry rows pick up an optional `panel_requirements`
block (additive — old rows still validate).

---

## §30 What's deferred (after v0.2)

Carried from §23, plus:

- **panel_requirements seed** — concrete blocks for the 17 currently
  registered chains. A "panel-requirement-seed" PR will land them
  once the runtime conductor can read them.
- **Plan UI** — page 13 (or a panel kind `plan_review`) that renders
  a `panel_plan_v1` with phase strips, gate status pills, and
  Accept / Edit / Dismiss buttons.
- **Plan diff renderer** — visualises a plan diffed against the
  current panel state (which steps will spawn, which are already
  there, which need an upstream run first).
- **Chain → plan auto-promotion** — if the chain audit reports a
  `one-step` chain and the user opens that chain's page, the
  conductor can auto-generate a `panel_plan_v1` and present it for
  review. Same diff loop as today, just with a plan object on top.

---

_End of DYNAMIC_PANELS_SPEC.md (v0.2)._
