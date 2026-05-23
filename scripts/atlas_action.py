#!/usr/bin/env python3
"""atlas_action — stdlib CLI for the atlas-core action pipeline.

Bridges the gap between "the wiring is in" and "I can run analyses from
a terminal" — without needing httpx / requests / a browser.

Five subcommands map 1:1 to the four endpoints in atlas_server.py:

  submit   POST /api/actions               run a manifest, print produced_layers
  log      GET  /api/actions/{action_id}   read the latest action log entry
  list     GET  /api/layers                filter the envelope index
  get      GET  /api/layers/{layer_id}     fetch one envelope
  new-id                                   print a schema-conformant action_id

Examples:

  # Submit a manifest from a file, against the default localhost server
  atlas_action submit -f manifest.json --atlas inversion

  # Pipe a manifest in
  cat manifest.json | atlas_action submit --atlas inversion

  # Skip the network — print the manifest the CLI would send
  atlas_action submit -f manifest.json --dry-run

  # After a submit, fetch the first produced envelope
  atlas_action get fst_windows_main_226_hatchery_C_gar_LG28_abc

  # List the 10 most recent staging envelopes for one cohort
  atlas_action list --layer-type relatedness_result --stage staging --limit 10

  # Read the action log
  atlas_action log act_1715000000000_a4b

Server URL precedence:
  --server <url>  >  $ATLAS_SERVER_URL  >  http://127.0.0.1:8000

This script imports nothing outside stdlib so it can run from the same
WSL Python that runs atlas_server, from Windows Python, or from any
notebook environment.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import string
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Tuple


DEFAULT_SERVER = "http://127.0.0.1:8000"


# =============================================================================
# Tiny HTTP client — stdlib only
# =============================================================================

def _resolve_server(arg: Optional[str]) -> str:
    return (arg or os.environ.get("ATLAS_SERVER_URL") or DEFAULT_SERVER).rstrip("/")


def _request(method: str, url: str, body: Optional[Dict[str, Any]] = None,
             timeout: float = 600.0) -> Tuple[int, bytes]:
    data = None
    headers = {"accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["content-type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        # 4xx/5xx — read the body for the error message
        return e.code, (e.read() or b"")
    except urllib.error.URLError as e:
        raise SystemExit(f"connection error: {e.reason}  ({url})")


def _request_json(method: str, url: str, body: Optional[Dict[str, Any]] = None,
                  timeout: float = 600.0) -> Tuple[int, Any]:
    status, raw = _request(method, url, body, timeout)
    if not raw:
        return status, None
    try:
        return status, json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError:
        return status, raw.decode("utf-8", errors="replace")


# =============================================================================
# Manifest helpers
# =============================================================================

def new_action_id(tag: Optional[str] = None) -> str:
    """Match the action_manifest.schema.json regex: ^act_[A-Za-z0-9_]+$"""
    ms = int(time.time() * 1000)
    suffix = tag or "".join(random.choices(string.ascii_lowercase + string.digits, k=3))
    return f"act_{ms}_{suffix}"


def _read_manifest(path: Optional[str]) -> Dict[str, Any]:
    """Read a manifest from a file path, or from stdin if path is '-' or None."""
    if path is None or path == "-":
        if sys.stdin.isatty():
            raise SystemExit("manifest: no -f given and stdin is a tty (paste JSON or use -f file)")
        raw = sys.stdin.read()
    else:
        with open(path, "r", encoding="utf-8") as fh:
            raw = fh.read()
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise SystemExit(f"manifest: invalid JSON ({e})")


# =============================================================================
# Subcommand implementations
# =============================================================================

def cmd_submit(args: argparse.Namespace) -> int:
    manifest = _read_manifest(args.file)
    if "action_id" not in manifest:
        manifest["action_id"] = new_action_id(args.action_id_tag)
    if args.action_id_set:
        manifest["action_id"] = args.action_id_set

    if args.dry_run:
        json.dump(manifest, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0

    server = _resolve_server(args.server)
    qs = f"?atlas={urllib.parse.quote(args.atlas)}" if args.atlas else ""
    url = f"{server}/api/actions{qs}"
    status, body = _request_json("POST", url, manifest)

    if status >= 400:
        msg = body if isinstance(body, str) else json.dumps(body, indent=2)
        sys.stderr.write(f"HTTP {status} from POST {url}\n{msg}\n")
        return 1

    if args.quiet:
        # One layer_id per line — handy for piping into `xargs atlas_action get`.
        for lid in (body.get("produced_layers") or []):
            print(lid)
        return 0

    if args.json:
        json.dump(body, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0

    # Human-readable default
    print(f"✓ action {body.get('action_id')} → atlas={body.get('atlas_id')}")
    layers = body.get("produced_layers") or []
    print(f"  produced {len(layers)} layer(s):")
    for lid in layers:
        print(f"    {lid}")

    if args.fetch and layers:
        print()
        print("--- envelopes ---")
        for lid in layers:
            status, env = _request_json("GET", f"{server}/api/layers/{urllib.parse.quote(lid)}")
            if status >= 400:
                print(f"  (fetch failed: HTTP {status})  {lid}")
                continue
            print(f"  {lid}:")
            # Show a compact summary of the envelope, not the full payload.
            print(f"    stage:     {env.get('stage')}")
            print(f"    status:    {env.get('status')}")
            print(f"    dataset:   {env.get('dataset_id')}")
            print(f"    type:      {env.get('layer_type')} / {env.get('schema_version')}")
            coord = env.get("coordinate")
            if coord:
                print(f"    coord:     {json.dumps(coord)}")
            payload = env.get("payload") or {}
            if isinstance(payload, dict):
                summary = payload.get("summary")
                if summary is not None:
                    print(f"    summary:   {json.dumps(summary)}")
                else:
                    keys = list(payload.keys())[:5]
                    print(f"    payload:   keys={keys}{'…' if len(payload) > 5 else ''}")
    return 0


def cmd_log(args: argparse.Namespace) -> int:
    server = _resolve_server(args.server)
    url = f"{server}/api/actions/{urllib.parse.quote(args.action_id)}"
    status, body = _request_json("GET", url)
    if status >= 400:
        sys.stderr.write(f"HTTP {status} from GET {url}\n")
        if body:
            sys.stderr.write((body if isinstance(body, str) else json.dumps(body, indent=2)) + "\n")
        return 1
    if args.json:
        json.dump(body, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0
    print(f"action_id:       {body.get('action_id')}")
    print(f"status:          {body.get('status')}")
    print(f"submitted_at:    {body.get('submitted_at')}")
    print(f"started_at:      {body.get('started_at')}")
    print(f"finished_at:     {body.get('finished_at')}")
    print(f"duration_ms:     {body.get('duration_ms')}")
    print(f"produced_layers: {body.get('produced_layers')}")
    err = body.get("error")
    if err:
        print(f"error.kind:      {err.get('kind')}")
        print(f"error.message:   {err.get('message')}")
        if args.verbose:
            print("--- trace ---")
            print(err.get("trace"))
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    server = _resolve_server(args.server)
    qp: Dict[str, str] = {}
    if args.layer_type: qp["layer_type"] = args.layer_type
    if args.dataset_id: qp["dataset_id"] = args.dataset_id
    if args.stage:      qp["stage"] = args.stage
    if args.status:     qp["status"] = args.status
    if args.limit:      qp["limit"] = str(args.limit)
    qs = ("?" + urllib.parse.urlencode(qp)) if qp else ""
    url = f"{server}/api/layers{qs}"
    status, body = _request_json("GET", url)
    if status >= 400:
        sys.stderr.write(f"HTTP {status} from GET {url}\n")
        return 1
    rows = body.get("layers") or []
    if args.quiet:
        for r in rows:
            print(r.get("layer_id", ""))
        return 0
    if args.json:
        json.dump(body, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0
    print(f"{body.get('n', len(rows))} shown (total {body.get('total', '?')})")
    if not rows:
        return 0
    # Compact table
    widths = {"layer_id": 0, "layer_type": 0, "stage": 0, "dataset_id": 0}
    for r in rows:
        for k in widths:
            widths[k] = max(widths[k], len(str(r.get(k, ""))))
    hdr = f"  {'layer_id'.ljust(widths['layer_id'])}  {'layer_type'.ljust(widths['layer_type'])}  {'stage'.ljust(widths['stage'])}  {'dataset_id'.ljust(widths['dataset_id'])}  created_at"
    print(hdr)
    print("  " + "-" * (len(hdr) - 2))
    for r in rows:
        print(
            f"  {str(r.get('layer_id','')).ljust(widths['layer_id'])}  "
            f"{str(r.get('layer_type','')).ljust(widths['layer_type'])}  "
            f"{str(r.get('stage','')).ljust(widths['stage'])}  "
            f"{str(r.get('dataset_id','')).ljust(widths['dataset_id'])}  "
            f"{r.get('created_at','')}"
        )
    return 0


def cmd_get(args: argparse.Namespace) -> int:
    server = _resolve_server(args.server)
    url = f"{server}/api/layers/{urllib.parse.quote(args.layer_id)}"
    status, body = _request_json("GET", url)
    if status >= 400:
        sys.stderr.write(f"HTTP {status} from GET {url}\n")
        if body:
            sys.stderr.write((body if isinstance(body, str) else json.dumps(body, indent=2)) + "\n")
        return 1
    if args.payload_only:
        json.dump((body or {}).get("payload"), sys.stdout, indent=2)
    else:
        json.dump(body, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


def cmd_new_id(args: argparse.Namespace) -> int:
    print(new_action_id(args.tag))
    return 0


# =============================================================================
# Argparse wiring
# =============================================================================

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="atlas_action",
        description="CLI for the atlas-core action pipeline (POST /api/actions et al.).",
    )
    p.add_argument("--server", help=f"server base URL (default: $ATLAS_SERVER_URL or {DEFAULT_SERVER})")
    sub = p.add_subparsers(dest="cmd", required=True)

    # submit
    s = sub.add_parser("submit", help="submit a manifest to POST /api/actions")
    s.add_argument("-f", "--file", help="manifest file (use '-' or omit for stdin)")
    s.add_argument("--atlas", help="?atlas=… query param (overrides manifest.atlas_id + master_config)")
    s.add_argument("--action-id-set", help="override action_id in the manifest")
    s.add_argument("--action-id-tag", help="3-char tag for the auto-generated action_id")
    s.add_argument("--fetch", action="store_true", help="GET each produced envelope after submit")
    s.add_argument("--dry-run", action="store_true", help="print the manifest the CLI would POST, then exit")
    s.add_argument("--json", action="store_true", help="emit raw server response JSON")
    s.add_argument("--quiet", "-q", action="store_true", help="one layer_id per line; suppress headers")
    s.set_defaults(func=cmd_submit)

    # log
    s = sub.add_parser("log", help="GET /api/actions/{action_id}")
    s.add_argument("action_id")
    s.add_argument("--json", action="store_true", help="emit raw JSON")
    s.add_argument("--verbose", "-v", action="store_true", help="show error trace when status=error")
    s.set_defaults(func=cmd_log)

    # list
    s = sub.add_parser("list", help="GET /api/layers (filter the envelope index)")
    s.add_argument("--layer-type")
    s.add_argument("--dataset-id")
    s.add_argument("--stage", choices=["staging", "normalized"])
    s.add_argument("--status", choices=["review", "active", "deprecated", "stale", "superseded"])
    s.add_argument("--limit", type=int, default=50)
    s.add_argument("--json", action="store_true", help="emit raw JSON")
    s.add_argument("--quiet", "-q", action="store_true", help="one layer_id per line")
    s.set_defaults(func=cmd_list)

    # get
    s = sub.add_parser("get", help="GET /api/layers/{layer_id}")
    s.add_argument("layer_id")
    s.add_argument("--payload-only", action="store_true", help="print only payload, not the full envelope")
    s.set_defaults(func=cmd_get)

    # new-id
    s = sub.add_parser("new-id", help="print a schema-conformant action_id and exit")
    s.add_argument("--tag", help="3-char trailing tag (default: random)")
    s.set_defaults(func=cmd_new_id)

    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
