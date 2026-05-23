"""
population_endpoint.py — JSON-shim endpoints for the population-atlas data slots.

Read-only endpoints that surface the cohort-level JSON files the population
atlas's pages consume:

    GET /api/population/slots                          → list of slot names
    GET /api/population/{slot}                         → that slot's JSON bytes
    GET /api/population/ngsadmix/q/{k}                 → NGSadmix Q matrix at K=<k>

Slot → file (under PROJECT_ROOT):

    per_sample_stats           data/per_sample_stats.json
    family_clusters            data/family_clusters.json
    inversion_carriers         data/inversion_carriers.json
    marker_controls            data/marker_controls.json
    hatchery_health_cohorts    data/hatchery_health.json
    pcangsd_pca                data/pcangsd/pca.json
    ngsrelate_kinship          data/ngsrelate/kinship_matrix.json
    module_qc_summary          data/qc/module_qc_summary.json

The K-templated NGSadmix slot is served separately because the K value is
part of the URL: GET /api/population/ngsadmix/q/8 reads
data/ngsadmix/Q_K8.json. K must be an integer in [2, 12] (NGSadmix sweep
range; values outside that range 400 rather than 404 to surface caller
mistakes).

All non-bulk slots are optional — when the file is absent the endpoint
returns 404 and the atlas page renders its scaffold "data pending"
message. This is mirrored exactly from diversity_endpoint.py: the
contract is "either the file is there and we serve it, or 404 and the
caller falls back."

Mount from atlas_server.py:

    from population_endpoint import make_population_router
    app.include_router(make_population_router(_safe_project_path))

`_safe_project_path` is injected so this module doesn't import
atlas_server (avoids a circular import; matches the diversity_endpoint /
ld_endpoint / dosage_bridge sidecar convention).
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Dict

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response


# =============================================================================
# Slot inventory — mirrors atlases/population/registries/data/layers.registry.json
# =============================================================================

SLOTS: Dict[str, str] = {
    "per_sample_stats":        "data/per_sample_stats.json",
    "family_clusters":         "data/family_clusters.json",
    "inversion_carriers":      "data/inversion_carriers.json",
    "marker_controls":         "data/marker_controls.json",
    "hatchery_health_cohorts": "data/hatchery_health.json",
    "pcangsd_pca":             "data/pcangsd/pca.json",
    "ngsrelate_kinship":       "data/ngsrelate/kinship_matrix.json",
    "module_qc_summary":       "data/qc/module_qc_summary.json",
}

# K-templated slot — the actual file path depends on K.
NGSADMIX_Q_TEMPLATE = "data/ngsadmix/Q_K{k}.json"
NGSADMIX_K_MIN = 2
NGSADMIX_K_MAX = 12


def make_population_router(safe_path: Callable[[str], Path]) -> APIRouter:
    """Build the population router.

    `safe_path` is the atlas_server `_safe_project_path` callable; it
    resolves a relative path under PROJECT_ROOT and rejects traversal.
    """
    router = APIRouter(prefix="/api/population", tags=["population"])

    @router.get("/slots")
    async def list_slots() -> Dict[str, list]:
        return {
            "slots": sorted(SLOTS.keys()),
            "templated_slots": ["ngsadmix_q"],
        }

    @router.get("/ngsadmix/q/{k}")
    async def get_ngsadmix_q(k: int) -> Response:
        if k < NGSADMIX_K_MIN or k > NGSADMIX_K_MAX:
            raise HTTPException(
                400,
                f"K={k} out of range [{NGSADMIX_K_MIN}, {NGSADMIX_K_MAX}]",
            )
        rel = NGSADMIX_Q_TEMPLATE.format(k=k)
        target = safe_path(rel)
        if not target.exists():
            raise HTTPException(404, f"ngsadmix Q file missing: {rel}")
        return Response(
            content=target.read_bytes(),
            media_type="application/json",
        )

    @router.get("/{slot}")
    async def get_slot(slot: str) -> Response:
        rel = SLOTS.get(slot)
        if rel is None:
            raise HTTPException(404, f"unknown population slot: {slot}")
        target = safe_path(rel)
        if not target.exists():
            raise HTTPException(404, f"population slot file missing: {rel}")
        return Response(
            content=target.read_bytes(),
            media_type="application/json",
        )

    return router
