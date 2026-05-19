# DISPATCHER_SPEC — the action-proposing layer

Status: **v0 (frozen)**.  Schema version: `dispatcher_plan_v1`.

> The librarian resolves layer state.
> The manager classifies product readiness + estimability.
> **The dispatcher proposes the next concrete action.**

The dispatcher is the third tier above the registry — and the LAST that
ever writes JSON the runner cares about.  Even so, **the dispatcher does
not execute anything.**  It writes `action_manifest_v1` JSON files into a
queue directory.  An external runner (e.g. `POST /api/actions` from PR
\#3, or a shell loop, or a human) is what picks them up.

This preserves the system's §refusals: connect ≠ resolve ≠ run.

---

## §1 The three-tier picture (updated)

```
  Question
      │
      ▼
  ┌───────────────────────┐
  │  Manager              │   "is the product ready?"  "what can we estimate?"
  └──────────┬────────────┘
             │
             ▼
  ┌───────────────────────┐
  │  Dispatcher (this PR) │   "for the things that aren't ready,
  └──────────┬────────────┘    propose one action_manifest per missing producer"
             │
             ▼  writes to 02_queue/<action_id>.json
  ┌───────────────────────┐
  │  Runner (out of scope)│   POST /api/actions, biomod, shell loop, …
  └───────────────────────┘
```

---

## §2 What the dispatcher does

For a given `question_id` + scope:

1. Call `Manager.check_question_readiness(qid, scope)`.
2. For every required product with `status in {missing, blocked}`:
   - If the product's `produced_by.analysis_id` is registered → build one
     `action_manifest_v1` from `analysis_registry[analysis_id]`.
   - Otherwise → emit a `register_producer` advisory (no manifest written).
3. De-duplicate: one manifest per producing `analysis_id` even when it's
   the producer of multiple missing products.
4. Return a `dispatcher_plan_v1` object listing the manifests.
5. **If `--commit`**: write each manifest to `02_queue/<action_id>.json`.

---

## §3 The §refusals

1. **No execution.** Ever. The dispatcher only writes manifests.
2. **No invented runners.** If `analysis_registry.default_runner` is
   empty for the producing analysis, the dispatcher falls back to
   `runners.<analysis_id>.run` (the convention) but never invents a path
   to an unregistered analysis.
3. **No producers minted.** If a missing product has no `produced_by` set,
   the dispatcher emits a `register_producer` advisory; it will NOT mint
   a manifest with a guessed runner.
4. **No write-back to the registries.** Only `02_queue/` is touched.

---

## §4 Action manifest shape (`action_manifest_v1`)

Each manifest follows `schemas/registry_schemas/action_manifest.schema.json`
from PR #2.  Example (produced for `inversion_pair_incompatibility_LG01_LG28`):

```json
{
  "schema_version":   "action_manifest_v1",
  "action_id":        "act_1779178311578_inversio_eoj",
  "type":             "run_inversion_pair_incompatibility",
  "dataset_id":       "samples_226_v1",
  "runner":           "analysis.inversion_pair_incompatibility.adapter_atlas",
  "target":           { "sample_set": "samples_226_v1",
                        "interval_set": "inv_LG28_INV_001_v1" },
  "params":           {},
  "expected_outputs": [{ "layer_type": "inversion_pair_distortion_LG01_LG28.v1",
                          "schema_version": "inversion_pair_distortion_LG01_LG28.v1_v1",
                          "stage": "normalized" }],
  "submitted_by":     "lib.dispatcher",
  "submitted_at":     "2026-05-15T11:31:51Z",
  "notes":            "proposed by dispatcher for question 'inversion_pair_incompatibility_LG01_LG28'",
  "_dispatch": {
    "question_id":  "inversion_pair_incompatibility_LG01_LG28",
    "produces":     "inversion_pair_distortion_LG01_LG28.v1",
    "analysis_id":  "inversion_pair_incompatibility",
    "reason":       "manager readiness reported this product as missing/blocked"
  }
}
```

The `_dispatch` subobject is the dispatcher's own provenance — runners
ignore it, but page 10 / future debug views can show *why* this manifest
exists.

---

## §5 CLI

```
python3 -m lib.dispatcher --question <qid> [--sample-set X] [--interval-set Y] [--candidate Z]
                          [--commit]               # default: dry run
python3 -m lib.dispatcher --list                    # show what's queued
python3 -m lib.dispatcher --clear [--yes]           # empty 02_queue/
```

`--commit` is required to actually write files.  Without it the dispatcher
prints exactly what it WOULD queue — useful for review meetings.

---

## §6 Queue directory layout

```
02_queue/
├── act_<ts_ms>_<analysis>_<3char>.json     one per proposed action
└── …
```

`act_id` convention: `act_<unix_ms>_<analysis_id[:12]>_<3-char>`. Stable,
sortable by time, runner-friendly.

---

## §7 What's deferred

- **No real runner.** Lands when `POST /api/actions` (PR #3) is wired to
  poll `02_queue/`, or a shell loop is acceptable.
- **No queue UI.** Today the dispatcher CLI lists queued manifests.
  A page (probably page 11 — "Queue") will visualise + claim them.
- **No retry / backoff / status.** A future v1 will track per-manifest
  state (queued → running → succeeded / failed).  v0 is fire-and-forget.

---

_End of DISPATCHER_SPEC.md (v0)._
