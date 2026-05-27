#!/usr/bin/env python3
"""
check_chunks.py — validate manuscript_chunks.jsonl against the registry.

Mirrors check_analysis_registry / check_plans in form. Walks every
chunk row and verifies:

  1. schema fields present (chunk_id, section, atlas, analysis_id,
     template, placeholders)
  2. section ∈ {methods, results, discussion}
  3. atlas ∈ atlases.jsonl (when set)
  4. analysis_id ∈ analysis_registry.jsonl (when set)
  5. every {{placeholder}} in template has an entry in placeholders{}
  6. every [@RefId] in template + every references[*] entry exists in
     references.jsonl
  7. placeholders.<name>.source ∈ {literal, scope, scope_or_literal,
     module, registry}
  8. placeholders sourced from `module` reference a module_name in
     module_registry.jsonl
  9. placeholders sourced from `registry` reference an analysis_id
     in analysis_registry.jsonl

Exit 0 if clean; 1 if any check fails. Wired into smoke_all_stack so
chunk drift is caught at commit time.
"""
from __future__ import annotations
import json
import pathlib
import re
import sys

REPO = pathlib.Path(__file__).resolve().parents[3]
REG  = REPO / "toolkit_registries" / "relatedness" / "01_registry"

ALLOWED_SECTIONS = {"methods", "results", "discussion"}
ALLOWED_SOURCES  = {"literal", "scope", "scope_or_literal", "module", "registry"}
REQUIRED_FIELDS  = {"chunk_id", "section", "atlas", "template", "placeholders"}


def load_jsonl(p: pathlib.Path) -> list[dict]:
    if not p.exists(): return []
    return [json.loads(l) for l in p.read_text().splitlines() if l.strip()]


def check(chunks_path: pathlib.Path) -> list[str]:
    chunks    = load_jsonl(chunks_path)
    atlases   = {a["atlas_id"]     for a in load_jsonl(REG / "atlases.jsonl")}
    analyses  = {r["analysis_id"]  for r in load_jsonl(REG / "analysis_registry.jsonl")}
    modules   = {m["module_name"]  for m in load_jsonl(REG / "module_registry.jsonl")}
    refs      = {r["ref_id"]       for r in load_jsonl(REG / "references.jsonl")}

    errs: list[str] = []
    seen_ids: set[str] = set()
    for i, c in enumerate(chunks, start=1):
        cid = c.get("chunk_id", f"<row {i}>")
        miss = REQUIRED_FIELDS - set(c.keys())
        if miss:
            errs.append(f"{cid}: missing required field(s) {sorted(miss)}")

        if c.get("chunk_id") in seen_ids:
            errs.append(f"{cid}: duplicate chunk_id")
        seen_ids.add(c.get("chunk_id"))

        sec = c.get("section")
        if sec and sec not in ALLOWED_SECTIONS:
            errs.append(f"{cid}: section {sec!r} not in {sorted(ALLOWED_SECTIONS)}")

        a = c.get("atlas")
        if a and a not in atlases:
            errs.append(f"{cid}: atlas {a!r} not in atlases.jsonl")

        aid = c.get("analysis_id")
        if aid and aid not in analyses:
            errs.append(f"{cid}: analysis_id {aid!r} not in analysis_registry")

        tpl = c.get("template", "") or ""
        placeholders = c.get("placeholders") or {}

        # 5. every {{name}} has a placeholders entry
        used_in_body = set(re.findall(r"\{\{([a-zA-Z0-9_]+)\}\}", tpl))
        missing_decl = used_in_body - set(placeholders.keys())
        if missing_decl:
            errs.append(f"{cid}: template uses {sorted(missing_decl)} but no placeholders entry")

        # 6. inline [@RefId] + declared references[] both must exist
        inline_refs = set(re.findall(r"\[@([A-Za-z][A-Za-z0-9_]*)\]", tpl))
        decl_refs   = set(c.get("references") or [])
        for r in (inline_refs | decl_refs):
            if r not in refs:
                errs.append(f"{cid}: reference {r!r} not in references.jsonl")

        # 7/8/9. placeholder source consistency
        for name, spec in placeholders.items():
            src = (spec or {}).get("source", "literal")
            if src not in ALLOWED_SOURCES:
                errs.append(f"{cid}.placeholders.{name}: source {src!r} not in {sorted(ALLOWED_SOURCES)}")
            if src == "module":
                mn = (spec or {}).get("module_name")
                if mn and mn not in modules:
                    errs.append(f"{cid}.placeholders.{name}: module_name {mn!r} not in module_registry")
            if src == "registry":
                ra = (spec or {}).get("analysis_id")
                if ra and ra not in analyses:
                    errs.append(f"{cid}.placeholders.{name}: analysis_id {ra!r} not in analysis_registry")

    return errs


def main(argv: list[str] | None = None) -> int:
    chunks_path = REG / "manuscript_chunks.jsonl"
    if not chunks_path.exists():
        print("OK    no manuscript_chunks.jsonl — nothing to check")
        return 0
    n = sum(1 for l in chunks_path.read_text().splitlines() if l.strip())
    errs = check(chunks_path)
    if errs:
        print(f"FAIL  {len(errs)} problem(s) across {n} chunk(s):")
        for e in errs[:60]:
            print(f"  - {e}")
        if len(errs) > 60:
            print(f"  ... and {len(errs) - 60} more")
        return 1
    print(f"OK    {n} chunk(s) clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
