"""Tests for /api/diversity/{slot} (server/diversity_endpoint.py).

Mirrors the pattern in test_file_compute_endpoints.py: bootstrap the
file subsystem against a temporary project root, then exercise the
diversity router via FastAPI's TestClient.

Run from the server/ directory:
    python -m unittest test_diversity_endpoint -v
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
from diversity_endpoint import SLOTS


def _fresh_client(project_root: Path) -> TestClient:
    ps.PROJECT_ROOT = None
    ps.ENGINES = None
    ps.CACHE = None
    ps.SAMPLES = None
    ps._bootstrap_file(project_root)
    return TestClient(ps.app)


def _seed_slot(project_root: Path, slot: str, body: dict) -> Path:
    rel = SLOTS[slot]
    target = project_root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(body), encoding="utf-8")
    return target


class TestDiversityEndpoint(unittest.TestCase):

    def test_slots_lists_all_five(self):
        with tempfile.TemporaryDirectory() as td:
            client = _fresh_client(Path(td))
            r = client.get("/api/diversity/slots")
            self.assertEqual(r.status_code, 200)
            self.assertEqual(
                r.json(),
                {"slots": sorted([
                    "divergence_network",
                    "embedded_tables",
                    "functional_burden",
                    "roh_gene_overlap",
                    "texture_metrics",
                ])},
            )

    def test_get_existing_slot_returns_file_bytes(self):
        with tempfile.TemporaryDirectory() as td:
            project = Path(td)
            payload = {"dt_globals": {"cohort": "test"}, "dt_S1": [1, 2, 3]}
            _seed_slot(project, "embedded_tables", payload)
            client = _fresh_client(project)

            r = client.get("/api/diversity/embedded_tables")
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.headers["content-type"], "application/json")
            self.assertEqual(r.json(), payload)

    def test_missing_file_returns_404(self):
        with tempfile.TemporaryDirectory() as td:
            client = _fresh_client(Path(td))
            r = client.get("/api/diversity/texture_metrics")
            self.assertEqual(r.status_code, 404)
            self.assertIn("missing", r.json()["detail"])

    def test_unknown_slot_returns_404(self):
        with tempfile.TemporaryDirectory() as td:
            client = _fresh_client(Path(td))
            r = client.get("/api/diversity/not_a_real_slot")
            self.assertEqual(r.status_code, 404)
            self.assertIn("unknown diversity slot", r.json()["detail"])

    def test_each_slot_round_trips(self):
        """All five declared slots serve the file they point at."""
        with tempfile.TemporaryDirectory() as td:
            project = Path(td)
            for slot in SLOTS:
                _seed_slot(project, slot, {"_slot": slot})
            client = _fresh_client(project)
            for slot in SLOTS:
                r = client.get(f"/api/diversity/{slot}")
                self.assertEqual(r.status_code, 200, msg=slot)
                self.assertEqual(r.json(), {"_slot": slot}, msg=slot)

    def test_endpoint_503_when_subsystem_disabled(self):
        """No project root → /file subsystem is down → safe_path raises 503."""
        ps.PROJECT_ROOT = None
        client = TestClient(ps.app)
        r = client.get("/api/diversity/embedded_tables")
        self.assertEqual(r.status_code, 503)


if __name__ == "__main__":
    unittest.main(verbosity=2)
