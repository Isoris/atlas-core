#!/usr/bin/env python3
"""
build_panel_coverage_graph.py — emit 01_registry/graphs/panel_coverage_graph.json.

Sixth registered graph per DYNAMIC_PANELS_SPEC §25. Bidirectional cache
of analysis ↔ panel relationships, derived purely from existing
registry rows + manuscript_chunks rows.

Nodes:
  - analysis (kind: analysis)   one per analysis_registry row
  - panel    (kind: panel)      one per panels.jsonl row
  - atlas    (kind: atlas)      one per atlases.jsonl row

Edges:
  - analysis_to_panel       analysis → panel
    Where the link comes from:
      • spawn_rule.when.page['workspace_health'] ∋ panel → if panel
        wraps a registry that includes the analysis_id, mark the edge.
        Coarse but useful: the cohort/atlas/etc summary cards link to
        every atlas's analyses.
      • manuscript chunk: chunk.analysis_id = X AND
        chunk's chunk_id pattern matches panel layout → bind.
        Today the only such panel is manuscript_chunks_panel; the
        binding is via filter.manuscript_chunks.analysis_id.
      • plan steps already encode this directly: plan.steps[*].from_analysis
        + plan.steps[*].panel_id pair. We walk those for the strongest
        signal.

  - panel_to_atlas          panel → atlas (panel.atlas)

  - analysis_to_atlas       analysis → atlas (via module.atlas)

The graph isn't authoritative — it's a derived cache rebuilt on every
registry reload. Conductor and plan generator read it; nobody writes
it but this script.

Usage:
    python3 -m lib.build_panel_coverage_graph

Wired into smoke_all_stack so cache drift is caught at commit time.
"""
from __future__ import annotations
import json
import pathlib
import sys
import time
from collections import defaultdict

REPO = pathlib.Path(__file__).resolve().parents[3]
REG  = REPO / "toolkit_registries" / "relatedness" / "01_registry"
PQ   = REPO / "toolkit_registries" / "relatedness" / "02_queue" / "plans"


def load_jsonl(p: pathlib.Path) -> list[dict]:
    if not p.exists(): return []
    return [json.loads(l) for l in p.read_text().splitlines() if l.strip()]


def build() -> dict:
    atlases  = load_jsonl(REG / "atlases.jsonl")
    panels   = load_jsonl(REG / "panels.jsonl")
    analyses = load_jsonl(REG / "analysis_registry.jsonl")
    modules  = {m["module_name"]: m for m in load_jsonl(REG / "module_registry.jsonl")}
    modes    = load_jsonl(REG / "analysis_modes.jsonl")
    chunks   = load_jsonl(REG / "manuscript_chunks.jsonl")

    # nodes
    nodes = []
    for a in atlases:    nodes.append({"id": a["atlas_id"],     "kind": "atlas",    "label": a.get("label", a["atlas_id"]), "color": a.get("color", "#6c727f")})
    for a in analyses:   nodes.append({"id": a["analysis_id"],  "kind": "analysis", "label": a.get("label", a["analysis_id"]), "status": a.get("status", "?")})
    for p in panels:     nodes.append({"id": p["panel_id"],     "kind": "panel",    "label": p.get("label", p["panel_id"]),    "atlas": p.get("atlas", "")})

    # edges
    edges: list[dict] = []
    seen: set[tuple] = set()
    def add_edge(src, dst, kind, **extras):
        key = (src, dst, kind)
        if key in seen: return
        seen.add(key)
        edges.append({"from": src, "to": dst, "kind": kind, **extras})

    # panel → atlas
    for p in panels:
        if p.get("atlas"):
            add_edge(p["panel_id"], p["atlas"], "panel_in_atlas")

    # analysis → atlas (via module.atlas — find any mode whose module is in this analysis)
    for a in analyses:
        aid = a["analysis_id"]
        for m in modes:
            if m.get("analysis_type") == aid:
                mod = modules.get(m.get("module_name"))
                if mod and mod.get("atlas"):
                    add_edge(aid, mod["atlas"], "analysis_in_atlas")

    # analysis ↔ panel via plan steps (strongest binding)
    plan_files = sorted(PQ.glob("plan_*.json")) if PQ.exists() else []
    for f in plan_files:
        try:
            plan = json.loads(f.read_text())
        except Exception:
            continue
        for step in plan.get("steps", []):
            fa = step.get("from_analysis")
            pid = step.get("panel_id")
            if fa and pid:
                add_edge(fa, pid, "analysis_produces_panel",
                         phase=step.get("phase"), role=step.get("role"))

    # analysis ↔ panel via manuscript_chunks (chunk binds chunk.analysis_id ↔ manuscript_chunks_panel)
    chunks_panel = "manuscript_chunks_panel"
    if any(p["panel_id"] == chunks_panel for p in panels):
        for c in chunks:
            if c.get("analysis_id"):
                add_edge(c["analysis_id"], chunks_panel, "analysis_writes_chunk",
                         chunk_id=c["chunk_id"], section=c.get("section"))

    # roll-ups (counts the conductor can query without re-walking)
    by_atlas_analysis = defaultdict(int)
    by_atlas_panel    = defaultdict(int)
    for e in edges:
        if e["kind"] == "analysis_in_atlas": by_atlas_analysis[e["to"]] += 1
        if e["kind"] == "panel_in_atlas":    by_atlas_panel[e["to"]]    += 1

    return {
        "schema_version": "panel_coverage_graph_v1",
        "rewritten_at":   time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "n_nodes":        len(nodes),
        "n_edges":        len(edges),
        "nodes":          nodes,
        "edges":          edges,
        "rollups": {
            "analyses_per_atlas": dict(by_atlas_analysis),
            "panels_per_atlas":   dict(by_atlas_panel),
        },
    }


def main(argv: list[str] | None = None) -> int:
    out_dir = REG / "graphs"
    out_dir.mkdir(parents=True, exist_ok=True)
    g = build()
    out = out_dir / "panel_coverage_graph.json"
    out.write_text(json.dumps(g, indent=2) + "\n")
    print(f"wrote {out.relative_to(REPO)}  ({g['n_nodes']} nodes, {g['n_edges']} edges)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
