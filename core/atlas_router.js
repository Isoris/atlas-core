// core/atlas_router.js
// =====================================================================
// Page router for the Atlas shell.
//
// Each atlas declares pages in manifest.json with { id, fragment, module }.
// The router:
//   - parses URL hash → (atlas_id, page_id)
//   - fetches the fragment HTML, injects into #app-root
//   - imports the module, calls module.mount(root, atlasState, registry)
//   - on next navigation, calls previous module.unmount(root) if defined
//
// Also responsible for building the topbar from discovered manifests.
//
// =====================================================================

// ---------------------------------------------------------------------
// IMPLEMENTATION_NOTE for next chat:
//   ~250 LOC. The interesting bits:
//   1. URL hash format: #/inversion/page1 or just #/inversion (default page)
//      or #/  (atlas picker). Backward compat for #/page1 only when
//      exactly one atlas is loaded.
//   2. Module import: dynamic import() with cache busting in dev mode.
//      In prod, modules are content-hashed and cached forever.
//   3. mount() contract:
//        async mount(root, atlasState, registry)
//        async unmount(root)
//      mount may be async (await preloads). unmount may also be async
//      (e.g. to flush pending writes).
//   4. Topbar: when one atlas is loaded, show stages + pages flat.
//      When multiple are loaded, show atlas selector + per-atlas stages.
// ---------------------------------------------------------------------

export class AtlasRouter {

  constructor({ atlasState, registry, manifests }) {
    this.state = atlasState;
    this.registry = registry;
    this.manifests = manifests;       // Map<atlas_id, manifest>
    this._currentModule = null;
    this._currentRoot = null;
  }

  attach() {
    window.addEventListener('hashchange', () => this._navigateFromHash());
    this._renderScopebar();
    this._navigateFromHash();
    this._renderTopbar();
  }

  async navigate(atlas_id, page_id) {
    const manifest = this.manifests.get(atlas_id);
    if (!manifest) throw new Error(`Unknown atlas: ${atlas_id}`);

    const page = manifest.pages.find(p => p.id === page_id);
    if (!page) throw new Error(`Unknown page: ${atlas_id}/${page_id}`);

    // Unmount previous
    if (this._currentModule?.unmount) {
      try { await this._currentModule.unmount(this._currentRoot); }
      catch (e) { console.error('unmount threw:', e); }
    }

    // Load per-page stylesheet if declared. Loaded BEFORE the fragment is
    // injected so the page renders styled, not flashed-unstyled. Stylesheets
    // are kept in <head> across navigations (cheap) and re-used.
    if (page.stylesheet) {
      this._ensureStylesheet(page.stylesheet, atlas_id);
    }

    // Fetch fragment + import module
    const fragmentHtml = await fetch(page.fragment).then(r => r.text());
    const root = document.getElementById('app-root');
    root.innerHTML = fragmentHtml;

    const module = await import('/' + page.module);
    if (typeof module.mount !== 'function') {
      throw new Error(`Page ${atlas_id}/${page_id}: module has no mount() export`);
    }

    // Update state, fire page_mount event for prewarm scheduler
    this.state.shared.currentPage = { atlas_id, page_id };
    this.state.emit('shell.page_mount', { atlas_id, page_id });

    // Mount
    await module.mount(root, this.state, this.registry);

    this._currentModule = module;
    this._currentRoot = root;
  }

  _ensureStylesheet(href, atlas_id) {
    if (document.querySelector(`link[rel="stylesheet"][href="${href}"]`)) return;
    const link = document.createElement('link');
    link.rel = 'stylesheet';
    link.href = href;
    link.dataset.atlas = atlas_id;
    link.dataset.scope = 'page';
    document.head.appendChild(link);
  }

  _navigateFromHash() {
    const hash = window.location.hash.slice(1) || '/';
    // Format: #/atlas_id/page_id, or #/atlas_id (= default page),
    // or #/ (= first atlas, first page).
    const parts = hash.split('/').filter(p => p.length > 0);

    let atlas_id, page_id;
    if (parts.length === 0) {
      // Default: first atlas, first page
      const firstAtlas = [...this.manifests.keys()][0];
      if (!firstAtlas) return;
      atlas_id = firstAtlas;
      page_id = this.manifests.get(firstAtlas).pages[0]?.id;
    } else if (parts.length === 1) {
      // Backward-compat: if exactly one atlas loaded and someone hashed
      // #/page1, treat parts[0] as page id of that atlas.
      if (this.manifests.size === 1 && !this.manifests.has(parts[0])) {
        atlas_id = [...this.manifests.keys()][0];
        page_id = parts[0];
      } else {
        atlas_id = parts[0];
        page_id = this.manifests.get(atlas_id)?.pages[0]?.id;
      }
    } else {
      atlas_id = parts[0];
      page_id = parts[1];
    }

    if (!atlas_id || !page_id) return;
    this.navigate(atlas_id, page_id).catch(err => {
      console.error(`Router navigate(${atlas_id}/${page_id}) failed:`, err);
    });
    this._renderTopbar(atlas_id, page_id);
  }

  /**
   * Render the scopebar (sticky strip below the topbar). Each atlas may
   * declare a `scope_pickers` array in its manifest:
   *
   *   "scope_pickers": [
   *     { "slot": "activeChrom", "label": "chromosome",
   *       "options": ["LG28", ...], "shared": true }
   *   ]
   *
   * `slot` is the AtlasState slot to set on change. If `shared: true`
   * (default), the slot lives on `state.shared.<slot>` and emits
   * `shared.<slot>.changed`; otherwise it lives on `state.<atlas_id>.<slot>`
   * and emits `<atlas_id>.<slot>.changed`. For shared chrom/candidate
   * the convenience setters (setActiveChrom / setActiveCandidate) are used
   * so the prewarm scheduler picks up the event under its existing names.
   *
   * Pickers are rendered in manifest order, grouped by atlas. If no atlas
   * declares any pickers, the scopebar stays empty (CSS hides it).
   */
  _renderScopebar() {
    const bar = document.getElementById('scopebar');
    if (!bar) return;
    bar.innerHTML = '';

    for (const [atlas_id, manifest] of this.manifests) {
      const pickers = Array.isArray(manifest.scope_pickers) ? manifest.scope_pickers : [];
      for (const picker of pickers) {
        if (!picker || !picker.slot) continue;
        const opts = Array.isArray(picker.options) ? picker.options : [];

        const wrap = document.createElement('div');
        wrap.className = 'scope-picker';
        wrap.dataset.atlas = atlas_id;
        wrap.dataset.slot = picker.slot;

        const label = document.createElement('span');
        label.className = 'scope-picker-label';
        label.textContent = (picker.label || picker.slot) + ':';
        wrap.appendChild(label);

        const sel = document.createElement('select');
        // Add a "— none —" placeholder unless the picker is required.
        if (!picker.required) {
          const placeholder = document.createElement('option');
          placeholder.value = '';
          placeholder.textContent = '— none —';
          sel.appendChild(placeholder);
        }
        for (const opt of opts) {
          const o = document.createElement('option');
          if (typeof opt === 'string') {
            o.value = opt; o.textContent = opt;
          } else if (opt && typeof opt === 'object') {
            o.value = opt.value; o.textContent = opt.label || opt.value;
          }
          sel.appendChild(o);
        }

        // Pre-select the current state value if any.
        const isShared = picker.shared !== false;
        const current = isShared
          ? this.state.shared[picker.slot]
          : (this.state[atlas_id] || {})[picker.slot];
        if (current != null) sel.value = String(current);

        sel.addEventListener('change', (ev) => {
          const value = ev.target.value || null;
          this._applyScopePick(atlas_id, picker.slot, value, isShared);
        });

        wrap.appendChild(sel);
        bar.appendChild(wrap);
      }
    }
  }

  /**
   * Apply a scopebar selection to AtlasState, using convenience setters
   * for the well-known shared slots so prewarm events fire under their
   * canonical names.
   */
  _applyScopePick(atlas_id, slot, value, isShared) {
    if (isShared) {
      if (slot === 'activeChrom' && typeof this.state.setActiveChrom === 'function') {
        this.state.setActiveChrom(value);
      } else if (slot === 'activeCandidate' && typeof this.state.setActiveCandidate === 'function') {
        // Candidate is usually an object; the picker passes an id string.
        // Pages decide how to resolve id→object; we just stash the id.
        this.state.setActiveCandidate(value ? { id: value } : null);
      } else {
        const old = this.state.shared[slot];
        this.state.shared[slot] = value;
        this.state.emit(`shared.${slot}.changed`, { newValue: value, oldValue: old });
      }
    } else {
      const bucket = this.state[atlas_id] || (this.state[atlas_id] = {});
      const old = bucket[slot];
      bucket[slot] = value;
      this.state.emit(`${atlas_id}.${slot}.changed`, { newValue: value, oldValue: old });
    }
    // Re-mount the current page so it sees the new scope. This matches
    // the scrubber/zone UX of the legacy app: changing chromosome
    // rebuilds the view.
    const cur = this.state.shared.currentPage;
    if (cur && cur.atlas_id && cur.page_id) {
      this.navigate(cur.atlas_id, cur.page_id).catch(err => {
        console.error('Router re-navigate after scope change failed:', err);
      });
    }
  }

  _renderTopbar(currentAtlas, currentPage) {
    const bar = document.getElementById('topbar');
    if (!bar) return;
    bar.innerHTML = '';

    // Determine which stage to expand. If a page is active and we know
    // its stage (from the manifest), expand that stage; else fall back
    // to the first stage in manifest order. Stage pills CSS hides tabs
    // whose data-stage doesn't match #topbar[data-active-stage].
    let activeStageForBar = null;
    if (currentAtlas && currentPage) {
      const mf = this.manifests.get(currentAtlas);
      if (mf && Array.isArray(mf.pages)) {
        const p = mf.pages.find(x => x.id === currentPage);
        if (p && p.stage) activeStageForBar = p.stage;
      }
    }
    if (!activeStageForBar) {
      const firstMf = this.manifests.values().next().value;
      if (firstMf && Array.isArray(firstMf.stages) && firstMf.stages.length > 0) {
        activeStageForBar = firstMf.stages[0].id;
      }
    }
    if (activeStageForBar) bar.dataset.activeStage = activeStageForBar;
    else delete bar.dataset.activeStage;

    const multi = this.manifests.size > 1;

    // Multi-atlas switcher — small <select> at the left of the topbar
    // when more than one atlas is registered. Mirrors the legacy
    // atlasModeIndicator hover-dropdown (header line 4902+). Switching
    // navigates to the chosen atlas's first page.
    if (multi) {
      const switcher = document.createElement('span');
      switcher.className = 'atlas-switcher';
      const label = document.createElement('span');
      label.className = 'atlas-switcher-label';
      label.textContent = 'atlas:';
      switcher.appendChild(label);
      const sel = document.createElement('select');
      sel.className = 'atlas-switcher-select';
      for (const [aid, mf] of this.manifests) {
        const opt = document.createElement('option');
        opt.value = aid;
        opt.textContent = mf.atlas_name || aid;
        if (aid === currentAtlas) opt.selected = true;
        sel.appendChild(opt);
      }
      sel.addEventListener('change', () => {
        const aid = sel.value;
        const mf = this.manifests.get(aid);
        const firstPage = mf && mf.pages && mf.pages[0] && mf.pages[0].id;
        if (aid && firstPage) {
          window.location.hash = `#/${aid}/${firstPage}`;
        }
      });
      switcher.appendChild(sel);
      bar.appendChild(switcher);
    }

    for (const [atlas_id, manifest] of this.manifests) {
      // Multi-atlas mode: render only the active atlas's tabs to keep
      // the topbar uncluttered. The switcher above is the way to reach
      // the other atlases — we don't also render an "INVERSION DETECTION
      // ATLAS" text label because the switcher's current value already
      // tells the user which atlas they're in.
      if (multi && atlas_id !== currentAtlas) continue;
      const sec = document.createElement('div');
      sec.className = 'atlas-section';

      // Group pages by stage
      const byStage = new Map();
      for (const page of manifest.pages) {
        const stage = page.stage || 'default';
        if (!byStage.has(stage)) byStage.set(stage, []);
        byStage.get(stage).push(page);
      }

      // Order stages by manifest.stages if present
      const stageOrder = (manifest.stages || []).map(s => s.id);
      const stages = [...byStage.keys()].sort((a, b) => {
        const ia = stageOrder.indexOf(a); const ib = stageOrder.indexOf(b);
        return (ia === -1 ? 999 : ia) - (ib === -1 ? 999 : ib);
      });

      // Map manifest.stages metadata for label lookup.
      const stageMeta = new Map();
      for (const s of (manifest.stages || [])) stageMeta.set(s.id, s);

      // Build a sequential display-number map keyed by page.id. Pages get
      // their display number based on their position in manifest.pages
      // (so reordering the manifest reorders the tab numbering), rather
      // than extracting it from the raw `page1` / `page12` id. Pages can
      // override with an explicit `displayNum` field in the manifest.
      const displayNumByPage = new Map();
      let seqIdx = 0;
      for (const p of manifest.pages) {
        seqIdx++;
        if (p && p.id) {
          displayNumByPage.set(p.id, p.displayNum != null ? String(p.displayNum) : String(seqIdx));
        }
      }

      for (const stage of stages) {
        const pagesInStage = byStage.get(stage);
        // Stage pill — small label with a colored dot indicating workflow
        // stage. Mirrors the legacy tabBar's tab-stage-pill (monolith line
        // 5003+). No expand/collapse behavior in v1; pills are pure visual
        // groupers between tab clusters. Pill counts the # of pages in the
        // stage. Pills are non-clickable for now.
        if (stage && stage !== 'default') {
          const pill = document.createElement('button');
          pill.type = 'button';
          pill.className = 'tab-stage-pill';
          pill.dataset.stage = stage;
          if (stage === activeStageForBar) pill.dataset.expanded = '1';
          const meta = stageMeta.get(stage);
          const label = (meta && meta.label) || stage;
          pill.title = (meta && meta.description)
            || `Click to expand the "${label}" tab group`;
          const dot = document.createElement('span');
          dot.className = 'pill-dot';
          dot.textContent = '●';
          pill.appendChild(dot);
          pill.appendChild(document.createTextNode(' ' + label));
          const count = document.createElement('span');
          count.className = 'pill-count';
          count.textContent = '(' + pagesInStage.length + ')';
          pill.appendChild(count);
          // Click → toggle this stage's expansion. If the clicked pill is
          // already the active stage, REMOVE the active-stage attribute so
          // all tab clusters collapse (only pills visible). Otherwise focus
          // on this stage. Mutates the topbar's data-active-stage attribute
          // that the CSS reads to show/hide tabs. Does NOT navigate.
          pill.addEventListener('click', () => {
            const isActive = bar.dataset.activeStage === stage;
            if (isActive) {
              delete bar.dataset.activeStage;
              bar.querySelectorAll('.tab-stage-pill').forEach(p => {
                p.dataset.expanded = '0';
              });
            } else {
              bar.dataset.activeStage = stage;
              bar.querySelectorAll('.tab-stage-pill').forEach(p => {
                p.dataset.expanded = (p.dataset.stage === stage) ? '1' : '0';
              });
            }
          });
          sec.appendChild(pill);
        }
        for (const page of pagesInStage) {
          const btn = document.createElement('button');
          btn.dataset.stage = stage;
          // Display number = position in manifest.pages (1-indexed) or
          // explicit page.displayNum override. Renders as a small dim
          // mono span before the label, matching the legacy convention
          // of "1 local PCA |z|" / "2 candidate focus" tabs. Sequential
          // numbering matches the atlas author's intent regardless of
          // page id (e.g. "local PCA θπ" with id `page12` can display
          // as tab "4" if it's the 4th page in the manifest).
          const numStr = displayNumByPage.get(page.id);
          if (numStr) {
            const num = document.createElement('span');
            num.className = 'num';
            num.textContent = numStr;
            btn.appendChild(num);
          }
          btn.appendChild(document.createTextNode(' ' + (page.label || page.id)));
          if (page.tooltip) btn.title = page.tooltip;
          if (atlas_id === currentAtlas && page.id === currentPage) {
            btn.classList.add('active');
          }
          btn.addEventListener('click', () => {
            window.location.hash = `#/${atlas_id}/${page.id}`;
          });
          sec.appendChild(btn);
        }
      }

      bar.appendChild(sec);
    }
  }
}
