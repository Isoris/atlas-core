// core/shell_chrome.js
// =====================================================================
// Shell header chrome: theme toggle + folder-button bridging.
//
// The header lives in atlas-core/index.html (legacy-style port). Most of
// its visual is pure CSS (base.css), but a few behaviours need JS:
//
//   1. Theme toggle      — cycles html[data-theme] dark → light → academic,
//                          persisted to localStorage.
//   2. Folder buttons    — the session/mode/data dropdowns hold buttons
//                          like 💾 save, 📂 load, 📐 fixed, 🏗 candidate mode.
//                          Per-page modules wire the actual handlers
//                          (page1 owns #candidateModeBtn etc.). The shell
//                          relays clicks on `[data-cmd]` buttons by
//                          dispatching a CustomEvent('shell.chrome.cmd')
//                          on document, which page modules can listen for.
//
// Pages don't need to bind to specific button IDs — they listen for the
// shell.chrome.cmd event with the relevant `cmd` string and do their thing.
// =====================================================================

const THEMES = ['dark', 'light', 'academic'];
const THEME_LS_KEY = 'atlas.theme';
const THEME_LABEL = { dark: '☀ light', light: '📓 academic', academic: '🌙 dark' };

export function attachShellChrome(opts = {}) {
  _wireThemeToggle();
  _wireFolderButtons();
  _wireGlobalSettingsBtn();
  _wireServerPing(opts.serverUrl || window.ATLAS_SERVER_URL || 'http://127.0.0.1:8000');
  _wireSchemaBadge();
  _wireJsScriptsBadge();
}

// Forward header gear clicks to the active page's sidebar.
//
// Sidebar collapse semantics live in the active page (e.g. for inversion
// page1, sidebar.js wires #sidebarToggleBtn against `.wrap[data-sidebar]`
// and redraws canvases on transition). We click the page-owned toggle so
// those handlers fire. As a robust fallback — for atlases that haven't
// wired a toggle button yet, or for the brief window before page-mount —
// we also flip `.wrap[data-sidebar]` directly so the CSS responds even
// when no JS handler is listening.
function _wireGlobalSettingsBtn() {
  const btn = document.getElementById('globalSettingsBtn');
  if (!btn) return;
  btn.addEventListener('click', () => {
    const pageToggle = document.getElementById('sidebarToggleBtn');
    if (pageToggle && pageToggle !== btn) {
      // .click() is more reliable than dispatchEvent(new MouseEvent('click'))
      // for triggering programmatically-added handlers — Safari quirks.
      pageToggle.click();
      return;
    }
    // Fallback: no page-owned toggle exists. Flip .wrap[data-sidebar]
    // directly so the inversion.css grid-template-columns rule still
    // collapses the aside. Other atlases use the same convention.
    const wrap = document.querySelector('#app-root .wrap, main .wrap, .wrap');
    if (wrap) {
      const collapsed = wrap.getAttribute('data-sidebar') === 'collapsed';
      if (collapsed) wrap.removeAttribute('data-sidebar');
      else           wrap.setAttribute('data-sidebar', 'collapsed');
      return;
    }
    // Last-ditch: toggle a `.collapsed` class on the first <aside>.
    const aside = document.querySelector('#app-root aside, main aside');
    if (aside) aside.classList.toggle('collapsed');
  });
}

function _wireThemeToggle() {
  const btn = document.getElementById('themeToggleBtn');
  if (!btn) return;

  // Restore persisted theme on boot. Default to dark.
  const stored = (() => { try { return localStorage.getItem(THEME_LS_KEY); } catch (_) { return null; } })();
  const initial = THEMES.includes(stored) ? stored : 'dark';
  _applyTheme(initial);

  btn.addEventListener('click', () => {
    const cur = document.documentElement.dataset.theme || 'dark';
    const i = THEMES.indexOf(cur);
    const next = THEMES[(i + 1) % THEMES.length];
    _applyTheme(next);
    try { localStorage.setItem(THEME_LS_KEY, next); } catch (_) {}
  });
}

function _applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  const btn = document.getElementById('themeToggleBtn');
  if (btn) btn.textContent = THEME_LABEL[theme] || '☀ light';
}

// Maps shell folder-button commands to the page-element IDs that actually
// implement the handler. The shell delegates by forwarding a click on the
// matching page button (when it exists). Pages keep their own button IDs;
// the shell just provides a consistent way to fire them from the header.
const CMD_TO_PAGE_ID = {
  'save-session':    'saveSessionBtn',
  'load-session':    'loadSessionBtn',
  'layout-mode':     'layoutModeBtn',
  'reset-layout':    'resetLayoutBtn',
  'candidate-mode':  'candidateModeBtn',
  'auto-fill':       'atlasToolsAutofill',
  'ig-labels':       'atlasToolsLabelsToggle',
  'export-data':     'atlasToolsExport',
  'open-matrix':     'atlasToolsMatrix',
  'active-samples':  'activeSamplesBadge',
};

function _wireFolderButtons() {
  // Delegated listener: forward each header [data-cmd] click to the
  // matching page-owned button (so existing legacy handlers fire), AND
  // also dispatch a CustomEvent so pages that didn't render a button
  // (or want to react globally) can still respond.
  //
  // Sources: buttons in folder panels AND direct header buttons
  // (`.header-direct-btn`) like compact / reset layout.
  document.addEventListener('click', (ev) => {
    const btn = ev.target.closest(
      'header .header-folder-panel [data-cmd], header .header-direct-btn[data-cmd]'
    );
    if (!btn) return;
    const cmd = btn.dataset.cmd;
    const targetId = CMD_TO_PAGE_ID[cmd];
    const target = targetId && document.getElementById(targetId);
    if (target && target !== btn) {
      // Synthesize a click on the page-owned button. Use dispatchEvent
      // instead of .click() so any framework-bound listeners still fire.
      target.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
    }
    document.dispatchEvent(new CustomEvent('shell.chrome.cmd', {
      detail: { cmd, sourceButton: btn },
    }));
  });
}

// =====================================================================
// Server status probe — pings the atlas server's /health endpoint
// every 15s and reflects the result on the #atlasServerStandaloneBtn
// indicator (green dot + "up", red "down", grey "probing"). Click opens
// a small popup with the current status + the launcher command.
// =====================================================================
const SERVER_PROBE_INTERVAL_MS = 15000;
const SERVER_PROBE_TIMEOUT_MS  = 3500;

function _wireServerPing(baseUrl) {
  const btn   = document.getElementById('atlasServerStandaloneBtn');
  if (!btn) return;
  const label = document.getElementById('atlasServerStandaloneLabel');

  let lastStatus = 'probing';
  const setStatus = (s) => {
    lastStatus = s;
    btn.dataset.status = s;  // up / down / probing — CSS reads this for dot color
    if (label) label.textContent = s === 'up' ? 'server' : s === 'down' ? 'server (down)' : 'server…';
  };

  const probe = async () => {
    setStatus('probing');
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), SERVER_PROBE_TIMEOUT_MS);
    try {
      const r = await fetch(`${baseUrl.replace(/\/$/, '')}/health`, {
        method: 'GET', signal: ctrl.signal, cache: 'no-store',
      });
      setStatus(r.ok ? 'up' : 'down');
    } catch (_) {
      setStatus('down');
    } finally {
      clearTimeout(t);
    }
  };

  probe();
  setInterval(probe, SERVER_PROBE_INTERVAL_MS);

  btn.addEventListener('click', () => {
    _openModal({
      title: 'Atlas server',
      body: _serverStatusBody(baseUrl, lastStatus),
    });
  });
}

function _serverStatusBody(baseUrl, status) {
  const statusLabel = status === 'up'   ? '<span style="color: var(--good);">● up</span>'
                    : status === 'down' ? '<span style="color: var(--bad);">● down</span>'
                    :                     '<span style="color: var(--ink-dim);">◌ probing…</span>';
  const startCmd = './run_atlas.sh   # or: python3 run_atlas.py';
  return `
    <div style="margin-bottom: 14px;">
      Status: ${statusLabel}
      <div class="dim" style="margin-top: 4px;">URL: <code>${_esc(baseUrl)}</code></div>
    </div>
    <div style="font-size: 10px; color: var(--ink-dimmer); text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 4px;">Start the server</div>
    <pre style="margin: 0 0 12px; padding: 8px 12px; background: var(--panel); border: 1px solid var(--rule); border-radius: 3px; color: var(--ink); overflow-x: auto;">${_esc(startCmd)}</pre>
    <div class="dim" style="font-size: 11px;">
      The atlas works in view-only mode without a server. Start one to enable saving sessions
      and live popstats / LD / dosage computes.
    </div>
  `;
}

// =====================================================================
// Schema badge — clicking opens a registry modal that lists the layers
// recognized by the active page (read from window.__atlasSchemaLayers if
// the page exposes it; otherwise empty).
// =====================================================================
function _wireSchemaBadge() {
  const badge = document.getElementById('schemaBadge');
  if (!badge) return;
  badge.style.cursor = 'pointer';
  badge.addEventListener('click', () => {
    const layers = (window.__atlasSchemaLayers && Array.isArray(window.__atlasSchemaLayers))
      ? window.__atlasSchemaLayers : null;
    _openModal({
      title: 'Schema · loaded layers',
      body: _schemaModalBody(layers),
    });
  });
}

function _schemaModalBody(layers) {
  if (!layers || layers.length === 0) {
    return `<div class="dim">No JSON loaded yet. Once a chromosome JSON is loaded its detected layers will be listed here.</div>`;
  }
  const rows = layers.map(l => {
    const tick = l.present ? '✅' : '⚪';
    const color = l.present ? 'var(--good)' : 'var(--ink-dimmer)';
    return `
      <div style="display: grid; grid-template-columns: 24px 1fr 2fr; gap: 8px; padding: 4px 0; border-bottom: 1px solid var(--rule);">
        <div style="color: ${color};">${tick}</div>
        <div style="font-family: var(--mono); color: var(--ink);">${_esc(l.name)}</div>
        <div class="dim" style="font-size: 11px;">${_esc(l.description || '')}</div>
      </div>`;
  }).join('');
  return `<div style="font-size: 12px;">${rows}</div>`;
}

// =====================================================================
// JS scripts badge — clicking opens a modal listing every <script src>
// in the document plus every ES module path that registered through
// window.__atlasJsRegistry (page modules can opt in by pushing to it).
// =====================================================================
function _wireJsScriptsBadge() {
  const badge = document.getElementById('jsScriptsBadge');
  if (!badge) return;
  badge.style.cursor = 'pointer';
  const refresh = () => {
    const tags = _collectScriptTags();
    const modules = _collectRegisteredModules();
    const total = tags.length + modules.length;
    badge.textContent = `JS · ${total} script${total === 1 ? '' : 's'}`;
    badge.classList.toggle('v2', total > 0);
  };
  refresh();
  // Re-count on each click (modules load lazily after page mounts).
  badge.addEventListener('click', () => {
    refresh();
    const tags = _collectScriptTags();
    const modules = _collectRegisteredModules();
    _openModal({
      title: 'JavaScript modules',
      body: _jsScriptsModalBody(tags, modules),
    });
  });
}

function _collectScriptTags() {
  return Array.from(document.querySelectorAll('script[src]'))
    .map(s => ({
      src: s.getAttribute('src') || '',
      type: s.getAttribute('type') || 'script',
    }))
    .filter(s => s.src);
}

function _collectRegisteredModules() {
  const reg = window.__atlasJsRegistry;
  if (!Array.isArray(reg)) return [];
  return reg.slice();
}

function _jsScriptsModalBody(tags, modules) {
  const tagRows = tags.length === 0
    ? `<div class="dim">No <code>&lt;script src&gt;</code> tags in document.</div>`
    : tags.map(t => `
        <div style="display: grid; grid-template-columns: 24px 1fr 1fr; gap: 8px; padding: 4px 0; border-bottom: 1px solid var(--rule);">
          <div style="color: var(--good);">✅</div>
          <div style="font-family: var(--mono); color: var(--ink);">${_esc(t.src)}</div>
          <div class="dim" style="font-size: 11px;">${_esc(t.type)}</div>
        </div>`).join('');

  const moduleRows = modules.length === 0
    ? `<div class="dim">No ES modules registered themselves on <code>window.__atlasJsRegistry</code>.</div>`
    : modules.map(m => `
        <div style="display: grid; grid-template-columns: 24px 1fr 1fr; gap: 8px; padding: 4px 0; border-bottom: 1px solid var(--rule);">
          <div style="color: var(--good);">✅</div>
          <div style="font-family: var(--mono); color: var(--ink);">${_esc(m.name || m.path || '')}</div>
          <div class="dim" style="font-size: 11px;">${_esc(m.path || m.kind || '')}</div>
        </div>`).join('');

  return `
    <div style="margin-bottom: 14px;">
      <div style="font-size: 10px; color: var(--ink-dimmer); text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 6px;">
        &lt;script src&gt; tags (${tags.length})
      </div>
      ${tagRows}
    </div>
    <div>
      <div style="font-size: 10px; color: var(--ink-dimmer); text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 6px;">
        Registered ES modules (${modules.length})
      </div>
      ${moduleRows}
    </div>
  `;
}

// =====================================================================
// Lightweight modal — shared by server / schema / JS popups. Single
// instance attached to <body>; replaces content each open. Closes on
// ✕, Esc, or click-outside.
// =====================================================================
function _openModal({ title, body }) {
  let overlay = document.getElementById('atlasChromeModalOverlay');
  if (!overlay) {
    overlay = document.createElement('div');
    overlay.id = 'atlasChromeModalOverlay';
    overlay.style.cssText = `
      position: fixed; inset: 0; z-index: 9000;
      background: rgba(0, 0, 0, 0.45);
      display: none; align-items: flex-start; justify-content: center;
      padding-top: 60px;
    `;
    document.body.appendChild(overlay);
  }
  overlay.innerHTML = `
    <div role="dialog" aria-labelledby="atlasChromeModalTitle"
         style="background: var(--panel-2); color: var(--ink);
                border: 1px solid var(--rule); border-radius: 4px;
                box-shadow: 0 8px 32px rgba(0,0,0,0.5);
                max-width: 720px; width: 92%; padding: 16px 20px;
                font-family: var(--serif); font-size: 12px; line-height: 1.5;
                max-height: 80vh; overflow-y: auto;">
      <div style="display: flex; align-items: baseline; justify-content: space-between; margin: 0 0 12px;">
        <div id="atlasChromeModalTitle"
             style="font-size: 14px; font-weight: 600; color: var(--ink); font-family: var(--mono);">
          ${_esc(title)}
        </div>
        <button id="atlasChromeModalClose"
                style="background: transparent; border: 1px solid var(--rule);
                       color: var(--ink-dim); border-radius: 3px;
                       padding: 3px 10px; font-family: var(--mono); font-size: 11px;
                       cursor: pointer;"
                title="Close (Esc)">✕ close</button>
      </div>
      <div>${body}</div>
    </div>
  `;
  overlay.style.display = 'flex';

  const close = () => {
    overlay.style.display = 'none';
    document.removeEventListener('keydown', onKey);
    overlay.removeEventListener('click', onOverlay);
  };
  const onKey = (e) => { if (e.key === 'Escape') close(); };
  const onOverlay = (e) => { if (e.target === overlay) close(); };
  document.addEventListener('keydown', onKey);
  overlay.addEventListener('click', onOverlay);
  overlay.querySelector('#atlasChromeModalClose').addEventListener('click', close);
}

function _esc(s) {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}
