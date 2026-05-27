# ADDON_SPEC — what a new addon can register

Status: **v0 (frozen).** Schema version: `addon_manifest_v1`.

> Companion to `DYNAMIC_PANELS_SPEC` (the conductor contract) and
> `BRIDGE_SPEC` (the external-DB contract). This doc enumerates
> **every type of UI surface an external contributor can register**
> via JSONL rows, without writing per-page HTML or per-renderer JS.

The atlas-core dashboard composes from 4 registries:

```
01_registry/panels.jsonl       (panel_v1 — UI primitives)
01_registry/spawn_rules.jsonl  (spawn_rule_v1 — when to spawn)
01_registry/pages.jsonl        (page_v1   — slot inventory per page)
+ addon-side data registries   (analyses, layers, modules, …)
```

An **addon** is anything that lands rows in one or more of those
files. A full atlas is an addon. A single new panel is an addon.
A new external DB adapter is an addon. The contract is the same:
declare in JSONL; the conductor + the existing renderers do the
rest. No per-addon HTML, no per-addon JS, no LLM in the loop.

---

## §1 The 6 addon kinds

| addon kind | what it ships | minimum to register |
|---|---|---|
| **A. Panel** | one renderer on an existing page | 1 row in `panels.jsonl` + 1 row in `spawn_rules.jsonl` + (optionally) a renderer in `conductor.js` if it isn't a generic kind |
| **B. Page extension** | a new slot on an existing page + panels targeted there | edit the page HTML to add `<div data-slot="...">` + spawn rules naming that slot |
| **C. Whole page** | a new top-nav entry (page 15, page 16, …) | new HTML file under `page/`, 1 row in `pages.jsonl`, topnav patch on the 14 existing pages, optional `docs/<page>.md` |
| **D. Analysis** | one new analysis_id + its modes + its layers | 1 row in `analysis_registry`, ≥1 row in `analysis_modes`, 1 row in `module_registry`, 0+ rows in `layer_registry` |
| **E. Bridge** | one new external-database wrapper | 1 row in `external_databases.jsonl` + adapter folder under `bridge/<db>/` (endpoints.json + LICENSE_NOTICE.md) |
| **F. Validator** | new audit step | 1 script under `scripts/check_*.py` + 1 entry in `smoke_all_stack.py` |

The conductor + bridge + chain audit handle the wiring; the addon
contributes data + (optionally) a renderer if its panel kind is new.

---

## §2 Panel kinds (DYNAMIC_PANELS_SPEC §2 + this v0 catalogue)

These are the `kind` values an addon can declare on a `panel_v1` row.
Each has a registered renderer (or a documented fallback) — using a
kind not on this list lands the "no renderer registered (TODO)"
dashed placeholder per spec §11.

| `kind` | what it renders | typical `data_source.kind` | example |
|---|---|---|---|
| `card`         | summary block with key/value rows or small tables | `registry`, `scope+registry` | `atlas_summary_card`, `cohort_summary_card`, `bridge_summary_card` |
| `table`        | tabular view, paginated if needed | `layer`, `analysis_result`, `registry` | `karyotype_panel`, `mendelian_panel` (legacy panels.jsonl rows) |
| `chart`        | a single chart (line / scatter / bar / hist) | `layer`, `analysis_result` | (not yet registered; renderer TODO) |
| `text`         | a markdown paragraph | `manuscript_chunk` | (used inline by page 12) |
| `form`         | small input form | `scope` | (used by scope ribbon — not a registered panel) |
| `preview`      | read-only JSON / TSV peek (truncated) | `analysis_result` | `previews.js` hover popovers (page 4 / 13) |
| `triage`       | ranked candidate triage table | `chain_audit` | chain-readiness on page 2 (hardcoded today; registered panel TBD) |
| `chain`        | chain-pipeline visualization | `chain_audit`, `panel_coverage_graph` | (TBD; chain audit table is the closest precursor) |
| `bibliography` | numbered reference list with DOI links | `manuscript_chunk` | (used inline by page 12 preview) |
| `empty`        | explanatory empty state | (any) | (used as fallback when a real panel has nothing to render) |

Promoting a new `kind` to the registered set:

1. Add the renderer to `page/conductor.js` (one `render<KindName>` function in the dispatch table).
2. Document it in this list with a worked example.
3. Add a test panel + spawn rule on `workspace_health` to validate.

Until step 1, the addon's panel will render as the dashed TODO
placeholder — visible failure, not invisible omission.

---

## §3 `data_source.kind` values

What an addon's panel can read from. Adding a kind not on this list
fails the `check_panels` validator.

| `data_source.kind` | yields |
|---|---|
| `scope` | live scope ribbon (atlas / cohort / sample_set / interval_set / candidate_id) |
| `registry` | one or more JSONL files under `01_registry/` (declared via `reads: [...]`) |
| `layer` | the rows of a specific `layer_id` (file or analysis_result) |
| `analysis_result` | the latest run of a given `analysis_id` |
| `chain_audit` | the chain-audit verdict (tiers, missing inputs) for a given chain |
| `manuscript_chunk` | a row from `manuscript_chunks.jsonl` with placeholder hydration |
| `scope+registry` | scope + registry compound; most common |
| `file` | a single runtime file (e.g. `02_queue/bridge_log.jsonl`) — addon declares the path in `reads` |

Promoting a new `data_source.kind` requires:
1. Update `check_panels.py` `ALLOWED_DATA_SOURCE_KINDS`.
2. Update `BRIDGE_SPEC` § wherever the kind lands.
3. Add a test panel that uses it.

---

## §4 Spawn rule `when` keys

What an addon's `spawn_rule_v1.when` clause can match against (§6 of
DYNAMIC_PANELS_SPEC). Adding a new `when` key requires extending the
conductor's match evaluator + `check_panels` validation.

| key | matches against | form |
|---|---|---|
| `page`       | current page_id from .topnav .tag       | array of page_ids |
| `scope`      | `getScope()` keys                       | `{key: "*"}` (any non-empty) or `{key: "literal-value"}` |
| `registry`   | live registry counts                    | named predicates (e.g. `chain_audit:has_one_step_chains`) |
| `chain_audit`| per-chain verdict                       | `{chain_id: "*", tier: ["one", "multi"]}` |
| `manuscript` | manuscript chunks selection             | `{has_chunks: true}` |

---

## §5 Pages — adding a whole new one

| step | what |
|---|---|
| 1 | New HTML file under `page/<name>.html` with the standard chrome (topnav, scope ribbon, shared scripts: `doc.js`, `search.js`, `loader.js`, `filters.js`, `registry-cache.js`, `conductor.js`, `scope.js`, `previews.js`) |
| 2 | Add `<a href="<name>.html"><span class="num">N.</span> Label</a>` to **all** existing pages' `nav.topnav` |
| 3 | Add `<span class="tag">Atlas-core — page N</span>` so the conductor's `pageIdFromDoc()` can identify the page (parses the page-N marker) |
| 4 | Update `conductor.js` `pageIdFromDoc()` map: `{ N: "name" }` |
| 5 | Update `check_panels.py` `KNOWN_PAGE_IDS` — adding the page_id to the allowed enum |
| 6 | Update `docs/<name>.md` for `doc.js` to surface the page's reference |

A page is just an HTML skeleton with declared slots. The conductor
fills the slots from `spawn_rules.jsonl`. Adding a page costs nothing
at runtime beyond the topnav link — the page itself can be empty
except for `<div data-slot="conductor-demo">`.

### Slot conventions

| slot name | typical contents |
|---|---|
| `main`          | primary panels — wide cards, tables |
| `rail-right`    | side rail — narrower summary cards |
| `conductor-demo`| anything the conductor spawns generically (the catch-all) |
| `footer-row`    | sticky footer panels (queue counts, etc.) |

Slots are declared two ways and must agree:

1. **At runtime**, by the page HTML — `<div data-slot="...">`. The
   conductor finds them on DOM load and uses them to place spawned
   panels.
2. **At audit time**, by `pages.jsonl` — each row carries
   `"slots": [...]`. `check_panels` reads this inventory and rejects
   any spawn rule whose target page declares slots that don't
   intersect the spawned panel's `slot_affinity` (otherwise the
   conductor would silently drop the spawn).

When you add a new slot to a page, update both the HTML AND the
page's `pages.jsonl` row — out-of-sync is the addon-author bug class
that `check_panels` is designed to catch.

---

## §6 Worked example — adding a new addon

Suppose a contributor wants to add a "ucsc_track_picker" panel for
the cross_species_atlas that lets users pick a UCSC track to overlay
on the breakpoint coordinates.

```
1. Register the panel
   01_registry/panels.jsonl  +1 row:
     {"panel_id": "ucsc_track_picker",
      "schema_version": "panel_v1",
      "label": "UCSC track picker",
      "kind": "form",
      "atlas": "cross_species_atlas",
      "data_source": {"kind": "registry",
                       "reads": ["external_databases.jsonl"]},
      "slot_affinity": ["conductor-demo", "rail-right"],
      "fluidity": {...},
      "dismissable": true,
      "status": "experimental"}

2. Register the spawn rule
   01_registry/spawn_rules.jsonl  +1 row:
     {"rule_id": "ucsc_track_picker_on_cross_species",
      "schema_version": "spawn_rule_v1",
      "when": {"page": ["candidate_review"],
                "scope": {"atlas": "cross_species_atlas"}},
      "then": {"spawn": [{"panel_id": "ucsc_track_picker",
                           "priority": 55}]}}

3. Add a renderer
   page/conductor.js — add renderUcscTrackPicker() + entry in
   RENDERERS dispatch table.

4. Verify
   python3 -m toolkit_registries.scripts.smoke_all_stack
   → 21/21 green, check_panels validates the new row + rule
```

No HTML changes to candidate_review.html. No registry FK changes.
The conductor finds the form-kind panel, spawns it into a slot, and
the renderer reads `external_databases.jsonl` to populate the UCSC
track list. Adding more renderers later (e.g. `chart` kind for the
actual track view) follows the same pattern.

---

## §7 What an addon CANNOT do

The §refusals enforced across the spec docs:

1. **No invented panel kinds.** Use one of §2's, or add yours to the
   catalogue first (renderer + doc + test).
2. **No invented data_source kinds.** §3's list is the universe.
3. **No invented spawn `when` keys.** §4's list is the universe.
4. **No spawning into slots that don't exist on the target page.**
   The conductor silently skips; debug via `?atlas_cache_debug=1`.
5. **No registry mutation from a panel.** Read-only. Mutations go
   through the dispatcher (manifests) or the librarian (registration).
6. **No cohort-crossing claims.** A panel scoped to one cohort never
   inherits results from another cohort's atlas.
7. **No agentic per-call indirection.** The conductor + bridge
   already give addons one-function-call surfaces; no SKILL.md /
   LLM-per-call inside an addon.

---

## §8 Quick lookup table — "I want to add X, what do I touch?"

| I want to add | touch |
|---|---|
| A new card on workspace_health | `panels.jsonl` + `spawn_rules.jsonl` + (maybe) a renderer |
| A new section on an existing page | edit the page HTML (`<div data-slot="...">`) + spawn rules |
| A new top-nav page | new `page/<name>.html` + topnav patch on 14 pages + `pages.jsonl` row + `pageIdFromDoc()` map entry + `KNOWN_PAGE_IDS` enum entry + optional `docs/<name>.md` |
| A new analysis | `analysis_registry` + `analysis_modes` + `module_registry` + 0+ `layer_registry` rows |
| A new external DB | `external_databases.jsonl` + `bridge/<db>/endpoints.json` + `bridge/<db>/LICENSE_NOTICE.md` |
| A new validator | `scripts/check_<thing>.py` + `smoke_all_stack` step |
| A new manuscript chunk | `manuscript_chunks.jsonl` + (maybe) new rows in `references.jsonl` |
| A new spawn predicate | extend `conductor.js` match logic + `check_panels` validator |
| A new panel kind | extend `conductor.js` RENDERERS + this doc's §2 catalogue + worked example |

---

## §9 Files added by this spec

- `ADDON_SPEC.md`     (this file)

No registry rows. No code. Pure documentation.

Future amendments:
- A `check_addons.py` validator that walks an addon's manifest and
  verifies every claimed row resolves cleanly. (Requires first
  defining `addon_manifest_v1` — the addon's claim list.)

Landed since v0:
- ~~A formal `pages.jsonl` schema with slot inventory per page~~ —
  shipped: pages.jsonl carries `slots: [...]` on every row, derived
  from each page's `<div data-slot="...">` declarations, and
  `check_panels` rejects spawn rules whose slot_affinity has no
  overlap with the target page's slots. The `KNOWN_PAGE_IDS` enum
  inside `check_panels` is no longer hardcoded — it's derived from
  pages.jsonl directly. Step 4 of §5 (the `pageIdFromDoc()` map
  edit) is still required for the runtime page identifier, but the
  audit chain is registry-driven end-to-end.

---

_End of ADDON_SPEC.md (v0)._
