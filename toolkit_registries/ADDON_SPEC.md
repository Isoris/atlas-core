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
| **G. Derived object** | a new first-class synthesised object (candidate, LRR regime, breakpoint pair) that many analyses FK to + its harvester join spec | 1 row in `derived_objects.jsonl` (`derived_object_v1`) declaring `instance_layer` + `harvest[]` join modes; rows themselves live in the instance layer file |

The conductor + bridge + chain audit handle the wiring; the addon
contributes data + (optionally) a renderer if its panel kind is new.

A **derived object** (kind G) is the one addon that produces *no* new
primary data — it declares that a synthesised object (the rows of an
existing layer) is a first-class addressable subject, and how to
harvest its scattered evidence into one aggregate. Primary-data
registries declare what CAN be computed; the derived-object registry
declares what synthesised subjects the system addresses. The rows
still live in layer files — `derived_objects.jsonl` only declares the
*kind* + the join spec. See §11.

---

## §2 Panel kinds — canonical live catalogue

These are the `kind` values an addon can declare on a `panel_v1` row.
Each has a registered renderer (or a documented fallback) — using a
kind not on this list lands the "no renderer registered (TODO)"
dashed placeholder per DYNAMIC_PANELS_SPEC §11.

This table is the **operator's source-of-truth**. DYNAMIC_PANELS_SPEC
§2 mirrors the bare kind-enum but defers to this section for the
typical `data_source.kind`, registered examples, and the in-place
promotion process below — no `panel_v2` spec bump is required to
add a new kind.

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
- (none currently outstanding)

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
- ~~`check_addons.py` validator~~ — shipped: `addon_manifest_v1`
  schema lands in `addons.jsonl`; each row enumerates `claims`
  (registry filename → list of row ids it lands), `files` (relative
  paths the addon ships under `toolkit_registries/`), `renderers`
  (conductor.js dispatch entries), and `depends_on` (other
  addon_ids). `check_addons` validates every claim against the
  target registry's canonical id field (see `ID_FIELD_BY_FILE` in
  the script), every file path, every dep. Wired into smoke
  (22/22). See §10 below.

---

## §10 `addon_manifest_v1` — the row shape

Each addon registers itself in `01_registry/addons.jsonl` with this
row:

```json
{
  "addon_id":       "<unique id>",
  "schema_version": "addon_manifest_v1",
  "label":          "<human-readable>",
  "kind":           "<one of §1's six>",
  "owner":          "<attribution string>",
  "status":         "experimental | active | deprecated",
  "claims": {
    "panels.jsonl":      ["panel_id_a", "panel_id_b"],
    "spawn_rules.jsonl": ["rule_id_x"],
    "...":               ["..."]
  },
  "files":          ["bridge/<db>/endpoints.json", "..."],
  "renderers":      ["renderMyPanelCard"],
  "depends_on":     ["<other_addon_id>"],
  "extends_page":   "<page_id>",     // required when kind=page_extension
  "adds_slot":      "<slot_name>",   // required when kind=page_extension
  "describes":      "<freeform>"
}
```

Field semantics:

| field | meaning | validated by `check_addons` |
|---|---|---|
| `addon_id`       | unique row key | duplicate detection |
| `schema_version` | pin to `addon_manifest_v1` | exact match |
| `kind`           | one of §1's six | enum check |
| `status`         | lifecycle | enum check |
| `claims`         | registry filename → row ids landed | each id must exist in the target registry; registry filename must be known (see `ID_FIELD_BY_FILE` in `check_addons.py`) |
| `files`          | relative paths under `toolkit_registries/` | each must exist on disk |
| `renderers`      | conductor.js dispatch entries (advisory) | not enforced (lax — runtime would show the dashed TODO placeholder anyway) |
| `depends_on`     | other `addon_id`s | must resolve to another row |
| `extends_page`   | page_id this addon adds a slot to (page_extension kind only) | required when `kind=page_extension`; must resolve to a row in `pages.jsonl` |
| `adds_slot`      | slot name added to the host page (page_extension kind only) | required when `kind=page_extension`; the slot must appear in the host page's `slots` field after the HTML edit |

The validator catches the addon-author bug classes that the spec's
§7 "no invented kinds / data_sources / when keys" rule is designed
to surface — but at audit time, not at runtime when the conductor
silently drops the spawn.

### Worked example: `kind=page_extension`

The simplest demonstration of a page-extension addon lives in
`workspace_health_footer_extension`:

```jsonl
{"addon_id": "workspace_health_footer_extension",
 "schema_version": "addon_manifest_v1",
 "kind": "page_extension",
 "extends_page": "workspace_health",
 "adds_slot": "footer-row",
 "claims": {
   "panels.jsonl":      ["registry_health_strip"],
   "spawn_rules.jsonl": ["registry_health_strip_on_workspace_health"]},
 "files":     ["relatedness/page/workspace_health.html"],
 "renderers": ["renderRegistryHealthStrip"],
 "describes": "..."}
```

It ships four coordinated changes:

1. **HTML**: `workspace_health.html` gains
   `<div data-slot="footer-row" ...>` at the bottom.
2. **Registry**: the `workspace_health` row in `pages.jsonl` gets
   `"slots": ["conductor-demo", "footer-row"]`.
3. **Panel**: `registry_health_strip` lands in `panels.jsonl` with
   `slot_affinity: ["footer-row"]`.
4. **Spawn rule**: `registry_health_strip_on_workspace_health`
   targets the `workspace_health` page with priority 30.

`check_addons` enforces all four pieces are consistent. If the
extension forgets to update `pages.jsonl`, the validator fails with:

```
workspace_health_footer_extension.adds_slot: slot 'footer-row' not
in pages.jsonl row for 'workspace_health' (slots: ['conductor-demo'])
```

(Audit-time visibility for what would otherwise be a silent
conductor.pickSlot mismatch at runtime.)

---

## §11 Derived objects (`derived_object_v1`)

Primary-data registries declare **schemas of capability** (what can be
computed) and **schemas of structure** (what kinds of layers exist). A
*derived object* is a third schema: **what synthesised subjects the
system addresses.** An inversion candidate is the canonical example —
it has a stable id, an interval, and 8+ analysis-result layers carry
its `candidate_id` (or overlap its interval). The candidate is what the
manuscript *talks about*; the per-atlas results are evidence that
attaches to it.

The rows of each object still live in a layer file (the candidate rows
live in `inversion_candidates`/`candidate_registry`). `derived_objects.jsonl`
only declares the **kind** + how to **harvest** its evidence:

```jsonc
{"object_kind":     "candidate",
 "schema_version":  "derived_object_v1",
 "owning_atlas":    "inversion_atlas",
 "identity_keys":   ["candidate_id"],
 "spatial_keys":    ["chrom", "start", "end"],
 "instance_layer":  "inversion_candidates",
 "aggregate_schema":"candidate_aggregate_v1",
 "harvest": [
   {"analysis_type": "popstats",  "layer": "popstats_result",
    "mode": "spatial_window", "row_chrom": "chrom",
    "row_start": "start_bp", "row_end": "end_bp"},
   {"analysis_type": "mendelian", "layer": "mendelian_result",
    "mode": "chromosome"},
   {"layer": "candidate_registry", "mode": "direct_fk",
    "fk": "candidate_id"}],
 "lifecycle_states": ["discovery", "ranked", "validated",
                      "manuscript", "dropped"]}
```

### The three join modes

| mode | when | how the harvester joins |
|---|---|---|
| `direct_fk`      | result rows carry the object's id column | filter rows where `fk == instance_id` |
| `spatial_window` | result rows carry chrom + start + end | keep rows on the same chromosome whose `[start,end]` overlaps the instance interval |
| `chromosome`     | result file is per-chromosome (one file per LG) | attach the whole file to instances on that chromosome |

### The harvester

`lib/derived_object_harvester.py` is generic over `derived_objects.jsonl`.
For each instance it resolves result files via `analysis_results.jsonl`
(the run log) by matching `analysis_type` + the instance's chromosome
short-name against the result path, applies the per-source join mode,
and emits one `<aggregate_schema>` JSON under
`02_queue/<kind>s/<instance_id>.json`.

```bash
python3 -m toolkit_registries.relatedness.lib.derived_object_harvester --kind candidate --all
python3 -m ...derived_object_harvester --kind candidate --instance inv_LG28_INV_001 --stdout
python3 -m ...derived_object_harvester --kind candidate --all --commit
```

`check_derived_objects.py` validates the registry; the harvest is
exercised in smoke (`--kind candidate --all` → "2 candidate(s)
harvested"). §refusals: read-only, never mutates a registry, never
crosses cohort boundaries (the instance row carries its own cohort).

The pull-side promise: at any moment you can ask atlas-core for the
full record of candidate X and get one JSON aggregating every atlas's
evidence — no tab-hopping across per-atlas surfaces.

### Genericity — the 2nd object kind

`LRR_regime` (long-range haplotype regime) was added as the 2nd
derived-object kind with **zero harvester code change** — one row in
`derived_objects.jsonl` + a synthetic instance file
(`02_sets/regimes/lrr_regimes.tsv`). It reuses the same
`spatial_window` + `chromosome` join modes; the only differences are
`identity_keys` (`regime_id`) and `instance_layer`. The harvester reads
the join spec from the registry, so a 3rd kind (breakpoint_pair on the
cross-species side) is the same one-row addition. This is the payoff of
registering the *kind* rather than special-casing the harvester.

### The pull-side surface

`candidate_aggregate_card` (page 6, Candidate review) renders the
harvested JSON scope-aware: it reads
`02_queue/candidates/<scope.candidate_id>.json`, falls back to the
example seed, and shows one collapsible block per evidence layer. Pick
a candidate in the scope ribbon → see every atlas's evidence in one
pane.

---

_End of ADDON_SPEC.md (v0)._
