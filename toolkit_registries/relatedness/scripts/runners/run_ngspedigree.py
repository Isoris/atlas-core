"""ngsPedigree runner (stub). Consumes an upstream relatedness_res and
produces a pedigree.tsv.
"""

from __future__ import annotations

import pathlib
from typing import Any, Dict

from ._base import run_with_stub


def _stub_writer(out_path: pathlib.Path) -> None:
    out_path.write_text(
        "offspring\tparent1\tparent2\tlikelihood\n"
        "GAR003\tGAR001\tGAR002\t0.91\n"
        "GAR004\tGAR001\tGAR002\t0.88\n"
    )


def run(manifest: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    return run_with_stub(
        manifest       = manifest,
        context        = context,
        analysis_type  = "ngspedigree",
        method_id      = "ngspedigree_v1",
        output_subdir  = "ngspedigree",
        output_ext     = ".pedigree.tsv",
        stub_writer    = _stub_writer,
        real_executor  = None,
    )
