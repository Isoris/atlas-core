#!/usr/bin/env python3
"""
readiness_planner.py — given a set of requested pages / packages, walk
the connection map backwards and emit a readiness plan.

Per ADAPTER_CONTRACT.md §7. The planner answers: "if the user wants
these pages / packages rendered, what layers need to exist, what
analyses would produce the missing layers, and what's COMPLETE /
READY_TO_RUN / BLOCKED today?"

Stdlib only. Does NOT run any analysis.

Usage:
  python3 -m lib.readiness_planner --page candidate_review
  python3 -m lib.readiness_planner --package discovery_karyotype_package \
        --sample-set samples_226_v1 --interval-set inv_LG28_INV_001_v1
  python3 -m lib.readiness_planner --page candidate_review --page-id mendelian \
        --json
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Dict, List, Optional, Set


# --------------------------------------------------------------------------- #
def _find_root(start: pathlib.Path) -> pathlib.Path:
    p = start.resolve()
    for cand in [p, *p.parents]:
        if (cand / "01_registry").is_dir():
            return cand
    raise SystemExit("could not find 01_registry/ above " + str(start))


def _read_jsonl(path: pathlib.Path) -> List[Dict]:
    if not path.is_file(): return []
    rows = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _read_json(path: pathlib.Path) -> Optional[Dict]:
    if not path.is_file(): return None
    return json.loads(path.read_text(encoding="utf-8"))


def _csv(s) -> List[str]:
    if isinstance(s, list): return [x for x in s if x]
    return [x.strip() for x in (s or "").split(",") if x.strip()]


# --------------------------------------------------------------------------- #
class ReadinessPlanner:
    """Reads the connection map + registries + results; emits a plan."""

    def __init__(self, registry_root: pathlib.Path):
        self.root = registry_root
        reg = registry_root / "01_registry"
        self.layers    = {l["layer_id"]:    l for l in _read_jsonl(reg / "layer_registry.jsonl")}
        self.hooks     = {h["hook_id"]:     h for h in _read_jsonl(reg / "hook_registry.jsonl")}
        self.analyses  = {a["analysis_id"]: a for a in _read_jsonl(reg / "analysis_registry.jsonl")}
        self.panels    = {p["panel_id"]:    p for p in _read_jsonl(reg / "panels.jsonl")}
        self.pages     = {p["page_id"]:     p for p in _read_jsonl(reg / "pages.jsonl")}
        self.results   = _read_jsonl(reg / "analysis_results.jsonl")
        cm = _read_json(reg / "connection_map.json")
        if cm is None:
            raise SystemExit("connection_map.json not found — run lib.build_connection_map first")
        self.connection_map = cm

    # ---- public entry points ----
    def plan_pages(self, page_ids: List[str], scope: Dict) -> Dict:
        # Expand pages → set of hook_ids
        hook_ids = set()
        for pid in page_ids:
            pg = self.pages.get(pid)
            if not pg:
                continue
            if pg.get("hook_id"):
                hook_ids.add(pg["hook_id"])
        # Collect required + optional layers across all hooks
        return self._plan_for_hooks(hook_ids, scope, label="pages", labels=page_ids)

    def plan_packages(self, package_ids: List[str], scope: Dict) -> Dict:
        # Expand packages → hooks they touch
        cm_packages = {p["package_id"]: p for p in self.connection_map.get("packages", [])}
        hook_ids: Set[str] = set()
        analysis_ids: Set[str] = set()
        for pkid in package_ids:
            pkg = cm_packages.get(pkid)
            if not pkg: continue
            for pg in (pkg.get("pages") or []):
                hook_ids.add(pg["hook_id"])
            for a in (pkg.get("analyses") or []):
                analysis_ids.add(a["analysis_id"])
        plan = self._plan_for_hooks(hook_ids, scope, label="packages", labels=package_ids)
        # Augment with the package's analyses if any are not on a hook chain
        for aid in analysis_ids:
            a = self.analyses.get(aid)
            if not a: continue
            for lid in _csv(a.get("produces")):
                if lid not in plan["per_layer"]:
                    plan["per_layer"][lid] = self._resolve_layer(lid, scope)
                    plan["per_layer"][lid]["reached_via"] = "package_direct"
        plan["scope"] = scope
        return plan

    # ---- core walk ----
    def _plan_for_hooks(self, hook_ids: Set[str], scope: Dict,
                        label: str, labels: List[str]) -> Dict:
        per_layer: Dict[str, Dict] = {}
        per_hook: List[Dict] = []
        for hid in sorted(hook_ids):
            h = self.hooks.get(hid)
            if not h:
                per_hook.append({"hook_id": hid, "state": "UNKNOWN", "reason": "hook not in registry"})
                continue
            reqs = _csv(h.get("requires_layers"))
            opts = _csv(h.get("optional_layers"))
            for lid in reqs + opts:
                if lid not in per_layer:
                    per_layer[lid] = self._resolve_layer(lid, scope)
            req_states = [per_layer[lid]["state"] for lid in reqs]
            opt_states = [per_layer[lid]["state"] for lid in opts]
            hook_state = self._aggregate(req_states)
            per_hook.append({
                "hook_id":      hid,
                "state":        hook_state,
                "required":     reqs,
                "optional":     opts,
                "req_states":   req_states,
                "opt_states":   opt_states,
            })
        # Roll-up
        aggregate = self._aggregate([h.get("state", "UNKNOWN") for h in per_hook])
        ready_actions = []
        for lid, rec in per_layer.items():
            if rec["state"] == "READY_TO_RUN":
                for aid in rec.get("producers", []):
                    ready_actions.append({
                        "action": "run", "analysis_id": aid, "produces": lid,
                        "label":  f"Run {aid} to produce {lid}",
                        "trigger_policy": (self.analyses.get(aid) or {}).get("default_runner") and "manual" or "manual",
                    })
        return {
            "schema_version":  "readiness_plan_v1",
            "request_label":   label,
            "requested":       labels,
            "scope":           scope,
            "aggregate_state": aggregate,
            "per_hook":        per_hook,
            "per_layer":       per_layer,
            "ready_actions":   ready_actions,
        }

    # ---- per-layer resolution (mirrors resolve_layer.py logic) ----
    def _resolve_layer(self, layer_id: str, scope: Dict, seen=None) -> Dict:
        seen = seen or set()
        if layer_id in seen:
            return {"layer_id": layer_id, "state": "BLOCKED_BY_INPUT", "reason": "cycle"}
        seen = seen | {layer_id}
        row = self.layers.get(layer_id)
        if not row:
            return {"layer_id": layer_id, "state": "UNKNOWN_CONTRACT",
                    "reason": "layer not in registry"}
        kind = row.get("source_kind")
        if kind == "file":
            default = (row.get("default_path") or "").strip()
            if default:
                p = (self.root / default).resolve()
                if p.exists():
                    return {"layer_id": layer_id, "state": "RESOLVED",
                            "reason": f"file present at {default}", "default_path": default}
                return {"layer_id": layer_id, "state": "KNOWN_MISSING",
                        "reason": f"default_path missing: {default}", "default_path": default}
            return {"layer_id": layer_id, "state": "KNOWN_MISSING",
                    "reason": "file-kind layer; no default_path and no scope match"}
        if kind == "analysis_result":
            producers = [a["analysis_id"] for a in self.analyses.values()
                         if layer_id in _csv(a.get("produces"))]
            if not producers:
                return {"layer_id": layer_id, "state": "UNKNOWN_CONTRACT",
                        "reason": f"no analysis produces {layer_id!r}", "producers": []}
            # check for an existing result row matching scope
            pset = set(producers)
            for r in self.results:
                if r.get("analysis_type") not in pset: continue
                if scope.get("sample_set")   and r.get("sample_set_id")   != scope["sample_set"]:   continue
                if scope.get("interval_set") and r.get("interval_set_id") != scope["interval_set"]: continue
                if r.get("status") == "active":
                    return {"layer_id": layer_id, "state": "COMPLETE",
                            "reason": f"matching result {r.get('result_id')!r}",
                            "result_id": r.get("result_id"), "producers": producers}
                if r.get("status") == "failed":
                    return {"layer_id": layer_id, "state": "FAILED",
                            "reason": f"result {r.get('result_id')!r} failed",
                            "result_id": r.get("result_id"), "producers": producers}
            # No result. Walk producers' inputs.
            upstream = []
            for aid in producers:
                a = self.analyses.get(aid, {})
                for u in _csv(a.get("input_layer_types")):
                    upstream.append(self._resolve_layer(u, scope, seen))
            ok  = {"RESOLVED", "COMPLETE"}
            bad = {"KNOWN_MISSING", "BLOCKED_BY_INPUT", "UNKNOWN_CONTRACT", "FAILED"}
            if all(u["state"] in ok for u in upstream):
                state = "READY_TO_RUN"
            elif any(u["state"] in bad for u in upstream):
                state = "BLOCKED_BY_INPUT"
            else:
                state = "KNOWN_MISSING"
            return {"layer_id": layer_id, "state": state,
                    "reason": f"no existing result; upstream = {','.join(u['state'] for u in upstream)}",
                    "producers": producers,
                    "missing_inputs": [u["layer_id"] for u in upstream if u["state"] in bad]}
        return {"layer_id": layer_id, "state": "UNKNOWN_CONTRACT",
                "reason": f"source_kind {kind!r} not implemented in planner"}

    @staticmethod
    def _aggregate(states: List[str]) -> str:
        if not states: return "HIDDEN"
        s = set(states)
        if s == {"RESOLVED"} or s == {"COMPLETE"} or s == {"RESOLVED", "COMPLETE"}:
            return "COMPLETE"
        if s == {"READY_TO_RUN"}:
            return "READY_TO_RUN"
        if "FAILED" in s:
            return "FAILED"
        if s <= {"KNOWN_MISSING", "BLOCKED_BY_INPUT", "UNKNOWN_CONTRACT"}:
            return "BLOCKED"
        return "PARTIAL"


# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--page",    action="append", default=[], help="page_id (repeatable)")
    ap.add_argument("--package", action="append", default=[], help="package_id (repeatable)")
    ap.add_argument("--sample-set",   default=None)
    ap.add_argument("--interval-set", default=None)
    ap.add_argument("--candidate",    default=None)
    ap.add_argument("--registry-root", default=None)
    ap.add_argument("--json", action="store_true", help="emit the full plan as JSON")
    args = ap.parse_args()

    if not args.page and not args.package:
        ap.error("at least one --page or --package is required")

    start = pathlib.Path(args.registry_root) if args.registry_root else pathlib.Path(__file__).parent
    root = _find_root(start)
    planner = ReadinessPlanner(root)

    scope = {"sample_set": args.sample_set, "interval_set": args.interval_set, "candidate_id": args.candidate}
    plans = []
    if args.page:    plans.append(planner.plan_pages(args.page, scope))
    if args.package: plans.append(planner.plan_packages(args.package, scope))

    if args.json:
        print(json.dumps(plans if len(plans) > 1 else plans[0], indent=2))
        return 0

    for plan in plans:
        print(f"=== requested {plan['request_label']}: {plan['requested']} ===")
        print(f"aggregate: {plan['aggregate_state']}")
        for h in plan.get("per_hook", []):
            print(f"  hook {h['hook_id']}: {h['state']}  (req={len(h.get('required', []))}, opt={len(h.get('optional', []))})")
        print(f"  layers: {len(plan['per_layer'])}")
        for lid, l in sorted(plan["per_layer"].items()):
            extra = ""
            if l.get("result_id"):       extra = f" (result={l['result_id']})"
            elif l.get("default_path"):  extra = f" (file={l['default_path']})"
            elif l.get("missing_inputs"):extra = f" (missing={','.join(l['missing_inputs'])})"
            print(f"    [{l['state']:>17}] {lid}{extra}")
        if plan.get("ready_actions"):
            print("  ready_actions:")
            for a in plan["ready_actions"]:
                print(f"    - {a['label']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
