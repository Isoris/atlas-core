#!/usr/bin/env python3
"""
build_chain_graph.py — emit 01_registry/graphs/chain_graph.json.

Per DYNAMIC_PANELS_SPEC §18.1. Nodes are chain analysis_ids; edges
encode the chain → required-producer → producer-chain relationship.

Tier annotation per chain:
  ready       all required layers have a producer with
              last_run_status='success' and ready='true'
  one         one required layer is missing/unready
  multi       more than one is missing/unready
  blocked     at least one required layer has no producer at all
"""
from __future__ import annotations
import json
import pathlib
import sys
import time
from collections import defaultdict

REPO = pathlib.Path(__file__).resolve().parents[3]
REG  = REPO / "toolkit_registries" / "relatedness" / "01_registry"

CHAIN_FORCE = {
    "hpp_offspring_pipeline", "interchromosomal_inversion_effect",
    "intrachromosomal_co_karyotype_effect", "nco_inside_vs_outside_inversion",
    "regime_topology", "per_sample_diversity_assembly",
    "ancestry_het_test_battery", "cohort_master_assembly",
    "banding_pipeline_full", "haplotype_regimes_het_mode",
    "bp_atlas_pipeline", "gene_order_consolidation", "archaeology_synthesis",
    "regime_mendelian_annotation", "regime_pedigree_inference",
    "msmc_per_founder_background", "relatedness_per_chrom_adaptive",
    "bp4_population_overlap",
}


def load_jsonl(p: pathlib.Path) -> list[dict]:
    if not p.exists(): return []
    return [json.loads(l) for l in p.read_text().splitlines() if l.strip()]


def is_chain(r: dict) -> bool:
    if r.get("analysis_id") in CHAIN_FORCE: return True
    eng = (r.get("engine", "") or "").lower()
    if eng.endswith("_chain"): return True
    desc = r.get("description", "") or ""
    return "CHAIN:" in desc or "(chain)" in desc.lower()


def layer_ready(layer_id: str, layers: dict, producer_map: dict, modules: dict, modes_by_atype: dict) -> bool:
    L = layers.get(layer_id)
    if L and L.get("source_kind") == "file":
        return True
    for aid in producer_map.get(layer_id, []):
        for m in modes_by_atype.get(aid, []):
            mod = modules.get(m.get("module_name"))
            if mod and mod.get("last_run_status") == "success" and mod.get("ready") == "true":
                return True
    return False


def build() -> dict:
    reg = load_jsonl(REG / "analysis_registry.jsonl")
    modes = load_jsonl(REG / "analysis_modes.jsonl")
    layers = {L["layer_id"]: L for L in load_jsonl(REG / "layer_registry.jsonl")}
    modules = {m["module_name"]: m for m in load_jsonl(REG / "module_registry.jsonl")}
    modes_by_atype = defaultdict(list)
    for m in modes: modes_by_atype[m["analysis_type"]].append(m)
    producer_map = defaultdict(list)
    for m in modes:
        for p in (m.get("produces", "") or "").split(","):
            p = p.strip()
            if p: producer_map[p].append(m["analysis_type"])

    chains = [r for r in reg if is_chain(r)]
    nodes = []
    for c in chains:
        aid = c["analysis_id"]
        # required layers from all modes
        required = set()
        for m in modes_by_atype.get(aid, []):
            for d in (m.get("required_dimensions", "") or "").split(","):
                d = d.strip()
                if d in layers: required.add(d)
        # classify
        missing_no_producer = [L for L in required if not producer_map.get(L) and layers.get(L, {}).get("source_kind") != "file"]
        unready             = [L for L in required if not layer_ready(L, layers, producer_map, modules, modes_by_atype)]
        if missing_no_producer:        tier = "blocked"
        elif len(unready) == 0:        tier = "ready"
        elif len(unready) == 1:        tier = "one"
        else:                          tier = "multi"
        nodes.append({"id": aid, "kind": "chain", "label": c.get("label", aid),
                      "tier": tier, "n_required": len(required), "n_unready": len(unready)})

    edges = []
    seen_e = set()
    def add_edge(src, dst, kind, **extras):
        key = (src, dst, kind)
        if key in seen_e: return
        seen_e.add(key)
        edges.append({"from": src, "to": dst, "kind": kind, **extras})

    # chain → required layers → producer analyses
    chain_ids = {n["id"] for n in nodes}
    for c in chains:
        aid = c["analysis_id"]
        for m in modes_by_atype.get(aid, []):
            for d in (m.get("required_dimensions", "") or "").split(","):
                d = d.strip()
                if d in layers:
                    add_edge(aid, d, "chain_requires_layer",
                             source_kind=layers[d].get("source_kind"))
                    for prod in producer_map.get(d, []):
                        add_edge(d, prod, "layer_produced_by")

    rollup_by_tier = defaultdict(int)
    for n in nodes: rollup_by_tier[n["tier"]] += 1

    return {
        "schema_version": "chain_graph_v1",
        "rewritten_at":   time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "n_nodes":        len(nodes),
        "n_edges":        len(edges),
        "nodes":          nodes,
        "edges":          edges,
        "rollups": {"by_tier": dict(rollup_by_tier)},
    }


def main(argv: list[str] | None = None) -> int:
    out_dir = REG / "graphs"
    out_dir.mkdir(parents=True, exist_ok=True)
    g = build()
    out = out_dir / "chain_graph.json"
    out.write_text(json.dumps(g, indent=2) + "\n")
    by = g["rollups"]["by_tier"]
    print(f"wrote {out.relative_to(REPO)}  ({g['n_nodes']} chains: "
          f"ready={by.get('ready',0)} one={by.get('one',0)} "
          f"multi={by.get('multi',0)} blocked={by.get('blocked',0)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
