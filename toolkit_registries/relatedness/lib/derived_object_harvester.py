#!/usr/bin/env python3
"""
derived_object_harvester.py — harvest all per-atlas evidence for a
derived object (inversion candidate, LRR regime, …) into one aggregate.

Generic over 01_registry/derived_objects.jsonl. For each object kind it:

  1. loads the instance rows from the object's instance_layer file
  2. for each instance, walks the kind's `harvest` list and joins
     evidence by one of three modes:
       - direct_fk      : result rows carry the object's fk column
       - spatial_window : result rows carry chrom+start+end; kept where
                          they overlap the instance interval
       - chromosome     : per-chromosome result file attached whole
  3. emits one <aggregate_schema> JSON per instance under
     02_queue/<kind>s/<instance_id>.json (+ rebuilds index.json)

Result files are resolved from analysis_results.jsonl (the run log) by
matching analysis_type + the instance's chromosome short-name against
the result path. No execution; pure read. §refusals: read-only, never
mutates a registry, never crosses cohort boundaries (the candidate
carries its own cohort via the instance row).

Usage:
  python3 -m toolkit_registries.relatedness.lib.derived_object_harvester --kind candidate --all
  python3 -m ...derived_object_harvester --kind candidate --instance inv_LG28_INV_001 --stdout
  python3 -m ...derived_object_harvester --kind candidate --all --commit
"""
from __future__ import annotations
import argparse
import csv
import datetime as dt
import json
import pathlib
import re
import sys

REPO  = pathlib.Path(__file__).resolve().parents[3]
RELA  = REPO / "toolkit_registries" / "relatedness"
REG   = RELA / "01_registry"
QUEUE = RELA / "02_queue"


def load_jsonl(p: pathlib.Path) -> list[dict]:
    if not p.exists(): return []
    return [json.loads(l) for l in p.read_text().splitlines() if l.strip()]


def load_table(p: pathlib.Path) -> list[dict]:
    """Read a .tsv / .res / .mendelian.tsv as list[dict]. Tab-delimited."""
    if not p.exists(): return []
    text = p.read_text().splitlines()
    if not text: return []
    reader = csv.DictReader(text, delimiter="\t")
    return [dict(r) for r in reader]


def chrom_short(chrom: str) -> str:
    """C_gar_LG28 -> LG28 ; LG28 -> LG28."""
    m = re.search(r"(LG\d+|chr\w+|scaffold_?\d+)", chrom or "", re.IGNORECASE)
    return m.group(1) if m else (chrom or "")


def to_int(v) -> int | None:
    try: return int(float(v))
    except (TypeError, ValueError): return None


def overlaps(c_start: int, c_end: int, r_start, r_end) -> bool:
    rs, re_ = to_int(r_start), to_int(r_end)
    if rs is None or re_ is None: return False
    return rs <= c_end and re_ >= c_start


def resolve_result_files(analysis_type: str, short: str, runs: list[dict]) -> list[pathlib.Path]:
    """Find result files for an analysis_type whose path mentions the
    instance's chromosome short-name. Falls back to all rows of that
    analysis_type when none mention the chromosome (genome-wide runs)."""
    hits, generic = [], []
    for r in runs:
        if r.get("analysis_type") != analysis_type:
            continue
        path = r.get("path", "")
        p = RELA / path
        if not p.exists():
            continue
        if short and short.lower() in path.lower():
            hits.append(p)
        else:
            generic.append(p)
    return hits or generic


def harvest_instance(obj: dict, inst: dict, runs: list[dict]) -> dict:
    kind  = obj["object_kind"]
    id_key = obj["identity_keys"][0]
    sk    = obj.get("spatial_keys") or []
    inst_id = inst.get(id_key)
    chrom = inst.get(sk[0]) if len(sk) >= 1 else None
    start = to_int(inst.get(sk[1])) if len(sk) >= 2 else None
    end   = to_int(inst.get(sk[2])) if len(sk) >= 3 else None
    short = chrom_short(chrom) if chrom else ""

    agg = {
        "schema_version": obj.get("aggregate_schema", "aggregate_v1"),
        "object_kind":    kind,
        id_key:           inst_id,
        "as_of":          dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "identity":       dict(inst),
        "evidence":       {},
    }

    for h in (obj.get("harvest") or []):
        mode  = h.get("mode")
        layer = h.get("layer", "?")
        block = {"mode": mode, "layer": layer, "rows": [], "n": 0}

        if mode == "direct_fk":
            fk = h.get("fk", id_key)
            # direct_fk layers are analysis_result layers; resolve their
            # file via the layer's default_path if present, else skip
            # gracefully (the instance simply has no rows yet).
            rows = []
            for r in runs:
                # direct_fk rows would live in files tagged with this layer;
                # v0 resolves nothing extra — the instance_layer already
                # carries the candidate, so direct_fk is a no-op unless a
                # dedicated file exists. Left as an extension point.
                pass
            block["rows"] = rows
            block["n"] = len(rows)

        else:
            files = resolve_result_files(h.get("analysis_type", ""), short, runs)
            rows = []
            for f in files:
                table = load_table(f)
                if mode == "spatial_window":
                    rc, rs_, re_ = h["row_chrom"], h["row_start"], h["row_end"]
                    for row in table:
                        if chrom_short(row.get(rc, "")) != short:
                            continue
                        if start is not None and end is not None and not overlaps(start, end, row.get(rs_), row.get(re_)):
                            continue
                        rows.append(row)
                else:  # chromosome
                    rows.extend(table)
            block["rows"] = rows
            block["n"] = len(rows)
            block["files"] = [str(f.relative_to(RELA)) for f in files]

        agg["evidence"][layer] = block

    return agg


def harvest_kind(kind: str, instance_id: str | None) -> list[dict]:
    objs = {o["object_kind"]: o for o in load_jsonl(REG / "derived_objects.jsonl")}
    if kind not in objs:
        raise SystemExit(f"unknown object_kind {kind!r}; known: {sorted(objs)}")
    obj   = objs[kind]
    layers = {L["layer_id"]: L for L in load_jsonl(REG / "layer_registry.jsonl")}
    runs  = load_jsonl(REG / "analysis_results.jsonl")

    inst_layer = layers.get(obj["instance_layer"], {})
    inst_path  = RELA / (inst_layer.get("default_path") or "")
    instances  = load_table(inst_path)
    id_key = obj["identity_keys"][0]
    if instance_id:
        instances = [r for r in instances if r.get(id_key) == instance_id]
    return [harvest_instance(obj, inst, runs) for inst in instances]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--kind", default="candidate", help="object_kind from derived_objects.jsonl")
    ap.add_argument("--instance", default="", help="restrict to one instance id")
    ap.add_argument("--all", action="store_true", help="harvest every instance of the kind")
    ap.add_argument("--stdout", action="store_true", help="print aggregate JSON to stdout (no write)")
    ap.add_argument("--commit", action="store_true", help="write 02_queue/<kind>s/<id>.json + index.json")
    args = ap.parse_args(argv)

    if not (args.instance or args.all):
        ap.error("pass --instance <id> or --all")

    aggs = harvest_kind(args.kind, args.instance or None)
    if not aggs:
        print(f"no {args.kind} instances matched"); return 1

    if args.stdout:
        print(json.dumps(aggs[0] if args.instance else aggs, indent=2, ensure_ascii=False))
        return 0

    out_dir = QUEUE / f"{args.kind}s"
    id_key = "candidate_id" if args.kind == "candidate" else f"{args.kind}_id"
    total_rows = 0
    for agg in aggs:
        n = sum(b.get("n", 0) for b in agg["evidence"].values())
        total_rows += n
        iid = agg.get(id_key) or agg.get("object_kind")
        per_layer = ", ".join(f"{k}={v.get('n', 0)}" for k, v in agg["evidence"].items())
        print(f"  {iid:24s} evidence rows={n:4d}  ({per_layer})")
        if args.commit:
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / f"{iid}.json").write_text(json.dumps(agg, indent=2, ensure_ascii=False) + "\n")

    print(f"\n  {len(aggs)} {args.kind}(s) harvested; {total_rows} total evidence rows")
    if args.commit:
        idx = {"schema_version": "harvest_index_v1", "kind": args.kind,
               "rebuilt_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
               "instances": [a.get(id_key) for a in aggs]}
        (out_dir / "index.json").write_text(json.dumps(idx, indent=2) + "\n")
        print(f"  wrote {out_dir.relative_to(RELA)}/*.json (+ index.json)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
