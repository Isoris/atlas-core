#!/usr/bin/env python3
"""
check_addons.py — validate addons.jsonl against the registries it claims.

Per ADDON_SPEC v0: each addon row enumerates what it lands in each
registry (the "claims" map) and what files it ships (the "files"
list). This validator walks every row and verifies:

  1. addon_id unique
  2. schema_version == 'addon_manifest_v1'
  3. kind ∈ {panel, page_extension, page, analysis, bridge, validator}
  4. status ∈ {experimental, active, deprecated}
  5. every claimed registry file is one of the known files
  6. every claimed id resolves to an existing row in that registry
     (via the registry's canonical id field — see ID_FIELD_BY_FILE)
  7. every shipped file (relative path) exists on disk
  8. every depends_on addon_id resolves to another row

Exit 0 / 1 like the rest of the suite. Wired into smoke_all_stack.
"""
from __future__ import annotations
import json
import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parents[3]
TK   = REPO / "toolkit_registries"
REG  = TK / "relatedness" / "01_registry"

ALLOWED_KINDS    = {"panel", "page_extension", "page", "analysis", "bridge", "validator"}
ALLOWED_STATUSES = {"experimental", "active", "deprecated"}

# Per-registry id field. Adding a registry: extend this map.
ID_FIELD_BY_FILE: dict[str, str] = {
    "panels.jsonl":              "panel_id",
    "spawn_rules.jsonl":         "rule_id",
    "pages.jsonl":               "page_id",
    "analysis_registry.jsonl":   "analysis_id",
    "module_registry.jsonl":     "module_id",
    "layer_registry.jsonl":      "layer_id",
    "external_databases.jsonl":  "db_id",
    "manuscript_chunks.jsonl":   "chunk_id",
    "references.jsonl":          "ref_id",
    "atlases.jsonl":             "atlas_id",
    "cohorts.jsonl":             "cohort_id",
}


def load_jsonl(p: pathlib.Path) -> list[dict]:
    if not p.exists(): return []
    return [json.loads(l) for l in p.read_text().splitlines() if l.strip()]


def registry_ids(filename: str) -> set[str]:
    field = ID_FIELD_BY_FILE[filename]
    return {r[field] for r in load_jsonl(REG / filename) if field in r}


def check() -> list[str]:
    errs: list[str] = []
    addons = load_jsonl(REG / "addons.jsonl")
    addon_ids = {a["addon_id"] for a in addons if a.get("addon_id")}

    seen: set[str] = set()
    for i, a in enumerate(addons, start=1):
        aid = a.get("addon_id", f"<row {i}>")
        if not a.get("addon_id"):
            errs.append(f"{aid}: missing addon_id"); continue
        if a["addon_id"] in seen:
            errs.append(f"{aid}: duplicate addon_id")
        seen.add(a["addon_id"])

        if a.get("schema_version") != "addon_manifest_v1":
            errs.append(f"{aid}: schema_version != 'addon_manifest_v1' (got {a.get('schema_version')!r})")
        if a.get("kind") not in ALLOWED_KINDS:
            errs.append(f"{aid}: kind {a.get('kind')!r} not in {sorted(ALLOWED_KINDS)}")
        if a.get("status") not in ALLOWED_STATUSES:
            errs.append(f"{aid}: status {a.get('status')!r} not in {sorted(ALLOWED_STATUSES)}")

        claims = a.get("claims") or {}
        for filename, ids in claims.items():
            if filename not in ID_FIELD_BY_FILE:
                errs.append(f"{aid}.claims: {filename!r} not in known registries {sorted(ID_FIELD_BY_FILE)}")
                continue
            available = registry_ids(filename)
            for claimed in ids:
                if claimed not in available:
                    errs.append(f"{aid}.claims[{filename}]: id {claimed!r} not found in {filename}")

        for relpath in (a.get("files") or []):
            abspath = TK / relpath
            if not abspath.exists():
                errs.append(f"{aid}.files: {relpath!r} not found under toolkit_registries/")

        for dep in (a.get("depends_on") or []):
            if dep not in addon_ids:
                errs.append(f"{aid}.depends_on: addon_id {dep!r} not in addons.jsonl")

    return errs


def main(argv: list[str] | None = None) -> int:
    errs = check()
    n = sum(1 for _ in load_jsonl(REG / "addons.jsonl"))
    if errs:
        print(f"FAIL  {len(errs)} problem(s) across {n} addon(s):")
        for e in errs[:50]:
            print(f"  - {e}")
        if len(errs) > 50:
            print(f"  ... and {len(errs) - 50} more")
        return 1
    print(f"OK    {n} addon(s) clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
