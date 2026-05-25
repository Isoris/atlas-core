// core/cross_atlas_imports.js
// =====================================================================
// Cross-atlas read-time cohort policer per SPEC_cohorts_v1.md §7.
//
// Every cross-atlas read (atlas A reading atlas B's layer) flows
// through `read({ consumer_atlas_id, layer_ref, ... })`. The resolver:
//
//   1. Splits `layer_ref` into `<producer_atlas_id>.<layer_id>`.
//   2. Looks up the producer atlas's layer entry to read its
//      `cohort_id` declaration.
//   3. Looks up the consumer's declared cohorts (via the cohorts
//      registry, filtered by `consumer_atlas_id`).
//   4. If producer_cohort ∈ consumer_cohorts → pass (same-cohort read).
//   5. Else, search for a matching handoff in cohorts.registry.json.
//      - Hit → pass + attach `handoff_used` to meta.
//      - Miss + `allow_cohort_mismatch === true` → pass + log warning
//        (the Phase-0a soft-default).
//      - Miss + `allow_cohort_mismatch === false` → throw
//        `CohortMismatchError` with the SPEC-§10 message template.
//   6. Resolve the data via the standard `Registry.resolve()` path.
//
// Phase 0a vs 0b:
//
//   SPEC_cohorts_v1 §11 prescribes a two-step rollout. This module
//   ships Phase 0a (allow_cohort_mismatch defaults to TRUE, only logs
//   a warning on cohort cross). Atlas authors get a window to declare
//   handoffs without breakage. Phase 0b flips the default to FALSE.
//
//   To opt INTO strict mode early, atlases can pass
//   `cross_atlas_imports.setStrictMode(true)` at boot. The flag is
//   read by every `read()` call; per-call `allow_cohort_mismatch` is
//   still honoured (escape hatch).
//
// Public exports:
//
//   class CohortMismatchError extends Error
//   class LayerNotFoundError extends Error
//   class AtlasNotInstalledError extends Error
//
//   setStrictMode(enabled: boolean)
//   isStrictMode() → boolean
//
//   read({
//     consumer_atlas_id,       // string, required
//     layer_ref,               // '<atlas_id>.<layer_id>', required
//     registry,                // Registry instance (atlas-core registry_core)
//     cohorts_registry,        // cohorts registry object (loadCohortsRegistry result)
//     args,                    // forwarded to registry.resolve()
//     allow_cohort_mismatch,   // optional per-call escape; default = global strict flag
//     knob_hash,               // optional workflow-staleness check (SPEC §8)
//   }) → Promise<{ data, meta }>
// =====================================================================

import { findHandoff, getCohort, getCohortsForAtlas } from './cohorts_registry.js';

// ---------------------------------------------------------------------
// Errors
// ---------------------------------------------------------------------

export class CohortMismatchError extends Error {
  constructor(message, detail) {
    super(message);
    this.name = 'CohortMismatchError';
    this.detail = detail || null;
  }
}

export class LayerNotFoundError extends Error {
  constructor(layer_ref) {
    super(`cross_atlas_imports: layer not found: '${layer_ref}'`);
    this.name = 'LayerNotFoundError';
    this.layer_ref = layer_ref;
  }
}

export class AtlasNotInstalledError extends Error {
  constructor(atlas_id) {
    super(`cross_atlas_imports: atlas '${atlas_id}' is not installed (not in atlases/_index.json)`);
    this.name = 'AtlasNotInstalledError';
    this.atlas_id = atlas_id;
  }
}

// ---------------------------------------------------------------------
// Phase 0a / 0b strict-mode flag
// ---------------------------------------------------------------------
// Default false === "Phase 0a" === permissive (warn instead of throw).
// Flipping to true === "Phase 0b" === strict (throw on unhandoff'd mismatch).

let _strictMode = false;

export function setStrictMode(enabled) {
  _strictMode = !!enabled;
}

export function isStrictMode() {
  return _strictMode;
}

// ---------------------------------------------------------------------
// Public read() — the policer + resolver
// ---------------------------------------------------------------------

export async function read(opts) {
  if (!opts || typeof opts !== 'object') {
    throw new TypeError('cross_atlas_imports.read: opts object required');
  }
  const {
    consumer_atlas_id,
    layer_ref,
    registry,
    cohorts_registry,
    args,
    knob_hash,
  } = opts;
  const allow_mismatch = (opts.allow_cohort_mismatch !== undefined)
    ? !!opts.allow_cohort_mismatch
    : !_strictMode;

  if (typeof consumer_atlas_id !== 'string' || !consumer_atlas_id) {
    throw new TypeError('cross_atlas_imports.read: consumer_atlas_id required');
  }
  if (typeof layer_ref !== 'string' || layer_ref.indexOf('.') < 0) {
    throw new TypeError(
      `cross_atlas_imports.read: layer_ref must be '<atlas_id>.<layer_id>' (got '${layer_ref}')`);
  }
  if (!registry || typeof registry.resolve !== 'function') {
    throw new TypeError('cross_atlas_imports.read: registry (with .resolve()) required');
  }
  if (!cohorts_registry) {
    throw new TypeError('cross_atlas_imports.read: cohorts_registry required');
  }

  const dotIdx = layer_ref.indexOf('.');
  const producer_atlas_id = layer_ref.slice(0, dotIdx);
  const producer_layer_id = layer_ref.slice(dotIdx + 1);

  // Resolve producer cohort from the producer atlas's layer entry.
  // registry_core exposes per-atlas layer entries via internal indexes;
  // we use a shape-tolerant lookup so this stays portable across
  // registry_core versions.
  const producer_cohort_id = _resolveProducerCohort(registry, producer_atlas_id, producer_layer_id);
  // null → producer layer didn't declare a cohort_id. Treat as
  // "implicit consumer cohort" — same-cohort read assumed; flagged
  // in meta so the page can surface a hint.

  // Resolve consumer cohorts.
  const consumer_cohorts = getCohortsForAtlas(cohorts_registry, consumer_atlas_id)
    .map(c => c.cohort_id);

  // Cohort check.
  let handoff_used = null;
  let cohort_status;
  if (producer_cohort_id == null) {
    cohort_status = 'producer_unknown_cohort';
  } else if (consumer_cohorts.indexOf(producer_cohort_id) >= 0) {
    cohort_status = 'same_cohort';
  } else {
    // Look for a handoff per (producer_cohort, every consumer_cohort).
    for (const cc of consumer_cohorts) {
      const hf = findHandoff(cohorts_registry, producer_cohort_id, cc, layer_ref);
      if (hf) { handoff_used = hf; break; }
    }
    if (handoff_used) {
      cohort_status = 'handoff';
    } else if (allow_mismatch) {
      cohort_status = 'mismatch_allowed';
      _warnMismatch(consumer_atlas_id, layer_ref, producer_cohort_id, consumer_cohorts);
    } else {
      throw new CohortMismatchError(
        _formatMismatchError(consumer_atlas_id, layer_ref, producer_cohort_id, consumer_cohorts),
        { consumer_atlas_id, layer_ref, producer_atlas_id, producer_cohort_id, consumer_cohorts },
      );
    }
  }

  // Fetch the data via the standard registry path.
  let data;
  try {
    data = await registry.resolve(producer_layer_id, args || {});
  } catch (e) {
    // Map registry errors to our domain errors when recognisable.
    const msg = (e && e.message) ? e.message : String(e);
    if (msg.includes('unknown key') || msg.includes('not found')) {
      throw new LayerNotFoundError(layer_ref);
    }
    throw e;
  }

  // Workflow-status (SPEC §8) — placeholder until SPEC_workflows_v1 ships.
  // For now we just attach knob_hash to the meta block; the producer-side
  // workflow status lookup is a future addition.
  const workflow_status = knob_hash ? 'unknown' : 'ok';

  return {
    data,
    meta: {
      producer_atlas_id,
      producer_cohort_id,
      consumer_cohorts,
      cohort_status,
      handoff_used:    handoff_used ? handoff_used.handoff_id : null,
      knob_hash:       knob_hash || null,
      workflow_status,
    },
  };
}

// ---------------------------------------------------------------------
// internals
// ---------------------------------------------------------------------

// Shape-tolerant producer-cohort lookup. registry_core stashes atlas
// data on `this._atlases.get(atlas_id) → { layers, … }`. We probe
// `registry.getLayerEntryFor(atlas_id, layer_id)` first (future API),
// then fall back to the internal map. Returns null when the atlas /
// layer / cohort_id field isn't found — caller handles by treating as
// 'producer_unknown_cohort'.
function _resolveProducerCohort(registry, atlas_id, layer_id) {
  if (registry && typeof registry.getLayerEntryFor === 'function') {
    try {
      const e = registry.getLayerEntryFor(atlas_id, layer_id);
      if (e && typeof e.cohort_id === 'string') return e.cohort_id;
    } catch (_) {}
  }
  // Fallback: poke at _atlases map. Stable across current registry_core
  // versions; refactors should expose a proper accessor.
  if (registry && registry._atlases && typeof registry._atlases.get === 'function') {
    try {
      const a = registry._atlases.get(atlas_id);
      const e = a && a.layers && a.layers[layer_id];
      if (e && typeof e.cohort_id === 'string') return e.cohort_id;
    } catch (_) {}
  }
  return null;
}

function _warnMismatch(consumer_atlas_id, layer_ref, producer_cohort_id, consumer_cohorts) {
  if (typeof console === 'undefined') return;
  console.warn(
    `[cohorts] cross-atlas read in PERMISSIVE mode: atlas '${consumer_atlas_id}' ` +
    `(cohorts: [${consumer_cohorts.join(', ')}]) reading '${layer_ref}' ` +
    `(producer cohort: '${producer_cohort_id}'). No matching handoff. ` +
    `Add an entry to cohorts.registry.json or pass allow_cohort_mismatch=false to surface as an error.`);
}

function _formatMismatchError(consumer_atlas_id, layer_ref, producer_cohort_id, consumer_cohorts) {
  // SPEC §10 message template.
  return (
    `CohortMismatchError: atlas '${consumer_atlas_id}' (cohorts: [${consumer_cohorts.join(', ')}]) ` +
    `tried to read '${layer_ref}' (cohort: '${producer_cohort_id}'). No matching ` +
    `cross-reference handoff in cohorts.registry.json. To allow this read, add:\n\n` +
    `  {\n` +
    `    "handoff_id":        "<choose-a-name>",\n` +
    `    "from_cohort":       "${producer_cohort_id}",\n` +
    `    "to_cohort":         "${consumer_cohorts[0] || '<consumer_cohort_id>'}",\n` +
    `    "via_layer_pattern": "^${_escapeRegex(layer_ref)}$",\n` +
    `    "handoff_kind":      "coordinate_handoff",\n` +
    `    "rationale":         "<why this read is safe>"\n` +
    `  }\n`
  );
}

function _escapeRegex(s) {
  return String(s).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}
