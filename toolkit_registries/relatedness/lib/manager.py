#!/usr/bin/env python3
"""
manager.py — the readiness layer above the librarian.

Per MANAGER_SPEC.md.  The Manager does NOT replace the librarian; it sits
above it.  The librarian knows *where* layers / files / results are; the
Manager knows *whether they are usable now* — i.e. whether a registered
research product (one biological object) is ready for downstream use.

  check_product_status(product_id, scope)        -> readiness record
  check_question_readiness(question_id, scope)   -> readiness report

Stdlib only.  Read-only.  Recomputes status on every call.

Usage:
  python3 -m lib.manager --product inversion_karyotypes.v1
  python3 -m lib.manager --question inversion_effect_on_meiosis_per_chromosome
  python3 -m lib.manager --scope --product inversion_karyotypes.v1
                       --product pedigree_dyads.v1   --json
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


def _csv(s) -> List[str]:
    if isinstance(s, list): return [x for x in s if x]
    return [x.strip() for x in (s or "").split(",") if x.strip()]


# --------------------------------------------------------------------------- #
# We re-use the librarian's resolution logic by importing from resolve_layer.
# Falling back to a tiny inline resolver when the librarian isn't importable
# (e.g. running the manager in isolation from the relatedness layout).

def _import_resolver(root: pathlib.Path):
    sys.path.insert(0, str(root.parent))
    try:
        from relatedness.scripts.resolve_layer import Resolver  # type: ignore
        return Resolver(root)
    except Exception:
        return None


# --------------------------------------------------------------------------- #
class Manager:
    """The readiness layer above the librarian."""

    PRODUCT_STATES = ("ready", "validated", "available", "missing",
                      "blocked", "stale", "deprecated")
    QUESTION_STATES = ("ready_to_run", "partial", "blocked", "unknown")

    def __init__(self, registry_root: pathlib.Path):
        self.root = registry_root
        reg = registry_root / "01_registry"
        self.products  = {p["product_id"]:  p for p in _read_jsonl(reg / "products.jsonl")}
        self.questions = {q["question_id"]: q for q in _read_jsonl(reg / "questions.jsonl")}
        self.layers    = {l["layer_id"]:    l for l in _read_jsonl(reg / "layer_registry.jsonl")}
        self.analyses  = {a["analysis_id"]: a for a in _read_jsonl(reg / "analysis_registry.jsonl")}
        self.results   = _read_jsonl(reg / "analysis_results.jsonl")
        self.librarian = _import_resolver(registry_root)

    # ---- public ----
    def check_product_status(
        self,
        product_id: str,
        scope: Optional[Dict] = None,
        _seen: Optional[Set[str]] = None,
    ) -> Dict:
        """Return a readiness record for one product. Recursive over depends_on."""
        scope = scope or {}
        _seen = _seen or set()
        if product_id in _seen:
            return {"product_id": product_id, "status": "blocked",
                    "reason": "cycle in depends_on"}
        _seen = _seen | {product_id}
        p = self.products.get(product_id)
        if not p:
            return {"product_id": product_id, "status": "missing",
                    "reason": "product not in products.jsonl"}

        # Step 1: backing-layer resolution
        layer_states: List[Dict] = []
        for lid in (p.get("backed_by_layers") or []):
            layer_states.append(self._resolve_layer(lid, scope))
        layer_state_set = {l["state"] for l in layer_states}

        if not p.get("backed_by_layers"):
            base_status = "missing"
            base_reason = "no backed_by_layers declared"
        elif "UNKNOWN_CONTRACT" in layer_state_set:
            base_status = "missing"
            base_reason = f"backing layer contract missing ({_first(layer_states, 'UNKNOWN_CONTRACT')})"
        elif "FAILED" in layer_state_set:
            base_status = "blocked"
            base_reason = f"backing layer failed ({_first(layer_states, 'FAILED')})"
        elif "BLOCKED_BY_INPUT" in layer_state_set or "KNOWN_MISSING" in layer_state_set:
            base_status = "missing"
            base_reason = "backing layer(s) missing: " + ", ".join(
                f"{l['layer_id']}({l['state']})" for l in layer_states if l["state"] not in {"RESOLVED", "COMPLETE"})
        elif all(l["state"] in {"RESOLVED", "COMPLETE"} for l in layer_states):
            base_status = "available"
            base_reason = "backing layers resolve"
        else:
            base_status = "missing"
            base_reason = "indeterminate"

        # Step 2: confidence → validated / ready
        conf = (p.get("confidence") or "unreviewed").strip()
        if base_status == "available":
            if conf == "review_passed":
                base_status, base_reason = "ready", base_reason + "; review_passed"
            elif conf == "preliminary":
                base_status, base_reason = "validated", base_reason + "; preliminary (no review yet)"
            elif conf == "rejected":
                base_status, base_reason = "blocked", base_reason + "; review rejected"
            # 'unreviewed' stays at 'available'

        # Step 3: depends_on propagation
        upstream_bad, upstream_stale = [], []
        for dep in (p.get("depends_on") or []):
            dep_rec = self.check_product_status(dep, scope, _seen=_seen)
            if dep_rec["status"] in {"missing", "blocked", "deprecated"}:
                upstream_bad.append({"product_id": dep, "status": dep_rec["status"]})
            elif dep_rec["status"] == "stale":
                upstream_stale.append({"product_id": dep, "status": dep_rec["status"]})
        if upstream_bad:
            base_status = "blocked"
            base_reason = f"upstream not ready: " + ", ".join(
                f"{u['product_id']}({u['status']})" for u in upstream_bad)
        elif upstream_stale and base_status in {"ready", "validated", "available"}:
            base_status = "stale"
            base_reason = f"upstream stale: " + ", ".join(u["product_id"] for u in upstream_stale)

        return {
            "product_id":  product_id,
            "label":       p.get("label", ""),
            "kind":        p.get("kind", ""),
            "atlas":       p.get("atlas", ""),
            "status":      base_status,
            "reason":      base_reason,
            "confidence":  conf,
            "biological_scope": p.get("biological_scope", {}),
            "sample_scope":     p.get("sample_scope", ""),
            "coordinate_scope": p.get("coordinate_scope", ""),
            "backed_by_layers": p.get("backed_by_layers", []),
            "layer_states":     layer_states,
            "depends_on":       p.get("depends_on", []),
            "valid_for":        p.get("valid_for", []),
            "produced_by":      p.get("produced_by", {}),
            "path":             p.get("path", ""),
            "upstream_bad":     upstream_bad,
            "upstream_stale":   upstream_stale,
        }

    def check_question_readiness(
        self,
        question_id: str,
        scope: Optional[Dict] = None,
    ) -> Dict:
        scope = scope or {}
        q = self.questions.get(question_id)
        if not q:
            return {"question_id": question_id, "status": "unknown",
                    "reason": "question not in questions.jsonl"}
        per_req: List[Dict] = []
        for req in (q.get("requires") or []):
            pid = req["product_id"]
            rec = self.check_product_status(pid, scope)
            rec["role"]    = req.get("role", "")
            rec["required"] = req.get("required", True)
            per_req.append(rec)

        statuses = {r["status"] for r in per_req if r.get("required", True)}
        if not statuses:
            agg = "ready_to_run"
        elif statuses == {"ready"}:
            agg = "ready_to_run"
        elif "missing" in statuses or "blocked" in statuses or "deprecated" in statuses:
            agg = "partial" if "ready" in statuses or "validated" in statuses or "available" in statuses else "blocked"
        elif "stale" in statuses:
            agg = "partial"
        else:
            agg = "partial"

        # next_actions: for each missing/blocked required product, look up producer
        next_actions: List[Dict] = []
        for rec in per_req:
            if not rec.get("required", True): continue
            if rec["status"] in {"missing", "blocked"}:
                producer = rec.get("produced_by") or {}
                aid = producer.get("analysis_id")
                if aid:
                    next_actions.append({"action": "run", "analysis_id": aid,
                                         "produces": rec["product_id"],
                                         "label": f"Run {aid} to produce {rec['product_id']}"})
                else:
                    next_actions.append({"action": "register_producer",
                                         "produces": rec["product_id"],
                                         "label": f"Register a producing analysis for {rec['product_id']}"})

        return {
            "question_id":      question_id,
            "schema_version":   "manager_v1",
            "label":            q.get("label", ""),
            "description":      q.get("description", ""),
            "biological_scope": q.get("biological_scope", {}),
            "status":           agg,
            "per_required":     per_req,
            "outputs":          q.get("outputs", []),
            "tags":             q.get("tags", []),
            "next_actions":     next_actions,
        }

    def check_scope_intersection(self, product_ids: List[str], scope: Optional[Dict] = None) -> Dict:
        """Given a set of products the user has 'scoped in', return the
        what's-around report: their readiness, plus nearby products that
        share scope and questions answerable today."""
        scope = scope or {}
        selected = [self.check_product_status(pid, scope) for pid in product_ids]

        # Nearby products: same sample_scope OR same coordinate_scope
        sample_scopes = {p.get("sample_scope") for p in selected if p.get("sample_scope")}
        coord_scopes  = {p.get("coordinate_scope") for p in selected if p.get("coordinate_scope")}
        nearby: List[Dict] = []
        for pid, p in self.products.items():
            if pid in product_ids: continue
            if (p.get("sample_scope") in sample_scopes) or (p.get("coordinate_scope") in coord_scopes):
                nearby.append({
                    "product_id": pid,
                    "label":      p.get("label", ""),
                    "kind":       p.get("kind", ""),
                    "status_quick": self.check_product_status(pid, scope)["status"],
                    "sample_scope":     p.get("sample_scope", ""),
                    "coordinate_scope": p.get("coordinate_scope", ""),
                })

        # Answerable questions: ones whose requires[] intersects with selected
        sel_set = set(product_ids)
        answerable: List[Dict] = []
        for qid, q in self.questions.items():
            req_ids = [r["product_id"] for r in (q.get("requires") or [])]
            if any(rid in sel_set for rid in req_ids):
                rep = self.check_question_readiness(qid, scope)
                answerable.append({
                    "question_id": qid,
                    "label":       q.get("label", ""),
                    "status":      rep["status"],
                    "uses_selected": sorted(set(req_ids) & sel_set),
                })

        return {
            "schema_version":   "manager_scope_intersection_v1",
            "selected_products":selected,
            "selected_ids":     product_ids,
            "scope":            scope,
            "nearby_products":  nearby,
            "answerable_questions": answerable,
        }

    # ---- internals ----
    def _resolve_layer(self, layer_id: str, scope: Dict) -> Dict:
        """Resolve one layer either via the imported librarian or a tiny fallback."""
        if self.librarian is not None:
            try:
                r = self.librarian.resolve_layer(
                    layer_id,
                    scope.get("sample_set"),
                    scope.get("interval_set"),
                    scope.get("candidate_id"),
                )
                return {"layer_id": layer_id, "state": r["state"], "reason": r.get("reason", "")}
            except Exception as e:
                return {"layer_id": layer_id, "state": "UNKNOWN_CONTRACT", "reason": f"librarian failed: {e}"}
        # tiny fallback: check whether the layer is in layer_registry
        if layer_id not in self.layers:
            return {"layer_id": layer_id, "state": "UNKNOWN_CONTRACT", "reason": "no library"}
        return {"layer_id": layer_id, "state": "RESOLVED", "reason": "fallback resolver (always RESOLVED)"}


def _first(states: List[Dict], match: str) -> str:
    for s in states:
        if s["state"] == match: return s["layer_id"]
    return ""


# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--product",  action="append", default=[], help="product_id (repeatable)")
    ap.add_argument("--question", default=None, help="question_id")
    ap.add_argument("--scope",    action="store_true", help="treat the --product list as a scope intersection")
    ap.add_argument("--sample-set",   default=None)
    ap.add_argument("--interval-set", default=None)
    ap.add_argument("--candidate",    default=None)
    ap.add_argument("--registry-root", default=None)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if not args.product and not args.question:
        ap.error("at least one --product or --question is required")

    start = pathlib.Path(args.registry_root) if args.registry_root else pathlib.Path(__file__).parent
    root = _find_root(start)
    mgr = Manager(root)
    scope = {"sample_set": args.sample_set, "interval_set": args.interval_set, "candidate_id": args.candidate}

    if args.question:
        rep = mgr.check_question_readiness(args.question, scope)
        out = rep
    elif args.scope and len(args.product) > 1:
        out = mgr.check_scope_intersection(args.product, scope)
    elif len(args.product) == 1:
        out = mgr.check_product_status(args.product[0], scope)
    else:
        # multiple products without --scope: just print each
        out = [mgr.check_product_status(pid, scope) for pid in args.product]

    if args.json:
        print(json.dumps(out, indent=2)); return 0

    if args.question:
        print(f"question: {out['question_id']}  status: {out['status']}")
        print(f"  label: {out['label']}")
        for r in out.get("per_required", []):
            mark = {"ready": "✓", "validated": "•", "available": "•",
                    "missing": "✗", "blocked": "✗", "stale": "⚠",
                    "deprecated": "·"}.get(r["status"], "?")
            print(f"  {mark} [{r['status']:>10}] {r['product_id']}   ({r.get('role', '')})")
        if out.get("next_actions"):
            print("  next_actions:")
            for a in out["next_actions"]:
                print(f"    - {a['label']}")
    elif isinstance(out, dict) and out.get("schema_version") == "manager_scope_intersection_v1":
        print(f"scope intersection of {len(out['selected_ids'])} products")
        print("  selected:")
        for s in out["selected_products"]:
            print(f"    [{s['status']:>10}] {s['product_id']}  {s.get('label', '')}")
        if out.get("nearby_products"):
            print(f"  nearby ({len(out['nearby_products'])}):")
            for n in out["nearby_products"]:
                print(f"    [{n['status_quick']:>10}] {n['product_id']}  {n['label']}")
        if out.get("answerable_questions"):
            print(f"  answerable questions ({len(out['answerable_questions'])}):")
            for q in out["answerable_questions"]:
                print(f"    [{q['status']:>12}] {q['question_id']}  uses=[{','.join(q['uses_selected'])}]")
    elif isinstance(out, list):
        for r in out:
            print(f"[{r['status']:>10}] {r['product_id']}   {r['reason']}")
    else:
        print(f"[{out['status']:>10}] {out['product_id']}")
        print(f"  reason: {out['reason']}")
        print(f"  confidence: {out['confidence']}")
        if out.get("upstream_bad"):
            print(f"  upstream bad: {', '.join(u['product_id'] for u in out['upstream_bad'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
