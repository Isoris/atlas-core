"""ngsRelate runner (stub). Wraps the ngsRelate binary call; when the
binary is absent on PATH, writes contract-true synthetic output so the
chain stays testable end-to-end.

Real wiring: replace ``_execute_real`` with a ``subprocess.run`` of the
real ngsRelate binary (typically reading the BEAGLE.gz pointed at by
``manifest.target.input_value_id`` and writing a .res to ``out_path``).
"""

from __future__ import annotations

import pathlib
from typing import Any, Dict

from ._base import run_with_stub


def _stub_writer(out_path: pathlib.Path) -> None:
    """Write a minimal .res with the standard ngsRelate column shape."""
    out_path.write_text(
        "a\tb\tnSites\ttheta\trab\tIBS0\tIBS1\tIBS2\tKING\n"
        "0\t1\t6\t0.05\t0.10\t100\t250\t150\t0.02\n"
        "0\t2\t6\t0.04\t0.09\t60\t140\t90\t0.01\n"
    )


def run(manifest: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    return run_with_stub(
        manifest       = manifest,
        context        = context,
        analysis_type  = "ngsrelate",
        method_id      = "ngsrelate_v2",
        output_subdir  = "ngsrelate",
        output_ext     = ".res",
        stub_writer    = _stub_writer,
        real_executor  = None,   # stub-only for the scaffolding PR
    )
