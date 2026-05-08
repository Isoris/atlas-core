# How to run the atlas locally

From a WSL shell:

```bash
bash atlas-core/build/setup_local_dirs.sh    # once — creates the dir layout on /mnt/e/
# (move/symlink your raw outputs into those folders — separate concern)
bash atlas-core/build/assemble.sh             # any time atlas-core or inversion-atlas changes
cd ../atlas-workspace && bash start.sh        # every session
# open http://127.0.0.1:8000/
```

## What each step does

**`setup_local_dirs.sh`** — lays down the directory shape the atlas
proposes on `/mnt/e/`: `results_inversions/`, `results_diversity/`,
`results_population/`, `results_genome/`, plus `atlas-cache/` for the
server caches and writable evidence roots. **Folders only** — getting
your raw outputs into those slots (move, symlink, mount) is a separate,
one-time decision the atlas doesn't make for you. Idempotent (mkdir -p),
safe to re-run.

**`assemble.sh`** — reads `build/atlas.config`, copies `atlas-core/` and
each `atlas_<name>` source into `../atlas-workspace/`, links the data
folder (both as `workspace/data` and as `workspace/mnt/e` so absolute
`/mnt/e/...` paths in `master_config.yaml` resolve through the static
mount), and writes `.atlas.env` with the chosen `atlas_server.local.yaml`.
Re-run any time you edit a source folder.

**`start.sh`** — boots `atlas_server.py` from
`atlas-workspace/server/atlas_server.py` on `127.0.0.1:8000`. Serves the
UI, the `/file` + `/compute` endpoints, and (when the YAML config loads
without errors) the `/api/popstats/*`, `/api/dosage/*`, `/api/ld/*`
endpoints. Ctrl+C to stop.

## Configuration files

| File | What it controls |
|------|------------------|
| `build/atlas.config` | Which atlases to assemble; data root; server config path |
| `master_config.yaml` (workspace root) | Registry roots — absolute `/mnt/e/results_*/...` paths |
| `species/gariepinus.config.yaml` | Cohort + reference fasta declaration |
| `server/atlas_server.local.yaml` | beagle / dosage / sample_list / engines / cache paths |

## First-run prerequisites

Python deps for the server, once per Python env:

```bash
pip install -r atlas-core/server/requirements.txt
```

Compiled engine binaries (region_popstats, hobs_windower, angsd_fixed_HWE,
instant_q) at the paths in `server/atlas_server.local.yaml` →
`engines:` block. Without them, `/api/popstats/*` returns 503 but
everything else still works.

## Common knobs

```bash
ATLAS_PORT=8001     bash start.sh   # different port
ATLAS_RELOAD=1      bash start.sh   # auto-reload server on Python edits
```

## Troubleshooting

- **404 on `/mnt/e/...` URLs** → `assemble.sh` didn't create the
  same-path mirror. Re-run `assemble.sh` and check
  `atlas-workspace/mnt/e` exists as a symlink.
- **`/api/popstats/*` returns 503** → `server_config` line in
  `atlas.config` missing or pointing at a YAML the server couldn't
  parse. Check `start.sh` startup log.
- **`samples.ind: not found`** → `_shared/samples.ind` is empty.
  `setup_local_dirs.sh` only creates folders; the actual sample list has
  to be placed into `/mnt/e/results_inversions/_shared/` by you (move
  the file in, symlink it from wherever it lives, etc.).
- **No `gariepinus/...` data visible** → `master_config.yaml` uses
  absolute `/mnt/e/results_*/` paths now; the registry doesn't expect a
  `gariepinus/` subtree at all. If a layer entry still references one,
  it's stale and points at the old layout.
