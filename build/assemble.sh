#!/usr/bin/env bash
# atlas-core/build/assemble.sh
# =====================================================================
# Read atlas.config, copy each listed atlas into atlas-workspace/,
# wire data + server_config, done.
#
# Run from anywhere:
#     bash atlas-core/build/assemble.sh
#
# Re-run any time you've made changes in any source folder.
# =====================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CONFIG="$SCRIPT_DIR/atlas.config"

if [ ! -f "$CONFIG" ]; then
  echo "ERROR: $CONFIG not found."
  echo "       Copy atlas.config.example to atlas.config and edit the paths."
  exit 1
fi

# Parse "key = value" lines, ignore comments and blanks.
# Result: $kv_keys (array of keys), $kv_<key> (value variables).
kv_keys=()
while IFS= read -r line; do
  line="${line%%#*}"                          # strip comments
  line="$(echo "$line" | sed 's/^ *//;s/ *$//')"  # trim
  [ -z "$line" ] && continue
  key="${line%%=*}"; key="$(echo "$key" | sed 's/ *$//')"
  val="${line#*=}";  val="$(echo "$val" | sed 's/^ *//')"
  kv_keys+=("$key")
  declare "kv_$key=$val"
done < "$CONFIG"

# Resolve a path: absolute as-is, relative resolved against atlas-core/build/.
resolve_path() {
  case "$1" in
    /*) echo "$1" ;;
    *)  echo "$(cd "$SCRIPT_DIR" && cd "$1" 2>/dev/null && pwd || echo "$SCRIPT_DIR/$1")" ;;
  esac
}

# atlas_core is required, plus at least one atlas_<other>.
[ "${kv_atlas_core:-}" ] || { echo "ERROR: atlas.config missing 'atlas_core ='"; exit 1; }

ATLAS_CORE="$(resolve_path "$kv_atlas_core")"
[ -d "$ATLAS_CORE" ]  || { echo "ERROR: atlas_core path does not exist: $ATLAS_CORE"; exit 1; }
[ -f "$ATLAS_CORE/index.html" ] || { echo "ERROR: $ATLAS_CORE has no index.html"; exit 1; }

# Workspace lives next to atlas-core (i.e., the parent folder).
PARENT="$(cd "$ATLAS_CORE/.." && pwd)"
WORKSPACE="$PARENT/atlas-workspace"

# 1. Clean ----------------------------------------------------------------
echo "==> cleaning $WORKSPACE/"
rm -rf "$WORKSPACE"
mkdir -p "$WORKSPACE/atlases"

# 2. Copy atlas-core contents into workspace root ------------------------
echo "==> copying atlas_core: $ATLAS_CORE"
( cd "$ATLAS_CORE" && tar -cf - --exclude=build --exclude=.git . ) \
  | ( cd "$WORKSPACE" && tar -xf - )

# 2b. Pick up atlases bundled inside atlas-core itself -------------------
# atlas-core may ship its own atlas package(s) under atlas-core/atlases/<id>/
# (e.g. the `core` atlas — the registry-dashboard pages: conversation, action,
# registries, catalogue). The tar copy in step 2 already moved them into
# $WORKSPACE/atlases/<id>/; here we just record their ids so they end up at
# the FRONT of atlas_ids (i.e. first in atlases/_index.json, which makes
# them the default atlas the router opens).
atlas_ids=()
if [ -d "$WORKSPACE/atlases" ]; then
  for sub in "$WORKSPACE/atlases"/*/; do
    [ -d "$sub" ] || continue
    aid="$(basename "$sub")"
    [ -f "$sub/manifest.json" ] || continue
    echo "==> bundled atlas $aid: $sub (from atlas-core)"
    atlas_ids+=("$aid")
  done
fi

# 3. Copy each other atlas -----------------------------------------------
for key in "${kv_keys[@]}"; do
  case "$key" in
    atlas_core|data|server_config) continue ;;
    atlas_*) ;;
    *) continue ;;
  esac
  src_var="kv_$key"
  src="$(resolve_path "${!src_var}")"
  if [ ! -d "$src" ]; then
    echo "  ! skipping $key — path not found: $src"
    continue
  fi
  # Each atlas folder must have atlases/<id>/manifest.json inside.
  if [ ! -d "$src/atlases" ]; then
    echo "  ! skipping $key — $src has no atlases/ subfolder"
    continue
  fi
  for sub in "$src/atlases"/*/; do
    [ -d "$sub" ] || continue
    aid="$(basename "$sub")"
    [ -f "$sub/manifest.json" ] || continue
    echo "==> copying atlas $aid: $sub"
    cp -r "$sub" "$WORKSPACE/atlases/"
    atlas_ids+=("$aid")
  done
done

# 4. Write atlases/_index.json -------------------------------------------
# Dedupe atlas_ids while preserving order: if an external atlas in step 3
# shadows a bundled one from step 2b, the bundled id stays at the front
# (which keeps it as the default) and the duplicate from step 3 is dropped.
deduped_ids=()
declare -A seen_ids=()
for aid in "${atlas_ids[@]}"; do
  if [ -z "${seen_ids[$aid]:-}" ]; then
    deduped_ids+=("$aid")
    seen_ids[$aid]=1
  fi
done

{
  echo "{"
  echo "  \"_doc\":          \"Atlas list. Written by assemble.sh. Bundled atlases (shipped inside atlas-core/atlases/) come first, then external atlases in atlas.config order. The router opens the first listed atlas as the default.\","
  echo "  \"_assembled_at\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\","
  echo -n "  \"atlases\":      ["
  first=1
  for aid in "${deduped_ids[@]}"; do
    if [ $first -eq 1 ]; then first=0; else echo -n ","; fi
    echo -n "\"$aid\""
  done
  echo "]"
  echo "}"
} > "$WORKSPACE/atlases/_index.json"

# 5. Symlink the data folder into the workspace -------------------------
# Two complementary links, both pointing at the same target:
#   (a) $WORKSPACE/data            -> $DATA_DIR     (legacy convenience link)
#   (b) $WORKSPACE/$DATA_DIR       -> $DATA_DIR     (full-path mirror)
# Link (b) lets master_config.yaml use absolute paths like
# /mnt/e/results_inversions/01_beagle and have the unified server's
# static mount serve them: a fetch for /mnt/e/X resolves to
# $WORKSPACE/mnt/e/X, which (b) bridges back to the real $DATA_DIR/X.
if [ "${kv_data:-}" ]; then
  DATA_DIR="$(resolve_path "$kv_data")"
  if [ -d "$DATA_DIR" ]; then
    # (a) legacy convenience link
    ln -s "$DATA_DIR" "$WORKSPACE/data"
    echo "==> linked data: $DATA_DIR → $WORKSPACE/data"
    # (b) full-path mirror (only for absolute DATA_DIR, which it always is
    # after resolve_path; but be explicit for clarity).
    case "$DATA_DIR" in
      /*)
        PARENT_DIR="$(dirname "$DATA_DIR")"
        BASENAME="$(basename "$DATA_DIR")"
        mkdir -p "$WORKSPACE$PARENT_DIR"
        ln -s "$DATA_DIR" "$WORKSPACE$PARENT_DIR/$BASENAME"
        echo "==> mirrored absolute path: $DATA_DIR → $WORKSPACE$PARENT_DIR/$BASENAME"
        ;;
    esac
  else
    echo "  ! data path not found: $DATA_DIR (skipping links)"
  fi
fi

# 6. Drop start.sh into the workspace ------------------------------------
cp "$SCRIPT_DIR/start.sh" "$WORKSPACE/start.sh"
chmod +x "$WORKSPACE/start.sh"

# 7. Pass server_config through env file (start.sh reads it) -------------
if [ "${kv_server_config:-}" ]; then
  CFG_PATH="$(resolve_path "$kv_server_config")"
  echo "ATLAS_POPSTATS_CONFIG=$CFG_PATH" > "$WORKSPACE/.atlas.env"
  echo "==> popstats config: $CFG_PATH"
fi

# 8. Done ----------------------------------------------------------------
echo
echo "==> workspace: $WORKSPACE"
echo "    atlases:   ${atlas_ids[*]:-<none>}"
echo
echo "Next:"
echo "    cd $WORKSPACE"
echo "    bash start.sh"
echo "    # http://localhost:8000/"
