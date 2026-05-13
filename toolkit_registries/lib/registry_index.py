"""
toolkit_registries/lib/registry_index.py

Build the two flat-TSV catalogues from the JSON-per-record registry:

  - set_registry.tsv          ← from <root>/sets/<entity_type>/*.json (set_v1)
  - analysis_registry.tsv     ← from <root>/analyses/*.json           (analysis_v1)

Column orders are pinned by set_registry_row_v1.schema.json and
analysis_registry_row_v1.schema.json. Empty cells are zero-length strings
(not 'NA' / '.') so split('\\t') has the right column count.

Usage (CLI):
    python registry_index.py /path/to/registry [--out-dir <dir>]
    python registry_index.py --example     # scan inventory/example_data/registry

Usage (lib):
    from registry_index import build_set_registry, build_analysis_registry
    rows = build_set_registry(registry_root)
    write_tsv(rows, set_registry_row_columns, out_path)
"""

from __future__ import annotations

import argparse
import csv
import json
import pathlib
import sys
from typing import Dict, Iterable, List, Optional


SET_REGISTRY_COLUMNS = [
    "set_id", "entity_type", "label", "path", "n_entities", "hash",
    "parent_set_id", "filter_profile_id", "coordinate_system",
    "intended_use", "status", "created_at", "definition_path",
]

ANALYSIS_REGISTRY_COLUMNS = [
    "analysis_id", "analysis_version", "label", "description",
    "input_entity_types", "input_layer_types", "produces",
    "engine", "endpoint", "default_runner",
    "status", "requires", "intended_use", "definition_path",
]


# --------------------------------------------------------------------------- #
# Generic helpers                                                              #
# --------------------------------------------------------------------------- #

def _load_json_dir(root: pathlib.Path, glob: str = "*.json", recursive: bool = False) -> List[Dict]:
    """Read all .json files matching glob (optionally recursive), return parsed dicts."""
    out = []
    if not root.is_dir():
        return out
    iterator = root.rglob(glob) if recursive else root.glob(glob)
    for p in sorted(iterator):
        try:
            obj = json.loads(p.read_text())
            obj["_path"] = str(p)  # used to fill definition_path
            out.append(obj)
        except Exception as e:
            print(f"  warn: skipping {p}: {e}", file=sys.stderr)
    return out


def _short(p: Optional[str], registry_root: pathlib.Path) -> str:
    """Render a path as relative-to-registry_root when possible."""
    if not p:
        return ""
    try:
        return str(pathlib.Path(p).relative_to(registry_root))
    except ValueError:
        return p


def _join_csv(values: Optional[Iterable[str]]) -> str:
    """Comma-join a list (deduplicated, sorted) for TSV cells. None / empty → ''."""
    if not values:
        return ""
    items = sorted({str(v) for v in values if v})
    return ",".join(items)


# --------------------------------------------------------------------------- #
# set_registry.tsv                                                             #
# --------------------------------------------------------------------------- #

def build_set_registry(registry_root: pathlib.Path) -> List[Dict]:
    """Scan <registry_root>/sets/**/*.json for set_v1 records, return rows
    for set_registry.tsv. Each row has every column in SET_REGISTRY_COLUMNS;
    missing optional fields become ''.
    """
    registry_root = pathlib.Path(registry_root)
    sets_root = registry_root / "sets"
    records = _load_json_dir(sets_root, recursive=True)

    # Detect derived_from with multiple parents — these need definition_path
    # (TSV can't carry the parents list cleanly).
    rows = []
    for r in records:
        derived = r.get("derived_from") or {}
        parents = derived.get("parents") or []
        single_parent = r.get("parent_set_id") or (parents[0] if parents and len(parents) == 1 and derived.get("op") in ("from_set", "from_group") else "")
        needs_def_path = bool(derived) and (len(parents) > 1 or derived.get("op") == "filter" or (derived.get("op") in ("intersect", "union", "difference") and len(parents) > 1))

        row = {
            "set_id":            r.get("set_id", ""),
            "entity_type":       r.get("entity_type", ""),
            "label":             r.get("label", ""),
            "path":              r.get("path", ""),
            "n_entities":        "" if r.get("n_entities") is None else str(r.get("n_entities")),
            "hash":              r.get("hash", ""),
            "parent_set_id":     single_parent or "",
            "filter_profile_id": r.get("filter_profile_id", ""),
            "coordinate_system": r.get("coordinate_system", ""),
            "intended_use":      r.get("intended_use", ""),
            "status":            r.get("status", "active"),
            "created_at":        r.get("created_at", ""),
            "definition_path":   _short(r["_path"], registry_root) if needs_def_path else "",
        }
        rows.append(row)

    rows.sort(key=lambda x: (x["entity_type"] or "", x["set_id"] or ""))
    return rows


# --------------------------------------------------------------------------- #
# analysis_registry.tsv                                                        #
# --------------------------------------------------------------------------- #

def build_analysis_registry(registry_root: pathlib.Path) -> List[Dict]:
    """Scan <registry_root>/analyses/*.json for analysis_v1 records, return
    rows for analysis_registry.tsv."""
    registry_root = pathlib.Path(registry_root)
    analyses_root = registry_root / "analyses"
    records = _load_json_dir(analyses_root)

    rows = []
    for r in records:
        inputs = r.get("inputs") or {}
        sets_in    = inputs.get("sets") or []
        artifacts  = inputs.get("artifacts") or []
        produces   = r.get("produces") or []

        # Flatten nested arrays into comma-separated cells.
        input_entity_types = _join_csv([s.get("entity_type") for s in sets_in])
        input_layer_types  = _join_csv([a.get("layer_type")  for a in artifacts])
        produces_str       = _join_csv([p.get("layer_type")  for p in produces])
        requires_str       = _join_csv(r.get("requires") or [])

        # When any of the nested arrays are non-trivial, point at the JSON.
        needs_def_path = (
            len(sets_in) > 1 or
            len(artifacts) > 1 or
            len(produces) > 1 or
            any(s.get("cardinality") not in (None, "one") for s in sets_in)
        )

        row = {
            "analysis_id":        r.get("analysis_id", ""),
            "analysis_version":   r.get("analysis_version", ""),
            "label":              r.get("label", ""),
            "description":        (r.get("description", "") or "").splitlines()[0][:200],
            "input_entity_types": input_entity_types,
            "input_layer_types":  input_layer_types,
            "produces":           produces_str,
            "engine":             r.get("engine", "") or "",
            "endpoint":           r.get("endpoint", "") or "",
            "default_runner":     r.get("default_runner", "") or "",
            "status":             r.get("status", "active"),
            "requires":           requires_str,
            "intended_use":       r.get("intended_use", ""),
            "definition_path":    _short(r["_path"], registry_root) if needs_def_path else "",
        }
        rows.append(row)

    rows.sort(key=lambda x: (x["analysis_id"] or ""))
    return rows


# --------------------------------------------------------------------------- #
# TSV writer                                                                   #
# --------------------------------------------------------------------------- #

def write_tsv(rows: List[Dict], columns: List[str], out_path: pathlib.Path) -> int:
    """Write rows to out_path as TSV with the given column order. Empty cells
    are zero-length strings. Returns the number of rows written.
    """
    out_path = pathlib.Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh, delimiter="\t", lineterminator="\n",
                            quoting=csv.QUOTE_MINIMAL)
        writer.writerow(columns)
        for r in rows:
            writer.writerow([r.get(c, "") for c in columns])
    return len(rows)


# --------------------------------------------------------------------------- #
# CLI                                                                          #
# --------------------------------------------------------------------------- #

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Build set_registry.tsv and analysis_registry.tsv from the per-record JSONs.")
    ap.add_argument("registry_root", nargs="?", help="Path to <registry_root>/.")
    ap.add_argument("--example", action="store_true", help="Scan toolkit_registries/inventory/example_data/registry/.")
    ap.add_argument("--out-dir", help="Where to write the TSVs. Default: <registry_root>/.")
    args = ap.parse_args(argv)

    if args.example:
        here = pathlib.Path(__file__).resolve().parent
        registry = here.parent / "inventory" / "example_data" / "registry"
    elif args.registry_root:
        registry = pathlib.Path(args.registry_root)
    else:
        ap.print_help()
        return 2

    out_dir = pathlib.Path(args.out_dir) if args.out_dir else registry

    set_rows = build_set_registry(registry)
    set_path = out_dir / "set_registry.tsv"
    n_sets = write_tsv(set_rows, SET_REGISTRY_COLUMNS, set_path)

    analysis_rows = build_analysis_registry(registry)
    analysis_path = out_dir / "analysis_registry.tsv"
    n_analyses = write_tsv(analysis_rows, ANALYSIS_REGISTRY_COLUMNS, analysis_path)

    print(f"set_registry.tsv      {n_sets:>3} rows → {set_path}", file=sys.stderr)
    print(f"analysis_registry.tsv {n_analyses:>3} rows → {analysis_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
