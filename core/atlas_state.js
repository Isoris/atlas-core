// core/atlas_state.js
// =====================================================================
// The global AtlasState container.
//
// Lives on window.AtlasState. Pages read/write through it directly.
// Shape (per SPEC_atlas_state_v1.md, TBD):
//
//   AtlasState = {
//     shared: {
//       activeChrom, activeCandidate, activeRegion, activeWindow,
//       sampleIds, serverBaseUrl, currentPage
//     },
//     inversion: { ...inversion-private slots... },
//     diversity: { ...diversity-private slots... },
//     ...one bucket per loaded atlas...
//   }
//
// AtlasState also has a tiny event bus (subscribe / emit) so the
// prewarm scheduler can react to state changes.
//
// =====================================================================

// ---------------------------------------------------------------------
// IMPLEMENTATION_NOTE for next chat:
//   ~200 LOC. Three subsystems:
//   1. Slot scaffolding: at register_atlas time, the shell calls
//      atlasState.registerAtlasSlots(atlas_id, slotDefs) which walks
//      slots.registry.json and creates the bucket with defaults.
//   2. Event bus: emit when shared.* slots change so prewarm scheduler
//      can preload. Per-atlas slot changes don't emit by default
//      (they're noisy). Atlases can opt in.
//   3. Persistence: localStorage round-trip on visibility change.
//      Scope: only slots tagged persist:true in slots.registry.json.
//      Cross-atlas slots round-trip too.
//
// SLOT VALIDATION:
//   The shell SHOULD warn (not throw) when a page writes to
//   AtlasState.<other_atlas>.* — that's a contract violation but
//   sometimes useful for prototyping. Strict-mode flag for tests.
// ---------------------------------------------------------------------

const SHARED_DEFAULTS = {
  activeChrom: null,
  activeCandidate: null,
  activeRegion: null,
  activeWindow: null,
  activeSpecies: null,
  activeCohort: null,
  sampleIds: null,
  serverBaseUrl: null,
  currentPage: null
};

export class AtlasState {

  constructor({ serverBaseUrl } = {}) {
    this.shared = { ...SHARED_DEFAULTS };
    if (serverBaseUrl) this.shared.serverBaseUrl = serverBaseUrl;
    this._subscribers = new Map();    // event_name → Set<callback>
    this._strict = false;
  }

  // ------------------------------------------------------------------
  // Atlas registration: called once per atlas at startup, by the shell
  // after atlas_discovery returns.
  // ------------------------------------------------------------------

  registerAtlasSlots(atlas_id, slotDefs) {
    if (this[atlas_id]) {
      throw new Error(`AtlasState: atlas '${atlas_id}' already registered`);
    }
    const bucket = {};
    const persistKeys = [];
    for (const [name, def] of Object.entries(slotDefs)) {
      if (name.startsWith('_')) continue;
      if (typeof def !== 'object' || def === null) continue;
      bucket[name] = (def.default !== undefined) ? this._cloneDefault(def.default, def.type) : null;
      if (def.persist === true) persistKeys.push(name);
    }
    this[atlas_id] = bucket;
    if (!this._slotDefs) this._slotDefs = new Map();
    this._slotDefs.set(atlas_id, slotDefs);
    if (!this._persistKeys) this._persistKeys = new Map();
    this._persistKeys.set(atlas_id, persistKeys);
  }

  _cloneDefault(value, type) {
    // Deep-clone defaults so atlases can't accidentally share mutable
    // defaults (e.g. two pages pushing into the same default array).
    if (type === 'Set') return new Set();
    if (type === 'Map') return new Map();
    if (Array.isArray(value)) return [...value];
    if (value && typeof value === 'object') return JSON.parse(JSON.stringify(value));
    return value;
  }

  // ------------------------------------------------------------------
  // Event bus
  // ------------------------------------------------------------------

  subscribe(event, callback) {
    if (!this._subscribers.has(event)) this._subscribers.set(event, new Set());
    this._subscribers.get(event).add(callback);
    return () => this._subscribers.get(event).delete(callback);
  }

  emit(event, payload) {
    const subs = this._subscribers.get(event);
    if (!subs) return;
    for (const cb of subs) {
      try { cb(payload); } catch (e) { console.error(`AtlasState subscriber for '${event}' threw:`, e); }
    }
  }

  // ------------------------------------------------------------------
  // Convenience setters that emit events
  // ------------------------------------------------------------------

  setActiveChrom(chrom) {
    const old = this.shared.activeChrom;
    if (old === chrom) return;
    this.shared.activeChrom = chrom;
    this.emit('shared.activeChrom.changed', { newValue: chrom, oldValue: old });
  }

  setActiveCandidate(cand) {
    const old = this.shared.activeCandidate;
    if (old === cand) return;
    this.shared.activeCandidate = cand;
    this.emit('shared.activeCandidate.changed', { newValue: cand, oldValue: old });
  }

  // ------------------------------------------------------------------
  // Persistence
  // ------------------------------------------------------------------

  savePersisted() {
    if (typeof localStorage === 'undefined') return;
    const out = { shared: {} };
    // Shared: persist activeChrom + activeCandidate identity (not full object).
    if (this.shared.activeChrom) out.shared.activeChrom = this.shared.activeChrom;
    if (this.shared.activeCandidate && this.shared.activeCandidate.id) {
      out.shared.activeCandidateId = this.shared.activeCandidate.id;
    }
    // 2026-05-19: persist the last visited page so close/reopen lands on
    // the same atlas + tab the user was on. The router writes
    // `shared.currentPage = { atlas_id, page_id }` after every navigate().
    if (this.shared.currentPage && this.shared.currentPage.atlas_id
        && this.shared.currentPage.page_id) {
      out.shared.currentPage = {
        atlas_id: this.shared.currentPage.atlas_id,
        page_id:  this.shared.currentPage.page_id,
      };
    }
    // Per-atlas persisted slots.
    if (this._persistKeys) {
      for (const [atlas_id, keys] of this._persistKeys) {
        if (!keys.length) continue;
        const bucket = this[atlas_id];
        if (!bucket) continue;
        out[atlas_id] = {};
        for (const k of keys) {
          out[atlas_id][k] = bucket[k];
        }
      }
    }
    try {
      localStorage.setItem('atlas_state_v1', JSON.stringify(out));
    } catch (e) {
      console.warn('AtlasState.savePersisted: localStorage write failed:', e);
    }
  }

  loadPersisted() {
    if (typeof localStorage === 'undefined') return;
    let raw;
    try { raw = localStorage.getItem('atlas_state_v1'); }
    catch { return; }
    if (!raw) return;
    let parsed;
    try { parsed = JSON.parse(raw); }
    catch { return; }
    if (parsed.shared) {
      if (parsed.shared.activeChrom) this.shared.activeChrom = parsed.shared.activeChrom;
      // Note: activeCandidate is rehydrated by the caller using the id, since
      // the full candidate object lives in registry-resolved data.
      if (parsed.shared.activeCandidateId) this.shared._pendingCandidateId = parsed.shared.activeCandidateId;
      // 2026-05-19: stash the persisted currentPage under _pendingCurrentPage
      // so the router can use it as the hash fallback at boot time. Not
      // written into shared.currentPage directly because the router treats
      // that as live navigation state.
      if (parsed.shared.currentPage
          && parsed.shared.currentPage.atlas_id
          && parsed.shared.currentPage.page_id) {
        this.shared._pendingCurrentPage = {
          atlas_id: parsed.shared.currentPage.atlas_id,
          page_id:  parsed.shared.currentPage.page_id,
        };
      }
    }
    for (const k of Object.keys(parsed)) {
      if (k === 'shared') continue;
      if (this[k] && typeof this[k] === 'object') {
        Object.assign(this[k], parsed[k]);
      }
    }
  }
}
