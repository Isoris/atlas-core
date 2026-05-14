#!/usr/bin/env python3
"""
resolve_layer.py — APLR's librarian.

Given a layer_id (and optionally a scope: sample_set_id / interval_set_id /
candidate_id), return one of nine states:

  RESOLVED            terminal source-kind layer present (file row found, etc.)
  KNOWN_MISSING       contract registered, no product / file matches the scope
  UNKNOWN_CONTRACT    layer_id not in layer_registry.tsv
  BLOCKED_BY_INPUT    analysis_result layer; some upstream input is itself
                      KNOWN_MISSING / BLOCKED / UNKNOWN
  READY_TO_RUN        analysis_result layer; every upstream resolves to
                      RESOLVED / COMPLETE — the analysis would be runnable
  COMPLETE            analysis_result layer; a matching row exists in
                      analysis_results.tsv with status=active
  STALE               not used yet (placeholder for hash-based invalidation)
  FAILED              analysis_results row exists with status=failed
  PARTIAL             not used yet (placeholder for chunked / per-chrom outputs)

This script is the *librarian* — it never runs anything, never writes anything.
The dispatcher / planner (separate concern) uses these states to decide what
to do next.

Usage
-----
  python3 resolve_layer.py --layer mendelian_result \
      --sample-set samples_226_v1 --interval inv_LG28_INV_001_v1
  python3 resolve_layer.py --hook mendelian_page_load \
      --sample-set samples_226_v1 --candidate inv_LG28_INV_001

Stdlib only.
"""
from __future__ import annotations

import argparse
import csv
import json
import pathlib
import sys
from typing import Dict, List, Optional, Set, Tuple

STATES = (
    "RESOLVED", "KNOWN_MISSING", "UNKNOWN_CONTRACT",
    "BLOCKED_BY_INPUT", "READY_TO_RUN", "COMPLETE",
    "STALE", "FAILED", "PARTIAL",
)


def _find_root(start: pathlib.Path) -> pathlib.Path:
    for cand in [start.resolve(), *start.resolve().parents]:
        if (cand / "01_registry" / "layer_registry.tsv").is_file():
            return cand
    raise SystemExit("could not find 01_registry/layer_registry.tsv anywhere above " + str(start))


def _read_tsv(path: pathlib.Path) -> List[Dict[str, str]]:
    if not path.is_file():
        return []
    with open(path, newline="", encoding="utf-8") as fh:
        return [{k: (v if v is not None else "") for k, v in r.items()}
                for r in csv.DictReader(fh, delimiter="\t")]


def _index(rows: List[Dict[str, str]], key: str) -> Dict[str, Dict[str, str]]:
    return {r[key]: r for r in rows if r.get(key)}


def _csv_field(s: Optional[str]) -> List[str]:
    return [x.strip() for x in (s or "").split(",") if x.strip()]


# --------------------------------------------------------------------------- #
class Resolver:
    """The librarian. Pure read-only graph walk over the registry TSVs."""

    def __init__(self, root: pathlib.Path):
        self.root = root
        reg = root / "01_registry"
        self.layers   = _index(_read_tsv(reg / "layer_registry.tsv"),   "layer_id")
        self.hooks    = _index(_read_tsv(reg / "hook_registry.tsv"),    "hook_id")
        self.analyses = _index(_read_tsv(reg / "analysis_registry.tsv"),"analysis_id")
        self.results  = _read_tsv(reg / "analysis_results.tsv")
        self.values   = _read_tsv(reg / "input_values.tsv")
        self.samples  = _index(_read_tsv(reg / "sample_sets.tsv"),   "sample_set_id")
        self.intervals= _index(_read_tsv(reg / "interval_sets.tsv"), "interval_set_id")
        self.sites    = _index(_read_tsv(reg / "site_sets.tsv"),     "site_set_id")
        self.groups   = _index(_read_tsv(reg / "group_sets.tsv"),    "group_set_id")
        # Index analysis_result rows for quick lookup by analysis_type + scope.
        # Use the dict's preservation of insertion order so __repr__ stays stable.

    # ---- public API ----
    def resolve_layer(
        self,
        layer_id: str,
        sample_set: Optional[str] = None,
        interval_set: Optional[str] = None,
        candidate_id: Optional[str] = None,
        _seen: Optional[Set[str]] = None,
    ) -> Dict[str, object]:
        """Return {state, layer_id, reason, scope, upstream:[...]}."""
        _seen = _seen or set()
        if layer_id in _seen:
            # cycle guard
            return self._mk(layer_id, "BLOCKED_BY_INPUT", "cycle in graph",
                            sample_set, interval_set, candidate_id)
        _seen = _seen | {layer_id}

        row = self.layers.get(layer_id)
        if not row:
            return self._mk(layer_id, "UNKNOWN_CONTRACT",
                            "layer_id not in layer_registry.tsv",
                            sample_set, interval_set, candidate_id)

        kind = row.get("source_kind", "")
        if kind == "file":
            return self._resolve_file_layer(row, sample_set, interval_set, candidate_id)
        if kind == "analysis_result":
            return self._resolve_analysis_layer(
                row, sample_set, interval_set, candidate_id, _seen)
        # operation / inline source kinds: not yet implemented; return UNKNOWN.
        return self._mk(layer_id, "UNKNOWN_CONTRACT",
                        f"source_kind {kind!r} not yet implemented in librarian",
                        sample_set, interval_set, candidate_id)

    def resolve_hook(
        self,
        hook_id: str,
        sample_set: Optional[str] = None,
        interval_set: Optional[str] = None,
        candidate_id: Optional[str] = None,
    ) -> Dict[str, object]:
        hook = self.hooks.get(hook_id)
        if not hook:
            return {"hook_id": hook_id, "state": "UNKNOWN_CONTRACT",
                    "reason": "hook_id not in hook_registry.tsv", "layers": []}
        per_layer = []
        for lid in _csv_field(hook.get("requires_layers")):
            per_layer.append(self.resolve_layer(
                lid, sample_set, interval_set, candidate_id))
        # Hook is "ready" iff every layer is RESOLVED or COMPLETE.
        ready = all(p["state"] in {"RESOLVED", "COMPLETE"} for p in per_layer)
        blocked = any(p["state"] in {"KNOWN_MISSING", "BLOCKED_BY_INPUT", "UNKNOWN_CONTRACT", "FAILED"} for p in per_layer)
        if ready:
            agg = "RESOLVED"
        elif blocked:
            agg = "BLOCKED_BY_INPUT"
        else:
            agg = "READY_TO_RUN"
        return {"hook_id": hook_id, "state": agg, "page_id": hook.get("page_id", ""),
                "provides_view": hook.get("provides_view", ""), "layers": per_layer}

    def compose_hook(
        self,
        hook_id: str,
        sample_set: Optional[str] = None,
        interval_set: Optional[str] = None,
        candidate_id: Optional[str] = None,
    ) -> Dict[str, object]:
        """Return a page_composition_plan_v1 dict for a hook.
        Per LAYER_GRAPH_BUILDER_SPEC.md §5 — maps each layer's
        librarian state into a panel_state via the fixed table."""
        hook = self.hooks.get(hook_id)
        if not hook:
            return {"hook_id": hook_id, "schema_version": "page_composition_plan_v1",
                    "page_id": "", "hook_state": "HIDDEN", "panels": [],
                    "reason": "hook_id not in hook_registry.tsv"}

        req = _csv_field(hook.get("requires_layers"))
        opt = _csv_field(hook.get("optional_layers"))
        panel_ids = _csv_field(hook.get("panels"))
        all_layers = [(lid, True) for lid in req] + [(lid, False) for lid in opt]

        panels: List[Dict[str, object]] = []
        for i, (lid, is_required) in enumerate(all_layers):
            res = self.resolve_layer(lid, sample_set, interval_set, candidate_id)
            panel_state = self._panel_state(res["state"], is_required)
            panel_id = panel_ids[i] if i < len(panel_ids) else f"{lid}_panel"
            entry: Dict[str, object] = {
                "panel_id":    panel_id,
                "layer_id":    lid,
                "required":    is_required,
                "panel_state": panel_state,
                "layer_state": res["state"],
                "reason":      res.get("reason", ""),
            }
            # missing_layers: from upstream of an analysis_result
            missing = [u["layer_id"] for u in res.get("upstream", []) or []
                       if u["state"] in {"KNOWN_MISSING", "BLOCKED_BY_INPUT",
                                          "UNKNOWN_CONTRACT", "FAILED"}]
            if missing:
                entry["missing_layers"] = missing
            if "result_id" in res:
                entry["result_id"] = res["result_id"]
            row = self.layers.get(lid, {})
            if res["state"] == "RESOLVED" and row.get("default_path"):
                entry["default_path"] = row["default_path"]
            # actions: suggestions (the dispatcher reads these; they're never auto-executed)
            actions = []
            if panel_state == "READY_TO_RUN":
                # find which producer analysis would run
                producers = [a["analysis_id"] for a in self.analyses.values()
                             if lid in _csv_field(a.get("produces"))]
                for aid in producers:
                    actions.append({"action": "run", "label": f"Run {aid}", "target": aid})
            elif panel_state == "VISIBLE_BLOCKED":
                actions.append({"action": "edit_registry",
                                "label": f"Inspect {lid} in the layer registry",
                                "target": lid})
            if actions:
                entry["actions"] = actions
            panels.append(entry)

        hook_state = self._aggregate_hook_state(panels)
        return {
            "hook_id":        hook_id,
            "schema_version": "page_composition_plan_v1",
            "page_id":        hook.get("page_id", ""),
            "scope": {"sample_set": sample_set, "interval_set": interval_set,
                      "candidate_id": candidate_id},
            "hook_state":     hook_state,
            "panels":         panels,
        }

    @staticmethod
    def _panel_state(layer_state: str, is_required: bool) -> str:
        if layer_state in {"RESOLVED", "COMPLETE"}:
            return "VISIBLE_COMPLETE"
        if layer_state == "READY_TO_RUN":
            return "READY_TO_RUN"
        if layer_state in {"STALE", "PARTIAL"}:
            return "VISIBLE_PARTIAL"
        # missing / blocked / unknown / failed
        return "VISIBLE_BLOCKED" if is_required else "HIDDEN_OPTIONAL"

    @staticmethod
    def _aggregate_hook_state(panels: List[Dict[str, object]]) -> str:
        req = [p for p in panels if p["required"]]
        if not req:
            return "HIDDEN"
        req_states = {p["panel_state"] for p in req}
        if req_states == {"VISIBLE_COMPLETE"}:
            return "COMPLETE"
        if req_states == {"READY_TO_RUN"}:
            return "READY_TO_RUN"
        if req_states == {"VISIBLE_BLOCKED"}:
            return "BLOCKED"
        if all(p["panel_state"] in {"VISIBLE_BLOCKED"} for p in req if p["layer_state"] == "UNKNOWN_CONTRACT"):
            # Every required layer is UNKNOWN_CONTRACT → page is hidden entirely
            if all(p["layer_state"] == "UNKNOWN_CONTRACT" for p in req):
                return "HIDDEN"
        return "PARTIAL"

    # ---- internals ----
    def _resolve_file_layer(self, row, sample_set, interval_set, candidate_id):
        lid = row["layer_id"]
        # First: probe default_path if declared. A present file always resolves.
        default = (row.get("default_path") or "").strip()
        if default:
            candidate_path = (self.root / default).resolve()
            if candidate_path.exists():
                return self._mk(lid, "RESOLVED",
                                f"file present at {default}",
                                sample_set, interval_set, candidate_id,
                                default_path=default)
            # default_path declared but missing → KNOWN_MISSING, unless we fall
            # through to a scope-driven lookup below.
        # Map known file layers to their underlying registry.
        if lid == "sample_set":
            present = bool(sample_set) and sample_set in self.samples
            return self._mk(lid, "RESOLVED" if present else "KNOWN_MISSING",
                            f"sample_set_id={sample_set!r} {'found' if present else 'not in sample_sets.tsv'}",
                            sample_set, interval_set, candidate_id)
        if lid == "interval_set":
            present = bool(interval_set) and interval_set in self.intervals
            return self._mk(lid, "RESOLVED" if present else "KNOWN_MISSING",
                            f"interval_set_id={interval_set!r} {'found' if present else 'not in interval_sets.tsv'}",
                            sample_set, interval_set, candidate_id)
        if lid == "beagle_file":
            hits = [v for v in self.values if v.get("value_kind") == "beagle"
                    and (not sample_set   or v.get("sample_set_id")   == sample_set)
                    and (not interval_set or v.get("interval_set_id") == interval_set)]
            return self._mk(lid, "RESOLVED" if hits else "KNOWN_MISSING",
                            f"{len(hits)} beagle row(s) match scope",
                            sample_set, interval_set, candidate_id)
        if lid == "sites_file":
            hits = [s for s in self.sites.values()
                    if not interval_set or s.get("interval_set_id") == interval_set]
            return self._mk(lid, "RESOLVED" if hits else "KNOWN_MISSING",
                            f"{len(hits)} site_set row(s) match scope",
                            sample_set, interval_set, candidate_id)
        if lid == "group_set":
            return self._mk(lid, "RESOLVED" if self.groups else "KNOWN_MISSING",
                            f"{len(self.groups)} group_set row(s) registered",
                            sample_set, interval_set, candidate_id)
        # stub / external file layers (karyotype_calls, inversion_candidates):
        # status=stub → KNOWN_MISSING by convention until a producer registers.
        return self._mk(lid, "KNOWN_MISSING",
                        f"{lid}: file-kind layer; no producer registered (status={row.get('status')})",
                        sample_set, interval_set, candidate_id)

    def _resolve_analysis_layer(self, row, sample_set, interval_set, candidate_id, seen):
        lid = row["layer_id"]
        # Find producer analyses: analysis_registry rows whose `produces`
        # contains this layer_id.
        producers = [a for a in self.analyses.values()
                     if lid in _csv_field(a.get("produces"))]
        if not producers:
            return self._mk(lid, "UNKNOWN_CONTRACT",
                            f"no analysis_registry row declares produces={lid!r}",
                            sample_set, interval_set, candidate_id)
        # Check whether a matching analysis_result already exists.
        producer_ids = {a["analysis_id"] for a in producers}
        for r in self.results:
            if r.get("analysis_type") not in producer_ids:
                continue
            if sample_set   and r.get("sample_set_id")   != sample_set:   continue
            if interval_set and r.get("interval_set_id") != interval_set: continue
            status = r.get("status", "")
            if status == "active":
                return self._mk(lid, "COMPLETE",
                                f"analysis_results.tsv row {r.get('result_id')!r} matches scope",
                                sample_set, interval_set, candidate_id,
                                result_id=r.get("result_id"))
            if status == "failed":
                return self._mk(lid, "FAILED",
                                f"analysis_results.tsv row {r.get('result_id')!r} status=failed",
                                sample_set, interval_set, candidate_id,
                                result_id=r.get("result_id"))
        # No existing result. Walk upstream — the analysis's input_layer_types.
        # If every upstream resolves to RESOLVED / COMPLETE -> READY_TO_RUN;
        # else BLOCKED_BY_INPUT.
        upstream_states = []
        for a in producers:
            for upstream_lid in _csv_field(a.get("input_layer_types")):
                up = self.resolve_layer(upstream_lid, sample_set, interval_set,
                                        candidate_id, _seen=seen)
                upstream_states.append(up)
        ok = {"RESOLVED", "COMPLETE"}
        bad = {"KNOWN_MISSING", "BLOCKED_BY_INPUT", "UNKNOWN_CONTRACT", "FAILED"}
        if all(u["state"] in ok for u in upstream_states):
            state = "READY_TO_RUN"
        elif any(u["state"] in bad for u in upstream_states):
            state = "BLOCKED_BY_INPUT"
        else:
            state = "KNOWN_MISSING"
        return self._mk(lid, state,
                        f"no existing result; upstream states = "
                        + ", ".join(u["state"] for u in upstream_states),
                        sample_set, interval_set, candidate_id,
                        upstream=upstream_states)

    @staticmethod
    def _mk(layer_id, state, reason, sample_set, interval_set, candidate_id,
            **extra):
        out = {
            "layer_id": layer_id,
            "state": state,
            "reason": reason,
            "scope": {"sample_set": sample_set,
                      "interval_set": interval_set,
                      "candidate_id": candidate_id},
        }
        out.update(extra)
        return out


# --------------------------------------------------------------------------- #
def _print_layer(res, indent=0):
    pad = "  " * indent
    print(f"{pad}[{res['state']}] {res['layer_id']}: {res['reason']}")
    for u in res.get("upstream", []) or []:
        _print_layer(u, indent + 1)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--layer",   help="layer_id to resolve")
    g.add_argument("--hook",    help="hook_id to resolve (walks all required_layers)")
    g.add_argument("--compose", help="hook_id to compose (emits page_composition_plan_v1)")
    ap.add_argument("--sample-set",   default=None)
    ap.add_argument("--interval-set", default=None)
    ap.add_argument("--candidate",    default=None)
    ap.add_argument("--json", action="store_true", help="emit JSON instead of text")
    ap.add_argument("--registry-root", default=None)
    args = ap.parse_args()

    start = pathlib.Path(args.registry_root) if args.registry_root else pathlib.Path(__file__).parent
    root = _find_root(start)
    r = Resolver(root)

    if args.layer:
        res = r.resolve_layer(args.layer, args.sample_set, args.interval_set, args.candidate)
    elif args.compose:
        res = r.compose_hook(args.compose, args.sample_set, args.interval_set, args.candidate)
    else:
        res = r.resolve_hook(args.hook, args.sample_set, args.interval_set, args.candidate)

    if args.json or args.compose:
        # --compose always emits JSON (the composition plan is JSON-only).
        print(json.dumps(res, indent=2))
        return 0

    if args.layer:
        _print_layer(res)
    else:
        print(f"hook: {res['hook_id']}  state: {res['state']}  page: {res.get('page_id')}")
        for p in res["layers"]:
            _print_layer(p, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
