#!/usr/bin/env python3
"""
check_analysis_registry.py — validate analysis_registry.tsv shape + FK targets.

Stdlib only. Run with no args from anywhere inside the relatedness/ tree.

What it checks
--------------
1. analysis_registry.tsv parses, all rows have the schema's required columns,
   `status` is one of {active, experimental, deprecated}, and `analysis_id`
   is unique across rows.
2. Every `analysis_type` referenced by `analysis_modes.tsv` resolves to an
   `analysis_id` in the registry.  This is the canonical mode-table -> catalog FK.
3. Every `analysis_type` referenced by `analysis_results.tsv` resolves to an
   `analysis_id` in the registry.  Existing results stay valid.
4. Every mode's `produces` is one of the comma-separated `produces` values
   declared on its parent registry row.  (Layer-type consistency.)
5. Every mode's `module_name` resolves to a row in `module_registry.tsv`,
   when the module registry is present.
6. Each registry row's `requires` (comma-separated upstream analysis_ids) all
   resolve to other rows in the same file.

Exit code 0 when clean, 1 when any rule fails.
"""
from __future__ import annotations

import csv
import pathlib
import sys
from typing import Dict, List, Set, Tuple

REQUIRED_COLS = {
    "analysis_id", "analysis_version", "status",
}
ALL_COLS = [
    "analysis_id", "analysis_version", "label", "description",
    "input_entity_types", "input_layer_types", "produces",
    "engine", "endpoint", "default_runner",
    "status", "requires", "intended_use", "definition_path",
]
ALLOWED_STATUS = {"active", "experimental", "deprecated", "stub"}


def _find_root(start: pathlib.Path) -> pathlib.Path:
    for cand in [start.resolve(), *start.resolve().parents]:
        if (cand / "01_registry" / "analysis_registry.tsv").is_file():
            return cand
    raise SystemExit("could not find 01_registry/analysis_registry.tsv anywhere above " + str(start))


def _read_tsv(path: pathlib.Path) -> List[Dict[str, str]]:
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        return [{k: (v if v is not None else "") for k, v in r.items()} for r in reader]


def main() -> int:
    root = _find_root(pathlib.Path(__file__).parent)
    reg_dir = root / "01_registry"
    errors: List[str] = []

    registry_path = reg_dir / "analysis_registry.tsv"
    rows = _read_tsv(registry_path)
    if not rows:
        errors.append(f"{registry_path.name}: file is empty")
        _report(registry_path, errors)
        return 1

    header = list(rows[0].keys())
    missing = REQUIRED_COLS - set(header)
    if missing:
        errors.append(f"{registry_path.name}: header missing required columns {sorted(missing)}")
    extras = set(header) - set(ALL_COLS)
    if extras:
        errors.append(f"{registry_path.name}: header has unexpected columns {sorted(extras)}")

    seen_ids: Set[str] = set()
    for i, r in enumerate(rows, start=2):
        aid = r.get("analysis_id", "")
        if not aid:
            errors.append(f"{registry_path.name}:{i}: empty analysis_id")
            continue
        if aid in seen_ids:
            errors.append(f"{registry_path.name}:{i}: duplicate analysis_id {aid!r}")
        seen_ids.add(aid)
        if not r.get("analysis_version"):
            errors.append(f"{registry_path.name}:{i}: empty analysis_version on {aid!r}")
        s = r.get("status", "")
        if s not in ALLOWED_STATUS:
            errors.append(f"{registry_path.name}:{i}: status {s!r} not in {sorted(ALLOWED_STATUS)} on {aid!r}")

    # 6. requires FK
    for i, r in enumerate(rows, start=2):
        req = (r.get("requires") or "").strip()
        if not req:
            continue
        for upstream in [x.strip() for x in req.split(",") if x.strip()]:
            if upstream not in seen_ids:
                errors.append(f"{registry_path.name}:{i}: requires {upstream!r} not in registry (row {r.get('analysis_id')!r})")

    # 2. analysis_modes FK
    modes_path = reg_dir / "analysis_modes.tsv"
    mode_rows: List[Dict[str, str]] = []
    if modes_path.is_file():
        mode_rows = _read_tsv(modes_path)
        for i, m in enumerate(mode_rows, start=2):
            atype = m.get("analysis_type", "")
            if atype and atype not in seen_ids:
                errors.append(f"{modes_path.name}:{i}: analysis_type {atype!r} not in analysis_registry")

    # 4. produces consistency (modes' single produces value must be in registry's comma list)
    registry_by_id = {r["analysis_id"]: r for r in rows if r.get("analysis_id")}
    for i, m in enumerate(mode_rows, start=2):
        atype = m.get("analysis_type", "")
        mp = (m.get("produces") or "").strip()
        if not atype or atype not in registry_by_id or not mp:
            continue
        declared = {x.strip() for x in (registry_by_id[atype].get("produces") or "").split(",") if x.strip()}
        if declared and mp not in declared:
            errors.append(
                f"{modes_path.name}:{i}: produces {mp!r} not declared on registry row "
                f"{atype!r} (declared: {sorted(declared)})"
            )

    # 5. module_name FK
    mod_path = reg_dir / "module_registry.tsv"
    if mod_path.is_file() and mode_rows:
        modules = {r.get("module_name", "") for r in _read_tsv(mod_path) if r.get("module_name")}
        for i, m in enumerate(mode_rows, start=2):
            mn = m.get("module_name", "")
            if mn and mn not in modules:
                errors.append(f"{modes_path.name}:{i}: module_name {mn!r} not in module_registry.tsv")

    # 3. analysis_results FK
    results_path = reg_dir / "analysis_results.tsv"
    if results_path.is_file():
        for i, r in enumerate(_read_tsv(results_path), start=2):
            atype = r.get("analysis_type", "")
            if atype and atype not in seen_ids:
                errors.append(f"{results_path.name}:{i}: analysis_type {atype!r} not in analysis_registry")

    _report(registry_path, errors)
    return 1 if errors else 0


def _report(registry_path: pathlib.Path, errors: List[str]) -> None:
    if errors:
        print(f"FAIL  {registry_path.parent.parent}: {len(errors)} problem(s)")
        for e in errors:
            print("  -", e)
    else:
        print(f"OK    {registry_path.parent.parent}: analysis_registry.tsv + FKs clean")


if __name__ == "__main__":
    sys.exit(main())
