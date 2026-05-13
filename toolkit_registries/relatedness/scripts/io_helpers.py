"""
Shared loaders for the relatedness/ TSV registries. Stdlib only.

Resolves paths relative to the registry root (the parent of 01_registry/).
"""

from __future__ import annotations

import csv
import gzip
import pathlib
from typing import Dict, List, Optional


def find_registry_root(start: Optional[pathlib.Path] = None) -> pathlib.Path:
    """Walk upward from `start` (or the script's parent) looking for an
    01_registry/ directory. Returns the parent of 01_registry/."""
    p = pathlib.Path(start or pathlib.Path(__file__).resolve().parent).resolve()
    for candidate in [p, *p.parents]:
        if (candidate / "01_registry").is_dir():
            return candidate
    raise SystemExit(
        "could not find 01_registry/ — pass --registry-root explicitly"
    )


def read_tsv(path: pathlib.Path) -> List[Dict[str, str]]:
    """Read a TSV file with a header row. Returns a list of dicts.
    Empty cells are kept as empty strings."""
    rows = []
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        for r in reader:
            rows.append({k: (v if v is not None else "") for k, v in r.items()})
    return rows


def index_by(rows: List[Dict[str, str]], key: str) -> Dict[str, Dict[str, str]]:
    return {r[key]: r for r in rows if r.get(key)}


def load_all(registry_root: pathlib.Path) -> Dict[str, Dict[str, Dict[str, str]]]:
    """Load all six TSVs and return them keyed by id."""
    reg = registry_root / "01_registry"
    out = {
        "sample_sets":      index_by(read_tsv(reg / "sample_sets.tsv"),      "sample_set_id"),
        "group_sets":       index_by(read_tsv(reg / "group_sets.tsv"),       "group_set_id"),
        "interval_sets":    index_by(read_tsv(reg / "interval_sets.tsv"),    "interval_set_id"),
        "site_sets":        index_by(read_tsv(reg / "site_sets.tsv"),        "site_set_id"),
        "input_values":     index_by(read_tsv(reg / "input_values.tsv"),     "value_id"),
        "analysis_results": index_by(read_tsv(reg / "analysis_results.tsv"), "result_id"),
    }
    return out


def open_text(path: pathlib.Path):
    """Open .gz transparently as text."""
    p = pathlib.Path(path)
    if str(p).endswith(".gz"):
        return gzip.open(p, "rt", encoding="utf-8")
    return open(p, "r", encoding="utf-8")


def parse_beagle_header(header_line: str) -> List[str]:
    """Parse a BEAGLE GL header line. Returns the unique sample-id list in
    the order they appear. Standard BEAGLE format puts 3 columns per
    sample after the marker/allele1/allele2 prefix; the per-sample columns
    are typically the sample id repeated 3 times (sometimes with _AA / _Aa
    / _aa suffixes). This function handles both."""
    cols = header_line.rstrip("\n").rstrip("\r").split("\t")
    if len(cols) < 6 or cols[:3] != ["marker", "allele1", "allele2"]:
        # Some pipelines name the leading columns slightly differently.
        # We tolerate any 3-column prefix.
        pass
    sample_cols = cols[3:]
    if len(sample_cols) % 3 != 0:
        raise ValueError(
            f"BEAGLE header has {len(sample_cols)} sample columns; expected a multiple of 3"
        )
    samples = []
    for i in range(0, len(sample_cols), 3):
        triplet = sample_cols[i:i + 3]
        # Strip trailing _AA / _Aa / _aa suffixes if present
        names = [c.rsplit("_", 1)[0] if c.endswith(("_AA", "_Aa", "_aa")) else c for c in triplet]
        if len(set(names)) != 1:
            raise ValueError(
                f"BEAGLE header triplet {i // 3}: expected 3 cols for the same sample, "
                f"got {triplet}"
            )
        samples.append(names[0])
    return samples


def beagle_rows_iter(path: pathlib.Path):
    """Yield (marker, allele1, allele2, n_data_cols) for each data row."""
    with open_text(path) as fh:
        next(fh)  # skip header
        for line in fh:
            line = line.rstrip("\n").rstrip("\r")
            if not line:
                continue
            cols = line.split("\t")
            yield cols[0], cols[1] if len(cols) > 1 else "", cols[2] if len(cols) > 2 else "", len(cols) - 3


def beagle_count_rows(path: pathlib.Path) -> int:
    n = 0
    with open_text(path) as fh:
        next(fh)  # skip header
        for line in fh:
            if line.strip():
                n += 1
    return n


def read_sample_ids(samples_tsv: pathlib.Path) -> List[str]:
    """Read sample_id column from a samples TSV (in file order)."""
    with open(samples_tsv, "r", encoding="utf-8") as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        return [r["sample_id"] for r in reader if r.get("sample_id")]


def read_sites_count(sites_path: pathlib.Path) -> int:
    """Count data rows in a sites TSV(.gz). Header is skipped."""
    n = 0
    with open_text(sites_path) as fh:
        next(fh)
        for line in fh:
            if line.strip():
                n += 1
    return n


def read_groups_sample_ids(groups_tsv: pathlib.Path) -> List[str]:
    with open(groups_tsv, "r", encoding="utf-8") as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        return [r["sample_id"] for r in reader if r.get("sample_id")]


# Pretty status helpers --------------------------------------------------- #

OK   = "✓ OK"
FAIL = "✗ FAIL"
WARN = "⚠ WARN"


def status(passed: bool) -> str:
    return OK if passed else FAIL
