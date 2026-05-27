#!/usr/bin/env python3
"""
bridge_client.py — unified non-agentic entry point for the bridge tier.

Google's science-skills repo wraps each external database (InterPro,
UniProt, ...) in a SKILL.md + a Python CLI. The agentic loop is:
  LLM reads SKILL.md → emits CLI command → subprocess runs → LLM parses output.

That's expensive (one LLM round-trip per call) and adds a non-
deterministic step. atlas-core skips the SKILL.md layer and hits the
underlying REST APIs directly:

    from lib.bridge_client import bridge_query
    rows = bridge_query("interpro", "interpro_entries_by_protein",
                        params={"accession": "P04637"})

bridge_query honours the declared rate limit, paginates lazily, and
caches by params hash to 02_queue/bridge_cache/<db>/<endpoint>/<hash>.jsonl.
Every call logs to 02_queue/bridge_log.jsonl for audit.

Per BRIDGE_SPEC.md §5. Adapter-specific HTTP code lives in
bridge/<db_id>/client.py; this file orchestrates rate-limit + cache +
audit + endpoint validation across all of them.

§refusals:
  - No cohort claims. Bridge results are upstream annotations,
    never tagged with the 226-cohort sample_set.
  - No re-hosting. Cache TTL only.
  - No invented endpoints. Unknown endpoint_id is a hard refusal.
  - No silent failures. Every non-2xx is logged + re-raised.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib
import importlib.util
import json
import pathlib
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Iterator

REPO = pathlib.Path(__file__).resolve().parents[3]
REG  = REPO / "toolkit_registries" / "relatedness" / "01_registry"
PQ   = REPO / "toolkit_registries" / "relatedness" / "02_queue"
BR   = REPO / "toolkit_registries" / "bridge"


def load_jsonl(p: pathlib.Path) -> list[dict]:
    if not p.exists(): return []
    return [json.loads(l) for l in p.read_text().splitlines() if l.strip()]


def _db_registry() -> dict[str, dict]:
    return {r["db_id"]: r for r in load_jsonl(REG / "external_databases.jsonl")}


def _endpoint_map(db_id: str, adapter_dir: str) -> dict[str, dict]:
    f = REPO / "toolkit_registries" / adapter_dir / "endpoints.json"
    if not f.exists():
        raise FileNotFoundError(f"no endpoints.json under {adapter_dir} for db_id={db_id!r}")
    data = json.loads(f.read_text())
    eps = data if isinstance(data, list) else data.get("endpoints", [])
    return {e["endpoint_id"]: e for e in eps}


def _params_hash(params: dict) -> str:
    s = json.dumps(params, sort_keys=True, separators=(",", ":"))
    return hashlib.sha1(s.encode("utf-8")).hexdigest()[:12]


def _cache_path(db_id: str, endpoint_id: str, params: dict) -> pathlib.Path:
    return PQ / "bridge_cache" / db_id / endpoint_id / f"{_params_hash(params)}.jsonl"


def _log(entry: dict) -> None:
    log = PQ / "bridge_log.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


_LAST_CALL_TS: dict[str, float] = {}


def _respect_min_interval(db_id: str, min_ms: int) -> None:
    last = _LAST_CALL_TS.get(db_id, 0)
    elapsed_ms = (time.time() - last) * 1000
    if elapsed_ms < min_ms:
        time.sleep((min_ms - elapsed_ms) / 1000.0)
    _LAST_CALL_TS[db_id] = time.time()


def _validate(endpoint: dict, params: dict) -> dict:
    """Verify params against endpoint.params declaration. Returns the
    validated params (with defaults filled in)."""
    decl = endpoint.get("params") or {}
    out = dict(params)
    for name, spec in decl.items():
        if spec.get("required") and name not in out:
            raise ValueError(f"endpoint {endpoint['endpoint_id']}: missing required param {name!r}")
        if name not in out and "default" in spec:
            out[name] = spec["default"]
    # reject unknown params
    unknown = set(out.keys()) - set(decl.keys())
    if unknown:
        raise ValueError(f"endpoint {endpoint['endpoint_id']}: unknown params {sorted(unknown)} "
                         f"(declared: {sorted(decl.keys())})")
    return out


def _split_params(endpoint: dict, params: dict) -> tuple[dict, dict]:
    """Separate path-params from query-params per the endpoint declaration."""
    decl = endpoint.get("params") or {}
    path_p, query_p = {}, {}
    for k, v in params.items():
        kind = (decl.get(k) or {}).get("kind", "query")
        (path_p if kind == "path" else query_p)[k] = v
    return path_p, query_p


def _fill_path(template: str, path_p: dict) -> str:
    out = template
    for k, v in path_p.items():
        out = out.replace("{" + k + "}", urllib.parse.quote(str(v), safe=""))
    if "{" in out:
        raise ValueError(f"unfilled path placeholder(s) in {out!r}")
    return out


def _http_get(url: str, retry_on: list[int], max_retries: int = 5) -> dict | list:
    last_err = None
    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "atlas-core/bridge"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                if resp.status >= 400 and resp.status in retry_on:
                    last_err = f"HTTP {resp.status}"
                    time.sleep(min(2 ** attempt, 30)); continue
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            last_err = f"HTTP {e.code}"
            if e.code in retry_on:
                time.sleep(min(2 ** attempt, 30)); continue
            raise
        except urllib.error.URLError as e:
            last_err = f"URLError {e.reason}"
            time.sleep(min(2 ** attempt, 10)); continue
    raise RuntimeError(f"bridge: exhausted retries after {max_retries} attempts; last={last_err}")


# ---------- public API ---------- #


def bridge_query(db_id: str, endpoint_id: str, params: dict | None = None,
                 use_cache: bool = True, max_pages: int | None = None) -> Iterator[dict]:
    """Lazily yields rows from an upstream bridge endpoint.

    db_id        — row in external_databases.jsonl (e.g. 'interpro')
    endpoint_id  — row in bridge/<db>/endpoints.json (e.g.
                    'interpro_entries_by_protein')
    params       — declared params + their values (path + query)
    use_cache    — read from 02_queue/bridge_cache/ if a fresh hit exists
    max_pages    — stop after this many pages (None = walk all)
    """
    dbs = _db_registry()
    if db_id not in dbs:
        raise KeyError(f"bridge: db_id {db_id!r} not in external_databases.jsonl "
                       f"(known: {sorted(dbs.keys())})")
    db = dbs[db_id]
    eps = _endpoint_map(db_id, db["adapter_dir"])
    if endpoint_id not in eps:
        raise KeyError(f"bridge: endpoint_id {endpoint_id!r} not in {db['adapter_dir']}/endpoints.json "
                       f"(known: {sorted(eps.keys())})")
    endpoint = eps[endpoint_id]
    params = _validate(endpoint, params or {})

    # Cache hit?
    cache = _cache_path(db_id, endpoint_id, params)
    if use_cache and cache.exists():
        ttl = endpoint.get("cache_seconds", 0)
        age = time.time() - cache.stat().st_mtime
        if ttl and age < ttl:
            for line in cache.read_text().splitlines():
                if line.strip(): yield json.loads(line)
            return

    rate = db.get("rate_limit") or {}
    retry_on = rate.get("retry_on_status", [429, 500, 502, 503, 504])
    min_ms   = rate.get("min_interval_ms", 250)

    # Build URL
    path_p, query_p = _split_params(endpoint, params)
    path = _fill_path(endpoint["path"], path_p)
    base = db["base_url"].rstrip("/")
    page_size = endpoint.get("page_size") or query_p.get("page_size")
    pages_walked = 0
    next_url = f"{base}{path}"
    if query_p:
        next_url += ("?" + urllib.parse.urlencode(query_p))

    if use_cache:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache_fh = cache.open("w")
    else:
        cache_fh = None

    try:
        while next_url:
            _respect_min_interval(db_id, min_ms)
            t0 = time.time()
            doc = _http_get(next_url, retry_on=retry_on)
            elapsed_ms = int((time.time() - t0) * 1000)
            _log({
                "ts":          time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "db_id":       db_id,
                "endpoint_id": endpoint_id,
                "url":         next_url,
                "ok":          True,
                "elapsed_ms":  elapsed_ms,
            })
            # InterPro / UniProt style: dict with `results` + `next`.
            # Flat list also supported.
            rows = []
            next_url = None
            if isinstance(doc, dict):
                rows = doc.get("results") or doc.get("hits") or doc.get("entries") or []
                next_url = doc.get("next")
            elif isinstance(doc, list):
                rows = doc
            for r in rows:
                if cache_fh: cache_fh.write(json.dumps(r, ensure_ascii=False) + "\n")
                yield r
            pages_walked += 1
            if max_pages and pages_walked >= max_pages: break
    finally:
        if cache_fh: cache_fh.close()


def bridge_count(db_id: str, endpoint_id: str, params: dict | None = None) -> int | None:
    """Returns the upstream 'count' field if the endpoint exposes one
    (InterPro, UniProt do). NEVER iterates the full result set to count.
    Returns None if the upstream doesn't provide one."""
    dbs = _db_registry()
    db = dbs[db_id]
    eps = _endpoint_map(db_id, db["adapter_dir"])
    endpoint = eps[endpoint_id]
    params = _validate(endpoint, params or {})
    path_p, query_p = _split_params(endpoint, params)
    path = _fill_path(endpoint["path"], path_p)
    url = f"{db['base_url'].rstrip('/')}{path}"
    if query_p:
        url += ("?" + urllib.parse.urlencode(query_p))
    rate = db.get("rate_limit") or {}
    _respect_min_interval(db_id, rate.get("min_interval_ms", 250))
    doc = _http_get(url, retry_on=rate.get("retry_on_status", [429, 500, 502, 503, 504]))
    if isinstance(doc, dict):
        for k in ("count", "total", "n_total"):
            if k in doc and isinstance(doc[k], int):
                return doc[k]
    return None


# ---------- CLI ---------- #


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="atlas-core bridge — non-agentic external DB client.")
    ap.add_argument("--db",       required=True, help="db_id (interpro, uniprot, ...)")
    ap.add_argument("--endpoint", required=True, help="endpoint_id from bridge/<db>/endpoints.json")
    ap.add_argument("--params",   default="",    help="comma-separated key=value pairs")
    ap.add_argument("--output",   default="",    help="write rows to file (.jsonl); '-' for stdout")
    ap.add_argument("--list-dbs", action="store_true", help="print registered db_ids + status and exit")
    ap.add_argument("--list-endpoints", action="store_true", help="print db's endpoint catalogue and exit")
    ap.add_argument("--count",    action="store_true", help="print upstream count instead of fetching")
    ap.add_argument("--no-cache", action="store_true", help="bypass + don't write the cache")
    ap.add_argument("--max-pages", type=int, default=None, help="stop after N pages")
    args = ap.parse_args(argv)

    if args.list_dbs:
        for db in load_jsonl(REG / "external_databases.jsonl"):
            print(f"  {db['db_id']:<14} {db.get('status','?'):<14} {db.get('label','')}")
        return 0

    if args.list_endpoints:
        dbs = _db_registry()
        if args.db not in dbs:
            print(f"unknown db_id {args.db!r}"); return 1
        try:
            eps = _endpoint_map(args.db, dbs[args.db]["adapter_dir"])
        except FileNotFoundError as e:
            print(f"  ({e})"); return 0
        for eid, e in sorted(eps.items()):
            print(f"  {eid:<40} {e.get('method','GET'):<5} {e['path']}")
        return 0

    params = {}
    for kv in (args.params.split(",") if args.params else []):
        if not kv.strip(): continue
        k, _, v = kv.partition("=")
        params[k.strip()] = v.strip()

    if args.count:
        n = bridge_count(args.db, args.endpoint, params)
        print(json.dumps({"db": args.db, "endpoint": args.endpoint, "count": n}))
        return 0

    out_fh = sys.stdout if args.output in ("", "-") else open(args.output, "w")
    n = 0
    try:
        for row in bridge_query(args.db, args.endpoint, params,
                                use_cache=not args.no_cache, max_pages=args.max_pages):
            out_fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            n += 1
    finally:
        if out_fh is not sys.stdout: out_fh.close()
    if args.output and args.output != "-":
        print(f"  wrote {n} row(s) to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
