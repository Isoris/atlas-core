#!/usr/bin/env python3
"""
build_atlas_dependency_graph.py — emit 01_registry/graphs/atlas_dependency_graph.json.

Per DYNAMIC_PANELS_SPEC §18.1. Nodes are atlas_ids; edges encode the
depends_on_atlases declarative dependency. Lightest of the five graphs;
the conductor uses it for cross-atlas gating in spawn rules.
"""
from __future__ import annotations
import json
import pathlib
import sys
import time

REPO = pathlib.Path(__file__).resolve().parents[3]
REG  = REPO / "toolkit_registries" / "relatedness" / "01_registry"


def load_jsonl(p: pathlib.Path) -> list[dict]:
    if not p.exists(): return []
    return [json.loads(l) for l in p.read_text().splitlines() if l.strip()]


def build() -> dict:
    atlases = load_jsonl(REG / "atlases.jsonl")
    nodes = [{
        "id":     a["atlas_id"],
        "kind":   "atlas",
        "label":  a.get("label", a["atlas_id"]),
        "status": a.get("status", "?"),
        "color":  a.get("color", "#6c727f"),
    } for a in atlases]
    valid_ids = {a["atlas_id"] for a in atlases}
    edges = []
    seen = set()
    for a in atlases:
        for dep in (a.get("depends_on_atlases") or []):
            key = (a["atlas_id"], dep)
            if key in seen: continue
            seen.add(key)
            edges.append({"from": a["atlas_id"], "to": dep, "kind": "depends_on",
                          "satisfied": dep in valid_ids})
    return {
        "schema_version": "atlas_dependency_graph_v1",
        "rewritten_at":   time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "n_nodes":        len(nodes),
        "n_edges":        len(edges),
        "nodes":          nodes,
        "edges":          edges,
    }


def main(argv: list[str] | None = None) -> int:
    out_dir = REG / "graphs"
    out_dir.mkdir(parents=True, exist_ok=True)
    g = build()
    out = out_dir / "atlas_dependency_graph.json"
    out.write_text(json.dumps(g, indent=2) + "\n")
    print(f"wrote {out.relative_to(REPO)}  ({g['n_nodes']} atlases, {g['n_edges']} dependencies)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
