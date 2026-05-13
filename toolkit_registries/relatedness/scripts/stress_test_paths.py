#!/usr/bin/env python3
"""
Stress test for the two manuscript paths.

  Path A — relatedness chain
      candidate inversion + karyotype groups
          → ngsRelate (per_candidate)
          → ngsPedigree (global, inherits from ngsRelate)
          → mendelian (per_candidate, consumes pedigree)

  Path B — popstats chain
      candidate inversion + karyotype groups
          → popstats (per_candidate; FST / dxy / piN / piS)

For each step the test:
  1. Asks resolve.py to pick the contract (interval / site / value /
     group from the policies in analysis_modes.tsv).
  2. Reports STATUS: ✓ ready to run / ⚠ ambiguous / ✗ missing.
  3. (Optional, with --dispatch) actually runs the runner via
     dispatcher.dispatch_action and registers the result.

Usage:
    stress_test_paths.py                        # dry walk-through only
    stress_test_paths.py --dispatch             # also run the stub runners
    stress_test_paths.py --candidate-id LG28_INV_001 --sample-set samples_226_v1

Exit code: 0 if both paths walked cleanly, 1 otherwise.
"""

from __future__ import annotations

import argparse
import pathlib
import sys
from typing import Any, Dict, List, Tuple

_HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

import resolve as resolver                                        # noqa: E402
from io_helpers import find_registry_root, load_all, OK, FAIL, WARN  # noqa: E402


PATH_A = [
    ("ngsrelate",   "per_candidate"),
    ("ngspedigree", "global"),
    ("mendelian",   "per_candidate"),
]

PATH_B = [
    ("popstats",    "per_candidate"),
]


def _make_args(analysis: str, mode: str,
               sample_set: str,
               chromosome: str,
               candidate_id: str,
               group_set: str = "",
               ngsrelate_result: str = "",
               pedigree_result: str = ""):
    """Build the argparse.Namespace that resolve.resolve() expects."""
    ap = argparse.Namespace()
    ap.analysis         = analysis
    ap.mode             = mode
    ap.sample_set       = sample_set
    ap.chromosome       = chromosome
    ap.candidate_id     = candidate_id
    ap.candidate_set    = ""
    ap.ngsrelate_result = ngsrelate_result
    ap.pedigree_result  = pedigree_result
    ap.group_set        = group_set
    ap.explain          = False
    ap.emit_register_cmd= False
    ap.registry_root    = None
    return ap


def _walk_path(path_name: str,
               steps: List[Tuple[str, str]],
               base_args: Dict[str, str],
               dispatch: bool) -> bool:
    print(f"\n══ Path {path_name} ══════════════════════════════════════════════")
    print(f"   target: candidate={base_args['candidate_id']}  samples={base_args['sample_set']}")
    print()

    all_ok = True
    last_result_id_per_produces = {}  # produces tag → result_id (for upstream chaining)

    for i, (analysis, mode) in enumerate(steps, start=1):
        print(f"── step {i}/{len(steps)} : {analysis} / {mode} ─────────────")

        # Fold in upstream result ids if this step's mode requires them.
        upstream_ngs = last_result_id_per_produces.get("relatedness_res", "")
        upstream_ped = last_result_id_per_produces.get("pedigree_result", "")

        args = _make_args(
            analysis         = analysis,
            mode             = mode,
            sample_set       = base_args["sample_set"],
            chromosome       = base_args["chromosome"],
            candidate_id     = base_args["candidate_id"],
            group_set        = base_args.get("group_set", ""),
            ngsrelate_result = upstream_ngs,
            pedigree_result  = upstream_ped,
        )

        out = resolver.resolve(args)
        contract = out["contract"]

        for k in ("sample_set_id", "group_set_id", "interval_set_id",
                  "site_set_id", "input_value_id", "input_result_id", "produces"):
            v = contract.get(k, "")
            if v:
                print(f"      {k:<18} {v}")

        status = out["status"]
        if status == "ok":
            print(f"      → STATUS: {OK} ready to run")
        elif status == "missing":
            print(f"      → STATUS: {FAIL} missing inputs:")
            for m in out["missing"]:
                print(f"          • {m}")
            all_ok = False
        elif status == "ambiguous":
            print(f"      → STATUS: {WARN} ambiguous policy match:")
            for a in out["ambiguities"]:
                print(f"          • {a}")
            all_ok = False
        else:
            print(f"      → STATUS: {FAIL} {status}: {out.get('missing') or ''}")
            all_ok = False

        # Cache check: does a result already exist for this contract?
        regs = load_all(find_registry_root())
        existing = None
        for r in regs["analysis_results"].values():
            if (r.get("analysis_type") == analysis
                and r.get("sample_set_id")  == contract.get("sample_set_id", "")
                and r.get("interval_set_id")== contract.get("interval_set_id", "")
                and r.get("site_set_id")    == contract.get("site_set_id", "")):
                existing = r
                break
        if existing:
            print(f"      → CACHE: ✓ existing result_id = {existing['result_id']}")
            print(f"               (skip the runner; reuse this row)")
            # Pretend this is what would be passed downstream.
            produces = contract.get("produces") or ""
            if produces:
                last_result_id_per_produces[produces] = existing["result_id"]
        else:
            print(f"      → CACHE: no existing result — would run runner")
            if dispatch and status == "ok":
                print(f"      → DISPATCHING via dispatcher.dispatch_action …")
                sys.path.insert(0, str(_HERE.parent))
                import dispatcher as disp  # noqa: E402
                manifest = {
                    "action_id":  f"act_stress_{i}",
                    "type":       f"run_{analysis}",
                    "dataset_id": base_args["sample_set"],
                    "runner":     f"scripts.runners.run_{analysis}",
                    "target":     {
                        "sample_set_id":   contract.get("sample_set_id", ""),
                        "group_set_id":    contract.get("group_set_id", ""),
                        "interval_set_id": contract.get("interval_set_id", ""),
                        "site_set_id":     contract.get("site_set_id", ""),
                        "input_value_id":  contract.get("input_value_id", ""),
                        "input_result_id": contract.get("input_result_id", ""),
                        "candidate_id":    base_args["candidate_id"],
                        "chromosome":      base_args["chromosome"],
                    },
                }
                result = disp.dispatch_action(manifest, {"workspace_root": str(find_registry_root())})
                produced = result.get("produced_layers", [])
                print(f"               produced: {produced}")
                if produced:
                    produces = contract.get("produces") or ""
                    if produces:
                        last_result_id_per_produces[produces] = produced[0]
        print()
    return all_ok


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sample-set",   default="samples_226_v1")
    ap.add_argument("--chromosome",   default="C_gar_LG28")
    ap.add_argument("--candidate-id", default="inv_LG28_INV_001")
    ap.add_argument("--group-set",    default="",
                    help="Override group_set_id (default: resolved by family_karyotype policy)")
    ap.add_argument("--dispatch",     action="store_true",
                    help="Actually run the stub runner for each MISSING step")
    args = ap.parse_args(argv)

    base = {
        "sample_set":   args.sample_set,
        "chromosome":   args.chromosome,
        "candidate_id": args.candidate_id,
        "group_set":    args.group_set,
    }
    ok_a = _walk_path("A — relatedness chain", PATH_A, base, args.dispatch)
    ok_b = _walk_path("B — popstats chain",    PATH_B, base, args.dispatch)

    print("\n══ verdict ════════════════════════════════════════════════════")
    print(f"   Path A : {'✓ OK end-to-end' if ok_a else '✗ at least one step needs attention'}")
    print(f"   Path B : {'✓ OK end-to-end' if ok_b else '✗ at least one step needs attention'}")
    print()
    return 0 if (ok_a and ok_b) else 1


if __name__ == "__main__":
    raise SystemExit(main())
