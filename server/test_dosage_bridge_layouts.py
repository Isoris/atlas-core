"""Smoke tests for the 2026-05-26 sites/dosage layout patches in
dosage_bridge.py. Locks in:

  - _load_sites_in_window auto-detects:
        legacy   : `pos\\tmajor\\tminor[\\tmiss\\tdiag]`
        ANGSD    : `chrom\\tpos\\tmajor\\tminor[\\tmiss\\tdiag]`
    on the first data row and reuses the detected column index for the
    rest of the file. Output positions + line_indices match the same
    canonical values for both layouts.

  - _load_dosage_rows slices the TRAILING N cells (not the first N) so
    rows with leading metadata cols (ANGSD-emi style:
    `chrom\\tpos\\tmajor\\tminor\\td_s1\\t...\\td_sN`) align dosages
    correctly to sample indices.

  - _detect_dosage_header inspects trailing N cells too, so the first
    data row of an ANGSD-style file isn't mis-identified as a header.

Both legacy + ANGSD synthetic fixtures must produce identical
positions[] and dosage matrices.

Run:
    python -m unittest atlas-core.server.test_dosage_bridge_layouts
"""

import gzip
import shutil
import tempfile
import unittest
from pathlib import Path

import dosage_bridge as db


def _write_gz(path: Path, text: str) -> None:
    with gzip.open(path, "wt") as f:
        f.write(text)


# Canonical content shared by both fixtures. 5 sites, 4 samples.
_POSITIONS = [100, 200, 300, 400, 500]
_DOSAGES = [
    [0, 1, 2, 1],
    [0, 0, 1, 1],
    [1, 1, 1, 1],
    [2, -1, 0, 1],   # NA in sample 1 (cohort idx 1)
    [0, 2, 2, 2],
]


def _legacy_sites_content() -> str:
    """Legacy 3-col + 2 optional: `pos<TAB>major<TAB>minor<TAB>miss<TAB>diag`."""
    lines = ["pos\tmajor\tminor\tmissingness\tdiagnostic"]   # header row
    for i, p in enumerate(_POSITIONS):
        lines.append(f"{p}\tA\tG\t0.0{i}\t0.1{i}")
    return "\n".join(lines) + "\n"


def _angsd_sites_content() -> str:
    """ANGSD-sites: `chrom<TAB>pos<TAB>major<TAB>minor<TAB>miss<TAB>diag`."""
    lines = ["chrom\tpos\tmajor\tminor\tmissingness\tdiagnostic"]
    for i, p in enumerate(_POSITIONS):
        lines.append(f"C_gar_LG01\t{p}\tA\tG\t0.0{i}\t0.1{i}")
    return "\n".join(lines) + "\n"


def _marker_prefix_sites_content() -> str:
    """marker-prefix: `marker<TAB>chrom<TAB>pos<TAB>allele1<TAB>allele2`.

    The user's local cohort uses this layout (cf. 2026-05-26
    /e/results_inversions/02_dosage_sites/*.sites.tsv.gz). Position
    lives in col 2 — the parser must walk col 0/1/2 to find the first
    int-parseable cell.
    """
    lines = ["marker\tchrom\tpos\tallele1\tallele2"]
    for i, p in enumerate(_POSITIONS):
        lines.append(f"C_gar_LG01_{p}\tC_gar_LG01\t{p}\t2\t0")
    return "\n".join(lines) + "\n"


def _legacy_dosage_content() -> str:
    """4-col tabs of dosage per line. Top row is the sample-ID header."""
    lines = ["s1\ts2\ts3\ts4"]   # header row
    for row in _DOSAGES:
        lines.append("\t".join(str(v) for v in row))
    return "\n".join(lines) + "\n"


def _angsd_dosage_content() -> str:
    """ANGSD-emi: `chrom<TAB>pos<TAB>major<TAB>minor<TAB>d_s1...d_sN`."""
    lines = ["chrom\tpos\tmajor\tminor\ts1\ts2\ts3\ts4"]   # header row
    for i, p in enumerate(_POSITIONS):
        row = "\t".join(str(v) for v in _DOSAGES[i])
        lines.append(f"C_gar_LG01\t{p}\tA\tG\t{row}")
    return "\n".join(lines) + "\n"


class SitesLoaderLayoutTest(unittest.TestCase):
    """_load_sites_in_window must produce identical output for all three
    supported layouts (legacy / ANGSD-sites / marker-prefix)."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="atlas_dosage_layout_"))
        self.legacy_sites = self.tmp / "legacy.sites.tsv.gz"
        self.angsd_sites  = self.tmp / "angsd.sites.tsv.gz"
        self.marker_sites = self.tmp / "marker.sites.tsv.gz"
        _write_gz(self.legacy_sites, _legacy_sites_content())
        _write_gz(self.angsd_sites,  _angsd_sites_content())
        _write_gz(self.marker_sites, _marker_prefix_sites_content())

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_full_range_legacy_layout(self) -> None:
        positions, miss, diag, idx, _stats = db._load_sites_in_window(
            self.legacy_sites, start=0, end=10_000)
        self.assertEqual(positions, _POSITIONS)
        self.assertEqual(idx, [0, 1, 2, 3, 4])
        # Missingness col 3 (legacy) populated for every row.
        self.assertEqual(len(miss), 5)
        for v in miss:
            self.assertIsNotNone(v)

    def test_full_range_angsd_layout(self) -> None:
        positions, miss, diag, idx, _stats = db._load_sites_in_window(
            self.angsd_sites, start=0, end=10_000)
        self.assertEqual(positions, _POSITIONS)
        self.assertEqual(idx, [0, 1, 2, 3, 4])
        # Missingness col offset shifts by 1 for ANGSD layout — should
        # still resolve correctly via pos_col + 3.
        self.assertEqual(len(miss), 5)
        for v in miss:
            self.assertIsNotNone(v)

    def test_window_slice_legacy(self) -> None:
        positions, _, _, idx, _stats = db._load_sites_in_window(
            self.legacy_sites, start=150, end=350)
        self.assertEqual(positions, [200, 300])
        self.assertEqual(idx, [1, 2])

    def test_window_slice_angsd(self) -> None:
        positions, _, _, idx, _stats = db._load_sites_in_window(
            self.angsd_sites, start=150, end=350)
        self.assertEqual(positions, [200, 300])
        self.assertEqual(idx, [1, 2])

    def test_empty_window_both_layouts(self) -> None:
        for sites in (self.legacy_sites, self.angsd_sites, self.marker_sites):
            positions, _, _, idx, _stats = db._load_sites_in_window(
                sites, start=10_000, end=20_000)
            self.assertEqual(positions, [])
            self.assertEqual(idx, [])

    # ------------------------------------------------------------------
    # 2026-05-26: marker-prefix layout (third layout) — user's local cohort
    # ------------------------------------------------------------------

    def test_full_range_marker_prefix_layout(self) -> None:
        positions, miss, diag, idx, _stats = db._load_sites_in_window(
            self.marker_sites, start=0, end=10_000)
        self.assertEqual(positions, _POSITIONS)
        self.assertEqual(idx, [0, 1, 2, 3, 4])
        # marker-prefix file has no missingness/diagnostic cols → all None.
        self.assertEqual(miss, [None] * 5)
        self.assertEqual(diag, [None] * 5)

    def test_window_slice_marker_prefix(self) -> None:
        positions, _, _, idx, _stats = db._load_sites_in_window(
            self.marker_sites, start=150, end=350)
        self.assertEqual(positions, [200, 300])
        self.assertEqual(idx, [1, 2])


class DosageLoaderLayoutTest(unittest.TestCase):
    """_load_dosage_rows must align trailing N cells to sample indices
    regardless of leading metadata columns."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="atlas_dosage_layout_"))
        self.legacy_dos = self.tmp / "legacy.dosage.tsv.gz"
        self.angsd_dos  = self.tmp / "angsd.dosage.tsv.gz"
        _write_gz(self.legacy_dos, _legacy_dosage_content())
        _write_gz(self.angsd_dos,  _angsd_dosage_content())

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_legacy_dosage_full(self) -> None:
        rows = db._load_dosage_rows(self.legacy_dos, [0, 1, 2, 3, 4], n_samples_expected=4)
        self.assertEqual(rows, _DOSAGES)

    def test_angsd_dosage_full(self) -> None:
        # ANGSD has 4 leading metadata cols (chrom, pos, major, minor)
        # before the 4 sample dosages — total 8 cells per row. The slice
        # `cells[-4:]` must pick the trailing 4 (the dosages), not the
        # leading 4 (the metadata).
        rows = db._load_dosage_rows(self.angsd_dos, [0, 1, 2, 3, 4], n_samples_expected=4)
        self.assertEqual(rows, _DOSAGES)

    def test_dosage_subset_legacy(self) -> None:
        rows = db._load_dosage_rows(self.legacy_dos, [1, 3], n_samples_expected=4)
        self.assertEqual(rows, [_DOSAGES[1], _DOSAGES[3]])

    def test_dosage_subset_angsd(self) -> None:
        rows = db._load_dosage_rows(self.angsd_dos, [1, 3], n_samples_expected=4)
        self.assertEqual(rows, [_DOSAGES[1], _DOSAGES[3]])

    def test_na_sentinel_preserved_in_angsd(self) -> None:
        # Row 3 (_DOSAGES[3]) has -1 in slot 1 — must round-trip through
        # the trailing-N slice without contamination from the chrom prefix.
        rows = db._load_dosage_rows(self.angsd_dos, [3], n_samples_expected=4)
        self.assertEqual(rows, [[2, -1, 0, 1]])


class DosageHeaderDetectionTest(unittest.TestCase):
    """_detect_dosage_header must inspect TRAILING N cells, so an ANGSD
    file's first data row (with non-numeric chrom in col 0) is NOT
    mis-classified as a header."""

    def test_legacy_header_detected(self) -> None:
        line = "s1\ts2\ts3\ts4"
        self.assertTrue(db._detect_dosage_header(line, n_samples_expected=4))

    def test_legacy_data_not_a_header(self) -> None:
        line = "0\t1\t2\t-1"
        self.assertFalse(db._detect_dosage_header(line, n_samples_expected=4))

    def test_angsd_header_detected(self) -> None:
        # Leading metadata + sample-ID header on trailing cells.
        line = "chrom\tpos\tmajor\tminor\ts1\ts2\ts3\ts4"
        self.assertTrue(db._detect_dosage_header(line, n_samples_expected=4))

    def test_angsd_data_not_a_header(self) -> None:
        # Leading metadata is non-numeric BUT trailing N cells are ints.
        # Was misclassified as data under the old `len != N` shortcut
        # because total cell count was 8 (≠4), so the function returned
        # False — but the old code then went on to parse the row's
        # leading cells as dosages, scrambling everything. New shape:
        # check trailing N; here trailing 4 are 0/1/2/-1 → data. Good.
        line = "C_gar_LG01\t100\tA\tG\t0\t1\t2\t-1"
        self.assertFalse(db._detect_dosage_header(line, n_samples_expected=4))

    def test_short_row_treated_as_data(self) -> None:
        # When cell count < expected, no per-sample header possible.
        # Loader pads with NA downstream; header-detector returns False.
        line = "0\t1"
        self.assertFalse(db._detect_dosage_header(line, n_samples_expected=4))


class SitesLoaderEdgeCasesTest(unittest.TestCase):
    """Edge cases for the auto-detection path."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="atlas_dosage_layout_"))

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_skips_comment_lines_then_picks_layout(self) -> None:
        # Leading "#" comments + header row, ANGSD layout below.
        path = self.tmp / "with_comments.sites.tsv.gz"
        content = (
            "# generated 2026-05-26\n"
            "# pipeline: angsd\n"
            "chrom\tpos\tmajor\tminor\n"        # header (auto-skipped via ValueError)
            "C_gar_LG01\t100\tA\tG\n"
            "C_gar_LG01\t250\tC\tT\n"
        )
        _write_gz(path, content)
        positions, _, _, idx, _stats = db._load_sites_in_window(path, start=0, end=1000)
        self.assertEqual(positions, [100, 250])
        self.assertEqual(idx, [0, 1])

    def test_empty_file_returns_empty(self) -> None:
        path = self.tmp / "empty.sites.tsv.gz"
        _write_gz(path, "")
        positions, _, _, idx, _stats = db._load_sites_in_window(path, start=0, end=1000)
        self.assertEqual(positions, [])
        self.assertEqual(idx, [])

    def test_header_only_file_returns_empty(self) -> None:
        path = self.tmp / "header_only.sites.tsv.gz"
        _write_gz(path, "chrom\tpos\tmajor\tminor\n")
        positions, _, _, idx, _stats = db._load_sites_in_window(path, start=0, end=1000)
        self.assertEqual(positions, [])
        self.assertEqual(idx, [])


class DosageIntCoercionTest(unittest.TestCase):
    """2026-05-26: _maybe_dosage_int now accepts continuous-float dosages
    (rounded to nearest int + clamped to {0, 1, 2}). Hard-call ints still
    pass through unchanged.
    """

    def test_int_hard_calls_unchanged(self) -> None:
        self.assertEqual(db._maybe_dosage_int("0"),  0)
        self.assertEqual(db._maybe_dosage_int("1"),  1)
        self.assertEqual(db._maybe_dosage_int("2"),  2)
        self.assertEqual(db._maybe_dosage_int("-1"), -1)

    def test_missing_sentinels(self) -> None:
        for s in ("", ".", "NA", "na", "  ", None):
            self.assertEqual(db._maybe_dosage_int(s or ""), -1)

    def test_float_rounded_to_nearest_int(self) -> None:
        # Real values from /e/results_inversions/02_dosage_sites/C_gar_LG01.dosage.tsv.gz
        self.assertEqual(db._maybe_dosage_int("0.000031"), 0)
        self.assertEqual(db._maybe_dosage_int("0.003891"), 0)
        self.assertEqual(db._maybe_dosage_int("0.832779"), 1)
        self.assertEqual(db._maybe_dosage_int("0.999999"), 1)
        self.assertEqual(db._maybe_dosage_int("1.001060"), 1)
        self.assertEqual(db._maybe_dosage_int("1.4"),      1)
        self.assertEqual(db._maybe_dosage_int("1.6"),      2)
        self.assertEqual(db._maybe_dosage_int("1.989731"), 2)
        self.assertEqual(db._maybe_dosage_int("2.0"),      2)

    def test_float_out_of_range_is_missing(self) -> None:
        self.assertEqual(db._maybe_dosage_int("-0.5"), -1)
        self.assertEqual(db._maybe_dosage_int("2.5"),  -1)
        self.assertEqual(db._maybe_dosage_int("99.9"), -1)

    def test_garbage_is_missing(self) -> None:
        self.assertEqual(db._maybe_dosage_int("hello"), -1)
        self.assertEqual(db._maybe_dosage_int("1.0e"),  -1)


if __name__ == "__main__":
    unittest.main()
