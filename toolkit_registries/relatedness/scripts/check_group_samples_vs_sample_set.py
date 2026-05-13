#!/usr/bin/env python3
"""
Verify a group_set's samples are a subset of (or equal to) its sample_set.

Usage:
    check_group_samples_vs_sample_set.py --group groups_main_v1
    check_group_samples_vs_sample_set.py --groups-file PATH --samples PATH

Exit code: 0 = subset, 1 = mismatch (samples in groups not in sample_set), 2 = bad inputs.
"""

from __future__ import annotations

import argparse
import pathlib
import sys

from io_helpers import (
    find_registry_root, load_all, read_sample_ids, read_groups_sample_ids, OK, FAIL, WARN,
)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--group", help="group_set_id from group_sets.tsv")
    ap.add_argument("--groups-file", help="Direct path to groups TSV")
    ap.add_argument("--samples", help="Direct path to samples TSV")
    ap.add_argument("--registry-root", help="Override registry root.")
    args = ap.parse_args(argv)

    root = pathlib.Path(args.registry_root) if args.registry_root else find_registry_root()

    if args.group:
        regs = load_all(root)
        g = regs["group_sets"].get(args.group)
        if not g:
            print(f"unknown group_set_id '{args.group}'", file=sys.stderr); return 2
        groups_path = root / g["path"]
        ss = regs["sample_sets"].get(g["sample_set_id"])
        if not ss:
            print(f"group '{args.group}' references unknown sample_set_id '{g['sample_set_id']}'", file=sys.stderr); return 2
        samples_path = root / ss["path"]
    elif args.groups_file and args.samples:
        groups_path = pathlib.Path(args.groups_file)
        samples_path = pathlib.Path(args.samples)
    else:
        ap.print_help(); return 2

    in_set    = set(read_sample_ids(samples_path))
    in_groups = read_groups_sample_ids(groups_path)
    in_groups_set = set(in_groups)

    extras = in_groups_set - in_set
    print(f"groups:  {groups_path}  ({len(in_groups)} samples)")
    print(f"samples: {samples_path}  ({len(in_set)} samples)")

    if extras:
        print(f"  {FAIL} {len(extras)} sample(s) in groups but NOT in sample_set:")
        for s in sorted(extras)[:10]:
            print(f"    {s}")
        return 1

    print(f"  {OK} every sample in groups is in sample_set")
    missing = in_set - in_groups_set
    if missing:
        print(f"  {WARN} {len(missing)} sample(s) in sample_set lack group rows (OK if ungrouped is intentional)")
        for s in sorted(missing)[:5]:
            print(f"    {s}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
