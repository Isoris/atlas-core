"""Tests for scripts/atlas_action.py — the CLI.

Spins up an in-process WSGI/threaded server bound to a random localhost
port (so the CLI's stdlib urllib calls can actually hit it), with the
TestClient-style 'testatlas' wired up. Exercises every subcommand:
submit, log, list, get, new-id.

Run from atlas-core/:
    python3 -m unittest scripts.test_atlas_action
"""
from __future__ import annotations

import contextlib
import io
import json
import shutil
import socket
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "server"))
sys.path.insert(0, str(HERE))

import atlas_server as ps
import atlas_action
from test_actions_endpoint import _write_test_atlas, _write_master_config  # type: ignore


def _free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


@contextlib.contextmanager
def _capture_stdout():
    buf = io.StringIO()
    old = sys.stdout
    sys.stdout = buf
    try:
        yield buf
    finally:
        sys.stdout = old


@contextlib.contextmanager
def _capture_stderr():
    buf = io.StringIO()
    old = sys.stderr
    sys.stderr = buf
    try:
        yield buf
    finally:
        sys.stderr = old


class AtlasActionCliTests(unittest.TestCase):
    """The CLI uses urllib against a real bound port; spin up uvicorn in
    a worker thread for the duration of the test class."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.mkdtemp(prefix="atlas_action_cli_")
        cls.workspace = Path(cls.tmp)
        _write_test_atlas(cls.workspace, "testatlas")
        _write_master_config(cls.workspace, "testatlas")

        # Reset module state, bootstrap the actions subsystem.
        ps.PROJECT_ROOT = None
        ps.WORKSPACE_ROOT = None
        ps.ATLAS_DISPATCHERS.clear()
        ps.ACTIONS_LOG_PATH = None
        ps.LAYERS_INDEX_PATH = None
        ps.LAYERS_DIR = None
        ps.ACTIVE_ATLAS = None
        ps.SERVER_BIND_URL = None
        ps._bootstrap_file(cls.workspace)
        ps.WORKSPACE_ROOT = cls.workspace

        cls.port = _free_port()
        ps._bootstrap_actions(cls.workspace, bind_url=f"http://127.0.0.1:{cls.port}")

        # Boot uvicorn in a thread.
        import uvicorn
        cls.config = uvicorn.Config(
            ps.app, host="127.0.0.1", port=cls.port,
            log_level="warning", access_log=False,
        )
        cls.server = uvicorn.Server(cls.config)
        cls.thread = threading.Thread(target=cls.server.run, daemon=True)
        cls.thread.start()
        # Wait until the server is accepting connections.
        deadline = time.time() + 10.0
        while time.time() < deadline:
            try:
                with socket.create_connection(("127.0.0.1", cls.port), timeout=0.2):
                    break
            except OSError:
                time.sleep(0.05)
        else:
            raise RuntimeError(f"uvicorn did not bind port {cls.port}")

        cls.base_url = f"http://127.0.0.1:{cls.port}"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.should_exit = True
        cls.thread.join(timeout=5.0)
        shutil.rmtree(cls.tmp, ignore_errors=True)

    # ----- helpers -----

    def _good_manifest(self) -> dict:
        return {
            "type":       "echo",
            "dataset_id": "main_226_hatchery",
            "runner":     "echo",
            "target":     {"slot": "foo"},
            "params":     {"hello": "world"},
            "expected_outputs": [
                {"layer_type": "echo", "schema_version": "echo_v0", "stage": "staging"}
            ],
        }

    def _write_manifest(self) -> Path:
        path = Path(self.tmp) / f"manifest_{int(time.time()*1000)}.json"
        path.write_text(json.dumps(self._good_manifest()), encoding="utf-8")
        return path

    # ----- new-id (no network) -----

    def test_new_id_matches_schema_regex(self) -> None:
        import re
        with _capture_stdout() as out:
            rc = atlas_action.main(["new-id"])
        self.assertEqual(rc, 0)
        text = out.getvalue().strip()
        self.assertRegex(text, r"^act_[A-Za-z0-9_]+$")

    def test_new_id_with_tag(self) -> None:
        with _capture_stdout() as out:
            rc = atlas_action.main(["new-id", "--tag", "xyz"])
        self.assertEqual(rc, 0)
        self.assertTrue(out.getvalue().strip().endswith("_xyz"))

    # ----- submit -----

    def test_submit_dry_run_emits_manifest(self) -> None:
        mpath = self._write_manifest()
        # Dry run must NOT contact the server at all — point at a bogus
        # base URL and the call should still succeed.
        with _capture_stdout() as out:
            rc = atlas_action.main([
                "--server", "http://127.0.0.1:1",   # nothing listens here
                "submit", "-f", str(mpath), "--dry-run",
            ])
        self.assertEqual(rc, 0)
        echoed = json.loads(out.getvalue())
        self.assertEqual(echoed["type"], "echo")
        self.assertIn("action_id", echoed)
        # action_id should have been auto-filled even on dry-run.
        self.assertRegex(echoed["action_id"], r"^act_[A-Za-z0-9_]+$")

    def test_submit_happy_path(self) -> None:
        mpath = self._write_manifest()
        with _capture_stdout() as out:
            rc = atlas_action.main([
                "--server", self.base_url, "submit",
                "-f", str(mpath), "--atlas", "testatlas",
            ])
        self.assertEqual(rc, 0, out.getvalue())
        body = out.getvalue()
        self.assertIn("✓ action act_", body)
        self.assertIn("atlas=testatlas", body)
        self.assertIn("produced 1 layer", body)

    def test_submit_quiet_emits_one_layer_id_per_line(self) -> None:
        mpath = self._write_manifest()
        with _capture_stdout() as out:
            rc = atlas_action.main([
                "--server", self.base_url, "submit",
                "-f", str(mpath), "--atlas", "testatlas", "-q",
            ])
        self.assertEqual(rc, 0)
        lines = [l for l in out.getvalue().splitlines() if l.strip()]
        self.assertEqual(len(lines), 1)
        self.assertTrue(lines[0].startswith("echo_main_226_hatchery_"))

    def test_submit_with_fetch_prints_envelope_summary(self) -> None:
        mpath = self._write_manifest()
        with _capture_stdout() as out:
            rc = atlas_action.main([
                "--server", self.base_url, "submit",
                "-f", str(mpath), "--atlas", "testatlas", "--fetch",
            ])
        self.assertEqual(rc, 0, out.getvalue())
        body = out.getvalue()
        self.assertIn("--- envelopes ---", body)
        self.assertIn("stage:     staging", body)
        self.assertIn("dataset:   main_226_hatchery", body)

    def test_submit_bad_manifest_surfaces_400(self) -> None:
        path = Path(self.tmp) / "bad_manifest.json"
        path.write_text(json.dumps({"type": "echo"}), encoding="utf-8")
        with _capture_stdout(), _capture_stderr() as err:
            rc = atlas_action.main([
                "--server", self.base_url, "submit",
                "-f", str(path), "--atlas", "testatlas",
            ])
        self.assertEqual(rc, 1)
        self.assertIn("HTTP 400", err.getvalue())

    # ----- list / get -----

    def test_list_emits_table(self) -> None:
        # Seed by submitting once
        atlas_action.main([
            "--server", self.base_url, "submit",
            "-f", str(self._write_manifest()), "--atlas", "testatlas", "-q",
        ])
        with _capture_stdout() as out:
            rc = atlas_action.main([
                "--server", self.base_url, "list", "--layer-type", "echo",
            ])
        self.assertEqual(rc, 0)
        body = out.getvalue()
        self.assertIn("layer_id", body)
        self.assertIn("echo", body)
        self.assertIn("staging", body)

    def test_list_quiet_emits_layer_ids(self) -> None:
        atlas_action.main([
            "--server", self.base_url, "submit",
            "-f", str(self._write_manifest()), "--atlas", "testatlas", "-q",
        ])
        with _capture_stdout() as out:
            rc = atlas_action.main([
                "--server", self.base_url, "list",
                "--layer-type", "echo", "-q",
            ])
        self.assertEqual(rc, 0)
        ids = [l for l in out.getvalue().splitlines() if l.strip()]
        self.assertGreaterEqual(len(ids), 1)
        self.assertTrue(all(i.startswith("echo_") for i in ids))

    def test_get_full_envelope(self) -> None:
        with _capture_stdout() as out:
            atlas_action.main([
                "--server", self.base_url, "submit",
                "-f", str(self._write_manifest()), "--atlas", "testatlas", "-q",
            ])
        layer_id = out.getvalue().strip().splitlines()[0]

        with _capture_stdout() as out:
            rc = atlas_action.main([
                "--server", self.base_url, "get", layer_id,
            ])
        self.assertEqual(rc, 0)
        env = json.loads(out.getvalue())
        self.assertEqual(env["layer_id"], layer_id)
        self.assertIn("payload", env)

    def test_get_payload_only(self) -> None:
        with _capture_stdout() as out:
            atlas_action.main([
                "--server", self.base_url, "submit",
                "-f", str(self._write_manifest()), "--atlas", "testatlas", "-q",
            ])
        layer_id = out.getvalue().strip().splitlines()[0]

        with _capture_stdout() as out:
            rc = atlas_action.main([
                "--server", self.base_url, "get",
                layer_id, "--payload-only",
            ])
        self.assertEqual(rc, 0)
        payload = json.loads(out.getvalue())
        # Echo extractor lifts target/params/source into the payload.
        self.assertIn("echo", payload)
        self.assertEqual(payload["echo"], {"hello": "world"})

    # ----- log -----

    def test_log_round_trip(self) -> None:
        # Submit, capture its action_id from --json output.
        with _capture_stdout() as out:
            atlas_action.main([
                "--server", self.base_url, "submit",
                "-f", str(self._write_manifest()), "--atlas", "testatlas",
                "--json",
            ])
        body = json.loads(out.getvalue())
        action_id = body["action_id"]

        with _capture_stdout() as out:
            rc = atlas_action.main([
                "--server", self.base_url, "log", action_id,
            ])
        self.assertEqual(rc, 0)
        text = out.getvalue()
        self.assertIn("status:          success", text)
        self.assertIn(action_id, text)

    def test_log_unknown_action_id_returns_1(self) -> None:
        with _capture_stdout(), _capture_stderr() as err:
            rc = atlas_action.main([
                "--server", self.base_url, "log", "act_nonexistent_999_zzz",
            ])
        self.assertEqual(rc, 1)
        self.assertIn("HTTP 404", err.getvalue())


if __name__ == "__main__":
    unittest.main()
