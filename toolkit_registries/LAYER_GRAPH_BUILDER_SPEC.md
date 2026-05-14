# LAYER_GRAPH_BUILDER_SPEC — APLR's user-facing contract

Status: **v1 (frozen)**.  Schema version: `layer_graph_v1`.

This document specifies the contract between the user, the LLM, and APLR
(the Atlas Pipeline & Layer Resolver) for building, validating, and
acting on **layer graphs**.

It is the canonical reference for the **Layer Graph Builder** UI, the
**LLM proposal mode**, and the **page-composition** behaviour of the
dashboard.  Everything downstream — pages, panels, the librarian, the
dispatcher — reads against the contracts defined here.

---

## §0 The one-sentence model

> **Modules produce layers.  Pages consume layers.  Hooks declare which
> layers a page needs.  The librarian resolves whether each layer is
> RESOLVED / COMPLETE / READY_TO_RUN / BLOCKED_BY_INPUT / KNOWN_MISSING /
> UNKNOWN_CONTRACT / FAILED / STALE / PARTIAL.  The dispatcher decides
> whether to act.  The Layer Graph Builder is the visual contract
> viewer.**

If a sentence in this document contradicts that paragraph, the paragraph
wins.

---

## §1 Why this exists

Biology workflows are messy.  A typical atlas page wants to display a
dozen related views — karyotype calls, relatedness graphs, Mendelian
panels, popstats tracks, breakpoint evidence — and any subset of them may
or may not exist in the current workspace.  Hard-coding "if this page
opens, run X then Y then Z" does not scale past a few analyses; it also
makes the system run things the user did not ask for.

The layer-graph design solves this:

1. **Every page state is derivable from the registries.**  No page is
   ever "broken because someone forgot to run X" — the page renders
   panel-by-panel based on whether each required layer resolves.
2. **No hidden runs.**  A page open is a *query*, not a *trigger*.
   `resolve()` never writes; only an explicit user (or scheduled)
   dispatch call runs anything.
3. **The graph is declarative.**  Modules declare what they consume and
   produce; hooks declare what they need; APLR walks the join.  No new
   biology is wired in code.
4. **AI can author the graph.**  Because every node and edge is typed
   against a controlled vocabulary, an LLM can propose a graph from a
   research question and APLR can validate it before commit.

---

## §2 The five-element vocabulary

Every node in the graph is one of five node types.  Anything an atlas
page deals with reduces to combinations of these.

| Node type | What it is | Examples | Lives in |
|---|---|---|---|
| **`set`**      | A named collection of entities of one type. | `samples_226_v1` (sample), `inv_LG28_INV_001_v1` (interval), `candidates_LG28_medium_v1` (candidate_interval) | `sample_sets.tsv` / `interval_sets.tsv` / `site_sets.tsv` / `group_sets.tsv` |
| **`filter`**   | A deterministic transformation `set → set` (selection / intersection / union / difference / predicate). | `same_chromosome_pair_filter`, `confidence_gte_medium` | `derivation_registry.tsv` (when committed) |
| **`layer`**    | A unit of data the atlas resolves.  Has a `source_kind` (`file` / `analysis_result` / `operation` / `inline`). | `karyotype_calls`, `relatedness_res`, `mendelian_result`, `long_range_haplotype_regime` | `layer_registry.tsv` |
| **`analysis`** | A KIND of computation: declares `input_entity_types`, `input_layer_types`, `produces`, `engine`, `default_runner`. | `ngsrelate`, `mendelian`, `popstats`, `karyotype_classifier` | `analysis_registry.tsv` |
| **`hook`**     | A page / panel / widget request.  Declares `requires_layers` (required) and `optional_layers`. | `mendelian_page_load`, `candidate_review_hook` | `hook_registry.tsv` |

That is the entire vocabulary.  More specialised concepts (operations,
inline payloads, products, derivations, operation_params) are subtypes
of these five.

### §2.1 Visual language (for the Graph Builder)

```
○  set         circle, white fill, entity_type label
◇  filter      diamond, light yellow, condition list
▭  layer       rectangle, fill by source_kind (file=green, analysis_result=blue, operation=amber, inline=purple)
⬡  analysis    hexagon, accent fill
🔌 hook         plug icon, dark grey
```

Edges:
- `→` solid : declared edge (came from a registry row)
- `⇢` dashed : proposed edge (LLM proposal or user draft, not yet committed)
- `⤳` red : invalid edge (failed type check)

---

## §3 The graph contract

A **layer graph** is a typed DAG.  Its JSON form is validated by
`schemas/registry_schemas/layer_graph_v1.schema.json` (defined below).

```json
{
  "graph_id":   "candidate_review_LG28_v1",
  "schema_version": "layer_graph_v1",
  "intent":     "Show karyotype-conditional Mendelian distortion inside one inversion candidate.",
  "scope":      { "sample_set": "samples_226_v1", "interval_set": "inv_LG28_INV_001_v1" },
  "nodes": [
    { "id": "candidate_inversions", "type": "set",
      "entity_type": "candidate_interval" },
    { "id": "karyotype_calls",       "type": "layer",
      "layer_id": "karyotype_calls" },
    { "id": "relatedness_res",       "type": "layer",
      "layer_id": "relatedness_res" },
    { "id": "pedigree_result",       "type": "layer",
      "layer_id": "pedigree_result" },
    { "id": "mendelian",             "type": "analysis",
      "analysis_id": "mendelian",
      "trigger_policy": "manual" },
    { "id": "mendelian_result",      "type": "layer",
      "layer_id": "mendelian_result" },
    { "id": "mendelian_page",        "type": "hook",
      "hook_id": "mendelian_page_load" }
  ],
  "edges": [
    ["candidate_inversions", "karyotype_calls",  "input"],
    ["relatedness_res",      "pedigree_result",  "input"],
    ["karyotype_calls",      "mendelian",        "input"],
    ["pedigree_result",      "mendelian",        "input"],
    ["mendelian",            "mendelian_result", "output"],
    ["mendelian_result",     "mendelian_page",   "input"]
  ]
}
```

### §3.1 Node fields

Every node has `id` (graph-local), `type` (one of the five), and a
type-specific reference:

- `set`: `entity_type` + (one of `set_id` / inline `members`)
- `filter`: `input` node id, `conditions[]` (field/op/value), `output` id (auto)
- `layer`: `layer_id` (FK → `layer_registry.layer_id`)
- `analysis`: `analysis_id` (FK → `analysis_registry.analysis_id`), `params` (optional), `trigger_policy` ∈ {`manual` | `auto` | `cached_only`}
- `hook`: `hook_id` (FK → `hook_registry.hook_id`)

Optional on every node:
- `confidence` ∈ {`high` | `medium` | `low`} — used by the LLM proposer
- `required` (boolean, default true)
- `reason` — free-text justification (LLM uses this to explain itself)

### §3.2 Edge fields

Every edge is a 3-tuple `[from_node_id, to_node_id, edge_type]`:

- `edge_type` ∈ {`input` | `output` | `feeds_into`}
- `input` and `output` are with respect to an **analysis** node.
- `feeds_into` is the catch-all (filter→set, set→layer, layer→hook).

### §3.3 What gets stored where

| Concept | Storage |
|---|---|
| One graph as a draft (not committed) | `localStorage` in the Layer Graph Builder page |
| One graph as a proposal (LLM-written) | A `proposed_graphs/<graph_id>.json` file under the workspace root |
| One graph as a committed plan | A row in `01_registry/graph_registry.tsv` + a JSON under `02_graphs/<graph_id>.json` |
| The *resolved* state of a graph | NOT stored.  Computed live by the librarian on every page load. |

We do not persist the resolved state.  Resolution is cheap (registry
joins) and persisting it invites stale-cache bugs that violate the
no-hidden-runs rule.

---

## §4 The 9 librarian states

`resolve_layer.py` returns exactly one of these per layer; the page
composition collapses them into the 5 panel states (§5).

| State | Meaning | Trigger |
|---|---|---|
| `RESOLVED`         | File-kind layer present in scope.                                                       | `default_path` file exists, OR registry row matches scope. |
| `COMPLETE`         | Analysis-result layer with a matching `analysis_results.tsv` row, `status=active`.       | Result row found. |
| `READY_TO_RUN`     | Analysis-result layer; every upstream input resolves to `RESOLVED` / `COMPLETE`.         | All upstreams green, no existing result. |
| `BLOCKED_BY_INPUT` | Analysis-result layer; at least one upstream is `KNOWN_MISSING` / `UNKNOWN` / `FAILED`.  | Some upstream red. |
| `KNOWN_MISSING`    | Contract registered; product / file absent in scope.                                     | Registered, not found. |
| `UNKNOWN_CONTRACT` | `layer_id` not in `layer_registry.tsv`, OR `source_kind` not implemented.                | No layer row. |
| `STALE`            | (reserved) Hash-based invalidation; an upstream hash changed.                            | Not yet implemented. |
| `FAILED`           | `analysis_results.tsv` row with `status=failed`.                                         | Result row found, marked failed. |
| `PARTIAL`          | (reserved) Chunked outputs; some shards present, others not.                              | Not yet implemented. |

**Critical distinction**: `KNOWN_MISSING` (we know what the layer is, the
product is absent) versus `UNKNOWN_CONTRACT` (the layer itself isn't
declared).  The first is fixable by running something; the second
requires editing the registry.

---

## §5 Page composition: the 5 panel states

A hook declares `requires_layers` and `optional_layers`.  The librarian's
**composition plan** maps each layer's resolution state to a panel state
according to this fixed table:

| Layer state \ Required? | required | optional |
|---|---|---|
| `RESOLVED` / `COMPLETE`     | `VISIBLE_COMPLETE`  | `VISIBLE_COMPLETE`  |
| `READY_TO_RUN`              | `READY_TO_RUN`      | `READY_TO_RUN`      |
| `KNOWN_MISSING`             | `VISIBLE_BLOCKED`   | `HIDDEN_OPTIONAL`   |
| `BLOCKED_BY_INPUT`          | `VISIBLE_BLOCKED`   | `HIDDEN_OPTIONAL`   |
| `UNKNOWN_CONTRACT`          | `VISIBLE_BLOCKED`   | `HIDDEN_OPTIONAL`   |
| `FAILED`                    | `VISIBLE_BLOCKED`   | `HIDDEN_OPTIONAL`   |
| `STALE` / `PARTIAL`         | `VISIBLE_PARTIAL`   | `VISIBLE_PARTIAL`   |

The aggregate **hook state** is:

| Panels                                                                                  | Hook state |
|---|---|
| All required panels `VISIBLE_COMPLETE`                                                 | `COMPLETE` |
| All required panels `READY_TO_RUN`                                                     | `READY_TO_RUN` |
| Some required `VISIBLE_COMPLETE`, others not (any mix that isn't pure complete/ready)  | `PARTIAL`  |
| All required `VISIBLE_BLOCKED`                                                         | `BLOCKED`  |
| Every required `UNKNOWN_CONTRACT`                                                      | `HIDDEN`   |

### §5.1 The page composition plan JSON

```json
{
  "hook_id":      "candidate_review_hook",
  "schema_version":"page_composition_plan_v1",
  "page_id":      "candidate_review",
  "scope":        { "sample_set": "samples_226_v1", "interval_set": "inv_LG28_INV_001_v1" },
  "hook_state":   "PARTIAL",
  "panels": [
    {
      "panel_id":      "candidate_overview_panel",
      "layer_id":      "inversion_candidates",
      "required":      true,
      "panel_state":   "VISIBLE_COMPLETE",
      "layer_state":   "RESOLVED",
      "missing_layers":[],
      "actions":       []
    },
    {
      "panel_id":      "karyotype_panel",
      "layer_id":      "karyotype_calls",
      "required":      true,
      "panel_state":   "VISIBLE_COMPLETE",
      "layer_state":   "RESOLVED"
    },
    {
      "panel_id":      "long_range_regime_panel",
      "layer_id":      "long_range_haplotype_regime",
      "required":      false,
      "panel_state":   "HIDDEN_OPTIONAL",
      "layer_state":   "KNOWN_MISSING"
    },
    {
      "panel_id":      "mendelian_panel",
      "layer_id":      "mendelian_result",
      "required":      false,
      "panel_state":   "VISIBLE_COMPLETE",
      "layer_state":   "COMPLETE",
      "result_id":     "mendelian_LG28_v2"
    }
  ]
}
```

The page renders by walking `panels[]`:

- `VISIBLE_COMPLETE` → full panel, with data preview.
- `VISIBLE_PARTIAL`  → full panel, with stale / partial badge.
- `VISIBLE_BLOCKED`  → compact red card.  Lists `missing_layers[]`.  If
  any missing layer is itself `READY_TO_RUN`, the card shows a manual
  **Run dependency** button (does not run; emits a dispatch request).
- `READY_TO_RUN`     → compact blue card.  Manual **Run** button.
- `HIDDEN_OPTIONAL`  → not rendered, or rendered as a collapsed grey
  placeholder if the user toggles "Show optional".

---

## §6 Edge validation rules

Edges are typed.  Not every node can connect to every other node.
Validation rules live in `vocabulary/edge_rules.tsv` and are evaluated
by `lib/edge_validator.py`.  The minimal v1 ruleset:

| from.type | to.type   | edge_type   | constraint |
|---|---|---|---|
| `set`      | `filter`   | `feeds_into` | `set.entity_type == filter.input_entity_type` |
| `filter`   | `set`      | `feeds_into` | always valid (filter outputs a derived set) |
| `set`      | `analysis` | `input`      | the analysis row has a `sets[].entity_type` matching `set.entity_type` |
| `set`      | `layer`    | `feeds_into` | `layer.entity_type == set.entity_type` (or layer is scope-anchored, e.g. `karyotype_calls` accepts `sample` + `candidate_interval`) |
| `layer`    | `analysis` | `input`      | `analysis.input_layer_types` contains `layer.layer_id` |
| `analysis` | `layer`    | `output`     | `analysis.produces` contains `layer.layer_id` |
| `layer`    | `hook`     | `input`      | `hook.requires_layers` ∪ `hook.optional_layers` contains `layer.layer_id` |

Anything else is invalid by default.  Invalid edges render red in the
Graph Builder and fail `aplr.validate(graph)`.

---

## §7 The three UI modes

The Layer Graph Builder operates in three modes, surfaced as tabs:

### §7.1 Ask mode

```
┌────────────────────────────────────────────────────────────────┐
│  Research question:                                            │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ Can we test whether candidate inversions with high       │  │
│  │ karyotype confidence show Mendelian distortion using     │  │
│  │ relatedness hubs?                                        │  │
│  └──────────────────────────────────────────────────────────┘  │
│  [ Propose graph ]                                              │
│                                                                 │
│  Suggested nodes (controlled vocabulary):                       │
│   high  ✓ candidate_interval_set                                │
│   high  ✓ karyotype_calls (layer)                               │
│   high  ✓ relatedness_res (layer)                               │
│   high  ✓ mendelian (analysis)                                  │
│   med   ⚠ long_range_haplotype_regime (not yet registered)      │
│   low   ? family_hubs (no producer)                             │
│                                                                 │
│  [ Add all required ]  [ Add only known ]  [ Discard ]          │
└────────────────────────────────────────────────────────────────┘
```

The LLM emits a `node_proposal_v1` document.  The Builder loads it as a
draft graph (dashed edges) until the user clicks **Add**.

### §7.2 Inspect mode

```
┌─ left rail ─┐  ┌─ canvas ─────────────────────┐  ┌─ right inspector ─┐
│ Nodes (drag) │  │                              │  │ Selected:          │
│  ○ set       │  │   ○ candidate_inversions     │  │   mendelian        │
│  ◇ filter    │  │      ↓                       │  │ analysis_id:       │
│  ▭ layer     │  │   ◇ confidence_gte_medium    │  │   mendelian        │
│  ⬡ analysis  │  │      ↓                       │  │ trigger_policy:    │
│  🔌 hook     │  │   ▭ karyotype_calls   ✅     │  │   manual           │
│              │  │      ↘     ⬡ mendelian ⚠   │  │ Required inputs:   │
│ Available    │  │   ▭ pedigree_result   ✅    │  │  ✅ karyotype_calls │
│ (registry):  │  │           ↓                  │  │  ✅ pedigree_result │
│  ▭ karyo...  │  │       ▭ mendelian_result ⚠   │  │ Status:            │
│  ▭ mendel... │  │           ↓                  │  │   READY_TO_RUN     │
│              │  │       🔌 mendelian_page      │  │ [ Run ]            │
└──────────────┘  └──────────────────────────────┘  └────────────────────┘
```

- Drag-from-rail places a new node; click two nodes to draw an edge.
- Each edge is validated live against §6's rules.
- Each node carries its librarian state as a badge.

### §7.3 Commit mode

```
┌────────────────────────────────────────────────────────────────┐
│  graph_id:  candidate_review_LG28_v1                            │
│  state:     READY_TO_RUN (1 ready, 0 blocked, 0 stale)          │
│                                                                 │
│  [ Validate graph ]  [ Save to localStorage ]                   │
│  [ Export JSON ]      [ Commit to registry ]                    │
│  [ Run selected ] ← runs the ONE selected READY_TO_RUN node     │
│                     (calls /api/actions; never auto-runs)       │
└────────────────────────────────────────────────────────────────┘
```

**Commit** writes a row to `01_registry/graph_registry.tsv` + a JSON
under `02_graphs/<graph_id>.json`.  **Run selected** dispatches one node
at a time via the existing `POST /api/actions` from PR #3.

---

## §8 LLM proposal mode — the killer feature

A research question is mapped to a proposed graph by **two LLM calls**,
both constrained by the controlled vocabulary from `vocabulary/` (PR #7).

### §8.1 The pipeline

```
human request
    ↓
Stage A — extract intent (LLM call #1)
    inputs:  the question, the domain index (vocabulary/domains.tsv)
    output:  { goal, entities[], analyses[], constraints[] }
    ↓
Stage B — map to vocabulary (deterministic)
    inputs:  Stage-A output + vocabulary/keywords/*.tsv
    output:  { layer_ids[], analysis_ids[], entity_types[], filters[] }
    ↓
Stage C — propose graph (LLM call #2)
    inputs:  Stage-B vocabulary hits, layer_registry, analysis_registry
    output:  node_proposal_v1 JSON (the graph draft + confidence per node)
    ↓
Stage D — validate (deterministic)
    inputs:  the proposal
    checks:  every node references a known layer_id / analysis_id;
             every edge passes §6 rules
    output:  { valid: bool, errors: [], proposal: <annotated> }
    ↓
Layer Graph Builder loads the proposal in Ask mode.
```

### §8.2 Locked prompts

The two LLM prompts are locked at v1.  See appendix A.  Bumping them
requires a `schema_version` bump on `node_proposal_v1`.

### §8.3 Confidence rules

Each proposed node carries a `confidence` field:

- `high`   — the term appeared verbatim (or as a controlled-vocab alias) in the question.
- `medium` — inferred via a domain edge (`vocabulary/edges.tsv`) of type `requires` / `belongs_to`.
- `low`    — added because the producing analysis demands it as input.

The UI separates `high` (always added) from `medium` (shown as a confirmation prompt) from `low` (collapsed by default).

### §8.4 Refusals

The LLM is forbidden from:
1. inventing a `layer_id` or `analysis_id` that does not exist in the registries (must use a known one or mark the node as a `stub`);
2. writing free-text answers — only proposal JSON;
3. proposing an `auto` trigger policy — only `manual` and `cached_only` are allowed on first pass;
4. omitting a `reason` field on any node.

---

## §9 Dispatcher — the other side of the split

The librarian (`resolve_layer.py`) reads.  The dispatcher writes.  This
PR ships only the librarian + a stub dispatcher; the full dispatcher is
in a follow-up PR.  The contract:

```python
# lib/dispatcher.py (stub today)
def plan(graph: dict, scope: dict) -> dict:
    """Walk the graph; return one of {RUN, SKIP, REUSE, QUEUE, BLOCK}
    per node, with reasons.  Does NOT execute."""

def dispatch(node_id: str, graph: dict, scope: dict) -> dict:
    """Resolve one node; if state is READY_TO_RUN, build an
    action_manifest and POST it to /api/actions.  Returns action_id."""
```

Connect-a-node ≠ compute.  Resolve-a-graph ≠ compute.  Only an explicit
`dispatch()` call runs anything.  Pages never call `dispatch()`
automatically.

---

## §10 What this spec refuses to do (the §refusals)

These are deliberate omissions that survive prompt-rewrites:

1. **No automatic compute on page load.**  Resolution is read-only.  Pages render readiness, not results-on-demand.
2. **No persistent resolved state.**  Don't cache the librarian's output to disk; recompute on every page load.  Caching invites stale-bug pain that violates the no-hidden-runs rule.
3. **No free-text from the LLM.**  Stage C produces JSON or nothing.
4. **No invented vocabulary.**  The LLM cannot mint a `layer_id` or `analysis_id`.  It can mark a node as a `stub` and propose the registry rows separately.
5. **No graph editing without validation.**  Every save / commit / export validates the graph against §6 rules first.
6. **No `auto` trigger policy on first pass.**  All proposed analyses start as `manual` or `cached_only`.  Promoting to `auto` is a deliberate workspace-level decision.
7. **No assumption that all five node types are present.**  A minimum graph is one `hook` + its required `layer`s; analyses and filters are only there when they apply.

---

## §11 Worked example — the manuscript stress test

The atlas will be exercised against **one inversion candidate on
chromosome 1 and one on chromosome 28**.  The two candidates are
hypothesised to be related (same breakpoint signature, or co-segregating
karyotypes, or both).  The full graph that supports the manuscript:

```
○ samples_226_v1
○ inv_LG01_INV_001_v1   ○ inv_LG28_INV_001_v1
       \                       /
        ▭ karyotype_calls (both candidates)
                |
        ⬡ ngsrelate (per_candidate × 2)
                |
        ▭ relatedness_res (per_candidate × 2)
                |
        ⬡ ngspedigree (global, uses the union)
                |
        ▭ pedigree_result
                |
        ⬡ mendelian (per_candidate × 2)
                |
        ▭ mendelian_result (per_candidate × 2)

        ⬡ popstats (per_candidate × 2, karyotype-grouped)
                |
        ▭ popstats_result (FST / dxy / piN / piS per candidate)

        ⬡ inversion_pair_incompatibility (LG01 × LG28)
                |
        ▭ distortion_summary

       all of the above feed →   🔌 candidate_review_hook
                                  🔌 mendelian_page_load
                                  🔌 popstats_page_load
                                  🔌 pair_review_hook   (LG01 × LG28)
```

This graph is the **stress test target**: the system should be able to
render every panel for both candidates, walk both manuscript paths
(relatedness and popstats) end-to-end, and surface the LG01 × LG28
pair-relation analysis as `READY_TO_RUN` once the per-candidate results
exist.

The vertical slice in this PR covers the **candidate_review_hook**
column only.  The rest will be wired in follow-ups.

---

## §12 Phase plan

| Phase | What lands | PR |
|---|---|---|
| **A** Spec + schemas + vocab + one vertical slice | this doc; 4 new schemas; 2 extended schemas; layer_registry / hook_registry rows; resolve_layer `--compose`; `candidate_review.html`; seed data for LG28 | **this PR** |
| B Edge-validator engine | `lib/edge_validator.py` reads `vocabulary/edge_rules.tsv`; live red/green edges in the Builder | next |
| C Layer Graph Builder v2 | full node-canvas; drag-from-rail; three modes (Ask / Inspect / Commit); local-only | next-next |
| D Page composition fan-out | every existing dashboard page reads composition plans; panels appear/disappear by state | next |
| E LLM proposal mode | `lib/funnel.py` from PR #7 wires Stage A + C; Stage B is deterministic | when phases B–D have shaken out |
| F Dispatcher | `lib/dispatcher.py.plan` / `.dispatch`; wired to `POST /api/actions` from PR #3 | parallel-track |
| G LG01 × LG28 pair-relation analysis | `inversion_pair_incompatibility` analysis row + runner + page | manuscript-driven |

---

## Appendix A — locked LLM prompts (v1)

### A.1 Stage A — extract intent

```
SYSTEM:
You are an intent extractor for atlas-core.  Given a research question
about population genomics, return strict JSON of the form:

{
  "goal": "<one short imperative sentence>",
  "entities": [<controlled vocabulary tokens — see appendix B>],
  "analyses": [<controlled analysis tokens>],
  "constraints": [<free-text qualifier phrases>],
  "vague_terms": [<phrases that need clarification>]
}

Do not produce prose.  Do not invent tokens; if the question references a
concept not in the vocabulary, place the phrase in `vague_terms`.

USER:
<research question>
```

### A.2 Stage C — propose graph

```
SYSTEM:
You are a graph proposer for atlas-core.  Inputs:
  - the user's intent (Stage-A output)
  - the controlled vocabulary hits (Stage-B output)
  - the current layer_registry and analysis_registry contents

Return strict JSON conforming to node_proposal_v1.schema.json.  Every
node MUST cite an existing `layer_id` or `analysis_id` (or be marked as
a `stub` with `confidence: low` and a `reason`).  Every edge MUST be
typed per the §6 edge-validation table.  No free text.

USER:
<intent + vocabulary hits + registry summary>
```

These prompts are version-pinned by `schema_version: layer_graph_v1`.
Changing them requires a bump.

---

## Appendix B — controlled-vocabulary tokens

The vocabulary lives in `vocabulary/` and is the source of truth for what
the LLM can emit:

- `vocabulary/domains.tsv` — 12 domain tags (genetics, relatedness, …).
- `vocabulary/keywords/<domain>.tsv` — per-domain term banks.
- `vocabulary/node_types.tsv` — the five node-type tokens (this PR).
- `vocabulary/edge_rules.tsv`  — the edge-validation table (this PR).
- `vocabulary/edges.tsv`       — graph relations across domains.

Bumping any of these is a `schema_version` bump and invalidates prior
proposals.

---

_End of LAYER_GRAPH_BUILDER_SPEC.md (v1)._
