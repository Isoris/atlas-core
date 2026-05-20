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
    """Bootstrap atlas_server against `project_root` AND ensure
    `<project_root>/data/` exists so diversity_endpoint's
    `_resolve_data_dir` falls through cleanly to the PROJECT_ROOT/data
    branch (instead of returning None → 404 diversity_data_dir_unset).
    Tests that specifically want the unset path call _fresh_client(...)
    then mkdir-skip; tests that want hits seed_slot before.
    """
    ps.PROJECT_ROOT = None
    ps.ENGINES = None
    ps.CACHE = None
    ps.SAMPLES = None
    ps._bootstrap_file(project_root)
    # Pre-create <project_root>/data/ so _resolve_data_dir succeeds
    # without ATLAS_DIVERSITY_DATA_DIR. The 2026-05 data-dir indirection
    # made the slot paths relative to the DATA dir, not the project root.
    (project_root / "data").mkdir(parents=True, exist_ok=True)
    return TestClient(ps.app)


def _seed_slot(project_root: Path, slot: str, body: dict) -> Path:
    """Seed a slot file at the location the endpoint reads from:
    `<project_root>/data/<SLOTS[slot]>`. Note the `data/` prefix —
    this is the PROJECT_ROOT/data fallback path used when
    ATLAS_DIVERSITY_DATA_DIR is unset.
    """
    rel = SLOTS[slot]
    target = project_root / "data" / rel
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
        """Data dir resolves (PROJECT_ROOT/data is pre-created by
        _fresh_client) but the specific slot file isn't seeded —
        endpoint returns 404 with 'missing' in the detail."""
        with tempfile.TemporaryDirectory() as td:
            client = _fresh_client(Path(td))
            r = client.get("/api/diversity/texture_metrics")
            self.assertEqual(r.status_code, 404)
            self.assertIn("missing", r.json()["detail"])

    def test_data_dir_unset_returns_404_with_fix_hint(self):
        """Neither ATLAS_DIVERSITY_DATA_DIR set NOR PROJECT_ROOT/data
        exists → endpoint returns 404 with the diversity_data_dir_unset
        error shape (added 2026-05 by the data-dir indirection). The
        `fix` field tells the user how to resolve."""
        with tempfile.TemporaryDirectory() as td:
            # Bootstrap WITHOUT pre-creating <project_root>/data, so
            # _resolve_data_dir returns None.
            ps.PROJECT_ROOT = None
            ps.ENGINES = None
            ps.CACHE = None
            ps.SAMPLES = None
            ps._bootstrap_file(Path(td))
            # Ensure no ATLAS_DIVERSITY_DATA_DIR leaks in from the
            # environment (e.g. the dev's shell):
            import os
            saved = os.environ.pop("ATLAS_DIVERSITY_DATA_DIR", None)
            try:
                client = TestClient(ps.app)
                r = client.get("/api/diversity/embedded_tables")
                self.assertEqual(r.status_code, 404)
                body = r.json()["detail"]
                self.assertEqual(body["error"], "diversity_data_dir_unset")
                self.assertIn("ATLAS_DIVERSITY_DATA_DIR", body["fix"])
            finally:
                if saved is not None:
                    os.environ["ATLAS_DIVERSITY_DATA_DIR"] = saved

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

    def test_no_project_root_returns_404_with_fix_hint(self):
        """No project root AND no ATLAS_DIVERSITY_DATA_DIR — the data-dir
        indirection (2026-05) catches the safe_path 503 internally and
        returns the same diversity_data_dir_unset 404 shape rather than
        leaking the bare 503. The `fix` field is the actionable hint.
        Predecessor test asserted 503 passthrough; the contract changed
        to prefer the explicit fix hint over the opaque service code."""
        ps.PROJECT_ROOT = None
        import os
        saved = os.environ.pop("ATLAS_DIVERSITY_DATA_DIR", None)
        try:
            client = TestClient(ps.app)
            r = client.get("/api/diversity/embedded_tables")
            self.assertEqual(r.status_code, 404)
            body = r.json()["detail"]
            self.assertEqual(body["error"], "diversity_data_dir_unset")
            self.assertIn("ATLAS_DIVERSITY_DATA_DIR", body["fix"])
        finally:
            if saved is not None:
                os.environ["ATLAS_DIVERSITY_DATA_DIR"] = saved


if __name__ == "__main__":
    unittest.main(verbosity=2)
