#!/usr/bin/env python3
"""
Scan a results directory and propose analysis_results.tsv rows.

Walks <results-dir> looking for files that match known patterns
(*.res → ngsRelate, pedigree*.tsv → ngsPedigree, *mendelian*.tsv →
mendelian, *.qopt → ngsadmix). For each match:

  1. Infers analysis_type from directory / filename.
  2. Infers a chromosome tag from the filename (LG12, C_gar_LG28,
     global, whole_genome, …).
  3. Looks up sample_set_id / site_set_id / interval_set_id /
     input_value_id / group_set_id / method_id from a defaults JSON
     (per-chromosome map; see 01_registry/scan_defaults.json).
  4. Skips files already referenced by an existing analysis_results.tsv
     row (by 'path' match).
  5. Prints a preview TSV. With --apply, appends the resolved rows.

Dry run is the default. --apply REFUSES rows that still have <TODO> or
unresolved FKs — fix the defaults file, re-run, then --apply.

Usage:
    scan_results.py --results-dir ../04_results --defaults ../01_registry/scan_defaults.json
    scan_results.py --results-dir ../04_results --defaults ../01_registry/scan_defaults.json --apply

Stdlib only. JSON for the defaults file (no PyYAML dep).
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

from io_helpers import find_registry_root, load_all, OK, FAIL, WARN


COLUMNS = [
    "result_id", "analysis_type", "path", "sample_set_id", "group_set_id",
    "interval_set_id", "site_set_id", "input_value_id", "input_result_id",
    "method_id", "params_id", "hash", "status", "created_at", "notes",
]


# --------------------------------------------------------------------------- #
# File-pattern recognition                                                     #
# --------------------------------------------------------------------------- #

# Order matters — more specific first.
ANALYSIS_PATTERNS: List[Tuple[re.Pattern, str]] = [
    (re.compile(r"mendelian.*\.tsv$"),    "mendelian"),
    (re.compile(r"pedigree.*\.tsv$"),     "ngspedigree"),
    (re.compile(r"\.res$"),               "ngsrelate"),
    (re.compile(r"\.qopt$"),              "ngsadmix"),
]

# Chromosome / scope tokens in filenames.
CHROM_RE = re.compile(
    r"(?:^|[._-])(C_gar_LG\d+|LG\d+|chr\w+|wholegenome|whole_genome|genome|global)(?:[._-]|$)",
    re.IGNORECASE,
)


def infer_analysis_type(p: pathlib.Path) -> Optional[str]:
    """Match the basename, then fall back to parent directory hint."""
    fname = p.name
    for rx, atype in ANALYSIS_PATTERNS:
        if rx.search(fname):
            return atype
    # parent-dir hint (so a/ngsrelate/something.tsv → ngsrelate)
    for part in reversed(p.parts):
        for _, atype in ANALYSIS_PATTERNS:
            if atype in part.lower():
                return atype
    return None


def infer_chrom_token(p: pathlib.Path) -> str:
    """Return a canonical chromosome tag. Empty string when nothing matched."""
    m = CHROM_RE.search(p.name)
    if not m:
        # try the whole path
        m = CHROM_RE.search(str(p))
    if not m:
        return ""
    tok = m.group(1)
    tok_l = tok.lower()
    if tok_l in ("wholegenome", "whole_genome", "genome", "global"):
        return "global"
    if tok_l.startswith("c_gar_lg"):
        # already canonical
        return "C_gar_" + tok[len("C_gar_"):].upper().replace("LG", "LG")
    if re.match(r"^lg\d+$", tok_l):
        # bare LG28 → C_gar_LG28 by convention (overridable in defaults)
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
# Defaults file                                                                #
# --------------------------------------------------------------------------- #

def load_defaults(path: Optional[pathlib.Path]) -> Dict:
    if not path:
        return {}
    with open(path) as fh:
        d = json.load(fh)
    if not isinstance(d, dict):
        sys.exit(f"defaults file {path} must be a JSON object")
    return d


def lookup_by_chrom(defaults: Dict, key: str, chrom: str) -> str:
    """Pick a default keyed by chrom token; fall back to '__any__' if present."""
    table = defaults.get(key) or {}
    if chrom and chrom in table: return table[chrom]
    if "__any__" in table:        return table["__any__"]
    return ""


# --------------------------------------------------------------------------- #
# Result_id naming                                                             #
# --------------------------------------------------------------------------- #

def propose_result_id(analysis_type: str, chrom: str, existing_ids: set) -> str:
    """<analysis_type>_<chrom_or_global>_v1; bump version on collision."""
    chrom_tag = chrom or "unscoped"
    chrom_tag = chrom_tag.replace("C_gar_", "")  # shorter
    base = f"{analysis_type}_{chrom_tag}"
    for v in range(1, 100):
        rid = f"{base}_v{v}"
        if rid not in existing_ids:
            return rid
    return f"{base}_v_TODO"


# --------------------------------------------------------------------------- #
# Scan                                                                         #
# --------------------------------------------------------------------------- #

def scan(results_dir: pathlib.Path,
         registry_root: pathlib.Path,
         defaults: Dict) -> List[Dict]:
    regs = load_all(registry_root)
    existing_paths = {(r.get("path") or "") for r in regs["analysis_results"].values()}
    existing_ids   = set(regs["analysis_results"].keys())

    proposals = []
    for p in sorted(results_dir.rglob("*")):
        if not p.is_file():
            continue
        atype = infer_analysis_type(p)
        if not atype:
            continue

        # Path relative to registry_root (TSV uses relative paths).
        try:
            rel = str(p.resolve().relative_to(registry_root.resolve()))
        except ValueError:
            rel = str(p)

        already = rel in existing_paths
        chrom = infer_chrom_token(p)
        if not chrom and atype in ("ngspedigree",):
            chrom = "global"

        prop = {
            "_kind":           atype,
            "_chrom":          chrom,
            "_already":        already,
            "result_id":       "",
            "analysis_type":   atype,
            "path":            rel,
            "sample_set_id":   defaults.get("sample_set_id", ""),
            "group_set_id":    defaults.get("group_set_id", ""),
            "interval_set_id": lookup_by_chrom(defaults, "interval_set_for_chrom", chrom),
            "site_set_id":     lookup_by_chrom(defaults, "site_set_for_chrom", chrom),
            "input_value_id":  lookup_by_chrom(defaults, "input_value_for_chrom", chrom),
            "input_result_id": "",
            "method_id":       (defaults.get("method_id_by_analysis") or {}).get(atype, ""),
            "params_id":       "",
            "hash":            "",
            "status":          "active",
            "created_at":      datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "notes":           "scanned by scan_results.py",
        }

        if not already:
            prop["result_id"] = propose_result_id(atype, chrom, existing_ids)
            existing_ids.add(prop["result_id"])
            try:
                prop["hash"] = sha256_of(p)
            except Exception:
                pass

        proposals.append(prop)
    return proposals


# --------------------------------------------------------------------------- #
# FK validation (before --apply)                                               #
# --------------------------------------------------------------------------- #

def validate(prop: Dict, regs: Dict) -> List[str]:
    """Return a list of validation errors for this proposal. Empty = valid."""
    errs = []
    fk_targets = [
        ("sample_set_id",   "sample_sets"),
        ("group_set_id",    "group_sets"),
        ("interval_set_id", "interval_sets"),
        ("site_set_id",     "site_sets"),
        ("input_value_id",  "input_values"),
    ]
    for col, table in fk_targets:
        v = prop.get(col, "")
        if not v:
            # Required-ish: sample_set + interval are needed for most analyses.
            if col in ("sample_set_id", "interval_set_id"):
                errs.append(f"{col} not set; add to defaults file")
            continue
        if v not in regs[table]:
            errs.append(f"{col}='{v}' not in {table}")
    return errs


# --------------------------------------------------------------------------- #
# Pretty printer                                                               #
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
            print(f"      analysis_type: {p['analysis_type']}   chrom: {p['_chrom'] or '?'}")
            for e in errs:
                print(f"      ✗ {e}")
            n_blocked += 1
            continue
        n_new += 1
        print(f"  {OK} {p['path']}")
        print(f"      analysis_type:   {p['analysis_type']}")
        print(f"      chrom:           {p['_chrom'] or '(global / none)'}")
        print(f"      result_id:       {p['result_id']}")
        print(f"      sample_set_id:   {p['sample_set_id']}")
        print(f"      interval_set_id: {p['interval_set_id']}")
        print(f"      site_set_id:     {p['site_set_id'] or '(empty)'}")
        print(f"      input_value_id:  {p['input_value_id'] or '(empty)'}")
        print(f"      method_id:       {p['method_id'] or '(empty)'}")
    print()
    print(f"{n_new} new · {n_skip} already registered · {n_blocked} blocked (fix defaults)")
    return n_new, n_skip, n_blocked


# --------------------------------------------------------------------------- #
# Append                                                                       #
# --------------------------------------------------------------------------- #

def append_rows(proposals: List[Dict], regs: Dict, registry_root: pathlib.Path) -> int:
    tsv = registry_root / "01_registry/analysis_results.tsv"
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
    ap.add_argument("--results-dir", required=True,
                    help="Path to the results tree to scan (e.g. ../04_results, or your real /mnt/e/.../results dir).")
    ap.add_argument("--defaults",
                    help="JSON file with default FK mappings (sample_set_id, site_set_for_chrom, …). "
                         "See 01_registry/scan_defaults.json for the example shape.")
    ap.add_argument("--apply", action="store_true",
                    help="Append valid proposals to analysis_results.tsv. Refuses rows with unresolved FKs.")
    ap.add_argument("--registry-root", help="Override registry root.")
    args = ap.parse_args(argv)

    root = pathlib.Path(args.registry_root) if args.registry_root else find_registry_root()
    results_dir = pathlib.Path(args.results_dir).resolve()
    if not results_dir.is_dir():
        sys.exit(f"results dir not found: {results_dir}")

    defaults_path = pathlib.Path(args.defaults).resolve() if args.defaults else None
    if defaults_path and not defaults_path.exists():
        sys.exit(f"defaults file not found: {defaults_path}")
    defaults = load_defaults(defaults_path)

    print()
    print(f"scanning: {results_dir}")
    if defaults_path: print(f"defaults: {defaults_path}")
    print()

    proposals = scan(results_dir, root, defaults)
    if not proposals:
        print("(no candidate result files found)")
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
        print(f"{OK} appended {n_wrote} row(s) → {root / '01_registry' / 'analysis_results.tsv'}")
    else:
        print()
        print("This was a DRY RUN. Re-run with --apply to actually append the new row(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
