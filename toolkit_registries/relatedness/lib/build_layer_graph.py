#!/usr/bin/env python3
"""
build_layer_graph.py — emit 01_registry/graphs/layer_graph.json.

Per DYNAMIC_PANELS_SPEC §18.1. Nodes are layer_ids; edges encode the
consumed_by / produced_by relationship walked from layer_registry +
analysis_modes (required_dimensions + produces columns).

Nodes:
  - layer (kind: layer)        one per layer_registry row
  - analysis (kind: analysis)  one per analysis_modes row's analysis_type

Edges:
  - produced_by   layer ← analysis    (mode.produces == layer)
  - consumed_by   layer → analysis    (mode.required_dimensions contains layer)
  - is_input      layer (when source_kind == 'file') — annotated, not an edge

The conductor's layer_graph gate uses this to answer:
  - "is layer X ready?"   (any producer with last_run_status=success)
  - "who consumes X?"     (downstream analyses)
  - "is X a file input?"  (no producer expected)
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
    layers   = load_jsonl(REG / "layer_registry.jsonl")
    modes    = load_jsonl(REG / "analysis_modes.jsonl")
    analyses = load_jsonl(REG / "analysis_registry.jsonl")
    modules  = {m["module_name"]: m for m in load_jsonl(REG / "module_registry.jsonl")}

    nodes = []
    for L in layers:
        nodes.append({
            "id":          L["layer_id"],
            "kind":        "layer",
            "source_kind": L.get("source_kind", "?"),
            "status":      L.get("status", "?"),
            "label":       L.get("label", L["layer_id"]),
        })
    seen_a = set()
    for m in modes:
        aid = m.get("analysis_type")
        if aid and aid not in seen_a:
            nodes.append({"id": aid, "kind": "analysis", "label": aid})
            seen_a.add(aid)

    edges = []
    seen_e = set()
    def add_edge(src, dst, kind, **extras):
        key = (src, dst, kind)
        if key in seen_e: return
        seen_e.add(key)
        edges.append({"from": src, "to": dst, "kind": kind, **extras})

    layer_ids = {n["id"] for n in nodes if n["kind"] == "layer"}
    for m in modes:
        aid = m.get("analysis_type")
        if not aid: continue
        # produces
        for p in (m.get("produces", "") or "").split(","):
            p = p.strip()
            if p in layer_ids:
                # Determine module last_run_status if available — annotates the edge
                mod = modules.get(m.get("module_name", ""))
                mod_status = mod.get("last_run_status", "") if mod else ""
                add_edge(aid, p, "produced_by", mode=m.get("mode", ""),
                         module=m.get("module_name", ""), last_run_status=mod_status)
        # required_dimensions (consumed)
        for d in (m.get("required_dimensions", "") or "").split(","):
            d = d.strip()
            if d in layer_ids:
                add_edge(d, aid, "consumed_by", mode=m.get("mode", ""),
                         module=m.get("module_name", ""))

    # Roll-ups
    file_layers       = sum(1 for n in nodes if n["kind"] == "layer" and n["source_kind"] == "file")
    analysis_layers   = sum(1 for n in nodes if n["kind"] == "layer" and n["source_kind"] == "analysis_result")
    orphan_layers     = [n["id"] for n in nodes if n["kind"] == "layer"
                          and n["source_kind"] != "file"
                          and not any(e["kind"] == "produced_by" and e["to"] == n["id"] for e in edges)]
    terminal_layers   = [n["id"] for n in nodes if n["kind"] == "layer"
                          and not any(e["kind"] == "consumed_by" and e["from"] == n["id"] for e in edges)]

    return {
        "schema_version": "layer_graph_v1",
        "rewritten_at":   time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "n_nodes":        len(nodes),
        "n_edges":        len(edges),
        "nodes":          nodes,
        "edges":          edges,
        "rollups": {
            "file_layers":         file_layers,
            "analysis_layers":     analysis_layers,
            "orphan_layers":       orphan_layers,
            "terminal_layers":     terminal_layers,
        },
    }


def main(argv: list[str] | None = None) -> int:
    out_dir = REG / "graphs"
    out_dir.mkdir(parents=True, exist_ok=True)
    g = build()
    out = out_dir / "layer_graph.json"
    out.write_text(json.dumps(g, indent=2) + "\n")
    print(f"wrote {out.relative_to(REPO)}  ({g['n_nodes']} nodes, {g['n_edges']} edges)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
