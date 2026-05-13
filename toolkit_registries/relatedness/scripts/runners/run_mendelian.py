"""Mendelian-inheritance runner (stub). Consumes a pedigree_result and a
BEAGLE, produces a per-trio mendelian-error rate table.
"""

from __future__ import annotations

import pathlib
from typing import Any, Dict

from ._base import run_with_stub


def _stub_writer(out_path: pathlib.Path) -> None:
    out_path.write_text(
        "trio_id\toffspring\tparent1\tparent2\tn_sites\tn_mendelian_errors\trate\n"
        "T1\tGAR003\tGAR001\tGAR002\t6\t0\t0.000\n"
        "T2\tGAR004\tGAR001\tGAR002\t6\t1\t0.167\n"
    )


def run(manifest: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    return run_with_stub(
        manifest       = manifest,
        context        = context,
        analysis_type  = "mendelian",
        method_id      = "mendelian_v1",
        output_subdir  = "mendelian",
        output_ext     = ".mendelian.tsv",
        stub_writer    = _stub_writer,
        real_executor  = None,
    )
