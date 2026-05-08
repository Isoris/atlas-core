// core/operation_runner.js
// =====================================================================
// HTTP bridge to the atlas's backend server (e.g. popstats_server.py).
//
// Given an operation entry from operations.registry.json plus an args
// dict + the AtlasState, assembles the request, calls the endpoint,
// and returns the parsed JSON.
//
// v1 schema validation: SOFT. If the schema file resolves and parses,
// we run a minimal type+required-keys check. If it doesn't (most do
// not in v1 — they're placeholders), we log a one-line debug note and
// pass the response through. This matches schema_status: 'pending'.
//
// The runner does NOT cache. Caching is the registry's job.
// =====================================================================

export class OperationRunner {

  constructor({ serverBaseUrl } = {}) {
    this.baseUrl = serverBaseUrl || 'http://localhost:8765';
    this._schemaCache = new Map();
  }

  async run(opEntry, args, atlasState) {
    const url = this._buildUrl(opEntry, args, atlasState);
    const method = (opEntry.method || 'POST').toUpperCase();

    let resp;
    if (method === 'GET') {
      resp = await fetch(url);
    } else {
      const body = this._assembleInputs(opEntry.inputs || [], args, atlasState);
      resp = await fetch(url, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
      });
    }

    if (!resp.ok) {
      // Try to surface the server's error message if it sent JSON.
      let detail = '';
      try {
        const err = await resp.json();
        detail = err.detail || err.error || JSON.stringify(err);
      } catch {
        try { detail = await resp.text(); } catch {}
      }
      throw new Error(
        `OperationRunner: ${method} ${url} → HTTP ${resp.status}` +
        (detail ? ` — ${detail}` : '')
      );
    }

    const value = await resp.json();
    if (opEntry.output_schema) await this._validateSoft(value, opEntry.output_schema);
    return value;
  }

  // ------------------------------------------------------------------

  _buildUrl(opEntry, args, atlasState) {
    let path = opEntry.endpoint;
    if (!path) throw new Error('OperationRunner: opEntry.endpoint is required');

    // For GET endpoints, append query_params from args if declared.
    if ((opEntry.method || 'POST').toUpperCase() === 'GET' && opEntry.query_params) {
      const qs = new URLSearchParams();
      for (const name of Object.keys(opEntry.query_params)) {
        const value = (args && args[name] !== undefined)
          ? args[name]
          : this._lookupSlot(name, atlasState);
        if (value !== undefined && value !== null) {
          qs.append(name, String(value));
        }
      }
      const qsStr = qs.toString();
      if (qsStr) path += '?' + qsStr;
    }

    return this.baseUrl + path;
  }

  _assembleInputs(inputNames, args, atlasState) {
    const body = {};
    for (const name of inputNames) {
      if (args && args[name] !== undefined) {
        body[name] = args[name];
        continue;
      }
      const val = this._lookupSlot(name, atlasState);
      if (val !== undefined) body[name] = val;
    }
    // Pass-through any extra args the caller wants in the body.
    if (args) {
      for (const k of Object.keys(args)) {
        if (body[k] === undefined) body[k] = args[k];
      }
    }
    return body;
  }

  _lookupSlot(name, atlasState) {
    if (!atlasState) return undefined;
    if (atlasState.shared && atlasState.shared[name] !== undefined) {
      return atlasState.shared[name];
    }
    // Per-atlas buckets — try each (atlases that registered slots become
    // top-level keys on AtlasState).
    for (const k of Object.keys(atlasState)) {
      if (k === 'shared' || k.startsWith('_')) continue;
      const bucket = atlasState[k];
      if (bucket && typeof bucket === 'object' && bucket[name] !== undefined) {
        return bucket[name];
      }
    }
    return undefined;
  }

  async _validateSoft(value, schemaPath) {
    let schema = this._schemaCache.get(schemaPath);
    if (schema === undefined) {
      try {
        const resp = await fetch(schemaPath);
        if (resp.ok) schema = await resp.json();
        else schema = null;
      } catch {
        schema = null;
      }
      this._schemaCache.set(schemaPath, schema);
    }
    if (!schema) return;                     // no schema available
    if (schema._status === 'pending') return; // explicit pending → skip
    if (schema.type === 'object' && !schema.required && !schema.properties) return;
    // Minimal check: top-level type + required keys.
    if (schema.type === 'object' && typeof value !== 'object') {
      throw new Error(`OperationRunner: response failed schema (${schemaPath}): expected object, got ${typeof value}`);
    }
    if (Array.isArray(schema.required)) {
      for (const k of schema.required) {
        if (value === null || value === undefined || !(k in value)) {
          throw new Error(`OperationRunner: response missing required key '${k}' (schema ${schemaPath})`);
        }
      }
    }
  }
}
