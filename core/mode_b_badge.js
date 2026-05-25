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
  // 2026-05-20: short-circuit when the layer is flagged `disabled: true` in
  // its registry entry. The flag is the canonical "contract-only — upstream
  // pipeline hasn't shipped yet" signal. Without this, probeModeB fires a
  // fetch that we KNOW will 404, just to land at the same "data pending"
  // badge. Skipping the fetch silences the server-log noise + the browser
  // console error.
  if (typeof registry.getLayerEntry === 'function') {
    const entry = registry.getLayerEntry(layerKey);
    if (entry && entry.disabled === true) {
      return {
        ok:      false,
        reason:  'layer-disabled',
        payload: null,
        disabled_reason: entry._disabled_reason || null,
      };
    }
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

  // Cache the result so the expanded card can be re-rendered from a
  // click without re-running the probe. Stored per slot; overwrites
  // on every re-render so the card always reflects the latest fetch.
  _lastProbe.set(slotId, { probeResult, opts, ts: Date.now() });

  // Idempotently wire the click handler the first time we render into
  // this slot. The handler stays attached even when textContent is
  // replaced on re-renders; we mark a flag on the element so we don't
  // double-bind. Cursor + role hint so the click affordance is visible.
  if (!slot.dataset.modeBClickable) {
    slot.dataset.modeBClickable = '1';
    slot.setAttribute('role', 'button');
    slot.setAttribute('tabindex', '0');
    slot.setAttribute('aria-haspopup', 'true');
    slot.setAttribute('aria-expanded', 'false');
    slot.style.cursor = 'pointer';
    slot.addEventListener('click', (e) => {
      // Don't toggle when the click landed on an interactive child
      // (e.g. a future inline link in the badge text).
      if (e.target && e.target !== slot && e.target.tagName === 'A') return;
      _toggleCard(slot, slotId);
    });
    slot.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        _toggleCard(slot, slotId);
      } else if (e.key === 'Escape') {
        _closeCard(slot);
      }
    });
  }

  if (!probeResult || !probeResult.ok) {
    slot.className = 'data-source-badge demo';
    const reason = (probeResult && probeResult.reason) || 'unknown';
    const hint = {
      'registry-not-injected': 'shell did not inject the registry — running standalone?',
      'empty-result':          'layer resolved but rows[] is empty — check the source.',
      'stub-payload':          'payload resolved but is a stub (upstream pipeline has not shipped yet).',
      'layer-disabled':        (probeResult && probeResult.disabled_reason)
                                 || 'layer flagged `disabled: true` in registry — upstream pipeline has not shipped yet.',
      'resolve-threw':         (probeResult && probeResult.error) || 'fetch / parse error',
      'unknown':               'no probe result',
    }[reason] || reason;
    // Treat both stub-payload (resolved but empty) AND layer-disabled
    // (skipped the fetch by design) as user-facing "data pending" — both
    // are "the file is coming later" states, not errors.
    const isPending = (reason === 'stub-payload' || reason === 'layer-disabled');
    slot.textContent = `○  Mode B (${label}${ctxStr}) ` +
                       (isPending ? 'data pending' : 'unavailable') +
                       ` — ${hint}`;
    slot.title = `registry.resolve("${(opts && opts.layerKey) || '?'}") ` +
                 (reason === 'stub-payload' ? 'returned a stub payload'
                   : reason === 'layer-disabled' ? 'skipped — layer flagged disabled'
                   : 'failed') +
                 '; page rendering unaffected.' +
                 carveTip;
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
}

// ---------------------------------------------------------------------------
// Per-slot last-probe state — used by the click-to-expand card. Keyed by
// slotId so re-renders update in place. Not exported; only the card
// renderer below reads it.
// ---------------------------------------------------------------------------
const _lastProbe = new Map();  // slotId -> { probeResult, opts, ts }

/**
 * Toggle the expanded card below `slot`. The card is a sibling div
 * appended right after the badge; created lazily on first toggle. Re-
 * renders content from `_lastProbe[slotId]` so it always reflects the
 * latest probe state without re-running the fetch.
 */
function _toggleCard(slot, slotId) {
  const existing = slot.nextElementSibling;
  if (existing && existing.classList && existing.classList.contains('mode-b-card') &&
      existing.dataset.forSlot === slotId) {
    // Toggle: hide if visible, show + refresh if hidden.
    if (existing.style.display === 'none') {
      _renderCard(existing, slotId);
      existing.style.display = 'block';
      slot.setAttribute('aria-expanded', 'true');
    } else {
      existing.style.display = 'none';
      slot.setAttribute('aria-expanded', 'false');
    }
    return;
  }
  // First open — create + insert.
  const card = document.createElement('div');
  card.className = 'mode-b-card';
  card.dataset.forSlot = slotId;
  _renderCard(card, slotId);
  slot.parentNode.insertBefore(card, slot.nextSibling);
  slot.setAttribute('aria-expanded', 'true');
}

function _closeCard(slot) {
  const existing = slot.nextElementSibling;
  if (existing && existing.classList && existing.classList.contains('mode-b-card')) {
    existing.style.display = 'none';
    slot.setAttribute('aria-expanded', 'false');
  }
}

/**
 * Render the card body. Reads the latest probe from `_lastProbe[slotId]`.
 * Shape:
 *   ┌ header — layer key (large) · context · close (×)
 *   │ summary — comparator output OR failure reason
 *   │ metadata — n rows, columns, carve fingerprint
 *   │ payload preview — first 5 rows as a small grid (when present)
 *   └ footer — link to the SPEC
 */
function _renderCard(card, slotId) {
  const entry = _lastProbe.get(slotId);
  if (!entry) {
    card.innerHTML =
      '<div class="mode-b-card-body"><em>No probe data captured yet — ' +
      'refresh the page.</em></div>';
    return;
  }
  const { probeResult, opts } = entry;
  const label = (opts && opts.label) || 'pipeline';
  const layerKey = (opts && opts.layerKey) || '(unknown layer)';
  const ctxStr = (opts && opts.context) ? ` · ${opts.context}` : '';

  const parts = [];
  parts.push('<div class="mode-b-card-header">');
  parts.push(`<div class="mode-b-card-title"><code>${_escapeHtml(layerKey)}</code>` +
             `<span class="mode-b-card-ctx">${_escapeHtml(label + ctxStr)}</span></div>`);
  parts.push('<button class="mode-b-card-close" type="button" aria-label="Close card">×</button>');
  parts.push('</div>');

  parts.push('<div class="mode-b-card-body">');

  // ----- State + summary line -----
  if (!probeResult || !probeResult.ok) {
    const reason = (probeResult && probeResult.reason) || 'unknown';
    const glyph =
      reason === 'stub-payload' || reason === 'layer-disabled' ? '○' : '○';
    parts.push(`<div class="mode-b-card-state demo">${glyph} ${_escapeHtml(_reasonLabel(reason))}</div>`);
    if (probeResult && probeResult.error) {
      parts.push(`<div class="mode-b-card-error"><strong>Error:</strong> <code>${_escapeHtml(probeResult.error)}</code></div>`);
    }
    if (probeResult && probeResult.disabled_reason) {
      parts.push(`<div class="mode-b-card-error">${_escapeHtml(probeResult.disabled_reason)}</div>`);
    }
  } else {
    // Run the comparator again to get pass/summary (cheap; same logic
    // renderModeBBadge already used). Defaults to a generic summary.
    let pass = true, summary = `${probeResult.n} rows resolved`;
    if (opts && typeof opts.compare === 'function') {
      try {
        const cmp = opts.compare(probeResult) || {};
        pass = cmp.pass !== false;
        summary = cmp.summary || summary;
      } catch (_) { /* keep defaults */ }
    }
    const glyph = pass ? '●' : '⚠';
    parts.push(`<div class="mode-b-card-state ${pass ? 'live' : 'demo'}">${glyph} ${_escapeHtml(summary)}</div>`);
  }

  // ----- Metadata grid -----
  if (probeResult && probeResult.ok) {
    parts.push('<div class="mode-b-card-meta">');
    parts.push(`<div class="meta-row"><span class="k">rows</span><span class="v"><code>${probeResult.n}</code></span></div>`);
    parts.push(`<div class="meta-row"><span class="k">columns</span><span class="v"><code>${_escapeHtml((probeResult.sample_keys || []).join(', ') || '(none)')}</code></span></div>`);
    if (opts && opts.provenance) {
      const p = opts.provenance;
      if (p.data_version) {
        parts.push(`<div class="meta-row"><span class="k">vs carve</span><span class="v"><code>${_escapeHtml(p.data_version)}</code></span></div>`);
      }
      if (p.content_sha256) {
        parts.push(`<div class="meta-row"><span class="k">carve sha</span><span class="v"><code>${_escapeHtml(p.content_sha256)}</code></span></div>`);
      }
    }
    parts.push('</div>');

    // ----- Payload preview (first 5 rows) -----
    if (Array.isArray(probeResult.rows) && probeResult.rows.length > 0) {
      const preview = probeResult.rows.slice(0, 5);
      const cols = probeResult.sample_keys || Object.keys(preview[0] || {});
      const visibleCols = cols.slice(0, 6);   // cap horizontal density
      parts.push('<div class="mode-b-card-preview">');
      parts.push(`<div class="preview-title">first ${preview.length} of ${probeResult.n} rows` +
                 (visibleCols.length < cols.length ? ` · first ${visibleCols.length} of ${cols.length} cols` : '') +
                 '</div>');
      parts.push('<table class="preview-table"><thead><tr>');
      for (const c of visibleCols) parts.push(`<th>${_escapeHtml(c)}</th>`);
      parts.push('</tr></thead><tbody>');
      for (const row of preview) {
        parts.push('<tr>');
        for (const c of visibleCols) {
          const v = row[c];
          const cell = v == null ? '<span class="null">—</span>'
                     : typeof v === 'number' ? _fmtNumber(v)
                     : _escapeHtml(String(v).slice(0, 60));
          parts.push(`<td>${cell}</td>`);
        }
        parts.push('</tr>');
      }
      parts.push('</tbody></table>');
      parts.push('</div>');
    }
  }

  parts.push('</div>');   // card-body

  parts.push('<div class="mode-b-card-footer">');
  parts.push('See <code>core/mode_b_badge.js</code> · <code>docs/SPEC_mode_b_pattern.md</code>');
  parts.push('</div>');

  card.innerHTML = parts.join('');

  // Wire close button
  const closeBtn = card.querySelector('.mode-b-card-close');
  if (closeBtn) {
    closeBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      card.style.display = 'none';
      const slot = document.getElementById(slotId);
      if (slot) slot.setAttribute('aria-expanded', 'false');
    });
  }
}

function _reasonLabel(reason) {
  return {
    'registry-not-injected': 'registry not injected — running standalone?',
    'empty-result':          'layer resolved but rows[] is empty',
    'stub-payload':          'payload resolved but is a stub (data pending)',
    'layer-disabled':        'layer flagged disabled in registry',
    'resolve-threw':         'registry.resolve threw an error',
    'unknown':               'no probe result',
  }[reason] || reason;
}

function _fmtNumber(v) {
  if (!Number.isFinite(v)) return '<span class="null">—</span>';
  const abs = Math.abs(v);
  // Compact-scientific for very small/large, plain otherwise
  if (abs !== 0 && (abs < 1e-3 || abs >= 1e7)) return `<code>${v.toExponential(3)}</code>`;
  if (Number.isInteger(v)) return `<code>${v.toString()}</code>`;
  return `<code>${v.toFixed(4)}</code>`;
}

function _escapeHtml(s) {
  return String(s ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
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
