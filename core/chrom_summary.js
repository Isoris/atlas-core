// core/chrom_summary.js
// =====================================================================
// SPEC_multichrom_load_orchestrator Slice 1 — chromSummary helpers.
//
// The atlas today keeps the full scrubber_main JSON in memory for ONE
// chromosome at a time. To support the all-28-chroms vision without
// OOM'ing the browser tab (28 × ~50-300 MB JSONs = several GB), we
// keep just the active chrom's full payload and reduce every other
// chrom to a small summary blob that stays in memory across switches.
//
// This module is the FOUNDATION layer (Slice 1):
//   - buildChromSummary(data) extracts the canonical summary shape
//     from a full scrubber_main payload (pure, no side effects).
//   - The summary is small enough to keep N of them resident even on a
//     mobile tab (~few KB per chrom; 28 chroms = under 100 KB total).
//   - AtlasState exposes setChromSummary(chrom, summary) +
//     getChromSummary(chrom) for the page-side wiring (Slice 2/3 will
//     persist the active chrom's full payload to IDB and lazy-load
//     others on demand; this module just defines the contract).
//
// The summary shape is documented in SPEC_multichrom_load_orchestrator.md
// §3 + §5 Q1. It surfaces only what the genome-wide ideogram +
// cross-chrom lineage matching + bulk-load progress chip need —
// every consumer either gets its answer from the summary or pays the
// per-chrom IDB rehydrate cost. Add fields here when (and only when)
// a real consumer needs them.
//
// IMPORTANT: this module is consumer-agnostic. The inversion-atlas's
// scrubber_main JSON shape leaks in through buildChromSummary, but
// every field extraction is null-tolerant so an atlas whose precomp
// doesn't declare some block (e.g. no candidate_tracks layer) just
// gets 0/null for those fields rather than throwing. Adding new
// atlases' scrubber payloads should not require touching this file.
// =====================================================================

/**
 * Canonical chrom-summary shape.
 *
 * @typedef {object} ChromSummary
 * @property {string}    chrom               Canonical chrom id (e.g. "C_gar_LG01").
 * @property {number}    n_windows           Window count for this chrom (0 if unknown).
 * @property {number}    n_samples           Sample count in the scrubber payload (0 if unknown).
 * @property {number}    chrom_length_bp     End coordinate of the last window in bp (0 if unknown).
 * @property {number}    n_l2_envelopes      L2-cluster envelope count (0 if absent).
 * @property {number}    n_candidates        Promoted-candidate count surfaced in this payload (0 if absent).
 * @property {string[]}  layers_present      Layer keys this chrom's precomp actually carries.
 * @property {boolean}   has_lineage_cache   Lineage compute already cached for this chrom.
 * @property {boolean}   has_inheritance_cache  Inheritance (L2-sweep) compute already cached.
 * @property {number}    built_at_ms         Date.now() of when the summary was built.
 * @property {?string}   data_version        Provenance data_version from the payload, when stamped.
 */

/**
 * Build the canonical summary blob from a full scrubber_main payload.
 *
 * Pure: doesn't mutate `data`, doesn't touch atlasState, doesn't fetch.
 * Null-tolerant: every field defaults to a safe zero/empty value when the
 * payload doesn't carry it. Returns the same shape regardless of which
 * atlas produced the payload.
 *
 * @param {object} data       The full scrubber_main JSON (or null).
 * @param {object} [opts]
 * @param {string} [opts.chrom]               Override the chrom id (when the payload has it under a non-standard field).
 * @param {boolean} [opts.has_lineage_cache]  Caller's compute-cache hint (defaults to false).
 * @param {boolean} [opts.has_inheritance_cache]
 * @returns {ChromSummary}
 */
export function buildChromSummary(data, opts = {}) {
  const d = (data && typeof data === 'object') ? data : {};
  const chrom = opts.chrom
    || (typeof d.chrom === 'string' ? d.chrom : null)
    || (typeof d.chromosome === 'string' ? d.chromosome : null)
    || '';

  const windows = Array.isArray(d.windows) ? d.windows : null;
  const n_windows = windows ? windows.length : (Number.isFinite(d.n_windows) ? d.n_windows | 0 : 0);
  const samples = Array.isArray(d.samples) ? d.samples : null;
  const n_samples = samples ? samples.length : (Number.isFinite(d.n_samples) ? d.n_samples | 0 : 0);

  // Chrom length = end_bp of the last window if windows[] is present and
  // carries end_bp; otherwise fall through to 0. We don't trust d.chrom_length
  // because that field isn't standardized across producers.
  let chrom_length_bp = 0;
  if (windows && windows.length > 0) {
    const last = windows[windows.length - 1];
    if (last && Number.isFinite(last.end_bp)) {
      chrom_length_bp = last.end_bp | 0;
    } else if (last && Number.isFinite(last.center_bp)) {
      chrom_length_bp = last.center_bp | 0;
    }
  }

  // L2 envelopes: inversion-atlas precomp carries them as data.envelopes or
  // data.tracks.envelopes. Other atlases may not have any — that's fine,
  // surface 0.
  let n_l2_envelopes = 0;
  if (Array.isArray(d.envelopes)) n_l2_envelopes = d.envelopes.length;
  else if (d.tracks && Array.isArray(d.tracks.envelopes)) n_l2_envelopes = d.tracks.envelopes.length;

  // Candidates: surface whichever of the canonical containers is populated.
  // inversion-atlas carries them under data.candidates / data.candidate_tracks;
  // other atlases just get 0.
  let n_candidates = 0;
  if (Array.isArray(d.candidates)) n_candidates = d.candidates.length;
  else if (Array.isArray(d.candidate_tracks)) n_candidates = d.candidate_tracks.length;
  else if (d.tracks && Array.isArray(d.tracks.candidates)) n_candidates = d.tracks.candidates.length;

  // Layers present: collect the names of top-level array/object blocks that
  // carry actual data (non-empty), filtering out provenance + bookkeeping.
  const SKIP = new Set([
    'chrom', 'chromosome', 'n_windows', 'n_samples', '_provenance',
    'data_version', 'content_sha256', 'carved_at', 'schema_version',
  ]);
  const layers_present = [];
  for (const k of Object.keys(d)) {
    if (k.startsWith('_')) continue;
    if (SKIP.has(k)) continue;
    const v = d[k];
    if (v == null) continue;
    if (Array.isArray(v) && v.length === 0) continue;
    if (typeof v === 'object' && !Array.isArray(v) && Object.keys(v).length === 0) continue;
    layers_present.push(k);
  }
  layers_present.sort();

  return {
    chrom,
    n_windows,
    n_samples,
    chrom_length_bp,
    n_l2_envelopes,
    n_candidates,
    layers_present,
    has_lineage_cache:    opts.has_lineage_cache === true,
    has_inheritance_cache: opts.has_inheritance_cache === true,
    built_at_ms:          Date.now(),
    data_version: (d._provenance && typeof d._provenance.data_version === 'string')
      ? d._provenance.data_version
      : (typeof d.data_version === 'string' ? d.data_version : null),
  };
}

/**
 * Merge a freshly-built summary into atlasState.shared.chromSummaries.
 * Idempotent: overwrites any existing entry for the same chrom key.
 * Emits 'shared.chromSummaries.changed' with the chrom + summary so the
 * Slice 2 bulk-load progress strip can react without polling.
 *
 * Side-effect only on atlasState — does not touch the registry, IDB, or
 * fetch anything. Callers that want IDB persistence should also pin to
 * the cache via registry.set('scrubber_main', payload, { chrom }) which
 * already goes through the warm-tier IDB path.
 *
 * @param {object} atlasState  AtlasState instance (must expose .shared and .emit).
 * @param {string} chrom
 * @param {ChromSummary} summary
 */
export function setChromSummary(atlasState, chrom, summary) {
  if (!atlasState || !atlasState.shared) return;
  if (typeof chrom !== 'string' || chrom.length === 0) return;
  if (!atlasState.shared.chromSummaries
      || typeof atlasState.shared.chromSummaries !== 'object') {
    atlasState.shared.chromSummaries = {};
  }
  atlasState.shared.chromSummaries[chrom] = summary;
  if (typeof atlasState.emit === 'function') {
    atlasState.emit('shared.chromSummaries.changed', { chrom, summary });
  }
}

/**
 * Read a previously-stored summary. Returns null when none exists for
 * the chrom. Cheap — just a Map lookup. Pages that want a guaranteed
 * fresh summary (e.g. after a chrom load) should call buildChromSummary
 * + setChromSummary themselves.
 *
 * @param {object} atlasState
 * @param {string} chrom
 * @returns {?ChromSummary}
 */
export function getChromSummary(atlasState, chrom) {
  if (!atlasState || !atlasState.shared) return null;
  const all = atlasState.shared.chromSummaries;
  if (!all || typeof all !== 'object') return null;
  return all[chrom] || null;
}

/**
 * List all known chrom summaries, sorted by chrom id in the conventional
 * LG-natural order (LG1, LG2, ..., LG28, then anything else lex). Useful
 * for the bulk-load progress strip + the genome-wide ideogram.
 *
 * @param {object} atlasState
 * @returns {ChromSummary[]}
 */
export function listChromSummaries(atlasState) {
  if (!atlasState || !atlasState.shared) return [];
  const all = atlasState.shared.chromSummaries;
  if (!all || typeof all !== 'object') return [];
  const entries = Object.entries(all);
  entries.sort(([a], [b]) => {
    const ma = a.match(/LG0*(\d+)$/);
    const mb = b.match(/LG0*(\d+)$/);
    if (ma && mb) return Number(ma[1]) - Number(mb[1]);
    if (ma && !mb) return -1;
    if (!ma && mb) return  1;
    return a.localeCompare(b);
  });
  return entries.map(([, s]) => s);
}
