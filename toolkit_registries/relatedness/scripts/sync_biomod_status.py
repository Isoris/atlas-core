#!/usr/bin/env python3
"""
Sync module_registry.tsv from `biomod status --json`.

biomod owns its own catalog (~/.biomod/envs/<env>/registry/, runs.sqlite).
This script takes a snapshot of `biomod status --json` and writes it to
01_registry/module_registry.tsv so the atlas pages can read module
readiness (installed / ready / stale / last_run.qc_status) without
shelling out to biomod from the browser.

Usage:
    # Live: shell out to biomod (requires biomod on PATH)
    sync_biomod_status.py

    # From a JSON dump (when biomod isn't installed yet, or for testing)
    biomod status --json > /tmp/biomod.json
    sync_biomod_status.py --from-json /tmp/biomod.json

    # Target a non-default biomod env
    sync_biomod_status.py --biomod-env inversion_atlas

The JSON shape is the one in the biomod v0 spec §'status JSON': an
array of module status objects. This script flattens each object into
one TSV row (see schemas/module_registry_row.schema.json).
"""

from __future__ import annotations

import argparse
import csv
import datetime
import json
import pathlib
import subprocess
import sys
from typing import Dict, List

from io_helpers import find_registry_root


COLUMNS = [
    "module_name", "version", "family", "biomod_status",
    "installed", "ready", "stale", "stale_reason",
    "parent", "derivatives",
    "last_run_id", "last_run_status", "last_run_qc",
    "last_run_started", "last_run_seconds", "n_samples",
    "conda_env_path", "biomod_env", "synced_at",
]


def _bool(v) -> str:
    if v is None:    return ""
    if v is True:    return "true"
    if v is False:   return "false"
    s = str(v).lower()
    return "true" if s == "true" else ("false" if s == "false" else "")


def _str(v) -> str:
    return "" if v is None else str(v)


def _iso(ts) -> str:
    """biomod uses unix epoch in SQLite; JSON output usually has ISO 8601.
    Tolerate both."""
    if ts is None or ts == "": return ""
    if isinstance(ts, (int, float)):
        try:
            return datetime.datetime.utcfromtimestamp(int(ts)).strftime("%Y-%m-%dT%H:%M:%SZ")
        except Exception:
            return str(ts)
    return str(ts)


def flatten_module(m: Dict, biomod_env: str) -> Dict[str, str]:
    last = m.get("last_run") or {}
    return {
        "module_name":      _str(m.get("name")),
        "version":          _str(m.get("version")),
        "family":           _str(m.get("family")),
        "biomod_status":    _str(m.get("status")),
        "installed":        _bool(m.get("installed", True)),
        "ready":            _bool(m.get("ready")),
        "stale":            _bool(m.get("stale")),
        "stale_reason":     _str(m.get("stale_reason")),
        "parent":           _str(m.get("parent")),
        "derivatives":      ",".join(m.get("derivatives") or []),
        "last_run_id":      _str(last.get("run_id")),
        "last_run_status":  _str(last.get("status")),
        "last_run_qc":      _str(last.get("qc_status")),
        "last_run_started": _iso(last.get("started_at")),
        "last_run_seconds": _str(last.get("runtime_seconds")),
        "n_samples":        _str(last.get("n_samples")),
        "conda_env_path":   _str(m.get("conda_env_path")),
        "biomod_env":       biomod_env,
        "synced_at":        datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def fetch_live(biomod_env: str) -> List[Dict]:
    cmd = ["biomod", "status", "--json"]
    if biomod_env and biomod_env != "default":
        cmd += ["--env", biomod_env]
    try:
        out = subprocess.check_output(cmd, text=True)
    except FileNotFoundError:
        sys.exit("biomod not found on PATH — install biomod, or pass --from-json <file>")
    except subprocess.CalledProcessError as e:
        sys.exit(f"biomod status failed (exit {e.returncode})")
    try:
        return json.loads(out)
    except json.JSONDecodeError as e:
        sys.exit(f"biomod status JSON parse failed: {e}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--from-json", help="Read biomod status JSON from this file instead of shelling out.")
    ap.add_argument("--biomod-env", default="default", help="Which biomod env (default: 'default').")
    ap.add_argument("--registry-root", help="Override atlas registry root.")
    ap.add_argument("--out", help="Override output path. Default: <registry_root>/01_registry/module_registry.tsv")
    ap.add_argument("--dry-run", action="store_true", help="Print the TSV to stdout, don't write.")
    args = ap.parse_args(argv)

    if args.from_json:
        modules = json.loads(pathlib.Path(args.from_json).read_text())
    else:
        modules = fetch_live(args.biomod_env)

    if not isinstance(modules, list):
        sys.exit(f"expected a JSON array; got {type(modules).__name__}")

    rows = [flatten_module(m, args.biomod_env) for m in modules]
    rows.sort(key=lambda r: (r["family"], r["module_name"]))

    out_path = pathlib.Path(args.out) if args.out else (
        (pathlib.Path(args.registry_root) if args.registry_root else find_registry_root())
        / "01_registry" / "module_registry.tsv"
    )

    if args.dry_run:
        fh = sys.stdout
        writer = csv.DictWriter(fh, fieldnames=COLUMNS, delimiter="\t", lineterminator="\n", quoting=csv.QUOTE_MINIMAL)
        writer.writeheader()
        for r in rows: writer.writerow(r)
        return 0

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS, delimiter="\t", lineterminator="\n", quoting=csv.QUOTE_MINIMAL)
        writer.writeheader()
        for r in rows:
            writer.writerow(r)

    print(f"wrote {len(rows)} module(s) → {out_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
