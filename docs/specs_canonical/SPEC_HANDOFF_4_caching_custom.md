# HANDOFF 4 — Custom user views and caching backend

**Goal**: extend the producer (HANDOFF 1) and atlas UI (HANDOFF 2) so
users can specify custom pair-set combinations beyond the four canonical
views, with results cached so the same spec doesn't recompute.

**Status**: not started. Depends on HANDOFF 1 (producer) being functional.

**Audience**: a fresh chat where Claude designs the custom-view system
and integrates it with the atlas UI. This is a polish-tier task — the
core value of the project is delivered without it. Build last.

---

## What this enables

The four canonical views (`bi_baseline`, `tri_extras`, `quad_extras`,
`all_pairs`) cover the main experimental matrix. But for some
investigations, a user might want:

- "MAJOR_MINOR1 + MINOR1_MINOR2 only — no MAJOR_MINOR2 — to isolate a
  specific contrast"
- "All pairs, but with `min_pair_allele_count >= 20` instead of 6"
- "Only sites where n_samples_with_minor is in [10, 30]" (a bespoke
  rare-but-real cohort)
- "Multi-allelic extras filtered to high MAF only"

These are one-off filter+weight combinations. We don't want to
pre-compute every possibility (combinatorial explosion), but we do want
results to feel as fast as switching between canonical views.

---

## Architecture

```
                  ┌──────────────────────────────────┐
                  │  Atlas UI: custom view picker    │
                  │  (checkbox + threshold sliders)  │
                  └────────────┬─────────────────────┘
                               │
                               ▼
                  ┌──────────────────────────────────┐
                  │  Spec hash                        │
                  │  hash = sha256(spec_json)         │
                  └────────────┬─────────────────────┘
                               │
                ┌──────────────┼──────────────┐
                ▼                             ▼
       ┌──────────────────┐          ┌─────────────────┐
       │ Cache hit?       │          │ Producer queue  │
       │ (filesystem      │ no  ────▶│ (job dispatcher)│
       │ or DB)           │          │                 │
       └────┬─────────────┘          └────────┬────────┘
            │ yes                             │
            ▼                                 ▼
       ┌──────────────────┐          ┌─────────────────┐
       │ Load cached JSON │◀─────────│ Producer runs;  │
       │ → atlas          │          │ writes to cache │
       └──────────────────┘          └─────────────────┘
```

### Cache key

```
hash_input = {
  candidate_id,
  pairs_allowlist,            // sorted list of role pairs
  filter_thresholds,          // sorted dict of all filter flags
  weighting,                  // {mode, weight_stat, power, cap_at_one}
  anchor_mode,
  centering,
  polarity_ref,
  window_def                  // {kind, size, step}
}
hash = sha256(json.dumps(hash_input, sort_keys=True))
```

Two specs differing only in a parameter that's irrelevant to output
(e.g., a comment field) should hash the same. Sorted dict serialization
ensures this.

### Cache layout

```
/path/to/cache/
├── candidates/
│   └── LG28_15.115_18.005/
│       ├── canonical/                   # pre-computed canonical views
│       │   ├── pca_<view>_<weight>_<anchor>.json
│       │   └── heatmap_<view>_<centering>.json
│       └── custom/                      # user-spec hashes
│           ├── <hash1>/
│           │   ├── spec.json
│           │   ├── pca.json
│           │   └── heatmap.json
│           └── <hash2>/
│               └── ...
└── catalog.json                         # index of all specs ever seen
```

The `catalog.json` lets the UI show "you've used this spec before"
suggestions and lets a cleanup script identify unused entries.

### Cache eviction

- **By age**: delete custom entries unused for > 30 days.
- **By size**: keep total cache under N GB; evict LRU.
- **By candidate**: when a candidate is deleted from the system, drop
  its directory.

Canonical views are never evicted — they're produced once at candidate
creation time.

---

## UI: custom view picker

### Component placement

A "Custom view" option in the existing view dropdown:

```
View: [all_pairs ▾]
  [Biallelic baseline]
  [Tri-allelic extras]
  [All multi-allelic extras]
  [All pairs]
  ─────────────
  [Custom...]            ← opens picker modal
  [My saved views ▾]     ← user-saved presets
```

Selecting "Custom..." opens a modal:

```
┌─ Custom view ─────────────────────────────────────────┐
│                                                        │
│  Pairs to include:                                    │
│    ☑ MAJOR_MINOR1                                     │
│    ☐ MAJOR_MINOR2                                     │
│    ☑ MINOR1_MINOR2                                    │
│    ☐ MAJOR_MINOR3                                     │
│    ☐ MINOR1_MINOR3                                    │
│    ☐ MINOR2_MINOR3                                    │
│                                                        │
│  Support thresholds:                                   │
│    Min pair allele count: [────●──] 20                 │
│    Min within-pair MAF:   [─●────] 0.05                │
│    Min n samples minor:    [────●──] 10                │
│    ...                                                 │
│                                                        │
│  Weighting: [max ▾] stat: [pair_count ▾] cap: [☑]     │
│                                                        │
│  Anchor mode: [bi_baseline ▾]                          │
│                                                        │
│  Window: [bp_span ▾] size: [50000] step: [50000]      │
│                                                        │
│  [ Save as preset... ]    [ Cancel ]    [ Apply ]     │
└────────────────────────────────────────────────────────┘
```

### Apply flow

1. Build spec object from form values
2. Compute hash
3. Query backend: `GET /api/cache/candidate/<id>/custom/<hash>`
4. If 200: load JSON, switch view
5. If 404: show "computing..." indicator, POST to start producer, poll
   or use websocket for completion
6. On completion: load JSON, switch view, persist hash → label mapping
   if "Save as preset" was checked

---

## Backend options

Two paths, depending on hosting model:

### Option A: filesystem cache + R script invocation

Atlas runs on a server with shell access to the producer scripts.
Simpler architecturally:

```bash
# When custom view requested:
spec_hash=$(echo "$spec_json" | sha256sum | cut -d' ' -f1)
cache_dir="/path/to/cache/candidates/<id>/custom/$spec_hash"

if [[ -f "$cache_dir/pca.json" ]]; then
    cat "$cache_dir/pca.json"
else
    mkdir -p "$cache_dir"
    echo "$spec_json" > "$cache_dir/spec.json"
    Rscript producer_pca.R \
        --candidate ... \
        --pairs $(parse_pairs spec.json) \
        --min_pair_allele_count $(parse spec.json) \
        ... \
        --out "$cache_dir/pca.json"
    Rscript producer_heatmap.R ... --out "$cache_dir/heatmap.json"
    cat "$cache_dir/pca.json"
fi
```

Per-spec runtime: ~5-30 seconds depending on filter strictness and
candidate size. Acceptable for interactive use as long as the UI shows
a progress indicator.

### Option B: serverless / API endpoint

Atlas is a static web app hosting JSONs from a CDN; producer runs
on-demand via a serverless function (Cloud Run, Lambda, etc.):

```javascript
async function fetchCustomView(spec) {
  const hash = sha256(JSON.stringify(spec));
  const cacheUrl = `https://cdn.example.com/cache/${candidateId}/${hash}/pca.json`;
  
  const cached = await fetch(cacheUrl);
  if (cached.ok) return cached.json();
  
  // Cache miss — invoke producer
  const job = await fetch('/api/produce', {
    method: 'POST',
    body: JSON.stringify({ candidateId, spec })
  });
  const { jobId } = await job.json();
  
  // Poll for completion
  while (true) {
    const status = await fetch(`/api/status/${jobId}`);
    const s = await status.json();
    if (s.done) return fetch(cacheUrl).then(r => r.json());
    await sleep(2000);
  }
}
```

More complex to set up; better for multi-user or distributed deployment.

---

## Recommendation

Start with **Option A** (filesystem + shell). Move to Option B only if
multi-user access becomes important. For Quentin's solo workflow on
LANTA, Option A is enough.

---

## Saved presets

Users may want to save named custom specs. Persist as a TSV or JSON
keyed by user (or globally):

```json
{
  "presets": [
    {
      "name": "Strict tri-allelic",
      "spec": { ... },
      "created": "2026-05-10T...",
      "candidate_used_with": ["LG28_15.115_18.005", ...]
    }
  ]
}
```

UI: "My saved views" dropdown shows the list; clicking applies the spec
to the current candidate (re-hashing for the new candidate's data).

---

## Spec validation before submission

Reject specs that would produce empty output:

- At least one role pair selected
- `min_n_alleles_obs <= max_n_alleles_obs`
- Filter thresholds within sensible ranges
- Window size > 0, step > 0

Show inline validation errors in the UI before "Apply" is enabled.

---

## Testing

- Submit known canonical specs (matching the 4 views) → should hit cache
  for canonical files
- Submit slight variations → should miss cache, run producer, populate
  cache
- Re-submit identical spec → should hit cache instantly
- Test cache eviction on a forced-small cache directory

---

## Pointers

- HANDOFF 1: producer scripts that this system invokes.
- HANDOFF 2: UI integration points where the custom view picker lives.
- SPEC_0 Section 7-10: the spec parameter space.

## What you can ignore

- HWE statistics (not in this layer).
- Multi-candidate batch operations (out of scope; one candidate at a
  time).
- User authentication (Quentin's solo workflow doesn't need it; can be
  added later).
