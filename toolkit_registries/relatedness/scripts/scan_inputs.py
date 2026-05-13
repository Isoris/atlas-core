#!/usr/bin/env python3
"""
Scan an inputs directory and propose input_values.tsv rows.

Symmetric counterpart to scan_results.py. Walks a directory tree
looking for input artifacts:

    *.beagle.gz        → BEAGLE_GL
    *.beagle           → BEAGLE_GL
    *.dosage.tsv.gz    → dosage
    *.dosage.tsv       → dosage
    *.saf.idx          → SAF
    *.vcf.gz           → VCF

For each match:
  1. Infers value_type from extension.
  2. Infers a chromosome tag from the filename (LG12, C_gar_LG28,
     global, whole_genome, …).
  3. Looks up sample_set_id / site_set_id / interval_set_id /
     site_tag from a defaults JSON (per-chromosome maps).
  4. For BEAGLE files, ALSO opens the file and reads:
       - the header → derives n_sample_columns
       - row count → n_rows
     so the proposed row is contract-true before it lands.
  5. Skips files already referenced by an existing input_values.tsv
     row (by 'path' match).
  6. Prints a preview TSV. With --apply, appends valid rows.

Defaults JSON (extends scan_defaults.json):

    {
      "inputs": {
        "sample_set_id": "samples_226_v1",
        "site_set_for_chrom":     { "global": "sites_thin500_global_v1", ... },
        "interval_set_for_chrom": { "global": "genome_all_v1",          ... },
        "site_tag_for_chrom":     { "global": "thin500_global",
                                    "C_gar_LG12": "LG12_thin500" }
      }
    }

`site_tag_for_chrom` is used to mint readable value_ids:
  `<value_type_short>_<site_tag>_v1` → e.g. `beagle_LG12_thin500_v1`.

Stdlib only. JSON for the defaults file.

Usage:
    scan_inputs.py --inputs-dir ../03_inputs --defaults ../01_registry/scan_defaults.json
    scan_inputs.py --inputs-dir ../03_inputs --defaults ../01_registry/scan_defaults.json --apply
"""

from __future__ import annotations

import argparse
import csv
import datetime
import hashlib
import json
import pathlib
import re
import sys
from typing import Dict, List, Optional, Tuple

from io_helpers import find_registry_root, load_all, open_text, OK, FAIL, WARN


COLUMNS = [
    "value_id", "value_type", "path", "sample_set_id", "site_set_id",
    "interval_set_id", "n_rows", "n_sample_columns", "hash", "notes",
]


# --------------------------------------------------------------------------- #
# File-pattern recognition                                                     #
# --------------------------------------------------------------------------- #

# Order matters — more specific first.
VALUE_PATTERNS: List[Tuple[re.Pattern, str, str]] = [
    # (regex, value_type, short_prefix_for_id)
    (re.compile(r"\.beagle(\.gz)?$"),      "BEAGLE_GL", "beagle"),
    (re.compile(r"\.dosage\.tsv(\.gz)?$"), "dosage",    "dosage"),
    (re.compile(r"\.saf\.idx$"),           "SAF",       "saf"),
    (re.compile(r"\.vcf\.gz$"),            "VCF",       "vcf"),
]

CHROM_RE = re.compile(
    r"(?:^|[._-])(C_gar_LG\d+|LG\d+|chr\w+|wholegenome|whole_genome|genome|global)(?:[._-]|$)",
    re.IGNORECASE,
)


def infer_value_type(p: pathlib.Path) -> Optional[Tuple[str, str]]:
    """Return (value_type, id_prefix) or None."""
    fname = p.name
    for rx, vtype, prefix in VALUE_PATTERNS:
        if rx.search(fname):
            return vtype, prefix
    return None


def infer_chrom_token(p: pathlib.Path) -> str:
    m = CHROM_RE.search(p.name) or CHROM_RE.search(str(p))
    if not m:
        return ""
    tok = m.group(1)
    tok_l = tok.lower()
    if tok_l in ("wholegenome", "whole_genome", "genome", "global"):
        return "global"
    if tok_l.startswith("c_gar_lg"):
        return "C_gar_" + tok[len("C_gar_"):].upper().replace("LG", "LG")
    if re.match(r"^lg\d+$", tok_l):
        return "C_gar_" + tok.upper()
    if re.match(r"^chr", tok_l):
        return tok
    return tok


def sha256_of(path: pathlib.Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            b = fh.read(chunk)
            if not b: break
            h.update(b)
    return "sha256:" + h.hexdigest()


# --------------------------------------------------------------------------- #
# BEAGLE-specific shape inference                                              #
# --------------------------------------------------------------------------- #

def beagle_header_shape(path: pathlib.Path) -> Tuple[int, int]:
    """Return (n_data_rows, n_sample_columns). n_sample_columns is the
    raw column count minus the 3 marker/allele1/allele2 leader columns
    — for standard BEAGLE GL that's 3 * n_samples."""
    with open_text(path) as fh:
        header = next(fh).rstrip("\n").rstrip("\r")
        n_sample_cols = max(0, len(header.split("\t")) - 3)
        n_rows = sum(1 for line in fh if line.strip())
    return n_rows, n_sample_cols


# --------------------------------------------------------------------------- #
# Defaults                                                                     #
# --------------------------------------------------------------------------- #

def load_defaults(path: Optional[pathlib.Path]) -> Dict:
    if not path: return {}
    with open(path) as fh:
        d = json.load(fh)
    return d.get("inputs") or {}


def lookup_by_chrom(defaults: Dict, key: str, chrom: str) -> str:
    table = defaults.get(key) or {}
    if chrom and chrom in table: return table[chrom]
    if "__any__" in table:        return table["__any__"]
    return ""


# --------------------------------------------------------------------------- #
# value_id naming                                                              #
# --------------------------------------------------------------------------- #

def propose_value_id(prefix: str, site_tag: str, chrom: str, existing_ids: set) -> str:
    """<prefix>_<site_tag>_v1; falls back to <prefix>_<chrom>_v1 if no tag."""
    tag = site_tag or (chrom.replace("C_gar_", "") if chrom else "unscoped")
    base = f"{prefix}_{tag}"
    for v in range(1, 100):
        vid = f"{base}_v{v}"
        if vid not in existing_ids:
            return vid
    return f"{base}_v_TODO"


# --------------------------------------------------------------------------- #
# Scan                                                                         #
# --------------------------------------------------------------------------- #

def scan(inputs_dir: pathlib.Path, registry_root: pathlib.Path, defaults: Dict) -> List[Dict]:
    regs = load_all(registry_root)
    existing_paths = {(r.get("path") or "") for r in regs["input_values"].values()}
    existing_ids   = set(regs["input_values"].keys())

    proposals = []
    for p in sorted(inputs_dir.rglob("*")):
        if not p.is_file(): continue
        match = infer_value_type(p)
        if not match: continue
        vtype, prefix = match

        try:
            rel = str(p.resolve().relative_to(registry_root.resolve()))
        except ValueError:
            rel = str(p)

        already = rel in existing_paths
        chrom = infer_chrom_token(p)
        site_tag = lookup_by_chrom(defaults, "site_tag_for_chrom", chrom)

        prop = {
            "_kind":           vtype,
            "_chrom":          chrom,
            "_already":        already,
            "value_id":        "",
            "value_type":      vtype,
            "path":            rel,
            "sample_set_id":   defaults.get("sample_set_id", ""),
            "site_set_id":     lookup_by_chrom(defaults, "site_set_for_chrom", chrom),
            "interval_set_id": lookup_by_chrom(defaults, "interval_set_for_chrom", chrom),
            "n_rows":          "",
            "n_sample_columns":"",
            "hash":            "",
            "notes":           "scanned by scan_inputs.py",
        }

        if not already:
            prop["value_id"] = propose_value_id(prefix, site_tag, chrom, existing_ids)
            existing_ids.add(prop["value_id"])
            try:
                prop["hash"] = sha256_of(p)
            except Exception:
                pass
            # BEAGLE-specific shape inference
            if vtype == "BEAGLE_GL":
                try:
                    n_rows, n_sample_cols = beagle_header_shape(p)
                    prop["n_rows"] = str(n_rows)
                    prop["n_sample_columns"] = str(n_sample_cols)
                except Exception as e:
                    prop["_warn"] = f"could not parse BEAGLE shape: {e}"

        proposals.append(prop)
    return proposals


# --------------------------------------------------------------------------- #
# FK validation                                                                #
# --------------------------------------------------------------------------- #

def validate(prop: Dict, regs: Dict) -> List[str]:
    errs = []
    fk_targets = [
        ("sample_set_id",   "sample_sets",   True),
        ("site_set_id",     "site_sets",     True),
        ("interval_set_id", "interval_sets", False),
    ]
    for col, table, required in fk_targets:
        v = prop.get(col, "")
        if not v:
            if required:
                errs.append(f"{col} not set; add to inputs.defaults")
            continue
        if v not in regs[table]:
            errs.append(f"{col}='{v}' not in {table}")
    return errs


# --------------------------------------------------------------------------- #
# Preview + apply                                                              #
# --------------------------------------------------------------------------- #

def preview(proposals: List[Dict], regs: Dict) -> Tuple[int, int, int]:
    n_new = n_skip = n_blocked = 0
    for p in proposals:
        if p["_already"]:
            print(f"  {WARN} {p['path']}")
            print(f"      already registered → SKIP")
            n_skip += 1
            continue
        errs = validate(p, regs)
        if errs:
            print(f"  {FAIL} {p['path']}")
            print(f"      value_type: {p['value_type']}   chrom: {p['_chrom'] or '?'}")
            for e in errs:
                print(f"      ✗ {e}")
            n_blocked += 1
            continue
        n_new += 1
        print(f"  {OK} {p['path']}")
        print(f"      value_type:      {p['value_type']}")
        print(f"      chrom:           {p['_chrom'] or '(global / none)'}")
        print(f"      value_id:        {p['value_id']}")
        print(f"      sample_set_id:   {p['sample_set_id']}")
        print(f"      site_set_id:     {p['site_set_id']}")
        print(f"      interval_set_id: {p['interval_set_id'] or '(empty)'}")
        if p.get("n_rows"):
            print(f"      n_rows:          {p['n_rows']}")
            print(f"      n_sample_cols:   {p['n_sample_columns']}")
        if p.get("_warn"):
            print(f"      ⚠  {p['_warn']}")
    print()
    print(f"{n_new} new · {n_skip} already registered · {n_blocked} blocked (fix defaults)")
    return n_new, n_skip, n_blocked


def append_rows(proposals: List[Dict], regs: Dict, registry_root: pathlib.Path) -> int:
    tsv = registry_root / "01_registry/input_values.tsv"
    rows_to_write = []
    for p in proposals:
        if p["_already"]: continue
        if validate(p, regs): continue
        out = {c: p.get(c, "") for c in COLUMNS}
        rows_to_write.append(out)
    if not rows_to_write:
        return 0
    with tsv.open("a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS, delimiter="\t",
                           lineterminator="\n", quoting=csv.QUOTE_MINIMAL)
        for r in rows_to_write:
            w.writerow(r)
    return len(rows_to_write)


# --------------------------------------------------------------------------- #
# CLI                                                                          #
# --------------------------------------------------------------------------- #

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--inputs-dir", required=True,
                    help="Path to the inputs tree (e.g. ../03_inputs, or your real /mnt/e/.../beagle/).")
    ap.add_argument("--defaults",
                    help="JSON file with default FK mappings under an 'inputs' key.")
    ap.add_argument("--apply", action="store_true",
                    help="Append valid proposals to input_values.tsv. Refuses rows with unresolved FKs.")
    ap.add_argument("--registry-root", help="Override registry root.")
    args = ap.parse_args(argv)

    root = pathlib.Path(args.registry_root) if args.registry_root else find_registry_root()
    inputs_dir = pathlib.Path(args.inputs_dir).resolve()
    if not inputs_dir.is_dir():
        sys.exit(f"inputs dir not found: {inputs_dir}")

    defaults_path = pathlib.Path(args.defaults).resolve() if args.defaults else None
    if defaults_path and not defaults_path.exists():
        sys.exit(f"defaults file not found: {defaults_path}")
    defaults = load_defaults(defaults_path)

    print()
    print(f"scanning: {inputs_dir}")
    if defaults_path: print(f"defaults: {defaults_path}  (inputs section)")
    print()

    proposals = scan(inputs_dir, root, defaults)
    if not proposals:
        print("(no candidate input files found)")
        return 0

    regs = load_all(root)
    n_new, n_skip, n_blocked = preview(proposals, regs)

    if args.apply:
        if n_blocked > 0:
            print()
            print(f"{FAIL} {n_blocked} proposal(s) have unresolved FKs — fix the defaults file and re-run.")
            print(f"      Refusing to --apply (no rows written).")
            return 1
        n_wrote = append_rows(proposals, regs, root)
        print()
        print(f"{OK} appended {n_wrote} row(s) → {root / '01_registry' / 'input_values.tsv'}")
    else:
        print()
        print("This was a DRY RUN. Re-run with --apply to actually append the new row(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
