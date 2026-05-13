#!/usr/bin/env python3
"""
The master check. Given a result_id, verify:

  1. The result row exists and all FKs resolve.
  2. The referenced files exist on disk.
  3. The input contract holds:
       - BEAGLE header sample order   == sample_set order
       - BEAGLE row count             == site_set n_sites
       - group_set samples            ⊆ sample_set
       - When input_result_id is set, the upstream result also passes.
  4. Print a green-light report:
       READY FOR: <list of analyses that can consume this result downstream>

Usage:
    check_result_contract.py --result ngsrelate_global_v1
    check_result_contract.py --result mendelian_LG12_v1

Exit code:
    0 = all contracts hold
    1 = at least one contract fails
    2 = bad inputs
"""

from __future__ import annotations

import argparse
import gzip
import pathlib
import sys
from typing import Dict, List

from io_helpers import (
    find_registry_root, load_all, parse_beagle_header, read_sample_ids,
    beagle_count_rows, read_sites_count, read_groups_sample_ids,
    OK, FAIL, WARN,
)


# Static knowledge of which downstream analyses a given analysis_type unblocks.
# Hand-coded for now; later a richer analysis_v1 vocabulary can drive this.
DOWNSTREAM = {
    "ngsrelate":   ["ngspedigree", "relatedness plots", "kinship QC", "family detection"],
    "ngspedigree": ["mendelian", "trio QC", "pedigree-based GWAS"],
    "mendelian":   ["family-QC summary tables", "trio reliability flags"],
    "ngsadmix":    ["population structure plots", "ancestry-aware scans"],
}


def file_exists(root: pathlib.Path, rel: str) -> bool:
    return (root / rel).exists() if rel else False


def check_one(root: pathlib.Path, regs: Dict, result_id: str, depth: int = 0,
              seen: set = None) -> bool:
    """Recursively check a result and any upstream input_result_id.
    Returns True if all checks pass."""
    seen = seen if seen is not None else set()
    if result_id in seen:
        # Cycle protection
        print(f"  {FAIL} cycle detected at {result_id}")
        return False
    seen.add(result_id)
    indent = "  " * depth

    r = regs["analysis_results"].get(result_id)
    if not r:
        print(f"{indent}{FAIL} unknown result_id '{result_id}'")
        return False

    print(f"{indent}RESULT: {result_id}  ({r.get('analysis_type', '?')})")
    ok = True

    # 1. FK integrity
    fks = [
        ("sample_set_id", "sample_sets",   r.get("sample_set_id")),
        ("group_set_id", "group_sets",     r.get("group_set_id")),
        ("interval_set_id","interval_sets",r.get("interval_set_id")),
        ("site_set_id",  "site_sets",      r.get("site_set_id")),
        ("input_value_id","input_values",  r.get("input_value_id")),
    ]
    for col, table, val in fks:
        if not val:
            continue  # optional FK
        if val in regs[table]:
            print(f"{indent}  {OK} {col}: {val}")
        else:
            print(f"{indent}  {FAIL} {col}: '{val}' not in {table}")
            ok = False

    upstream = r.get("input_result_id") or ""
    if upstream:
        if upstream in regs["analysis_results"]:
            print(f"{indent}  {OK} input_result_id: {upstream}")
        else:
            print(f"{indent}  {FAIL} input_result_id: '{upstream}' not in analysis_results")
            ok = False

    # 2. Output file exists
    if not file_exists(root, r.get("path", "")):
        print(f"{indent}  {FAIL} result file missing on disk: {r.get('path')}")
        ok = False
    else:
        print(f"{indent}  {OK} result file exists: {r.get('path')}")

    # 3. Input contract
    sample_set = regs["sample_sets"].get(r.get("sample_set_id", ""))
    site_set   = regs["site_sets"].get(r.get("site_set_id", ""))
    input_val  = regs["input_values"].get(r.get("input_value_id", ""))
    group_set  = regs["group_sets"].get(r.get("group_set_id", ""))

    if input_val and sample_set:
        beagle_path = root / input_val["path"]
        samples_path = root / sample_set["path"]
        if not beagle_path.exists():
            print(f"{indent}  {FAIL} input_value path missing: {input_val['path']}")
            ok = False
        elif not samples_path.exists():
            print(f"{indent}  {FAIL} sample_set path missing: {sample_set['path']}")
            ok = False
        else:
            # BEAGLE header vs samples
            opener = gzip.open if str(beagle_path).endswith(".gz") else open
            with opener(beagle_path, "rt", encoding="utf-8") as fh:
                header_line = next(fh)
            try:
                beagle_samples = parse_beagle_header(header_line)
                expected = read_sample_ids(samples_path)
                if beagle_samples == expected:
                    print(f"{indent}  {OK} BEAGLE header vs samples ({len(expected)} samples in canonical order)")
                else:
                    print(f"{indent}  {FAIL} BEAGLE header vs samples mismatch "
                          f"({len(beagle_samples)} in BEAGLE, {len(expected)} in sample_set)")
                    ok = False
            except Exception as e:
                print(f"{indent}  {FAIL} BEAGLE header parse: {e}")
                ok = False

    if input_val and site_set:
        beagle_path = root / input_val["path"]
        sites_path  = root / site_set["path"]
        if beagle_path.exists() and sites_path.exists():
            n_b = beagle_count_rows(beagle_path)
            n_s = read_sites_count(sites_path)
            if n_b == n_s:
                print(f"{indent}  {OK} BEAGLE rows vs sites ({n_b} rows)")
            else:
                print(f"{indent}  {FAIL} BEAGLE rows vs sites mismatch ({n_b} vs {n_s})")
                ok = False

    if group_set and sample_set:
        groups_path  = root / group_set["path"]
        samples_path = root / sample_set["path"]
        if groups_path.exists() and samples_path.exists():
            in_set = set(read_sample_ids(samples_path))
            in_grp = set(read_groups_sample_ids(groups_path))
            extras = in_grp - in_set
            if extras:
                print(f"{indent}  {FAIL} group_set has {len(extras)} samples not in sample_set: "
                      f"{sorted(extras)[:5]}{'…' if len(extras) > 5 else ''}")
                ok = False
            else:
                print(f"{indent}  {OK} group_set samples ⊆ sample_set")

    # 4. Recurse into upstream result
    if upstream:
        print(f"{indent}  upstream check:")
        upstream_ok = check_one(root, regs, upstream, depth=depth + 2, seen=seen)
        ok = ok and upstream_ok

    return ok


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--result", required=True, help="result_id from analysis_results.tsv")
    ap.add_argument("--registry-root", help="Override registry root.")
    args = ap.parse_args(argv)

    root = pathlib.Path(args.registry_root) if args.registry_root else find_registry_root()
    regs = load_all(root)

    print()
    ok = check_one(root, regs, args.result)
    print()

    r = regs["analysis_results"].get(args.result, {})
    atype = r.get("analysis_type", "")
    print(f"OVERALL: {OK if ok else FAIL}")
    if ok and atype in DOWNSTREAM:
        print(f"READY FOR:")
        for d in DOWNSTREAM[atype]:
            print(f"  • {d}")
    print()
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
