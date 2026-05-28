# HOWTO — using atlas-core day to day

A plain-language companion to the spec docs. If you read nothing else,
read this.

---

## What atlas-core is (and isn't)

It's a **filing system + dashboard** for the inversion project. It is
**not** a thing that runs analyses.

Three jobs, nothing more:

1. **Remembers what exists** — every analysis, result layer, candidate,
   and external database is written down as plain-text rows in
   `relatedness/01_registry/*.jsonl`. That's "the registry."
2. **Shows you the state** — the dashboard pages (`relatedness/page/*.html`)
   read those rows and draw cards: what's done, missing, runnable,
   ready to write up.
3. **Plans + records, doesn't execute** — when something needs running
   it writes a to-do note to `relatedness/02_queue/`; a separate runner
   picks it up. The actual computing lives in each atlas's `compute.js`.

**Mental model:** atlas-core is the *broker*, not the *executor*. The
atlases do the work; atlas-core makes it findable and composable. The
candidate (an inversion) is the *object*; every atlas's result is
*evidence that attaches to it*.

---

## The things you'll actually do

All commands run from the repo root (`atlas-core/`).

### "Show me everything about one inversion"

The headline feature. Pulls all per-atlas evidence for one candidate
into a single JSON:

```bash
python3 -m toolkit_registries.relatedness.lib.derived_object_harvester \
  --kind candidate --instance inv_LG28_INV_001 --stdout
```

- `--all` instead of `--instance <id>` → every candidate at once
- `--commit` → writes the JSON files to `02_queue/candidates/`
- `--kind LRR_regime` → harvest haplotype regimes instead of candidates

What you get: the candidate's interval + the popstats windows inside it,
the Mendelian rates, relatedness — joined from across the atlases. No
tab-hopping.

### "Let me look at the dashboard"

```bash
cd toolkit_registries/relatedness/page
python3 -m http.server 8000
# open http://localhost:8000/workspace_health.html
```

- `workspace_health.html` — overview: atlases, cohorts, bridges, addons,
  panel-coverage, the candidate count
- `candidate_review.html` — per-inversion view; the aggregate card
  (above) renders at the bottom for whichever candidate is in the scope
  ribbon
- `catalogue.html` — browse analyses + modules per atlas

### "Did I break anything?"

```bash
python3 -m toolkit_registries.scripts.smoke_all_stack
```

`26/26 passed` = every registry is internally consistent (no dangling
references, no invented kinds, harvester works, validators pass). Run
this before and after any change.

### "Look up a gene / domain / pathway from a public database"

The bridge tier — direct HTTP to 10 databases, no AI in the loop:

```bash
# list the databases
python3 -m toolkit_registries.relatedness.lib.bridge_client --list-dbs

# list one DB's endpoints
python3 -m toolkit_registries.relatedness.lib.bridge_client --db uniprot --list-endpoints

# e.g. UniProt entries for catfish (NCBI taxId 2724128)
python3 -m toolkit_registries.relatedness.lib.bridge_client \
  --db uniprot --endpoint search \
  --params "query=organism_id:2724128,format=json"
```

Databases: InterPro, UniProt, NCBI, PDB, UCSC, UniBind, STRING,
Reactome, PubMed, QuickGO. Cookbook + per-DB gotchas in `BRIDGE_USAGE.md`.

### "Refresh a paper citation from PubMed"

```bash
python3 -m toolkit_registries.relatedness.lib.refresh_references          # dry-run
python3 -m toolkit_registries.relatedness.lib.refresh_references --commit  # write it
```

### "Add a new thing (panel / page / analysis / database)"

Don't hand-edit blindly — every addition is declared as a registry row
and checked. The full recipe (the 7 addon kinds + what files each
touches) is in `ADDON_SPEC.md`. The short version:

| I want to add… | I touch… |
|---|---|
| a card on a page | `panels.jsonl` + `spawn_rules.jsonl` + a renderer in `conductor.js` |
| a whole page | new `page/<name>.html` + `pages.jsonl` row + topnav patch |
| an analysis | `analysis_registry.jsonl` + adapter folder under `analysis/<id>/` |
| an external DB | `external_databases.jsonl` + `bridge/<db>/` adapter |
| a new object kind | one row in `derived_objects.jsonl` |

Then run smoke. The validators (`check_*.py`) tell you if a row is
malformed or references something that doesn't exist.

---

## Where things live

```
toolkit_registries/relatedness/
├── 01_registry/      the plain-text rows — the source of truth
│   ├── *.jsonl       analyses, layers, modules, candidates, panels,
│   │                 pages, addons, derived_objects, external_databases
│   └── graphs/       derived dependency graphs (auto-regenerated)
├── 02_queue/         runtime notes: dispatched actions, harvested
│                     candidates, bridge call log (mostly gitignored;
│                     *.example.* files are shipped seeds)
├── 02_sets/          input sets (candidates, regimes, samples, sites)
├── 04_results/       analysis result files (popstats, mendelian, …)
├── lib/              the working code (harvester, bridge client,
│                     librarian, dispatcher, manager)
├── page/             the dashboard (HTML + conductor.js)
└── scripts/          the check_*.py validators

toolkit_registries/*.md   the specs:
  HOWTO.md (this)          day-to-day usage
  ADDON_SPEC.md            how to add anything (7 addon kinds)
  BRIDGE_USAGE.md          the 10 external databases, with recipes
  DYNAMIC_PANELS_SPEC.md   how the dashboard composes panels
  MERGE_PLAN.md            what's landed, what's open
```

---

## The golden rules

1. **The registry is the source of truth.** Pages read it; nothing
   writes back to it from a page.
2. **atlas-core never executes analyses.** It plans + records. The
   runner is separate; compute lives in each atlas.
3. **Cohort boundaries are sacred.** The 226-sample hatchery cohort,
   the F1 hybrid assembly, and the wild C. macrocephalus are never
   conflated. Coordinates can cross cohort lines; *claims cannot*.
4. **Run smoke before you trust anything.** `26/26` or investigate.

---

_If you're lost, start with the harvester command above on
`inv_LG28_INV_001` — seeing one real candidate end-to-end makes the
rest click._
