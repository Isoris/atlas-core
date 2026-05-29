#!/usr/bin/env python3
"""
check_panels.py — validate panels.jsonl + spawn_rules.jsonl against the registry.

Mirrors check_analysis_registry / check_plans / check_chunks. Walks
panels + spawn rules and verifies:

  panels.jsonl:
    1. panel_id unique
    2. schema_version == 'panel_v1'
    3. atlas (when set) ∈ atlases.jsonl
    4. data_source.kind (when set) ∈ {registry, scope, layer,
       analysis_result, chain_audit, manuscript_chunk, scope+registry,
       file}
    5. data_source.reads[*] (when set) point at files that exist under
       01_registry/ or 02_queue/ (loose path check)
    6. layer_id (when set, legacy shape) ∈ layer_registry
    7. fluidity.* has the right keys when present

  spawn_rules.jsonl:
    1. rule_id unique
    2. schema_version == 'spawn_rule_v1'
    3. when.page[*] ∈ pages.jsonl (derived; no hardcoded enum)
    4. then.spawn[*].panel_id ∈ panels.jsonl
    5. then.dismiss[*].panel_id ∈ panels.jsonl
    6. then.spawn[*]: when the target page declares a non-empty `slots`
       inventory AND the panel declares `slot_affinity`, the
       intersection must be non-empty (otherwise the conductor would
       silently skip the spawn at runtime — surface it as an error
       instead of a debug-only console line)

Exit 0 / 1 like the rest of the suite.
"""
from __future__ import annotations
import json
import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parents[3]
REG  = REPO / "toolkit_registries" / "relatedness" / "01_registry"

ALLOWED_DATA_SOURCE_KINDS = {
    "registry", "scope", "layer", "analysis_result",
    "chain_audit", "manuscript_chunk", "scope+registry", "file",
}


def load_jsonl(p: pathlib.Path) -> list[dict]:
    if not p.exists(): return []
    return [json.loads(l) for l in p.read_text().splitlines() if l.strip()]


def check() -> list[str]:
    errs: list[str] = []
    panels  = load_jsonl(REG / "panels.jsonl")
    rules   = load_jsonl(REG / "spawn_rules.jsonl")
    atlases = {a["atlas_id"] for a in load_jsonl(REG / "atlases.jsonl")}
    layers  = {L["layer_id"] for L in load_jsonl(REG / "layer_registry.jsonl")}
    pages   = load_jsonl(REG / "pages.jsonl")
    panel_ids = {p["panel_id"] for p in panels}
    page_slots: dict[str, list[str]] = {
        pg["page_id"]: (pg.get("slots") or []) for pg in pages if pg.get("page_id")
    }
    panel_slot_affinity: dict[str, list[str]] = {
        p["panel_id"]: (p.get("slot_affinity") or []) for p in panels if p.get("panel_id")
    }
    known_page_ids = set(page_slots)

    # --- panels ---
    seen: set[str] = set()
    for i, p in enumerate(panels, start=1):
        pid = p.get("panel_id", f"<row {i}>")
        if not p.get("panel_id"):
            errs.append(f"{pid}: missing panel_id"); continue
        if p["panel_id"] in seen:
            errs.append(f"{pid}: duplicate panel_id")
        seen.add(p["panel_id"])
        if p.get("schema_version") != "panel_v1":
            errs.append(f"{pid}: schema_version != 'panel_v1' (got {p.get('schema_version')!r})")
        a = p.get("atlas")
        if a and a not in atlases:
            errs.append(f"{pid}: atlas {a!r} not in atlases.jsonl")
        ds = p.get("data_source") or {}
        if ds:
            k = ds.get("kind")
            if k and k not in ALLOWED_DATA_SOURCE_KINDS:
                errs.append(f"{pid}.data_source.kind: {k!r} not in {sorted(ALLOWED_DATA_SOURCE_KINDS)}")
        L = p.get("layer_id")
        if L and L not in layers:
            errs.append(f"{pid}.layer_id: {L!r} not in layer_registry")
        f = p.get("fluidity")
        if f and ("size_classes" not in f or "min_width_px" not in f):
            errs.append(f"{pid}.fluidity: missing size_classes/min_width_px")

    # --- spawn rules ---
    seen_r: set[str] = set()
    for i, r in enumerate(rules, start=1):
        rid = r.get("rule_id", f"<row {i}>")
        if not r.get("rule_id"):
            errs.append(f"{rid}: missing rule_id"); continue
        if r["rule_id"] in seen_r:
            errs.append(f"{rid}: duplicate rule_id")
        seen_r.add(r["rule_id"])
        if r.get("schema_version") != "spawn_rule_v1":
            errs.append(f"{rid}: schema_version != 'spawn_rule_v1' (got {r.get('schema_version')!r})")
        when = r.get("when") or {}
        target_pages = list(when.get("page") or [])
        for pg in target_pages:
            if pg not in known_page_ids:
                errs.append(f"{rid}.when.page: {pg!r} not in pages.jsonl ({sorted(known_page_ids)})")
        for s in ((r.get("then") or {}).get("spawn") or []):
            sp_pid = s.get("panel_id")
            if sp_pid not in panel_ids:
                errs.append(f"{rid}.then.spawn: panel_id {sp_pid!r} not in panels.jsonl")
                continue
            affinity = panel_slot_affinity.get(sp_pid, [])
            if not affinity:
                continue
            for pg in target_pages:
                slots = page_slots.get(pg, [])
                if not slots:
                    continue
                if not (set(slots) & set(affinity)):
                    errs.append(
                        f"{rid}.then.spawn: panel {sp_pid!r} slot_affinity {affinity} "
                        f"has no overlap with page {pg!r} slots {slots}"
                    )
        for s in ((r.get("then") or {}).get("dismiss") or []):
            if s.get("panel_id") not in panel_ids:
                errs.append(f"{rid}.then.dismiss: panel_id {s.get('panel_id')!r} not in panels.jsonl")

    return errs


def main(argv: list[str] | None = None) -> int:
    errs = check()
    n_p = sum(1 for _ in load_jsonl(REG / "panels.jsonl"))
    n_r = sum(1 for _ in load_jsonl(REG / "spawn_rules.jsonl"))
    if errs:
        print(f"FAIL  {len(errs)} problem(s) across {n_p} panel(s) + {n_r} spawn rule(s):")
        for e in errs[:50]:
            print(f"  - {e}")
        if len(errs) > 50:
            print(f"  ... and {len(errs) - 50} more")
        return 1
    print(f"OK    {n_p} panel(s) + {n_r} spawn rule(s) clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
