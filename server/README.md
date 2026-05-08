# atlas-core / server

**There is no core server.** Each atlas package ships its own server.

## Why

The previous design had a generic `core/server/server.py` Flask shell
that auto-mounted atlas-specific routes from a `server-adapters/`
directory. That was wrong for two reasons:

1. **The real server already exists.** The inversion atlas ships a
   2109-LOC FastAPI server (`atlases/inversion/server/popstats_server.py`)
   that wraps four C engines (`region_popstats`, `hobs_windower`,
   `angsd_fixed_HWE`, `instant_q`) plus a dosage bridge and an LD
   endpoint. It has its own caching, content-addressable hashing,
   ANGSD patch handling, SSH-tunnel docs, integration tests. There
   is no value in wrapping it.

2. **Servers are atlas-shaped, not core-shaped.** The popstats
   server knows about BEAGLE files, sample lists, ANGSD options,
   group composition rules — all inversion-specific. A future
   diversity atlas would have its own server with different engines
   (msmc, smc++, etc.). A future genome atlas might have a synteny
   server. None of these are "shared plumbing".

## How it actually works

Each atlas package contains a complete, runnable server:

```
atlases/inversion/
├── server/
│   ├── popstats_server.py          ← FastAPI app, 2109 LOC
│   ├── dosage_bridge.py            ← 525 LOC
│   ├── lazy_windows_json.py        ← 90 LOC
│   ├── ld_endpoint.py              ← 372 LOC
│   ├── popstats_server.config.yaml
│   ├── requirements.txt
│   ├── test_*.py                   ← unit tests
│   ├── test_with_curl.sh           ← smoke tests
│   └── SERVER_README.md            ← install + run + tunnel docs
└── engines/
    ├── fast_ld/                    ← C source + Python wrapper, 2516 LOC
    └── producers/                  ← SV evidence pipeline scripts
```

The atlas's `manifest.json` points at the server entry point. To
run the atlas:

```bash
# On LANTA (where the engines + data live)
cd atlases/inversion/server
conda activate assembly
pip install -r requirements.txt
python popstats_server.py --config popstats_server.config.yaml
# Listens on 127.0.0.1:8765

# On laptop
ssh -L 8765:127.0.0.1:8765 lanta   # SSH tunnel
# Open the assembled atlas-workspace in browser
# atlas's status badge in toolbar should turn green
```

## What atlas-core provides

Not a server. Just a registry-engine convention for how pages reach
the server:

```js
// Page module
import { resolve } from '../../../core/atlas_api.js';

const result = await resolve('fst_dxy_thetapi_groupwise', {
  chrom: 'C_gar_LG28',
  region: { start_bp: 15000000, end_bp: 18000000 },
  groups: { HOM_REF: [...], HET: [...], HOM_INV: [...] },
  metrics: ['fst', 'dxy', 'theta_pi']
});
```

The registry's operation runner (`core/operation_runner.js`) reads
the operation entry from `inversion`'s `operations.registry.json`,
finds `endpoint: '/api/popstats/groupwise'`, POSTs to
`http://localhost:8765/api/popstats/groupwise`, validates the
response against `schemas/popstats_groupwise.schema.json`, caches
the result.

That's it. Core handles the HTTP plumbing. The atlas owns the
server.

## Multi-atlas deployment

When multiple atlases are loaded in the same workspace, each can ship
its own server on a different port:

```
atlases/inversion/server/   → 127.0.0.1:8765
atlases/diversity/server/   → 127.0.0.1:8766
atlases/genome/server/      → 127.0.0.1:8767
```

Each operation in `operations.registry.json` declares its own base
URL (defaulting to `http://localhost:8765` for inversion), and the
registry's operation runner uses the right one per operation.

## The audit-first rule

Before writing ANY new server code in any future chat:

1. Check `atlases/<atlas_id>/server/` to see what already exists.
2. Read the existing `SERVER_README.md`.
3. Audit the existing FastAPI route definitions (grep for
   `@app.post` and `@app.get`).
4. Only add new endpoints if the work genuinely requires them.
5. If you added an endpoint, also update `operations.registry.json`
   with its real URL, request shape, and source-line origin.

The previous chat invented endpoint names that don't exist. This
file exists to prevent that mistake.
