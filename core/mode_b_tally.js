// =============================================================================
// atlas-core/core/mode_b_tally.js
// =============================================================================
// Workspace-wide Mode-B tally chip. Mounts into a host element (typically the
// top chrome) and subscribes to two CustomEvents:
//
//   1. `mode_b_badge_render` (dispatched by core/mode_b_badge.js every time
//      a per-page Mode-B badge renders) — updates the slot count.
//   2. `shell.page_mount` (dispatched by atlas_router on navigation) —
//      remembers the active (atlas_id, page_id) so subsequent badge
//      events can be tagged with their home page and made navigable.
//
// Shows a single-line count across loaded atlases:
//
//   Mode B:  ● 8   ⚠ 1   ○ 9
//
// 2026-05-20: now clickable. Click → popover listing every slot grouped by
// atlas, with state glyph + label + a "go" link per slot that hash-navigates
// to that page (`#/atlas_id/page_id`). Click outside / Escape to close.
//
// State accounting:
//   live    — probe resolved + comparator.pass === true
//   drift   — probe resolved but comparator.pass === false
//   stub    — payload resolved but extractRows returned empty (stub on disk)
//   missing — probe failed at the registry boundary (404, not injected, etc.)
//
// `stub` and `missing` collapse into the ○ slot in the chip; the popover
// breaks them apart visually so reviewers can tell "data pending" from
// "registry unreachable".
//
// Slot table is keyed by slotId (re-renders update in place, no double-
// count). Tagged with (atlas_id, page_id) from the most recent shell.page_mount
// at the time the badge event fires — accurate in practice because Mode-B
// badges always render at mount time.
// =============================================================================

const _slots = new Map();   // slotId -> { state, label, layerKey, context, ts, atlas_id, page_id }

// Tracked from `shell.page_mount`; the most recently mounted (atlas, page).
// Any badge event in the next few seconds is presumed to belong to it.
let _activeAtlasId = null;
let _activePageId  = null;

/**
 * Mount the chip into `host`. Returns a teardown function. Idempotent.
 */
export function mountModeBTally(host) {
  if (!host || typeof document === 'undefined') return () => {};
  if (host.querySelector(':scope > .mode-b-tally')) return () => {};

  const chip = document.createElement('span');
  chip.className = 'mode-b-tally';
  chip.setAttribute('role', 'button');
  chip.setAttribute('tabindex', '0');
  chip.setAttribute('aria-haspopup', 'true');
  chip.setAttribute('aria-expanded', 'false');
  _renderChip(chip);
  host.appendChild(chip);

  // Popover lives in document.body so it can escape any overflow:hidden in
  // the chrome and so absolute positioning is straightforward. Created
  // lazily on first open.
  let popover = null;

  function openPopover() {
    if (!popover) {
      popover = document.createElement('div');
      popover.className = 'mode-b-tally-popover';
      popover.setAttribute('role', 'dialog');
      document.body.appendChild(popover);
    }
    _renderPopover(popover);
    _positionPopover(popover, chip);
    popover.style.display = 'block';
    chip.setAttribute('aria-expanded', 'true');
  }
  function closePopover() {
    if (popover) popover.style.display = 'none';
    chip.setAttribute('aria-expanded', 'false');
  }
  function togglePopover() {
    const open = popover && popover.style.display === 'block';
    if (open) closePopover(); else openPopover();
  }

  // Click chip → toggle
  chip.addEventListener('click', (e) => {
    e.stopPropagation();
    togglePopover();
  });
  // Enter / Space for keyboard
  chip.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      togglePopover();
    } else if (e.key === 'Escape') {
      closePopover();
    }
  });
  // Click outside → close
  const onDocClick = (e) => {
    if (!popover || popover.style.display !== 'block') return;
    if (popover.contains(e.target) || chip.contains(e.target)) return;
    closePopover();
  };
  document.addEventListener('click', onDocClick);
  const onEscape = (e) => { if (e.key === 'Escape') closePopover(); };
  document.addEventListener('keydown', onEscape);

  const onBadgeRender = (e) => {
    const d = e && e.detail;
    if (!d || !d.slotId) return;
    _slots.set(d.slotId, {
      state:    d.state,
      label:    d.label || null,
      layerKey: d.layerKey || null,
      context:  d.context || null,
      atlas_id: _activeAtlasId,
      page_id:  _activePageId,
      ts:       Date.now(),
    });
    _renderChip(chip);
    if (popover && popover.style.display === 'block') _renderPopover(popover);
  };
  document.addEventListener('mode_b_badge_render', onBadgeRender);

  const onPageMount = (e) => {
    const d = e && e.detail;
    if (!d) return;
    _activeAtlasId = d.atlas_id || _activeAtlasId;
    _activePageId  = d.page_id  || _activePageId;
  };
  document.addEventListener('shell.page_mount', onPageMount);

  return function teardown() {
    document.removeEventListener('mode_b_badge_render', onBadgeRender);
    document.removeEventListener('shell.page_mount', onPageMount);
    document.removeEventListener('click', onDocClick);
    document.removeEventListener('keydown', onEscape);
    if (popover && popover.parentNode) popover.parentNode.removeChild(popover);
    if (chip.parentNode) chip.parentNode.removeChild(chip);
  };
}

function _tally() {
  let live = 0, drift = 0, pending = 0;
  for (const { state } of _slots.values()) {
    if (state === 'live')      live++;
    else if (state === 'drift') drift++;
    else                        pending++;   // stub | missing | unknown
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
  chip.title = `${t.total} probe${t.total === 1 ? '' : 's'} — click for the full breakdown`;
}

function _renderPopover(popover) {
  const t = _tally();
  // Group slots by atlas_id; unknown atlas goes last.
  const byAtlas = new Map();
  for (const [slotId, info] of _slots.entries()) {
    const key = info.atlas_id || '(unknown atlas)';
    if (!byAtlas.has(key)) byAtlas.set(key, []);
    byAtlas.get(key).push({ slotId, ...info });
  }
  // Sort: known atlases by name, unknown last; within atlas by state.
  const atlasKeys = [...byAtlas.keys()].sort((a, b) => {
    const aU = a.startsWith('(');
    const bU = b.startsWith('(');
    if (aU !== bU) return aU ? 1 : -1;
    return a.localeCompare(b);
  });

  const parts = [];
  parts.push('<div class="mode-b-tally-popover-header">');
  parts.push(`<span class="title">Mode B across loaded atlases</span>`);
  parts.push(`<span class="counts">`);
  parts.push(`<span class="glyph-live">●</span>${t.live} `);
  parts.push(`<span class="glyph-drift">⚠</span>${t.drift} `);
  parts.push(`<span class="glyph-stub">○</span>${t.pending}`);
  parts.push(`</span>`);
  parts.push('</div>');

  parts.push('<div class="mode-b-tally-popover-body">');
  for (const atlasKey of atlasKeys) {
    parts.push(`<div class="atlas-group">`);
    parts.push(`<div class="atlas-name">${_escape(atlasKey)}</div>`);
    const items = byAtlas.get(atlasKey).sort((a, b) =>
      (_stateOrder(a.state) - _stateOrder(b.state)) || (b.ts - a.ts));
    for (const info of items) {
      const glyph = info.state === 'live'    ? '<span class="glyph-live">●</span>'
                  : info.state === 'drift'   ? '<span class="glyph-drift">⚠</span>'
                  : info.state === 'stub'    ? '<span class="glyph-stub">○</span><span class="state-tag">stub</span>'
                  : info.state === 'missing' ? '<span class="glyph-stub">○</span><span class="state-tag">missing</span>'
                  :                            '<span class="glyph-stub">○</span>';
      const label = _escape(info.label || info.slotId);
      const ctx = info.context ? `<span class="ctx"> · ${_escape(info.context)}</span>` : '';
      // Jump link — only when we know both atlas_id and page_id.
      const canJump = !atlasKey.startsWith('(') && info.page_id;
      const jump = canJump
        ? `<a class="jump" href="#/${encodeURIComponent(info.atlas_id)}/${encodeURIComponent(info.page_id)}" data-jump="1">go</a>`
        : `<span class="jump disabled" title="atlas/page id not captured">—</span>`;
      parts.push(`<div class="slot">${glyph}<span class="label">${label}${ctx}</span>${jump}</div>`);
    }
    parts.push('</div>');
  }
  parts.push('</div>');

  parts.push('<div class="mode-b-tally-popover-footer">');
  parts.push('Click <code>go</code> to navigate. See <code>core/mode_b_badge.js</code> for the helper.');
  parts.push('</div>');

  popover.innerHTML = parts.join('');

  // Wire jump clicks — close popover after navigation (router will handle the hash).
  popover.querySelectorAll('a.jump[data-jump]').forEach((a) => {
    a.addEventListener('click', () => {
      // Defer close so the hashchange handler in atlas_router gets the click.
      setTimeout(() => { popover.style.display = 'none'; }, 0);
    });
  });
}

function _positionPopover(popover, chip) {
  const r = chip.getBoundingClientRect();
  // Anchor under the chip, right-aligned to the chip's right edge.
  popover.style.position = 'fixed';
  popover.style.top  = `${r.bottom + 6}px`;
  // 360px is the popover's max-width; pin to the chip's right edge or the
  // viewport edge, whichever is more conservative.
  const maxW = 360;
  const leftPin = Math.max(8, r.right - maxW);
  popover.style.left = `${leftPin}px`;
  popover.style.maxWidth = `${maxW}px`;
  popover.style.zIndex = '10000';
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

function _escape(s) {
  return String(s ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}
