// Smoke test for core/sidebar_floating.js (workspace-wide promotion
// 2026-05-26 of the inversion-atlas prototype).
//
// Covers behaviors specific to the shell-level wiring:
//   - attachFloatingSidebarToShell subscribes to shell.page_mount
//   - it's idempotent at the shell level (second call is a no-op)
//   - the rAF-deferred install fires after each page_mount
//   - installFloatingSidebar bails silently on pages without #sidebarFloatBtn
//   - click toggles data-sidebar; mode persists across re-installs
//   - the new localStorage keys ('atlas.sidebarFloating.*') are used,
//     not the legacy inversion-atlas keys ('pca_scrubber_v3.*')
//
// Run from repo root:
//   node atlas-core/tests/test_sidebar_floating.js

let pass = 0, fail = 0;
function check(label, cond, extra) {
  if (cond) { pass++; console.log('  ✓', label); }
  else      { fail++; console.log('  ✗', label, extra ? ' — ' + extra : ''); }
}
function group(name) { console.log('\n--- ' + name + ' ---'); }

// ---------------------------------------------------------------------------
// DOM + localStorage shims. The module reaches for document,
// document.getElementById, document.querySelector, requestAnimationFrame,
// window.innerWidth/innerHeight, and localStorage.
// ---------------------------------------------------------------------------

const _store = new Map();
globalThis.localStorage = {
  getItem: (k) => _store.has(k) ? _store.get(k) : null,
  setItem: (k, v) => _store.set(k, String(v)),
  removeItem: (k) => _store.delete(k),
  clear: () => _store.clear(),
};

// requestAnimationFrame runs synchronously in tests so we don't have to
// await frames. The module also falls back to setTimeout when rAF is
// missing — both are sync here.
let _rafQueue = [];
globalThis.requestAnimationFrame = (fn) => {
  _rafQueue.push(fn);
  return _rafQueue.length;
};
function flushRaf() {
  while (_rafQueue.length) {
    const fn = _rafQueue.shift();
    try { fn(); } catch (e) { console.warn('rAF fn threw:', e); }
  }
}

globalThis.window = { innerWidth: 1280, innerHeight: 800 };

class FakeEl {
  constructor(tag, attrs = {}) {
    this.tagName = tag.toUpperCase();
    this.children = [];
    this.parentElement = null;
    this.attributes = new Map();
    this.style = {};
    this.dataset = {};
    this.classList = (() => {
      const set = new Set();
      return {
        add: (c) => set.add(c),
        remove: (c) => set.delete(c),
        contains: (c) => set.has(c),
      };
    })();
    this._listeners = new Map();
    for (const [k, v] of Object.entries(attrs)) {
      if (k === 'id') this.id = v;
      else if (k === 'textContent') this.textContent = v;
      else this.attributes.set(k, v);
    }
  }
  appendChild(c) { this.children.push(c); c.parentElement = this; return c; }
  getBoundingClientRect() { return { left: 100, top: 100, width: 320, height: 600 }; }
  setAttribute(k, v) { this.attributes.set(k, String(v)); }
  getAttribute(k) { return this.attributes.has(k) ? this.attributes.get(k) : null; }
  querySelector(sel) { return _querySelector(this, sel); }
  addEventListener(ev, fn) {
    if (!this._listeners.has(ev)) this._listeners.set(ev, new Set());
    this._listeners.get(ev).add(fn);
  }
  _fire(ev, payload) {
    const set = this._listeners.get(ev);
    if (!set) return;
    for (const fn of set) fn(payload || {});
  }
  setPointerCapture() {}
  releasePointerCapture() {}
}

function _querySelector(root, sel) {
  if (sel === ':scope > aside') {
    return root.children.find(c => c.tagName === 'ASIDE') || null;
  }
  if (sel === 'h2') {
    return _findFirst(root, c => c.tagName === 'H2');
  }
  if (sel === '.wrap') {
    return _findFirst(root, c =>
      c.classList && c.classList.contains('wrap')
   || (c.attributes && c.attributes.get('class') === 'wrap'));
  }
  return null;
}
function _findFirst(root, pred) {
  for (const c of root.children) {
    if (pred(c)) return c;
    const r = _findFirst(c, pred);
    if (r) return r;
  }
  return null;
}

function buildPageDom({ withFloatBtn = true } = {}) {
  const root = new FakeEl('div');
  const wrap = new FakeEl('div', { class: 'wrap' });
  wrap.classList.add('wrap');
  const aside = new FakeEl('aside');
  aside.appendChild(new FakeEl('h2', { textContent: 'Settings' }));
  wrap.appendChild(aside);
  if (withFloatBtn) wrap.appendChild(new FakeEl('button', { id: 'sidebarFloatBtn' }));
  root.appendChild(wrap);
  globalThis.document = {
    querySelector: (sel) => _querySelector(root, sel),
    getElementById: (id) => _findFirst(root, c => c.id === id),
  };
  return { root, wrap, aside };
}

// Tiny AtlasState-shaped stub — only the event-bus surface the shell touches.
function makeState() {
  const subs = new Map();
  return {
    subscribe(ev, fn) {
      if (!subs.has(ev)) subs.set(ev, new Set());
      subs.get(ev).add(fn);
    },
    emit(ev, payload) {
      const set = subs.get(ev);
      if (!set) return;
      for (const fn of set) fn(payload || {});
    },
  };
}

// Cache-bust import so each group resets the module's _shellWired flag.
async function freshShell() {
  return import('../core/sidebar_floating.js?t=' + Date.now() + Math.random());
}

// ---------------------------------------------------------------------------
group('attachFloatingSidebarToShell is idempotent + subscribes once');
{
  _store.clear();
  buildPageDom();
  const state = makeState();
  const mod = await freshShell();
  mod.attachFloatingSidebarToShell(state);
  mod.attachFloatingSidebarToShell(state);   // second call should be a no-op
  flushRaf();
  // Fire one page_mount — should trigger exactly one rAF-deferred install.
  state.emit('shell.page_mount', { atlas_id: 'inversion', page_id: 'local_pca_dosage' });
  check('one rAF queued after page_mount', _rafQueue.length === 1);
  flushRaf();
  // The install ran and stamped the aside.
  const wrap = document.querySelector('.wrap');
  check('aside dataset.floatDragWired = "1"',
        wrap.querySelector(':scope > aside').dataset.floatDragWired === '1');
}

// ---------------------------------------------------------------------------
group('bails silently when page has no #sidebarFloatBtn');
{
  _store.clear();
  buildPageDom({ withFloatBtn: false });
  const state = makeState();
  const mod = await freshShell();
  mod.attachFloatingSidebarToShell(state);
  flushRaf();
  state.emit('shell.page_mount', {});
  let threw = false;
  try { flushRaf(); } catch (e) { threw = true; }
  check('install did not throw on bare page', !threw);
  const wrap = document.querySelector('.wrap');
  check('aside not wired (no float button)',
        wrap.querySelector(':scope > aside').dataset.floatDragWired !== '1');
}

// ---------------------------------------------------------------------------
group('click flips data-sidebar; mode persists');
{
  _store.clear();
  const { wrap } = buildPageDom();
  const state = makeState();
  const mod = await freshShell();
  mod.attachFloatingSidebarToShell(state);
  flushRaf();
  state.emit('shell.page_mount', {});
  flushRaf();
  const btn = document.getElementById('sidebarFloatBtn');
  check('initial state docked', wrap.getAttribute('data-sidebar') !== 'floating');
  btn._fire('click');
  check('after click → floating',
        wrap.getAttribute('data-sidebar') === 'floating');
  check('atlas-core LS key written',
        localStorage.getItem('atlas.sidebarFloating.mode') === 'floating');
  check('legacy inversion-atlas LS key NOT written',
        localStorage.getItem('pca_scrubber_v3.sidebarFloating.mode') === null);
  btn._fire('click');
  check('after 2nd click → docked',
        wrap.getAttribute('data-sidebar') !== 'floating');
  check('LS key flipped back', localStorage.getItem('atlas.sidebarFloating.mode') === 'docked');
}

// ---------------------------------------------------------------------------
group('mode round-trips across page navigations');
{
  _store.clear();
  const state = makeState();
  const mod = await freshShell();
  mod.attachFloatingSidebarToShell(state);
  // Page A — flip to floating.
  {
    buildPageDom();
    flushRaf();
    state.emit('shell.page_mount', { atlas_id: 'inversion', page_id: 'A' });
    flushRaf();
    document.getElementById('sidebarFloatBtn')._fire('click');
  }
  // Page B — fresh DOM, mode should auto-restore.
  {
    const { wrap } = buildPageDom();
    state.emit('shell.page_mount', { atlas_id: 'inversion', page_id: 'B' });
    flushRaf();
    check('page B restored floating from LS',
          wrap.getAttribute('data-sidebar') === 'floating');
    check('page B button label = ⊟',
          document.getElementById('sidebarFloatBtn').textContent === '⊟');
  }
}

// ---------------------------------------------------------------------------
group('one-shot installFloatingSidebar (manual call) still works');
{
  _store.clear();
  const { wrap } = buildPageDom();
  const mod = await freshShell();
  // No shell wiring — call directly from a page mount equivalent.
  mod.installFloatingSidebar();
  check('docked default applied',
        wrap.getAttribute('data-sidebar') === '');
  document.getElementById('sidebarFloatBtn')._fire('click');
  check('manual install reacts to click', wrap.getAttribute('data-sidebar') === 'floating');
}

// ---------------------------------------------------------------------------
group('legacy inversion-atlas LS keys migrate on first install');
{
  // Simulate a user who flipped to floating BEFORE the shell-level
  // promotion: only the legacy 'pca_scrubber_v3.*' keys are present.
  _store.clear();
  localStorage.setItem('pca_scrubber_v3.sidebarFloating.mode', 'floating');
  localStorage.setItem('pca_scrubber_v3.sidebarFloating.pos',
    JSON.stringify({ left: 200, top: 150 }));
  const { wrap, aside } = buildPageDom();
  const mod = await freshShell();
  mod.installFloatingSidebar();
  check('legacy mode picked up → wrap is floating',
        wrap.getAttribute('data-sidebar') === 'floating');
  check('legacy position restored on aside (left)',
        aside.style.left === '200px');
  check('legacy position restored on aside (top)',
        aside.style.top === '150px');
  // The next write should land under the canonical key, not the legacy one.
  document.getElementById('sidebarFloatBtn')._fire('click');   // → docked
  document.getElementById('sidebarFloatBtn')._fire('click');   // → floating again
  check('canonical key written after first user flip',
        localStorage.getItem('atlas.sidebarFloating.mode') === 'floating');
  // Legacy key is NOT touched — never overwritten, never deleted; safe to
  // leave around for older code paths that haven't migrated yet.
  check('legacy mode key still present (read-only migration)',
        localStorage.getItem('pca_scrubber_v3.sidebarFloating.mode') === 'floating');
}

// ---------------------------------------------------------------------------
group('canonical LS key wins over legacy when both are present');
{
  _store.clear();
  // User has the canonical key set (later session) AND a stale legacy key.
  // The canonical value must win.
  localStorage.setItem('atlas.sidebarFloating.mode', 'docked');
  localStorage.setItem('pca_scrubber_v3.sidebarFloating.mode', 'floating');
  const { wrap } = buildPageDom();
  const mod = await freshShell();
  mod.installFloatingSidebar();
  check('canonical "docked" beats legacy "floating"',
        wrap.getAttribute('data-sidebar') !== 'floating');
}

// ---------------------------------------------------------------------------
console.log('\n=================');
console.log(`pass: ${pass}   fail: ${fail}`);
console.log('=================');
process.exit(fail === 0 ? 0 : 1);
