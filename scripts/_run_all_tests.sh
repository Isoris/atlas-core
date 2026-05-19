#!/usr/bin/env bash
# Run all action-pipeline test suites across atlas-core and the 5 atlases.
# Helper for local + CI smoke checks; safe to delete once a real CI lands.
#
# Invoke as `bash -l scripts/_run_all_tests.sh` so .bashrc activates the
# conda/mamba env that has fastapi/pandas/httpx. Without `-l`, python3
# resolves to a system interpreter that lacks the deps.
set -u

# Belt-and-braces: also source the user's mambaforge if .bashrc didn't.
if ! python3 -c 'import fastapi' 2>/dev/null; then
  if [ -d "$HOME/mambaforge/bin" ]; then export PATH="$HOME/mambaforge/bin:$PATH"; fi
  if [ -d "$HOME/miniconda3/bin" ];  then export PATH="$HOME/miniconda3/bin:$PATH";  fi
  if [ -d "$HOME/anaconda3/bin" ];   then export PATH="$HOME/anaconda3/bin:$PATH";   fi
fi

echo '--- atlas-core server ---'
cd /mnt/c/Users/quent/Desktop/atlas-core && python3 -m unittest discover -s server -p 'test_*.py' 2>&1 | tail -8

echo '--- atlas-core CLI ---'
python3 -m unittest scripts.test_atlas_action 2>&1 | tail -8

echo '--- atlas-core JS layer_api ---'
node tests/test_layer_api.js 2>&1 | tail -2

echo '--- atlas-core inventory page (pure helpers) ---'
node atlases/core/pages/test_inventory.js 2>&1 | tail -2

echo '--- meiosis-atlas adapter (staging + normalize) ---'
( cd /mnt/c/Users/quent/Desktop/meiosis-atlas/atlases/meiosis/registries && python3 test_adapter_smoke.py 2>&1 | tail -2 )
cd /mnt/c/Users/quent/Desktop/atlas-core

for atlas in inversion-atlas diversity-atlas population-atlas genome-atlas relatedness-atlas; do
  echo "--- $atlas ---"
  cd /mnt/c/Users/quent/Desktop/"$atlas"
  base=${atlas%-atlas}
  if [ "$atlas" = 'inversion-atlas' ]; then
    node atlases/"$base"/shared/test_atlas_server.js 2>&1 | tail -2
  else
    node atlases/"$base"/shared/test_api_client.js 2>&1 | tail -2
  fi
done

# Per-page envelope-aware migrations
echo '--- relatedness-atlas network page (envelope-aware) ---'
cd /mnt/c/Users/quent/Desktop/relatedness-atlas
node atlases/relatedness/pages/hub/test_network_data_source.js 2>&1 | tail -2

echo '--- relatedness-atlas compatibility page (envelope-aware) ---'
node atlases/relatedness/pages/hub/test_compatibility_data_source.js 2>&1 | tail -2

echo '--- genome-atlas page1 (envelope-aware chip wiring) ---'
cd /mnt/c/Users/quent/Desktop/genome-atlas
node atlases/genome/pages/assembly/test_page1_chips.js 2>&1 | tail -2

echo '--- diversity-atlas per_sample/page1 (envelope-provenance badge) ---'
cd /mnt/c/Users/quent/Desktop/diversity-atlas
node atlases/diversity/pages/per_sample/test_samples_provenance.js 2>&1 | tail -2

echo '--- population-atlas structure/page3 (multi-type panel-slot status) ---'
cd /mnt/c/Users/quent/Desktop/population-atlas
node atlases/population/pages/structure/test_page3_envelope_status.js 2>&1 | tail -2

echo '--- inversion-atlas page_overview (workspace-wide envelope inventory) ---'
cd /mnt/c/Users/quent/Desktop/inversion-atlas
node atlases/inversion/pages/catalogue/test_page_overview_inventory.js 2>&1 | tail -2
