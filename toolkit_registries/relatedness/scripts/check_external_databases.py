#!/usr/bin/env python3
"""
check_external_databases.py — validate the bridge registry.

Mirrors check_analysis_registry / check_plans / check_chunks / check_panels.
Walks external_databases.jsonl + each adapter's endpoints.json and verifies:

  external_databases.jsonl:
    1. db_id unique
    2. schema_version == 'external_db_v1'
    3. base_url starts with https://
    4. adapter_dir points at a directory under toolkit_registries/bridge/
    5. for status='experimental' or 'active', adapter_dir contains:
         endpoints.json + LICENSE_NOTICE.md
    6. rate_limit fields are sane (positive ints; retry_on_status is a list)

  bridge/<db>/endpoints.json:
    1. schema_version == bridge_endpoint_v1 OR endpoints[*].schema_version
       == bridge_endpoint_v1
    2. endpoint_id unique within the file
    3. method ∈ {GET, POST}
    4. path is set, params.*.kind ∈ {path, query, header}
    5. every {placeholder} in path has a corresponding required path-param
    6. returns_layer is set
    7. cache_seconds is non-negative int (when set)
"""
from __future__ import annotations
import json
import pathlib
import re
import sys

REPO = pathlib.Path(__file__).resolve().parents[3]
REG  = REPO / "toolkit_registries" / "relatedness" / "01_registry"
BR   = REPO / "toolkit_registries"

ALLOWED_METHODS = {"GET", "POST"}
ALLOWED_KINDS   = {"path", "query", "header"}
ALLOWED_STATUS  = {"active", "experimental", "planned", "deprecated"}


def load_jsonl(p: pathlib.Path) -> list[dict]:
    if not p.exists(): return []
    return [json.loads(l) for l in p.read_text().splitlines() if l.strip()]


def check_endpoints(adapter_dir: str) -> list[str]:
    errs: list[str] = []
    f = BR / adapter_dir / "endpoints.json"
    if not f.exists():
        return errs   # caller already flagged missing endpoints.json when required
    try:
        doc = json.loads(f.read_text())
    except Exception as e:
        return [f"{adapter_dir}/endpoints.json: parse failed: {e}"]
    eps = doc if isinstance(doc, list) else doc.get("endpoints", [])
    seen = set()
    for e in eps:
        eid = e.get("endpoint_id") or "<missing endpoint_id>"
        if eid in seen:
            errs.append(f"{adapter_dir}/endpoints.json: duplicate endpoint_id {eid!r}")
        seen.add(eid)
        sv = e.get("schema_version", doc.get("schema_version") if isinstance(doc, dict) else None)
        if sv != "bridge_endpoint_v1":
            errs.append(f"{adapter_dir}:{eid}: schema_version != 'bridge_endpoint_v1' (got {sv!r})")
        m = e.get("method", "GET")
        if m not in ALLOWED_METHODS:
            errs.append(f"{adapter_dir}:{eid}: method {m!r} not in {sorted(ALLOWED_METHODS)}")
        path = e.get("path")
        if not path:
            errs.append(f"{adapter_dir}:{eid}: missing path")
        if not e.get("returns_layer"):
            errs.append(f"{adapter_dir}:{eid}: missing returns_layer")
        if "cache_seconds" in e and (not isinstance(e["cache_seconds"], int) or e["cache_seconds"] < 0):
            errs.append(f"{adapter_dir}:{eid}: cache_seconds must be non-negative int")
        params = e.get("params") or {}
        for name, spec in params.items():
            kind = (spec or {}).get("kind", "query")
            if kind not in ALLOWED_KINDS:
                errs.append(f"{adapter_dir}:{eid}.params.{name}: kind {kind!r} not in {sorted(ALLOWED_KINDS)}")
        # path placeholder ↔ path-param coverage
        placeholders = set(re.findall(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}", path or ""))
        path_params  = {n for n, s in params.items() if (s or {}).get("kind") == "path"}
        miss = placeholders - path_params
        extra = path_params - placeholders
        if miss:
            errs.append(f"{adapter_dir}:{eid}: path placeholder(s) {sorted(miss)} have no path-param declaration")
        if extra:
            errs.append(f"{adapter_dir}:{eid}: path-param(s) {sorted(extra)} not referenced in path {path!r}")
    return errs


def check() -> list[str]:
    errs: list[str] = []
    dbs = load_jsonl(REG / "external_databases.jsonl")
    if not dbs:
        return errs   # no registry → nothing to check
    seen = set()
    for db in dbs:
        did = db.get("db_id") or "<missing db_id>"
        if did in seen:
            errs.append(f"{did}: duplicate db_id")
        seen.add(did)
        sv = db.get("schema_version")
        if sv != "external_db_v1":
            errs.append(f"{did}: schema_version != 'external_db_v1' (got {sv!r})")
        base = db.get("base_url", "")
        if not base.startswith("https://"):
            errs.append(f"{did}: base_url must start with https:// (got {base!r})")
        ad = db.get("adapter_dir", "")
        if not ad.startswith("bridge/"):
            errs.append(f"{did}: adapter_dir {ad!r} must start with 'bridge/'")
        status = db.get("status", "")
        if status not in ALLOWED_STATUS:
            errs.append(f"{did}: status {status!r} not in {sorted(ALLOWED_STATUS)}")
        adir = BR / ad
        if status in ("active", "experimental"):
            if not (adir / "endpoints.json").exists():
                errs.append(f"{did}: status={status} but {ad}/endpoints.json missing")
            if not (adir / "LICENSE_NOTICE.md").exists():
                errs.append(f"{did}: status={status} but {ad}/LICENSE_NOTICE.md missing")
        rl = db.get("rate_limit") or {}
        if rl:
            if not isinstance(rl.get("max_concurrent", 1), int) or rl.get("max_concurrent", 1) < 1:
                errs.append(f"{did}.rate_limit.max_concurrent: must be int ≥ 1")
            if not isinstance(rl.get("min_interval_ms", 0), int) or rl.get("min_interval_ms", 0) < 0:
                errs.append(f"{did}.rate_limit.min_interval_ms: must be non-negative int")
            if not isinstance(rl.get("retry_on_status", []), list):
                errs.append(f"{did}.rate_limit.retry_on_status: must be list")
        # endpoint-level checks
        if (adir / "endpoints.json").exists():
            errs.extend(check_endpoints(ad))
    return errs


def main(argv: list[str] | None = None) -> int:
    errs = check()
    dbs = load_jsonl(REG / "external_databases.jsonl")
    if errs:
        print(f"FAIL  {len(errs)} problem(s) across {len(dbs)} external database(s):")
        for e in errs[:50]:
            print(f"  - {e}")
        if len(errs) > 50:
            print(f"  ... and {len(errs) - 50} more")
        return 1
    print(f"OK    {len(dbs)} external database(s) clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
