# REGISTRY_LOOKUP — the (groups × analysis × samples × intervals) collapse

**Problem (verbatim from the design discussion):**

> If we register so many groups, we need to have set operations.
> groups × analysis × samples × intervals.

The naive design materializes every combination. With 50 named groups,
10 analyses, several interval choices (per-chrom × 28 + whole-genome +
candidate-scoped), the registry explodes into 100k+ entries before any
real intersections (HOM_INV ∩ ancestry_3 ∩ family_F042 …) are considered.

This doc is the design rule that prevents the explosion.

---

## The rule, in one sentence

> **Groups are named and finite. Sample sets are content-hashed and
> derived on demand. Results are identified by the content of their
> inputs, not by the route that named them.**

Two different group-naming routes that arrive at the same 50-sample
list **share** the same `sample_set_id` and hit the **same** result.
The registry stores one row per *distinct computation actually
performed*, never per cartesian-product cell.

---

## The three concepts, separated

| Concept | What it is | Identity | Schema |
|---|---|---|---|
| **Group** | Named, intent-tagged subset (`inv_LG28_HOM_INV`, `ancestry_K8_cluster3`, `family_F042`, …) | by `group_id` | `group_definition.schema.json` |
| **Sample set** | Sorted, deduplicated list of `sample_id`s used by ONE computation | by **content hash** of the sorted members | `sample_set_v1.schema.json` |
| **Result** | One analysis run against (sample set, input artifacts, params) | by **content hash** of `(analysis_id, sample_set_id, sorted(input_artifact_ids), params_hash)` | `analysis_result_v1.schema.json` |

Group registry stays small (hundreds of entries, append-only).
Sample-set table grows only when someone actually computes something.
Result table is a unique-index pointing at the layer envelope.

---

## Set algebra — six ops, composable

`sample_set_v1.derived_from.op` is one of:

| op | semantics | parents |
|---|---|---|
| `from_group`  | identity wrap around a single named group | `[group_id]` |
| `from_inline` | explicit sample list (ad-hoc, throwaway) | (`members` carries the list) |
| `intersect`   | members in **all** parents | 2+ group_ids or set_ids |
| `union`       | members in **any** parent | 2+ group_ids or set_ids |
| `difference`  | `parents[0]` minus the union of `parents[1..]` | 2+ |
| `filter`      | subset of one parent by a named predicate | `[single_parent]` + `predicate` tag |

Parents may be `group_id`s or other `sample_set_id`s — composition is
recursive. The library (`lib/set_algebra.py`) walks the tree, resolves
each `from_group` via the caller-supplied `GroupResolver`, and applies
the op.

**Why six and not three:** `from_group` + `from_inline` give you a
canonical entry point for the two terminal cases (named atomic vs
ad-hoc explicit). `filter` covers the common "drop samples missing X"
case without forcing an `intersect` with a synthetic ALL-with-X group.
You can survive with three (intersect/union/difference + always wrap
atoms in from_group), but the six-op form is more honest about intent.

---

## Content identity collapses the explosion

The key insight: when two routes produce the same member list, they
must produce the same `sample_set_id`.

```python
sample_set_id = "sset_" + sha256(sorted(members).join("\n") + "\n")[:16]
```

Worked example — three different routes, one `sample_set_id`:

```python
# Route A — direct intersection of named groups
expr_A = SetExpr.intersect("inv_LG28_HOM_INV", "ancestry_K8_cluster3")
members_A = materialize(expr_A, resolver)
# → ["CGA042", "CGA118"]
sid_A = sample_set_id(members_A)  # "sset_c8d4e2a1f6e09387"

# Route B — chain through a pre-registered sample set
expr_B = SetExpr.intersect("sset_a3f9e1c2d4b7e028",      # ancestry_3 materialized
                           "inv_LG28_HOM_INV")
members_B = materialize(expr_B, resolver)
# → ["CGA042", "CGA118"]
sid_B = sample_set_id(members_B)  # "sset_c8d4e2a1f6e09387"

# Route C — explicit inline list, computed by hand
expr_C = SetExpr.inline(["CGA118", "CGA042"])  # different order
members_C = materialize(expr_C, resolver)
# → ["CGA042", "CGA118"] (sorted)
sid_C = sample_set_id(members_C)  # "sset_c8d4e2a1f6e09387"

assert sid_A == sid_B == sid_C
```

All three look up the **same** `analysis_result_v1` row, point at the
**same** layer envelope, never recompute.

---

## Result identity — four components, one hash

```python
result_id = "res_" + sha256(
    f"{analysis_id}|{sample_set_id}|{','.join(sorted(input_artifact_ids))}|{params_hash}"
)[:16]
```

Where:

| Component | What it pins down |
|---|---|
| `analysis_id`         | which tool (`ngsrelate`, `mendelian`, `fst_pairwise`, `theta_pi`) |
| `sample_set_id`       | which samples (content-hashed; sort-invariant) |
| `input_artifact_ids`  | which beagle / sites / Q matrix / etc. (sort-invariant) |
| `params_hash`         | sha256 of canonical-JSON params (key-order-invariant) |

Two analyses that match on all four hit the same row, period. Any
single bump (different tool version, different sample, different input
file, different parameter) produces a new `result_id`.

Order-invariance is enforced by the hashing library
(`lib/set_algebra.py`): artifacts and params are sorted before
hashing. The smoke test at the bottom of that file verifies this.

---

## How a query flows

```
User wants:  "ngsRelate for HOM_INV ∩ ancestry_3 on the LG28 beagle".

1. Build a SetExpr:
       SetExpr.intersect("inv_LG28_HOM_INV", "ancestry_K8_cluster3")

2. Call lib/set_algebra.plan():
       plan(
         analysis_id        = "ngsrelate",
         expr               = expr,
         input_artifact_ids = ["beagle_LG28_v1", "sites_LG28_thin_v1"],
         params             = { "F_unknown": -1, "p": "ALL", ... },
         resolver           = atlas_resolver,    # reads groups + sample_sets
         index              = atlas_result_index # reads analysis_result_v1
       )

3a. status == "cached":
       result row found.
       return result["output_layer_id"]   ← Atlas renders that envelope.

3b. status == "todo":
       got back:
         { result_id, sample_set_id, members, n_members,
           input_artifact_ids, params_hash }
       Caller builds an action_manifest:
         {
           "action_id":      "act_<...>",
           "type":           "run_ngsrelate",
           "dataset_id":     "main_226_hatchery",
           "runner":         "runners.ngsrelate.run",
           "target":         { "members": members, "n_members": n_members },
           "params":         { ... },
           "expected_outputs": [ {
              "layer_type": "ngsrelate_result",
              "schema_version": "ngsrelate_result_v1",
              "_predeclared_result_id": result_id
           } ]
         }
       POSTs to /api/actions.
       On success, dispatcher:
         - writes a layer_envelope with layer_id = ngsrelate_result_<...>_v1
         - writes a sample_set_v1 row if sample_set_id is new
         - writes an analysis_result_v1 row pointing layer_id <- result_id
```

The action endpoint is the same one from `PIPELINE_FLOW.md`. The
LOOKUP happens BEFORE the action is submitted, which is why the action
endpoint never has to special-case "already done" — the caller's plan
step handles it.

---

## What stays small, what stays large

| Table | Growth rate | Storage |
|---|---|---|
| `group_definition`        | with named groups (~100s lifetime) | linear |
| `sample_set_v1`           | with **distinct** materialized sets that produced a result | sub-linear — collisions on intent are common |
| `analysis_result_v1`      | with **distinct** computations actually performed | linear in real work |
| `layer_envelope` files    | one per result + one per imported staging set | same as result table |

The cartesian (50 groups × 10 analyses × 29 intervals × …) never
materializes. Only computations the user actually requested do.

---

## What the existing system already does

Some of this is already implemented at the server level — we're
generalizing it to the registry level.

| Existing behaviour | File | What it is |
|---|---|---|
| Canonical sorting of groups for cache keying | `server/atlas_server.py:_canonical_groups` | Same sort-and-hash pattern; per-endpoint |
| `popstats_cache_key`, `hobs_cache_key`, `ancestry_q_cache_key` | `server/atlas_server.py` | Per-subsystem content hashes |
| Persist hook for content-addressed operation results | `core/registry_core.js:_persistOperationResult` + `core/registry_core.schema.json:layer_entry.persist` | `cache_layout: "content_addressed"` already keys cache by `{op_id}/{hash}.json` |

The new schemas (`sample_set_v1` + `analysis_result_v1`) **lift** that
pattern out of per-endpoint cache-key code and make it a first-class,
durable registry concept — so the same content-identity logic applies
to file-source layers, browser-side analyses, manually imported tables,
and server compute alike.

---

## What this doc does NOT do

- **Does not invent set-operation execution.** Materialization is
  pure Python set ops (`&`, `|`, `-`) on sorted member lists. No SQL,
  no graph DB.
- **Does not freeze the group_definition schema.** It stays as the
  canonical store for named, intent-tagged groups. `sample_set_v1` is
  parallel, not a replacement. A `from_group` sample-set is the bridge
  between them.
- **Does not require a new action endpoint.** `plan()` is a pure
  function the caller can run in browser JS, Python, or anywhere else.
  The action endpoint stays as defined in `PIPELINE_FLOW.md`.
- **Does not handle group versioning.** That's still
  `DATABASE_DESIGN.md §"Group versioning"`: a group's `created_at`
  timestamp is its version, and `analysis_result_v1` records the
  `created_at` of every parent group at compute time. A change to a
  group's members produces a new `sample_set_id` automatically (the
  content hash is different), so the lookup naturally yields a miss
  and the analysis re-runs.

---

## Per-atlas wiring — minimum to use this today

Each atlas's dispatcher (per `PIPELINE_FLOW.md §"Per-atlas wiring"`)
adds a `lookup_step` between manifest validation and runner dispatch:

```python
# inside dispatcher.dispatch_action(manifest, server_client):

from atlas_core.toolkit_registries.lib import set_algebra

# 1. Parse the expression the manifest carries
expr = set_algebra.SetExpr(**manifest["target"]["sample_set_expr"])

# 2. Plan
plan = set_algebra.plan(
    analysis_id        = manifest["type"],                  # 'run_ngsrelate' or similar
    expr               = expr,
    input_artifact_ids = manifest["target"]["input_artifact_ids"],
    params             = manifest.get("params", {}),
    resolver           = atlas_resolver,
    index              = atlas_result_index,
)

if plan["status"] == "cached":
    return {"action_id": manifest["action_id"],
            "produced_layers": [plan["result"]["output_layer_id"]],
            "cache_hit": True}

# 3. Dispatch the runner as usual; pass plan["members"] as the materialized set
raw = runner.run({**manifest, "_resolved_members": plan["members"]}, server_client)

# 4. Wrap output in a layer envelope (per PIPELINE_FLOW.md)
envelope = wrap_payload(...)

# 5. Persist the analysis_result_v1 row
result_row = {
    "result_id":         plan["result_id"],
    "analysis_id":       manifest["type"],
    "sample_set_id":     plan["sample_set_id"],
    "input_artifact_ids": plan["input_artifact_ids"],
    "params_hash":       plan["params_hash"],
    "params":            manifest.get("params", {}),
    "output_layer_id":   envelope["layer_id"],
    "status":            "active",
    "created_at":        now_iso(),
    "created_by_action_id": manifest["action_id"],
}
persist_result_row(result_row)
```

That's the whole integration. Five steps, plus whatever the runner
already does. The dispatcher gets to skip work whenever the lookup hits.

---

## What this lets the user do

Per the problem statement:

> Once that is passed to ngsRelate it needs to verify are all bam in
> the correct order the same as in the sample order in the list of
> bamfiles, is the sample count the same or not, so it must ask the
> group registry, then what interval do we use, is it whole genome or
> per chromosome, so that asks the interval registry. do we already
> have results for that? do we already have a .res for interval genome
> wide for this group of samples? yes and no.

Every one of those questions is answered by `lib/set_algebra.plan()`:

- **"Same sample order?"** — the dispatcher resolves `members` from
  the expression; the runner checks `members` against the beagle's
  `sample_list_v1` order before invoking ngsRelate.
- **"Same sample count?"** — `n_members` is in the plan output.
- **"Which interval?"** — encoded as input artifact IDs
  (`beagle_LG28_v1` vs `beagle_whole_genome_v1`). Each is a layer.
- **"Do we already have a .res?"** — that's exactly `status: "cached"`.

The lookup is one function call. The library does not care which atlas
called it.
