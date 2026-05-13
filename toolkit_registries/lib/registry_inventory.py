"""
toolkit_registries/lib/registry_inventory.py

Scan a registry directory and emit a flat 'analysis × group × samples × interval'
table — the thing you click and see.

The inventory is the answer to: "what does this registry contain right now?"

Reads (per the schemas in toolkit_registries/schemas/registry_schemas/):
  - analysis_result_v1.*.json   — one per distinct computation
  - sample_set_v1.*.json        — sample-set descriptors (content-hashed)
  - group_definition.*.json     — named groups (for nicer labels)
  - layer_envelope.*.json       — layer payload envelopes (for created_at and status)

Emits one row per analysis_result_v1 record:

  {
    "result_id":       "res_...",
    "analysis":        "ngsrelate",
    "analysis_version":"v2.0.0",
    "group_label":     "HOM_INV ∩ ancestry_K8_cluster3"   ← derived from set algebra
    "sample_set_id":   "sset_...",
    "n_samples":       12,
    "interval":        "C_gar_LG28"                       ← from coordinate_scope or artifacts
    "input_artifact_ids": ["beagle_LG28_v1", "sites_LG28_thin_v1"],
    "status":          "active",
    "created_at":      "2026-05-10T12:30:00Z",
    "layer_id":        "ngsrelate_result_..._v1",
    "params":          { ... }                            ← inline for click-to-expand
  }

Usage (CLI):
    python registry_inventory.py /path/to/registry [--json out.json] [--print]
    python registry_inventory.py --example   ← scan inventory/example_data and print

Usage (lib):
    from registry_inventory import scan
    rows = scan(registry_root)
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Dict, List, Optional


# --------------------------------------------------------------------------- #
# Loaders                                                                      #
# --------------------------------------------------------------------------- #

def _load_json_files(folder: pathlib.Path, pattern: str = "*.json") -> List[Dict]:
    """Read every .json file in folder, return a list of parsed dicts.
    Silently skips files that don't parse — caller can filter on shape."""
    out = []
    if not folder.is_dir():
        return out
    for p in sorted(folder.glob(pattern)):
        try:
            out.append(json.loads(p.read_text()))
        except Exception:
            continue
    return out


def _index_by(records: List[Dict], key: str) -> Dict[str, Dict]:
    return {r[key]: r for r in records if key in r}


# --------------------------------------------------------------------------- #
# Label derivation                                                             #
# --------------------------------------------------------------------------- #

OP_GLYPHS = {
    "intersect":  "∩",
    "union":      "∪",
    "difference": "\\",
}


def _group_label_from_sample_set(
    sset: Optional[Dict],
    groups: Dict[str, Dict],
) -> str:
    """Render a human-readable label for the sample set's group lineage.
    Falls back to the sample_set_id when no lineage is recorded."""
    if sset is None:
        return "(no sample_set)"

    label = sset.get("label")
    if label:
        return label

    derived = sset.get("derived_from")
    if not derived:
        return sset.get("sample_set_id", "(unknown)")

    op = derived["op"]
    parents = derived.get("parents", [])

    if op == "from_group" and parents:
        gid = parents[0]
        g = groups.get(gid)
        if g and g.get("label"):
            return g["label"]
        return gid

    if op == "from_inline":
        return f"(inline {sset.get('n_members', '?')} samples)"

    if op == "filter":
        parent_label = parents[0] if parents else "?"
        pred = derived.get("predicate") or "?"
        return f"{parent_label} | filter:{pred}"

    if op in OP_GLYPHS:
        glyph = OP_GLYPHS[op]
        # For pretty parents: use group label if available, else id
        def _parent_label(pid):
            g = groups.get(pid)
            return g["label"] if g and g.get("label") else pid
        if op == "difference":
            head = _parent_label(parents[0]) if parents else "?"
            tail = " ".join(_parent_label(p) for p in parents[1:])
            return f"{head} {glyph} {tail}" if tail else head
        return f" {glyph} ".join(_parent_label(p) for p in parents) or "?"

    return f"(op={op})"


# --------------------------------------------------------------------------- #
# Interval derivation                                                          #
# --------------------------------------------------------------------------- #

def _interval_label(result: Dict, artifacts_by_id: Dict[str, Dict]) -> str:
    """Pretty interval string from coordinate_scope or input_artifact_ids."""
    cs = result.get("coordinate_scope")
    if cs:
        chrom = cs.get("chrom")
        start = cs.get("start_bp")
        end = cs.get("end_bp")
        if chrom and start is not None and end is not None:
            return f"{chrom}:{start:_}-{end:_}"
        if chrom:
            return chrom

    # No coordinate_scope — fall back to artifact hints.
    artifact_ids = result.get("input_artifact_ids", [])
    if not artifact_ids:
        return "—"

    # If an artifact envelope carries a coordinate, use the first one we find.
    for aid in artifact_ids:
        a = artifacts_by_id.get(aid)
        if a:
            coord = a.get("coordinate")
            if coord and coord.get("chrom"):
                chrom = coord["chrom"]
                start = coord.get("start_bp")
                end = coord.get("end_bp")
                if start is not None and end is not None:
                    return f"{chrom}:{start:_}-{end:_}"
                return chrom

    # Last resort: try to infer from the artifact id text
    for aid in artifact_ids:
        for tok in aid.split("_"):
            if tok.startswith(("LG", "chr", "C_")) and any(c.isdigit() for c in tok):
                return tok
    return "whole-genome"


# --------------------------------------------------------------------------- #
# Scan                                                                          #
# --------------------------------------------------------------------------- #

def scan(registry_root: pathlib.Path) -> List[Dict]:
    """Walk a registry folder, return a list of inventory rows.

    Expected layout (per PIPELINE_FLOW.md §"Folder convention"):
      <registry_root>/
        analysis_results/*.json   ← analysis_result_v1 records
        sample_sets/*.json        ← sample_set_v1 records
        groups/*.json             ← group_definition records (optional)
        layers/**/*.json          ← layer envelopes (any depth)

    Missing folders are OK — the scan returns rows for whatever it finds.
    """
    registry_root = pathlib.Path(registry_root)

    results  = _load_json_files(registry_root / "analysis_results")
    ssets    = _load_json_files(registry_root / "sample_sets")
    groups   = _load_json_files(registry_root / "groups")

    # Layers can live in nested folders by layer_type. Walk recursively.
    layers = []
    layers_root = registry_root / "layers"
    if layers_root.is_dir():
        for p in sorted(layers_root.rglob("*.json")):
            try:
                layers.append(json.loads(p.read_text()))
            except Exception:
                continue

    by_sset    = _index_by(ssets,  "sample_set_id")
    by_group   = _index_by(groups, "group_id")
    by_layer   = _index_by(layers, "layer_id")

    rows = []
    for r in results:
        sset = by_sset.get(r.get("sample_set_id"))
        group_label = _group_label_from_sample_set(sset, by_group)
        n_samples = sset.get("n_members") if sset else None

        layer = by_layer.get(r.get("output_layer_id"))
        status = (layer or r).get("status", r.get("status", "?"))

        rows.append({
            "result_id":         r.get("result_id"),
            "analysis":          r.get("analysis_id"),
            "analysis_version":  r.get("analysis_version"),
            "group_label":       group_label,
            "sample_set_id":     r.get("sample_set_id"),
            "n_samples":         n_samples,
            "interval":          _interval_label(r, by_layer),
            "input_artifact_ids":r.get("input_artifact_ids", []),
            "status":            status,
            "created_at":        r.get("created_at"),
            "layer_id":          r.get("output_layer_id"),
            "params":            r.get("params", {}),
        })

    # Sort by created_at descending (most recent first) then by analysis
    rows.sort(key=lambda x: (x.get("created_at") or "", x.get("analysis") or ""),
              reverse=True)
    return rows


# --------------------------------------------------------------------------- #
# Sets and analyses — sibling sections for the inventory page                  #
# --------------------------------------------------------------------------- #

def scan_sets(registry_root: pathlib.Path) -> List[Dict]:
    """Scan <registry_root>/sets/**/*.json for set_v1 records.
    Returns a list of light rows suitable for the inventory page's Sets tab."""
    registry_root = pathlib.Path(registry_root)
    sets_root = registry_root / "sets"
    out = []
    if not sets_root.is_dir():
        return out
    for p in sorted(sets_root.rglob("*.json")):
        try:
            r = json.loads(p.read_text())
        except Exception:
            continue
        derived = r.get("derived_from") or {}
        out.append({
            "set_id":            r.get("set_id"),
            "entity_type":       r.get("entity_type"),
            "label":             r.get("label"),
            "n_entities":        r.get("n_entities"),
            "coordinate_system": r.get("coordinate_system"),
            "parent_set_id":     r.get("parent_set_id"),
            "derived_op":        derived.get("op"),
            "derived_parents":   derived.get("parents", []),
            "derived_predicate": derived.get("predicate"),
            "filter_profile_id": r.get("filter_profile_id"),
            "intended_use":      r.get("intended_use"),
            "status":            r.get("status", "active"),
            "created_at":        r.get("created_at"),
            "path":              r.get("path"),
        })
    out.sort(key=lambda x: (x.get("entity_type") or "", x.get("set_id") or ""))
    return out


def scan_analyses(registry_root: pathlib.Path) -> List[Dict]:
    """Scan <registry_root>/analyses/*.json for analysis_v1 records."""
    registry_root = pathlib.Path(registry_root)
    analyses_root = registry_root / "analyses"
    out = []
    if not analyses_root.is_dir():
        return out
    for p in sorted(analyses_root.glob("*.json")):
        try:
            r = json.loads(p.read_text())
        except Exception:
            continue
        inputs = r.get("inputs") or {}
        out.append({
            "analysis_id":      r.get("analysis_id"),
            "analysis_version": r.get("analysis_version"),
            "label":            r.get("label"),
            "description":      r.get("description"),
            "inputs_sets":      inputs.get("sets", []),
            "inputs_artifacts": inputs.get("artifacts", []),
            "produces":         r.get("produces", []),
            "engine":           r.get("engine"),
            "endpoint":         r.get("endpoint"),
            "default_runner":   r.get("default_runner"),
            "requires":         r.get("requires", []),
            "intended_use":     r.get("intended_use"),
            "status":           r.get("status", "active"),
        })
    out.sort(key=lambda x: x.get("analysis_id") or "")
    return out


def scan_all(registry_root: pathlib.Path) -> Dict[str, List[Dict]]:
    """Return a combined {results, sets, analyses} payload for the
    inventory page."""
    return {
        "results":  scan(registry_root),
        "sets":     scan_sets(registry_root),
        "analyses": scan_analyses(registry_root),
    }


# --------------------------------------------------------------------------- #
# CLI                                                                          #
# --------------------------------------------------------------------------- #

def _print_table(rows: List[Dict]) -> None:
    """ASCII table for quick terminal viewing."""
    if not rows:
        print("(empty registry)")
        return

    cols = ["analysis", "group_label", "n_samples", "interval", "status", "layer_id"]
    headers = ["Analysis", "Group", "N", "Interval", "Status", "Layer"]

    widths = [len(h) for h in headers]
    for r in rows:
        for i, c in enumerate(cols):
            v = "" if r.get(c) is None else str(r.get(c))
            widths[i] = max(widths[i], len(v))
    # Cap layer column
    widths[-1] = min(widths[-1], 48)

    def fmt(values):
        return " │ ".join(
            str(v).ljust(w)[:w] if i < len(widths) - 1 else (str(v) if len(str(v)) <= w else str(v)[: w - 1] + "…")
            for i, (v, w) in enumerate(zip(values, widths))
        )

    sep = "─┼─".join("─" * w for w in widths)
    print(fmt(headers))
    print(sep)
    for r in rows:
        print(fmt([r.get(c, "") if r.get(c) is not None else "" for c in cols]))
    print()
    print(f"{len(rows)} result(s).")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Scan a toolkit_registries registry and emit the inventory.")
    ap.add_argument("registry_root", nargs="?", help="Path to <registry_root>/. Optional with --example.")
    ap.add_argument("--example", action="store_true", help="Scan toolkit_registries/inventory/example_data/registry/.")
    ap.add_argument("--json", metavar="OUT", help="Write inventory rows to OUT as a JSON array.")
    ap.add_argument("--print", dest="do_print", action="store_true", help="Pretty-print as ASCII table to stdout (default if no --json).")
    args = ap.parse_args(argv)

    if args.example:
        # Resolve relative to this file
        here = pathlib.Path(__file__).resolve().parent
        registry = here.parent / "inventory" / "example_data" / "registry"
    elif args.registry_root:
        registry = pathlib.Path(args.registry_root)
    else:
        ap.print_help()
        return 2

    rows = scan(registry)

    if args.json:
        # Multi-section payload: results + sets + analyses. The HTML page
        # reads this single file to populate all four tabs (Results, Sets,
        # Analyses, Chain).
        payload = {
            "results":  rows,
            "sets":     scan_sets(registry),
            "analyses": scan_analyses(registry),
        }
        pathlib.Path(args.json).write_text(json.dumps(payload, indent=2))
        print(f"wrote {len(rows)} results + "
              f"{len(payload['sets'])} sets + "
              f"{len(payload['analyses'])} analyses → {args.json}",
              file=sys.stderr)
    if args.do_print or not args.json:
        _print_table(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
