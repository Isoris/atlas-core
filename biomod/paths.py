"""Filesystem layout.

Per the v0 spec: all state under ``~/.biomod/``. For tests and isolated
installs, set ``$BIOMOD_HOME`` to point at a different root — every
function in this module consults that env var first.

Layout (one env shown)::

    <home>/
    ├── config.yaml                 (channels list — step 7 of v0)
    └── envs/<env_name>/
        ├── registry/<module>/      (step 3+)
        ├── conda/<module>/         (step 3+; per-module conda env)
        └── runs.sqlite             (step 6+)

Step 1 creates ``envs/<env_name>/registry/`` (empty) and an empty
``runs.sqlite`` file. The SQLite schema lands in step 6.
"""

from __future__ import annotations

import os
import pathlib
import re


DEFAULT_ENV = "default"

# Names are restricted to make filesystem layout predictable. Same pattern
# as conda env names (with the additional constraint that they start with
# a letter so they're valid Python identifiers if anyone imports them).
_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")


def biomod_home() -> pathlib.Path:
    """Root of all biomod state. Override with ``$BIOMOD_HOME``."""
    override = os.environ.get("BIOMOD_HOME")
    if override:
        return pathlib.Path(override).expanduser()
    return pathlib.Path.home() / ".biomod"


def envs_dir() -> pathlib.Path:
    return biomod_home() / "envs"


def env_dir(name: str) -> pathlib.Path:
    return envs_dir() / name


def registry_dir(env_name: str) -> pathlib.Path:
    return env_dir(env_name) / "registry"


def conda_dir(env_name: str) -> pathlib.Path:
    return env_dir(env_name) / "conda"


def runs_db_path(env_name: str) -> pathlib.Path:
    return env_dir(env_name) / "runs.sqlite"


def active_env() -> str:
    """Value of ``$BIOMOD_ENV`` (the active env), falling back to 'default'."""
    return os.environ.get("BIOMOD_ENV") or DEFAULT_ENV


def valid_name(name: str) -> bool:
    """Whether `name` is a legal env / module identifier.

    Rule: lowercase letter, then lowercase letters / digits / underscore.
    Matches the recipe schema's `name` constraint in
    `recipe_schema.json` so envs and modules share a vocabulary.
    """
    return bool(name) and bool(_NAME_RE.match(name))


def list_env_names() -> list[str]:
    """Sorted list of existing env names. Empty if the home dir doesn't
    exist yet."""
    d = envs_dir()
    if not d.is_dir():
        return []
    return sorted(p.name for p in d.iterdir() if p.is_dir())
