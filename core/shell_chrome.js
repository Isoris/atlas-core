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
  _wireModeBTally();
  _wireWorkflowsBadge(opts);
  _wireChromSummaryBadge(opts);
}

// SPEC_multichrom_load_orchestrator Slice 1 — visible counter of how many
// chroms have a cached summary in this session. Subscribes to
// `shared.chromSummaries.changed`; hides itself until at least one
// summary lands. Tooltip enumerates every chrom + its counts so the user
// can sanity-check the cache without opening devtools. Click opens a
// modal with a jump-to-chrom link per row so the chip doubles as a
// session-history navigator.
function _wireChromSummaryBadge(opts) {
  const badge = document.getElementById('chromSummaryBadge');
  if (!badge) return;
  const state = (opts && opts.atlasState) || null;
  if (!state || typeof state.subscribe !== 'function') return;

  const orderedEntries = () => {
    const all = state.shared && state.shared.chromSummaries;
    if (!all || typeof all !== 'object') return [];
    const entries = Object.entries(all);
    entries.sort(([a], [b]) => {
      const ma = a.match(/LG0*(\d+)$/);
      const mb = b.match(/LG0*(\d+)$/);
      if (ma && mb) return Number(ma[1]) - Number(mb[1]);
      return a.localeCompare(b);
    });
    return entries;
  };

  // The scope-picker chrom count gives the denominator so the chip can
  // show "12 / 28 warmed". Best-effort: when the picker hasn't rendered
  // yet (cold boot before navigate) this returns 0 and we fall back to
  // the bare "chroms · N" label.
  const readScopebarChromCount = () => {
    if (typeof document === 'undefined') return 0;
    const sel = document.querySelector(
      '#scopebar .scope-picker[data-slot="activeChrom"] select');
    if (!sel) return 0;
    return Array.from(sel.options).filter(o => o.value && o.value.length > 0).length;
  };

  const refresh = () => {
    const entries = orderedEntries();
    if (entries.length === 0) {
      badge.style.display = 'none';
      return;
    }
    const total = readScopebarChromCount();
    const prewarm = (typeof window !== 'undefined') ? window.__atlasChromPrewarm : null;
    const warming = prewarm && prewarm.isEnabled && prewarm.isEnabled()
                 && total > 0 && entries.length < total;
    badge.style.display = 'inline-block';
    badge.style.cursor = 'pointer';
    badge.textContent = total > 0
      ? `chroms · ${entries.length} / ${total}${warming ? ' ⟳' : ''}`
      : `chroms · ${entries.length}`;
    badge.title = 'Chrom-summary cache (SPEC_multichrom_load_orchestrator Slice 1)\n'
      + (warming ? `Background prewarm running — ${total - entries.length} chrom(s) remaining.\n` : '')
      + 'Click to list cached chroms and jump.\n'
      + entries.map(([chrom, s]) => {
          const w = (s && s.n_windows != null) ? s.n_windows : '?';
          const n = (s && s.n_samples != null) ? s.n_samples : '?';
          const c = (s && s.n_candidates != null) ? s.n_candidates : 0;
          return `${chrom} — ${w} windows · ${n} samples · ${c} candidates`;
        }).join('\n');
  };

  // Idempotent click handler (the badge keeps the same DOM node across
  // refresh calls; we only need to bind once).
  if (!badge.dataset.cscWired) {
    badge.dataset.cscWired = '1';
    badge.setAttribute('role', 'button');
    badge.setAttribute('tabindex', '0');
    badge.addEventListener('click', () => _openChromSummaryModal(state, orderedEntries));
    badge.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        _openChromSummaryModal(state, orderedEntries);
      }
    });
  }

  refresh();
  state.subscribe('shared.chromSummaries.changed', refresh);
}

function _openChromSummaryModal(state, orderedEntriesFn) {
  const entries = orderedEntriesFn();
  const activeChrom = (state.shared && state.shared.activeChrom) || null;
  const rows = entries.map(([chrom, s]) => {
    const w = (s && s.n_windows != null) ? s.n_windows : 0;
    const n = (s && s.n_samples != null) ? s.n_samples : 0;
    const c = (s && s.n_candidates != null) ? s.n_candidates : 0;
    const layers = (s && Array.isArray(s.layers_present)) ? s.layers_present : [];
    const layerChips = layers.slice(0, 6).map(l =>
      `<span style="background: var(--panel-3, #232a36); color: var(--ink-dim);
                    padding: 1px 5px; border-radius: 2px; font-size: 10px;
                    margin-right: 3px;">${_esc(l)}</span>`
    ).join('') + (layers.length > 6 ? `<span style="color: var(--ink-dimmer); font-size: 10px;">+${layers.length - 6}</span>` : '');
    const isActive = chrom === activeChrom;
    const jumpBtn = isActive
      ? '<span style="color: var(--ink-dimmer); font-size: 10px;">(active)</span>'
      : `<button type="button" data-jump-chrom="${_esc(chrom)}"
                 style="background: var(--panel-3, #232a36); border: 1px solid var(--rule);
                        color: var(--ink); padding: 2px 8px; border-radius: 2px;
                        font: 10px var(--mono, ui-monospace, monospace); cursor: pointer;">
                 jump →</button>`;
    return `
      <div style="display: grid; grid-template-columns: 0.9fr 0.6fr 0.6fr 0.6fr 2fr 0.6fr;
                  gap: 8px; padding: 6px 4px; border-bottom: 1px solid var(--rule);
                  align-items: center; ${isActive ? 'background: var(--panel-3, #232a36);' : ''}">
        <div style="font-family: var(--mono); color: var(--ink); font-weight: ${isActive ? '600' : '400'};">${_esc(chrom)}</div>
        <div class="dim" style="font-family: var(--mono); font-size: 11px;">${w.toLocaleString()} win</div>
        <div class="dim" style="font-family: var(--mono); font-size: 11px;">${n} samp</div>
        <div class="dim" style="font-family: var(--mono); font-size: 11px;">${c} cand</div>
        <div>${layerChips || '<span class="dim" style="font-size: 10px;">—</span>'}</div>
        <div style="text-align: right;">${jumpBtn}</div>
      </div>`;
  }).join('');

  const prewarm = (typeof window !== 'undefined') ? window.__atlasChromPrewarm : null;
  const prewarmEnabled = prewarm && prewarm.isEnabled && prewarm.isEnabled();
  const prewarmRow = prewarm
    ? `<div style="display: flex; align-items: center; gap: 10px;
                   padding: 8px 4px; margin-top: 4px;
                   border-top: 1px solid var(--rule);">
         <label style="display: inline-flex; align-items: center; gap: 6px;
                       cursor: pointer; font-family: var(--mono); font-size: 11px;">
           <input type="checkbox" id="atlasChromPrewarmToggle"
                  ${prewarmEnabled ? 'checked' : ''} />
           <span>Background prewarm of remaining chroms</span>
         </label>
         <span class="dim" style="font-size: 10.5px;">
           Uses <code>requestIdleCallback</code>; warms one chrom at a time,
           neighbors-first. Toggle persists across sessions.
         </span>
       </div>`
    : '';

  // Bulk-load: opens a multi-file picker OR accepts drag-drop;
  // loadChromJsons parses each and writes to the registry warm tier +
  // chromSummary. Visible iff the host registered `window.__atlasRegistry`
  // (it does — see index.html).
  const canBulkLoad = (typeof window !== 'undefined' && window.__atlasRegistry);
  const bulkRow = canBulkLoad
    ? `<div id="atlasChromBulkLoadZone"
            style="padding: 10px 12px; margin-top: 6px;
                   border: 1px dashed var(--rule); border-radius: 3px;
                   background: var(--panel-2);
                   transition: background 80ms ease, border-color 80ms ease;">
         <div style="display: flex; align-items: center; gap: 10px;">
           <button type="button" id="atlasChromBulkLoadBtn"
                   style="background: var(--panel-3, #232a36); border: 1px solid var(--rule);
                          color: var(--ink); padding: 3px 12px; border-radius: 2px;
                          font: 10.5px var(--mono, ui-monospace, monospace); cursor: pointer;">
             📂 Bulk-load chrom JSONs…
           </button>
           <input type="file" id="atlasChromBulkLoadInput"
                  accept=".json,application/json" multiple
                  style="display: none;" />
           <span class="dim" style="font-size: 10.5px;">
             …or drag &amp; drop N scrubber_main JSONs anywhere on this row.
             Populates the registry cache + chromSummary for each. No network.
           </span>
         </div>
         <div id="atlasChromBulkLoadStatus" class="dim"
              style="font-size: 10.5px; margin-top: 6px; min-height: 14px;"></div>
       </div>`
    : '';

  const body = entries.length === 0
    ? '<div class="dim">No chroms summarized yet. Visit a page that loads a chromosome to populate the cache, or bulk-load JSONs from disk below.</div>' + bulkRow + prewarmRow
    : `<div style="display: grid; grid-template-columns: 0.9fr 0.6fr 0.6fr 0.6fr 2fr 0.6fr;
                   gap: 8px; padding: 4px; color: var(--ink-dim);
                   font-size: 10px; text-transform: uppercase; letter-spacing: 0.05em;
                   border-bottom: 1px solid var(--rule);">
        <div>chrom</div><div>windows</div><div>samples</div><div>candidates</div><div>layers</div><div></div>
      </div>${rows}
      <div class="dim" style="margin-top: 10px; font-size: 10.5px;">
        Active row is highlighted. "jump" sets the chromosome selector — pages re-mount
        on the new chrom; cached layers reload instantly from the in-flight Promise
        dedup + warm-tier IDB cache.
      </div>${bulkRow}${prewarmRow}`;
  _openModal({ title: `Chrom-summary cache · ${entries.length} cached`, body });

  // Wire jump buttons after the modal mounts.
  const overlay = document.getElementById('atlasChromeModalOverlay');
  if (!overlay) return;
  overlay.querySelectorAll('[data-jump-chrom]').forEach(btn => {
    btn.addEventListener('click', () => {
      const target = btn.getAttribute('data-jump-chrom');
      if (!target) return;
      // Find the active atlas's chrom selector and dispatch a change so
      // the router runs its full _applyScopePick path (state setter +
      // page re-mount). Falls back to a direct setActiveChrom + re-nav
      // when no scope picker is in the DOM.
      const sel = document.querySelector(
        '#scopebar .scope-picker[data-slot="activeChrom"] select');
      if (sel) {
        sel.value = target;
        sel.dispatchEvent(new Event('change', { bubbles: true }));
      } else if (typeof state.setActiveChrom === 'function') {
        state.setActiveChrom(target);
      }
      // Close the modal so the user sees the new chrom rendering.
      overlay.style.display = 'none';
    });
  });

  // Background-prewarm toggle.
  const toggle = overlay.querySelector('#atlasChromPrewarmToggle');
  if (toggle && prewarm && typeof prewarm.setEnabled === 'function') {
    toggle.addEventListener('change', (e) => {
      prewarm.setEnabled(!!e.target.checked);
      // Re-emit the chromSummaries event so the shell-header chip
      // immediately repaints with/without the ⟳ progress glyph,
      // without waiting for the next chrom to warm.
      if (typeof state.emit === 'function') {
        state.emit('shared.chromSummaries.changed', {
          chrom: null, summary: null, source: 'prewarm_toggle',
        });
      }
    });
  }

  // Bulk-load chrom JSONs (Slice 2). The picker button + the drag-drop
  // zone both funnel through the same runBulkLoad(files) helper so the
  // progress / refresh path is consistent.
  const bulkZone  = overlay.querySelector('#atlasChromBulkLoadZone');
  const bulkBtn   = overlay.querySelector('#atlasChromBulkLoadBtn');
  const bulkInput = overlay.querySelector('#atlasChromBulkLoadInput');
  const bulkStat  = overlay.querySelector('#atlasChromBulkLoadStatus');
  if (bulkZone && bulkBtn && bulkInput && bulkStat) {
    const runBulkLoad = async (files) => {
      if (!files || files.length === 0) return;
      bulkBtn.disabled = true;
      const start = Date.now();
      bulkStat.textContent = `Loading 0 / ${files.length}…`;
      try {
        const { loadChromJsons } = await import('./chrom_bulk_loader.js');
        const result = await loadChromJsons({
          files,
          registry:   window.__atlasRegistry,
          atlasState: state,
          onProgress: (p) => {
            bulkStat.textContent =
              `${p.status === 'loaded' ? '✓' : '⚠'} ${p.name}` +
              (p.chrom ? ` → ${p.chrom}` : '') +
              (p.reason ? ` (${p.reason})` : '') +
              `   ·   ${p.loaded} / ${p.total} loaded`;
          },
        });
        const ms = Date.now() - start;
        const skipNote = result.skipped.length
          ? ` · ${result.skipped.length} skipped`
          : '';
        bulkStat.textContent =
          `✓ ${result.loaded} / ${result.total} loaded in ${ms}ms${skipNote}. ` +
          `Modal refreshing…`;
        // Re-open the modal to show the new rows (preserves the toggle
        // state because it reads through prewarm.isEnabled()).
        setTimeout(() => _openChromSummaryModal(state, orderedEntriesFn), 600);
      } catch (err) {
        bulkStat.textContent = `bulk-load failed: ${err.message || err}`;
      } finally {
        bulkBtn.disabled = false;
        bulkInput.value = ''; // allow re-selecting the same files
      }
    };

    bulkBtn.addEventListener('click', () => bulkInput.click());
    bulkInput.addEventListener('change', (e) => runBulkLoad(e.target.files));

    // Drag-drop. Highlight the zone while a drag is in progress; capture
    // dropped files (or — when DataTransferItem with webkitGetAsEntry is
    // available — walk a dropped folder for its JSONs).
    const setActive = (active) => {
      bulkZone.style.borderColor = active ? 'var(--accent, #f5a524)' : 'var(--rule)';
      bulkZone.style.background  = active ? 'var(--panel-3, #232a36)' : 'var(--panel-2)';
    };
    bulkZone.addEventListener('dragenter', (e) => { e.preventDefault(); setActive(true);  });
    bulkZone.addEventListener('dragover',  (e) => { e.preventDefault(); e.dataTransfer.dropEffect = 'copy'; });
    bulkZone.addEventListener('dragleave', (e) => {
      // Only un-highlight when the drag truly leaves the zone (dragleave
      // fires on every child element too — we ignore the inner ones).
      if (e.target === bulkZone) setActive(false);
    });
    bulkZone.addEventListener('drop', async (e) => {
      e.preventDefault();
      setActive(false);
      const dt = e.dataTransfer;
      if (!dt) return;
      const collected = await _collectDroppedFiles(dt);
      runBulkLoad(collected);
    });
  }
}

// Walk a DataTransfer for File objects, recursing into dropped folders
// when the browser supports webkitGetAsEntry. Skips non-JSON entries
// at the walk level so the user can drag an entire workspace folder
// without selecting individual files. Falls back to dt.files when the
// folder API isn't available (older browsers, Safari < 11.1).
async function _collectDroppedFiles(dt) {
  const items = dt.items;
  const out = [];
  if (items && items.length > 0 && typeof items[0].webkitGetAsEntry === 'function') {
    const entries = [];
    for (let i = 0; i < items.length; i++) {
      const entry = items[i].webkitGetAsEntry && items[i].webkitGetAsEntry();
      if (entry) entries.push(entry);
    }
    for (const entry of entries) await _walkEntry(entry, out);
    if (out.length > 0) return out;
  }
  return Array.from(dt.files || []);
}

async function _walkEntry(entry, out) {
  if (!entry) return;
  if (entry.isFile) {
    if (!/\.json$/i.test(entry.name)) return;
    await new Promise((resolve) => {
      entry.file(
        (file) => { out.push(file); resolve(); },
        () => resolve()
      );
    });
    return;
  }
  if (entry.isDirectory) {
    const reader = entry.createReader();
    // readEntries returns at most 100 per call; loop until empty.
    const readBatch = () => new Promise((resolve) => {
      reader.readEntries((batch) => resolve(batch || []), () => resolve([]));
    });
    while (true) {
      const batch = await readBatch();
      if (batch.length === 0) break;
      for (const sub of batch) await _walkEntry(sub, out);
    }
  }
}

// Mount the workflows-status chip into #workflowsBadgeHost. Requires
// `opts.registry` (for getWorkflows) and `opts.manifests` (for the
// per-atlas iteration). Skips silently when either is absent.
// SPEC_workflows_v1 §5.
function _wireWorkflowsBadge(opts) {
  const host = document.getElementById('workflowsBadgeHost');
  if (!host) return;
  if (!opts || !opts.registry || !opts.manifests) {
    // Dev hint: missing inputs means the boot path forgot to pass them.
    // The badge is non-essential; warn-and-skip rather than throw.
    console.debug('[shell_chrome] workflows badge skipped (registry/manifests not passed to attachShellChrome).');
    return;
  }
  import('./workflow_status_badge.js')
    .then((m) => {
      try { m.mountWorkflowsBadge(host, { registry: opts.registry, manifests: opts.manifests }); }
      catch (e) { console.warn('[shell_chrome] mountWorkflowsBadge threw:', e); }
    })
    .catch((e) => console.warn('[shell_chrome] workflow_status_badge import failed:', e));
}

// Mount the workspace-wide Mode-B tally chip into #modeBTallyHost. The
// chip subscribes to the 'mode_b_badge_render' CustomEvent every per-page
// badge dispatches and shows a single-line count ('● 8  ⚠ 1  ○ 5')
// across all loaded atlases. Hidden until at least one badge reports.
function _wireModeBTally() {
  const host = document.getElementById('modeBTallyHost');
  if (!host) return;
  // Lazy import keeps the shell_chrome bundle thin if the tally is ever
  // disabled — dynamic import returns immediately, mount on resolve.
  import('./mode_b_tally.js')
    .then((m) => { try { m.mountModeBTally(host); } catch (_) {} })
    .catch(() => {});
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
      // 2026-05-20: mirror the page button's new label/title back onto
      // the header button so its text reflects the new state instead of
      // staying stuck on the initial "📐 compact". Defer one frame so the
      // page handler has run + mutated its own button's text before we
      // copy it. Quentin's report: clicking the header "compact" button
      // changes the layout but the button label never updates.
      requestAnimationFrame(() => {
        try {
          if (target.textContent && target.textContent !== btn.textContent) {
            btn.textContent = target.textContent;
          }
          if (target.title && target.title !== btn.title) {
            btn.title = target.title;
          }
          if (target.dataset && target.dataset.mode && btn.dataset) {
            btn.dataset.mode = target.dataset.mode;
          }
        } catch (_) { /* never fail the click on a label-mirror */ }
      });
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
  // 2026-05-20: reset + repopulate the schema badge on every atlas
  // transition. Previously only the inversion atlas's local_pca_dosage
  // wrote `window.__atlasSchemaLayers` (on chrom load), and that global
  // never got cleared — so navigating to e.g. the relatedness atlas
  // showed the inversion atlas's precomp fields as if they belonged to
  // relatedness. The fix has two layers:
  //
  //   1. On every page_mount where atlas_id changes: blow away the
  //      global + badge state.
  //   2. Then read `window.__atlasRegistry.getAtlasLayerNames(atlas_id)`
  //      (set in index.html) to repopulate with the new atlas's
  //      declared layers. Pages can still overwrite later with richer
  //      detail (e.g. inversion's local_pca_dosage writes "only the
  //      layers actually present in this chrom's precomp"); the
  //      registry baseline is just so the badge says SOMETHING even
  //      when no page has run its loader yet.
  let _lastAtlasId = null;
  document.addEventListener('shell.page_mount', (e) => {
    const d = (e && e.detail) || {};
    if (!d.atlas_id || d.atlas_id === _lastAtlasId) return;
    _lastAtlasId = d.atlas_id;
    window.__atlasSchemaLayers = null;
    badge.textContent = '';
    badge.style.display = 'none';
    badge.className = '';
    badge.title = '';
    // Repopulate from the registry, if it's exposed and has this atlas.
    const reg = window.__atlasRegistry;
    if (!reg || typeof reg.getAtlasLayers !== 'function') return;
    const layers = reg.getAtlasLayers(d.atlas_id) || {};
    const names = Object.keys(layers).sort();
    if (names.length === 0) return;
    window.__atlasSchemaLayers = names.map(name => {
      const entry = layers[name] || {};
      return {
        name,
        present: true,   // registered, not necessarily loaded; pages refine
        description: entry._doc || entry._status || '',
      };
    });
    badge.textContent = `schema · ${names.length} layer${names.length === 1 ? '' : 's'}`;
    badge.title = `Atlas: ${d.atlas_id}\nLayers (registered): ${names.join(', ')}`;
    badge.style.display = 'inline-block';
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
  // 2026-05-20: re-count after every page mount. The router fires a
  // `shell.page_mount` CustomEvent on `document` (see atlas_router.js
  // navigate(): `state.emit('shell.page_mount', ...)` plus a DOM-level
  // mirror below). Without this listener the badge stayed stuck on
  // "JS · 0 scripts" until the user clicked it — Quentin reported
  // "JS buttons still shows 0 scripts loaded (sometimes but not always)".
  document.addEventListener('shell.page_mount', () => {
    // rAF so the page's import() has resolved + the registry push has
    // landed before we recount. Re-count on a second rAF too for the
    // rare case where the page module pushes additional entries from
    // its mount() body (defensive belt-and-suspenders).
    requestAnimationFrame(() => {
      refresh();
      requestAnimationFrame(refresh);
    });
  });
  // Re-count on each click (modules load lazily after page mounts).
  badge.addEventListener('click', () => {
    refresh();
    const tags = _collectScriptTags();
    const allModules = _collectRegisteredModules();
    // 2026-05-23: window.__atlasJsRegistry is a process-lifetime global
    // that accumulates entries from every atlas you've ever visited in
    // this tab. Filtering to the active atlas matches what the user
    // expects when they click the badge — "what's running for THIS
    // atlas right now". The full cross-atlas list is still available
    // under the "all atlases" tab below. Active atlas is inferred from
    // the hash (#/<atlas_id>/<page_id>); falls back to "all" when there
    // is no hash. Modules are bucketed by name/path prefix matching the
    // atlas id (page modules push `relatedness/karyotypes` etc.).
    const activeAtlas = _activeAtlasFromHash();
    const scopedModules = activeAtlas
      ? allModules.filter(m => _moduleBelongsTo(m, activeAtlas))
      : allModules;
    _openModal({
      title: activeAtlas
        ? `JavaScript modules · ${activeAtlas}`
        : 'JavaScript modules',
      body: _jsScriptsModalBody(tags, scopedModules, allModules, activeAtlas),
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

function _activeAtlasFromHash() {
  const h = (window.location.hash || '').replace(/^#\/?/, '');
  if (!h) return null;
  const aid = h.split('/')[0];
  return aid || null;
}

function _moduleBelongsTo(mod, atlasId) {
  if (!mod || !atlasId) return false;
  const name = String(mod.name || '');
  const path = String(mod.path || '');
  // page modules typically push name="<atlas_id>/<page_id>" and
  // path="atlases/<atlas_id>/pages/.../<page>.js". Either side is enough.
  return name.startsWith(`${atlasId}/`) ||
         path.startsWith(`atlases/${atlasId}/`) ||
         path.includes(`/atlases/${atlasId}/`);
}

function _jsScriptsModalBody(tags, modules, allModules, activeAtlas) {
  const tagRows = tags.length === 0
    ? `<div class="dim">No <code>&lt;script src&gt;</code> tags in document.</div>`
    : tags.map(t => `
        <div style="display: grid; grid-template-columns: 24px 1fr 1fr; gap: 8px; padding: 4px 0; border-bottom: 1px solid var(--rule);">
          <div style="color: var(--good);">✅</div>
          <div style="font-family: var(--mono); color: var(--ink);">${_esc(t.src)}</div>
          <div class="dim" style="font-size: 11px;">${_esc(t.type)}</div>
        </div>`).join('');

  const moduleRows = modules.length === 0
    ? `<div class="dim">No ES modules registered themselves on <code>window.__atlasJsRegistry</code>${activeAtlas ? ` for atlas '${_esc(activeAtlas)}' yet` : ''}.</div>`
    : modules.map(m => `
        <div style="display: grid; grid-template-columns: 24px 1fr 1fr; gap: 8px; padding: 4px 0; border-bottom: 1px solid var(--rule);">
          <div style="color: var(--good);">✅</div>
          <div style="font-family: var(--mono); color: var(--ink);">${_esc(m.name || m.path || '')}</div>
          <div class="dim" style="font-size: 11px;">${_esc(m.path || m.kind || '')}</div>
        </div>`).join('');

  const scopeBanner = activeAtlas
    ? `<div style="font-size: 11px; color: var(--ink-dim); margin-bottom: 10px;">Showing modules for <b>${_esc(activeAtlas)}</b> only — ${modules.length} of ${(allModules || modules).length} loaded this session.</div>`
    : '';

  return `
    ${scopeBanner}
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
