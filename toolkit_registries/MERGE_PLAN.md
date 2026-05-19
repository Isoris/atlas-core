# MERGE_PLAN — landing the stacked PRs in order

Status: **v1 (refreshed after PR #25).**

The atlas-core branch currently carries **23 stacked PRs** (#3 → #25).
Each builds on the previous via branch stacking, so the cleanest merge
sequence is **bottom-up, one PR at a time**, in the order below.

After each merge the next branch's diff against `main` shrinks to just
that PR's content. Until the first one merges, every PR's diff looks
larger than it really is.

---

## Pre-merge gate — full-stack smoke

Run before merging anything. Exits 0 when green:

```
python3 toolkit_registries/scripts/smoke_all_stack.py
```

Today: **13/13 green in ~540 ms**. Exercises the librarian, manager,
estimability manager, and dispatcher tiers against the manuscript
stress-test question (`inversion_pair_incompatibility_LG01_LG28`).

---

## The merge order

### Tier 1 — infrastructure (independent of each other; can merge in any order)

| # | Title | Adds |
|---|---|---|
| 3  | `server/`: POST /api/actions + GET /api/layers       | action-pipeline endpoints |
| 4  | `biomod`: step 1 — env commands                       | conda-style module catalog (env management only) |
| 7  | spec: LLM funnel                                      | `LLM_FUNNEL_SPEC.md` + vocabulary + 7 schemas (doc-only) |

### Tier 2 — relatedness/ minimum

| # | Title | Adds |
|---|---|---|
| 2  | (already covered by #5 transitively) `relatedness/` minimum infrastructure | 6 flat-TSV registries + contract checkers |
| 5  | `relatedness/`: wire both manuscript paths end-to-end | dispatcher.py contract + 4 runner stubs + stress-test |
| 6  | `page/`: hover-preview popovers                       | previews.js |
| 8  | brick-edit sidebar                                    | page 3 right-side editor + biomod recipe download |

### Tier 3 — catalogues (the contracts the rest of the stack depends on)

| # | Title | Adds |
|---|---|---|
| 9  | `relatedness/`: analysis_registry.tsv catalogue       | analysis_registry_v1 + FK validator |
| 10 | layer + hook registries + librarian                   | resolve_layer.py + 9-state librarian + page 5 |
| 11 | Layer Graph Builder spec v1                           | `LAYER_GRAPH_BUILDER_SPEC.md` + 5 schemas + page 6 |
| 12 | edge validator + Graph Builder page 7                 | lib/edge_validator.py + page 7 |
| 13 | adapter contract + packages + connection map + planner | `ADAPTER_CONTRACT.md` + JSONL canonical + first adapter |

### Tier 4 — Manager + UI

| # | Title | Adds |
|---|---|---|
| 14 | Status Manager + research products/questions + page 8 | `MANAGER_SPEC.md` §1-§4 + Manager + readiness page |
| 15 | Estimability Manager (sub-role)                       | `MANAGER_SPEC.md` §3.5 + estimability.py + estimands.jsonl |
| 16 | inversion_pair_incompatibility (LG01 × LG28)          | adapter compute + product + question + 2 estimands |
| 17 | Layer Connector (page 9) + integration prompt         | page 9 + `ATLAS_INTEGRATION_PROMPT.md` |
| 18 | atlas catalogue + data-driven page-9 sidebar          | atlas_v1 + atlases.jsonl + page-9 rerender |

### Tier 5 — polish + dispatcher

| # | Title | Adds |
|---|---|---|
| 19 | Workspace Health (page 10) + per-page docs            | page 10 + page/docs/*.md + doc.js |
| 20 | universal search + deep links                          | search.js + ?focus= deep-link handling |
| 21 | sticky scope ribbon + per-atlas color stripes         | scope.js + atlas-colors.js |
| 22 | page 1 deterministic matcher                          | research-question matcher (no LLM) |
| 23 | atlas dropdown in ribbon + full-width topnav          | atlas selector + CSS override |
| 24 | atlas filter wired on pages 8/9/10                    | scope.atlas filter live everywhere |
| 25 | **Phase F — Dispatcher v0**                            | `DISPATCHER_SPEC.md` + lib/dispatcher.py + 02_queue/ |
| 26 | **(this PR)** Merge plan + full-stack smoke test       | this file + scripts/smoke_all_stack.py |

---

## After each merge

```
1. git checkout main && git pull
2. python3 toolkit_registries/scripts/smoke_all_stack.py
3. confirm 13/13 green
4. proceed to the next PR
```

If a PR conflicts (because something further up the stack touched the
same file), rebase the next branch onto the freshly-merged `main` and
re-run the smoke before re-pushing.

---

## §refusals (about the merge itself)

1. **Don't squash-merge everything into one commit.** The PRs are stacked
   per *concept* — squashing them loses the per-tier architecture history.
2. **Don't merge out of order.** Tier 3 expects tier 2 (especially #5)
   to have landed; tier 4 expects tier 3's JSONL canonical to exist.
3. **Don't skip the smoke.** It catches cross-tier contract drift in
   ~half a second.
4. **Don't edit TSVs by hand for adapter-backed rows post-merge.**
   `python3 -m lib.tsv_from_jsonl` regenerates them from JSONL.

---

## What remains open after this merge

The phase plan from `LAYER_GRAPH_BUILDER_SPEC.md` §12 still has:

- **Phase D** — page composition fan-out on pages 2 / 3 / 4
- **Phase E** — LLM funnel Stages A + C (need a provider)
- **Page 11 — Queue UI** that visualises `02_queue/`
- **Real runner** wired to `02_queue/` (PR #3's `POST /api/actions` is the natural target)
- **`runs.jsonl`** for per-manifest state tracking

Each its own PR off `main` after this stack lands.

---

_End of MERGE_PLAN.md (v1)._
