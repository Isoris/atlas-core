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

  safe_key="$(echo "$key" | sed 's/[^A-Za-z0-9_]/_/g')"
  kv_keys+=("$safe_key")
  declare "kv_$safe_key=$val"
done < "$CONFIG"

# Resolve a path: absolute as-is, relative resolved against atlas-core/build/.
resolve_path() {
  case "$1" in
    /*) echo "$1" ;;
    *)  echo "$(cd "$SCRIPT_DIR" && cd "$1" 2>/dev/null && pwd || echo "$SCRIPT_DIR/$1")" ;;
  esac
}

# 2026-05-29: assemble was slow because every run did a FULL recopy
# (tar for atlas-core, rm -rf + cp -r per atlas). On WSL/DrvFs (/mnt/c)
# each file write is a Windows-driver round-trip, so rewriting unchanged
# files dominated the runtime. rsync's size+mtime quick-check skips
# unchanged files, making re-runs near-instant. We fall back to the old
# tar/cp path if rsync isn't installed.
#
# rsync flags: -r recurse, -l preserve symlinks, -t preserve mtimes.
# -t is REQUIRED — the incremental quick-check compares size+mtime, so
# without it every re-run recopies everything. We deliberately omit
# -p/-o/-g (perms/owner/group): DrvFs maps those to fixed values, so
# preserving them just adds slow, noisy chmod/chown round-trips.
have_rsync=0
if command -v rsync >/dev/null 2>&1; then have_rsync=1; fi

# Copy atlas-core's root into the workspace, EXCLUDING build/.git/atlases.
# atlases/ is handled per-atlas (steps 2b/3) so external atlases copied
# later aren't clobbered. No --delete here: stale root files lingering is
# the same harmless trade-off the old tar had, and --delete would churn
# start.sh/.atlas.env (recreated in steps 6/7) on every run.
sync_root() {
  if [ "$have_rsync" -eq 1 ]; then
    rsync -rlt \
      --exclude='/.git' --exclude='/build' --exclude='/atlases' \
      "$ATLAS_CORE/" "$WORKSPACE/"
  else
    ( cd "$ATLAS_CORE" && tar -cf - --exclude=build --exclude=.git --exclude=atlases . ) \
      | ( cd "$WORKSPACE" && tar -xf - )
  fi
}

# Copy one atlas package (atlases/<aid>/) into the workspace, pruning
# files removed upstream (--delete) but PRESERVING the generated specs/
# dir, which index_specs.py writes after the copy — without the exclude,
# --delete would wipe it every run.
sync_atlas() {
  local src="$1" dst="$2"
  mkdir -p "$dst"
  if [ "$have_rsync" -eq 1 ]; then
    rsync -rlt --delete --exclude='/specs' "$src" "$dst/"
  else
    # fallback: wipe everything except specs/, then full copy.
    find "$dst" -mindepth 1 -maxdepth 1 ! -name specs -exec rm -rf {} + 2>/dev/null || true
    cp -r "$src". "$dst/"
  fi
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
# 2026-05-20: was `rm -rf $WORKSPACE && mkdir -p ...` which broke any
# running dev server's directory handle (the inode of $WORKSPACE changes
# on wipe+recreate, so Starlette's StaticFiles loses its mount target
# until restart). Quentin's report: a fresh assemble produced 404s on
# every page fragment until the user restarted start.sh.
# New strategy: keep $WORKSPACE intact; sync into it in place. Each atlas
# subdirectory is rsync'd with --delete (steps 2b/3) so stale files from
# renamed/removed pages don't linger. Root-level files are synced without
# --delete, so files removed upstream may linger at the root (acceptable
# trade-off vs. breaking the running server, same as the old tar copy).
if [ ! -d "$WORKSPACE" ]; then
  echo "==> creating $WORKSPACE/"
  mkdir -p "$WORKSPACE/atlases"
else
  echo "==> refreshing $WORKSPACE/ in place (server-friendly)"
  mkdir -p "$WORKSPACE/atlases"
fi

# 2. Copy atlas-core contents into workspace root ------------------------
echo "==> copying atlas_core: $ATLAS_CORE"
sync_root

# spec indexers run in the background (one python3 per atlas); we collect
# their PIDs and wait before writing _index.json. Parallelizing ~25
# interpreter startups is a meaningful chunk of the runtime on DrvFs.
spec_pids=()

# 2b. Pick up atlases bundled inside atlas-core itself -------------------
# atlas-core may ship its own atlas package(s) under atlas-core/atlases/<id>/
# (e.g. the `core` atlas — the registry-dashboard pages: conversation, action,
# registries, catalogue). Step 2 excludes /atlases from the root copy, so we
# sync each bundled atlas here (and record its id at the FRONT of atlas_ids,
# i.e. first in atlases/_index.json, which makes it the default the router
# opens).
atlas_ids=()
if [ -d "$ATLAS_CORE/atlases" ]; then
  for sub in "$ATLAS_CORE/atlases"/*/; do
    [ -d "$sub" ] || continue
    aid="$(basename "$sub")"
    [ -f "$sub/manifest.json" ] || continue
    echo "==> bundled atlas $aid: $WORKSPACE/atlases/$aid/ (from atlas-core)"
    sync_atlas "$sub" "$WORKSPACE/atlases/$aid"
    atlas_ids+=("$aid")
    # SPECs for bundled atlases come from atlas-core's repo root
    # (atlas-core keeps them under docs/SPEC_*.md, not specs_done/).
    python3 "$SCRIPT_DIR/index_specs.py" "$aid" "$ATLAS_CORE" \
      "$WORKSPACE/atlases/$aid/specs" &
    spec_pids+=("$!")
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
    if [ ! -f "$sub/manifest.json" ]; then
      # Not an atlas package. Underscore-prefixed dirs (e.g. _shared/) hold
      # cross-atlas modules imported as ../../../_shared/x.js, so they must
      # land in $WORKSPACE/atlases/<name> for the import to resolve — but
      # they carry no manifest, no id, and no specs. Copy those through;
      # skip any other non-atlas dir. 2026-05-29: evolution-atlas/atlases/
      # _shared/ was 404ing because the manifest gate dropped it.
      case "$aid" in
        _*) echo "==> copying shared dir $aid: $WORKSPACE/atlases/$aid/ (from $key)"
            sync_atlas "$sub" "$WORKSPACE/atlases/$aid" ;;
      esac
      continue
    fi
    echo "==> copying atlas $aid: $sub"
    # 2026-05-20: prune THIS atlas's stale files (renamed/removed pages)
    # while keeping the workspace-root inode stable (see step 1 comment).
    # sync_atlas does an incremental rsync --delete (preserving specs/),
    # so unchanged files aren't rewritten — the big DrvFs speedup.
    sync_atlas "$sub" "$WORKSPACE/atlases/$aid"
    atlas_ids+=("$aid")
    # Index specs_done/ + specs_todo/ + SPECS.md at the source repo root
    # (NOT inside atlases/<aid>/). Fail-soft: missing folders just yield an
    # empty section in specs_index.json; never aborts the assemble.
    python3 "$SCRIPT_DIR/index_specs.py" "$aid" "$src" \
      "$WORKSPACE/atlases/$aid/specs" &
    spec_pids+=("$!")
  done
done

# Wait for all background spec indexers before writing _index.json.
if [ "${#spec_pids[@]}" -gt 0 ]; then
  for pid in "${spec_pids[@]}"; do wait "$pid" || true; done
fi

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

# 5. Data folder — server handles external roots natively, no symlinks. ----
# Earlier versions of assemble.sh symlinked $WORKSPACE/data → $DATA_DIR
# and $WORKSPACE/$DATA_DIR → $DATA_DIR so the static-file mount could
# serve files outside the workspace tree. Two reasons those are gone now:
#
#   1. WSL/DrvFs (Windows /mnt/c) rejects cross-drive symlinks with
#      EPERM unless WSL is launched as Administrator with metadata mount
#      options — `ln -s` failing was the visible symptom of "Operation
#      not permitted" during assemble.
#   2. They never actually worked for serving content anyway: Starlette's
#      StaticFiles path-traversal guard realpath's the target and rejects
#      anything outside the mount's own directory, so a symlink pointing
#      OUT of $WORKSPACE returned 404 silently. The fix (in
#      atlas_server._bootstrap_external_root_mounts) was to mount the
#      external prefix as its OWN StaticFiles entry — see the docstring
#      on that function. With native mounts in place the symlinks are
#      pure cruft.
#
# We still record kv_data so start.sh / the server can pass it through
# as an env or use it for sanity reporting, but no filesystem links are
# created here. If a future workflow needs $WORKSPACE/data to be a real
# directory (rather than nothing), copy your data in by hand or add a
# separate config knob — don't bring the symlinks back.
if [ "${kv_data:-}" ]; then
  DATA_DIR="$(resolve_path "$kv_data")"
  if [ -d "$DATA_DIR" ]; then
    echo "==> external data root: $DATA_DIR (served by atlas_server.py via _bootstrap_external_root_mounts)"
  else
    echo "  ! data path not found: $DATA_DIR (server will skip native mount for this prefix)"
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
