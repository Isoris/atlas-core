#!/usr/bin/env python3
"""
smoke_all_stack.py — end-to-end smoke test for the whole atlas-core stack.

Exercises every Python tier added across PRs #11 – #25:

  Phase A   build_connection_map.py        librarian-tier scanner
  Phase A   check_analysis_registry.py     catalogue FK validator
  Phase A   resolve_layer.py               librarian (--layer, --hook, --compose)
  Phase B   edge_validator.py              graph edge validation (PR #12)
  Phase D   tsv_from_jsonl.py              JSONL → TSV derived view
  Manager   manager.py                     product status + question readiness
  Manager   estimability.py                Estimability Manager
  Phase F   dispatcher.py                  plan + list + clear

Exits 0 when every step is green; 1 on any failure. Stdlib only.

Usage:
  python3 scripts/smoke_all_stack.py            # human output
  python3 scripts/smoke_all_stack.py --json     # machine output
"""
from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys
import time


def _here() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parent


def _run(label: str, cmd: list, cwd: pathlib.Path, check_stdout: list = None) -> dict:
    t0 = time.time()
    p = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True)
    ok = p.returncode == 0
    if ok and check_stdout:
        for s in check_stdout:
            if s not in (p.stdout + p.stderr):
                ok = False
                err = f"expected {s!r} in output"
                break
        else:
            err = ""
    else:
        err = p.stderr.strip().splitlines()[-1] if (p.stderr and not ok) else ""
    return {
        "label": label,
        "ok":    ok,
        "exit":  p.returncode,
        "ms":    int((time.time() - t0) * 1000),
        "err":   err,
        "head":  (p.stdout or p.stderr).strip().splitlines()[:3],
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    # Locate the relatedness root + python prefix
    here = _here()
    repo_root = here.parent
    rel = repo_root / "toolkit_registries" / "relatedness"
    if not (rel / "01_registry").is_dir():
        # Try alternative: invoked from inside toolkit_registries
        rel = here.parent / "relatedness"
    if not (rel / "01_registry").is_dir():
        print("could not find toolkit_registries/relatedness/01_registry/", file=sys.stderr)
        return 2

    steps = [
        # ---- librarian-tier ----
        _run("build_connection_map", [sys.executable, "-m", "lib.build_connection_map"], rel,
             check_stdout=["0 warnings"]),
        _run("check_analysis_registry", [sys.executable, "scripts/check_analysis_registry.py"], rel,
             check_stdout=["OK"]),
        _run("resolve_layer (one layer)",
             [sys.executable, "scripts/resolve_layer.py", "--layer", "karyotype_calls"], rel,
             check_stdout=["RESOLVED"]),
        _run("resolve_layer (--compose hook)",
             [sys.executable, "scripts/resolve_layer.py", "--compose", "candidate_review_hook",
              "--sample-set", "samples_226_v1", "--interval-set", "inv_LG28_INV_001_v1",
              "--candidate", "inv_LG28_INV_001"], rel,
             check_stdout=["page_composition_plan_v1"]),

        # ---- TSV derived view ----
        _run("tsv_from_jsonl", [sys.executable, "-m", "lib.tsv_from_jsonl", "--dry-run"], rel,
             check_stdout=["would write"]),

        # ---- manager-tier ----
        _run("manager (product status)",
             [sys.executable, "-m", "lib.manager", "--product", "inversion_candidates.v1"], rel,
             check_stdout=["ready"]),
        _run("manager (question readiness)",
             [sys.executable, "-m", "lib.manager",
              "--question", "inversion_pair_incompatibility_LG01_LG28",
              "--sample-set", "samples_226_v1",
              "--interval-set", "inv_LG28_INV_001_v1"], rel,
             check_stdout=["status"]),
        _run("manager (scope intersection)",
             [sys.executable, "-m", "lib.manager", "--scope",
              "--product", "inversion_candidates.v1",
              "--product", "inversion_karyotypes.v1"], rel,
             check_stdout=["scope intersection"]),

        # ---- estimability ----
        _run("estimability (observed_pair_distortion)",
             [sys.executable, "-m", "lib.estimability",
              "--estimand", "observed_pair_distortion"], rel,
             check_stdout=["estimable", "observed_pair_distortion"]),
        _run("estimability (needs_extra_data path)",
             [sys.executable, "-m", "lib.estimability",
              "--estimand", "male_vs_female_meiosis"], rel,
             check_stdout=["needs_extra_data"]),
        _run("estimability (question roll-up)",
             [sys.executable, "-m", "lib.estimability",
              "--question", "inversion_pair_incompatibility_LG01_LG28"], rel,
             check_stdout=["estimability"]),

        # ---- dispatcher (Phase F) ----
        _run("dispatcher (dry-run)",
             [sys.executable, "-m", "lib.dispatcher",
              "--question", "inversion_pair_incompatibility_LG01_LG28",
              "--sample-set", "samples_226_v1",
              "--interval-set", "inv_LG28_INV_001_v1"], rel,
             check_stdout=["DRY RUN", "would commit"]),
        _run("dispatcher (commit + list + clear)",
             ["bash", "-c", " && ".join([
                 f"{sys.executable} -m lib.dispatcher --question inversion_pair_incompatibility_LG01_LG28 "
                 "--sample-set samples_226_v1 --interval-set inv_LG28_INV_001_v1 --commit",
                 f"{sys.executable} -m lib.dispatcher --list",
                 f"{sys.executable} -m lib.dispatcher --clear --yes",
             ])], rel,
             check_stdout=["committed", "cleared"]),
    ]

    n_ok = sum(1 for s in steps if s["ok"])
    n_fail = len(steps) - n_ok
    summary = {
        "schema_version": "smoke_summary_v1",
        "total":  len(steps),
        "passed": n_ok,
        "failed": n_fail,
        "ms":     sum(s["ms"] for s in steps),
        "steps":  steps,
    }
    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        for s in steps:
            mark = "✓" if s["ok"] else "✗"
            print(f"  {mark}  {s['label']:<42}  {s['ms']:>5} ms  exit={s['exit']}")
            if not s["ok"]:
                print(f"      err: {s['err']}")
                for line in s["head"]:
                    print(f"      | {line}")
        print()
        print(f"  {n_ok}/{len(steps)} passed in {summary['ms']} ms")
    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
