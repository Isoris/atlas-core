#!/usr/bin/env python3
"""
tsv_from_jsonl.py — regenerate the TSV derived view from the canonical JSONL.

Per ADAPTER_CONTRACT.md §5.4: JSONL is canonical; TSV is a derived view
emitted by this script for grep / awk / pandas / Excel viewing. Never
edit the TSVs by hand for adapter-backed rows.

Stdlib only. Idempotent.
"""
from __future__ import annotations

import argparse
import csv
import json
import pathlib
import sys
from typing import Dict, List


# --------------------------------------------------------------------------- #
def _find_root(start: pathlib.Path) -> pathlib.Path:
    p = start.resolve()
    for cand in [p, *p.parents]:
        if (cand / "01_registry").is_dir():
            return cand
    raise SystemExit("could not find 01_registry/ above " + str(start))


def _read_jsonl(path: pathlib.Path) -> List[Dict]:
    if not path.is_file(): return []
    rows = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


# Column orders for each registry. Pulled from the per-row schemas under
# schemas/registry_schemas/*.json (the _tsv_column_order field). We keep
# them inline here so the script has no schema-loading dependency.
COLUMN_ORDERS = {
    "layer_registry": [
        "layer_id", "source_kind", "entity_type", "label", "description",
        "schema_path", "example_path", "default_path", "status", "intended_use", "definition_path"
    ],
    "hook_registry": [
        "hook_id", "page_id", "provides_view", "requires_layers",
        "optional_layers", "panels",
        "scope_dims", "label", "description", "status", "definition_path"
    ],
    "analysis_registry": [
        "analysis_id", "analysis_version", "label", "description",
        "input_entity_types", "input_layer_types", "produces",
        "engine", "endpoint", "default_runner",
        "status", "requires", "intended_use", "definition_path"
    ],
    "analysis_results": [
        "result_id", "analysis_type", "path", "sample_set_id", "group_set_id",
        "interval_set_id", "site_set_id", "input_value_id", "input_result_id",
        "method_id", "params_id", "hash", "status", "created_at", "notes"
    ],
}


def _write_tsv(path: pathlib.Path, rows: List[Dict], columns: List[str]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=columns, delimiter="\t",
                           extrasaction="ignore", restval="")
        w.writeheader()
        for r in rows:
            # Fill any missing column with empty string for stable column count.
            out = {c: (r.get(c, "") if r.get(c) is not None else "") for c in columns}
            w.writerow(out)


# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--registry-root", default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    start = pathlib.Path(args.registry_root) if args.registry_root else pathlib.Path(__file__).parent
    root = _find_root(start)
    reg = root / "01_registry"

    n_written = 0
    for stem, cols in COLUMN_ORDERS.items():
        src = reg / f"{stem}.jsonl"
        if not src.is_file():
            print(f"skip {stem}: no JSONL")
            continue
        rows = _read_jsonl(src)
        dst = reg / f"{stem}.tsv"
        if args.dry_run:
            print(f"would write {dst.name}  ({len(rows)} rows, {len(cols)} cols)")
        else:
            _write_tsv(dst, rows, cols)
            print(f"wrote {dst.name}  ({len(rows)} rows, {len(cols)} cols)")
            n_written += 1
    if not args.dry_run:
        print(f"done: regenerated {n_written} TSV(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
