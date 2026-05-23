"""
diversity_endpoint.py — JSON-shim endpoints for the diversity-atlas data slots.

Read-only endpoints that surface the five JSON files the diversity atlas's
shared/data_loader.js consumes:

    GET /api/diversity/slots                          → list of slot names
    GET /api/diversity/{slot}                         → that slot's JSON bytes

Slot → file (under the resolved diversity data dir; see below):

    embedded_tables     embedded_tables.json
    texture_metrics     texture_metrics.json
    functional_burden   functional_burden.json
    roh_gene_overlap    roh_gene_overlap.json
    divergence_network  divergence_network.json

The four non-bulk slots are optional — when the file is absent the endpoint
returns 404 and the atlas page renders its "data pending" fallback. The
bulk `embedded_tables` slot is required by the legacy renderers; its 404
is a configuration error, not a runtime fallback.

Data-dir resolution (2026-05-19, was: only PROJECT_ROOT/data):

    1. ATLAS_DIVERSITY_DATA_DIR env var, if set        ← preferred
    2. PROJECT_ROOT/data via safe_path()                ← fallback
    3. Common dev layout: <workspace>/atlases/../../diversity-atlas/data
       — handled by setting ATLAS_DIVERSITY_DATA_DIR explicitly.

Why the env var: PROJECT_ROOT can only point at ONE directory, but the dev
setup serves a unified workspace while the diversity JSONs live in their
source repo (diversity-atlas/data/). Symlinking is brittle on WSL/DrvFs
(see assemble.sh comments). The env var lets the operator point straight
at the source dir without symlinks or PROJECT_ROOT contortions.

Mount from atlas_server.py:

    from diversity_endpoint import make_diversity_router
    app.include_router(make_diversity_router(_safe_project_path))

`_safe_project_path` is injected so this module doesn't import
atlas_server (avoids a circular import; matches the ld_endpoint /
dosage_bridge sidecar convention). It's used as the FALLBACK; the
env-var path is preferred when set.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Callable, Dict, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response


log = logging.getLogger(__name__)

SLOTS: Dict[str, str] = {
    "embedded_tables":    "embedded_tables.json",
    "texture_metrics":    "texture_metrics.json",
    "functional_burden":  "functional_burden.json",
    "roh_gene_overlap":   "roh_gene_overlap.json",
    "divergence_network": "divergence_network.json",
}


def _resolve_data_dir(
    safe_path: Callable[[str], Path],
) -> Optional[Path]:
    """Resolve the diversity data dir at request time.

    1. ATLAS_DIVERSITY_DATA_DIR (absolute path) wins if set + exists.
    2. Otherwise fall back to PROJECT_ROOT/data via safe_path('data').
    Returns None if neither resolves to an existing directory (caller
    raises 404 with a useful error message).
    """
    env = os.environ.get("ATLAS_DIVERSITY_DATA_DIR")
    if env:
        p = Path(env).expanduser()
        if p.is_dir():
            return p
        log.warning(
            "ATLAS_DIVERSITY_DATA_DIR=%s does not exist; falling back to PROJECT_ROOT/data",
            env,
        )
    # Fallback: PROJECT_ROOT/data via the caller-injected safe_path.
    try:
        p = safe_path("data")
        if p.is_dir():
            return p
    except HTTPException:
        # 403 (path escapes root) or 503 (PROJECT_ROOT unset) — surface
        # as None so the route returns a clear 404 instead of leaking
        # the internal exception.
        pass
    return None


def make_diversity_router(safe_path: Callable[[str], Path]) -> APIRouter:
    """Build the diversity router.

    `safe_path` is the atlas_server `_safe_project_path` callable; used
    only as the fallback when ATLAS_DIVERSITY_DATA_DIR isn't set.
    """
    router = APIRouter(prefix="/api/diversity", tags=["diversity"])

    @router.get("/slots")
    async def list_slots() -> Dict[str, list]:
        return {"slots": sorted(SLOTS.keys())}

    @router.get("/_where")
    async def where_data() -> Dict[str, object]:
        """Diagnostic: report the resolved data dir + env-var source.

        Useful when the user is debugging a 404 / 403: hit
        `/api/diversity/_where` to see what dir the endpoint is reading.
        """
        env = os.environ.get("ATLAS_DIVERSITY_DATA_DIR")
        data_dir = _resolve_data_dir(safe_path)
        return {
            "env_set":  env is not None,
            "env_value": env,
            "resolved": str(data_dir) if data_dir else None,
            "exists":   data_dir is not None and data_dir.is_dir(),
        }

    @router.get("/{slot}")
    async def get_slot(slot: str) -> Response:
        rel = SLOTS.get(slot)
        if rel is None:
            raise HTTPException(404, f"unknown diversity slot: {slot}")
        data_dir = _resolve_data_dir(safe_path)
        if data_dir is None:
            raise HTTPException(404, {
                "error": "diversity_data_dir_unset",
                "fix":   "set ATLAS_DIVERSITY_DATA_DIR=<path/to/diversity-atlas/data> "
                         "OR launch atlas_server with --project-root <diversity-atlas>",
            })
        target = data_dir / rel
        if not target.exists():
            raise HTTPException(404, f"diversity slot file missing: {target}")
        return Response(
            content=target.read_bytes(),
            media_type="application/json",
        )

    return router
