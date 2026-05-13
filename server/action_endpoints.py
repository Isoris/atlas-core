"""
Action endpoints — pure-Python implementation for POST /api/actions,
GET /api/actions/{id}, GET /api/layers, GET /api/layers/{id}.

Contract per toolkit_registries/PIPELINE_FLOW.md:

  POST /api/actions       receive an action_manifest, validate, log,
                          dispatch synchronously, return action_id +
                          status + produced_layers
  GET  /api/actions/{id}  read the latest log entry for that action
  GET  /api/layers        list layer envelopes under <workspace>/layers/
  GET  /api/layers/{id}   return one layer envelope

Filesystem layout the endpoints assume (under PROJECT_ROOT):

  <workspace>/
    registry/
      actions.log.jsonl       append-only log (per PIPELINE_FLOW.md)
    layers/
      <layer_type>/.../<layer_id>.json
    dispatcher.py             optional — per-atlas runner registry

If <workspace>/dispatcher.py is absent the action endpoint runs in
**documentation mode**: it accepts manifests, appends them to the log
with status=success and produced_layers=[], but doesn't execute anything.
This lets atlas-core ship the contract without bundling runners — each
atlas drops in its own dispatcher when it has one.

This module is intentionally framework-agnostic: it does not import
FastAPI. atlas_server.py wires the four decorators around these
functions and translates ValidationError → HTTPException(400).
"""

from __future__ import annotations

import datetime
import importlib.util
import json
import pathlib
import re
import sys
import traceback
from typing import Any, Callable, Dict, List, Optional


# --------------------------------------------------------------------------- #
# Filesystem layout                                                            #
# --------------------------------------------------------------------------- #

REGISTRY_DIR_NAME   = "registry"
LAYERS_DIR_NAME     = "layers"
ACTIONS_LOG_NAME    = "actions.log.jsonl"
DISPATCHER_FILENAME = "dispatcher.py"


def actions_log_path(workspace: pathlib.Path) -> pathlib.Path:
    return workspace / REGISTRY_DIR_NAME / ACTIONS_LOG_NAME


def layers_root(workspace: pathlib.Path) -> pathlib.Path:
    return workspace / LAYERS_DIR_NAME


def dispatcher_path(workspace: pathlib.Path) -> pathlib.Path:
    return workspace / DISPATCHER_FILENAME


# --------------------------------------------------------------------------- #
# Validation (stdlib only — minimal shape check against                        #
# action_manifest_v1.schema.json's required fields + patterns)                 #
# --------------------------------------------------------------------------- #

ACTION_ID_PATTERN  = re.compile(r"^act_[A-Za-z0-9_]+$")
TYPE_PATTERN       = re.compile(r"^[a-z][a-z0-9_]*$")
DATASET_PATTERN    = re.compile(r"^[a-z][a-z0-9_]*$")

REQUIRED_FIELDS = ("action_id", "type", "dataset_id", "runner")


class ValidationError(Exception):
    """Raised when an action manifest fails validation. The server
    translates this to HTTP 400."""


class DuplicateActionError(Exception):
    """Raised when POST /api/actions receives a manifest whose action_id
    is already present in the log. Server translates to HTTP 409."""


def validate_action_manifest(body: Any) -> Dict[str, Any]:
    """Minimal validator. Returns the manifest dict, or raises
    ValidationError. We deliberately don't enforce additionalProperties:
    extra fields are allowed (per the schema's additionalProperties: true)."""
    if not isinstance(body, dict):
        raise ValidationError("manifest must be a JSON object")
    missing = [k for k in REQUIRED_FIELDS if not body.get(k)]
    if missing:
        raise ValidationError(f"missing required field(s): {missing}")
    if not ACTION_ID_PATTERN.match(body["action_id"]):
        raise ValidationError(
            f"action_id '{body['action_id']}' must match {ACTION_ID_PATTERN.pattern}")
    if not TYPE_PATTERN.match(body["type"]):
        raise ValidationError(
            f"type '{body['type']}' must match {TYPE_PATTERN.pattern}")
    if not DATASET_PATTERN.match(body["dataset_id"]):
        raise ValidationError(
            f"dataset_id '{body['dataset_id']}' must match {DATASET_PATTERN.pattern}")
    # expected_outputs, if present, must be a list of {layer_type, schema_version}
    eo = body.get("expected_outputs")
    if eo is not None:
        if not isinstance(eo, list):
            raise ValidationError("expected_outputs must be an array")
        for i, o in enumerate(eo):
            if not isinstance(o, dict):
                raise ValidationError(f"expected_outputs[{i}] must be an object")
            for k in ("layer_type", "schema_version"):
                if not o.get(k):
                    raise ValidationError(
                        f"expected_outputs[{i}].{k} is required")
    return body


# --------------------------------------------------------------------------- #
# Action log (JSONL, append-only)                                              #
# --------------------------------------------------------------------------- #

def now_iso() -> str:
    return datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def append_action_log(workspace: pathlib.Path, entry: Dict[str, Any]) -> None:
    p = actions_log_path(workspace)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, separators=(",", ":")) + "\n")


def read_action_log(workspace: pathlib.Path) -> List[Dict[str, Any]]:
    p = actions_log_path(workspace)
    if not p.exists():
        return []
    out = []
    with p.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def latest_action_entry(workspace: pathlib.Path, action_id: str) -> Optional[Dict[str, Any]]:
    matches = [e for e in read_action_log(workspace) if e.get("action_id") == action_id]
    return matches[-1] if matches else None


# --------------------------------------------------------------------------- #
# Dispatcher discovery                                                         #
# --------------------------------------------------------------------------- #

def find_dispatcher(workspace: pathlib.Path) -> Optional[Callable]:
    """Look for <workspace>/dispatcher.py. If found, import it (under a
    unique module name to avoid sys.modules cache poisoning across calls)
    and return its `dispatch_action` attribute. Else None.

    The expected signature: dispatch_action(manifest, context) -> dict
    where context is {workspace_root: str}.
    """
    p = dispatcher_path(workspace)
    if not p.exists():
        return None
    mod_name = f"atlas_dispatcher_{abs(hash(str(p.resolve()))) & 0xffff_ffff:08x}"
    spec = importlib.util.spec_from_file_location(mod_name, p)
    if spec is None or spec.loader is None:
        return None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return getattr(mod, "dispatch_action", None)


def dispatch(workspace: pathlib.Path, manifest: Dict[str, Any]) -> Dict[str, Any]:
    """Synchronously run the workspace's dispatcher (if any). Returns a
    result dict: { status, produced_layers, error?, duration_ms?, note? }."""
    fn = find_dispatcher(workspace)
    started = datetime.datetime.utcnow()
    if fn is None:
        return {
            "status":          "success",
            "produced_layers": [],
            "note":            f"no {DISPATCHER_FILENAME} in workspace — documentation mode",
            "duration_ms":     0,
        }
    try:
        ctx = {"workspace_root": str(workspace)}
        result = fn(manifest, ctx)
    except Exception as e:
        return {
            "status":          "error",
            "produced_layers": [],
            "error":           {"kind": "runner",
                                "message": str(e),
                                "trace":   traceback.format_exc(limit=8)},
            "duration_ms":     int((datetime.datetime.utcnow() - started).total_seconds() * 1000),
        }
    produced = []
    if isinstance(result, dict):
        produced = list(result.get("produced_layers") or [])
    return {
        "status":          "success",
        "produced_layers": produced,
        "duration_ms":     int((datetime.datetime.utcnow() - started).total_seconds() * 1000),
    }


# --------------------------------------------------------------------------- #
# Layers                                                                       #
# --------------------------------------------------------------------------- #

def _layer_summary(envelope: Dict[str, Any], rel_path: str) -> Dict[str, Any]:
    return {
        "layer_id":       envelope.get("layer_id"),
        "layer_type":     envelope.get("layer_type"),
        "schema_version": envelope.get("schema_version"),
        "stage":          envelope.get("stage"),
        "dataset_id":     envelope.get("dataset_id"),
        "status":         envelope.get("status"),
        "created_at":     envelope.get("created_at"),
        "path":           rel_path,
    }


def list_layers(workspace: pathlib.Path,
                layer_type: Optional[str] = None,
                dataset_id: Optional[str] = None,
                stage: Optional[str] = None,
                limit: int = 200) -> List[Dict[str, Any]]:
    """Walk <workspace>/layers/**/*.json, return summaries. Filters are
    AND'd; empty filter = no filter on that field."""
    root = layers_root(workspace)
    if not root.is_dir():
        return []
    out: List[Dict[str, Any]] = []
    for p in sorted(root.rglob("*.json")):
        try:
            env = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if layer_type and env.get("layer_type") != layer_type: continue
        if dataset_id and env.get("dataset_id") != dataset_id: continue
        if stage      and env.get("stage")      != stage:      continue
        out.append(_layer_summary(env, str(p.relative_to(workspace))))
        if len(out) >= limit:
            break
    return out


def find_layer(workspace: pathlib.Path, layer_id: str) -> Optional[Dict[str, Any]]:
    """Locate one layer envelope by its layer_id. Returns the full envelope
    or None. Walks the layers tree; for big trees an index file at
    <workspace>/registry/layers.registry.json could replace this scan,
    but the scan is cheap enough for the v0 contract."""
    root = layers_root(workspace)
    if not root.is_dir():
        return None
    for p in root.rglob("*.json"):
        try:
            env = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if env.get("layer_id") == layer_id:
            return env
    return None


# --------------------------------------------------------------------------- #
# Orchestration (POST /api/actions handler body)                               #
# --------------------------------------------------------------------------- #

def handle_post_action(workspace: pathlib.Path, body: Any) -> Dict[str, Any]:
    """End-to-end handler for POST /api/actions. Returns the JSON the
    server should respond with. Raises ValidationError on bad shape or
    KeyError-with-message-startswith('duplicate:') on duplicate action_id."""
    manifest = validate_action_manifest(body)

    if latest_action_entry(workspace, manifest["action_id"]):
        # Duplicate action_id. Route handler translates to HTTP 409.
        raise DuplicateActionError(
            f"action_id '{manifest['action_id']}' already exists")

    submitted_at = now_iso()
    append_action_log(workspace, {
        "action_id":    manifest["action_id"],
        "manifest":     manifest,
        "submitted_at": submitted_at,
        "status":       "queued",
    })

    started_at = now_iso()
    append_action_log(workspace, {
        "action_id":    manifest["action_id"],
        "manifest":     manifest,
        "submitted_at": submitted_at,
        "started_at":   started_at,
        "status":       "running",
    })

    result = dispatch(workspace, manifest)
    finished_at = now_iso()

    final_entry = {
        "action_id":       manifest["action_id"],
        "manifest":        manifest,
        "submitted_at":    submitted_at,
        "started_at":      started_at,
        "finished_at":     finished_at,
        "status":          result["status"],
        "produced_layers": result.get("produced_layers", []),
    }
    if "duration_ms" in result:
        final_entry["duration_ms"] = result["duration_ms"]
    if "error" in result:
        final_entry["error"] = result["error"]
    append_action_log(workspace, final_entry)

    response = {
        "action_id":       manifest["action_id"],
        "status":          result["status"],
        "produced_layers": result.get("produced_layers", []),
    }
    if "note" in result:
        response["note"] = result["note"]
    if "error" in result:
        response["error"] = result["error"]
    return response
