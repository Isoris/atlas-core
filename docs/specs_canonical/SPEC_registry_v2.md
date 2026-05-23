# SPEC_registry_v2 — atlas registry, the design we'll actually build

**Status:** specification, no code yet. To be reviewed before any
schema/layer change lands.
**Supersedes:** the two earlier critique docs
(`REGISTRY_PROPOSAL_CRITIQUE.md`, `REG_DOLLAR_REVISITED.md`) and the
lane-B sketch (`LANE_B_PLAN.md`). Those were intermediate; this is
the consolidated answer.
**Companion:** `DATA_DOMAINS.md` (to be written) — the ground-truth
inventory the spec is verified against.

---

## 0. The design rule

> **One resolver, four source kinds, one write path, three new
> first-class entities, one written domain inventory. Nothing else.**

Everything else in either of the previous proposals (a `reg$`
god-object, parallel storage hierarchies, per-tool API methods) is
explicitly out of scope. If the spec doesn't list it, we don't build
it.

---

## 1. What we have today (so we don't redesign it)

### Three layers, already correct

```
                  ┌──────────────────────────────────────────┐
                  │  Pages (UI)                              │
                  │   read state, call analysis or registry, │
                  │   render returned values                 │
                  └─────────────┬──────────────┬─────────────┘
                                │              │
                ┌───────────────▼──┐      ┌────▼────────────┐
                │ analysis/*.js    │      │ registry        │
                │   (the science)  │──────►   .resolve()    │
                │                  │      │   .write()      │
                │                  │      │   .invalidate() │
                └──────────────────┘      └────┬────────────┘
                                               │
                  ┌────────────────────────────▼──────────────┐
                  │ Source kinds (already implemented)        │
                  │   file       — fetch JSON/TSV from disk   │
                  │   operation  — POST to popstats_server.py │
                  │   inline     — embedded in config         │
                  │   analysis   — call browser-side module   │
                  └──────────────────┬────────────────────────┘
                                     │
              ┌──────────────────────▼──────────────────────┐
              │ popstats_server.py on LANTA (over SSH tunnel)│
              │   12 GET/POST endpoints                      │
              │   POST /file/{path}  ←  the write endpoint   │
              └──────────────────────┬──────────────────────┘
                                     │
              ┌──────────────────────▼──────────────────────┐
              │ Toolkit registries (R/Python/bash, on disk) │
              │   sample / interval / evidence / results    │
              │   FK discipline, integrity checks           │
              └─────────────────────────────────────────────┘
```

This stack is **the spec**. The v2 work below adds three entities, one
method, one event hook, and one inventory doc. That's all.

### Existing surface, summary

- 37 layers in `layers.registry.json` (10 candidate_*, 6 cohort_*,
  3 band_*, etc.)
- 8 server operations (popstats / ancestry / dosage / LD)
- 8 file scopes including 1 with `writable: true` (the
  `review_session_writes` precedent)
- 4 source kinds: `file | operation | inline | analysis`
- 3 cache tiers: `hot | warm | cold`
- 5 preload events: `chrom_change | candidate_change | page_mount |
  viewport_change | explicit`
- 2 conflict-resolution flags on layer entries: `provisional | owned_by`
- Toolkit registries with `result_row.provenance.config_hash` +
  `who.group_version` for stale detection on the manuscript side

None of this changes in v2.

---

## 2. What v2 adds (and only this)

| # | Addition | Lives in | Effort |
|---|---|---|---|
| 1 | `candidate_versions` first-class entity | toolkit + browser layer entries | 2 sessions |
| 2 | `candidate_active_version` pointer | toolkit + browser layer entry | (part of 1) |
| 3 | Ground-truth `relatedness` schema (replace placeholder) | atlas schemas/ | 0.5 session |
| 4 | `Registry.write(key, args, payload)` method | core/registry_core.js | 0.5 session |
| 5 | Transitive cache invalidation on candidate_change | core/registry_core.js | 0.5 session |
| 6 | `mendelian_inheritance.schema.json` structured block | toolkit | 0.5 session |
| 7 | `analysis/mendelian_inheritance.js` orchestrator | atlas analysis/ | 1 session |
| 8 | Server-side path allowlist for `POST /file/{path}` | server | 0.5 session |
| 9 | `DATA_DOMAINS.md` inventory doc | atlas-core/docs/ | 0.5 session |

**Total: ~6 sessions.** Items 1, 3, 8, 9 are independent and
parallelisable. Item 7 needs 1, 4, 6.

---

## 3. The three new first-class entities (item 1)

### 3.1 `candidate_versions.tsv` — append-only version history

One row per (candidate_id, version_id). Append-only, never rewritten.
Old versions get `status="deprecated"` rather than being deleted.

| Field | Type | Purpose |
|---|---|---|
| `candidate_id` | string | FK → `candidate_intervals.candidate_id` |
| `version_id` | string | unique within candidate; e.g. `v1_localPCA_initial`, `v2_theta_refined` |
| `chrom` | string | version-specific boundaries |
| `start_bp` | int | |
| `end_bp` | int | |
| `source_methods` | array | e.g. `["localPCA","thetaPi"]` |
| `parent_version_id` | string \| null | previous version this was refined from (in-lineage DAG) |
| `active_callset_id` | string | name of the karyotype callset bound to this version |
| `status` | enum | `initial \| refined \| final \| deprecated` |
| `created_at` | ISO timestamp | doubles as version-version (mirrors `sample_groups.created`) |
| `dependency_hash` | short hash | sha1 over `{chrom, start_bp, end_bp, active_callset_id, sorted(source_methods)}` |
| `notes` | string | free text, not analysis-relevant |

### 3.2 `candidate_active_version.tsv` — rewrite-in-place pointer

One row per candidate. Updated when active version changes.

| Field | Type | Purpose |
|---|---|---|
| `candidate_id` | string | PK, FK → `candidate_intervals.candidate_id` |
| `active_version_id` | string | FK → `candidate_versions.version_id` |
| `set_at` | ISO timestamp | when this version became active |

### 3.3 Minimal change to `candidate_intervals.tsv`

Add one optional field: `status` ∈ `{active, split, deprecated}`,
default `"active"`. **No other change.** Existing
`{chrom, start_bp, end_bp}` fields stay; on every `set_active_version`
operation, the toolkit copies the active version's boundaries into
the candidate row so legacy readers see consistent values without
needing to know about versions.

### 3.4 Versions ≠ splits

The two operations are distinct:

| Operation | Effect |
|---|---|
| **Boundary refinement** | New row in `candidate_versions`, optionally update active pointer. Lineage stays the same. |
| **Split into children** | Set parent's `candidate_intervals.status="split"`. Create new candidates with `parent_id=parent_cid` (existing field). Each child gets its own version history. |

This is the single most important design call in the spec, and it's
what the proposals confused. Splits use the existing `parent_id`
mechanism on `candidate_intervals`. Versions are a new dimension
within an unchanged candidate.

---

## 4. The relatedness schema (item 3)

Replace the empty placeholder
`inversion-atlas/atlases/inversion/registries/schemas/relatedness.schema.json`
with a real schema for ngsRelate output. The columns ngsRelate
typically writes:

| Column | Type | Notes |
|---|---|---|
| `a` | int | sample index, primary |
| `b` | int | sample index, secondary |
| `nSites` | int | sites compared |
| `J7`, `J8`, `J9` | float | IBD probability components |
| `theta` | float | kinship coefficient |
| `rab`, `Fa`, `Fb` | float | inbreeding-related |
| `IBS0`, `IBS1`, `IBS2` | float | IBS state proportions |
| `Rxy`, `Rab` | float | relatedness statistics |
| `loglh`, `nIter` | float, int | optimization metadata |

**One schema file, one layer entry, no per-tool API methods.** When
KING / hap-IBD / etc. get wired, each gets its own
`relatedness_<tool>.schema.json` and its own layer entry. The atlas
state holds `state.relatedness.activeTool` as an enum so pages know
which layer to ask for.

**Layer entry shape:**

```jsonc
"cohort_relatedness": {                  // existing key, kept for backward compat
  "tier": "warm",
  "source": "file",
  "path": "data/relatedness/{tool}/{run_id}/relatedness.tsv",
  "format": "tsv",
  "schema": "schemas/relatedness_ngsrelate.schema.json",
  "schema_status": "validated",
  "fields": null    // optional column subset; null = return all
}
```

The `fields` field is added at this point. When the analysis module
asks for only 5 columns out of 19, the parser drops the rest before
caching. This requires a small change to `layer_router.js` (~10 LOC).

---

## 5. `Registry.write(key, args, payload)` (item 4)

### Contract

```js
const result = await registry.write('mendelian_inheritance_block', {
  candidate_id: 'LG28_INV_001',
  version_id:   'v2_theta_refined',
}, mendelianResult);
// → { ok: true, path: '...', bytes: 1234 }
```

### Implementation rules

1. **Layer must declare `writable: true`** — same flag as on file
   entries. Adding it to `layer_entry` schema is a 2-line meta-schema
   change.
2. **The layer's `path` template substitutes args** — same templating
   `resolve()` already uses.
3. **Schema validation runs before sending.** If the payload fails
   the layer's schema, throw locally; don't call the server.
4. **The HTTP transport is `POST /file/{path:path}`** — already
   exists at `popstats_server.py:1365`. Body is the serialised
   payload (JSON for JSON layers, raw bytes for binary).
5. **On success, invalidate own cache entry.** Next `resolve()` reads
   from disk, picks up the new value.
6. **No retries, no queue.** Atlas is not a write-heavy system. If
   the server is down, the write fails loudly.

### What it does NOT do

- It does NOT create a parallel storage hierarchy. The path always
  points into the toolkit's `evidence_registry/per_candidate/<cid>/structured/`
  or `results_registry/...` directory.
- It does NOT bypass the toolkit. The write lands in the same place
  R-side `reg$evidence$write_block(...)` would land, just from the
  browser.
- It does NOT compute provenance for you. The caller (analysis
  module) embeds `{candidate_version_id, callset_id, dependency_hash,
  ...}` in the payload itself.

---

## 6. Transitive cache invalidation on candidate_change (item 5)

### What it does

When `AtlasState.shared.activeCandidate` changes (or
`active_version_id` for the same candidate changes), the resolver
walks its hot+warm caches and evicts every entry whose cache key
contains `:${old_candidate_id}:` or `:${old_version_id}:`.

### Implementation

```js
// In atlas_state.js setActiveCandidate, after emit:
this.registry.invalidateAllForCandidate(oldCandidate?.id);

// In registry_core.js:
invalidateAllForCandidate(candidate_id) {
  if (!candidate_id) return;
  const needle = `:${candidate_id}:`;
  for (const key of this.cache.hot.keys()) {
    if (key.includes(needle)) this.cache.hot.delete(key);
  }
  // Same for warm; warm is async-iterable.
}
```

> **Implementation note.** `atlas_state.js` has no `this.registry` reference
> today (see `core/atlas_state.js` constructor — only `serverBaseUrl` is
> stashed). Two options when wiring this: (a) inject the registry into
> `AtlasState` at bootstrap, or (b) have the registry subscribe to
> `shared.activeCandidate.changed` itself and call `invalidateAllForCandidate`
> in the subscriber. (b) matches the existing pattern — the prewarm
> scheduler already subscribes to the same event — and keeps AtlasState
> from holding a reference to the registry.
>
> **Prerequisite.** This whole section assumes `setActiveCandidate(cand)` is
> actually called when the user promotes a candidate. The migrated local_pca_dosage
> path (`pages/discovery/local_pca_dosage/candidates.js setCandidate()` +
> `loadCandidateList()`) now bridges into atlas-core's setter; before that
> bridge landed, the event never fired and this invalidation would have
> been a no-op for the only code path that matters.

~30 LOC including the warm-tier walk.

### What it does NOT do

- It does NOT walk dependency edges in a graph database.
- It does NOT mark anything as `stale=true`. The cache entry just
  vanishes; next `resolve()` re-reads.
- It does NOT touch cohort-level layers (`cohort_relatedness`,
  `cohort_diversity`, etc.) — their cache keys don't include
  `candidate_id`, so the substring match doesn't fire. **This is
  correct.** Refining one candidate must not invalidate cohort-wide
  results.

This is the cheapest possible correct solution. If we need
finer-grained dependency tracking later (e.g., invalidate only
results that include the changed version's `dependency_hash`), it's
a one-method extension, not a redesign.

---

## 7. `mendelian_inheritance.schema.json` (item 6)

A new structured-block schema in the toolkit at
`atlas-core/toolkit_registries/schemas/structured_block_schemas/mendelian_inheritance.schema.json`,
modelled on existing siblings (e.g. `boundary_refined.schema.json`).
Required fields per block:

```json
{
  "result_type":           "mendelian_inheritance",
  "candidate_id":          "LG28_INV_001",
  "candidate_version_id":  "v2_theta_refined",
  "callset_id":            "thetaRefined_K3_v2",
  "relatedness_result_id": "ngsrelate_v1_broodstock_qc_pass",
  "sample_set_id":         "natora_pruned_81",
  "analysis_version":      "mendelian_inheritance_v1.0",
  "dependency_hash":       "<sha1>",
  "thresholds": { "theta_min": 0.0884, "ibs0_max": 0.005, "..." : "..." },
  "metrics": {
    "n_pairs_tested":       null,
    "n_informative_pairs":  null,
    "n_contradictions":     null,
    "contradiction_rate":   null,
    "support_status":       "supported|inconclusive|contradicted"
  },
  "per_family": [ /* one row per family */ ],
  "per_pair":   [ /* one row per related pair */ ],
  "warnings":   [ /* free-text */ ],
  "created_at": "ISO timestamp"
}
```

The `dependency_hash` is computed by `mendelian_inheritance.js` from:

```
sha1({
  candidate_version_id, callset_id,
  relatedness_result_id, sample_set_id,
  analysis_version, sorted(thresholds.entries())
})
```

— and **only** those fields. Display-only metadata (notes, color,
review status) is NOT in the hash, so cosmetic edits to a candidate
never trigger re-runs. This is the precise boundary the proposals
asked for, written down once, in one place.

### Filename convention

```
evidence_registry/per_candidate/<cid>/structured/mendelian_inheritance.<version_id>.json
```

The version_id suffix lets us keep mendelian results for v1, v2, and
split children side by side without overwriting. The "current" one is
the one whose `candidate_version_id` matches the active version per
`candidate_active_version.tsv`.

---

## 8. `analysis/mendelian_inheritance.js` orchestrator (item 7)

### Position in the architecture

Sits next to the existing `analysis/mendelian.js` (which holds the
core math). The orchestrator's job is to:

1. Read inputs from the registry (no `fetch`, no path knowledge).
2. Filter / join / call core math from `mendelian.js`.
3. Build payload with `dependency_hash` and provenance fields.
4. Write result through `registry.write(...)`.
5. Return result to caller (the page).

### Signature

```js
export async function runMendelianInheritance({
  registry,
  candidate_id,
  version_id,           // optional; defaults to active version
  selectedFamilies,     // optional; null = all informative
  selectedSamples,
  thresholds,           // optional; defaults to spec defaults
  recompute = false     // if true, skip cache lookup
}) {
  // ... 3.1 resolve inputs
  // ... 3.2 compute dependency_hash, look up cached block
  // ... 3.3 if cached and !recompute, return
  // ... 3.4 filter, join, call core math
  // ... 3.5 build payload, validate against schema
  // ... 3.6 write back through registry.write(...)
  // ... 3.7 return payload
}
```

### What it does NOT do

- It does NOT know file paths. Inputs come from `registry.resolve(...)`,
  output goes through `registry.write(...)`.
- It does NOT decide what's an inversion. It validates a *given*
  callset's Mendelian behaviour.
- It does NOT compare versions. The page can call it three times for
  three versions and compare in JS. The orchestrator is single-version.

---

## 9. Server-side path allowlist (item 8)

Currently `POST /file/{path:path}` writes any path under the project
root. For v2, restrict to:

```python
ALLOWED_WRITE_PATTERNS = [
    r"^evidence_registry/per_candidate/[A-Za-z0-9_]+/structured/[A-Za-z0-9_.-]+\.json$",
    r"^results_registry/[A-Za-z0-9_./-]+\.(tsv|json)$",
    r"^session/[A-Za-z0-9_.-]+\.json$",  # for review_session_writes precedent
]
```

If none match, return 403. ~15 LOC at the top of `file_post()`.

This closes the only real security hole in the architecture as it
stands. Browser-side analysis can write back, but only into the
canonical evidence/results paths.

---

## 10. `DATA_DOMAINS.md` inventory (item 9)

A single doc in `atlas-core/docs/` listing every biological data
domain the atlas serves. Format:

```markdown
## <domain>

- **Layer prefix:** `<prefix>_*`
- **Existing layers:** N (list)
- **Schema status:** validated / pending / placeholder
- **Source kind(s):** file / operation / analysis
- **Writable from browser:** yes / no
- **Cache tier(s):** hot / warm / cold
- **Server endpoints:** (if any)
- **Toolkit table:** (e.g. `evidence_registry/per_candidate/.../<block>`)
- **Example consumers:** (local_pca_dosage, boundary_refinement, ...)
```

Entries: `samples`, `relatedness`, `ancestry`, `diversity`,
`localPCA`, `inversion_candidates` (incl. versions), `sv`, `markers`,
`recombination` (future), `crossSpecies`, `burden` (future),
`repeats`, `phylo`, `catalogues`.

This is the "don't forget anything" guarantee, in a form that can be
diffed in PRs and updated as new layers wire up. **Not** a runtime
object.

---

## 11. What's explicitly NOT in v2

- ❌ Global `reg$` object. Same name as toolkit R-side `reg$`. The
  37-layer namespace is the registry; pages use `registry.resolve(...)`
  directly. If a domain facade is wanted later as syntactic sugar
  (~200 LOC, post-v2), name it `domain` or `atlas$`, not `reg$`.
- ❌ Per-tool API methods like `reg$.relatedness.getResult('ngsrelate', ...)`.
  Tool name is an argument, not a method.
- ❌ Parallel storage trees like `04_intermediate/` or `05_catalogues/`.
  The toolkit's `evidence_registry/per_candidate/` and
  `results_registry/` are the canonical homes; we use them.
- ❌ Browser-side discovery of relatedness/ancestry folders. The
  atlas knows path templates; discovery is pipeline-side or
  manuscript-side.
- ❌ A separate `candidate_callsets.tsv` table in v2.
  `active_callset_id` is a string field on `candidate_versions`. Add
  the table only when a callset is shared across versions or
  validation needs grow.
- ❌ A graph-database dependency tracker. Substring match on
  `:${candidate_id}:` in cache keys is enough; dependency_hash on
  result payloads catches the rest at read time.
- ❌ Auth for `POST /file/{path}` beyond path allowlisting. The
  server is on a tunneled LANTA session. Real auth is a v3 concern.

---

## 12. Architecture readiness check (verified against current state)

For each domain in the proposed inventory, does v2's plumbing cover
the chain "compute → save → invalidate stale → next page reads
fresh"?

| Domain | Today | After v2 | Gap? |
|---|---|---|---|
| samples | ✅ existing layers, no writes | unchanged | none |
| relatedness | ⚠️ placeholder schema | real schema + ngsrelate layer | closes |
| ancestry | ✅ server operation | unchanged | none |
| diversity | ✅ file + operations | unchanged | none |
| localPCA / band tracking | ✅ existing layers | unchanged | none |
| inversion candidates | ⚠️ flat, no versions | versioned, write-back via registry | closes |
| sv | ✅ existing layers | unchanged | none |
| markers | ✅ stub | unchanged (real schema later) | minor |
| recombination | ❌ none | unchanged (future content) | future |
| crossSpecies | ✅ one layer | unchanged | none |
| burden | ❌ none | unchanged (future content) | future |
| repeats | ✅ existing layers | unchanged | none |
| phylo | ✅ existing layer | unchanged | none |
| catalogues | ✅ via `manual_review_queue` etc. | adds `promoteToCatalogue` action via Registry.write | closes |

**Conclusion: v2 closes every "today gap" relevant to the manuscript
chain (versioning, relatedness schema, write-back). The future ❌
domains slot into the existing framework without further architectural
change.**

---

## 13. Three open questions for you

The same three from the lane-B sketch, surfaced here so the spec can
be finalised:

1. **Where do ngsRelate output files live on LANTA today?** I'll write
   the schema against the real columns. If they don't exist yet,
   I'll mock with the canonical ngsRelate columns and note the path
   as a TODO at the top of the layer entry.

2. **`active_callset_id` as a string field, or a proper
   `candidate_callsets.tsv` table?** Default: string field for v2,
   defer the table until a real conflict shows up.

3. **Server-side path allowlist (default), or full schema validation
   server-side from day one?** Default: allowlist. Browser validates
   payload before sending; server only checks the path is in a
   permitted directory.

If you give one-line answers to those, the next chat can start
drafting `candidate_version.schema.json` against ground-truth
conventions.

---

## 14. Final mental model (one screen)

```
   pages       →  state, registry.resolve(), call analysis, render
   analysis    →  the science: pull ingredients via registry,
                  filter, join, compute, write through registry
   registry    →  data access, caching, schemas, write path
                    .resolve(key, args)        — read cached/fresh
                    .write(key, args, payload) — write through to canonical store
                    .invalidate(key, args)     — drop one cache entry
                    .invalidateAllForCandidate(cid) — drop all candidate-scoped entries

   Source kinds: file | operation | inline | analysis
   Cache tiers:  hot | warm | cold
   First-class entities: candidate, candidate_version, callset (string for now)
   Dependency hash: sha1 of analysis-relevant fields only, embedded in payload
   Write transport: POST /file/{path:path} with server-side allowlist
   Inventory:    DATA_DOMAINS.md, single source of truth for "what we serve"
```

That's the spec. ~6 sessions to land. No god-objects, no parallel
hierarchies, no name collisions. Every plumbing addition is tied to
a real chain in the manuscript workflow.
