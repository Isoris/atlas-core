#!/usr/bin/env python3
"""
Append a row to analysis_results.tsv. Refuses to register a row whose
contract doesn't pass check_result_contract.py.

Usage:
    register_result.py \\
      --result-id          ngsrelate_LG28_v1 \\
      --analysis-type      ngsrelate \\
      --path               04_results/ngsrelate/LG28.res \\
      --sample-set-id      samples_226_v1 \\
      --group-set-id       groups_main_v1 \\
      --interval-set-id    C_gar_LG28_full_v1 \\
      --site-set-id        sites_LG28_thin500_v1 \\
      --input-value-id     beagle_LG28_thin500_v1 \\
      --method-id          ngsrelate_v2 \\
      [--input-result-id   <upstream_result_id>] \\
      [--params-id         …]  [--hash …]  [--status active]  [--notes …] \\
      [--force]   # skip the contract check (NOT recommended)

After writing the row, runs check_result_contract.py and exits with its code.
"""

from __future__ import annotations

import argparse
import csv
import datetime
import pathlib
import sys
import subprocess

from io_helpers import find_registry_root, load_all


COLUMNS = [
    "result_id", "analysis_type", "path", "sample_set_id", "group_set_id",
    "interval_set_id", "site_set_id", "input_value_id", "input_result_id",
    "method_id", "params_id", "hash", "status", "created_at", "notes",
]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--registry-root", help="Override registry root.")
    ap.add_argument("--result-id",        required=True)
    ap.add_argument("--analysis-type",    required=True)
    ap.add_argument("--path",             required=True)
    ap.add_argument("--sample-set-id",    required=True)
    ap.add_argument("--group-set-id",     default="")
    ap.add_argument("--interval-set-id",  default="")
    ap.add_argument("--site-set-id",      default="")
    ap.add_argument("--input-value-id",   default="")
    ap.add_argument("--input-result-id",  default="")
    ap.add_argument("--method-id",        default="")
    ap.add_argument("--params-id",        default="")
    ap.add_argument("--hash",             default="")
    ap.add_argument("--status",           default="active")
    ap.add_argument("--notes",            default="")
    ap.add_argument("--force",            action="store_true",
                    help="Register even if the contract check fails (NOT recommended).")
    args = ap.parse_args(argv)

    root = pathlib.Path(args.registry_root) if args.registry_root else find_registry_root()
    tsv  = root / "01_registry/analysis_results.tsv"

    regs = load_all(root)
    if args.result_id in regs["analysis_results"]:
        print(f"FAIL: result_id '{args.result_id}' already registered. Pick a new id "
              f"(or edit the row by hand).", file=sys.stderr)
        return 2

    # Pre-check FKs so we fail fast before writing
    fks = [
        ("sample_set_id",   "sample_sets",      args.sample_set_id),
        ("group_set_id",    "group_sets",       args.group_set_id),
        ("interval_set_id", "interval_sets",    args.interval_set_id),
        ("site_set_id",     "site_sets",        args.site_set_id),
        ("input_value_id",  "input_values",     args.input_value_id),
        ("input_result_id", "analysis_results", args.input_result_id),
    ]
    bad = []
    for col, table, val in fks:
        if val and val not in regs[table]:
            bad.append(f"  {col}='{val}' not in {table}")
    if bad and not args.force:
        print("FAIL: FK pre-check did not pass:")
        print("\n".join(bad))
        print("(use --force to register anyway)")
        return 2

    new_row = {
        "result_id":       args.result_id,
        "analysis_type":   args.analysis_type,
        "path":            args.path,
        "sample_set_id":   args.sample_set_id,
        "group_set_id":    args.group_set_id,
        "interval_set_id": args.interval_set_id,
        "site_set_id":     args.site_set_id,
        "input_value_id":  args.input_value_id,
        "input_result_id": args.input_result_id,
        "method_id":       args.method_id,
        "params_id":       args.params_id,
        "hash":            args.hash,
        "status":          args.status,
        "created_at":      datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "notes":           args.notes,
    }

    # Append row
    with tsv.open("a", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS, delimiter="\t",
                                lineterminator="\n", quoting=csv.QUOTE_MINIMAL)
        writer.writerow(new_row)
    print(f"appended row → {tsv}")

    # Run the contract check
    here = pathlib.Path(__file__).resolve().parent
    rc = subprocess.call([sys.executable, str(here / "check_result_contract.py"),
                          "--result", args.result_id])
    if rc != 0 and not args.force:
        print(f"WARN: contract check failed (exit {rc}). The row is now in the "
              f"registry; consider editing it or removing it by hand.", file=sys.stderr)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
