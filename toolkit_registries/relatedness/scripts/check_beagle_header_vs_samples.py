#!/usr/bin/env python3
"""
Verify a BEAGLE GL file's per-sample column ORDER matches a sample_set.

Usage:
    check_beagle_header_vs_samples.py --value beagle_thin500_global_v1
    check_beagle_header_vs_samples.py --beagle PATH --samples PATH

The first form looks up the row in input_values.tsv + sample_sets.tsv.

Exit code: 0 = match, 1 = mismatch, 2 = bad inputs.
"""

from __future__ import annotations

import argparse
import pathlib
import sys

from io_helpers import (
    find_registry_root, load_all, parse_beagle_header, read_sample_ids, OK, FAIL,
)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--value", help="value_id from input_values.tsv")
    ap.add_argument("--beagle", help="Direct path to .beagle.gz")
    ap.add_argument("--samples", help="Direct path to samples TSV")
    ap.add_argument("--registry-root", help="Override registry root (parent of 01_registry/)")
    args = ap.parse_args(argv)

    root = pathlib.Path(args.registry_root) if args.registry_root else find_registry_root()

    if args.value:
        regs = load_all(root)
        v = regs["input_values"].get(args.value)
        if not v:
            print(f"unknown value_id '{args.value}'", file=sys.stderr); return 2
        beagle_path = root / v["path"]
        ss = regs["sample_sets"].get(v["sample_set_id"])
        if not ss:
            print(f"value '{args.value}' references unknown sample_set_id '{v['sample_set_id']}'", file=sys.stderr); return 2
        samples_path = root / ss["path"]
    elif args.beagle and args.samples:
        beagle_path = pathlib.Path(args.beagle)
        samples_path = pathlib.Path(args.samples)
    else:
        ap.print_help(); return 2

    # Read header
    import gzip
    opener = gzip.open if str(beagle_path).endswith(".gz") else open
    with opener(beagle_path, "rt", encoding="utf-8") as fh:
        header = next(fh)
    beagle_samples = parse_beagle_header(header)

    expected = read_sample_ids(samples_path)

    print(f"BEAGLE:  {beagle_path}")
    print(f"samples: {samples_path}")
    print(f"  beagle has {len(beagle_samples)} samples; expected {len(expected)}")

    if beagle_samples == expected:
        print(f"  {OK} order + identity match")
        return 0

    # Detailed diff
    if len(beagle_samples) != len(expected):
        print(f"  {FAIL} count mismatch ({len(beagle_samples)} vs {len(expected)})")
    else:
        bad = []
        for i, (b, e) in enumerate(zip(beagle_samples, expected)):
            if b != e:
                bad.append((i, b, e))
        if bad:
            print(f"  {FAIL} order mismatch in {len(bad)} positions:")
            for i, b, e in bad[:8]:
                print(f"    pos {i}: BEAGLE='{b}'  expected='{e}'")
            if len(bad) > 8:
                print(f"    … and {len(bad) - 8} more")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
