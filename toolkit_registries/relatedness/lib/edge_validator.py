#!/usr/bin/env python3
"""
edge_validator.py — Phase B of LAYER_GRAPH_BUILDER_SPEC.md §6.

Validate a `layer_graph_v1` JSON against the edge-rule table in
`vocabulary/edge_rules.tsv`. Reads:

  vocabulary/edge_rules.tsv     the (from_type, to_type, edge_type, constraint) rows
  layer_registry.tsv            for entity_type / source_kind lookups
  analysis_registry.tsv         for input_layer_types / produces lookups
  hook_registry.tsv             for requires_layers / optional_layers lookups

Stdlib only. Usage:

  python3 -m lib.edge_validator --graph path/to/graph.json
  python3 -m lib.edge_validator --graph -      # read stdin

Exit 0 if every edge passes; 1 if any edge fails. JSON report on stdout.
"""
from __future__ import annotations

import argparse
import csv
import json
import pathlib
import sys
from typing import Dict, List, Optional, Tuple


# --------------------------------------------------------------------------- #
def _find_root(start: pathlib.Path) -> pathlib.Path:
    """Walk upward to find the directory containing both
    01_registry/layer_registry.tsv and (../../)vocabulary/edge_rules.tsv."""
    p = start.resolve()
    for cand in [p, *p.parents]:
        if (cand / "01_registry" / "layer_registry.tsv").is_file():
            return cand
    raise SystemExit("could not find 01_registry/layer_registry.tsv anywhere above " + str(start))


def _find_vocab_root(registry_root: pathlib.Path) -> Optional[pathlib.Path]:
    """The vocabulary/ folder lives in toolkit_registries/, the parent of relatedness/."""
    for cand in [registry_root, *registry_root.parents]:
        if (cand / "vocabulary" / "edge_rules.tsv").is_file():
            return cand
    return None


def _read_tsv(path: pathlib.Path) -> List[Dict[str, str]]:
    if not path.is_file():
        return []
    with open(path, newline="", encoding="utf-8") as fh:
        return [{k: (v if v is not None else "") for k, v in r.items()}
                for r in csv.DictReader(fh, delimiter="\t")]


def _index(rows: List[Dict[str, str]], key: str) -> Dict[str, Dict[str, str]]:
    return {r[key]: r for r in rows if r.get(key)}


def _csv_field(s: Optional[str]) -> List[str]:
    return [x.strip() for x in (s or "").split(",") if x.strip()]


# --------------------------------------------------------------------------- #
class EdgeValidator:
    """Reads the registries + edge_rules.tsv; validates a layer_graph_v1."""

    def __init__(self, registry_root: pathlib.Path,
                 vocab_root: Optional[pathlib.Path] = None):
        self.root = registry_root
        reg = registry_root / "01_registry"
        self.layers   = _index(_read_tsv(reg / "layer_registry.tsv"),   "layer_id")
        self.analyses = _index(_read_tsv(reg / "analysis_registry.tsv"),"analysis_id")
        self.hooks    = _index(_read_tsv(reg / "hook_registry.tsv"),    "hook_id")
        # The edge_rules.tsv lives in toolkit_registries/vocabulary/, one or
        # two directories up from the registry root.
        vroot = vocab_root or _find_vocab_root(registry_root)
        if vroot is None:
            raise SystemExit("could not find vocabulary/edge_rules.tsv "
                             "near " + str(registry_root))
        self.rules = _read_tsv(vroot / "vocabulary" / "edge_rules.tsv")

    # ---- public ----
    def validate(self, graph: Dict) -> Dict:
        nodes_by_id = {n["id"]: n for n in graph.get("nodes", [])}
        errors: List[Dict] = []
        warnings: List[Dict] = []

        for n in graph.get("nodes", []):
            err = self._validate_node(n)
            if err: errors.append(err)

        for edge in graph.get("edges", []):
            if not (isinstance(edge, list) and len(edge) == 3):
                errors.append({"edge": edge, "error": "edge must be a 3-tuple [from_id, to_id, edge_type]"})
                continue
            from_id, to_id, edge_type = edge
            from_node = nodes_by_id.get(from_id)
            to_node   = nodes_by_id.get(to_id)
            if not from_node:
                errors.append({"edge": edge, "error": f"from_id {from_id!r} not in nodes[]"})
                continue
            if not to_node:
                errors.append({"edge": edge, "error": f"to_id {to_id!r} not in nodes[]"})
                continue
            ok, why = self._validate_edge(from_node, to_node, edge_type)
            if not ok:
                errors.append({"edge": edge,
                               "from_type": from_node.get("type"),
                               "to_type":   to_node.get("type"),
                               "error": why})

        # Sanity: every node referenced by an edge exists (already checked above).
        return {
            "graph_id": graph.get("graph_id", "<no id>"),
            "n_nodes":  len(graph.get("nodes", [])),
            "n_edges":  len(graph.get("edges", [])),
            "valid":    not errors,
            "errors":   errors,
            "warnings": warnings,
        }

    # ---- node validation ----
    def _validate_node(self, n: Dict) -> Optional[Dict]:
        nt = n.get("type")
        nid = n.get("id", "<?>")
        if nt == "layer":
            lid = n.get("layer_id")
            if not lid:
                return {"node": nid, "error": "layer node missing layer_id"}
            if lid not in self.layers and not n.get("stub"):
                return {"node": nid, "error": f"layer_id {lid!r} not in layer_registry (set stub=true if intentional)"}
        elif nt == "analysis":
            aid = n.get("analysis_id")
            if not aid:
                return {"node": nid, "error": "analysis node missing analysis_id"}
            if aid not in self.analyses and not n.get("stub"):
                return {"node": nid, "error": f"analysis_id {aid!r} not in analysis_registry"}
        elif nt == "hook":
            hid = n.get("hook_id")
            if not hid:
                return {"node": nid, "error": "hook node missing hook_id"}
            if hid not in self.hooks and not n.get("stub"):
                return {"node": nid, "error": f"hook_id {hid!r} not in hook_registry"}
        elif nt == "set":
            if not n.get("entity_type"):
                return {"node": nid, "error": "set node missing entity_type"}
        elif nt == "filter":
            if not n.get("input"):
                return {"node": nid, "error": "filter node missing 'input' (graph-local id)"}
        else:
            return {"node": nid, "error": f"unknown node type {nt!r}"}
        return None

    # ---- edge validation ----
    def _validate_edge(self, from_node: Dict, to_node: Dict, edge_type: str) -> Tuple[bool, str]:
        ft, tt = from_node.get("type"), to_node.get("type")
        rule = next((r for r in self.rules
                     if r["from_type"] == ft
                     and r["to_type"]   == tt
                     and r["edge_type"] == edge_type), None)
        if not rule:
            return False, f"no edge rule for ({ft} -> {tt}, {edge_type})"
        constraint = rule.get("constraint", "always")
        # Evaluate constraint
        if constraint == "always":
            return True, ""
        if constraint == "entity_type_match":
            from_et = from_node.get("entity_type", "")
            to_et   = (to_node.get("entity_type", "")
                       or self.layers.get(to_node.get("layer_id", ""), {}).get("entity_type", ""))
            if not from_et or not to_et:
                return False, "entity_type_match: missing entity_type on one side"
            return (from_et == to_et), (
                f"entity_type_match: {from_et!r} != {to_et!r}" if from_et != to_et else "")
        if constraint == "layer_in_inputs":
            aid = to_node.get("analysis_id")
            lid = from_node.get("layer_id")
            inputs = _csv_field(self.analyses.get(aid, {}).get("input_layer_types"))
            if lid in inputs:
                return True, ""
            return False, f"layer_in_inputs: {lid!r} not in {aid!r}.input_layer_types={inputs}"
        if constraint == "layer_in_produces":
            aid = from_node.get("analysis_id")
            lid = to_node.get("layer_id")
            produces = _csv_field(self.analyses.get(aid, {}).get("produces"))
            if lid in produces:
                return True, ""
            return False, f"layer_in_produces: {lid!r} not in {aid!r}.produces={produces}"
        if constraint == "layer_in_requires_or_optional":
            hid = to_node.get("hook_id")
            lid = from_node.get("layer_id")
            row = self.hooks.get(hid, {})
            allowed = _csv_field(row.get("requires_layers")) + _csv_field(row.get("optional_layers"))
            if lid in allowed:
                return True, ""
            return False, f"layer_in_requires_or_optional: {lid!r} not in {hid!r} required/optional layers"
        return False, f"unknown constraint {constraint!r}"


# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--graph", required=True, help="path to a layer_graph_v1 JSON; '-' for stdin")
    ap.add_argument("--registry-root", default=None)
    ap.add_argument("--quiet", action="store_true", help="suppress JSON report on success")
    args = ap.parse_args()

    text = sys.stdin.read() if args.graph == "-" else pathlib.Path(args.graph).read_text(encoding="utf-8")
    graph = json.loads(text)

    start = pathlib.Path(args.registry_root) if args.registry_root else pathlib.Path(__file__).parent
    root = _find_root(start)
    v = EdgeValidator(root)
    report = v.validate(graph)
    if not (args.quiet and report["valid"]):
        print(json.dumps(report, indent=2))
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    sys.exit(main())
