// core/sidebar_floating.js
// =====================================================================
// Workspace-wide floating-sidebar mode for any page with `.wrap > aside`.
//
// Origin: ported from inversion-atlas/atlases/inversion/shared/sidebar_floating.js
// on 2026-05-26 (Quentin's "the setting bar on the left hand side it
// should be floating and it shouldn't be on the left hand side"). Promoted
// to atlas-core so every atlas's pages get the feature without per-atlas
// wiring; the install fires on every `shell.page_mount` event from the
// router and opt-in is just "include a #sidebarFloatBtn in the page HTML".
//
// What this does:
//
//   1. After each page mount, scan for `.wrap > aside` + `#sidebarFloatBtn`.
//      If both are present, install the toggle + drag handle.
//   2. Click #sidebarFloatBtn → flips .wrap[data-sidebar] between '' (the
//      docked default) and 'floating'.
//   3. In 'floating' mode the CSS (shell.css §floating-sidebar) takes aside
//      out of the grid via position:fixed; main reclaims the column width.
//   4. The first <h2> in the aside becomes a drag handle (cursor:grab).
//      Pointer-down + drag repositions; pointer-up persists top/left to
//      localStorage.
//   5. Position is restored on the next mount. If stored position would
//      land off-screen (window resized) the panel snaps to default top-right.
//   6. Idempotent — each aside is only wired once (`data-floatDragWired='1'`).
//
// Coupling: relies on the `.wrap > aside` markup that every atlas uses
// (see shell_chrome.js's `_wireGlobalSettingsBtn` fallback — same probe).
// No imports from any atlas; lives entirely in atlas-core.
// =====================================================================

// 'closed'   — aside hidden, main reclaims full width (default for opt-in pages)
// 'floating' — aside detached as a draggable floating panel
// 'docked'   — legacy; aside lives in the grid (kept for back-compat / non-opt-in pages)
const LS_MODE_KEY = 'atlas.sidebarFloating.mode';
const LS_POS_KEY  = 'atlas.sidebarFloating.pos';    // JSON {left, top}

// Legacy keys from the inversion-atlas-only prototype (shipped 2026-05-26,
// promoted to atlas-core same day). Read once on first install so users
// don't lose their floating-mode + position when the shell takes over;
// never written. After the first migration the values land under the
// canonical atlas.* keys above and stay there.
const LEGACY_LS_MODE_KEY = 'pca_scrubber_v3.sidebarFloating.mode';
const LEGACY_LS_POS_KEY  = 'pca_scrubber_v3.sidebarFloating.pos';

let _shellWired = false;
const _wiredButtons = new WeakSet();

/**
 * Wire the auto-install once per shell lifetime. Subscribes to the
 * `shell.page_mount` event the router emits after every page mount and
 * scans the just-mounted DOM for `.wrap > aside` + `#sidebarFloatBtn`.
 * Idempotent.
 *
 * Pass the AtlasState so we can use its event bus; falls back to a
 * one-shot install() if no state is given (manual call from a page).
 */
export function attachFloatingSidebarToShell(atlasState) {
  if (_shellWired) return;
  _shellWired = true;
  if (atlasState && typeof atlasState.subscribe === 'function') {
    atlasState.subscribe('shell.page_mount', () => {
      // rAF so the page HTML has been inserted before we query.
      if (typeof requestAnimationFrame === 'function') requestAnimationFrame(installFloatingSidebar);
      else setTimeout(installFloatingSidebar, 0);
    });
  }
  // Also try once now in case a page is already mounted at shell-attach time.
  installFloatingSidebar();
}

/**
 * One-shot install. Idempotent per (aside, button) pair — safe to call
 * from a page mount() if the atlasState subscribe path isn't available.
 */
export function installFloatingSidebar() {
  if (typeof document === 'undefined') return;

  const wrap  = document.querySelector('.wrap');
  const aside = wrap && wrap.querySelector(':scope > aside');
  const btn   = document.getElementById('sidebarFloatBtn');
  if (!wrap || !aside || !btn) return;   // page didn't opt in

  // Restore mode on every install (handles page-switch with persisted mode).
  let mode = _readMode();
  _applyMode(wrap, aside, mode);
  _syncBtnLabel(btn, mode);

  // Bind click handler only once per button instance.
  // 2026-05-26: gear click toggles between 'closed' (hidden) and 'floating'
  // (visible). 'docked' is no longer reachable from the toggle — it remains
  // a valid persisted state for users who set it before this change, but
  // the next click flips them into the closed/floating cycle.
  if (!_wiredButtons.has(btn)) {
    _wiredButtons.add(btn);
    btn.addEventListener('click', () => {
      mode = (mode === 'floating') ? 'closed' : 'floating';
      _writeMode(mode);
      _applyMode(wrap, aside, mode);
      _syncBtnLabel(btn, mode);
    });
  }

  _installDragHandle(aside);
}

// ---------------------------------------------------------------------
// mode application — sets data-sidebar + restores last position
// ---------------------------------------------------------------------

function _applyMode(wrap, aside, mode) {
  if (mode === 'floating') {
    wrap.setAttribute('data-sidebar', 'floating');
    const pos = _readPos();
    if (pos && _isOnScreen(pos)) {
      aside.style.left  = pos.left + 'px';
      aside.style.top   = pos.top  + 'px';
      aside.style.right = 'auto';
    } else {
      aside.style.left  = '';
      aside.style.top   = '';
      aside.style.right = '';
    }
  } else if (mode === 'closed') {
    // Hidden — main reclaims the full grid; the gear in the topbar
    // remains the entry point. CSS rule in shell.css handles display:none.
    wrap.setAttribute('data-sidebar', 'closed');
    aside.style.left  = '';
    aside.style.top   = '';
    aside.style.right = '';
  } else {
    // Legacy 'docked' state. Kept so users who opted into docking before
    // 2026-05-26 don't lose their preference; new defaults skip past it.
    wrap.setAttribute('data-sidebar', '');
    aside.style.left  = '';
    aside.style.top   = '';
    aside.style.right = '';
  }
}

function _syncBtnLabel(btn, mode) {
  if (mode === 'floating') {
    btn.textContent = '⊟';
    btn.title = 'Close the floating settings panel.';
  } else {
    btn.textContent = '📌';
    btn.title = 'Open the floating settings panel. Drag the first heading to move it.';
  }
}

// ---------------------------------------------------------------------
// drag handle — first <h2> in the aside becomes a pointer-drag grip
// ---------------------------------------------------------------------

function _installDragHandle(aside) {
  if (aside.dataset.floatDragWired === '1') return;
  aside.dataset.floatDragWired = '1';

  let dragging = false;
  let startX = 0, startY = 0, startLeft = 0, startTop = 0;

  aside.addEventListener('pointerdown', (e) => {
    const wrap = aside.parentElement;
    if (!wrap || wrap.getAttribute('data-sidebar') !== 'floating') return;
    const handle = aside.querySelector('h2');
    if (!handle || !(e.target === handle || handle.contains(e.target))) return;
    e.preventDefault();
    dragging = true;
    aside.classList.add('sidebar-dragging');
    const rect = aside.getBoundingClientRect();
    startX = e.clientX; startY = e.clientY;
    startLeft = rect.left; startTop = rect.top;
    try { aside.setPointerCapture(e.pointerId); } catch (_) {}
  });

  aside.addEventListener('pointermove', (e) => {
    if (!dragging) return;
    const dx = e.clientX - startX, dy = e.clientY - startY;
    let left = startLeft + dx, top = startTop + dy;
    const w = aside.offsetWidth || 320;
    left = Math.max(-w + 60, Math.min(window.innerWidth - 60, left));
    top  = Math.max(0,        Math.min(window.innerHeight - 40, top));
    aside.style.left  = left + 'px';
    aside.style.top   = top  + 'px';
    aside.style.right = 'auto';
  });

  aside.addEventListener('pointerup', (e) => {
    if (!dragging) return;
    dragging = false;
    aside.classList.remove('sidebar-dragging');
    try { aside.releasePointerCapture(e.pointerId); } catch (_) {}
    const rect = aside.getBoundingClientRect();
    _writePos({ left: Math.round(rect.left), top: Math.round(rect.top) });
  });

  aside.addEventListener('pointercancel', () => {
    if (!dragging) return;
    dragging = false;
    aside.classList.remove('sidebar-dragging');
  });
}

// ---------------------------------------------------------------------
// persistence
// ---------------------------------------------------------------------

function _readMode() {
  try {
    // Prefer the canonical key; fall back to the legacy inversion-atlas
    // key so a user who flipped the toggle BEFORE the shell-level promotion
    // doesn't lose their preference. Legacy key is read-only; the next
    // _writeMode() lands the value under the canonical key.
    // 2026-05-26: default is now 'closed' (sidebar hidden until the user
    // clicks the gear) for opt-in pages. Previously 'docked'.
    const v = localStorage.getItem(LS_MODE_KEY);
    if (v === 'floating' || v === 'docked' || v === 'closed') return v;
    const legacy = localStorage.getItem(LEGACY_LS_MODE_KEY);
    if (legacy === 'floating') return 'floating';
    return 'closed';
  } catch (_) { return 'closed'; }
}
function _writeMode(mode) {
  try { localStorage.setItem(LS_MODE_KEY, mode); } catch (_) {}
}
function _readPos() {
  try {
    let raw = localStorage.getItem(LS_POS_KEY);
    if (!raw) raw = localStorage.getItem(LEGACY_LS_POS_KEY);
    if (!raw) return null;
    const v = JSON.parse(raw);
    if (!v || typeof v.left !== 'number' || typeof v.top !== 'number') return null;
    return v;
  } catch (_) { return null; }
}
function _writePos(pos) {
  try { localStorage.setItem(LS_POS_KEY, JSON.stringify(pos)); } catch (_) {}
}
function _isOnScreen(pos) {
  if (!pos) return false;
  return (pos.left + 80 < window.innerWidth)
      && (pos.left + 320 - 80 > 0)
      && (pos.top + 40 < window.innerHeight)
      && (pos.top >= 0);
}
