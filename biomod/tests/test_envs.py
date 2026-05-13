"""Tests for biomod env commands.

Stdlib unittest. Each test gets its own ``BIOMOD_HOME`` tmpdir so no
state leaks across tests or into the user's real ``~/.biomod/``.

Run:
    python3 -m unittest biomod.tests.test_envs -v
or just:
    python3 biomod/tests/test_envs.py
"""

from __future__ import annotations

import io
import json
import os
import pathlib
import shutil
import sqlite3
import sys
import tempfile
import unittest
from contextlib import contextmanager

# Make `import biomod` work when running this file directly.
_HERE = pathlib.Path(__file__).resolve()
sys.path.insert(0, str(_HERE.parent.parent.parent))

from biomod import cli as biomod_cli
from biomod import envs, paths
from biomod.exit_codes import SUCCESS, USER_ERROR, STATE_INCONSISTENT


@contextmanager
def capture_stdout():
    buf = io.StringIO()
    old = sys.stdout
    sys.stdout = buf
    try:
        yield buf
    finally:
        sys.stdout = old


@contextmanager
def capture_stderr():
    buf = io.StringIO()
    old = sys.stderr
    sys.stderr = buf
    try:
        yield buf
    finally:
        sys.stderr = old


class BiomodHomeMixin:
    """Each test class gets an isolated $BIOMOD_HOME pointing at a tmpdir."""

    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="biomod-test-")
        self._old_home = os.environ.get("BIOMOD_HOME")
        os.environ["BIOMOD_HOME"] = self._tmp

    def tearDown(self):
        if self._old_home is None:
            os.environ.pop("BIOMOD_HOME", None)
        else:
            os.environ["BIOMOD_HOME"] = self._old_home
        shutil.rmtree(self._tmp, ignore_errors=True)


# --------------------------------------------------------------------------- #
# create                                                                       #
# --------------------------------------------------------------------------- #

class TestCreate(BiomodHomeMixin, unittest.TestCase):

    def test_create_fresh_env_returns_success(self):
        with capture_stdout() as out:
            rc = envs.cmd_create("inversions")
        self.assertEqual(rc, SUCCESS)
        self.assertIn("inversions", out.getvalue())

        d = paths.env_dir("inversions")
        self.assertTrue(d.is_dir(), f"env dir missing: {d}")
        self.assertTrue(paths.registry_dir("inversions").is_dir())
        self.assertTrue(paths.conda_dir("inversions").is_dir())
        self.assertTrue(paths.runs_db_path("inversions").is_file())

    def test_create_runs_sqlite_is_valid_db(self):
        envs.cmd_create("e1")
        # The file should be openable as a SQLite database (even with no tables).
        conn = sqlite3.connect(str(paths.runs_db_path("e1")))
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        conn.close()
        self.assertEqual(rows, [])  # no tables yet — step 6 adds them

    def test_create_duplicate_env_fails(self):
        envs.cmd_create("dup")
        with capture_stderr() as err:
            rc = envs.cmd_create("dup")
        self.assertEqual(rc, USER_ERROR)
        self.assertIn("already exists", err.getvalue())

    def test_invalid_name_rejected(self):
        for bad in ("BadCaps", "1starts_with_digit", "with-dash", "", "with space"):
            with capture_stderr():
                rc = envs.cmd_create(bad)
            self.assertEqual(rc, USER_ERROR, f"name {bad!r} should be rejected")
            self.assertFalse(paths.env_dir(bad).exists(),
                              f"env dir should not be created for {bad!r}")

    def test_valid_name_examples(self):
        for ok in ("default", "a", "a1", "a_b_c", "inversions_v2"):
            self.assertTrue(paths.valid_name(ok), f"name {ok!r} should be valid")


# --------------------------------------------------------------------------- #
# activate / deactivate                                                        #
# --------------------------------------------------------------------------- #

class TestActivateDeactivate(BiomodHomeMixin, unittest.TestCase):

    def test_activate_existing_prints_export(self):
        envs.cmd_create("e1")
        with capture_stdout() as out:
            rc = envs.cmd_activate("e1")
        self.assertEqual(rc, SUCCESS)
        self.assertIn("export BIOMOD_ENV='e1'", out.getvalue())

    def test_activate_unknown_env_fails(self):
        with capture_stderr() as err:
            rc = envs.cmd_activate("nope")
        self.assertEqual(rc, USER_ERROR)
        self.assertIn("does not exist", err.getvalue())

    def test_activate_invalid_name_fails(self):
        with capture_stderr():
            rc = envs.cmd_activate("Bad-Name")
        self.assertEqual(rc, USER_ERROR)

    def test_deactivate_prints_unset(self):
        with capture_stdout() as out:
            rc = envs.cmd_deactivate()
        self.assertEqual(rc, SUCCESS)
        self.assertIn("unset BIOMOD_ENV", out.getvalue())


# --------------------------------------------------------------------------- #
# env list                                                                     #
# --------------------------------------------------------------------------- #

class TestEnvList(BiomodHomeMixin, unittest.TestCase):

    def test_list_empty(self):
        with capture_stdout() as out:
            rc = envs.cmd_env_list(as_json=False)
        self.assertEqual(rc, SUCCESS)
        self.assertIn("no envs yet", out.getvalue())

    def test_list_json_empty_returns_array(self):
        with capture_stdout() as out:
            rc = envs.cmd_env_list(as_json=True)
        self.assertEqual(rc, SUCCESS)
        self.assertEqual(json.loads(out.getvalue()), [])

    def test_list_with_envs(self):
        envs.cmd_create("alpha")
        envs.cmd_create("beta")
        with capture_stdout() as out:
            rc = envs.cmd_env_list(as_json=True)
        self.assertEqual(rc, SUCCESS)
        rows = json.loads(out.getvalue())
        names = sorted(r["name"] for r in rows)
        self.assertEqual(names, ["alpha", "beta"])
        for r in rows:
            self.assertEqual(r["n_modules"], 0)
            self.assertIn("bytes_on_disk", r)
            self.assertTrue(r["has_runs_db"])

    def test_list_table_format_shows_active_marker(self):
        envs.cmd_create("alpha")
        envs.cmd_create("beta")
        os.environ["BIOMOD_ENV"] = "alpha"
        try:
            with capture_stdout() as out:
                envs.cmd_env_list(as_json=False)
            text = out.getvalue()
            # Find the table row for alpha (not the legend line at the bottom).
            alpha_lines = [
                l for l in text.splitlines()
                if "alpha" in l and "MODULES" not in l and "BIOMOD_ENV" not in l
            ]
            self.assertEqual(len(alpha_lines), 1, alpha_lines)
            self.assertTrue(alpha_lines[0].lstrip().startswith("*"),
                            f"expected '*' marker on alpha row, got: {alpha_lines[0]!r}")
            # Beta line should NOT carry the marker.
            beta_lines = [
                l for l in text.splitlines()
                if "beta" in l and "MODULES" not in l and "BIOMOD_ENV" not in l
            ]
            self.assertEqual(len(beta_lines), 1, beta_lines)
            self.assertFalse(beta_lines[0].lstrip().startswith("*"),
                             f"beta should not carry '*' marker, got: {beta_lines[0]!r}")
        finally:
            os.environ.pop("BIOMOD_ENV", None)


# --------------------------------------------------------------------------- #
# env remove                                                                   #
# --------------------------------------------------------------------------- #

class TestEnvRemove(BiomodHomeMixin, unittest.TestCase):

    def test_remove_existing_with_yes(self):
        envs.cmd_create("trash")
        with capture_stdout() as out:
            rc = envs.cmd_env_remove("trash", yes=True)
        self.assertEqual(rc, SUCCESS)
        self.assertFalse(paths.env_dir("trash").exists())
        self.assertIn("removed", out.getvalue())

    def test_remove_unknown_fails(self):
        with capture_stderr():
            rc = envs.cmd_env_remove("ghost", yes=True)
        self.assertEqual(rc, USER_ERROR)

    def test_remove_without_yes_on_non_tty_refuses(self):
        envs.cmd_create("keep")
        # Tests run under unittest with non-tty stdin by default.
        # In this environment, sys.stdin.isatty() is False → should refuse.
        with capture_stderr() as err:
            rc = envs.cmd_env_remove("keep", yes=False)
        self.assertEqual(rc, USER_ERROR)
        self.assertIn("--yes", err.getvalue())
        self.assertTrue(paths.env_dir("keep").exists(),
                        "env should NOT be removed without --yes on non-tty")

    def test_invalid_name_rejected(self):
        with capture_stderr():
            rc = envs.cmd_env_remove("Bad-Caps", yes=True)
        self.assertEqual(rc, USER_ERROR)


# --------------------------------------------------------------------------- #
# CLI integration (argparse → handler)                                         #
# --------------------------------------------------------------------------- #

class TestCli(BiomodHomeMixin, unittest.TestCase):

    def test_create_via_cli(self):
        with capture_stdout():
            rc = biomod_cli.main(["create", "-n", "via_cli"])
        self.assertEqual(rc, SUCCESS)
        self.assertTrue(paths.env_dir("via_cli").is_dir())

    def test_create_missing_name_arg_fails(self):
        # argparse raises SystemExit(2) when a required arg is missing.
        with capture_stderr():
            with self.assertRaises(SystemExit):
                biomod_cli.main(["create"])

    def test_activate_then_deactivate_via_cli(self):
        biomod_cli.main(["create", "-n", "demo"])
        with capture_stdout() as out:
            rc = biomod_cli.main(["activate", "demo"])
        self.assertEqual(rc, SUCCESS)
        self.assertIn("export BIOMOD_ENV='demo'", out.getvalue())

        with capture_stdout() as out:
            rc = biomod_cli.main(["deactivate"])
        self.assertEqual(rc, SUCCESS)
        self.assertIn("unset BIOMOD_ENV", out.getvalue())

    def test_env_list_json_via_cli(self):
        biomod_cli.main(["create", "-n", "one"])
        biomod_cli.main(["create", "-n", "two"])
        with capture_stdout() as out:
            rc = biomod_cli.main(["env", "list", "--json"])
        self.assertEqual(rc, SUCCESS)
        rows = json.loads(out.getvalue())
        self.assertEqual(sorted(r["name"] for r in rows), ["one", "two"])

    def test_env_remove_with_yes_via_cli(self):
        biomod_cli.main(["create", "-n", "gone"])
        with capture_stdout():
            rc = biomod_cli.main(["env", "remove", "gone", "--yes"])
        self.assertEqual(rc, SUCCESS)
        self.assertFalse(paths.env_dir("gone").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
