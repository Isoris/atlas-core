#!/usr/bin/env bash
# atlas-core/build/start.sh
# =====================================================================
# Launch the unified atlas server.
#
# This script is normally invoked from the assembled workspace, where
# assemble.sh / link.sh has placed it (or a symlink to it) at
# atlas-workspace/start.sh. You run it as:
#
#     cd atlas-workspace
#     bash start.sh
#
# That's it. The server then serves:
#
#     http://localhost:8000/                  ← the atlas UI
#     http://localhost:8000/api/popstats/...  ← compute endpoints
#     http://localhost:8000/file/...          ← read/write project files
#     http://localhost:8000/health            ← server status
#
# All from ONE port, ONE process.
#
# ENV VARS (optional)
# -------------------
#   ATLAS_PORT=8000            port to bind (default 8000)
#   ATLAS_RELOAD=1             auto-reload server on Python edits (dev only)
#   ATLAS_POPSTATS_CONFIG=...  enable the popstats compute subsystem by
#                              passing a config YAML; without this, popstats
#                              endpoints return 503 and everything else still
#                              works (UI, /file, /compute).
# =====================================================================

set -euo pipefail

# Resolve the workspace root: the folder this script lives in.
# (When invoked via a symlink, BASH_SOURCE points at the link path; we
# follow it so $WORKSPACE_ROOT is the real on-disk workspace.)
SCRIPT_PATH="${BASH_SOURCE[0]}"
while [ -L "$SCRIPT_PATH" ]; do
  SCRIPT_PATH="$(readlink "$SCRIPT_PATH")"
done
WORKSPACE_ROOT="$(cd "$(dirname "$SCRIPT_PATH")" && pwd)"

# Pick up any env vars assemble.sh wrote (e.g. ATLAS_POPSTATS_CONFIG from
# atlas.config's server_config setting).
if [ -f "$WORKSPACE_ROOT/.atlas.env" ]; then
  set -a
  . "$WORKSPACE_ROOT/.atlas.env"
  set +a
fi

# The unified server now lives in atlas-core (see atlas-core/server/README.md).
# After assemble.sh, it sits at $WORKSPACE_ROOT/server/atlas_server.py.
SERVER_PY="$WORKSPACE_ROOT/server/atlas_server.py"

# Back-compat: if an old assembled workspace still has the previous
# atlases/<id>/server/atlas_server.py (or popstats_server.py) layout,
# fall through to it.
if [ ! -f "$SERVER_PY" ]; then
  for cand in "$WORKSPACE_ROOT"/atlases/*/server/atlas_server.py \
              "$WORKSPACE_ROOT"/atlases/*/server/popstats_server.py; do
    [ -f "$cand" ] || continue
    SERVER_PY="$cand"
    break
  done
fi

if [ ! -f "$SERVER_PY" ]; then
  echo "ERROR: server entry point not found in this workspace."
  echo "       Looked for: $WORKSPACE_ROOT/server/atlas_server.py"
  echo "       (and the legacy atlases/*/server/atlas_server.py fallback)"
  echo "       Did assemble.sh complete successfully?"
  exit 1
fi

SERVER_DIR="$(dirname "$SERVER_PY")"

# Sanity: are the Python deps installed?
if ! python3 -c "import fastapi, uvicorn" 2>/dev/null; then
  echo "Python deps missing. Install with:"
  echo "    pip install -r $SERVER_DIR/requirements.txt"
  echo "(or, if you don't want to clutter the system Python):"
  echo "    pip install --user -r $SERVER_DIR/requirements.txt"
  exit 1
fi

PORT="${ATLAS_PORT:-8000}"
RELOAD_FLAG=""
if [ "${ATLAS_RELOAD:-}" = "1" ]; then
  RELOAD_FLAG="--reload"
fi

POPSTATS_CONFIG_FLAG=""
if [ -n "${ATLAS_POPSTATS_CONFIG:-}" ]; then
  POPSTATS_CONFIG_FLAG="--config $ATLAS_POPSTATS_CONFIG"
fi

echo "==> starting atlas server on http://127.0.0.1:$PORT/"
echo "    workspace_root: $WORKSPACE_ROOT"
echo "    server:         $SERVER_PY"
echo "    Ctrl+C to stop."
echo

# cd into the server folder so its sibling imports (ld_endpoint,
# dosage_bridge) resolve. Pass --workspace-root and --project-root so
# the server serves the UI from the workspace AND treats it as the
# project root for /file IO.
cd "$SERVER_DIR"
SERVER_BASENAME="$(basename "$SERVER_PY")"
exec python3 "$SERVER_BASENAME" \
  --workspace-root "$WORKSPACE_ROOT" \
  --project-root   "$WORKSPACE_ROOT" \
  --host 127.0.0.1 \
  --port "$PORT" \
  $POPSTATS_CONFIG_FLAG \
  $RELOAD_FLAG
