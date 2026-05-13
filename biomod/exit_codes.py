"""Named exit codes per the biomod v0 spec.

These integer values are part of the CLI contract — callers (atlas-core,
shell scripts) rely on them. Don't reorder.
"""

SUCCESS              = 0
USER_ERROR           = 1   # bad args, env not found, name clash, etc.
RECIPE_VALIDATION    = 2   # used in later steps
CONDA_FAILED         = 3   # used in later steps
STATE_INCONSISTENT   = 4   # corrupt SQLite, missing files; manual fix
