"""Shared base for the four runner stubs (ngsrelate / ngspedigree /
mendelian / popstats).

Each runner module wraps a binary (or a stub) that produces an output
file, then registers it in ``analysis_results.tsv``. The shape is the
same for all four — only the binary call and the output filename
differ. This module exposes the shared scaffold so the per-tool runners
stay tiny.

The stub mode (``_execute_real`` returns ``None``) writes a minimal
contract-true synthetic output file so the chain remains testable end-
to-end without the real binary on PATH. Swap ``_execute_real`` for the
actual ``subprocess.run`` call when you wire your real binary.
"""

from __future__ import annotations

import csv
import datetime
import hashlib
import pathlib
import re
import sys
from typing import Any, Callable, Dict, Optional

# Make biomod/relatedness/scripts/io_helpers.py importable.
_RUNNERS_DIR = pathlib.Path(__file__).resolve().parent
_SCRIPTS_DIR = _RUNNERS_DIR.parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from io_helpers import find_registry_root, load_all  # noqa: E402


COLUMNS = [
    "result_id", "analysis_type", "path", "sample_set_id", "group_set_id",
    "interval_set_id", "site_set_id", "input_value_id", "input_result_id",
    "method_id", "params_id", "hash", "status", "created_at", "notes",
]


def _now_iso() -> str:
    return datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha256(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            b = fh.read(1 << 20)
            if not b:
                break
            h.update(b)
    return "sha256:" + h.hexdigest()


def _next_result_id(regs: Dict, base: str) -> str:
    existing = set(regs["analysis_results"].keys())
    for v in range(1, 1000):
        rid = f"{base}_v{v}"
        if rid not in existing:
            return rid
    return f"{base}_v_TODO"


def _chrom_tag_for_path(manifest: Dict[str, Any], context: Dict[str, Any]) -> str:
    """Best-effort chrom tag for the output filename and result_id base.

    Looks at manifest.target.chromosome → manifest.target.candidate_id →
    manifest.target.interval_set_id → 'global'.
    """
    t = manifest.get("target") or {}
    if t.get("chromosome"):    return t["chromosome"].replace("C_gar_", "")
    if t.get("candidate_id"):  return t["candidate_id"]
    if t.get("interval_set_id"):
        # take the trailing _v1 off if present
        return re.sub(r"_v\d+$", "", t["interval_set_id"])
    return "global"


def append_result_row(workspace: pathlib.Path,
                      manifest: Dict[str, Any],
                      result_id: str,
                      analysis_type: str,
                      output_rel_path: str,
                      sha: str,
                      method_id: str,
                      notes: str = "") -> None:
    """Append a fully-resolved row to analysis_results.tsv."""
    target = manifest.get("target") or {}
    row = {
        "result_id":       result_id,
        "analysis_type":   analysis_type,
        "path":            output_rel_path,
        "sample_set_id":   target.get("sample_set_id", ""),
        "group_set_id":    target.get("group_set_id", ""),
        "interval_set_id": target.get("interval_set_id", ""),
        "site_set_id":     target.get("site_set_id", ""),
        "input_value_id":  target.get("input_value_id", ""),
        "input_result_id": target.get("input_result_id", ""),
        "method_id":       method_id,
        "params_id":       target.get("params_id", ""),
        "hash":            sha,
        "status":          "active",
        "created_at":      _now_iso(),
        "notes":           notes,
    }
    tsv = workspace / "01_registry" / "analysis_results.tsv"
    with tsv.open("a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS, delimiter="\t",
                           lineterminator="\n", quoting=csv.QUOTE_MINIMAL)
        w.writerow(row)


def run_with_stub(
    *,
    manifest:       Dict[str, Any],
    context:        Dict[str, Any],
    analysis_type:  str,
    method_id:      str,
    output_subdir:  str,
    output_ext:     str,
    stub_writer:    Callable[[pathlib.Path], None],
    real_executor:  Optional[Callable[[pathlib.Path, Dict[str, Any], Dict[str, Any]], None]] = None,
) -> Dict[str, Any]:
    """Generic runner harness. Picks the workspace from `context`, decides
    real-vs-stub based on `real_executor`, writes the output file,
    appends a row to analysis_results.tsv, and returns
    ``{produced_layers: [result_id]}``.

    Real-vs-stub: ``real_executor`` is the real-binary call. If it is
    None (the default for our scaffolding) or it raises
    ``FileNotFoundError`` (binary missing), the harness falls back to
    ``stub_writer``. The row's ``notes`` column flags which mode was used.
    """
    ws = pathlib.Path(context.get("workspace_root") or find_registry_root())

    regs = load_all(ws)
    chrom_tag = _chrom_tag_for_path(manifest, context)
    result_id = _next_result_id(regs, f"{analysis_type}_{chrom_tag}")

    out_dir = ws / "04_results" / output_subdir
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{chrom_tag}{output_ext}"

    used_stub = real_executor is None
    if real_executor is not None:
        try:
            real_executor(out_path, manifest, context)
        except FileNotFoundError:
            used_stub = True
    if used_stub:
        stub_writer(out_path)

    sha = _sha256(out_path) if out_path.exists() else ""
    note = (f"stub runner: synthetic output (binary {method_id} not on PATH)"
            if used_stub
            else f"real runner: produced by {method_id}")
    append_result_row(
        workspace=ws,
        manifest=manifest,
        result_id=result_id,
        analysis_type=analysis_type,
        output_rel_path=str(out_path.relative_to(ws)),
        sha=sha,
        method_id=method_id,
        notes=note,
    )
    return {"produced_layers": [result_id], "note": note}
