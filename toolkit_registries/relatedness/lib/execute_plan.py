#!/usr/bin/env python3
"""
execute_plan.py — translate an accepted panel_plan_v1 into action_manifest_v1
                   entries the dispatcher can queue.

The bridge between page 14 (Plans, panel_plan_v1) and page 11 (Queue,
action_manifest_v1). DYNAMIC_PANELS_SPEC §27.4 declares the lifecycle:

  generate → review → (edit | accept | dismiss) → execute

This script is the EXECUTE step. It reads a panel_plan_v1, walks
step.actions[] where:
  - action.kind == "dispatch"
  - action.enabled  is True
  - all gates_status[*].passes is True
…and emits one action_manifest_v1 per qualifying action into
02_queue/<action_id>.json.

The dispatcher's existing index rewriter then picks the new manifests
up on its next refresh.

§refusals (mirrors lib/dispatcher.py):
  - No execution. We write manifests; an external runner runs them.
  - No registry write-back. Only 02_queue/ is touched.
  - No producer minting. action.action_id is generated; the plan
    must have already specified analysis_id via from_analysis.

Usage:
  python3 -m lib.execute_plan --plan plan_auto_bp4_population_overlap [--commit]
  python3 -m lib.execute_plan --all                           # all plans that meet the gate
  python3 -m lib.execute_plan --all --commit
"""
from __future__ import annotations
import argparse
import json
import pathlib
import sys
import time
import secrets
import string

REPO = pathlib.Path(__file__).resolve().parents[3]
REG  = REPO / "toolkit_registries" / "relatedness" / "01_registry"
PQ   = REPO / "toolkit_registries" / "relatedness" / "02_queue"


def load_jsonl(p: pathlib.Path) -> list[dict]:
    if not p.exists(): return []
    return [json.loads(l) for l in p.read_text().splitlines() if l.strip()]


def short_token(n: int = 3) -> str:
    return "".join(secrets.choice(string.ascii_lowercase) for _ in range(n))


def action_id_for(analysis_id: str) -> str:
    ms = int(time.time() * 1000)
    return f"act_{ms}_{analysis_id[:12]}_{short_token()}"


def manifest_for_step(plan: dict, step: dict, action: dict, registry: dict) -> dict | None:
    aid = step.get("from_analysis")
    if not aid: return None
    reg = registry.get(aid)
    if not reg: return None

    expected_layers = []
    for L in (reg.get("produces", "") or "").split(","):
        L = L.strip()
        if L: expected_layers.append({
            "layer_type":     L,
            "schema_version": f"{L}_v1",
            "stage":          "normalized",
        })

    return {
        "schema_version":   "action_manifest_v1",
        "action_id":        action_id_for(aid),
        "type":             f"run_{aid}",
        "dataset_id":       plan.get("scope_required", {}).get("sample_set", "") or "samples_226_v1",
        "runner":           reg.get("default_runner", "") or f"analysis.{aid}.adapter_atlas",
        "target": {
            "sample_set":   plan.get("scope_required", {}).get("sample_set", "") or "",
            "interval_set": plan.get("scope_required", {}).get("interval_set", "") or "",
            "candidate_id": plan.get("scope_required", {}).get("candidate_id", "") or "",
        },
        "params": {},
        "expected_outputs": expected_layers,
        "submitted_by":     "lib.execute_plan",
        "submitted_at":     time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "notes":            f"proposed by execute_plan from plan {plan.get('plan_id')!r} step.phase={step.get('phase')}",
        "_plan": {
            "plan_id":      plan.get("plan_id"),
            "phase":        step.get("phase"),
            "panel_id":     step.get("panel_id"),
            "action_id":    action.get("action_id"),
            "from_analysis": aid,
        },
    }


def step_action_eligible(step: dict, action: dict) -> tuple[bool, str]:
    if action.get("kind") != "dispatch":         return False, "kind != dispatch"
    if not action.get("enabled", False):          return False, "action.enabled = False"
    # action gates must all pass
    for g in (action.get("gates_status") or []):
        if not g.get("passes", False):
            return False, f"gate {g.get('graph')}:{g.get('node')} fails"
    # step gates must all pass too
    for g in (step.get("gates_status") or []):
        if not g.get("passes", False):
            return False, f"step gate {g.get('graph')}:{g.get('node')} fails"
    return True, "ok"


def collect_eligible(plan: dict, registry: dict) -> list[tuple[dict, dict, dict]]:
    out = []
    for step in plan.get("steps", []):
        for action in (step.get("actions") or []):
            ok, _why = step_action_eligible(step, action)
            if not ok: continue
            m = manifest_for_step(plan, step, action, registry)
            if m: out.append((step, action, m))
    return out


def execute_one(plan_path: pathlib.Path, registry: dict, commit: bool) -> tuple[int, list[str]]:
    plan = json.loads(plan_path.read_text())
    eligible = collect_eligible(plan, registry)
    written: list[str] = []
    for _step, _action, manifest in eligible:
        if commit:
            out = PQ / f"{manifest['action_id']}.json"
            out.write_text(json.dumps(manifest, indent=2) + "\n")
            written.append(out.name)
        else:
            written.append(manifest["action_id"])
    return len(eligible), written


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan",  default="", help="Plan filename under 02_queue/plans/ (e.g. plan_auto_bp4_population_overlap.json).")
    ap.add_argument("--all",   action="store_true", help="Walk every plan_*.json in 02_queue/plans/.")
    ap.add_argument("--commit", action="store_true", help="Write the manifests to 02_queue/. Without it, dry-run.")
    args = ap.parse_args(argv)

    plans_dir = PQ / "plans"
    if not plans_dir.exists():
        print("no 02_queue/plans/ — nothing to execute")
        return 0

    registry = {r["analysis_id"]: r for r in load_jsonl(REG / "analysis_registry.jsonl")}

    targets: list[pathlib.Path] = []
    if args.all:
        targets = sorted(plans_dir.glob("plan_*.json"))
    elif args.plan:
        p = plans_dir / args.plan
        if not p.exists():
            print(f"plan file not found: {p}"); return 1
        targets = [p]
    else:
        ap.print_help(); return 1

    total = 0
    for p in targets:
        n, names = execute_one(p, registry, args.commit)
        total += n
        if not n: continue
        verb = "would write" if not args.commit else "wrote"
        print(f"  {p.name}:  {verb} {n} manifest(s)")
        for name in names:
            print(f"    • {name}")
    if args.commit and total:
        # rebuild dispatcher index so page 11 picks the new manifests up
        try:
            from toolkit_registries.relatedness.lib.dispatcher import Dispatcher  # type: ignore
            Dispatcher(toolkit_root=REPO / "toolkit_registries" / "relatedness")._rewrite_index()
        except Exception as e:
            print(f"  WARN: could not rewrite dispatcher index: {e}", file=sys.stderr)
    if not args.commit:
        print(f"--- dry-run; would write {total} manifest(s) total. Re-run with --commit to write.")
    else:
        print(f"--- committed {total} manifest(s). Page 11 Queue will pick them up on next refresh.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
