// =============================================================================
// atlas-core/core/mode_b_badge.js
// =============================================================================
// Shared "Mode B" probe + badge renderer for atlas pages.
//
// Each atlas page renders from a primary data source (a manuscript carve,
// a precomp JSON cached in AtlasState, etc.). A Mode-B probe resolves the
// SAME data through the layer registry independently, then renders a small
// inline badge so reviewers can see:
//
//   ●  match     — registry resolved cleanly, comparator says shape agrees
//   ⚠  drift     — registry resolved but comparator says shape disagrees
//   ○  missing   — registry not injected / resolve threw / payload empty
//
// All failure modes are non-fatal. The page never blocks on the probe.
//
// History: lived per-atlas in 2026-05-20, promoted here on third use
// (diversity-atlas + inversion-atlas + ?). API is the union of the two
// per-atlas predecessors:
//
//   * opts.extractRows   — project a row array out of an object payload
//                          (scrubber_main.windows, candidate_lineage.versions, …)
//   * opts.compare       — comparator returning { pass, summary }
//   * opts.context       — short scope tag in the badge text (chrom / candidate id)
//   * opts.provenance    — carve fingerprint appended to the badge tooltip
//                          (data_loader.js ctx.PROVENANCE shape)
//
// Pages import this from a relative path back to atlas-core:
//
//   import { probeModeB, renderModeBBadge }
//     from '../../../../core/mode_b_badge.js';
//
// Atlases that don't yet have the var(--ink-dim) / var(--panel-2) /
// var(--rule) CSS tokens declared can either define them in their own
// stylesheet or replace the badge container's inline style.
// =============================================================================


/**
 * Resolve a layer through the injected registry. Always returns; never
 * throws. Shape:
 *   { ok: true,  rows, payload, n, sample_keys }
 *   { ok: false, reason, error?, payload? }
 *
 * `opts.extractRows(payload) => Array | null` lets callers point at a
 * sub-array of an object payload. Default extractor: pass through arrays,
 * reject anything else (which is the shape `format: tsv` layers produce
 * via parseDelimited).
 *
 * `probeResult.payload` is always the raw resolved value when the probe
 * reached the registry — useful for comparators that need top-level
 * fields like `cohort_summary` or `active_version_id` alongside per-row stats.
 */
export async function probeModeB(registry, layerKey, args, opts) {
  if (!registry || typeof registry.resolve !== 'function') {
    return { ok: false, reason: 'registry-not-injected' };
  }
  const extractRows = (opts && opts.extractRows) || _defaultExtractRows;
  try {
    const payload = await Promise.resolve(registry.resolve(layerKey, args || {}));
    const rows = extractRows(payload);
    if (!Array.isArray(rows) || rows.length === 0) {
      // Distinguish empty payload (stub on disk) from missing payload
      // (no fetch). Nullish resolve return → file unreachable.
      const reason = (payload == null) ? 'empty-result' : 'stub-payload';
      return { ok: false, reason, payload };
    }
    return {
      ok:          true,
      rows,
      payload,
      n:           rows.length,
      sample_keys: Object.keys(rows[0] || {}),
    };
  } catch (e) {
    return { ok: false, reason: 'resolve-threw', error: String(e && e.message || e) };
  }
}

function _defaultExtractRows(payload) {
  return Array.isArray(payload) ? payload : null;
}


/**
 * Render a Mode-B badge into a DOM slot.
 *
 * @param slotId           element id of the badge container
 * @param probeResult      return value of probeModeB()
 * @param opts.label       short layer name shown in the badge text
 * @param opts.layerKey    layer key (logged in tooltip)
 * @param opts.context     optional scope tag (chrom / candidate id /
 *                          version id) appended after the label
 * @param opts.compare     optional (probeResult) => { pass, summary }
 * @param opts.provenance  optional ctx.PROVENANCE block from a data_loader
 *                          ({ data_version, content_sha256, carved_at, ... });
 *                          when present, appended as "— vs carve: …" to the
 *                          badge tooltip so a reviewer can see which carve
 *                          they're cross-checking against
 */
export function renderModeBBadge(slotId, probeResult, opts) {
  const slot = (typeof document !== 'undefined') && document.getElementById(slotId);
  if (!slot) return;
  const label = (opts && opts.label) || 'pipeline';
  const ctxStr = (opts && opts.context) ? ` · ${opts.context}` : '';
  const carveTip = _carveTooltip(opts && opts.provenance);

  if (!probeResult || !probeResult.ok) {
    slot.className = 'data-source-badge demo';
    const reason = (probeResult && probeResult.reason) || 'unknown';
    const hint = {
      'registry-not-injected': 'shell did not inject the registry — running standalone?',
      'empty-result':          'layer resolved but rows[] is empty — check the source.',
      'stub-payload':          'payload resolved but is a stub (upstream pipeline has not shipped yet).',
      'resolve-threw':         (probeResult && probeResult.error) || 'fetch / parse error',
      'unknown':               'no probe result',
    }[reason] || reason;
    slot.textContent = `○  Mode B (${label}${ctxStr}) ` +
                       (reason === 'stub-payload' ? 'data pending' : 'unavailable') +
                       ` — ${hint}`;
    slot.title = `registry.resolve("${(opts && opts.layerKey) || '?'}") ` +
                 (reason === 'stub-payload' ? 'returned a stub payload' : 'failed') +
                 '; page rendering unaffected.' +
                 carveTip;
    _emitBadgeEvent(slotId, opts,
      reason === 'stub-payload' ? 'stub' : 'missing',
      probeResult);
    return;
  }

  let verdict = '';
  let pass = true;
  if (opts && typeof opts.compare === 'function') {
    const cmp = opts.compare(probeResult) || {};
    pass = cmp.pass !== false;
    verdict = cmp.summary || '';
  } else {
    verdict = `(${probeResult.n} rows resolved)`;
  }
  slot.className = 'data-source-badge ' + (pass ? 'live' : 'demo');
  const tag = pass ? '●' : '⚠';
  slot.textContent = `${tag}  Mode B (${label}${ctxStr}) — ${verdict}`;
  slot.title = `registry.resolve("${(opts && opts.layerKey) || label}") → ` +
               `${probeResult.n} rows, columns: ${probeResult.sample_keys.join(', ')}` +
               carveTip;

  _emitBadgeEvent(slotId, opts, pass ? 'live' : 'drift', probeResult);
}

/**
 * Emit a CustomEvent on document so a workspace-wide listener (e.g. the
 * top-chrome tally chip) can keep a running count of how many slots are
 * live / drifting / pending across all loaded atlases. Detail shape:
 *
 *   { slotId, label, layerKey, state: 'live' | 'drift' | 'stub' | 'missing',
 *     n, reason }
 *
 * Failure-state callsites use `_emitBadgeEvent(... 'stub' | 'missing', null)`
 * so the listener can still update the tally even when no probe payload
 * exists. Bubbles and is composed so the chip subscriber can live anywhere
 * in the document tree.
 */
function _emitBadgeEvent(slotId, opts, state, probeResult) {
  if (typeof document === 'undefined' || typeof CustomEvent !== 'function') return;
  try {
    document.dispatchEvent(new CustomEvent('mode_b_badge_render', {
      bubbles: true,
      composed: true,
      detail: {
        slotId,
        label:    (opts && opts.label) || null,
        layerKey: (opts && opts.layerKey) || null,
        context:  (opts && opts.context) || null,
        state,
        n:        probeResult && probeResult.n ? probeResult.n : 0,
        reason:   probeResult && probeResult.reason ? probeResult.reason : null,
      },
    }));
  } catch (_) {
    // Older browsers without composed-event support — silent; the tally
    // chip is best-effort UX, not a correctness primitive.
  }
}

/** Build the trailing "vs carve …" line for a badge tooltip. Empty when
 *  no provenance block was passed. */
function _carveTooltip(prov) {
  if (!prov) return '';
  const parts = [];
  if (prov.data_version)   parts.push(`carve ${prov.data_version}`);
  if (prov.content_sha256) parts.push(`sha ${prov.content_sha256}`);
  if (prov.carved_at)      parts.push(prov.carved_at);
  return parts.length ? `\n— vs carve: ${parts.join(' · ')}` : '';
}


/**
 * Statistic helpers — small enough that a shared import beats duplication.
 */
export function medianOf(rows, ...keys) {
  const xs = [];
  for (const r of rows || []) {
    for (const k of keys) {
      const v = r && r[k];
      if (typeof v === 'number' && Number.isFinite(v)) { xs.push(v); break; }
    }
  }
  if (xs.length === 0) return null;
  xs.sort((a, b) => a - b);
  const mid = xs.length >> 1;
  return (xs.length & 1) ? xs[mid] : 0.5 * (xs[mid - 1] + xs[mid]);
}

export function meanOf(rows, ...keys) {
  let sum = 0, n = 0;
  for (const r of rows || []) {
    for (const k of keys) {
      const v = r && r[k];
      if (typeof v === 'number' && Number.isFinite(v)) { sum += v; n += 1; break; }
    }
  }
  return n ? sum / n : null;
}

export function distinctCount(rows, key) {
  const s = new Set();
  for (const r of rows || []) if (r && r[key] != null) s.add(r[key]);
  return s.size;
}

/**
 * Relative-difference helper. Returns null when either input is null/NaN
 * or baseline is zero. Used by comparators to decide pass/drift against
 * a carve baseline (e.g. median H vs carve median H).
 */
export function relDiff(observed, baseline) {
  if (observed == null || baseline == null) return null;
  if (typeof observed !== 'number' || typeof baseline !== 'number') return null;
  if (!Number.isFinite(observed) || !Number.isFinite(baseline) || baseline === 0) return null;
  return Math.abs(observed - baseline) / Math.abs(baseline);
}
