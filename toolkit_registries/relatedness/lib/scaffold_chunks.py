#!/usr/bin/env python3
"""
scaffold_chunks.py — emit starter manuscript_chunks rows for chains
                      that lack chunks.

The audit + plan-generator both surface chains as 'ready to run'; the
manuscript writer (page 12) only renders them if a chunk exists. This
script closes the gap: walks chains without chunks, prints a JSONL-
ready scaffold the maintainer can paste into manuscript_chunks.jsonl
and then edit.

Pure read tool. Does NOT modify manuscript_chunks.jsonl — the
maintainer reviews each scaffold and accepts/edits before committing
(same discipline as the dispatcher: propose, never auto-write).

Usage:
    python3 -m lib.scaffold_chunks                       # all chains
    python3 -m lib.scaffold_chunks --analysis bp4_population_overlap
    python3 -m lib.scaffold_chunks --section methods     # only methods scaffolds
    python3 -m lib.scaffold_chunks --paste-ready         # one JSONL line per row
"""
from __future__ import annotations
import argparse
import json
import pathlib
import re
import sys
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


def infer_atlas(analysis_id: str, modes: list[dict], modules: dict) -> str:
    for m in modes:
        if m.get("analysis_type") == analysis_id:
            mod = modules.get(m.get("module_name"))
            if mod and mod.get("atlas"): return mod["atlas"]
    return ""


def starter_methods(reg: dict, atlas: str) -> dict:
    aid = reg["analysis_id"]
    label_short = reg.get("label", aid).split("—")[0].split("(")[0].strip()
    inputs = [s.strip() for s in (reg.get("input_layer_types","") or "").split(",") if s.strip()]
    outputs = [s.strip() for s in (reg.get("produces","") or "").split(",") if s.strip()]
    placeholders = {
        "version": {"source": "registry", "analysis_id": aid, "path": "analysis_version", "default": reg.get("analysis_version","v0")},
    }
    # Add canonical placeholders found in similar existing chunks
    placeholders["sample_set"]   = {"source": "scope", "path": "sample_set",   "default": "qcpass_226"}
    placeholders["candidate_id"] = {"source": "scope", "path": "candidate_id", "default": "inv_LG28_INV_001"}

    in_phrase  = ", ".join(f"`{i}`" for i in inputs[:4]) or "the registered input layers"
    out_phrase = ", ".join(f"`{o}`" for o in outputs[:4]) or "the registered output layers"

    template = (
        f"{label_short} was executed via the `{aid}` adapter "
        f"(v{{{{version}}}}) on the {{{{sample_set}}}} cohort. "
        f"The analysis consumed {in_phrase} and emitted {out_phrase}. "
        f"<!-- EDIT: describe parameters, thresholds, statistical test choice; "
        f"reference the citations relevant to the method —[@RefId]. -->"
    )
    return {
        "chunk_id":     f"methods.{aid}",
        "section":      "methods",
        "atlas":        atlas or "",
        "analysis_id":  aid,
        "label":        f"{label_short} — methods paragraph (SCAFFOLD)",
        "template":     template,
        "placeholders": placeholders,
        "references":   [],
    }


def starter_results(reg: dict, atlas: str) -> dict:
    aid = reg["analysis_id"]
    label_short = reg.get("label", aid).split("—")[0].split("(")[0].strip()
    outputs = [s.strip() for s in (reg.get("produces","") or "").split(",") if s.strip()]
    out_phrase = outputs[0] if outputs else "the analysis output"
    template = (
        f"The {aid} run on {{{{sample_set}}}} produced {{{{n_rows}}}} rows in `{out_phrase}`. "
        f"<!-- EDIT: summarise the headline values, thresholds passed, cohort distribution. "
        f"Cite manuscript table N. -->"
    )
    return {
        "chunk_id":     f"results.{aid}",
        "section":      "results",
        "atlas":        atlas or "",
        "analysis_id":  aid,
        "label":        f"{label_short} — results paragraph (SCAFFOLD)",
        "template":     template,
        "placeholders": {
            "sample_set": {"source": "scope", "path": "sample_set", "default": "qcpass_226"},
            "n_rows":     {"source": "literal", "default": "<EDIT>"},
        },
        "references":   [],
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--analysis",   default="", help="Restrict to one analysis_id.")
    ap.add_argument("--section",    default="methods,results", help="Comma-separated subset of {methods,results}.")
    ap.add_argument("--paste-ready", action="store_true", help="One JSONL line per scaffold (for direct paste).")
    args = ap.parse_args(argv)

    reg     = load_jsonl(REG / "analysis_registry.jsonl")
    modes   = load_jsonl(REG / "analysis_modes.jsonl")
    modules = {m["module_name"]: m for m in load_jsonl(REG / "module_registry.jsonl")}
    chunks  = load_jsonl(REG / "manuscript_chunks.jsonl")

    # Index existing chunks by (analysis_id, section)
    have = defaultdict(set)
    for c in chunks:
        if c.get("analysis_id"):
            have[c["analysis_id"]].add(c.get("section"))

    chains = [r for r in reg if is_chain(r)]
    if args.analysis:
        chains = [r for r in chains if r["analysis_id"] == args.analysis]

    want_sections = [s.strip() for s in args.section.split(",") if s.strip()]
    scaffolds: list[tuple[str, dict]] = []
    for r in chains:
        aid = r["analysis_id"]
        atlas = infer_atlas(aid, modes, modules)
        for sec in want_sections:
            if sec in have[aid]:   # already has a chunk for this section
                continue
            if sec == "methods":
                scaffolds.append((aid, starter_methods(r, atlas)))
            elif sec == "results":
                scaffolds.append((aid, starter_results(r, atlas)))

    if not scaffolds:
        print("OK  every chain already has chunks for the requested sections.")
        return 0

    if args.paste_ready:
        for _aid, row in scaffolds:
            print(json.dumps(row, ensure_ascii=False))
        return 0

    print(f"# {len(scaffolds)} chunk scaffold(s) for chains lacking coverage")
    print(f"# Paste into 01_registry/manuscript_chunks.jsonl after editing each <!-- EDIT --> mark.\n")
    by_atlas: dict[str, list[tuple[str, dict]]] = defaultdict(list)
    for aid, row in scaffolds:
        by_atlas[row.get("atlas") or "(none)"].append((aid, row))
    for atlas in sorted(by_atlas):
        print(f"## atlas: {atlas}")
        for aid, row in sorted(by_atlas[atlas], key=lambda t: t[1]["chunk_id"]):
            print(f"  • {row['chunk_id']:<55} ← {aid}")
        print()
    print("Re-run with --paste-ready to emit JSONL rows.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
