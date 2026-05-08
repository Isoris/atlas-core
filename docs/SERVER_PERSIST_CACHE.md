# SERVER_PERSIST_CACHE — how operation results land on disk

This doc covers the registry-v2 **persist hook**: when a registry layer
with `source: operation` returns from the server, the result is also
written to disk under a configured cache root. Subsequent identical
calls hit the disk cache instead of recomputing.

Read this when:
- You're adding a new server endpoint and wondering whether to mark its
  layer `persist: true`.
- A server result you expected to be cached is being recomputed every
  time.
- You need to clear the cache for a specific operation.
- Tarballing the project for the next chat and need to know what to
  exclude.

---

## The contract in one sentence

> **A layer with `source: operation` and `persist: true` writes every
> successful result to `_cache/server_results/{op_id}/{hash}.json` at
> the configured cache root, and pages keep using `registry.resolve()`
> exactly as before — they never see the cache directly.**

---

## How it works

```
page calls registry.resolve('fst_dxy_thetapi_groupwise', { chrom: 'LG28', ... })
         │
         ▼
Registry._fetchFromSource(entry, args, atlas_id)     // entry.source === 'operation'
         │
         ├─→ runner.run(opEntry, args, state)        // POST to popstats_server.py
         │       returns: result (parsed JSON)
         │
         ├─→ if (entry.persist === true)
         │       _persistOperationResult(entry, args, result)   // FIRE-AND-FORGET
         │            │
         │            ├─→ buildPersistPath:
         │            │     _cache/server_results/{op_id}/{hash}.json
         │            │     where hash = stableHashHex(args)
         │            │
         │            ├─→ POST /file/{path} with JSON.stringify(result)
         │            │     server: _is_path_allowed_for_write → True
         │            │     server: _resolve_write_target rewrites prefix to
         │            │             SERVER_RESULTS_CACHE_ROOT
         │            │     server writes the bytes
         │            │
         │            └─→ on failure: console.warn (does NOT fail the resolve)
         │
         └─→ returns result to the page (synchronously, no wait on persist)
```

The page gets its result without waiting for the disk write. If the
write fails (disk full, server down, allowlist mismatch) the user sees
the result and a one-line warning lands in the console.

---

## What's on the allowlist

Server-side allowlist (`_is_path_allowed_for_write` in
`popstats_server.py`):

| # | Prefix | Used by |
|---|---|---|
| 1 | `data/candidates/{cid}/lineage.json` | `Registry.write` on `candidate_lineage` |
| 2 | `data/candidates/{cid}/{version_id}/<aspect>.json` | `Registry.write` on per-candidate aspect layers |
| 3 | `data/arrangement_calls/{cid}/{version_id}/<file>` | `Registry.write` on `arrangement_calls` |
| 4 | `data/review/inversion/sessions/{session_id}/<file>` | Existing review-session writes (legacy) |
| 5 | `_cache/server_results/{op_id}/{hash}.json` | Persist hook on `persist: true` operation layers |

Anything else: HTTP 403 with a clear message listing the permitted
prefixes. The browser-side `Registry.write` does its own pre-flight
checks (writable: true, source === 'file', version_id present), but
the server allowlist is the second line of defence and cannot be
bypassed by a misconfigured layer.

---

## Where the cache lives on disk

**Logical path** (what the registry sees, what `POST /file/{path}` is
called with):

```
_cache/server_results/{op_id}/{hash}.json
```

**Physical path** (where the bytes actually go):

```
{SERVER_RESULTS_CACHE_ROOT}/{op_id}/{hash}.json
```

`SERVER_RESULTS_CACHE_ROOT` is configured in
`atlases/inversion/server/popstats_server.config.yaml` under the
`server_results_cache_root` key. **Default:**
`/mnt/e/inversion-atlas-cache/server_results/`.

The default is deliberately outside the project tree, on Quentin's big
disk. Test runs accumulate cache files; we don't want them bloating
project tarballs or `git status` output.

The server creates the cache root at startup (`_bootstrap`). If the
mkdir fails, the server still starts — the next persist write surfaces
the error, the resolve still succeeds because persist is
fire-and-forget.

---

## When to set `persist: true`

**Yes** — heavy server compute over the cohort that's deterministic
in its inputs:

- `popstats_groupwise` (FST + dXY + theta_pi over 226 samples)
- `popstats_hobs_groupwise` (HoverE at multiple scales)
- `ancestry_groupwise_q` (NGSadmix-equivalent groupwise Q)
- `ld_split_heatmap` (split-heatmap LD over a region; reasked per candidate)
- `shelf_ld_test` (small but per-candidate; cache to avoid recompute on revisit)

**No** — cheap or non-cacheable:

- `health` ping (free, no point)
- `dosage_chunk` / `dosage_manifest` (already disk-backed; the server
  reads them from a pre-baked TSV store on every call, no compute)
- Any operation whose result is a function of state the cache key
  doesn't capture (timestamps, random sampling, "current cohort
  membership")

---

## Cache layout: `content_addressed` vs `path_template`

Two flavours of persist path, both implemented:

### `content_addressed` (default)

```
_cache/server_results/{op_id}/{stableHashHex(args)}.json
```

Args order doesn't matter (`stableStringify` sorts keys before
hashing). Used by all 5 inversion-atlas persist layers today.

### `path_template`

```
{layer.path with templateFill}
```

Falls back to using the layer's own `path` field. Only useful when the
template's slot list (`{chrom}`, `{candidate_id}`, etc.) fully
determines the result — i.e. the args coverage exactly matches the
slot coverage. The default is safer; reach for `path_template` only
when there's a specific reason.

Set per-layer in `layers.registry.json`:

```jsonc
{
  "tier": "cold",
  "source": "operation",
  "operation": "my_op",
  "persist": true,
  "cache_layout": "content_addressed"   // or "path_template"
}
```

---

## Clearing the cache

Three ways:

1. **One layer, one args set** (most common):
   ```bash
   rm /mnt/e/inversion-atlas-cache/server_results/popstats_groupwise/<hash>.json
   ```
   The next `resolve()` on that layer + args goes back to the server.

2. **All results for one operation** (after binary recompile):
   ```bash
   rm -rf /mnt/e/inversion-atlas-cache/server_results/popstats_groupwise/
   ```

3. **Everything** (start fresh):
   ```bash
   rm -rf /mnt/e/inversion-atlas-cache/server_results/
   ```

The directory is recreated automatically on the next persist write.

---

## Tarballing for handoff

When packaging the project to send to the next chat, exclude the cache
explicitly:

```bash
tar czf inversion-atlas_$(date -I).tar.gz \
    --exclude='_cache/server_results/*' \
    --exclude='node_modules' \
    --exclude='.git' \
    inversion-atlas/
```

The `_cache/server_results/` directory by default lives at
`/mnt/e/inversion-atlas-cache/server_results/` so it's outside the
project root entirely — but if you reconfigure `server_results_cache_root`
to point inside the project (e.g. for a CI environment), the exclude
matters.

---

## Debugging "my result is being recomputed"

Symptom: you `await registry.resolve('fst_dxy_thetapi_groupwise', { ... })`
twice in a row and the second call still hits the server.

Checklist:

1. **Is `persist: true` on the layer entry?** Open
   `atlases/inversion/registries/data/layers.registry.json`, find the
   layer, confirm.
2. **Did the persist write actually succeed?** Browser console — look
   for `"Registry persist: failed to cache..."`. If present, the write
   threw; the result didn't make it to disk.
3. **Is the server's `SERVER_RESULTS_CACHE_ROOT` writable by the
   process?** Server log on startup logs the resolved path or warns if
   `mkdir` failed.
4. **Are the args identical between the two calls?** Different
   `args.fields` values, different `args` ordering — wait, ordering is
   normalised by `stableHashHex`; but missing vs explicit-undefined
   args produce different hashes. Compare the two arg objects byte-for-byte.
5. **In-memory cache miss?** Cold-tier layers don't keep results in
   the in-memory cache (only `hot` and `warm` do). For a `cold` +
   `persist: true` layer, the second resolve still calls the server
   first; the persist hook only kicks in if the **layer's tier is
   warm**. If you want disk-cache hits to short-circuit the server,
   the layer needs `tier: warm` AND `persist: true` AND a `path` that
   the read side can route to. (None of the 5 operation layers in the
   inversion atlas need this today — they all run cold and re-fetch
   the server on demand; the persist file is the audit trail, not the
   hot read path.)

For (5), if you want the disk cache to be the read source on
subsequent calls, the layer entry should be `source: file` with the
operation triggered out-of-band (a different code path). That's a v3
optimization — not on the v2 spec.

---

## Why fire-and-forget

Three reasons:

1. **The page already has the result.** Making the persist write
   block would slow the user-visible round trip for no benefit.
2. **The cache is a performance optimization, not source of truth.**
   The server can always recompute. A failed cache write is a missed
   speed-up, not a data-loss event.
3. **Failures are common in dev.** A typoed
   `server_results_cache_root` shouldn't fail every server compute —
   it should log loudly and let the user keep working.

The trade-off: a successful resolve doesn't guarantee a successful
disk write. If audit-trail-grade durability is needed for a specific
operation, mark its layer `persist: true` AND have the analysis module
that consumes it explicitly call `Registry.write()` on a separate file
layer. That's the existing `Registry.write` path — synchronous, throws
on failure, two-line block at the call site.

---

## What this enables next

Now that the registry has both a read path and a write path:

- Browser-side analysis modules (`mendelian_inheritance.js`,
  `breeding_card.js`) write per-candidate JSONs to
  `data/candidates/{cid}/{version_id}/<thing>.json` via
  `Registry.write`.
- HPC-side producers write the same canonical paths from SLURM scripts;
  the browser reads through the same registry layers — producer
  location is invisible to the page.
- Server-compute results land on disk as a side-effect, freeing the
  next session's tests from re-running heavy ANGSD/NGSadmix calls.

The page migration sessions will exercise these paths one
analysis-flow at a time. Each migrated page proves that another
slice of the registry is wired end-to-end.
