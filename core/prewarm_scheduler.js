// core/prewarm_scheduler.js
// =====================================================================
// Listens for AtlasState change events and pre-warms layers tagged
// with the corresponding preload_on trigger.
//
// Trigger events (v1):
//   - chrom_change      (from shared.activeChrom.changed)
//   - candidate_change  (from shared.activeCandidate.changed)
//   - page_mount        (from shell.page_mount)
//
// For hot-tier layers, the resolved value is also written to
// AtlasState.<atlas_id>.tracks.<chrom>.<layer> when entry.pin_to is
// set, so pages can read directly without going through resolve().
//
// Cancellation: each trigger increments a generation counter. In-flight
// preloads from older generations are aborted via AbortController.
// =====================================================================

export class PrewarmScheduler {

  constructor({ atlasState, registry } = {}) {
    this.state = atlasState;
    this.registry = registry;
    this._gens = {
      chrom: 0,
      candidate: 0,
      page: 0
    };
    this._abortControllers = new Map();
  }

  attach() {
    if (!this.state || typeof this.state.subscribe !== 'function') {
      console.warn('PrewarmScheduler.attach: atlasState has no subscribe()');
      return;
    }
    this.state.subscribe('shared.activeChrom.changed', (ev) => {
      this.onChromChange(ev.newValue, ev.oldValue);
    });
    this.state.subscribe('shared.activeCandidate.changed', (ev) => {
      this.onCandidateChange(ev.newValue, ev.oldValue);
    });
    this.state.subscribe('shell.page_mount', (ev) => {
      this.onPageMount(ev.atlas_id, ev.page_id);
    });
  }

  // ------------------------------------------------------------------

  async onChromChange(newChrom /*, oldChrom */) {
    const gen = ++this._gens.chrom;
    this._abortGen('chrom', gen - 1);
    const ctrl = new AbortController();
    this._abortControllers.set(`chrom:${gen}`, ctrl);

    await this._preloadByEvent('chrom_change', this._buildArgs({ chrom: newChrom }), ctrl, gen, 'chrom');
  }

  async onCandidateChange(newCand /*, oldCand */) {
    const gen = ++this._gens.candidate;
    this._abortGen('candidate', gen - 1);
    const ctrl = new AbortController();
    this._abortControllers.set(`candidate:${gen}`, ctrl);

    if (!newCand || !newCand.id) return;
    await this._preloadByEvent('candidate_change', this._buildArgs({ candidate_id: newCand.id }), ctrl, gen, 'candidate');
  }

  // Pull every primitive from shared state into the resolve args so layer
  // path templates like 'data/precomp/{chrom}.json' or
  // 'data/cohort/ancestry/windows/{chrom}_K{K}.tsv' can fill all placeholders
  // without each event handler needing to know which keys matter.
  //
  // Aliases: shared state uses 'activeChrom' but legacy layer templates
  // use {chrom}; same for {candidate_id} ← shared.activeCandidate.id.
  _buildArgs(seed) {
    const args = Object.assign({}, seed || {});
    const sh = (this.state && this.state.shared) || {};
    if (args.chrom === undefined && typeof sh.activeChrom === 'string') {
      args.chrom = sh.activeChrom;
    }
    if (args.candidate_id === undefined && sh.activeCandidate && sh.activeCandidate.id) {
      args.candidate_id = sh.activeCandidate.id;
    }
    if (args.species === undefined && typeof sh.activeSpecies === 'string') {
      args.species = sh.activeSpecies;
    }
    for (const [k, v] of Object.entries(sh)) {
      if (args[k] !== undefined) continue;
      if (v != null && (typeof v === 'string' || typeof v === 'number')) {
        args[k] = v;
      }
    }
    return args;
  }

  async onPageMount(atlas_id, page_id) {
    const gen = ++this._gens.page;
    this._abortGen('page', gen - 1);
    const ctrl = new AbortController();
    this._abortControllers.set(`page:${gen}`, ctrl);

    if (!this.registry || !this.registry._atlases) return;
    const atlas = this.registry._atlases.get(atlas_id);
    if (!atlas) return;
    const pageEntry = (atlas.pages && atlas.pages[page_id]) || null;
    if (!pageEntry || !Array.isArray(pageEntry.preloads)) return;

    const args = this._buildArgs();

    for (const layerKey of pageEntry.preloads) {
      if (ctrl.signal.aborted) return;
      try {
        await this.registry.resolve(layerKey, args);
      } catch (e) {
        const msg = (e && e.message) || String(e);
        if (msg.includes('HTTP 404')) {
          if (typeof console.debug === 'function') {
            console.debug(`Prewarm onPageMount: ${atlas_id}/${page_id} optional preload '${layerKey}' missing (404)`);
          }
        } else {
          console.warn(`Prewarm onPageMount: ${atlas_id}/${page_id} preload '${layerKey}' failed:`, e);
        }
      }
    }
  }

  // ------------------------------------------------------------------

  /**
   * Walk every atlas's layers, find ones with matching preload_on,
   * resolve them in parallel. Honor abort signal.
   */
  async _preloadByEvent(eventName, args, ctrl, gen, genKind) {
    if (!this.registry || !this.registry._atlases) return;
    const tasks = [];
    for (const [atlas_id, atlas] of this.registry._atlases) {
      for (const [name, entry] of Object.entries(atlas.layers || {})) {
        if (name.startsWith('_')) continue;
        if (typeof entry !== 'object' || entry === null) continue;
        if (entry.preload_on !== eventName) continue;
        tasks.push(this._preloadLayer(name, entry, args, atlas_id, ctrl));
      }
    }
    // Promise.all parallelizes; we don't await individual failures.
    // 404s on side-car layers (band_*.tsv, repeat_density, candidate_tracks,
    // etc.) are expected when the precomp ships only the main scrubber JSON.
    // Downgrade those to debug-only so the console isn't drowned in noise;
    // genuine errors (5xx, network, parse failures) still console.warn.
    await Promise.all(tasks.map(t => t.catch(e => {
      const msg = (e && e.message) || String(e);
      if (msg.includes('HTTP 404')) {
        if (typeof console.debug === 'function') {
          console.debug(`Prewarm ${eventName}: optional layer missing (404):`, msg);
        }
      } else {
        console.warn(`Prewarm ${eventName}: layer preload failed:`, e);
      }
    })));

    if (this._gens[genKind] === gen) {
      this._abortControllers.delete(`${genKind}:${gen}`);
    }
  }

  async _preloadLayer(name, entry, args, atlas_id, ctrl) {
    if (ctrl.signal.aborted) return;
    const value = await this.registry.resolve(name, args);
    if (ctrl.signal.aborted) return;

    // For hot-tier with pin_to declared, also write to AtlasState path
    // so pages can read AtlasState.<atlas_id>.tracks.<chrom>.<layer>
    // directly.
    if ((entry.tier === 'hot') && entry.pin_to) {
      this._pinToState(entry.pin_to, args, value, atlas_id);
    }
  }

  _pinToState(pinPathTemplate, args, value, atlas_id) {
    if (!this.state) return;
    let path;
    try {
      path = templateFillSimple(pinPathTemplate, args, this.state);
    } catch (e) {
      console.warn(`Prewarm: pin_to template '${pinPathTemplate}' failed:`, e);
      return;
    }
    // path looks like "AtlasState.inversion.tracks.LG28"
    // We strip the leading "AtlasState." and walk.
    const parts = path.replace(/^AtlasState\./, '').split('.');
    let target = this.state;
    for (let i = 0; i < parts.length - 1; i++) {
      const p = parts[i];
      if (!target[p] || typeof target[p] !== 'object') target[p] = {};
      target = target[p];
    }
    target[parts[parts.length - 1]] = value;
  }

  _abortGen(kind, gen) {
    const k = `${kind}:${gen}`;
    const ctrl = this._abortControllers.get(k);
    if (ctrl) {
      ctrl.abort();
      this._abortControllers.delete(k);
    }
  }
}

// Local copy of templateFill — we don't import from registry_core to
// avoid circular dependency. Same semantics, simpler signature.
function templateFillSimple(template, args, atlasState) {
  return template.replace(/\{([^}]+)\}/g, (_, name) => {
    if (args && args[name] !== undefined) return String(args[name]);
    if (atlasState.shared && atlasState.shared[name] !== undefined) {
      return String(atlasState.shared[name]);
    }
    throw new Error(`templateFillSimple: unresolved '{${name}}' in '${template}'`);
  });
}
