// core/registry_core.js
// =====================================================================
// The Atlas registry engine.
//
// Generic, biology-blind. Resolves named results from the appropriate
// cache tier (RAM / IndexedDB / file / server / analysis module).
//
// Public API (per SPEC_registry_v1.md §3):
//
//   resolve(key, args)        → value | Promise<value>
//   set(key, value, args)     → void
//   invalidate(key, args)     → void
//   register_atlas(id, conf)  → void
//   trace(key, args)          → ResolutionPlan
//
// Hot-path rule: resolve() for hot-tier layers returns synchronously
// when the value is already pinned in cache, returns a Promise on miss.
// Pages that read hot data should ideally bypass resolve() entirely
// and read AtlasState directly.
// =====================================================================

import { CacheStore }      from './cache_store.js';
import { OperationRunner } from './operation_runner.js';
import { LayerRouter }     from './layer_router.js';

export class Registry {

  constructor({ atlasState, serverBaseUrl, masterConfig = null } = {}) {
    this.state = atlasState;
    this.cache = new CacheStore();
    this.runner = new OperationRunner({ serverBaseUrl });
    this.router = new LayerRouter();
    this.serverBaseUrl = serverBaseUrl || 'http://localhost:8765';
    // master_config (per toolkit_registries/MASTER_CONFIG.md). Optional —
    // when null, layers must use bare `path:` (resolved atlas-relative
    // via _resolveAtlasFilePath). When present, layers may opt in to
    // `root: <name>` + `path_under_root: <template>` for portable paths.
    this.masterConfig = masterConfig;

    this._atlases = new Map();           // atlas_id → { layers, ops, files, pages, slots }
    this._layerIndex = new Map();        // layer_key → { atlas_id, entry }
    this._operationIndex = new Map();    // op_key → { atlas_id, entry }
    this._analysisModuleCache = new Map(); // module_path → resolved module

    // Persist sub-system (per SPEC v2 item 4 + the operation persist hook).
    // Server results cache logical prefix; the server rewrites this to the
    // configured filesystem root (popstats_server.config.yaml >
    // server_results_cache_root, default /mnt/e/inversion-atlas-cache/server_results/).
    this._serverResultsCachePrefix = '_cache/server_results';
  }

  // -------------------------------------------------------------------
  // PUBLIC API
  // -------------------------------------------------------------------

  /**
   * Resolve a named key.
   *
   * Returns synchronously for hot-tier values that are already cached.
   * Returns a Promise otherwise.
   */
  resolve(key, args = {}) {
    const lookup = this._lookup(key);
    if (!lookup) {
      console.warn(`Registry.resolve: unknown key '${key}'`);
      return null;
    }

    const { entry } = lookup;
    const cacheKey = this._buildCacheKey(key, entry, args);
    const tier = entry.cache_tier || entry.tier;

    // Hot-tier short-circuit: return synchronously if cached.
    if (tier === 'hot') {
      const cached = this.cache.get('hot', cacheKey);
      if (cached !== null) return cached;
      // Miss → fetch and cache. Returns a Promise.
      return this._fetchAndCache(key, lookup, args, cacheKey, tier);
    }

    // Warm/cold: always async.
    return this._resolveAsync(key, lookup, args, cacheKey, tier);
  }

  async _resolveAsync(key, lookup, args, cacheKey, tier) {
    if (tier === 'warm') {
      const cached = await this.cache.get('warm', cacheKey);
      if (cached !== null) return cached;
    }
    // Cold tier never cached at this layer; just go to source.
    return this._fetchAndCache(key, lookup, args, cacheKey, tier);
  }

  async _fetchAndCache(key, lookup, args, cacheKey, tier) {
    const { atlas_id, entry } = lookup;
    const value = await this._fetchFromSource(entry, args, atlas_id);
    if (tier === 'hot' || tier === 'warm') {
      this.cache.set(tier, cacheKey, value);
    }
    return value;
  }

  set(key, value, args = {}) {
    const lookup = this._lookup(key);
    if (!lookup) {
      console.warn(`Registry.set: unknown key '${key}'`);
      return;
    }
    const { entry } = lookup;
    const cacheKey = this._buildCacheKey(key, entry, args);
    const tier = entry.cache_tier || entry.tier;
    if (tier === 'hot' || tier === 'warm') {
      this.cache.set(tier, cacheKey, value);
    }
  }

  invalidate(key, args = {}) {
    const lookup = this._lookup(key);
    if (!lookup) return;
    const cacheKey = this._buildCacheKey(key, lookup.entry, args);
    const tier = lookup.entry.cache_tier || lookup.entry.tier;
    if (tier === 'hot' || tier === 'warm') {
      this.cache.delete(tier, cacheKey);
    }
  }

  /**
   * Write a payload to a writable layer.
   *
   * Per SPEC v2 item 4. Browser-side analysis modules and the server
   * persist hook both go through this method.
   *
   * Contract:
   *   - layer must be writable: true (otherwise throws before any HTTP)
   *   - layer must have entry.path with {slot} templating; required slots
   *     resolve from args first, then from atlasState.shared/buckets
   *     (templateFill); a missing slot throws
   *   - per-candidate layers (path contains {candidate_id}) require args
   *     to include version_id explicitly (via {version_id} in path,
   *     templateFill enforces this); we surface a clearer error before
   *     templateFill runs
   *   - payload is the JS object to write; it's JSON-serialised here
   *   - on success, updates the read-side cache entry with the same
   *     payload so the next resolve() returns it without a fetch
   *   - returns { ok: true, path, bytes } on success, throws on failure
   *
   * Server-side path allowlist (popstats_server.py:_is_path_allowed)
   * provides the second line of defence: even if a layer is mistakenly
   * marked writable, the server rejects writes outside the canonical
   * write prefixes.
   */
  async write(layerKey, args = {}, payload = null) {
    const lookup = this._lookup(layerKey);
    if (!lookup) throw new Error(`Registry.write: unknown layer '${layerKey}'`);
    const { entry } = lookup;

    if (entry.writable !== true) {
      throw new Error(
        `Registry.write: layer '${layerKey}' is not writable. ` +
        `Set 'writable: true' on its layer entry, and ensure the ` +
        `server's path allowlist accepts its path prefix.`
      );
    }
    if (entry.source !== 'file') {
      throw new Error(
        `Registry.write: layer '${layerKey}' has source='${entry.source}'. ` +
        `Only source='file' layers may be written. ` +
        `(operation-source layers persist via the persist hook, not write().)`
      );
    }
    if (!entry.path) {
      throw new Error(
        `Registry.write: layer '${layerKey}' has no path template. ` +
        `Only file-source layers with a path can be written to.`
      );
    }
    if (payload === null || payload === undefined) {
      throw new Error(`Registry.write: payload is required (got ${payload})`);
    }

    // Per-candidate layers: surface the version_id requirement clearly
    // BEFORE templateFill (whose generic "unresolved placeholder" message
    // is less helpful). The check is path-template based: any layer whose
    // path includes {candidate_id} needs a version_id when also using
    // {version_id}. The 7 candidate layers in the inversion atlas all
    // satisfy this — the new policy is no fallback default.
    if (entry.path.includes('{candidate_id}') && entry.path.includes('{version_id}')) {
      if (!args || args.version_id === undefined || args.version_id === null) {
        throw new Error(
          `Registry.write: layer '${layerKey}' requires args.version_id ` +
          `(per-candidate per-version layer; no fallback default).`
        );
      }
    }

    const path = templateFill(entry.path, args, this.state);
    const url  = this.serverBaseUrl + '/file/' + path;
    const body = JSON.stringify(payload);

    const resp = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body
    });

    if (!resp.ok) {
      let detail = '';
      try {
        const err = await resp.json();
        detail = err.detail || err.error || JSON.stringify(err);
      } catch {
        try { detail = await resp.text(); } catch {}
      }
      throw new Error(
        `Registry.write: POST ${url} → HTTP ${resp.status}` +
        (detail ? ` — ${detail}` : '')
      );
    }
    const result = await resp.json();

    // Update read-side cache so the next resolve() returns the value
    // we just wrote, without a re-fetch.
    const cacheKey = this._buildCacheKey(layerKey, entry, args);
    const tier = entry.cache_tier || entry.tier;
    if (tier === 'hot' || tier === 'warm') {
      this.cache.set(tier, cacheKey, payload);
    }

    return { ok: true, path, bytes: result.bytes ?? body.length, layer: layerKey };
  }

  /**
   * Build the persist path for an operation result.
   *
   * Default layout: content_addressed → _cache/server_results/{op_id}/{hash}.json
   * Alternative: path_template → use entry.path with {slot} fill (rare; only
   * makes sense when args fully determine the path via existing placeholders).
   *
   * Used by _fetchFromOperation when the layer entry has persist: true.
   */
  _buildPersistPath(layerKey, entry, args) {
    const layout = entry.cache_layout || 'content_addressed';
    if (layout === 'path_template') {
      if (!entry.path) {
        throw new Error(
          `Registry persist: layer '${layerKey}' uses cache_layout='path_template' ` +
          `but has no path field.`
        );
      }
      return templateFill(entry.path, args, this.state);
    }
    // content_addressed (default)
    const opId = entry.operation || layerKey;
    const hash = stableHashHex(args || {});
    return `${this._serverResultsCachePrefix}/${opId}/${hash}.json`;
  }

  /**
   * Atlas-side registration. Called once per atlas at startup.
   *
   * Conflict resolution per README_PAIRING.md §11:
   *   - Identical config            → silent merge
   *   - Incumbent provisional:true  → succession (new wins)
   *   - Incumbent owned_by matches  → ownership transfer (new wins)
   *   - Otherwise different         → throw
   */
  register_atlas(atlas_id, configs) {
    const layers     = (configs.layers     && configs.layers.layers)     || {};
    const operations = (configs.operations && configs.operations.operations) || {};
    const files      = (configs.files      && configs.files.files)       || {};
    const pages      = (configs.pages      && configs.pages.pages)       || {};
    const slots      = (configs.slots      && configs.slots.slots)       || {};

    // Index layers
    for (const [name, entry] of Object.entries(layers)) {
      if (name.startsWith('_')) continue;
      if (typeof entry !== 'object' || entry === null) continue;
      this._registerKey(this._layerIndex, name, atlas_id, entry, 'layer');
    }

    // Index operations
    for (const [name, entry] of Object.entries(operations)) {
      if (name.startsWith('_')) continue;
      if (typeof entry !== 'object' || entry === null) continue;
      this._registerKey(this._operationIndex, name, atlas_id, entry, 'operation');
    }

    this._atlases.set(atlas_id, { layers, operations, files, pages, slots });

    // Hook for prewarm scheduler
    if (this.state && typeof this.state.emit === 'function') {
      this.state.emit('atlas_registered', { atlas_id });
    }
  }

  _registerKey(index, name, atlas_id, entry, kind) {
    const incumbent = index.get(name);
    if (!incumbent) {
      index.set(name, { atlas_id, entry });
      return;
    }
    if (deepEqual(incumbent.entry, entry)) {
      // Identical — idempotent.
      return;
    }
    if (incumbent.entry.provisional === true) {
      console.info(`Registry: succession of ${kind} '${name}' from '${incumbent.atlas_id}' to '${atlas_id}' (incumbent provisional)`);
      index.set(name, { atlas_id, entry });
      return;
    }
    if (incumbent.entry.owned_by === atlas_id) {
      console.info(`Registry: ownership transfer of ${kind} '${name}' from '${incumbent.atlas_id}' to '${atlas_id}'`);
      index.set(name, { atlas_id, entry });
      return;
    }
    throw new Error(
      `Registry.register_atlas: conflict on ${kind} '${name}' between ` +
      `'${incumbent.atlas_id}' and '${atlas_id}'. Mark the incumbent ` +
      `'provisional: true' and/or 'owned_by: <future_atlas>' if you want ` +
      `succession. See README_PAIRING.md §11.`
    );
  }

  trace(key, args = {}) {
    const lookup = this._lookup(key);
    if (!lookup) return null;
    const { atlas_id, entry } = lookup;
    const cacheKey = this._buildCacheKey(key, entry, args);
    const tier = entry.cache_tier || entry.tier;
    return {
      key,
      args,
      atlas_id,
      tier,
      source: entry.source,
      endpoint: entry.endpoint,
      operation: entry.operation,
      analysis: entry.analysis,
      path: entry.path,
      cache_key: cacheKey,
      schema: entry.schema,
      schema_status: entry.schema_status || 'validated',
      provisional: !!entry.provisional,
      owned_by: entry.owned_by
    };
  }

  // -------------------------------------------------------------------
  // PRIVATE
  // -------------------------------------------------------------------

  /**
   * Look up a key. Layer index first, then operation index. Supports
   * namespaced lookups (atlas:key).
   */
  _lookup(key) {
    if (key.includes(':')) {
      const [, bare] = key.split(':');
      return this._layerIndex.get(bare) || this._operationIndex.get(bare) || null;
    }
    return this._layerIndex.get(key) || this._operationIndex.get(key) || null;
  }

  /**
   * Build a cache key from the entry's cache_key template plus args
   * plus state slots. Falls back to "<key>:<argsJSON>" if no template.
   *
   * Effective `fields` (per-call args.fields ?? entry.fields ?? null)
   * is appended to the cache key so different column subsets cache
   * separately. This prevents a 5-column read from being served from
   * a 23-column cache entry (or vice versa).
   */
  _buildCacheKey(key, entry, args) {
    const fields = this._resolveFields(entry, args);
    let baseKey;
    if (entry.cache_key) {
      baseKey = templateFill(entry.cache_key, args, this.state);
    } else {
      // Default cache key: key + args JSON, with deterministic ordering.
      const sortedArgs = {};
      for (const k of Object.keys(args).sort()) {
        if (k === 'fields') continue;  // fields handled separately
        sortedArgs[k] = args[k];
      }
      baseKey = key + ':' + JSON.stringify(sortedArgs);
    }
    if (fields && fields.length) {
      // Sort to make cache key order-invariant: fields=['a','b'] and
      // fields=['b','a'] return the same data, should hit the same cache.
      const sortedFields = [...fields].sort();
      return baseKey + '#fields=' + sortedFields.join(',');
    }
    return baseKey;
  }

  /**
   * Compute the effective `fields` allow-list for a given (entry, args).
   * Per-call args.fields overrides layer-level entry.fields.
   * Returns null when no filtering is requested.
   */
  _resolveFields(entry, args) {
    if (args && Array.isArray(args.fields) && args.fields.length > 0) {
      return args.fields;
    }
    if (Array.isArray(entry.fields) && entry.fields.length > 0) {
      return entry.fields;
    }
    return null;
  }

  /**
   * Prepend `atlases/<atlas_id>/` to a literal file path, unless the
   * path is already absolute (`/...`), URL-rooted (`http(s)://...`), or
   * already workspace-rooted (`atlases/...`). Mirrors the convention in
   * `_runAnalysis` so layer paths and analysis paths share a single
   * resolution rule. The atlas root mirrors the on-disk source layout
   * documented in `README_PAIRING.md` §2.
   */
  _resolveAtlasFilePath(path, atlas_id) {
    if (typeof path !== 'string' || path.length === 0) return path;
    if (path.startsWith('atlases/')) return path;
    if (path.startsWith('/'))         return path;
    if (/^https?:\/\//.test(path))    return path;
    return `atlases/${atlas_id}/${path}`;
  }

  /**
   * Resolve a layer's `root: <name>` against the loaded master_config.
   * Throws with a helpful message if no master_config is loaded or the
   * named root is unknown. See toolkit_registries/MASTER_CONFIG.md.
   *
   * Imported here as a method (rather than calling resolveRootPath
   * directly) so that subclasses / tests can override.
   */
  _resolveRootPathForLayer(entry, args) {
    if (!this.masterConfig) {
      throw new Error(
        `Registry: layer references root '${entry.root}' but no master_config is loaded. ` +
        `Drop a master_config.yaml at the workspace root or rewrite the layer with 'path:' instead.`
      );
    }
    const roots = this.masterConfig.roots || {};
    const rootEntry = roots[entry.root];
    if (!rootEntry) {
      throw new Error(
        `Registry: layer references unknown root '${entry.root}'. ` +
        `Known roots: ${Object.keys(roots).sort().join(', ')}`
      );
    }
    let p = rootEntry.path;
    if (rootEntry.species_scoped) {
      const speciesId =
        (args && args.species_id) ||
        (this.state && this.state.shared && this.state.shared.activeSpecies) ||
        _firstActiveSpecies(this.masterConfig);
      if (!speciesId) {
        throw new Error(
          `Registry: root '${entry.root}' is species_scoped but no species_id resolved ` +
          `(no args.species_id, no state.shared.activeSpecies, no master_config.species[].active=true).`
        );
      }
      p = p.replace(/\{species_id\}/g, speciesId);
    }
    if (p.startsWith('./')) p = p.slice(2);
    return p;
  }

  /**
   * Dispatch the actual fetch based on entry.source.
   */
  async _fetchFromSource(entry, args, atlas_id) {
    if (entry.source === 'inline') {
      return entry.value === undefined ? null : entry.value;
    }
    if (entry.source === 'file') {
      // Per-candidate per-version layers require version_id. Throw with a
      // clear message before templateFill's generic error, so callers
      // know which slot they forgot.
      if (entry.path && entry.path.includes('{candidate_id}') && entry.path.includes('{version_id}')) {
        if (!args || args.version_id === undefined || args.version_id === null) {
          throw new Error(
            `Registry.resolve: per-candidate layer requires args.version_id ` +
            `(no fallback default; path='${entry.path}'). ` +
            `Tip: resolve('candidate_lineage', { candidate_id }) first, ` +
            `then use lineage.active_version_id for subsequent calls.`
          );
        }
      }
      // Two ways to specify a file path on a layer:
      //   (a) `path: <template>` — atlas-relative; legacy form. Resolved
      //       by prepending atlases/<atlas_id>/ via _resolveAtlasFilePath.
      //   (b) `root: <name>` + `path_under_root: <template>` — portable
      //       form per toolkit_registries/MASTER_CONFIG.md. Root resolves
      //       through the loaded master_config; the under-root template
      //       is then filled with args / state.
      // The two forms are mutually exclusive on a single layer; the
      // master-config form takes precedence if both are present.
      let path;
      if (entry.root) {
        const rootPath = this._resolveRootPathForLayer(entry, args);
        const sub = entry.path_under_root
          ? templateFill(entry.path_under_root, args, this.state)
          : '';
        path = sub ? _joinPath(rootPath, sub) : rootPath;
      } else {
        const filled = templateFill(entry.path, args, this.state);
        path = this._resolveAtlasFilePath(filled, atlas_id);
      }
      const fields = this._resolveFields(entry, args);
      return this.router.fetchFile(path, entry.format || 'json', fields);
    }
    if (entry.source === 'operation') {
      const opLookup = this._operationIndex.get(entry.operation);
      if (!opLookup) throw new Error(`Registry: layer references unknown operation '${entry.operation}'`);
      const result = await this.runner.run(opLookup.entry, args, this.state);

      // Persist hook (per SPEC v2 + the operation persist contract).
      // If the layer entry has persist: true, write the result to the
      // server results cache as a fire-and-forget side-effect. The
      // caller gets `result` back unchanged either way.
      if (entry.persist === true) {
        this._persistOperationResult(entry, args, result).catch(err => {
          // Persistence is opportunistic — don't fail the resolve()
          // if the disk write fails. Log loudly so it's visible.
          console.warn(
            `Registry persist: failed to cache operation '${entry.operation}' result:`,
            err && err.message ? err.message : err
          );
        });
      }

      return result;
    }
    if (entry.source === 'analysis') {
      return this._runAnalysis(entry.analysis, args, atlas_id);
    }
    throw new Error(`Registry: unknown source '${entry.source}'`);
  }

  /**
   * Write an operation result to the server results cache. Called by
   * _fetchFromSource when entry.persist === true. Fire-and-forget from
   * the resolve() path.
   */
  async _persistOperationResult(entry, args, result) {
    // Find the layer key for this entry (reverse lookup) so error
    // messages point at the right place; not strictly needed otherwise.
    let layerKey = '<unknown_layer>';
    for (const [k, v] of this._layerIndex) {
      if (v.entry === entry) { layerKey = k; break; }
    }
    const path = this._buildPersistPath(layerKey, entry, args);
    const url  = this.serverBaseUrl + '/file/' + path;
    const body = JSON.stringify(result);

    const resp = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body
    });
    if (!resp.ok) {
      let detail = '';
      try { detail = await resp.text(); } catch {}
      throw new Error(`HTTP ${resp.status}${detail ? ' — ' + detail : ''}`);
    }
    return { ok: true, path };
  }

  /**
   * Run a browser-side analysis module.
   *
   * analysisRef format: 'path/to/module.js#exportName'
   * Path is relative to the calling atlas's directory.
   */
  async _runAnalysis(analysisRef, ctx, atlas_id) {
    if (!analysisRef) throw new Error('Registry: analysis source requires entry.analysis ref');
    const [modulePath, exportName] = analysisRef.split('#');
    if (!exportName) throw new Error(`Registry: analysis ref '${analysisRef}' missing '#exportName'`);

    const fullPath = `atlases/${atlas_id}/${modulePath}`;
    let mod = this._analysisModuleCache.get(fullPath);
    if (!mod) {
      mod = await import(/* @vite-ignore */ '/' + fullPath);
      this._analysisModuleCache.set(fullPath, mod);
    }
    const fn = mod[exportName];
    if (typeof fn !== 'function') {
      throw new Error(`Registry: analysis module ${fullPath} has no '${exportName}' export, or it isn't a function`);
    }
    return fn(this, ctx);
  }
}

// =====================================================================
// Pure helpers, exported for tests.
// =====================================================================

/**
 * Join two path-like strings with a single '/'. Trailing/leading
 * separators on either side are collapsed. Idempotent.
 */
function _joinPath(a, b) {
  if (!a) return b || '';
  if (!b) return a || '';
  return a.replace(/\/+$/, '') + '/' + b.replace(/^\/+/, '');
}

/**
 * Pick the first active species in the master config, or fall back
 * to the first listed species. Returns null when no species are listed.
 */
function _firstActiveSpecies(masterConfig) {
  if (!masterConfig || !Array.isArray(masterConfig.species)) return null;
  const active = masterConfig.species.find((s) => s && s.active === true);
  if (active) return active.id;
  return masterConfig.species[0]?.id || null;
}

/**
 * Replace {key} occurrences in template by args[key], then by
 * atlasState.shared[key]. Throws if a placeholder is unresolved.
 */
export function templateFill(template, args, atlasState) {
  if (!template) return template;
  return template.replace(/\{([^}]+)\}/g, (_, name) => {
    if (args && args[name] !== undefined) return String(args[name]);
    if (atlasState && atlasState.shared && atlasState.shared[name] !== undefined) {
      return String(atlasState.shared[name]);
    }
    // Per-atlas buckets
    if (atlasState) {
      for (const k of Object.keys(atlasState)) {
        if (k === 'shared' || k.startsWith('_')) continue;
        const bucket = atlasState[k];
        if (bucket && typeof bucket === 'object' && bucket[name] !== undefined) {
          return String(bucket[name]);
        }
      }
    }
    throw new Error(`templateFill: unresolved placeholder '{${name}}' in template '${template}'`);
  });
}

/**
 * Deep equality for the conflict-resolution check. Handles plain
 * objects, arrays, primitives. Not for Date / Set / Map.
 */
export function deepEqual(a, b) {
  if (a === b) return true;
  if (a === null || b === null) return false;
  if (typeof a !== typeof b) return false;
  if (typeof a !== 'object') return false;
  if (Array.isArray(a) !== Array.isArray(b)) return false;
  const ka = Object.keys(a);
  const kb = Object.keys(b);
  if (ka.length !== kb.length) return false;
  for (const k of ka) {
    if (!deepEqual(a[k], b[k])) return false;
  }
  return true;
}

/**
 * Stable hex hash of a value. Used to derive content-addressed cache
 * paths for persisted operation results. Deterministic for objects
 * (key-sorted JSON), arrays (positional), primitives. NOT a cryptographic
 * hash — just enough to avoid collisions across realistic args.
 *
 * Uses a small FNV-1a 32-bit variant emitted as 8 hex chars. Two args
 * differ in cache path iff they JSON-serialise differently after key
 * sorting. The cache is invalidated on the server side by deleting the
 * file; no need to use SHA for ours-only paths.
 *
 * Exported for tests.
 */
export function stableHashHex(value) {
  const s = stableStringify(value);
  // FNV-1a 32-bit
  let h = 0x811c9dc5 >>> 0;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i) & 0xff;
    h = Math.imul(h, 0x01000193) >>> 0;
  }
  return h.toString(16).padStart(8, '0');
}

/**
 * JSON.stringify with deterministic object key ordering. Arrays keep
 * positional order. Used by stableHashHex.
 *
 * Exported for tests.
 */
export function stableStringify(value) {
  if (value === null || typeof value !== 'object') return JSON.stringify(value);
  if (Array.isArray(value)) {
    return '[' + value.map(stableStringify).join(',') + ']';
  }
  const keys = Object.keys(value).sort();
  const parts = keys.map(k => JSON.stringify(k) + ':' + stableStringify(value[k]));
  return '{' + parts.join(',') + '}';
}
