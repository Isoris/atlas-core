// core/atlas_discovery.js
// =====================================================================
// Finds installed atlases at startup by scanning atlases/*/manifest.json.
//
// Browsers can't list directories, so we use one of two approaches:
//
//   PROD:  the assembly step writes atlases/_index.json which lists
//          every atlas folder. discover() reads that file.
//   DEV:   a small dev server endpoint (/api/_dev/list-atlases) returns
//          the list dynamically. Falls back to _index.json if absent.
//
// Either way, returns: Map<atlas_id, manifest_object>
//
// =====================================================================

// ---------------------------------------------------------------------
// IMPLEMENTATION_NOTE for next chat:
//   ~80 LOC. The discovery itself is trivial; what matters is the
//   error reporting:
//   - Manifest not found → log + skip (graceful degradation)
//   - Manifest malformed → throw (atlas is broken, fix it)
//   - Manifest's atlas_id doesn't match folder name → throw (mismatched
//     packaging, will cause routing bugs later)
//
// ASSEMBLY STEP responsibility:
//   The assembly script (per README_PAIRING §10) MUST emit
//   atlases/_index.json after rsyncing atlases. Format:
//     { "atlases": ["inversion", "diversity", ...] }
//   This is the only file the discovery code needs in production.
// ---------------------------------------------------------------------

export async function discover({ devMode = false } = {}) {
  const ids = await _listAtlases({ devMode });
  const manifests = new Map();
  for (const id of ids) {
    try {
      const manifest = await _loadManifest(id);
      _validateManifest(id, manifest);
      manifests.set(id, manifest);
    } catch (err) {
      console.error(`atlas_discovery: failed to load atlas '${id}':`, err);
      // Don't throw — let the user see the topbar with the working atlases.
    }
  }
  return manifests;
}

async function _listAtlases({ devMode }) {
  if (devMode) {
    try {
      const resp = await fetch('/api/_dev/list-atlases');
      if (resp.ok) return (await resp.json()).atlases;
    } catch { /* fall through */ }
  }
  const resp = await fetch('atlases/_index.json');
  if (!resp.ok) {
    console.warn('atlas_discovery: no atlases/_index.json found. Did you run the assembly step?');
    return [];
  }
  return (await resp.json()).atlases || [];
}

async function _loadManifest(atlas_id) {
  const resp = await fetch(`atlases/${atlas_id}/manifest.json`);
  if (!resp.ok) throw new Error(`HTTP ${resp.status} for atlases/${atlas_id}/manifest.json`);
  return resp.json();
}

function _validateManifest(folder_id, manifest) {
  if (!manifest.atlas_id) {
    throw new Error(`manifest.json in atlases/${folder_id}/ is missing 'atlas_id'`);
  }
  if (manifest.atlas_id !== folder_id) {
    throw new Error(`manifest atlas_id='${manifest.atlas_id}' does not match folder name '${folder_id}'`);
  }
  if (!Array.isArray(manifest.pages)) {
    throw new Error(`atlases/${folder_id}/manifest.json: 'pages' must be an array`);
  }
  // IMPLEMENTATION_NOTE: also validate against a manifest-meta-schema
  // (not the registry meta-schema; manifests are simpler).
}
