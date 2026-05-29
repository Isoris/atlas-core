#!/usr/bin/env python3
"""
check_derived_objects.py — validate derived_objects.jsonl.

A derived object is a synthesised, addressable subject (an inversion
candidate, an LRR regime, a breakpoint pair) that many analyses FK to.
The rows of each object live in a layer file; this meta-registry only
declares the object KIND + how to harvest its evidence. Per ADDON_SPEC
§1 row G.

Validates:
  1. object_kind unique
  2. schema_version == 'derived_object_v1'
  3. owning_atlas ∈ atlases.jsonl
  4. instance_layer ∈ layer_registry
  5. identity_keys non-empty
  6. each harvest[*].layer ∈ layer_registry
  7. each harvest[*].mode ∈ {spatial_window, chromosome, direct_fk}
  8. mode=spatial_window requires row_chrom / row_start / row_end
  9. mode=direct_fk requires fk
 10. lifecycle_states non-empty

Exit 0 / 1 like the rest of the suite. Wired into smoke_all_stack.
"""
from __future__ import annotations
import json
import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parents[3]
REG  = REPO / "toolkit_registries" / "relatedness" / "01_registry"

ALLOWED_MODES = {"spatial_window", "chromosome", "direct_fk"}


def load_jsonl(p: pathlib.Path) -> list[dict]:
    if not p.exists(): return []
    return [json.loads(l) for l in p.read_text().splitlines() if l.strip()]


def check() -> list[str]:
    errs: list[str] = []
    objs    = load_jsonl(REG / "derived_objects.jsonl")
    atlases = {a["atlas_id"] for a in load_jsonl(REG / "atlases.jsonl")}
    layers  = {L["layer_id"] for L in load_jsonl(REG / "layer_registry.jsonl")}

    seen: set[str] = set()
    for i, o in enumerate(objs, start=1):
        kind = o.get("object_kind", f"<row {i}>")
        if not o.get("object_kind"):
            errs.append(f"{kind}: missing object_kind"); continue
        if o["object_kind"] in seen:
            errs.append(f"{kind}: duplicate object_kind")
        seen.add(o["object_kind"])

        if o.get("schema_version") != "derived_object_v1":
            errs.append(f"{kind}: schema_version != 'derived_object_v1' (got {o.get('schema_version')!r})")
        a = o.get("owning_atlas")
        if a and a not in atlases:
            errs.append(f"{kind}.owning_atlas: {a!r} not in atlases.jsonl")
        il = o.get("instance_layer")
        if not il:
            errs.append(f"{kind}: missing instance_layer")
        elif il not in layers:
            errs.append(f"{kind}.instance_layer: {il!r} not in layer_registry")
        if not (o.get("identity_keys") or []):
            errs.append(f"{kind}: identity_keys must be non-empty")
        if not (o.get("lifecycle_states") or []):
            errs.append(f"{kind}: lifecycle_states must be non-empty")

        for h in (o.get("harvest") or []):
            lyr = h.get("layer")
            if lyr and lyr not in layers:
                errs.append(f"{kind}.harvest: layer {lyr!r} not in layer_registry")
            mode = h.get("mode")
            if mode not in ALLOWED_MODES:
                errs.append(f"{kind}.harvest[{lyr}]: mode {mode!r} not in {sorted(ALLOWED_MODES)}")
            if mode == "spatial_window" and not all(h.get(k) for k in ("row_chrom", "row_start", "row_end")):
                errs.append(f"{kind}.harvest[{lyr}]: mode=spatial_window requires row_chrom / row_start / row_end")
            if mode == "direct_fk" and not h.get("fk"):
                errs.append(f"{kind}.harvest[{lyr}]: mode=direct_fk requires fk")

    return errs


def main(argv: list[str] | None = None) -> int:
    errs = check()
    n = sum(1 for _ in load_jsonl(REG / "derived_objects.jsonl"))
    if errs:
        print(f"FAIL  {len(errs)} problem(s) across {n} derived-object kind(s):")
        for e in errs[:50]:
            print(f"  - {e}")
        return 1
    print(f"OK    {n} derived-object kind(s) clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
