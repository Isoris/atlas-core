"""Tests for /api/population/{slot} (server/population_endpoint.py).

Mirrors the pattern in test_diversity_endpoint.py: bootstrap the file
subsystem against a temporary project root, then exercise the population
router via FastAPI's TestClient.

Run from the server/ directory:
    python -m unittest test_population_endpoint -v
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from fastapi.testclient import TestClient

import atlas_server as ps
from population_endpoint import (
    NGSADMIX_K_MAX,
    NGSADMIX_K_MIN,
    NGSADMIX_Q_TEMPLATE,
    SLOTS,
    make_population_router,
)


# The population router is not mounted by atlas_server.py yet (per-session
# constraint: don't touch atlas_server.py). Tests mount it manually onto a
# fresh TestClient. Once the include_router line lands in atlas_server.py,
# this helper can be replaced by a plain TestClient(ps.app).
def _fresh_client(project_root: Path) -> TestClient:
    ps.PROJECT_ROOT = None
    ps.ENGINES = None
    ps.CACHE = None
    ps.SAMPLES = None
    ps._bootstrap_file(project_root)
    # Idempotently mount the router. FastAPI doesn't dedupe routes by
    # path, so we check whether /api/population/slots is already routed.
    already_mounted = any(
        getattr(r, "path", None) == "/api/population/slots"
        for r in ps.app.router.routes
    )
    if not already_mounted:
        ps.app.include_router(make_population_router(ps._safe_project_path))
    return TestClient(ps.app)


def _seed_slot(project_root: Path, slot: str, body: dict) -> Path:
    rel = SLOTS[slot]
    target = project_root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(body), encoding="utf-8")
    return target


def _seed_ngsadmix_q(project_root: Path, k: int, body: dict) -> Path:
    rel = NGSADMIX_Q_TEMPLATE.format(k=k)
    target = project_root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(body), encoding="utf-8")
    return target


class TestPopulationEndpoint(unittest.TestCase):

    def test_slots_lists_all_eight(self):
        with tempfile.TemporaryDirectory() as td:
            client = _fresh_client(Path(td))
            r = client.get("/api/population/slots")
            self.assertEqual(r.status_code, 200)
            body = r.json()
            self.assertEqual(
                body["slots"],
                sorted([
                    "per_sample_stats",
                    "family_clusters",
                    "inversion_carriers",
                    "marker_controls",
                    "hatchery_health_cohorts",
                    "pcangsd_pca",
                    "ngsrelate_kinship",
                    "module_qc_summary",
                ]),
            )
            self.assertEqual(body["templated_slots"], ["ngsadmix_q"])

    def test_get_existing_slot_returns_file_bytes(self):
        with tempfile.TemporaryDirectory() as td:
            project = Path(td)
            payload = {
                "n_samples": 226,
                "samples": [{"sample": "S001", "F_ROH": 0.04, "het": 0.0021}],
            }
            _seed_slot(project, "per_sample_stats", payload)
            client = _fresh_client(project)

            r = client.get("/api/population/per_sample_stats")
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.headers["content-type"], "application/json")
            self.assertEqual(r.json(), payload)

    def test_missing_file_returns_404(self):
        with tempfile.TemporaryDirectory() as td:
            client = _fresh_client(Path(td))
            r = client.get("/api/population/family_clusters")
            self.assertEqual(r.status_code, 404)
            self.assertIn("missing", r.json()["detail"])

    def test_unknown_slot_returns_404(self):
        with tempfile.TemporaryDirectory() as td:
            client = _fresh_client(Path(td))
            r = client.get("/api/population/not_a_real_slot")
            self.assertEqual(r.status_code, 404)
            self.assertIn("unknown population slot", r.json()["detail"])

    def test_each_slot_round_trips(self):
        """All eight declared slots serve the file they point at."""
        with tempfile.TemporaryDirectory() as td:
            project = Path(td)
            for slot in SLOTS:
                _seed_slot(project, slot, {"_slot": slot})
            client = _fresh_client(project)
            for slot in SLOTS:
                r = client.get(f"/api/population/{slot}")
                self.assertEqual(r.status_code, 200, msg=slot)
                self.assertEqual(r.json(), {"_slot": slot}, msg=slot)

    def test_ngsadmix_q_round_trips_at_canonical_k(self):
        with tempfile.TemporaryDirectory() as td:
            project = Path(td)
            payload = {"K": 8, "samples": ["S001"], "Q": [[0.1] * 8]}
            _seed_ngsadmix_q(project, 8, payload)
            client = _fresh_client(project)
            r = client.get("/api/population/ngsadmix/q/8")
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.json(), payload)

    def test_ngsadmix_q_missing_returns_404(self):
        with tempfile.TemporaryDirectory() as td:
            client = _fresh_client(Path(td))
            r = client.get(f"/api/population/ngsadmix/q/{NGSADMIX_K_MIN}")
            self.assertEqual(r.status_code, 404)
            self.assertIn("ngsadmix Q file missing", r.json()["detail"])

    def test_ngsadmix_q_out_of_range_returns_400(self):
        with tempfile.TemporaryDirectory() as td:
            client = _fresh_client(Path(td))
            for k in (NGSADMIX_K_MIN - 1, NGSADMIX_K_MAX + 1, 0):
                r = client.get(f"/api/population/ngsadmix/q/{k}")
                self.assertEqual(r.status_code, 400, msg=f"k={k}")
                self.assertIn("out of range", r.json()["detail"])

    def test_endpoint_503_when_subsystem_disabled(self):
        """No project root → /file subsystem is down → safe_path raises 503."""
        ps.PROJECT_ROOT = None
        # Manually mount the router onto the fresh app state so the test
        # exercises the 503 path without going through _fresh_client (which
        # bootstraps PROJECT_ROOT). Re-use the existing app; the router is
        # idempotent across tests.
        already_mounted = any(
            getattr(r, "path", None) == "/api/population/slots"
            for r in ps.app.router.routes
        )
        if not already_mounted:
            ps.app.include_router(make_population_router(ps._safe_project_path))
        client = TestClient(ps.app)
        r = client.get("/api/population/per_sample_stats")
        self.assertEqual(r.status_code, 503)


if __name__ == "__main__":
    unittest.main(verbosity=2)
