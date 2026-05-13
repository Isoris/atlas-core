#!/usr/bin/env python3
"""
Mode-driven contract resolver. Turns a vague request into a concrete contract.

Usage:
    resolve.py --analysis ngsrelate --mode genome_wide \\
               --sample-set samples_226_v1

    resolve.py --analysis ngsrelate --mode per_chromosome \\
               --sample-set samples_226_v1 --chromosome C_gar_LG12

    resolve.py --analysis ngspedigree --mode global \\
               --ngsrelate-result ngsrelate_global_v1

    resolve.py --analysis mendelian --mode per_candidate \\
               --candidate-id LG12_INV_001 --pedigree-result ngspedigree_global_v1

The resolver walks 01_registry/analysis_modes.tsv to find the row matching
(analysis_type, mode), then:
  1. Verifies the user supplied every required_dimension.
  2. Applies the policies (interval_policy, site_policy, group_policy,
     value_policy) to fill the rest from the six registries.
  3. Checks the resolved (sample_set, site_set, interval_set, input_value)
     contract is internally consistent.
  4. Prints the FULL CONTRACT — what would land in analysis_results.tsv if
     you ran the analysis.
  5. Exits 0 (resolved cleanly), 1 (missing/ambiguous), 2 (bad inputs).

Options:
    --emit-register-cmd   print the matching register_result.py command line
    --explain             show why each policy picked what it picked
    --registry-root PATH

The resolver is deterministic. If a policy has multiple valid candidates,
it FAILS with status=ambiguous and lists the options — no silent guessing.
"""

from __future__ import annotations

import argparse
import pathlib
import sys
from typing import Dict, List, Optional, Tuple

from io_helpers import find_registry_root, load_all, read_tsv, OK, FAIL, WARN


# --------------------------------------------------------------------------- #
# Policy resolvers — one per known policy tag                                  #
# --------------------------------------------------------------------------- #
#
# Each returns (chosen_id_or_None, candidates_list, why_string).
# When chosen is None, candidates lists what was matched (0, 2+, or "ambiguous").
# When chosen is set, candidates is [chosen] and why explains the choice.


def _interval_policy(tag: str, regs: Dict, args, sample_set_id: str = "") -> Tuple[Optional[str], List[str], str]:
    rows = list(regs["interval_sets"].values())
    if tag == "genome_all":
        cands = [r for r in rows if r.get("interval_type") == "genome"]
        if len(cands) == 1: return (cands[0]["interval_set_id"], [c["interval_set_id"] for c in cands], "interval_type=genome")
        return (None, [c["interval_set_id"] for c in cands], "interval_type=genome (need exactly 1)")
    if tag == "chromosome_full":
        if not args.chromosome:
            return (None, [], "need --chromosome")
        cands = [r for r in rows if r.get("interval_type") == "chromosome"
                 and args.chromosome in r.get("interval_set_id", "")]
        # Fallback: scan the file path for the chrom literal
        if not cands:
            cands = [r for r in rows if r.get("interval_type") == "chromosome"
                     and args.chromosome in r.get("path", "")]
        if len(cands) == 1: return (cands[0]["interval_set_id"], [c["interval_set_id"] for c in cands], f"interval_type=chromosome containing '{args.chromosome}'")
        return (None, [c["interval_set_id"] for c in cands], f"interval_type=chromosome matching '{args.chromosome}'")
    if tag == "candidate_interval":
        if not args.candidate_id:
            return (None, [], "need --candidate-id")
        cands = [r for r in rows if r.get("interval_type") == "candidate"
                 and args.candidate_id in r.get("interval_set_id", "")]
        if len(cands) == 1: return (cands[0]["interval_set_id"], [c["interval_set_id"] for c in cands], f"interval_type=candidate matching '{args.candidate_id}'")
        return (None, [c["interval_set_id"] for c in cands], f"interval_type=candidate matching '{args.candidate_id}'")
    return (None, [], f"unknown interval_policy '{tag}'")


def _site_policy(tag: str, regs: Dict, args, interval_set_id: str = "") -> Tuple[Optional[str], List[str], str]:
    rows = list(regs["site_sets"].values())
    if tag == "thin500_global":
        cands = [r for r in rows if "thin500" in r.get("site_set_id", "")
                 and "global" in r.get("site_set_id", "")]
        if len(cands) == 1: return (cands[0]["site_set_id"], [c["site_set_id"] for c in cands], "site_set name contains 'thin500' and 'global'")
        return (None, [c["site_set_id"] for c in cands], "site name contains thin500+global (need exactly 1)")
    if tag == "thin500_per_chr":
        cands = [r for r in rows if "thin500" in r.get("site_set_id", "")
                 and r.get("interval_set_id") == interval_set_id]
        if len(cands) == 1: return (cands[0]["site_set_id"], [c["site_set_id"] for c in cands], f"thin500 site_set with interval_set_id={interval_set_id}")
        return (None, [c["site_set_id"] for c in cands], f"thin500 + interval_set_id={interval_set_id}")
    if tag == "candidate_sites":
        cands = [r for r in rows if r.get("interval_set_id") == interval_set_id
                 and r.get("operation") == "intersect"]
        if len(cands) == 1: return (cands[0]["site_set_id"], [c["site_set_id"] for c in cands], f"site_set with interval_set_id={interval_set_id} and operation=intersect")
        return (None, [c["site_set_id"] for c in cands], f"intersect site_set on interval={interval_set_id}")
    if tag == "karyotype_calls":
        # Future: a special site_set type for karyotype-defining variants
        return (None, [], "karyotype_calls policy not implemented yet (no example data)")
    return (None, [], f"unknown site_policy '{tag}'")


def _group_policy(tag: str, regs: Dict, args, sample_set_id: str = "") -> Tuple[Optional[str], List[str], str]:
    rows = list(regs["group_sets"].values())
    relevant = [r for r in rows if r.get("sample_set_id") == sample_set_id]
    if tag == "family_population":
        cands = [r for r in relevant
                 if "family" in r.get("group_columns", "") and "population" in r.get("group_columns", "")]
        if len(cands) == 1: return (cands[0]["group_set_id"], [c["group_set_id"] for c in cands], "group_columns contain 'family' and 'population'")
        return (None, [c["group_set_id"] for c in cands], "family+population (need exactly 1)")
    if tag == "family_karyotype":
        cands = [r for r in relevant
                 if "family" in r.get("group_columns", "") and "karyotype" in r.get("group_columns", "")]
        if not cands and relevant:
            # Fall back to family_population if no karyotype groups exist yet
            return (None, [], "no group_set with family+karyotype columns; consider --group-set explicitly")
        if len(cands) == 1: return (cands[0]["group_set_id"], [c["group_set_id"] for c in cands], "group_columns contain 'family' and 'karyotype'")
        return (None, [c["group_set_id"] for c in cands], "family+karyotype (need exactly 1)")
    if tag == "optional_groups":
        return ("", [], "groups optional; leaving empty")
    return (None, [], f"unknown group_policy '{tag}'")


def _value_policy(tag: str, regs: Dict, sample_set_id: str, site_set_id: str, interval_set_id: str) -> Tuple[Optional[str], List[str], str]:
    if tag == "none":
        return ("", [], "this analysis consumes an upstream result, not a value file")
    if tag == "beagle_matching":
        rows = list(regs["input_values"].values())
        cands = [r for r in rows
                 if r.get("value_type", "").startswith("BEAGLE")
                 and r.get("sample_set_id") == sample_set_id
                 and r.get("site_set_id") == site_set_id
                 and (not interval_set_id or r.get("interval_set_id") == interval_set_id)]
        if len(cands) == 1: return (cands[0]["value_id"], [c["value_id"] for c in cands], f"BEAGLE matching ({sample_set_id}, {site_set_id}, {interval_set_id})")
        return (None, [c["value_id"] for c in cands], f"BEAGLE matching ({sample_set_id}, {site_set_id}, {interval_set_id})")
    return (None, [], f"unknown value_policy '{tag}'")


# --------------------------------------------------------------------------- #
# Mode resolution                                                              #
# --------------------------------------------------------------------------- #

REGISTERED_POLICIES = {
    "interval": _interval_policy,
    "site":     _site_policy,
    "group":    _group_policy,
    "value":    _value_policy,
}


def load_modes(registry_root: pathlib.Path) -> List[Dict]:
    return read_tsv(registry_root / "01_registry" / "analysis_modes.tsv")


def find_mode(modes: List[Dict], analysis: str, mode: str) -> Optional[Dict]:
    for m in modes:
        if m.get("analysis_type") == analysis and m.get("mode") == mode:
            return m
    return None


def resolve(args) -> Dict:
    """Return a dict { status, contract, missing, ambiguities, log } describing
    the resolution outcome.

    status: 'ok' | 'missing' | 'ambiguous' | 'invalid'
    """
    root = pathlib.Path(args.registry_root) if args.registry_root else find_registry_root()
    regs = load_all(root)
    modes = load_modes(root)

    m = find_mode(modes, args.analysis, args.mode)
    if not m:
        all_modes = sorted({(x.get('analysis_type'), x.get('mode')) for x in modes})
        return {"status": "invalid", "log": [],
                "missing": [f"no mode '{args.analysis}/{args.mode}' in analysis_modes.tsv"],
                "available": [f"{a}/{md}" for a, md in all_modes if a == args.analysis] or
                             [f"{a}/{md}" for a, md in all_modes]}

    log = [f"mode: {m['analysis_type']}/{m['mode']}  ({m.get('label', '')})"]
    contract = {
        "analysis_type": m["analysis_type"],
        "mode":          m["mode"],
        "produces":      m.get("produces", ""),
    }
    missing = []
    ambiguities = []

    # 1. Required dimensions check
    required = [d.strip() for d in (m.get("required_dimensions") or "").split(",") if d.strip()]
    have = {
        "sample_set":       args.sample_set,
        "chromosome":       args.chromosome,
        "candidate_id":     args.candidate_id,
        "ngsrelate_result": args.ngsrelate_result,
        "pedigree_result":  args.pedigree_result,
        "candidate_set":    args.candidate_set,
        "group_set":        args.group_set,
    }
    for dim in required:
        if not have.get(dim):
            missing.append(f"required dimension '{dim}' not provided (use --{dim.replace('_', '-')})")
    if missing:
        return {"status": "missing", "contract": contract, "missing": missing,
                "ambiguities": [], "log": log}

    # 2. Inheritance from upstream result (when policy is "same_as_input")
    inherited = {}
    upstream_id = args.ngsrelate_result or args.pedigree_result
    if upstream_id:
        upstream = regs["analysis_results"].get(upstream_id)
        if not upstream:
            return {"status": "invalid", "contract": contract,
                    "missing": [f"upstream result '{upstream_id}' not in analysis_results.tsv"],
                    "ambiguities": [], "log": log}
        inherited = {
            "sample_set_id":   upstream.get("sample_set_id"),
            "group_set_id":    upstream.get("group_set_id"),
            "interval_set_id": upstream.get("interval_set_id"),
            "site_set_id":     upstream.get("site_set_id"),
        }
        contract["input_result_id"] = upstream_id
        log.append(f"inherits from upstream {upstream_id}: "
                   f"sample={inherited['sample_set_id']}, interval={inherited['interval_set_id']}")

    sample_set_id = args.sample_set or inherited.get("sample_set_id") or ""
    contract["sample_set_id"] = sample_set_id

    # 3. interval_policy
    ip = m.get("interval_policy") or ""
    if ip == "same_as_input" and inherited.get("interval_set_id"):
        contract["interval_set_id"] = inherited["interval_set_id"]
        log.append(f"interval (inherited): {contract['interval_set_id']}")
    elif ip:
        chosen, cands, why = _interval_policy(ip, regs, args, sample_set_id)
        log.append(f"interval_policy='{ip}': {why} → {chosen or '(no unique match)'}")
        if chosen:
            contract["interval_set_id"] = chosen
        else:
            (ambiguities if cands else missing).append(
                f"interval_policy='{ip}': {why}" + (f" — candidates: {cands}" if cands else "")
            )

    interval_set_id = contract.get("interval_set_id", "")

    # 4. site_policy
    sp = m.get("site_policy") or ""
    if sp == "same_as_input" and inherited.get("site_set_id"):
        contract["site_set_id"] = inherited["site_set_id"]
        log.append(f"site (inherited): {contract['site_set_id']}")
    elif sp:
        chosen, cands, why = _site_policy(sp, regs, args, interval_set_id)
        log.append(f"site_policy='{sp}': {why} → {chosen or '(no unique match)'}")
        if chosen:
            contract["site_set_id"] = chosen
        else:
            (ambiguities if cands else missing).append(
                f"site_policy='{sp}': {why}" + (f" — candidates: {cands}" if cands else "")
            )

    site_set_id = contract.get("site_set_id", "")

    # 5. group_policy
    gp = m.get("group_policy") or ""
    if args.group_set:
        contract["group_set_id"] = args.group_set
        log.append(f"group (explicit): {args.group_set}")
    elif gp == "same_as_input" and inherited.get("group_set_id"):
        contract["group_set_id"] = inherited["group_set_id"]
        log.append(f"group (inherited): {contract['group_set_id']}")
    elif gp:
        chosen, cands, why = _group_policy(gp, regs, args, sample_set_id)
        log.append(f"group_policy='{gp}': {why} → {chosen or '(no unique match)'}")
        if chosen is None:
            (ambiguities if cands else missing).append(
                f"group_policy='{gp}': {why}" + (f" — candidates: {cands}" if cands else "")
            )
        else:
            contract["group_set_id"] = chosen

    # 6. value_policy
    vp = m.get("value_policy") or ""
    if vp:
        chosen, cands, why = _value_policy(vp, regs, sample_set_id, site_set_id, interval_set_id)
        log.append(f"value_policy='{vp}': {why} → {chosen or '(no unique match)' if vp != 'none' else '(none)'}")
        if chosen is None:
            (ambiguities if cands else missing).append(
                f"value_policy='{vp}': {why}" + (f" — candidates: {cands}" if cands else "")
            )
        else:
            contract["input_value_id"] = chosen

    # Status
    if missing:
        return {"status": "missing", "contract": contract, "missing": missing,
                "ambiguities": ambiguities, "log": log}
    if ambiguities:
        return {"status": "ambiguous", "contract": contract, "missing": [],
                "ambiguities": ambiguities, "log": log}
    return {"status": "ok", "contract": contract, "missing": [],
            "ambiguities": [], "log": log}


# --------------------------------------------------------------------------- #
# Pretty printer                                                               #
# --------------------------------------------------------------------------- #

CONTRACT_FIELDS = [
    "analysis_type", "mode",
    "sample_set_id", "group_set_id", "interval_set_id", "site_set_id",
    "input_value_id", "input_result_id",
    "produces",
]


def print_outcome(out: Dict, args) -> None:
    print()
    if args.explain:
        print("=== resolution log ===")
        for line in out.get("log", []):
            print(f"  {line}")
        print()

    print("=== contract ===")
    contract = out.get("contract", {})
    for f in CONTRACT_FIELDS:
        v = contract.get(f, "")
        print(f"  {f:<18}  {v if v else '(empty)'}")
    print()

    status = out["status"]
    if status == "ok":
        print(f"STATUS: {OK}  ready to run")
    elif status == "missing":
        print(f"STATUS: {FAIL}  missing inputs:")
        for m in out["missing"]:
            print(f"  • {m}")
    elif status == "ambiguous":
        print(f"STATUS: {WARN}  ambiguous policy match — pick one explicitly:")
        for a in out["ambiguities"]:
            print(f"  • {a}")
    elif status == "invalid":
        print(f"STATUS: {FAIL}  invalid request:")
        for m in out["missing"]:
            print(f"  • {m}")
        if out.get("available"):
            print(f"  available modes: {', '.join(out['available'])}")
    print()

    if args.emit_register_cmd and status == "ok":
        c = contract
        print("=== suggested register_result.py invocation ===")
        cmd = ["python3", "register_result.py",
               "--result-id",        f"<your_new_id>",
               "--analysis-type",    c.get("analysis_type", ""),
               "--path",             "<path/to/the/output/file>",
               "--sample-set-id",    c.get("sample_set_id", "")]
        for k, flag in [("group_set_id", "--group-set-id"),
                        ("interval_set_id", "--interval-set-id"),
                        ("site_set_id", "--site-set-id"),
                        ("input_value_id", "--input-value-id"),
                        ("input_result_id", "--input-result-id")]:
            v = c.get(k)
            if v:
                cmd.extend([flag, v])
        cmd.extend(["--method-id", f"{c.get('analysis_type', '')}_v?"])
        print("  " + " \\\n    ".join(cmd))
        print()


# --------------------------------------------------------------------------- #
# CLI                                                                          #
# --------------------------------------------------------------------------- #

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--analysis",  required=True)
    ap.add_argument("--mode",      required=True)
    ap.add_argument("--sample-set",       default="", help="sample_set_id (required by most modes)")
    ap.add_argument("--chromosome",       default="", help="chrom name, e.g. C_gar_LG12 (required by per_chromosome modes)")
    ap.add_argument("--candidate-id",     default="", help="candidate id (required by per_candidate modes)")
    ap.add_argument("--candidate-set",    default="", help="candidate_set_id (when applicable)")
    ap.add_argument("--ngsrelate-result", default="", help="upstream relatedness_res result_id (for ngspedigree)")
    ap.add_argument("--pedigree-result",  default="", help="upstream pedigree_result result_id (for mendelian)")
    ap.add_argument("--group-set",        default="", help="explicit group_set_id (overrides group_policy)")
    ap.add_argument("--explain",          action="store_true", help="show the policy decisions step by step")
    ap.add_argument("--emit-register-cmd", action="store_true", help="print a register_result.py invocation skeleton")
    ap.add_argument("--registry-root",    help="override registry root")
    args = ap.parse_args(argv)

    out = resolve(args)
    print_outcome(out, args)

    return {"ok": 0, "missing": 1, "ambiguous": 1, "invalid": 2}[out["status"]]


if __name__ == "__main__":
    raise SystemExit(main())
