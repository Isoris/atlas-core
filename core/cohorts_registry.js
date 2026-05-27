// core/cohorts_registry.js
// =====================================================================
// Cohort registry loader + API per SPEC_cohorts_v1.md.
//
// Atlas-core consumes this module at startup to load
// `core/cohorts.registry.json`, validate it against the schema rules
// in SPEC §5, and expose lookup helpers that `cross_atlas_imports.js`
// + page code consult at every cross-atlas read.
//
// Public exports:
//
//   loadCohortsRegistry(coreRoot, opts?) → Promise<registry>
//     Fetch + JSON-parse cohorts.registry.json. coreRoot is the
//     atlas-core base URL (defaults to '/' when running in-browser
//     under atlas-core's StaticFiles mount).
//
//   validateCohortsRegistry(registry, atlasesIndex) → string[]
//     Schema-shape + cross-reference validation per SPEC §5. Returns
//     [] when valid; otherwise an array of one-line error messages.
//     Atlas-core throws on non-empty result (SPEC §10: "loud failure").
//
//   getCohort(registry, cohort_id) → cohort | null
//   listCohorts(registry)         → cohort[]
//   getCohortsForAtlas(registry, atlas_id) → cohort[]
//
//   findHandoff(registry, from_cohort, to_cohort, layer_ref) → handoff | null
//     SPEC §6 + §7 algorithm: regex-match `<atlas_id>.<layer_id>`
//     against every handoff's `via_layer_pattern` and pick the FIRST
//     hit whose from/to pair matches. Returns null when nothing
//     matches (caller decides what to do — error or warn).
//
//   listHandoffs(registry, opts?) → handoff[]
//     Filter by from_cohort / to_cohort / handoff_kind.
// =====================================================================

export async function loadCohortsRegistry(coreRoot, opts) {
  const root = (coreRoot || '').replace(/\/+$/, '');
  const url = (root ? root + '/' : '') + 'core/cohorts.registry.json';
  const fetchFn = (opts && opts.fetch) || (typeof fetch === 'function' ? fetch : null);
  if (!fetchFn) {
    throw new Error('loadCohortsRegistry: no fetch available (pass opts.fetch in Node)');
  }
  const resp = await fetchFn(url);
  if (!resp.ok) {
    throw new Error(`loadCohortsRegistry: GET ${url} → HTTP ${resp.status}`);
  }
  const registry = await resp.json();
  if (!registry || typeof registry !== 'object') {
    throw new Error(`loadCohortsRegistry: ${url} did not parse as an object`);
  }
  return registry;
}

// =====================================================================
// validation — SPEC §5
// =====================================================================

export function validateCohortsRegistry(registry, atlasesIndex) {
  const errors = [];
  if (!registry || typeof registry !== 'object') {
    return ['cohorts.registry.json: payload is not an object'];
  }
  if (typeof registry.version !== 'string' || !/^\d+\.\d+(\.\d+)?$/.test(registry.version)) {
    errors.push(`cohorts.registry.json: missing or malformed 'version' (got ${JSON.stringify(registry.version)})`);
  }
  if (!Array.isArray(registry.cohorts)) {
    errors.push('cohorts.registry.json: cohorts[] missing or not an array');
  }
  if (!Array.isArray(registry.cross_reference_handoffs)) {
    errors.push('cohorts.registry.json: cross_reference_handoffs[] missing or not an array');
  }
  if (errors.length) return errors;   // bail before per-row checks

  // §5.1: every cohort_id unique.
  const seenCohortIds = new Set();
  for (let i = 0; i < registry.cohorts.length; i++) {
    const c = registry.cohorts[i];
    if (!c || typeof c !== 'object') {
      errors.push(`cohorts[${i}]: not an object`);
      continue;
    }
    if (typeof c.cohort_id !== 'string' || !/^[a-z][a-z0-9_]*$/.test(c.cohort_id)) {
      errors.push(`cohorts[${i}]: bad cohort_id ${JSON.stringify(c.cohort_id)}`);
      continue;
    }
    if (seenCohortIds.has(c.cohort_id)) {
      errors.push(`cohorts[${i}] (${c.cohort_id}): duplicate cohort_id`);
    }
    seenCohortIds.add(c.cohort_id);

    // §5.2: reference_id non-empty.
    if (typeof c.reference_id !== 'string' || c.reference_id.length === 0) {
      errors.push(`cohorts[${i}] (${c.cohort_id}): reference_id missing or empty`);
    }

    // §5.3: every atlases[] entry refers to an installed atlas.
    if (!Array.isArray(c.atlases)) {
      errors.push(`cohorts[${i}] (${c.cohort_id}): atlases[] is not an array`);
    } else if (atlasesIndex && Array.isArray(atlasesIndex.atlases)) {
      const installed = new Set(atlasesIndex.atlases);
      for (const aid of c.atlases) {
        if (!installed.has(aid)) {
          errors.push(`cohorts[${i}] (${c.cohort_id}): atlases[] references '${aid}' but it is not in atlases/_index.json (installed: ${[...installed].sort().join(', ')})`);
        }
      }
    }
  }

  // §5.4 + §5.5: handoffs reference known cohorts; via_layer_pattern is a valid regex.
  // §5.6: no two handoffs match the same (from, to, layer) tuple.
  const seenHandoffIds = new Set();
  const handoffByPattern = new Map();   // serialized key → handoff_id
  for (let i = 0; i < registry.cross_reference_handoffs.length; i++) {
    const h = registry.cross_reference_handoffs[i];
    if (!h || typeof h !== 'object') {
      errors.push(`cross_reference_handoffs[${i}]: not an object`);
      continue;
    }
    if (typeof h.handoff_id !== 'string' || !/^[a-z][a-z0-9_]*$/.test(h.handoff_id)) {
      errors.push(`cross_reference_handoffs[${i}]: bad handoff_id ${JSON.stringify(h.handoff_id)}`);
      continue;
    }
    if (seenHandoffIds.has(h.handoff_id)) {
      errors.push(`cross_reference_handoffs[${i}] (${h.handoff_id}): duplicate handoff_id`);
    }
    seenHandoffIds.add(h.handoff_id);

    if (!seenCohortIds.has(h.from_cohort)) {
      errors.push(`handoff '${h.handoff_id}': from_cohort '${h.from_cohort}' is not a registered cohort_id`);
    }
    if (!seenCohortIds.has(h.to_cohort)) {
      errors.push(`handoff '${h.handoff_id}': to_cohort '${h.to_cohort}' is not a registered cohort_id`);
    }
    if (typeof h.via_layer_pattern !== 'string' || h.via_layer_pattern.length === 0) {
      errors.push(`handoff '${h.handoff_id}': via_layer_pattern missing or empty`);
    } else {
      try { new RegExp(h.via_layer_pattern); }
      catch (e) {
        errors.push(`handoff '${h.handoff_id}': via_layer_pattern is not a valid regex (${e.message})`);
      }
    }
    // §5.6 — duplicate tuple detection keyed by (from, to, pattern). We
    // can't iterate all possible layers, but identical patterns sharing
    // the same from/to pair always overlap.
    const key = `${h.from_cohort}|${h.to_cohort}|${h.via_layer_pattern}`;
    if (handoffByPattern.has(key)) {
      errors.push(`handoff '${h.handoff_id}': duplicates pattern of '${handoffByPattern.get(key)}'`);
    }
    handoffByPattern.set(key, h.handoff_id);

    if (typeof h.rationale !== 'string' || h.rationale.length === 0) {
      errors.push(`handoff '${h.handoff_id}': rationale missing (required for audit)`);
    }
  }

  return errors;
}

// =====================================================================
// lookup helpers — SPEC §6
// =====================================================================

export function getCohort(registry, cohort_id) {
  if (!registry || !Array.isArray(registry.cohorts)) return null;
  for (const c of registry.cohorts) {
    if (c && c.cohort_id === cohort_id) return c;
  }
  return null;
}

export function listCohorts(registry) {
  return (registry && Array.isArray(registry.cohorts)) ? registry.cohorts.slice() : [];
}

export function getCohortsForAtlas(registry, atlas_id) {
  if (!registry || !Array.isArray(registry.cohorts)) return [];
  return registry.cohorts.filter(c =>
    c && Array.isArray(c.atlases) && c.atlases.indexOf(atlas_id) >= 0);
}

// Cache compiled regexes keyed by pattern string so per-read lookups
// don't re-compile.
const _regexCache = new Map();
function _compilePattern(pattern) {
  if (_regexCache.has(pattern)) return _regexCache.get(pattern);
  let re;
  try { re = new RegExp(pattern); }
  catch (_) { re = null; }
  _regexCache.set(pattern, re);
  return re;
}

export function findHandoff(registry, from_cohort, to_cohort, layer_ref) {
  if (!registry || !Array.isArray(registry.cross_reference_handoffs)) return null;
  for (const h of registry.cross_reference_handoffs) {
    if (!h) continue;
    if (h.from_cohort !== from_cohort) continue;
    if (h.to_cohort   !== to_cohort)   continue;
    const re = _compilePattern(h.via_layer_pattern);
    if (re && re.test(layer_ref)) return h;
  }
  return null;
}

export function listHandoffs(registry, opts) {
  const o = opts || {};
  if (!registry || !Array.isArray(registry.cross_reference_handoffs)) return [];
  return registry.cross_reference_handoffs.filter(h => {
    if (!h) return false;
    if (o.from_cohort   && h.from_cohort   !== o.from_cohort)   return false;
    if (o.to_cohort     && h.to_cohort     !== o.to_cohort)     return false;
    if (o.handoff_kind  && h.handoff_kind  !== o.handoff_kind)  return false;
    return true;
  });
}
