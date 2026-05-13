#!/usr/bin/env python3
"""
Verify a BEAGLE GL file's row count matches the registered site_set's
n_sites. Optionally also verifies the marker column (chrom_pos) matches
the sites file row-by-row.

Usage:
    check_beagle_rows_vs_sites.py --value beagle_thin500_global_v1
    check_beagle_rows_vs_sites.py --beagle PATH --sites PATH [--strict-marker]

Exit code: 0 = match, 1 = mismatch, 2 = bad inputs.
"""

from __future__ import annotations

import argparse
import pathlib
import sys

from io_helpers import (
    find_registry_root, load_all, beagle_count_rows, beagle_rows_iter,
    open_text, read_sites_count, OK, FAIL, WARN,
)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--value",  help="value_id from input_values.tsv")
    ap.add_argument("--beagle", help="Direct path to .beagle.gz")
    ap.add_argument("--sites",  help="Direct path to sites TSV(.gz)")
    ap.add_argument("--strict-marker", action="store_true",
                    help="Also verify each marker matches chrom_pos in the sites file (in order).")
    ap.add_argument("--registry-root", help="Override registry root.")
    args = ap.parse_args(argv)

    root = pathlib.Path(args.registry_root) if args.registry_root else find_registry_root()

    if args.value:
        regs = load_all(root)
        v = regs["input_values"].get(args.value)
        if not v:
            print(f"unknown value_id '{args.value}'", file=sys.stderr); return 2
        beagle_path = root / v["path"]
        ss = regs["site_sets"].get(v["site_set_id"])
        if not ss:
            print(f"value '{args.value}' references unknown site_set_id '{v['site_set_id']}'", file=sys.stderr); return 2
        sites_path = root / ss["path"]
        declared_n = int(ss["n_sites"]) if ss.get("n_sites") else None
    elif args.beagle and args.sites:
        beagle_path = pathlib.Path(args.beagle)
        sites_path  = pathlib.Path(args.sites)
        declared_n  = None
    else:
        ap.print_help(); return 2

    n_beagle = beagle_count_rows(beagle_path)
    n_sites  = read_sites_count(sites_path)

    print(f"BEAGLE: {beagle_path}")
    print(f"sites:  {sites_path}")
    print(f"  beagle data rows: {n_beagle}")
    print(f"  sites rows:       {n_sites}")
    if declared_n is not None:
        print(f"  declared n_sites: {declared_n}")

    rc = 0
    if n_beagle != n_sites:
        print(f"  {FAIL} row count mismatch")
        rc = 1
    elif declared_n is not None and n_sites != declared_n:
        print(f"  {WARN} sites file has {n_sites} rows but registry declares {declared_n}")
        rc = 1
    else:
        print(f"  {OK} row counts agree")

    if args.strict_marker:
        # Walk both in lockstep
        with open_text(sites_path) as sfh:
            next(sfh)  # header
            site_iter = (line.rstrip().split("\t") for line in sfh if line.strip())
            mismatches = []
            for i, (marker, _a1, _a2, _ndata) in enumerate(beagle_rows_iter(beagle_path)):
                try:
                    chrom, pos = next(site_iter)[:2]
                except StopIteration:
                    mismatches.append((i, marker, "(EOF in sites)"))
                    break
                expected = f"{chrom}_{pos}"
                if marker != expected:
                    mismatches.append((i, marker, expected))
            if mismatches:
                print(f"  {FAIL} marker mismatches: {len(mismatches)} (showing first 5)")
                for i, m, e in mismatches[:5]:
                    print(f"    row {i}: BEAGLE='{m}'  expected='{e}'")
                rc = 1
            else:
                print(f"  {OK} markers match sites file row-by-row")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
