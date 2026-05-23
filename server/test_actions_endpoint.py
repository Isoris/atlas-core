"""Integration tests for the action pipeline (POST /api/actions et al.).

Boots atlas_server with FastAPI's TestClient against a tmp workspace,
drops a minimal 'testatlas' dispatcher into atlases/testatlas/registries/,
and exercises:

  POST /api/actions                  — submit + persist + log
  GET  /api/actions/{action_id}      — log readback
  GET  /api/layers                   — index + filters
  GET  /api/layers/{layer_id}        — envelope readback

The test atlas's runner is pure file-IO (no HTTP callbacks) so the test
doesn't need a bound port — TestClient runs the FastAPI app through
its ASGI transport. The HTTP-callback path (runner POSTs back to the
server) is covered by the diversity/population endpoint tests plus the
JS unit tests in tests/test_layer_api.js.

Run from server/:
    python -m unittest test_actions_endpoint -v
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import textwrap
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from fastapi.testclient import TestClient

import atlas_server as ps


# =============================================================================
# Test-atlas factory — writes a minimal but real registry layout under tmp/
# =============================================================================

_DISPATCHER_PY = textwrap.dedent("""
    \"\"\"Minimal test dispatcher — exercises the contract atlas_server expects.\"\"\"
    from __future__ import annotations
    import importlib, json, pathlib, time
    HERE = pathlib.Path(__file__).parent

    def _load(p):
        return json.loads(p.read_text(encoding="utf-8"))

    def _import(dotted):
        mod, fn = dotted.rsplit(".", 1)
        return getattr(importlib.import_module(mod), fn)

    def _now():
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    def dispatch_action(manifest, client):
        actions = _load(HERE / "data/actions.registry.json")["actions"]
        if manifest["type"] not in actions:
            raise KeyError(f"unknown action type: {manifest['type']}")
        runner = _import(actions[manifest["type"]]["runner"])
        raw = runner(manifest, client)

        extractors = _load(HERE / "data/extractors.registry.json")["extractors"]
        envelopes = []
        for spec in (manifest.get("expected_outputs") or []):
            ex = next(
                e for e in extractors
                if e["layer_type"] == spec["layer_type"]
                and e["schema_version"] == spec["schema_version"]
            )
            parser = _import(ex["parser"])
            payload = parser(raw, ex.get("params") or {})
            envelopes.append({
                "layer_id":       f"{spec['layer_type']}_{manifest['dataset_id']}_{manifest['action_id'].rsplit('_', 1)[-1]}",
                "layer_type":     spec["layer_type"],
                "schema_version": spec["schema_version"],
                "stage":          spec.get("stage", "normalized"),
                "dataset_id":     manifest["dataset_id"],
                "status":         "review" if spec.get("stage") == "staging" else "active",
                "created_at":     _now(),
                "provenance": {
                    "action_id": manifest["action_id"],
                    "runner":    actions[manifest["type"]]["runner"],
                    "extractor": ex["parser"],
                },
                "source_files": list(raw.values()),
                "payload": payload,
            })
        return envelopes
""").lstrip()

_RUNNER_PY = textwrap.dedent("""
    \"\"\"Pure file-IO runner — writes a JSON payload, returns its path.\"\"\"
    import json, os, pathlib

    def run(manifest, client):
        root = pathlib.Path(os.environ.get("ATLAS_PROJECT_ROOT") or ".")
        out_dir = root / "raw_results" / "testatlas" / manifest["action_id"]
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "echo.json"
        out_path.write_text(json.dumps({
            "echoed": manifest.get("params") or {},
            "target": manifest.get("target") or {},
        }), encoding="utf-8")
        return {"echo_json": str(out_path)}

    def run_bad(manifest, client):
        raise RuntimeError("synthetic runner failure for negative-path test")
""").lstrip()

_EXTRACTOR_PY = textwrap.dedent("""
    \"\"\"Echo extractor — reads the runner's JSON, lifts a field into payload.\"\"\"
    import json, pathlib

    def extract(raw_outputs, params):
        path = pathlib.Path(raw_outputs["echo_json"])
        doc = json.loads(path.read_text(encoding="utf-8"))
        return {
            "echo":   doc.get("echoed"),
            "target": doc.get("target"),
            "source": str(path),
        }
""").lstrip()

_SCHEMA_IN = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "required": ["params"],
    "properties": {
        "params": {"type": "object", "additionalProperties": True},
        "target": {"type": "object", "additionalProperties": True},
    },
    "additionalProperties": True,
}

_SCHEMA_OUT = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "required": ["echo"],
    "additionalProperties": True,
    "properties": {
        "echo":   {"type": "object", "additionalProperties": True},
        "target": {"type": ["object", "null"], "additionalProperties": True},
        "source": {"type": "string"},
    },
}


def _write_test_atlas(workspace: Path, atlas_id: str = "testatlas",
                     include_bad_action: bool = True) -> None:
    """Drop a minimal registries/ tree for an atlas under <workspace>."""
    reg = workspace / "atlases" / atlas_id / "registries"
    (reg / "schemas" / "schema_in").mkdir(parents=True, exist_ok=True)
    (reg / "schemas" / "schema_out").mkdir(parents=True, exist_ok=True)
    (reg / "data").mkdir(parents=True, exist_ok=True)
    (reg / "runners").mkdir(parents=True, exist_ok=True)
    (reg / "extractors").mkdir(parents=True, exist_ok=True)

    (reg / "dispatcher.py").write_text(_DISPATCHER_PY, encoding="utf-8")
    (reg / "runners" / "__init__.py").write_text("", encoding="utf-8")
    (reg / "runners" / "echo.py").write_text(_RUNNER_PY, encoding="utf-8")
    (reg / "extractors" / "__init__.py").write_text("", encoding="utf-8")
    (reg / "extractors" / "echo.py").write_text(_EXTRACTOR_PY, encoding="utf-8")

    (reg / "schemas" / "schema_in" / "echo_v1.schema.json").write_text(
        json.dumps(_SCHEMA_IN, indent=2), encoding="utf-8"
    )
    (reg / "schemas" / "schema_out" / "echo_v0.schema.json").write_text(
        json.dumps(_SCHEMA_OUT, indent=2), encoding="utf-8"
    )

    actions = {"actions": {"echo": {
        "runner":    "runners.echo.run",
        "schema_in": "echo_v1",
    }}}
    if include_bad_action:
        actions["actions"]["echo_fail"] = {
            "runner":    "runners.echo.run_bad",
            "schema_in": "echo_v1",
        }
    (reg / "data" / "actions.registry.json").write_text(
        json.dumps(actions, indent=2), encoding="utf-8"
    )
    (reg / "data" / "extractors.registry.json").write_text(json.dumps({
        "extractors": [{
            "extractor_id":   "extract_echo_v0",
            "layer_type":     "echo",
            "schema_version": "echo_v0",
            "stage":          "staging",
            "parser":         "extractors.echo.extract",
        }],
    }, indent=2), encoding="utf-8")


def _write_master_config(workspace: Path, active_atlas: str) -> None:
    (workspace / "master_config.yaml").write_text(
        f"atlas:\n  active_atlas: {active_atlas}\n", encoding="utf-8"
    )


# =============================================================================
# Test harness — fresh workspace per test, ditto fresh client
# =============================================================================

class ActionsEndpointTests(unittest.TestCase):

    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp(prefix="atlas_actions_test_")
        self.workspace = Path(self.tmp)
        _write_test_atlas(self.workspace, "testatlas")
        _write_master_config(self.workspace, "testatlas")

        # Reset module-level state so two tests don't share a dispatcher cache.
        ps.PROJECT_ROOT = None
        ps.WORKSPACE_ROOT = None
        ps.ATLAS_DISPATCHERS.clear()
        ps.ACTIONS_LOG_PATH = None
        ps.LAYERS_INDEX_PATH = None
        ps.LAYERS_DIR = None
        ps.ACTIVE_ATLAS = None
        ps.SERVER_BIND_URL = None

        ps._bootstrap_file(self.workspace)
        ps.WORKSPACE_ROOT = self.workspace
        ps._bootstrap_actions(self.workspace, bind_url="http://127.0.0.1:0")
        self.client = TestClient(ps.app)

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ----- helpers -----

    @staticmethod
    def _new_action_id(tag: str = "abc") -> str:
        return f"act_{int(time.time() * 1000)}_{tag}"

    def _good_manifest(self, action_id: str | None = None) -> dict:
        return {
            "action_id":  action_id or self._new_action_id(),
            "type":       "echo",
            "dataset_id": "main_226_hatchery",
            "runner":     "echo",
            "target":     {"slot": "foo"},
            "params":     {"hello": "world"},
            "expected_outputs": [
                {"layer_type": "echo", "schema_version": "echo_v0", "stage": "staging"}
            ],
        }

    # ----- happy path -----

    def test_submit_action_round_trip(self) -> None:
        m = self._good_manifest()
        resp = self.client.post("/api/actions", json=m)
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["action_id"], m["action_id"])
        self.assertEqual(body["atlas_id"], "testatlas")
        self.assertEqual(len(body["produced_layers"]), 1)
        layer_id = body["produced_layers"][0]

        # Action log entry is success and references the produced layer.
        log_resp = self.client.get(f"/api/actions/{m['action_id']}")
        self.assertEqual(log_resp.status_code, 200, log_resp.text)
        entry = log_resp.json()
        self.assertEqual(entry["status"], "success")
        self.assertEqual(entry["produced_layers"], [layer_id])
        self.assertIn("duration_ms", entry)

        # Layer envelope was written to disk and indexed.
        envelope_path = (self.workspace / "layers" / "echo"
                         / "main_226_hatchery" / f"{layer_id}.json")
        self.assertTrue(envelope_path.exists(), f"missing: {envelope_path}")
        env = json.loads(envelope_path.read_text(encoding="utf-8"))
        self.assertEqual(env["layer_id"], layer_id)
        self.assertEqual(env["stage"], "staging")
        self.assertEqual(env["payload"]["echo"], {"hello": "world"})
        self.assertEqual(env["provenance"]["action_id"], m["action_id"])

        # Layers index includes the new row.
        idx = json.loads(
            (self.workspace / "registry" / "layers.registry.json")
            .read_text(encoding="utf-8")
        )
        ids = [r["layer_id"] for r in idx["layers"]]
        self.assertIn(layer_id, ids)

    def test_get_layers_filters(self) -> None:
        m1 = self._good_manifest(self._new_action_id("aa"))
        m2 = self._good_manifest(self._new_action_id("bb"))
        m2["dataset_id"] = "other_cohort"
        for m in (m1, m2):
            r = self.client.post("/api/actions", json=m)
            self.assertEqual(r.status_code, 200, r.text)

        # No filter → both
        all_resp = self.client.get("/api/layers")
        self.assertEqual(all_resp.status_code, 200)
        self.assertGreaterEqual(all_resp.json()["total"], 2)

        # Filter by dataset_id
        filt = self.client.get("/api/layers?dataset_id=other_cohort")
        self.assertEqual(filt.status_code, 200)
        layers = filt.json()["layers"]
        self.assertTrue(all(r["dataset_id"] == "other_cohort" for r in layers))
        self.assertTrue(any(r["dataset_id"] == "other_cohort" for r in layers))

        # Filter by layer_type that doesn't exist
        none = self.client.get("/api/layers?layer_type=does_not_exist")
        self.assertEqual(none.status_code, 200)
        self.assertEqual(none.json()["layers"], [])

    def test_get_layer_by_id(self) -> None:
        m = self._good_manifest()
        resp = self.client.post("/api/actions", json=m)
        layer_id = resp.json()["produced_layers"][0]

        env_resp = self.client.get(f"/api/layers/{layer_id}")
        self.assertEqual(env_resp.status_code, 200)
        env = env_resp.json()
        self.assertEqual(env["layer_id"], layer_id)
        # Minimal envelope contract — the same fields the helper asserts.
        for k in ("layer_id", "layer_type", "schema_version", "stage",
                  "dataset_id", "status", "created_at", "payload"):
            self.assertIn(k, env)

    # ----- atlas resolution precedence -----

    def test_atlas_query_param_wins_over_master_config(self) -> None:
        # Write a SECOND atlas; master_config still points at 'testatlas'.
        _write_test_atlas(self.workspace, "secondatlas",
                          include_bad_action=False)
        ps.ATLAS_DISPATCHERS.clear()   # force re-import

        m = self._good_manifest()
        resp = self.client.post("/api/actions?atlas=secondatlas", json=m)
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(resp.json()["atlas_id"], "secondatlas")

    def test_manifest_atlas_id_overrides_master_config(self) -> None:
        _write_test_atlas(self.workspace, "thirdatlas",
                          include_bad_action=False)
        ps.ATLAS_DISPATCHERS.clear()

        m = self._good_manifest()
        m["atlas_id"] = "thirdatlas"
        resp = self.client.post("/api/actions", json=m)
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(resp.json()["atlas_id"], "thirdatlas")

    def test_master_config_active_atlas_is_fallback(self) -> None:
        m = self._good_manifest()
        # No ?atlas=, no manifest.atlas_id → should fall back to master_config.
        resp = self.client.post("/api/actions", json=m)
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(resp.json()["atlas_id"], "testatlas")

    # ----- negative paths -----

    def test_invalid_manifest_400(self) -> None:
        # Missing required 'runner' field
        bad = {
            "action_id":  "act_xxx_111",
            "type":       "echo",
            "dataset_id": "d",
        }
        resp = self.client.post("/api/actions", json=bad)
        self.assertEqual(resp.status_code, 400, resp.text)
        self.assertIn("missing required", resp.text)

    def test_bad_action_id_pattern_400(self) -> None:
        bad = {
            "action_id":  "not_an_act_id",
            "type":       "echo",
            "dataset_id": "d",
            "runner":     "echo",
        }
        resp = self.client.post("/api/actions", json=bad)
        self.assertEqual(resp.status_code, 400)
        self.assertIn("action_id", resp.text)

    def test_unknown_atlas_404(self) -> None:
        m = self._good_manifest()
        resp = self.client.post("/api/actions?atlas=nosuchatlas", json=m)
        self.assertEqual(resp.status_code, 404, resp.text)
        self.assertIn("no dispatcher for atlas", resp.text)

    def test_dispatcher_error_appears_in_log(self) -> None:
        m = self._good_manifest()
        m["type"] = "echo_fail"   # this runner raises
        resp = self.client.post("/api/actions", json=m)
        self.assertEqual(resp.status_code, 500, resp.text)

        # Log entry exists, status=error, error details populated.
        log_resp = self.client.get(f"/api/actions/{m['action_id']}")
        self.assertEqual(log_resp.status_code, 200)
        entry = log_resp.json()
        self.assertEqual(entry["status"], "error")
        self.assertIsNotNone(entry["error"])
        self.assertIn("synthetic runner failure", entry["error"]["message"])
        # No layers should have been produced.
        self.assertEqual(entry["produced_layers"], [])

    def test_unknown_action_id_404(self) -> None:
        resp = self.client.get("/api/actions/act_nonexistent_999_zzz")
        self.assertEqual(resp.status_code, 404)

    def test_unknown_layer_id_404(self) -> None:
        resp = self.client.get("/api/layers/never_existed")
        self.assertEqual(resp.status_code, 404)


if __name__ == "__main__":
    unittest.main()
