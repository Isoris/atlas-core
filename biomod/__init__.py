"""biomod — module catalog + package manager for bioinformatics analyses.

v0 spec is staged in seven steps. This package currently ships **step 1**
(environment commands: create / activate / deactivate / env list /
env remove). See README.md for the staged roadmap.

Non-negotiable v0 design rules (per the brief):
  1. No `biomod run` command, ever. biomod is a catalog + package
     manager, not an orchestrator.
  2. Recipe schema is the contract. Renaming/removing fields requires
     a schema_version bump.
  3. `derive --reason` is required (when derive lands in step 5).
"""

__version__ = "0.1.0-step1"
