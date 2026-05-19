#!/usr/bin/env python3
"""
dispatcher.py — Phase F (v0). The other side of the librarian / manager split.

The librarian resolves layer state. The manager classifies product
readiness + estimability. The dispatcher PROPOSES the next concrete
action: for every question the user asks about, it walks the manager's
`next_actions[]` list and emits one action_manifest_v1 JSON per
proposed run into a queue directory (`02_queue/`).

Crucially: **the dispatcher never executes.** It writes manifests.
Running them is a separate step (e.g. POST /api/actions from PR #3).
This preserves the §refusals: connect ≠ resolve ≠ run.

Usage
-----
  python3 -m lib.dispatcher --question inversion_pair_incompatibility_LG01_LG28
      # dry run — prints the manifests that WOULD be queued

  python3 -m lib.dispatcher --question inversion_pair_incompatibility_LG01_LG28 --commit
      # writes the manifests to 02_queue/<action_id>.json

  python3 -m lib.dispatcher --list
      # show what's currently queued

  python3 -m lib.dispatcher --clear
      # empty the queue (requires --yes when stdin is not a tty)

Stdlib only. Imports the Manager from lib/manager.py when available;
falls back to reading questions.jsonl directly if not.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import string
import sys
import time
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
    sys.path.insert(0, str(root.parent))
    try:
        from relatedness.lib.manager import Manager  # type: ignore
        return Manager(root)
    except Exception:
        return None


# --------------------------------------------------------------------------- #
class Dispatcher:
    """Proposes next runs. Writes action_manifest_v1 JSONs to 02_queue/.

    Does NOT execute anything; that's the runner / POST /api/actions
    contract from PIPELINE_FLOW.md and PR #3.
    """

    def __init__(self, registry_root: pathlib.Path):
        self.root = registry_root
        reg = registry_root / "01_registry"
        self.products  = {p["product_id"]:  p for p in _read_jsonl(reg / "products.jsonl")}
        self.questions = {q["question_id"]: q for q in _read_jsonl(reg / "questions.jsonl")}
        self.analyses  = {a["analysis_id"]: a for a in _read_jsonl(reg / "analysis_registry.jsonl")}
        self.manager   = _import_manager(registry_root)
        self.queue_dir = registry_root / "02_queue"

    # ---- public ----
    def plan(self, question_id: str, scope: Optional[Dict] = None) -> Dict:
        """Compute what would be dispatched (no writes)."""
        scope = scope or {}
        q = self.questions.get(question_id)
        if not q:
            return {"question_id": question_id, "manifests": [],
                    "reason": "question not in questions.jsonl"}

        if self.manager:
            rep = self.manager.check_question_readiness(question_id, scope)
        else:
            rep = self._fallback_readiness(question_id)

        manifests: List[Dict] = []
        seen_analysis_ids = set()  # de-dupe — same analysis can produce multiple missing products
        for req in (rep.get("per_required") or []):
            if not req.get("required", True): continue
            if req["status"] not in {"missing", "blocked"}: continue
            pid = req["product_id"]
            producer = (req.get("produced_by") or {}).get("analysis_id")
            if not producer:
                # No producer registered — emit a "register_producer" suggestion only.
                manifests.append({
                    "kind": "register_producer",
                    "product_id": pid,
                    "reason": "no analysis_registry row declares this product as produces",
                    "action_id": _mint_action_id("reg"),
                    "skipped": True,
                })
                continue
            if producer in seen_analysis_ids:
                continue
            seen_analysis_ids.add(producer)
            manifests.append(self._build_manifest(producer, pid, question_id, scope))
        return {
            "question_id":    question_id,
            "schema_version": "dispatcher_plan_v1",
            "aggregate":      rep.get("status", "unknown"),
            "scope":          scope,
            "manifests":      manifests,
        }

    def dispatch(self, question_id: str, scope: Optional[Dict] = None,
                 *, commit: bool = False) -> Dict:
        plan = self.plan(question_id, scope)
        runnable = [m for m in plan["manifests"] if not m.get("skipped")]
        if not commit:
            return {"committed": 0, "would_commit": len(runnable),
                    "skipped": len(plan["manifests"]) - len(runnable),
                    "queue_dir": str(self.queue_dir),
                    "manifests": plan["manifests"]}
        self.queue_dir.mkdir(parents=True, exist_ok=True)
        written = []
        for m in runnable:
            p = self.queue_dir / f"{m['action_id']}.json"
            p.write_text(json.dumps(m, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            written.append({"path": str(p), "action_id": m["action_id"], "type": m["type"]})
        return {"committed": len(written),
                "skipped":   len(plan["manifests"]) - len(runnable),
                "queue_dir": str(self.queue_dir),
                "written":   written,
                "all":       plan["manifests"]}

    def list_queued(self) -> List[Dict]:
        if not self.queue_dir.is_dir(): return []
        out = []
        for p in sorted(self.queue_dir.glob("act_*.json")):
            try:
                out.append({"path": str(p), **json.loads(p.read_text(encoding="utf-8"))})
            except Exception as e:
                out.append({"path": str(p), "error": str(e)})
        return out

    def clear(self) -> int:
        if not self.queue_dir.is_dir(): return 0
        n = 0
        for p in self.queue_dir.glob("act_*.json"):
            p.unlink()
            n += 1
        return n

    # ---- internals ----
    def _build_manifest(self, analysis_id: str, produces_layer: str,
                        question_id: str, scope: Dict) -> Dict:
        """Construct a minimal action_manifest_v1 row."""
        a = self.analyses.get(analysis_id, {})
        action_id = _mint_action_id(analysis_id[:8])
        dataset_id = (scope.get("sample_set") or "default_cohort")
        target = {k: v for k, v in scope.items() if v}
        m = {
            "schema_version":   "action_manifest_v1",
            "action_id":        action_id,
            "type":             "run_" + analysis_id,
            "dataset_id":       dataset_id,
            "runner":           a.get("default_runner") or f"runners.{analysis_id}.run",
            "target":           target,
            "params":           {},
            "expected_outputs": [{"layer_type": produces_layer,
                                  "schema_version": f"{produces_layer}_v1",
                                  "stage": "normalized"}],
            "submitted_by":     "lib.dispatcher",
            "submitted_at":     time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "notes":            f"proposed by dispatcher for question {question_id!r}",
            "_dispatch": {
                "question_id":  question_id,
                "produces":     produces_layer,
                "analysis_id":  analysis_id,
                "reason":       "manager readiness reported this product as missing/blocked",
            },
        }
        return m

    def _fallback_readiness(self, qid: str) -> Dict:
        """Minimal readiness shape when the Manager isn't importable."""
        q = self.questions.get(qid) or {}
        per = []
        for r in (q.get("requires") or []):
            p = self.products.get(r["product_id"]) or {}
            status = "missing" if not p.get("backed_by_layers") else "available"
            per.append({"product_id": r["product_id"], "status": status,
                        "required": r.get("required", True),
                        "produced_by": p.get("produced_by") or {}})
        return {"question_id": qid, "status": "partial", "per_required": per}


def _mint_action_id(tag: str) -> str:
    ts = int(time.time() * 1000)
    # 3-char suffix from time microseconds (deterministic-ish, no random module needed for v0)
    micro = int((time.time() - int(time.time())) * 1_000_000) % 46656  # 36^3
    chars = string.digits + string.ascii_lowercase
    s = ""
    for _ in range(3):
        s = chars[micro % 36] + s; micro //= 36
    safe = "".join(c for c in tag if c.isalnum())[:12].lower() or "x"
    return f"act_{ts}_{safe}_{s}"


# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--question", help="question_id to plan / dispatch from")
    g.add_argument("--list",  action="store_true", help="list manifests currently queued")
    g.add_argument("--clear", action="store_true", help="delete every manifest from the queue dir")
    ap.add_argument("--commit", action="store_true",
                    help="actually write manifests to 02_queue/ (default: dry run)")
    ap.add_argument("--yes",    action="store_true", help="confirm --clear in a non-tty session")
    ap.add_argument("--sample-set",   default=None)
    ap.add_argument("--interval-set", default=None)
    ap.add_argument("--candidate",    default=None)
    ap.add_argument("--registry-root", default=None)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    start = pathlib.Path(args.registry_root) if args.registry_root else pathlib.Path(__file__).parent
    root  = _find_root(start)
    d = Dispatcher(root)

    if args.list:
        rows = d.list_queued()
        if args.json:
            print(json.dumps(rows, indent=2)); return 0
        if not rows:
            print(f"queue is empty ({d.queue_dir})"); return 0
        print(f"{len(rows)} manifest(s) queued in {d.queue_dir}:")
        for r in rows:
            print(f"  {r.get('action_id', '?'):>50}  {r.get('type', '?')}   produces={r.get('expected_outputs', [{}])[0].get('layer_type', '?')}")
        return 0

    if args.clear:
        if sys.stdin.isatty():
            try:
                ans = input(f"delete every act_*.json from {d.queue_dir}? [y/N] ").strip().lower()
            except EOFError:
                ans = "n"
            if ans not in {"y", "yes"}:
                print("aborted"); return 0
        else:
            if not args.yes:
                print("--clear in non-tty session requires --yes", file=sys.stderr); return 2
        n = d.clear()
        print(f"cleared {n} manifest(s) from {d.queue_dir}"); return 0

    scope = {"sample_set":   args.sample_set,
             "interval_set": args.interval_set,
             "candidate_id": args.candidate}
    out = d.dispatch(args.question, scope, commit=args.commit)

    if args.json:
        print(json.dumps(out, indent=2)); return 0

    if args.commit:
        print(f"committed {out['committed']} manifest(s) to {out['queue_dir']}")
        for w in out["written"]:
            print(f"  + {w['action_id']}   type={w['type']}   → {w['path']}")
        if out["skipped"]:
            print(f"  ({out['skipped']} skipped — see plan for 'register_producer' suggestions)")
    else:
        print(f"DRY RUN — would commit {out['would_commit']} manifest(s) to {out['queue_dir']}")
        for m in out["manifests"]:
            if m.get("skipped"):
                print(f"  · register_producer for {m['product_id']!r}  ({m['reason']})")
            else:
                print(f"  + {m['action_id']}   type={m['type']}   produces={m['expected_outputs'][0]['layer_type']}")
        print("  (re-run with --commit to write)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
