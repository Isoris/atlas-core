#!/usr/bin/env python3
"""
plan_generator.py — emit panel_plan_v1 plans from chain audit.

Walks analysis_registry.jsonl, identifies chain analyses, infers
panel_plan_v1 step phases (stage / render / propose / narrate) from
the chain's input/output declarations + the manuscript chunks tied to
the chain. Writes one plan file per chain to 02_queue/plans/ and
maintains index.json so page 14 can render them.

The conductor (DYNAMIC_PANELS_SPEC §27) will eventually consume these
plans through panel_coverage_graph. Until that lands, this script is
the simplest path from "chain registered" to "plan reviewable on
page 14".

§refusals (mirrors the dispatcher's):
  1. No execution. Plans are reviewed, accepted, dismissed — never
     run from here.
  2. No registry writes. Reads JSONL, writes plan files only.
  3. No invented panels. Step.panel_id values are either registered
     in panels.jsonl OR labelled "TODO" — fail visibly.

Usage:
    python3 -m lib.plan_generator              # write plans + index
    python3 -m lib.plan_generator --list       # show what would be written
    python3 -m lib.plan_generator --clear      # remove non-example plans
"""
from __future__ import annotations
import argparse
import json
import pathlib
import sys
import time
from collections import defaultdict

REPO = pathlib.Path(__file__).resolve().parents[3]
REG  = REPO / "toolkit_registries" / "relatedness" / "01_registry"
PQ   = REPO / "toolkit_registries" / "relatedness" / "02_queue" / "plans"

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


def is_chain(reg: dict) -> bool:
    if reg.get("analysis_id") in CHAIN_FORCE: return True
    eng = (reg.get("engine", "") or "").lower()
    if eng.endswith("_chain"): return True
    desc = reg.get("description", "") or ""
    return "CHAIN:" in desc or "(chain)" in desc.lower()


def collect_chunks_for(analysis_id: str, chunks: list[dict]) -> list[dict]:
    return [c for c in chunks if c.get("analysis_id") == analysis_id]


def infer_atlas(analysis_id: str, modes: list[dict], modules: dict) -> str:
    for m in modes:
        if m.get("analysis_type") == analysis_id:
            mod = modules.get(m.get("module_name"))
            if mod and mod.get("atlas"): return mod["atlas"]
    return ""


def gate_for_layer(layer_id: str, layers: dict, producer_map: dict, modules: dict, modes_by_atype: dict) -> dict:
    L = layers.get(layer_id)
    # file-source layers are inherently ready
    if L and L.get("source_kind") == "file":
        return {"graph": "layer_graph", "node": layer_id, "state": "ready", "passes": True}
    producers = producer_map.get(layer_id) or []
    if not producers:
        return {"graph": "layer_graph", "node": layer_id, "state": "no_producer", "passes": False}
    # check if any producer's module has last_run_status=success + ready=true
    for aid in producers:
        for m in modes_by_atype.get(aid, []):
            mod = modules.get(m.get("module_name"))
            if mod and mod.get("last_run_status") == "success" and mod.get("ready") == "true":
                return {"graph": "layer_graph", "node": layer_id, "state": "ready", "passes": True}
    return {"graph": "layer_graph", "node": layer_id, "state": "producer_not_run", "passes": False}


def build_plan(chain: dict, ctx: dict) -> dict:
    aid = chain["analysis_id"]
    atlas = infer_atlas(aid, ctx["modes"], ctx["modules_by_name"])
    label = chain.get("label", aid)
    description = chain.get("description", "")

    # Determine the required inputs from analysis_modes.required_dimensions
    required_layers = set()
    for m in ctx["modes_by_atype"].get(aid, []):
        for d in (m.get("required_dimensions", "") or "").split(","):
            d = d.strip()
            if d and d in ctx["layers_by_id"]:
                required_layers.add(d)

    # Output layers (chain.produces)
    output_layers = [s.strip() for s in (chain.get("produces", "") or "").split(",") if s.strip()]

    # Build steps
    steps = []
    # STAGE phase: one per required input that's a scope-shaped layer (file-source)
    # plus a candidate_picker step if the chain consumes candidate_id-shaped inputs
    for L in sorted(required_layers):
        layer = ctx["layers_by_id"].get(L, {})
        if layer.get("source_kind") == "file":
            steps.append({
                "phase":          "stage",
                "panel_id":       f"{L}_picker",
                "role":           "scope_input",
                "from_analysis":  aid,
                "gates_status":   [gate_for_layer(L, ctx["layers_by_id"], ctx["producer_map"], ctx["modules_by_name"], ctx["modes_by_atype"])],
            })

    # RENDER phase: one per output layer
    for L in output_layers:
        steps.append({
            "phase":          "render",
            "panel_id":       f"{L}_card",
            "role":           "primary_result",
            "from_analysis":  aid,
            "expects_layers": [L],
            "gates_status":   [gate_for_layer(L, ctx["layers_by_id"], ctx["producer_map"], ctx["modules_by_name"], ctx["modes_by_atype"])],
        })

    # PROPOSE phase: one next-action step gated on chain readiness
    n_blocked = sum(1 for s in steps if s.get("gates_status") and not s["gates_status"][0]["passes"])
    chain_tier = "ready" if n_blocked == 0 else ("one" if n_blocked == 1 else "multi")
    steps.append({
        "phase":         "propose",
        "panel_id":      "next_action_proposal",
        "role":          "action",
        "from_analysis": aid,
        "actions": [{
            "action_id":    "queue_chain",
            "label":        f"Queue {aid} manifest",
            "kind":         "dispatch",
            "gates_status": [{"graph": "chain_graph", "node": aid, "tier": chain_tier, "passes": chain_tier in ("ready", "one")}],
            "enabled":      chain_tier in ("ready", "one"),
        }],
    })

    # NARRATE phase: one step per manuscript chunk tied to this chain
    for ch in collect_chunks_for(aid, ctx["chunks"]):
        steps.append({
            "phase":          "narrate",
            "panel_id":       "manuscript_chunks_panel",
            "role":           "writeup",
            "from_analysis":  aid,
            "filter":         {"manuscript_chunks.chunk_id": ch["chunk_id"]},
        })

    n_steps = len(steps)
    n_ready = sum(1 for s in steps if all(g.get("passes") for g in (s.get("gates_status") or [])))
    n_blocked_total = sum(1 for s in steps if not all(g.get("passes") for g in (s.get("gates_status") or [])))
    n_actions_enabled = sum(1 for s in steps for a in (s.get("actions") or []) if a.get("enabled"))

    first_unblocking = None
    for s in steps:
        if s["phase"] != "stage": continue
        for g in (s.get("gates_status") or []):
            if not g.get("passes") and g.get("state") == "producer_not_run":
                # find the first producer of that layer
                producers = ctx["producer_map"].get(g["node"], [])
                if producers:
                    first_unblocking = f"run_{producers[0]}_module"; break
        if first_unblocking: break

    plan_id = f"plan_auto_{aid}"
    plan = {
        "schema_version": "panel_plan_v1",
        "plan_id":        plan_id,
        "generated_at":   time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "goal":           f"Run {label}",
        "source": {
            "kind":            "chain_audit_auto",
            "funnel_session":  "",
            "vocab_activated": [],
        },
        "scope_required": {
            "atlas":        atlas or "",
            "cohort":       "",
            "sample_set":   "",
            "candidate_id": "",
        },
        "steps":   steps,
        "summary": {
            "n_steps":                 n_steps,
            "n_ready":                 n_ready,
            "n_gated_blocked":         n_blocked_total,
            "n_actions_enabled":       n_actions_enabled,
            "first_unblocking_action": first_unblocking or "",
        },
        "_provenance": {
            "from_dispatcher_plan_id": "",
            "atlas":                   atlas or "",
            "cohort":                  "",
            "generator":               "lib.plan_generator",
        },
    }
    return plan


def load_ctx() -> dict:
    reg = load_jsonl(REG / "analysis_registry.jsonl")
    modes = load_jsonl(REG / "analysis_modes.jsonl")
    modules = load_jsonl(REG / "module_registry.jsonl")
    layers = load_jsonl(REG / "layer_registry.jsonl")
    chunks = load_jsonl(REG / "manuscript_chunks.jsonl")
    modes_by_atype = defaultdict(list)
    for m in modes: modes_by_atype[m["analysis_type"]].append(m)
    producer_map = defaultdict(list)
    for m in modes:
        for L in (m.get("produces", "") or "").split(","):
            L = L.strip()
            if L: producer_map[L].append(m["analysis_type"])
    return {
        "registry":        reg,
        "modes":           modes,
        "modules_by_name": {m["module_name"]: m for m in modules},
        "layers_by_id":    {L["layer_id"]: L for L in layers},
        "chunks":          chunks,
        "modes_by_atype":  modes_by_atype,
        "producer_map":    producer_map,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--list",  action="store_true", help="dry-run; show what would be written")
    ap.add_argument("--clear", action="store_true", help="remove non-example plans + rewrite index")
    args = ap.parse_args(argv)
    PQ.mkdir(parents=True, exist_ok=True)

    if args.clear:
        n = 0
        for p in PQ.glob("plan_auto_*.json"):
            p.unlink(); n += 1
        # also rewrite an empty index, preserving any example seed
        _rewrite_index()
        print(f"  cleared {n} auto-generated plans + rewrote index")
        return 0

    ctx = load_ctx()
    chains = [r for r in ctx["registry"] if is_chain(r)]
    written = []
    for c in chains:
        plan = build_plan(c, ctx)
        if args.list:
            written.append((plan["plan_id"], plan["goal"], plan["summary"]["n_steps"]))
        else:
            out = PQ / (plan["plan_id"] + ".json")
            out.write_text(json.dumps(plan, indent=2) + "\n")
            written.append((plan["plan_id"], plan["goal"], plan["summary"]["n_steps"]))

    if args.list:
        for pid, goal, ns in written:
            print(f"  {pid:<60} {ns:>2} steps  {goal}")
        print(f"  --- would write {len(written)} plans")
        return 0

    _rewrite_index()
    print(f"  wrote {len(written)} plans to {PQ}")
    return 0


def _rewrite_index():
    # Build index covering every plan_*.json present (example + auto)
    files = sorted(PQ.glob("plan_*.json"))
    entries = []
    for f in files:
        p = json.loads(f.read_text())
        entries.append({
            "plan_id":      p["plan_id"],
            "goal":         p.get("goal", ""),
            "generated_at": p.get("generated_at", ""),
            "n_steps":      p.get("summary", {}).get("n_steps", 0),
            "n_ready":      p.get("summary", {}).get("n_ready", 0),
            "n_blocked":    p.get("summary", {}).get("n_gated_blocked", 0),
            "atlas":        p.get("scope_required", {}).get("atlas", ""),
            "cohort":       p.get("scope_required", {}).get("cohort", ""),
            "file":         f.name,
        })
    idx = {
        "schema_version": "queue_plan_index_v1",
        "plans_dir":      str(PQ.relative_to(REPO)),
        "rewritten_at":   time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "n":              len(entries),
        "entries":        entries,
    }
    (PQ / "index.json").write_text(json.dumps(idx, indent=2) + "\n")


if __name__ == "__main__":
    sys.exit(main())
