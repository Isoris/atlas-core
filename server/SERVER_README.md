# atlas_server

The unified atlas server. One process, one port, all in one place.
Lives in `atlas-core/server/` because every endpoint here is generic
plumbing — popstats / LD / dosage / file IO / compute — that every
atlas package shares. Per-atlas specialization lives in registry JSONs
and operations registries, NOT in server code.

Single-file Python service (~2 k lines) with five dependencies:
FastAPI, uvicorn, pyyaml, numpy, pandas.

## What it serves

Two subsystems, both wired into the same FastAPI app:

**Always-live subsystem** — needs only `--project-root` (and optionally
`--workspace-root` to also serve the assembled atlas UI):

| Method | Path                              | Purpose |
|--------|-----------------------------------|---------|
| GET    | `/health`                         | unified status across both subsystems |
| GET    | `/file/<path>`                    | read text/json/binary under the project root |
| POST   | `/file/<path>`                    | registry-v2 write (allowlisted prefixes only) |
| POST   | `/compute/<name>`                 | run a registered compute op |
| GET    | `/`                               | atlas UI from `--workspace-root/index.html` |

**Compute subsystem** — engaged when `--config <yaml>` is passed:

| Method | Path                              | Purpose |
|--------|-----------------------------------|---------|
| POST   | `/api/popstats/groupwise`         | wraps `region_popstats` (Engine F) |
| POST   | `/api/popstats/hobs_groupwise`    | wraps `angsd_fixed_HWE` + `hobs_windower` |
| POST   | `/api/ancestry/groupwise_q`       | reads `instant_q` cache, aggregates per group |
| POST   | `/api/shelf_ld_test`              | server-side shelf LD test |
| POST   | `/api/ld/split_heatmap`           | wraps the `fast_ld` engine |
| GET    | `/api/dosage/chunk`               | per-region dosage chunk for the streaming heatmap |
| GET    | `/api/dosage/manifest`            | dosage store manifest |
| GET    | `/api/cache/keys`                 | debug: list cache hashes |
| DELETE | `/api/cache/keys/<hash>`          | debug: drop one entry |
| GET    | `/api/jobs/<id>`                  | progress polling for slow runs |

All `POST` bodies are JSON. Group definitions are explicit member lists:

```json
{
  "chrom": "C_gar_LG28",
  "region": { "start_bp": 15000000, "end_bp": 18000000 },
  "groups": {
    "HOM1": ["CGA_001", "CGA_007"],
    "HET":  ["CGA_002", "CGA_011"],
    "HOM2": ["CGA_003", "CGA_017"]
  },
  "metrics": ["fst", "dxy", "theta_pi"],
  "win_bp": 50000, "step_bp": 10000
}
```

The atlas decides what a group **is** (by lassoing samples, intersecting
families with regimes, etc.). The server only knows how to compute
statistics given a list of sample IDs per group. Group names match
`[A-Za-z0-9_]+`. Member IDs are validated against the canonical sample
list (`SAMPLE_LIST_POPSTATS`); unknowns are rejected with a clear 400.
Up to 10 groups per request (Engine F's `MAX_GROUPS`).

## Run it

The normal way is via `atlas-core/build/start.sh`, which `assemble.sh`
drops into the workspace:

```bash
bash atlas-core/build/assemble.sh
cd ../atlas-workspace
bash start.sh
# http://127.0.0.1:8000/
```

`start.sh` invokes:

```bash
python3 atlas_server.py \
  --workspace-root <atlas-workspace> \
  --project-root   <atlas-workspace> \
  --host 127.0.0.1 --port 8000 \
  --config /mnt/e/atlas-core/server/atlas_server.local.yaml
```

You can also run the server directly for hacking:

```bash
cp atlas_server.config.example.yaml atlas_server.config.yaml
${EDITOR:-nano} atlas_server.config.yaml
python atlas_server.py --config atlas_server.config.yaml
```

The server logs a startup banner showing the resolved paths and the
engine binary hashes:

```
2026-05-08 18:00:48 [INFO] popstats: config loaded from ...
2026-05-08 18:00:48 [INFO] popstats: cache: loaded 0 entries (0.0 MB) from /mnt/e/atlas-cache/popstats_server_cache
2026-05-08 18:00:48 [INFO] popstats: sample_list: 226 ids from /mnt/e/results_inversions/_shared/samples.ind
2026-05-08 18:00:48 [INFO] popstats: startup complete: 226 samples, 4 engines, 0 cached entries
2026-05-08 18:00:48 [INFO] popstats: listening on http://127.0.0.1:8000
```

Verify with curl:

```bash
curl -s http://127.0.0.1:8000/health | python3 -m json.tool
```

## Cluster mode (LANTA + SSH tunnel)

The server binds to `127.0.0.1` only. To run it on a remote cluster
where the BEAGLE / BAM caches actually live, use a local-port-forward:

```bash
# laptop
ssh -L 8000:127.0.0.1:8000 lanta
# cluster (in tmux)
cd /scratch/.../atlas-core
bash build/assemble.sh && cd ../atlas-workspace && bash start.sh
```

The atlas's status badge in the toolbar should flip to green within 30
seconds. If 8000 is already in use locally, run on a different port and
update the atlas's `atlasServer.url` accordingly.

## About the ANGSD patch

`angsd_fixed_HWE` is **stock ANGSD with a one-line bugfix from Claire
Mérot's group** that corrects the per-site `F` estimator under the model
where samples within a group are not all in HWE (the case for grouped
inversion karyotypes). The CLI is unchanged from upstream ANGSD —
this server invokes it as a normal subprocess with the standard
`-bam -ref -out -GL 1 -doMajorMinor -doMaf 1 -SNP_pval 1e-6 -doHWE 1
-maxHetFreq 1.0 -minMaf -minMapQ -minQ -r <chr>: -nThreads N` argv.

Compile from source:

```bash
cd <patch-source-dir>
make clean && make -j8
cp angsd /mnt/c/Users/quent/Desktop/bio_tools_quentin/bin/angsd_fixed_HWE
```

Point the config's `engines.angsd_patched` at the resulting binary.
The server hashes the binary's bytes and includes that hash in every
HWE cache key, so a recompile auto-invalidates downstream cached
results.

## Cache layout and invalidation

```
${cache_dir}/                       # default /mnt/e/atlas-cache/popstats_server_cache/
  popstats/<hash>.json              region_popstats results (Engine F)
  hobs/<hash>.json                  Q07b+Q07c chained results
  ancestry/<hash>.json              instant_q-cache aggregations
  hwe/<hwe_hash>.hwe.gz             raw ANGSD HWE per-group output
  shelf_ld/                         (reserved)
  index.jsonl                       append-only log; the filesystem is authoritative

${server_results_cache_root}/       # default /mnt/e/atlas-cache/server_results/
  <op_id>/<hash>.json               registry-v2 persist-hook outputs
```

Cache keys are content-addressable:

```
sha256(chrom + region + sorted(group_name → sorted(members))
       + metric_set + win + step + binary_hash)[:32]
```

Sorting at every level guarantees that the atlas can send groups in any
UI order with identical hits. Recompiling any engine binary changes its
content hash → all dependent cache entries become unreachable on lookup
(eventually evicted by LRU at the configurable byte cap).

The cache directory is **safe to delete** at any time. The server will
rebuild the index from disk on the next start and silently re-run
engines on cache miss.

## Testing

```bash
# Unit tests (no engines needed, no server boot)
python test_units.py

# Smoke tests (boots a server with stub binaries + synthetic data)
bash test_with_curl.sh
```

Both are dependency-free against any cluster. Real-engine integration
testing happens against the live data — see the per-page driver docs.

## Operational notes

- **Single-user assumption**: the job manager and ANGSD scheduling
  assume one user at a time. Multi-user scaling (queue with backpressure,
  per-user cache namespaces) is out of scope.
- **HWE cost**: first request for a novel group composition triggers an
  ANGSD run (~5–15 s per group). Three groups in parallel ≈ same wall
  time. Subsequent requests with the same composition return in <100 ms.
- **`region_popstats` cost**: ~50–500 ms per chromosome depending on
  region restriction. Use the `region` field in requests to keep
  per-request latency interactive.
- **`local_Q_samples.tsv.gz` cost**: pure file IO + pandas group-by;
  ~50 ms uncached, <10 ms cached.

## Why this is in atlas-core

History: the server originally lived under
`inversion-atlas/atlases/inversion/server/popstats_server.py` because
the inversion atlas was the only thing that existed when it was
written. Reality check:

- The server reads from the data registry, which lives in atlas-core's
  `toolkit_registries/` and the per-atlas registry JSONs.
- The server doesn't know about *C. gariepinus* specifically — it knows
  about FST, dXY, dosage, LD as generic computations.
- The dosage path, the popstats engines, the LD code — all of these
  apply equally to macrocephalus, to a future shrimp atlas, to anything.

So the server moved to `atlas-core/server/`, was renamed
`popstats_server.py` → `atlas_server.py`, and the review-sessions write
allowlist was generalized from `data/review/inversion/sessions/` to
`data/review/{atlas_id}/sessions/`. Nothing inversion-specific remains
in the server code.
