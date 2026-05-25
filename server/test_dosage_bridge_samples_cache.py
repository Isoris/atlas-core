"""Smoke test for the _read_samples mtime cache (Tier-B finding #5).

Verifies:
  - First call reads from disk, populates cache
  - Second call with same mtime returns from cache (no re-read)
  - Touching the file (new mtime) invalidates the cache entry
  - Different paths cache independently
"""
import os
import time
import shutil
import tempfile
import unittest
from pathlib import Path

import dosage_bridge as db


class ReadSamplesCacheTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="atlas_dosage_test_"))
        self.samples_a = self.tmp / "samples_a.tsv"
        self.samples_b = self.tmp / "samples_b.tsv"
        self.samples_a.write_text("alpha\nbeta\ngamma\n", encoding="utf-8")
        self.samples_b.write_text("delta\nepsilon\n", encoding="utf-8")
        # Reset cache so tests don't share state.
        db._SAMPLES_CACHE.clear()

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_first_call_populates_cache(self) -> None:
        ids = db._read_samples(self.samples_a)
        self.assertEqual(ids, ["alpha", "beta", "gamma"])
        self.assertEqual(len(db._SAMPLES_CACHE), 1)

    def test_second_call_returns_cached_object(self) -> None:
        ids1 = db._read_samples(self.samples_a)
        ids2 = db._read_samples(self.samples_a)
        # Same list IDENTITY (not just equal) — proves it came from cache.
        self.assertIs(ids1, ids2)

    def test_touch_invalidates_cache(self) -> None:
        ids1 = db._read_samples(self.samples_a)
        # Bump mtime by 2 seconds so the (path, mtime_ns) key changes.
        new_t = time.time() + 2
        os.utime(self.samples_a, (new_t, new_t))
        # Rewrite contents so we can tell the cache was bypassed.
        self.samples_a.write_text("zeta\n", encoding="utf-8")
        # Restore the bumped mtime AFTER the write so the test is deterministic.
        os.utime(self.samples_a, (new_t, new_t))
        ids2 = db._read_samples(self.samples_a)
        self.assertEqual(ids2, ["zeta"])
        # Cache now has TWO entries — old + new mtime keys (the LRU sweep
        # is not part of the contract; just verify we didn't return stale).
        self.assertNotEqual(ids1, ids2)

    def test_different_paths_cache_independently(self) -> None:
        ids_a = db._read_samples(self.samples_a)
        ids_b = db._read_samples(self.samples_b)
        self.assertEqual(ids_a, ["alpha", "beta", "gamma"])
        self.assertEqual(ids_b, ["delta", "epsilon"])
        self.assertEqual(len(db._SAMPLES_CACHE), 2)

    def test_tab_separated_takes_first_column(self) -> None:
        p = self.tmp / "tabbed.tsv"
        p.write_text("alpha\tgroup1\nbeta\tgroup2\n", encoding="utf-8")
        ids = db._read_samples(p)
        self.assertEqual(ids, ["alpha", "beta"])


if __name__ == "__main__":
    unittest.main()
