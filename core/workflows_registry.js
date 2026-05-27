// core/workflows_registry.js
// =====================================================================
// Workflows-registry loader + API per SPEC_workflows_v1.md.
//
// Each atlas declares its own `registries/data/workflows.registry.json`.
// Atlas-core loads them per-atlas, validates against the schema rules in
// SPEC §6, and cross-validates against:
//   - cohorts.registry.json    — every workflow's cohort_id must exist
//   - layers.registry.json     — every produces/consumes layer_id must exist
//   - atlases/_index.json      — the atlas_id in the registry must be installed
//
// Validation failures are LOUD — atlas refuses to mount until they're
// fixed (mirrors the cohorts registry convention).
//
// Public exports:
//
//   loadWorkflowsRegistry(atlasRoot, opts?) → Promise<registry>
//     Fetch + JSON-parse atlas-relative workflows.registry.json. Returns
//     {atlas_id, version, workflows} or throws.
//
//   validateWorkflowsRegistry(registry, opts?) → string[]
//     Schema-shape + cross-reference validation per SPEC §6. opts:
//       { cohortsRegistry, layersIndex, atlasesIndex }
//     Returns [] when valid; otherwise an array of one-line error messages.
//
//   getWorkflow(registry, workflow_id) → workflow | null
//   listWorkflows(registry)            → workflow[]
//   getWorkflowsByConsumes(registry, layer_id) → workflow[]
//   getWorkflowsByProduces(registry, layer_id) → workflow[]
//
//   getStatusForWorkflow(atlasRoot, workflow, opts?) → Promise<status | null>
//     Reads workflow.status_file. Returns null on 404 (workflow never ran).
//
//   isWorkflowOutputStale(workflow, status) → boolean
//     Compares status.knob_hash to workflow.default_knob_hash (when not
//     'auto'). Returns true when they differ. Doesn't currently check
//     input-file mtimes — that's a v2 enhancement.
// =====================================================================

export async function loadWorkflowsRegistry(atlasRoot, opts) {
  const root = (atlasRoot || '').replace(/\/+$/, '');
  const url = (root ? root + '/' : '') + 'registries/data/workflows.registry.json';
  const fetchFn = (opts && opts.fetch) || (typeof fetch === 'function' ? fetch : null);
  if (!fetchFn) {
    throw new Error('loadWorkflowsRegistry: no fetch available (pass opts.fetch in Node)');
  }
  const resp = await fetchFn(url);
  if (!resp.ok) {
    throw new Error(`loadWorkflowsRegistry: GET ${url} → HTTP ${resp.status}`);
  }
  const registry = await resp.json();
  if (!registry || typeof registry !== 'object') {
    throw new Error(`loadWorkflowsRegistry: ${url} did not parse as an object`);
  }
  return registry;
}

// =====================================================================
// validation — SPEC §6
// =====================================================================

export function validateWorkflowsRegistry(registry, opts) {
  const errors = [];
  const o = opts || {};
  if (!registry || typeof registry !== 'object') {
    return ['workflows.registry.json: payload is not an object'];
  }

  // Top-level shape.
  if (typeof registry.atlas_id !== 'string' || !/^[a-z][a-z0-9_-]*$/.test(registry.atlas_id)) {
    errors.push(`workflows.registry.json: missing or malformed 'atlas_id' (got ${JSON.stringify(registry.atlas_id)})`);
  }
  if (typeof registry.version !== 'string' || !/^\d+\.\d+(\.\d+)?$/.test(registry.version)) {
    errors.push(`workflows.registry.json: missing or malformed 'version' (got ${JSON.stringify(registry.version)})`);
  }
  if (!Array.isArray(registry.workflows)) {
    errors.push('workflows.registry.json: workflows[] missing or not an array');
  }
  if (errors.length) return errors;   // bail before per-row checks

  // atlas_id must be installed when atlasesIndex is provided.
  if (o.atlasesIndex && Array.isArray(o.atlasesIndex.atlases)) {
    const installed = new Set(o.atlasesIndex.atlases);
    if (!installed.has(registry.atlas_id)) {
      errors.push(`workflows.registry.json: atlas_id '${registry.atlas_id}' is not in atlases/_index.json (installed: ${[...installed].sort().join(', ')})`);
    }
  }

  // Cross-reference indexes built once.
  const knownCohortIds = new Set(
    (o.cohortsRegistry && Array.isArray(o.cohortsRegistry.cohorts))
      ? o.cohortsRegistry.cohorts.map(c => c && c.cohort_id).filter(Boolean)
      : []
  );
  const knownLayerIds = new Set(
    (o.layersIndex && Array.isArray(o.layersIndex.layers))
      ? o.layersIndex.layers.map(l => l && l.layer_id).filter(Boolean)
      : []
  );

  // Per-workflow shape + cross-validation.
  const seenWorkflowIds = new Set();
  for (let i = 0; i < registry.workflows.length; i++) {
    const wf = registry.workflows[i];
    if (!wf || typeof wf !== 'object') {
      errors.push(`workflows[${i}]: not an object`);
      continue;
    }

    // §6.1 unique workflow_id within the atlas.
    if (typeof wf.workflow_id !== 'string' || !/^[a-z][a-z0-9_]*$/.test(wf.workflow_id)) {
      errors.push(`workflows[${i}]: bad workflow_id ${JSON.stringify(wf.workflow_id)}`);
      continue;
    }
    if (seenWorkflowIds.has(wf.workflow_id)) {
      errors.push(`workflows[${i}] (${wf.workflow_id}): duplicate workflow_id`);
    }
    seenWorkflowIds.add(wf.workflow_id);

    // Required top-level fields.
    if (typeof wf.label !== 'string' || wf.label.length === 0) {
      errors.push(`workflow '${wf.workflow_id}': label missing or empty`);
    }
    if (typeof wf.outputs_root !== 'string' || wf.outputs_root.length === 0) {
      errors.push(`workflow '${wf.workflow_id}': outputs_root missing or empty`);
    }
    if (typeof wf.status_file !== 'string' || wf.status_file.length === 0) {
      errors.push(`workflow '${wf.workflow_id}': status_file missing or empty`);
    }

    // §6.6 cohort_id must exist in cohorts.registry.json.
    if (typeof wf.cohort_id !== 'string' || !/^[a-z][a-z0-9_]*$/.test(wf.cohort_id)) {
      errors.push(`workflow '${wf.workflow_id}': bad cohort_id ${JSON.stringify(wf.cohort_id)}`);
    } else if (knownCohortIds.size > 0 && !knownCohortIds.has(wf.cohort_id)) {
      errors.push(`workflow '${wf.workflow_id}': cohort_id '${wf.cohort_id}' is not in cohorts.registry.json`);
    }

    // Stages.
    if (!Array.isArray(wf.stages) || wf.stages.length === 0) {
      errors.push(`workflow '${wf.workflow_id}': stages[] missing or empty`);
    } else {
      _validateStages(wf, knownLayerIds, errors);
    }

    // Runners.
    if (!Array.isArray(wf.runners) || wf.runners.length === 0) {
      errors.push(`workflow '${wf.workflow_id}': runners[] missing or empty`);
    } else {
      const seenRunnerIds = new Set();
      for (let r = 0; r < wf.runners.length; r++) {
        const rn = wf.runners[r];
        if (!rn || typeof rn !== 'object') {
          errors.push(`workflow '${wf.workflow_id}' runners[${r}]: not an object`);
          continue;
        }
        if (typeof rn.runner_id !== 'string' || !/^[a-z][a-z0-9_]*$/.test(rn.runner_id)) {
          errors.push(`workflow '${wf.workflow_id}' runners[${r}]: bad runner_id ${JSON.stringify(rn.runner_id)}`);
          continue;
        }
        if (seenRunnerIds.has(rn.runner_id)) {
          errors.push(`workflow '${wf.workflow_id}' runners[${r}] (${rn.runner_id}): duplicate runner_id`);
        }
        seenRunnerIds.add(rn.runner_id);
        if (typeof rn.script !== 'string' || rn.script.length === 0) {
          errors.push(`workflow '${wf.workflow_id}' runners[${r}] (${rn.runner_id}): script missing or empty`);
        }
      }
    }
  }

  return errors;
}

// §6.2 produces/consumes resolve to known layers (when layersIndex provided).
// §6.7 stages form a DAG (no cycles in produces ↔ consumes).
// §6.8 ordering respects DAG topo (earlier stages don't consume later stages).
function _validateStages(wf, knownLayerIds, errors) {
  const stageById = new Map();     // stage_id → stage
  const stageIdx  = new Map();     // stage_id → array index (for ordering check)
  const seenStageIds = new Set();
  for (let s = 0; s < wf.stages.length; s++) {
    const stg = wf.stages[s];
    if (!stg || typeof stg !== 'object') {
      errors.push(`workflow '${wf.workflow_id}' stages[${s}]: not an object`);
      continue;
    }
    if (typeof stg.stage_id !== 'string' || !/^[A-Za-z][A-Za-z0-9_]*$/.test(stg.stage_id)) {
      errors.push(`workflow '${wf.workflow_id}' stages[${s}]: bad stage_id ${JSON.stringify(stg.stage_id)}`);
      continue;
    }
    if (seenStageIds.has(stg.stage_id)) {
      errors.push(`workflow '${wf.workflow_id}' stages[${s}] (${stg.stage_id}): duplicate stage_id`);
    }
    seenStageIds.add(stg.stage_id);
    stageById.set(stg.stage_id, stg);
    stageIdx.set(stg.stage_id, s);

    if (typeof stg.script !== 'string' || stg.script.length === 0) {
      errors.push(`stage '${wf.workflow_id}.${stg.stage_id}': script missing or empty`);
    }
    // produces[] may be empty for side-effect / fold stages that transform
    // upstream data in place without registering a new layer (e.g. GO2 in
    // the cross-species gene_order_consolidation pipeline). When present,
    // every entry must resolve.
    if (stg.produces != null && !Array.isArray(stg.produces)) {
      errors.push(`stage '${wf.workflow_id}.${stg.stage_id}': produces is not an array`);
    } else if (Array.isArray(stg.produces) && knownLayerIds.size > 0) {
      for (const lid of stg.produces) {
        if (!knownLayerIds.has(lid)) {
          errors.push(`stage '${wf.workflow_id}.${stg.stage_id}': produces unknown layer_id '${lid}' (not in layers.registry.json)`);
        }
      }
    }
    if (stg.consumes && !Array.isArray(stg.consumes)) {
      errors.push(`stage '${wf.workflow_id}.${stg.stage_id}': consumes is not an array`);
    }
  }

  // §6.7 + §6.8 — DAG / ordering.
  // Build layer → producer-stage map. consume-stage must come AFTER producer-stage.
  // (Cross-atlas consumes that don't have a producer in this workflow are ignored —
  // they're satisfied by another atlas's registry; the cross_atlas_imports resolver
  // catches missing ones at read time.)
  const producerStage = new Map();   // layer_id → stage_id (within this workflow)
  for (const stg of stageById.values()) {
    if (!Array.isArray(stg.produces)) continue;
    for (const lid of stg.produces) {
      if (producerStage.has(lid)) {
        errors.push(`workflow '${wf.workflow_id}': layer_id '${lid}' is produced by both '${producerStage.get(lid)}' and '${stg.stage_id}'`);
      } else {
        producerStage.set(lid, stg.stage_id);
      }
    }
  }
  for (const stg of stageById.values()) {
    if (!Array.isArray(stg.consumes)) continue;
    for (const lid of stg.consumes) {
      const producer = producerStage.get(lid);
      if (!producer) continue;   // cross-atlas consume — out of scope here
      if (producer === stg.stage_id) {
        errors.push(`stage '${wf.workflow_id}.${stg.stage_id}': consumes its own output '${lid}' (cycle)`);
        continue;
      }
      if (stageIdx.get(producer) > stageIdx.get(stg.stage_id)) {
        errors.push(`stage '${wf.workflow_id}.${stg.stage_id}': consumes '${lid}' produced by later stage '${producer}' (ordering violates DAG)`);
      }
    }
  }
}

// =====================================================================
// lookup helpers
// =====================================================================

export function getWorkflow(registry, workflow_id) {
  if (!registry || !Array.isArray(registry.workflows)) return null;
  for (const wf of registry.workflows) {
    if (wf && wf.workflow_id === workflow_id) return wf;
  }
  return null;
}

export function listWorkflows(registry) {
  return (registry && Array.isArray(registry.workflows)) ? registry.workflows.slice() : [];
}

export function getWorkflowsByConsumes(registry, layer_id) {
  if (!registry || !Array.isArray(registry.workflows)) return [];
  return registry.workflows.filter(wf =>
    wf && Array.isArray(wf.stages) &&
    wf.stages.some(s => s && Array.isArray(s.consumes) && s.consumes.indexOf(layer_id) >= 0)
  );
}

export function getWorkflowsByProduces(registry, layer_id) {
  if (!registry || !Array.isArray(registry.workflows)) return [];
  return registry.workflows.filter(wf =>
    wf && Array.isArray(wf.stages) &&
    wf.stages.some(s => s && Array.isArray(s.produces) && s.produces.indexOf(layer_id) >= 0)
  );
}

// =====================================================================
// status.json reader — SPEC §5
// =====================================================================

export async function getStatusForWorkflow(atlasRoot, workflow, opts) {
  if (!workflow || typeof workflow.status_file !== 'string') return null;
  const root = (atlasRoot || '').replace(/\/+$/, '');
  const url = (root ? root + '/' : '') + workflow.status_file.replace(/^\/?/, '');
  const fetchFn = (opts && opts.fetch) || (typeof fetch === 'function' ? fetch : null);
  if (!fetchFn) {
    throw new Error('getStatusForWorkflow: no fetch available (pass opts.fetch in Node)');
  }
  let resp;
  try { resp = await fetchFn(url); }
  catch (_) { return null; }
  if (!resp.ok) return null;   // 404 == never ran; treat as null per SPEC §11
  try { return await resp.json(); }
  catch (_) { return null; }
}

export function isWorkflowOutputStale(workflow, status) {
  if (!workflow || !status) return false;
  // 'auto' default means "whatever the schema currently produces" — we
  // can't compare a hash to that without re-computing the knob set.
  // Conservative: don't flag stale in that case (let the chrome decide
  // based on input mtimes once that v2 check lands).
  if (workflow.default_knob_hash === 'auto') return false;
  if (typeof workflow.default_knob_hash !== 'string') return false;
  if (typeof status.knob_hash !== 'string') return false;
  return workflow.default_knob_hash !== status.knob_hash;
}
