"""
diversity_endpoint.py — JSON-shim endpoints for the diversity-atlas data slots.

Read-only endpoints that surface the five JSON files the diversity atlas's
shared/data_loader.js consumes:

    GET /api/diversity/slots                          → list of slot names
    GET /api/diversity/{slot}                         → that slot's JSON bytes

Slot → file (under PROJECT_ROOT):

    embedded_tables     data/embedded_tables.json
    texture_metrics     data/texture_metrics.json
    functional_burden   data/functional_burden.json
    roh_gene_overlap    data/roh_gene_overlap.json
    divergence_network  data/divergence_network.json

The four non-bulk slots are optional — when the file is absent the endpoint
returns 404 and the atlas page renders its "data pending" fallback. The
bulk `embedded_tables` slot is required by the legacy renderers; its 404
is a configuration error, not a runtime fallback.

Mount from atlas_server.py:

    from diversity_endpoint import make_diversity_router
    app.include_router(make_diversity_router(_safe_project_path))

`_safe_project_path` is injected so this module doesn't import
atlas_server (avoids a circular import; matches the ld_endpoint /
dosage_bridge sidecar convention).
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Dict

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response


SLOTS: Dict[str, str] = {
    "embedded_tables":    "data/embedded_tables.json",
    "texture_metrics":    "data/texture_metrics.json",
    "functional_burden":  "data/functional_burden.json",
    "roh_gene_overlap":   "data/roh_gene_overlap.json",
    "divergence_network": "data/divergence_network.json",
}


def make_diversity_router(safe_path: Callable[[str], Path]) -> APIRouter:
    """Build the diversity router.

    `safe_path` is the atlas_server `_safe_project_path` callable; it
    resolves a relative path under PROJECT_ROOT and rejects traversal.
    """
    router = APIRouter(prefix="/api/diversity", tags=["diversity"])

    @router.get("/slots")
    async def list_slots() -> Dict[str, list]:
        return {"slots": sorted(SLOTS.keys())}

    @router.get("/{slot}")
    async def get_slot(slot: str) -> Response:
        rel = SLOTS.get(slot)
        if rel is None:
            raise HTTPException(404, f"unknown diversity slot: {slot}")
        target = safe_path(rel)
        if not target.exists():
            raise HTTPException(404, f"diversity slot file missing: {rel}")
        return Response(
            content=target.read_bytes(),
            media_type="application/json",
        )

    return router
