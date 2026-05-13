"""popstats runner (stub). Calls ``region_popstats`` (or
``/api/popstats/groupwise`` on the live server) and writes a windowed
FST / dxy / piN / piS table.

Real wiring options (when you swap ``_execute_real``):

  (a) Direct binary: subprocess.run([region_popstats_path, ...])
  (b) Via the atlas server: POST to /api/popstats/groupwise (already
      wired in atlas_server.py)

The stub writes a contract-true synthetic table for the manuscript
Path B demo.
"""

from __future__ import annotations

import pathlib
from typing import Any, Dict

from ._base import run_with_stub


def _stub_writer(out_path: pathlib.Path) -> None:
    out_path.write_text(
        "chrom\tstart_bp\tend_bp\tn_sites\tfst\tdxy\tpiN\tpiS\n"
        "C_gar_LG28\t1000000\t1005000\t3\t0.18\t0.0042\t0.0008\t0.0016\n"
        "C_gar_LG28\t1005000\t1010000\t3\t0.22\t0.0051\t0.0011\t0.0019\n"
    )


def run(manifest: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    return run_with_stub(
        manifest       = manifest,
        context        = context,
        analysis_type  = "popstats",
        method_id      = "region_popstats_v0_4",
        output_subdir  = "popstats",
        output_ext     = ".popstats.tsv",
        stub_writer    = _stub_writer,
        real_executor  = None,
    )
