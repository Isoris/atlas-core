# biomod spec v0

Module catalog + package manager for analysis modules. Mirrors conda's CLI. Does not execute modules.

## Data model

**Module**: one analysis. Has scripts, declared inputs/outputs, parameters, descriptive metadata.

**Derivative**: a module that inherits scripts/outputs from a parent and overrides parameters only.

**Environment**: isolated namespace. Has its own module registry and run history. Same model as conda envs.

**Run**: one invocation of a module's entry script. Records inputs hash, runtime, samples, output bytes, QC.

## Filesystem layout

```
~/.biomod/
  envs/
    <env_name>/
      registry/<module_name>/
        meta.yaml
        internal/
      conda/<module_name>/
      runs.sqlite
  channels/                     # cached remote recipes (later)
```

`$BIOMOD_ENV` = active env name. Defaults to `default` if unset.

## Recipe format

YAML at `<env>/registry/<module>/meta.yaml`. Schema at `recipe_schema.json`. Required: `schema_version`, `name`, `version`, `description`, `family`. Common optional: `good_for`, `not_good_for`, `inputs`, `outputs`, `parameters`, `components`, `parent`, `parent_overrides`, `scope`, `tags`, `status`, `requirements`.

`requirements` is a list of conda package specs (`"r-base=4.3"`). Same syntax as conda meta.yaml.

`parent` is `<name>@<version>`. Derivatives have no `internal/` directory of their own — they inherit from parent.

## SQLite schema (`runs.sqlite`, per env)

```sql
CREATE TABLE runs (
  run_id          TEXT PRIMARY KEY,         -- uuid4
  module_name     TEXT NOT NULL,
  module_version  TEXT NOT NULL,
  started_at      INTEGER NOT NULL,         -- unix epoch
  finished_at     INTEGER,                  -- null if running
  status          TEXT NOT NULL,            -- 'running' | 'success' | 'failed'
  inputs_hash     TEXT NOT NULL,
  n_samples       INTEGER,
  runtime_seconds INTEGER,
  output_bytes    INTEGER,
  qc_status       TEXT,                     -- 'pass' | 'warn' | 'fail' | null
  qc_details      JSON,
  error_message   TEXT,
  log_path        TEXT
);

CREATE INDEX idx_runs_module ON runs(module_name, started_at DESC);
CREATE INDEX idx_runs_inputs ON runs(module_name, inputs_hash);
```

## CLI

All commands accept `--env <name>` to target a non-active env. All read-oriented commands accept `--json`.

### Environment

```
biomod create -n <name>
  Create env at ~/.biomod/envs/<name>/. Fails if exists. Initializes empty runs.sqlite.

biomod activate <name>
  Print shell snippet to set $BIOMOD_ENV. Usage: eval "$(biomod activate <name>)"

biomod deactivate
  Print shell snippet to unset $BIOMOD_ENV.

biomod env list [--json]
  List all envs with module counts and total disk usage.

biomod env remove <name> [--yes]
  Delete env. Requires --yes unless stdin is tty.
```

### Module install/remove

```
biomod install <name> [--version <v>] [--env <e>]
  Resolve recipe (local channels first, remote later), copy to registry/<name>/,
  create conda env at conda/<name>/ from recipe.requirements if present.
  Idempotent: re-running with same version is no-op. Different version: upgrade.

biomod register <path> [--env <e>]
  Same as install but source is a local directory containing meta.yaml + internal/.
  Used when atlas-core has a module checked out from git.

biomod remove <name> [--env <e>] [--yes]
  Delete registry/<name>/ and conda/<name>/. runs.sqlite rows retained.
```

### Inspection

```
biomod list [--env <e>] [--json]
  Installed modules in env. JSON shape: [{name, version, family, status, parent}].

biomod info <name> [--env <e>] [--json]
  Full recipe + last-run summary. JSON shape: {recipe: {...}, last_run: {...} | null}.

biomod status [<name>] [--env <e>] [--json]
  Operational state per module. JSON shape: see "status JSON" below.

biomod search <query> [--env <e>] [--json]
  Full-text over name + family + description + tags. JSON shape: same as list.
```

### Runs

```
biomod runs [<name>] [--env <e>] [--limit N] [--json]
  Run history. Without <name>: cross-module recent runs. With <name>: that module only.

biomod run-begin --module <name> --inputs-hash <h> [--samples <N>] [--env <e>]
  Insert running row. Print run_id to stdout. Module entry scripts call this at start.

biomod run-finish <run_id> [--output-bytes <N>] [--qc-status <s>] [--qc-details <json>]
  Mark success. Compute runtime_seconds from started_at.

biomod run-fail <run_id> [--error <msg>]
  Mark failed. Compute runtime_seconds from started_at.
```

## status JSON

```json
[
  {
    "name": "local_pca_GHSL",
    "version": "1.0.0",
    "family": "local_pca",
    "status": "stable",
    "installed": true,
    "ready": true,
    "stale": false,
    "stale_reason": null,
    "parent": null,
    "derivatives": ["local_pca_GHSL_strict"],
    "last_run": {
      "run_id": "uuid",
      "started_at": 1747200000,
      "finished_at": 1747208054,
      "runtime_seconds": 8054,
      "n_samples": 226,
      "output_bytes": 3650000000,
      "qc_status": "pass"
    }
  }
]
```

`ready = installed AND (last_run.status == 'success') AND NOT stale`.
`stale = inputs_hash_of_current_files != last_run.inputs_hash`. If never run, `stale = false` and `ready = false`.
`stale_reason`: string like `"input 'vcf' changed"` or null.

## Inputs hash

Defined as: sha256 of canonical-JSON-serialized `{module: name, version, normalized_inputs: {...}}` where each input file is represented by `sha256(file_contents)`, not by path. Parameters are not part of the hash — parameter changes are version bumps, not silent reruns.

Module entry scripts compute this hash before `run-begin`. biomod does not compute it (biomod doesn't know what the inputs are at the file level).

## Conda env management

When `recipe.requirements` is non-empty, `biomod install` creates a conda env at `~/.biomod/envs/<env>/conda/<module>/` by calling `conda create --prefix <path> <requirements>`. biomod shells out to conda; it does not bundle one.

Modules use their env by sourcing `~/.biomod/envs/<env>/conda/<module>/bin/activate` or equivalent. biomod does not auto-activate. Module entry scripts handle this themselves.

If `recipe.requirements` is empty/absent, no conda env is created.

## Derivative resolution

When a derivative is installed:

1. Check parent is installed in same env. If not, install parent first (recursive).
2. Copy derivative meta.yaml to `registry/<derivative>/meta.yaml`.
3. No `internal/` directory created for derivative.
4. No separate conda env — derivative shares parent's conda env.

At run time, the derivative's effective parameters are: `parent.parameters` with `derivative.parent_overrides.parameters` merged on top. biomod does not enforce this — it's the responsibility of whatever invokes the module to read both recipes and merge. `biomod info <derivative> --json` returns both `recipe` and `effective_recipe` (with parameters merged) for convenience.

## Channels (v0 scope: local only)

A channel is a directory or git repo containing `recipes/<name>/meta.yaml + internal/` per module. biomod resolves `install <name>` by searching channels in order. v0 supports only local directory channels listed in `~/.biomod/config.yaml`:

```yaml
channels:
  - /path/to/biomod-recipes
  - /home/user/my-recipes
```

Remote channels (HTTPS, git+https) are out of scope for v0.

## Exit codes

```
0   success
1   user error (bad args, module not found, etc.)
2   recipe validation failed
3   conda operation failed
4   biomod state inconsistent (corrupt SQLite, missing files); needs manual fix
```

## What biomod does not do

- Execute modules. No `biomod run`. Modules expose their own entry however they want.
- Track products / outputs. That's APLR (separate). biomod tracks runs only.
- Orchestrate workflows. No DAGs.
- Auth, multi-user, network. v0 is single-user local.

## Build order

1. `biomod create / activate / env list / env remove`. Just directory operations + a shell snippet generator.
2. Recipe loader + validator against `recipe_schema.json`. Already exists in seed catalog.
3. `biomod install / register / remove`. Filesystem copy + conda env create.
4. `biomod list / info / search`. Reads recipes.
5. `runs.sqlite` schema + `run-begin / run-finish / run-fail`. Just SQLite inserts.
6. `biomod status / runs`. Reads recipes + SQLite, computes ready/stale.

Each step is independently testable. Steps 1-2 are no-network, no-conda. Step 3 requires conda. Steps 4-6 require steps 1-3.

## Implementation notes

- Single Python package, no external runtime deps beyond `pyyaml`, `jsonschema`. `conda` invoked as subprocess.
- All state in `~/.biomod/`. No system-wide config.
- Concurrent CLI invocations on same env: use SQLite's built-in locking. Don't add file locks.
- All timestamps unix epoch integers in SQLite, ISO 8601 in JSON output.
- Recipe schema lives at `<biomod_install>/recipe_schema.json`, single source of truth.

End of spec.
