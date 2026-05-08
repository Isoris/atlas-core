#!/usr/bin/env bash
# One-shot (delete after running): rename inversion-discovery path
# folders to a more descriptive prefix, and copy the win10000.step2000
# pestPG slice into a dedicated inversion slot.
set -euo pipefail

INV=/mnt/e/results_inversions
DIV=/mnt/e/results_diversity

# 1. Rename inversion-discovery folders (3 paths)
declare -A renames=(
  ["path_localpca_GHSL"]="local_PCA_MDS_GHSL"
  ["path_localpca_thetapi"]="local_PCA_MDS_theta_pi"
  ["path_localpca_zblocks"]="local_PCA_MDS_z"
)
for old in "${!renames[@]}"; do
  new="${renames[$old]}"
  if [ -d "$INV/$old" ] && [ ! -e "$INV/$new" ]; then
    echo "==> rename $old -> $new"
    mv "$INV/$old" "$INV/$new"
  elif [ -e "$INV/$new" ]; then
    echo "    (already renamed: $new exists)"
  else
    echo "    (skip: $old not found)"
  fi
done

# 2. Create the win10000.step2000-only pestPG slot for STEP_TR_A/B
mkdir -p "$INV/03_theta_pi_pestPG"

# 3. Copy ONLY the win10000.step2000 pestPG files (per the STEP_TR_A/B
# README — analysis uses that scale exclusively, the other 3 scales
# stay in results_diversity/03_theta_pi for diversity scans).
echo "==> copy *.win10000.step2000.pestPG -> 03_theta_pi_pestPG/"
N=0
for f in "$DIV"/03_theta_pi/*.win10000.step2000.pestPG; do
  [ -f "$f" ] || continue
  cp -p -u "$f" "$INV/03_theta_pi_pestPG/"
  N=$((N+1))
done

echo
echo "=== results_inversions/ ==="
ls "$INV"
echo
printf '  03_theta_pi_pestPG: %s files\n' "$(ls "$INV/03_theta_pi_pestPG" | wc -l)"
printf '  diversity/03_theta_pi (full multiscale): %s files\n' "$(ls "$DIV/03_theta_pi" | wc -l)"
