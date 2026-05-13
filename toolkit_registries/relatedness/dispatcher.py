"""dispatcher.py — atlas-core's reference dispatcher for the relatedness workspace.

Implements the contract that `server/action_endpoints.py` looks for:

    def dispatch_action(manifest: dict, context: dict) -> dict:
        return {"produced_layers": [layer_id, ...]}

Drop this file at the **workspace root** alongside ``01_registry/``,
``02_sets/``, ``03_inputs/``, ``04_results/``. The atlas server discovers
it at ``<workspace>/dispatcher.py`` and calls ``dispatch_action`` from
``POST /api/actions``. With this file present, the atlas server is no
longer in "documentation mode" — every manifest actually runs.

Routes by ``manifest.type``:

  run_ngsrelate     → scripts.runners.run_ngsrelate
  run_ngspedigree   → scripts.runners.run_ngspedigree
  run_mendelian     → scripts.runners.run_mendelian
  run_popstats      → scripts.runners.run_popstats

Each runner takes the manifest, produces output files under
``04_results/<analysis_type>/``, and registers a row in
``01_registry/analysis_results.tsv``. The dispatcher returns the
``result_id`` of the new row in ``produced_layers``.

For tomorrow's VS work: copy this folder into your real workspace,
replace the synthetic TSVs with your real ones, swap each runner's
``_execute_real`` for the actual binary call (defaults are stub
generators that produce contract-true synthetic output).

This module is stdlib-only. Each runner is a sibling module under
``scripts/runners/``.
"""

from __future__ import annotations

import importlib
import pathlib
import sys
from typing import Any, Dict


_HERE = pathlib.Path(__file__).resolve().parent

# Make `scripts.runners.*` importable when this file is run from any cwd
# (the action endpoint imports it by file path, not as a package).
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))


# Manifest.type → runner module under scripts.runners.<X>
_RUNNER_MODULES = {
    "run_ngsrelate":   "scripts.runners.run_ngsrelate",
    "run_ngspedigree": "scripts.runners.run_ngspedigree",
    "run_mendelian":   "scripts.runners.run_mendelian",
    "run_popstats":    "scripts.runners.run_popstats",
}


def dispatch_action(manifest: Dict[str, Any],
                    context: Dict[str, Any]) -> Dict[str, Any]:
    """Server-side dispatcher entry point. Routes by manifest.type."""
    atype = manifest.get("type", "")
    mod_path = _RUNNER_MODULES.get(atype)
    if mod_path is None:
        raise RuntimeError(
            f"unknown action type '{atype}'. Wired types: "
            f"{', '.join(sorted(_RUNNER_MODULES))}"
        )
    mod = importlib.import_module(mod_path)
    # Each runner exposes a `run(manifest, context) -> dict` callable.
    return mod.run(manifest, context)
