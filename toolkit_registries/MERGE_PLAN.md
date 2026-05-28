# MERGE_PLAN — landing the stacked PRs in order

Status: **v1.3 (refreshed after the bridge tier + ADDON_SPEC + addon_manifest_v1 stack — 23/23 smoke).**

The atlas-core branch carries a **multi-PR active stack on top of
historical PRs #3 → #36**. The historical tiers in the merge tables below
remain the record of how the registry/manager/dispatcher tiers landed;
the **Live stack** section near the bottom is the current authoritative
landing order.

After each merge the next branch's diff against `main` shrinks to just
that PR's content. Until the first one merges, every PR's diff looks
larger than it really is.

---

## Pre-merge gate — full-stack smoke

Run before merging anything. Exits 0 when green:

```
python3 toolkit_registries/scripts/smoke_all_stack.py
```

Today: **23/23 green in ~1100 ms**. Exercises the librarian, manager,
estimability manager, dispatcher, conductor renderers, bridge tier,
panel-spawn coverage graph, addon manifest, and the offline-cassette
reference refresher — against the manuscript stress-test question
(`inversion_pair_incompatibility_LG01_LG28`).

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
- **Page 11 — Queue UI** that visualises `02_queue/` *(landed in PR #27)*
- **4-atlas split + cross-species adapter** *(landed in PR #28 — see `CROSS_SPECIES_BREAKPOINTS_WORKFLOW.md`)*
- **Real runner** wired to `02_queue/` (PR #3's `POST /api/actions` is the natural target)
- **`runs.jsonl`** for per-manifest state tracking
- **BP4 population overlap** — intersect cross_species breakpoint catalog with 226-cohort haploblocks (separate chat; strict cohort boundary)
- **BP5 figures** — R ribbons / dotplots / montages (separate chat)

Each its own PR off `main` after this stack lands.

---

_End of MERGE_PLAN.md (v1)._

---

## Live stack — registry tier (post PR #30 / cohort + plans + four-pack landed)

`origin/main` advanced past the historical merge tables; the four-pack +
karyotype-callers + cohort registry + manuscript-chunk coverage are
**merged**. The current local stack adds the **conductor wishlist,
bridge tier, addon manifest, and slot inventory** on top of that.

Stack order (each branch is `base=` the one above so the diff is minimal):

| stage | branch | head | base | adds |
|---|---|---|---|---|
| A | `claude/bridge-summary-card` | `8d6a0f0` | `origin/main` | conductor: bridge_summary_card panel + spawn rule + renderer |
| B | `claude/addon-spec` | `d3bc127` | A | `ADDON_SPEC.md` v0 (frozen) — six addon kinds + worked example |
| C | `claude/pages-slot-inventory` | `2708ed5` | B | `pages.jsonl` backfill 7 → 14 rows + `slots: [...]` field + check_panels slot-overlap rule |
| D | `claude/addon-manifest` | `434a9ca`* | C | `addon_manifest_v1` schema + `addons.jsonl` (23 rows) + `check_addons.py` + `addons_summary_card` + page_extension worked example + `bridge_log.example.jsonl` seed + `refresh_references --fixture` cassette mode |

(*) D extends as autopilot continues; the head moves but the base does
not. All four branches carry the hand-merged `README.md` resolution
(your shell-engine framing on top + a `toolkit_registries/` section
underneath).

Earlier branches in the local arc (already merged into the stack base or
into `origin/main`):

- `claude/bridge-tier`, `claude/bridge-5-more-adapters`,
  `claude/bridge-final-3-adapters` → folded into A
- `claude/four-pack`, `claude/manuscript-inversion-chunks`,
  `claude/registry-cache`, `claude/preview-pin-and-close`,
  `claude/page-12-manuscript` → already on `origin/main`

Merge order for this stack: **A → B → C → D**. Smoke must be 23/23 after each step before the next merges.

## What remains open after THIS stack lands

The ADDON_SPEC §9 "future amendments" list is now empty. The remaining
open items have moved off the registry tier and into the runtime tier:

| item | status | notes |
|---|---|---|
| **LLM funnel runtime** | open | Page 1 spec frozen; deterministic resolver + 2 LLM calls not yet wired. Needs a provider + cost/cache policy. |
| **Real BP4 runner** | open | Chain registered; `STEP_BP4_overlap_population.py` needs to land behind the dispatcher's `02_queue/` contract. |
| **Per-user telemetry** | open | Which spawn rules fire most, which panels get dismissed most. Hold until rules > 50 (currently 14). |
| **Live PubMed sweep** | open (network-blocked in sandbox) | `refresh_references --commit` would populate the remaining 16 references.jsonl rows; cassette already exercises the path in smoke. |
| **More addon kinds in service** | partial | 23 backfilled rows cover everything shipped under toolkit_registries/; page_extension has one example (workspace_health footer-row). Future addons land as one row each. |
| **`addons_summary_card` slot affinity expansion** | open | currently fixed to workspace_health; the spawn-when-any-page mode would surface the addon registry on every page. |
| **DYNAMIC_PANELS_SPEC ↔ ADDON_SPEC reconciliation** | open | DYNAMIC_PANELS_SPEC §2 panel kinds and ADDON_SPEC §2 panel kinds reference each other; a future refactor should pick one canonical home for the catalogue. |

_End of MERGE_PLAN.md (v1.3 — bridge + addon-manifest refresh)._
