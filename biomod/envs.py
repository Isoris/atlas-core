"""Environment commands — step 1 of the biomod v0 spec.

Implements:
  biomod create -n <name>
  biomod activate <name>          (prints shell snippet)
  biomod deactivate               (prints shell snippet)
  biomod env list [--json]
  biomod env remove <name> [--yes]

Pure stdlib. No conda, no SQLite schema, no recipe loader — those land
in later steps. The functions in this module return integer exit codes
that the CLI dispatcher propagates to ``sys.exit``.
"""

from __future__ import annotations

import json
import shutil
import sqlite3
import sys
from typing import Any, Dict, List

from . import paths
from .exit_codes import SUCCESS, USER_ERROR, STATE_INCONSISTENT


# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #

def _err(msg: str) -> None:
    print(msg, file=sys.stderr)


def _dir_size(p) -> int:
    """Total bytes under p. Returns 0 if p doesn't exist."""
    total = 0
    try:
        for sub in p.rglob("*"):
            if sub.is_file():
                try:
                    total += sub.stat().st_size
                except OSError:
                    pass
    except FileNotFoundError:
        pass
    return total


def _human_bytes(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def _env_summary(name: str) -> Dict[str, Any]:
    """Counts + sizes for one env. Cheap; called once per env in `env list`."""
    reg = paths.registry_dir(name)
    n_modules = 0
    if reg.is_dir():
        n_modules = sum(1 for p in reg.iterdir() if p.is_dir())
    return {
        "name":           name,
        "n_modules":      n_modules,
        "bytes_on_disk":  _dir_size(paths.env_dir(name)),
        "has_runs_db":    paths.runs_db_path(name).is_file(),
    }


# --------------------------------------------------------------------------- #
# Commands                                                                     #
# --------------------------------------------------------------------------- #

def cmd_create(name: str) -> int:
    """Create a new env at ~/.biomod/envs/<name>/."""
    if not paths.valid_name(name):
        _err(f"FAIL: env name '{name}' is invalid; must match ^[a-z][a-z0-9_]*$")
        return USER_ERROR
    d = paths.env_dir(name)
    if d.exists():
        _err(f"FAIL: env '{name}' already exists at {d}")
        return USER_ERROR
    paths.registry_dir(name).mkdir(parents=True, exist_ok=True)
    paths.conda_dir(name).mkdir(parents=True, exist_ok=True)
    # Initialize runs.sqlite as an empty valid SQLite database.
    # Step 6 will add the schema; until then it's a placeholder file.
    try:
        conn = sqlite3.connect(str(paths.runs_db_path(name)))
        conn.close()
    except sqlite3.Error as e:
        _err(f"FAIL: could not initialize runs.sqlite: {e}")
        return STATE_INCONSISTENT
    print(f"created env '{name}' at {d}")
    return SUCCESS


def cmd_activate(name: str) -> int:
    """Print a shell snippet that sets $BIOMOD_ENV.

    Intended usage: ``eval "$(biomod activate <name>)"``. Exits 1 if the
    env doesn't exist so eval doesn't execute a stale snippet.
    """
    if not paths.valid_name(name):
        _err(f"FAIL: env name '{name}' is invalid")
        return USER_ERROR
    if not paths.env_dir(name).is_dir():
        _err(f"FAIL: env '{name}' does not exist; run `biomod create -n {name}` first")
        return USER_ERROR
    # Single-quote the value to be safe under bash/zsh.
    print(f"export BIOMOD_ENV='{name}'")
    print(f"# biomod: activated env '{name}'")
    return SUCCESS


def cmd_deactivate() -> int:
    """Print a shell snippet that unsets $BIOMOD_ENV."""
    print("unset BIOMOD_ENV")
    print("# biomod: deactivated")
    return SUCCESS


def cmd_env_list(as_json: bool = False) -> int:
    """List all envs with module counts and disk usage."""
    names = paths.list_env_names()
    summaries: List[Dict[str, Any]] = [_env_summary(n) for n in names]
    if as_json:
        print(json.dumps(summaries, indent=2))
        return SUCCESS

    if not summaries:
        print("(no envs yet — run `biomod create -n <name>`)")
        return SUCCESS

    active = paths.active_env()
    print(f"{'':3} {'NAME':<24} {'MODULES':>7}  {'SIZE':>9}  PATH")
    print(f"{'-' * 3} {'-' * 24} {'-' * 7}  {'-' * 9}  ----")
    for s in summaries:
        marker = "*" if s["name"] == active else " "
        print(f" {marker}  {s['name']:<24} {s['n_modules']:>7}  "
              f"{_human_bytes(s['bytes_on_disk']):>9}  {paths.env_dir(s['name'])}")
    print()
    print(f"* = active ($BIOMOD_ENV={active})")
    return SUCCESS


def cmd_env_remove(name: str, yes: bool) -> int:
    """Delete an env directory. Confirms when --yes not given and stdin is a tty."""
    if not paths.valid_name(name):
        _err(f"FAIL: env name '{name}' is invalid")
        return USER_ERROR
    d = paths.env_dir(name)
    if not d.is_dir():
        _err(f"FAIL: env '{name}' does not exist")
        return USER_ERROR

    if not yes:
        if not sys.stdin.isatty():
            _err(f"FAIL: refusing to remove '{name}' without --yes (stdin is not a tty)")
            return USER_ERROR
        # Interactive confirm
        sys.stderr.write(f"Delete env '{name}' at {d}? [y/N] ")
        sys.stderr.flush()
        reply = sys.stdin.readline().strip().lower()
        if reply not in ("y", "yes"):
            _err("aborted")
            return USER_ERROR

    try:
        shutil.rmtree(d)
    except OSError as e:
        _err(f"FAIL: could not remove {d}: {e}")
        return STATE_INCONSISTENT
    print(f"removed env '{name}'")
    return SUCCESS
