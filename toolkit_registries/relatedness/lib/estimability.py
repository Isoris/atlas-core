#!/usr/bin/env python3
"""
estimability.py — the Estimability Manager (sub-role of MANAGER_SPEC.md §3.5).

The Status Manager answers "is this product ready?".  The Estimability
Manager answers "given the data we have, what specific scientific claims
can we actually make?".

Per estimand, returns one of:
  estimable           all preconditions met
  partially_estimable required preconditions met; optional gaps logged
  not_estimable       a required precondition is missing and fixable
                      from new compute / data ingest
  needs_extra_data    a required precondition is structurally missing
                      (e.g. parent sex unrecorded) — needs new metadata
                      or new samples, not new compute

Stdlib only.  Read-only.  Recursive over the Status Manager.

Usage:
  python3 -m lib.estimability --estimand observed_inheritance_effects
  python3 -m lib.estimability --question inversion_effect_on_meiosis_per_chromosome --json
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Dict, List, Optional


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


def _import_manager(root: pathlib.Path):
    """Try to load the Status Manager.  Fail soft when run in isolation."""
    sys.path.insert(0, str(root.parent))
    try:
        from relatedness.lib.manager import Manager  # type: ignore
        return Manager(root)
    except Exception:
        return None


# --------------------------------------------------------------------------- #
class EstimabilityManager:
    """The Estimability Manager.  Sits beside the Status Manager."""

    ESTIMAND_STATES = ("estimable", "partially_estimable", "not_estimable", "needs_extra_data")
    QUESTION_STATES = ("fully_estimable", "partially_estimable", "limited", "needs_extra_data", "unknown")

    # Sample-attribute statuses that count as "met"
    ATTRIBUTE_MET   = {"known", "covered"}
    ATTRIBUTE_PARTIAL = {"partial"}
    ATTRIBUTE_MISSING = {"unknown", "missing", "not_recorded"}

    def __init__(self, registry_root: pathlib.Path):
        self.root = registry_root
        reg = registry_root / "01_registry"
        self.estimands  = {e["estimand_id"]: e for e in _read_jsonl(reg / "estimands.jsonl")}
        self.attributes = {a["attribute"]:   a for a in _read_jsonl(reg / "sample_attributes.jsonl")}
        self.layers     = {l["layer_id"]:    l for l in _read_jsonl(reg / "layer_registry.jsonl")}
        self.questions  = {q["question_id"]: q for q in _read_jsonl(reg / "questions.jsonl")}
        self.manager    = _import_manager(registry_root)

    # ---- public ----
    def check_estimand(self, estimand_id: str, scope: Optional[Dict] = None) -> Dict:
        scope = scope or {}
        e = self.estimands.get(estimand_id)
        if not e:
            return {"estimand_id": estimand_id, "status": "not_estimable",
                    "reason": "estimand not in estimands.jsonl"}

        met:     List[Dict] = []
        missing: List[Dict] = []
        soft:    List[Dict] = []   # required=false but missing
        for pre in (e.get("preconditions") or []):
            r = self._resolve_precondition(pre, scope)
            r["precondition"] = pre
            if r["met"]:
                met.append(r)
            elif pre.get("required", True):
                missing.append(r)
            else:
                soft.append(r)

        # Aggregate
        if not missing and not soft:
            status, reason = "estimable", "all preconditions met"
        elif not missing and soft:
            status = "partially_estimable"
            reason = f"optional preconditions missing: {', '.join(s['precondition'].get('attribute') or s['precondition'].get('product_id') or s['precondition'].get('layer_id') or '?' for s in soft)}"
        elif any(m["kind"] == "sample_attribute" and m["reason_kind"] == "structurally_missing" for m in missing):
            status = "needs_extra_data"
            reason = f"needs metadata: {', '.join(m['precondition']['attribute'] for m in missing if m['kind'] == 'sample_attribute')}"
        else:
            status = "not_estimable"
            reason = "missing: " + ", ".join(
                (m['precondition'].get('product_id')
                 or m['precondition'].get('layer_id')
                 or m['precondition'].get('attribute')
                 or '?') for m in missing)

        return {
            "estimand_id":  estimand_id,
            "schema_version":"estimand_eval_v1",
            "question_id":  e.get("question_id", ""),
            "label":        e.get("label", ""),
            "status":       status,
            "reason":       reason,
            "met":          met,
            "missing":      missing,
            "soft_missing": soft,
            "limitations":  e.get("limitations", []),
        }

    def check_question_estimability(self, question_id: str,
                                    scope: Optional[Dict] = None) -> Dict:
        scope = scope or {}
        eids = [eid for eid, e in self.estimands.items()
                if e.get("question_id") == question_id]
        if not eids:
            return {"question_id": question_id, "status": "unknown",
                    "reason": "no estimands declared for this question"}
        per = [self.check_estimand(eid, scope) for eid in eids]
        statuses = {p["status"] for p in per}
        if statuses == {"estimable"}:
            agg = "fully_estimable"
        elif statuses <= {"estimable", "partially_estimable"}:
            agg = "partially_estimable"
        elif "needs_extra_data" in statuses:
            agg = "needs_extra_data"
        else:
            agg = "limited"
        return {
            "question_id":    question_id,
            "schema_version": "question_estimability_v1",
            "label":          self.questions.get(question_id, {}).get("label", ""),
            "status":         agg,
            "per_estimand":   per,
        }

    # ---- precondition resolvers ----
    def _resolve_precondition(self, pre: Dict, scope: Dict) -> Dict:
        kind = pre.get("kind")
        if kind == "product":
            return self._resolve_product(pre, scope)
        if kind == "layer":
            return self._resolve_layer(pre, scope)
        if kind == "sample_attribute":
            return self._resolve_attribute(pre, scope)
        return {"kind": kind, "met": False, "reason": f"unknown precondition kind {kind!r}",
                "reason_kind": "schema_error"}

    def _resolve_product(self, pre: Dict, scope: Dict) -> Dict:
        pid = pre.get("product_id", "")
        if not self.manager:
            return {"kind": "product", "product_id": pid, "met": False,
                    "reason": "Status Manager not importable", "reason_kind": "manager_unavailable"}
        rec = self.manager.check_product_status(pid, scope)
        st = rec.get("status", "missing")
        met = st in {"ready", "validated", "available"}
        return {"kind": "product", "product_id": pid, "met": met,
                "reason": f"product status = {st}",
                "reason_kind": "registry_resolvable" if st in {"missing", "blocked"} else "ok"}

    def _resolve_layer(self, pre: Dict, scope: Dict) -> Dict:
        lid = pre.get("layer_id", "")
        # Defer to the librarian via the Status Manager's internal resolver.
        if not self.manager:
            return {"kind": "layer", "layer_id": lid, "met": False,
                    "reason": "Status Manager not importable", "reason_kind": "manager_unavailable"}
        r = self.manager._resolve_layer(lid, scope)
        st = r.get("state", "UNKNOWN_CONTRACT")
        met = st in {"RESOLVED", "COMPLETE"}
        return {"kind": "layer", "layer_id": lid, "met": met,
                "reason": f"layer state = {st}",
                "reason_kind": "registry_resolvable"}

    def _resolve_attribute(self, pre: Dict, scope: Dict) -> Dict:
        attr = pre.get("attribute", "")
        row  = self.attributes.get(attr)
        if not row:
            # Structurally unknown — needs new metadata, not new compute.
            return {"kind": "sample_attribute", "attribute": attr, "met": False,
                    "reason": "attribute not in sample_attributes.jsonl",
                    "reason_kind": "structurally_missing"}
        st = row.get("status", "unknown")
        if st in self.ATTRIBUTE_MET:
            return {"kind": "sample_attribute", "attribute": attr, "met": True,
                    "reason": f"attribute {st!r} (covered {row.get('n_covered', '?')}/{row.get('n_total', '?')})",
                    "reason_kind": "ok"}
        if st in self.ATTRIBUTE_PARTIAL:
            return {"kind": "sample_attribute", "attribute": attr, "met": False,
                    "reason": f"attribute partially covered ({row.get('n_covered', '?')}/{row.get('n_total', '?')})",
                    "reason_kind": "structurally_missing"}
        return {"kind": "sample_attribute", "attribute": attr, "met": False,
                "reason": f"attribute {st!r}: {row.get('reason', '')}",
                "reason_kind": "structurally_missing"}


# --------------------------------------------------------------------------- #
def _label(pre: Dict) -> str:
    return (pre.get("product_id") or pre.get("layer_id") or pre.get("attribute") or "?")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--estimand", default=None)
    ap.add_argument("--question", default=None)
    ap.add_argument("--sample-set", default=None)
    ap.add_argument("--interval-set", default=None)
    ap.add_argument("--candidate", default=None)
    ap.add_argument("--registry-root", default=None)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    if not args.estimand and not args.question:
        ap.error("provide --estimand or --question")

    start = pathlib.Path(args.registry_root) if args.registry_root else pathlib.Path(__file__).parent
    root = _find_root(start)
    em = EstimabilityManager(root)
    scope = {"sample_set": args.sample_set, "interval_set": args.interval_set,
             "candidate_id": args.candidate}

    if args.estimand:
        out = em.check_estimand(args.estimand, scope)
    else:
        out = em.check_question_estimability(args.question, scope)

    if args.json:
        print(json.dumps(out, indent=2)); return 0

    if args.estimand:
        print(f"[{out['status']:>18}] {out['estimand_id']}")
        print(f"  reason: {out['reason']}")
        for r in out.get("met", []):
            print(f"    + {r['kind']:>16}: {_label(r['precondition'])}   {r['reason']}")
        for r in out.get("missing", []):
            print(f"    ✗ {r['kind']:>16}: {_label(r['precondition'])}   {r['reason']}")
        for r in out.get("soft_missing", []):
            print(f"    · {r['kind']:>16}: {_label(r['precondition'])}   (soft) {r['reason']}")
        if out.get("limitations"):
            print("  limitations:")
            for l in out["limitations"]:
                print(f"    - {l}")
    else:
        print(f"question: {out['question_id']}  estimability: {out['status']}")
        for p in out.get("per_estimand", []):
            mark = {"estimable": "✓", "partially_estimable": "•",
                    "not_estimable": "✗", "needs_extra_data": "⚠"}.get(p["status"], "?")
            print(f"  {mark} [{p['status']:>20}] {p['estimand_id']}")
            print(f"     {p['reason']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
