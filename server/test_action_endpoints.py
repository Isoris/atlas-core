#!/usr/bin/env python3
"""
test_action_endpoints.py — tests for the new action endpoints.

Two layers:
  • Pure-logic tests (stdlib only) for action_endpoints.py.
  • Optional integration tests via FastAPI's TestClient, executed only
    if `atlas_server` imports cleanly (it has numpy/pandas/yaml deps).

Run:
    python3 test_action_endpoints.py

Exit code 0 on pass, 1 on fail. Mirrors test_units.py style.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import action_endpoints as A


# ----- tiny harness ---------------------------------------------------------

_fails = 0


def assert_eq(a, b, label=""):
    global _fails
    if a != b:
        print(f"FAIL {label}: {a!r} != {b!r}")
        _fails += 1
    else:
        print(f"  ok  {label}")


def assert_true(c, label=""):
    global _fails
    if not c:
        print(f"FAIL {label}: expected truthy, got {c!r}")
        _fails += 1
    else:
        print(f"  ok  {label}")


def assert_raises(fn, exc, label=""):
    global _fails
    try:
        fn()
    except exc as e:
        print(f"  ok  {label}  ({type(e).__name__}: {e})")
        return
    except Exception as e:
        print(f"FAIL {label}: expected {exc.__name__}, got {type(e).__name__}: {e}")
        _fails += 1
        return
    print(f"FAIL {label}: expected {exc.__name__}, nothing raised")
    _fails += 1


# ----- pure logic tests -----------------------------------------------------

def test_validate_manifest():
    print("\n[test_validate_manifest]")

    # Happy path
    m = A.validate_action_manifest({
        "action_id":  "act_1715000000_abc",
        "type":       "run_ngsrelate",
        "dataset_id": "main_226_hatchery",
        "runner":     "runners.ngsrelate.run",
    })
    assert_eq(m["action_id"], "act_1715000000_abc", "happy path action_id passthrough")

    # Missing required field
    assert_raises(
        lambda: A.validate_action_manifest({"type": "x", "dataset_id": "y", "runner": "z"}),
        A.ValidationError, "missing action_id rejected")

    # Bad action_id pattern
    assert_raises(
        lambda: A.validate_action_manifest({
            "action_id": "bad_id",
            "type": "run_x",
            "dataset_id": "ds",
            "runner": "r",
        }),
        A.ValidationError, "action_id without 'act_' prefix rejected")

    # Bad type pattern
    assert_raises(
        lambda: A.validate_action_manifest({
            "action_id": "act_1_a",
            "type": "RunX",
            "dataset_id": "ds",
            "runner": "r",
        }),
        A.ValidationError, "type with uppercase rejected")

    # expected_outputs must be a list of objects with required fields
    assert_raises(
        lambda: A.validate_action_manifest({
            "action_id": "act_1_a",
            "type": "run_x",
            "dataset_id": "ds",
            "runner": "r",
            "expected_outputs": [{"layer_type": "fst_windows"}],   # missing schema_version
        }),
        A.ValidationError, "expected_outputs entry missing schema_version rejected")

    # additionalProperties: extra fields are allowed
    m2 = A.validate_action_manifest({
        "action_id":  "act_1_a",
        "type":       "run_x",
        "dataset_id": "ds",
        "runner":     "r",
        "notes":      "some free text",
        "submitted_by": "me",
    })
    assert_eq(m2.get("notes"), "some free text", "extra fields preserved")


def test_action_log_roundtrip():
    print("\n[test_action_log_roundtrip]")
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td)

        # Empty log: returns []
        assert_eq(A.read_action_log(ws), [], "empty log returns []")
        assert_eq(A.latest_action_entry(ws, "act_x"), None, "no action: latest is None")

        # Append two entries with same action_id, latest wins
        A.append_action_log(ws, {"action_id": "act_a", "status": "queued"})
        A.append_action_log(ws, {"action_id": "act_b", "status": "queued"})
        A.append_action_log(ws, {"action_id": "act_a", "status": "success"})

        rows = A.read_action_log(ws)
        assert_eq(len(rows), 3, "three rows in log")

        latest_a = A.latest_action_entry(ws, "act_a")
        assert_eq(latest_a["status"], "success", "latest entry for act_a is the third one")

        latest_b = A.latest_action_entry(ws, "act_b")
        assert_eq(latest_b["status"], "queued", "latest entry for act_b is the queued one")

        # File is JSONL — one JSON object per line, no commas
        text = (ws / A.REGISTRY_DIR_NAME / A.ACTIONS_LOG_NAME).read_text()
        lines = [l for l in text.splitlines() if l]
        assert_eq(len(lines), 3, "JSONL file has 3 lines")
        for line in lines:
            json.loads(line)  # parses without error
        assert_true(True, "every line is valid JSON")


def test_documentation_mode():
    """Workspace has no dispatcher.py → handle_post_action succeeds with
    empty produced_layers + a 'note' explaining documentation mode."""
    print("\n[test_documentation_mode]")
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td)
        body = {
            "action_id":  "act_1715_doc",
            "type":       "run_ngsrelate",
            "dataset_id": "main_226_hatchery",
            "runner":     "runners.ngsrelate.run",
        }
        resp = A.handle_post_action(ws, body)
        assert_eq(resp["action_id"], "act_1715_doc", "response carries action_id")
        assert_eq(resp["status"], "success", "documentation mode reports success")
        assert_eq(resp["produced_layers"], [], "no produced layers in doc mode")
        assert_true("note" in resp, "response includes a 'note' explaining doc mode")

        # Log has 3 entries: queued, running, success
        rows = A.read_action_log(ws)
        assert_eq(len(rows), 3, "three log entries (queued/running/success)")
        assert_eq(rows[0]["status"], "queued", "first entry queued")
        assert_eq(rows[1]["status"], "running", "second entry running")
        assert_eq(rows[2]["status"], "success", "third entry success")
        assert_true("finished_at" in rows[2], "success entry has finished_at")


def test_duplicate_action_id():
    print("\n[test_duplicate_action_id]")
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td)
        body = {
            "action_id":  "act_dup",
            "type":       "run_x",
            "dataset_id": "ds",
            "runner":     "r",
        }
        # First post succeeds
        A.handle_post_action(ws, body)
        # Second post raises DuplicateActionError
        assert_raises(
            lambda: A.handle_post_action(ws, body),
            A.DuplicateActionError,
            "second post with same action_id raises DuplicateActionError")


def test_dispatcher_discovery():
    print("\n[test_dispatcher_discovery]")
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td)

        # No dispatcher.py: find_dispatcher returns None
        assert_eq(A.find_dispatcher(ws), None, "no dispatcher.py → None")

        # Write a dispatcher that produces a layer_id
        (ws / "dispatcher.py").write_text(
            "def dispatch_action(manifest, context):\n"
            "    return {'produced_layers': ['fst_windows_demo_v1']}\n"
        )
        body = {
            "action_id":  "act_disp",
            "type":       "run_x",
            "dataset_id": "ds",
            "runner":     "r",
        }
        resp = A.handle_post_action(ws, body)
        assert_eq(resp["status"], "success", "dispatcher succeeded")
        assert_eq(resp["produced_layers"], ["fst_windows_demo_v1"],
                  "produced_layers from dispatcher.dispatch_action returned in response")


def test_dispatcher_failure():
    print("\n[test_dispatcher_failure]")
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td)
        (ws / "dispatcher.py").write_text(
            "def dispatch_action(manifest, context):\n"
            "    raise RuntimeError('boom from runner')\n"
        )
        resp = A.handle_post_action(ws, {
            "action_id":  "act_fail",
            "type":       "run_x",
            "dataset_id": "ds",
            "runner":     "r",
        })
        assert_eq(resp["status"], "error", "raises → status=error")
        assert_true("error" in resp, "response contains 'error'")
        assert_eq(resp["error"]["kind"], "runner", "error.kind = runner")
        assert_true("boom from runner" in resp["error"]["message"],
                    "error.message contains the raise message")


def test_list_and_find_layers():
    print("\n[test_list_and_find_layers]")
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td)
        # Empty: empty list, None
        assert_eq(A.list_layers(ws), [], "empty layers/ → []")
        assert_eq(A.find_layer(ws, "anything"), None, "empty layers/ → None")

        # Drop two envelopes
        env_a = {
            "layer_id":       "fst_windows_demo_v1",
            "layer_type":     "fst_windows",
            "schema_version": "fst_windows_v1",
            "stage":          "normalized",
            "dataset_id":     "main_226_hatchery",
            "status":         "active",
            "created_at":     "2026-05-13T11:00:00Z",
            "payload":        {"windows": []},
        }
        env_b = {
            "layer_id":       "ngsrelate_result_global_v1",
            "layer_type":     "ngsrelate_result",
            "schema_version": "ngsrelate_result_v1",
            "stage":          "normalized",
            "dataset_id":     "other_cohort",
            "status":         "active",
            "created_at":     "2026-05-13T11:10:00Z",
            "payload":        {},
        }
        (ws / "layers" / "fst_windows" / "main_226_hatchery").mkdir(parents=True)
        (ws / "layers" / "fst_windows" / "main_226_hatchery" / "fst_windows_demo_v1.json").write_text(json.dumps(env_a))
        (ws / "layers" / "ngsrelate_result").mkdir(parents=True)
        (ws / "layers" / "ngsrelate_result" / "ngsrelate_result_global_v1.json").write_text(json.dumps(env_b))

        # No filter: both shown
        all_layers = A.list_layers(ws)
        assert_eq(len(all_layers), 2, "list_layers returns both envelopes")

        # Filter by layer_type
        only_fst = A.list_layers(ws, layer_type="fst_windows")
        assert_eq(len(only_fst), 1, "filter by layer_type=fst_windows returns 1")
        assert_eq(only_fst[0]["layer_id"], "fst_windows_demo_v1", "right id in filter result")

        # Filter by dataset_id
        only_other = A.list_layers(ws, dataset_id="other_cohort")
        assert_eq(len(only_other), 1, "filter by dataset_id=other_cohort returns 1")

        # find_layer
        env = A.find_layer(ws, "fst_windows_demo_v1")
        assert_true(env is not None, "find_layer returns envelope")
        assert_eq(env["layer_id"], "fst_windows_demo_v1", "found envelope has right id")
        assert_eq(env["payload"], {"windows": []}, "find_layer returns full envelope (payload included)")

        assert_eq(A.find_layer(ws, "unknown"), None, "find_layer on unknown id → None")


def run_pure_logic_tests():
    test_validate_manifest()
    test_action_log_roundtrip()
    test_documentation_mode()
    test_duplicate_action_id()
    test_dispatcher_discovery()
    test_dispatcher_failure()
    test_list_and_find_layers()


# ----- integration tests via FastAPI TestClient (optional) -------------------

def run_integration_tests():
    """Boot atlas_server.app inside a tmpdir workspace, hit the four routes
    via TestClient. Skipped if atlas_server can't be imported."""
    print("\n[integration tests via FastAPI TestClient]")
    try:
        os.environ["ATLAS_PROJECT_ROOT"] = tempfile.mkdtemp(prefix="atlas-test-")
        import atlas_server  # noqa: F401
        from fastapi.testclient import TestClient
    except Exception as e:
        print(f"  skip  atlas_server / TestClient unavailable: {type(e).__name__}: {e}")
        return

    client = TestClient(atlas_server.app)
    ws = Path(os.environ["ATLAS_PROJECT_ROOT"])

    # POST a valid manifest
    body = {
        "action_id":  "act_1715_int_a",
        "type":       "run_ngsrelate",
        "dataset_id": "main_226_hatchery",
        "runner":     "runners.ngsrelate.run",
    }
    r = client.post("/api/actions", json=body)
    assert_eq(r.status_code, 200, "POST /api/actions valid → 200")
    j = r.json()
    assert_eq(j["status"], "success", "doc mode returns success")
    assert_eq(j["produced_layers"], [], "doc mode no produced layers")

    # Duplicate → 409
    r2 = client.post("/api/actions", json=body)
    assert_eq(r2.status_code, 409, "POST duplicate action_id → 409")

    # Invalid → 400
    r3 = client.post("/api/actions", json={"action_id": "bad"})
    assert_eq(r3.status_code, 400, "POST missing fields → 400")

    # GET the action
    r4 = client.get("/api/actions/act_1715_int_a")
    assert_eq(r4.status_code, 200, "GET /api/actions/<id> known → 200")
    assert_eq(r4.json()["status"], "success", "GET /api/actions returns latest status")

    r5 = client.get("/api/actions/act_nonexistent")
    assert_eq(r5.status_code, 404, "GET /api/actions/<id> unknown → 404")

    # /api/layers: no layers yet → []
    r6 = client.get("/api/layers")
    assert_eq(r6.status_code, 200, "GET /api/layers → 200")
    assert_eq(r6.json(), [], "GET /api/layers with no envelopes → []")

    # Drop one envelope and re-list
    (ws / "layers" / "fst_windows").mkdir(parents=True)
    env = {
        "layer_id":       "fst_windows_int_v1",
        "layer_type":     "fst_windows",
        "schema_version": "fst_windows_v1",
        "stage":          "normalized",
        "dataset_id":     "main_226_hatchery",
        "status":         "active",
        "created_at":     "2026-05-13T12:00:00Z",
        "payload":        {"windows": []},
    }
    (ws / "layers" / "fst_windows" / "fst_windows_int_v1.json").write_text(json.dumps(env))

    r7 = client.get("/api/layers")
    assert_eq(r7.status_code, 200, "GET /api/layers (with envelope) → 200")
    assert_eq(len(r7.json()), 1, "list returns the one envelope")

    r8 = client.get("/api/layers/fst_windows_int_v1")
    assert_eq(r8.status_code, 200, "GET /api/layers/<id> known → 200")
    assert_eq(r8.json()["layer_id"], "fst_windows_int_v1", "returned envelope has right id")

    r9 = client.get("/api/layers/unknown")
    assert_eq(r9.status_code, 404, "GET /api/layers/<id> unknown → 404")


# ----- entry ---------------------------------------------------------------

if __name__ == "__main__":
    run_pure_logic_tests()
    run_integration_tests()
    if _fails:
        print(f"\n{_fails} test(s) FAILED")
        sys.exit(1)
    print("\nall tests passed")
    sys.exit(0)
