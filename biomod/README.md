# biomod — module catalog + package manager for bioinformatics analyses

Bioconda for *analyses*, not tools. Inspired by, and CLI-mirrored to,
conda. **biomod does not execute modules** — it catalogues them, tracks
their runs, and surfaces their state. The atlas-core dashboard reads
the catalog; runners execute the binaries.

This package currently ships **step 1 of the v0 roadmap** (environment
commands only). Steps 2-7 land in follow-up PRs.

## What works today

```bash
biomod create -n <name>            # create an env at ~/.biomod/envs/<name>/
biomod activate <name>             # print shell snippet to set $BIOMOD_ENV
biomod deactivate                  # print shell snippet to unset $BIOMOD_ENV
biomod env list [--json]           # list all envs with module counts + sizes
biomod env remove <name> [--yes]   # delete an env (requires --yes on non-tty stdin)
```

Use:

```bash
biomod create -n inversions
eval "$(biomod activate inversions)"        # now $BIOMOD_ENV=inversions
biomod env list

# table mode:
#     NAME                  MODULES       SIZE  PATH
# --- --------------------- -------  ---------  ----
#  *  inversions                  0        0 B  ~/.biomod/envs/inversions
#     unified_ancestry            0        0 B  ~/.biomod/envs/unified_ancestry
#
# * = active ($BIOMOD_ENV=inversions)

biomod env list --json | jq .
eval "$(biomod deactivate)"
biomod env remove inversions --yes
```

Stdlib only — no `pyyaml`, no `jsonschema`, no `conda`. Step 2 adds
those deps when the recipe loader lands.

## Filesystem layout

```
~/.biomod/                                  ← override with $BIOMOD_HOME
└── envs/<name>/
    ├── registry/<module>/                  (step 3+ writes here)
    ├── conda/<module>/                     (step 3+ creates per-module conda env)
    └── runs.sqlite                         (empty in step 1; step 6 adds schema)
```

`$BIOMOD_HOME` is for testing / isolated installs. Default is `~/.biomod/`.
`$BIOMOD_ENV` is the active env (defaults to `default`).

## Roadmap (v0 spec — staged)

| Step | What lands | Status |
|---|---|---|
| **1. Env commands** | create / activate / deactivate / env list / env remove | **shipped** (this PR) |
| 2. Recipe loader | YAML reader + jsonschema validation against `recipe_schema.json` | deferred |
| 3. Install / register / remove | filesystem copy + `conda create` subprocess | deferred |
| 4. List / info / search | recipe reads, full-text search over name+family+description+tags | deferred |
| 5. Derive | `biomod derive <parent> --name <new> --reason <text> --set k=v …` — first-class parameter overrides, written from atlas UI | deferred |
| 6. Runs SQLite | runs.sqlite schema + `run-begin` / `run-finish` / `run-fail` (called by entry scripts) | deferred |
| 7. Status / runs | `biomod status` returns ready / stale / installed per module; `biomod runs` returns history | deferred |

The brief is locked at v0; the staging order is intentional and each
step is independently testable.

## Non-negotiable design rules

These are the v0 constraints that this package will refuse to bend on,
no matter what later PRs add:

1. **No `biomod run` command, ever.** The moment biomod executes
   modules, it becomes Nextflow. Resist this.
2. **Recipe schema is the contract.** Adding optional fields is fine.
   Renaming or removing fields requires a `schema_version` bump.
3. **`derive --reason` is required, not optional.** It's the only
   provenance for why a derivative exists. (Lands in step 5.)

## Exit codes

```
0  success
1  user error (bad args, env not found, name clash, etc.)
2  recipe validation failed   (step 2+)
3  conda failed               (step 3+)
4  state inconsistent (corrupt SQLite / missing files; needs manual fix)
```

These integer values are part of the CLI contract — atlas-core and
shell scripts rely on them.

## Tests

Stdlib `unittest`. Each test gets its own `$BIOMOD_HOME` tmpdir.

```bash
python3 -m unittest biomod.tests.test_envs -v
```

22 tests cover:
- `create` happy path, duplicate detection, name validation, runs.sqlite is a valid empty SQLite DB
- `activate` succeeds on known env, fails on unknown env (so `eval "$(biomod activate bad)"` is safe)
- `deactivate` always prints `unset BIOMOD_ENV`
- `env list` empty / populated / `--json` output / active marker
- `env remove` happy path, unknown rejected, non-tty stdin refuses without `--yes`
- CLI integration via `biomod.cli.main(argv)`

## What biomod does NOT do (per the brief)

- Execute modules. No `biomod run`.
- Track output products / caching. That's a separate layer (atlas-core's
  registries handle it).
- Orchestrate workflows. No DAGs.
- Auth, multi-user, network. v0 is single-user local.

When the runner lands in `atlas-core/toolkit_registries/relatedness/`
(or any atlas's `dispatcher.py`), biomod's only job is to answer:
*"is `ngsrelate_pairwise_v2` installed in this env, and was its last
run successful?"* — via `biomod status --json` once step 7 lands.
