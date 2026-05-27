// core/chrom_bulk_loader.js
// =====================================================================
// SPEC_multichrom_load_orchestrator Slice 2 — bulk JSON loader.
//
// Reads N chromosome scrubber_main JSONs from the user's disk, parses
// each, writes the payload into the registry warm-tier cache, and
// populates the corresponding chromSummary entry. Skips re-fetching the
// chroms the user just dropped in — every future page mount on those
// chroms returns instantly from cache.
//
// Designed for the "Soon its all ready then upload all chromosomes"
// vision: the user has 28 JSONs sitting on disk; they drop the folder
// in once and the whole atlas is warm.
//
// Public surface:
//   loadChromJsons({ files, registry, atlasState, onProgress? })
//     → { loaded: number, skipped: Array<{name, reason}>, total: number }
//
// Chrom-id detection (in priority order):
//   1. payload.chrom (or payload.chromosome) — canonical, set by the
//      precomp emitter
//   2. filename pattern — capture `C_<species>_LG<digits>` or `LG<digits>`
//      from anywhere in the basename
//   3. skip with reason 'chrom_unknown' (logged + surfaced to onProgress)
//
// All writes are sync after the parse; no network. The registry's
// CacheStore.set will async-persist to IDB in the warm tier.
// =====================================================================

import { buildChromSummary } from './chrom_summary.js';

const CHROM_FROM_FILENAME = /(C_[A-Za-z]+_LG\d+|LG\d+)(?:[._-]|\.json$|$)/;

/**
 * Bulk-load chrom scrubber JSONs.
 *
 * @param {object} args
 * @param {FileList|File[]} args.files   — from <input type=file multiple> or drag/drop
 * @param {object} args.registry         — Registry instance (for .set())
 * @param {object} args.atlasState       — AtlasState (for setChromSummary)
 * @param {function} [args.onProgress]   — ({ name, status, chrom?, reason?, loaded, total }) → void
 * @param {string} [args.layerKey]       — defaults to 'scrubber_main'
 * @returns {Promise<{loaded: number, skipped: Array, total: number}>}
 */
export async function loadChromJsons(args) {
  const { files, registry, atlasState, onProgress, layerKey } = args || {};
  const list = Array.from(files || []);
  const total = list.length;
  if (total === 0) return { loaded: 0, skipped: [], total: 0 };
  if (!registry || typeof registry.set !== 'function') {
    throw new Error('loadChromJsons: registry must expose set()');
  }
  if (!atlasState || typeof atlasState.setChromSummary !== 'function') {
    throw new Error('loadChromJsons: atlasState must expose setChromSummary()');
  }
  const key = layerKey || 'scrubber_main';

  let loaded = 0;
  const skipped = [];
  const report = (status, file, extra) => {
    if (typeof onProgress === 'function') {
      try {
        onProgress(Object.assign({
          name: (file && file.name) || '?',
          status, loaded, total,
        }, extra || {}));
      } catch (_) {}
    }
  };

  for (const file of list) {
    if (!_looksLikeJson(file)) {
      skipped.push({ name: file.name, reason: 'not_json' });
      report('skip', file, { reason: 'not_json' });
      continue;
    }
    let payload;
    try {
      const text = await file.text();
      payload = JSON.parse(text);
    } catch (e) {
      skipped.push({ name: file.name, reason: 'parse_error', error: e.message });
      report('skip', file, { reason: 'parse_error', error: e.message });
      continue;
    }
    const chrom = _resolveChrom(payload, file.name);
    if (!chrom) {
      skipped.push({ name: file.name, reason: 'chrom_unknown' });
      report('skip', file, { reason: 'chrom_unknown' });
      continue;
    }
    try {
      registry.set(key, payload, { chrom });
      atlasState.setChromSummary(chrom, buildChromSummary(payload, { chrom }));
      loaded += 1;
      report('loaded', file, { chrom });
    } catch (e) {
      skipped.push({ name: file.name, reason: 'registry_set_threw', error: e.message });
      report('skip', file, { reason: 'registry_set_threw', error: e.message });
    }
  }

  return { loaded, skipped, total };
}

/**
 * Best-effort chrom-id resolution. Exported so the shell modal can show
 * the user which id WILL be used before they commit to the load.
 *
 * @param {object} payload
 * @param {string} filename
 * @returns {?string}
 */
export function _resolveChrom(payload, filename) {
  if (payload && typeof payload === 'object') {
    if (typeof payload.chrom === 'string' && payload.chrom.length > 0)      return payload.chrom;
    if (typeof payload.chromosome === 'string' && payload.chromosome.length > 0) return payload.chromosome;
  }
  if (typeof filename === 'string') {
    const m = filename.match(CHROM_FROM_FILENAME);
    if (m) return m[1];
  }
  return null;
}

function _looksLikeJson(file) {
  if (!file || typeof file.name !== 'string') return false;
  if (file.type === 'application/json') return true;
  return /\.json$/i.test(file.name);
}
