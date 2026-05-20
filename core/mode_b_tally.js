// =============================================================================
// atlas-core/core/mode_b_tally.js
// =============================================================================
// Workspace-wide Mode-B tally chip. Mounts into a host element (typically the
// top chrome) and subscribes to the `mode_b_badge_render` CustomEvent that
// `core/mode_b_badge.js` dispatches every time a per-page Mode-B badge
// renders. Shows a single-line count across all loaded atlases:
//
//   Mode B:  ● 8   ⚠ 1   ○ 5
//
// State accounting:
//   live    — probe resolved + comparator.pass === true
//   drift   — probe resolved but comparator.pass === false
//   stub    — payload resolved but extractRows returned empty (stub on disk)
//   missing — probe failed at the registry boundary (404, not injected, etc.)
//
// `stub` and `missing` collapse into the ○ slot in the chip (both are
// "no useful data today"); a tooltip on the chip breaks them apart for
// reviewers debugging missing wiring.
//
// Keyed by slotId so re-renders (page navigation, hover-triggered refresh)
// update the existing entry instead of double-counting. Stale entries from
// unmounted pages are NOT pruned automatically — the chrome subscriber owns
// pruning if it cares (most multi-atlas reviewers want the historical view).
// =============================================================================

const _slots = new Map();   // slotId -> { state, label, layerKey, context, ts }

/**
 * Mount the chip into `host`. Returns a teardown function that removes the
 * listener and the element. Idempotent: if a previous chip is already
 * present in `host`, returns the existing instance's teardown function.
 *
 * Listener attaches to `document` so the chip catches events that bubble
 * up from per-page slots no matter how deep in the DOM they sit.
 */
export function mountModeBTally(host) {
  if (!host || typeof document === 'undefined') return () => {};
  if (host.querySelector(':scope > .mode-b-tally')) {
    // Don't double-mount; first caller wins.
    return () => {};
  }

  const chip = document.createElement('span');
  chip.className = 'mode-b-tally';
  chip.setAttribute('role', 'status');
  _renderChip(chip);
  host.appendChild(chip);

  const onBadgeRender = (e) => {
    const d = e && e.detail;
    if (!d || !d.slotId) return;
    _slots.set(d.slotId, {
      state:    d.state,
      label:    d.label || null,
      layerKey: d.layerKey || null,
      context:  d.context || null,
      ts:       Date.now(),
    });
    _renderChip(chip);
  };
  document.addEventListener('mode_b_badge_render', onBadgeRender);

  return function teardown() {
    document.removeEventListener('mode_b_badge_render', onBadgeRender);
    if (chip.parentNode) chip.parentNode.removeChild(chip);
  };
}

function _tally() {
  let live = 0, drift = 0, pending = 0;
  for (const { state } of _slots.values()) {
    if (state === 'live')                                    live++;
    else if (state === 'drift')                              drift++;
    else                                                     pending++;
  }
  return { live, drift, pending, total: _slots.size };
}

function _renderChip(chip) {
  const t = _tally();
  if (t.total === 0) {
    chip.textContent = '';
    chip.style.display = 'none';
    return;
  }
  chip.style.display = '';
  chip.innerHTML =
    '<span class="label">Mode B</span>' +
    `<span class="count${t.live    ? '' : ' zero'}"><span class="glyph-live">●</span>${t.live}</span>` +
    `<span class="count${t.drift   ? '' : ' zero'}"><span class="glyph-drift">⚠</span>${t.drift}</span>` +
    `<span class="count${t.pending ? '' : ' zero'}"><span class="glyph-stub">○</span>${t.pending}</span>`;

  // Tooltip — slot-by-slot breakdown, sorted by state then most recent.
  const lines = [`${t.total} probe${t.total === 1 ? '' : 's'} across loaded atlases:`];
  const entries = [..._slots.entries()].sort((a, b) =>
    (_stateOrder(a[1].state) - _stateOrder(b[1].state)) || (b[1].ts - a[1].ts));
  for (const [slotId, info] of entries) {
    const glyph = info.state === 'live' ? '●'
                : info.state === 'drift' ? '⚠'
                : info.state === 'stub' ? '○ (stub)'
                : '○';
    const label = info.label || slotId;
    const ctx = info.context ? ` · ${info.context}` : '';
    lines.push(`${glyph} ${label}${ctx}`);
  }
  chip.title = lines.join('\n');
}

function _stateOrder(state) {
  switch (state) {
    case 'live':    return 0;
    case 'drift':   return 1;
    case 'stub':    return 2;
    case 'missing': return 3;
    default:        return 9;
  }
}
