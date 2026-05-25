// core/chrom_prewarm_scheduler.js
// =====================================================================
// SPEC_multichrom_load_orchestrator Slice 3 (preview) — background
// chrom prewarmer.
//
// Walks the chromosome list from the active scope picker and uses
// requestIdleCallback to pre-resolve `scrubber_main` for each chrom
// that isn't already in the chrom-summary cache. Result: when the user
// next switches chroms, the warm-tier IDB cache (populated via
// registry.resolve → CacheStore.set) already has the payload, so the
// page mount await returns near-instantly.
//
// Design constraints:
//   - OPT-IN. Heavy: each scrubber_main is multi-MB and IDB persistence
//     has a per-origin quota. Default OFF; the chrom-summary modal
//     exposes a toggle that persists to localStorage.
//   - ONE AT A TIME. Idle-callback chained so the browser never
//     processes more than one chrom's parse at once. A long-running
//     idle frame yields back when its deadline expires.
//   - ABORTABLE. Disabling the toggle, or changing the active chrom,
//     cancels any in-flight schedule. New active chrom triggers a fresh
//     schedule centered on neighbors-first.
//   - DEDUP. Skips chroms that already have a summary entry (so we don't
//     redo work the user has already paid for in a previous session).
//   - NEVER NETWORK-RACE WITH THE ACTIVE PAGE. The active chrom's
//     scrubber_main resolve goes through the same registry path with
//     in-flight Promise dedup — if the user lands on LG02 while the
//     prewarmer was about to fetch LG02, they share the same fetch.
//
// Toggle storage key: 'atlas.chromPrewarmEnabled' (boolean string).
// =====================================================================

import { buildChromSummary } from './chrom_summary.js';

const TOGGLE_LS_KEY = 'atlas.chromPrewarmEnabled';

export class ChromPrewarmScheduler {

  /**
   * @param {object} opts
   * @param {object} opts.atlasState   — AtlasState instance (for activeChrom + chromSummaries)
   * @param {object} opts.registry     — Registry (for resolve())
   * @param {function} [opts.getChromList]  — () → string[] of all chroms to consider.
   *                                          Default reads the active scope picker DOM.
   */
  constructor({ atlasState, registry, getChromList } = {}) {
    this.state = atlasState;
    this.registry = registry;
    this.getChromList = getChromList || _readChromListFromScopebar;
    this._aborted = false;
    this._inflight = false;
    this._currentToken = 0;
  }

  isEnabled() {
    try {
      return typeof localStorage !== 'undefined'
        && localStorage.getItem(TOGGLE_LS_KEY) === 'true';
    } catch (_) {
      return false;
    }
  }

  setEnabled(enabled) {
    try {
      if (typeof localStorage !== 'undefined') {
        localStorage.setItem(TOGGLE_LS_KEY, enabled ? 'true' : 'false');
      }
    } catch (_) {}
    if (enabled) this.kick();
    else this.abort();
  }

  attach() {
    if (!this.state || typeof this.state.subscribe !== 'function') return;
    // Whenever the user changes chroms, restart the schedule around the
    // new active chrom (neighbors-first ordering).
    this.state.subscribe('shared.activeChrom.changed', () => {
      if (this.isEnabled()) this.kick();
    });
    // Also subscribe to summary changes — when a new summary lands we
    // can advance to the next un-summarized chrom on the next idle tick.
    this.state.subscribe('shared.chromSummaries.changed', () => {
      // Don't restart; let the in-flight chain advance naturally.
    });
    // Kick once on attach if the toggle was enabled in a prior session.
    if (this.isEnabled()) this.kick();
  }

  abort() {
    this._aborted = true;
    this._currentToken += 1;   // invalidates any pending idle callback
  }

  /**
   * Compute the prewarm order (neighbors-first around the active chrom,
   * minus chroms already summarized) and kick off the idle chain.
   * Idempotent: each kick increments a token so older chains exit on
   * their next idle wake.
   */
  kick() {
    this._aborted = false;
    const token = ++this._currentToken;
    const all = (this.getChromList && this.getChromList()) || [];
    if (all.length === 0) return;
    const active = (this.state && this.state.shared && this.state.shared.activeChrom) || null;
    const cached = (this.state && this.state.shared && this.state.shared.chromSummaries)
      ? this.state.shared.chromSummaries : {};
    const queue = _neighborsFirstOrder(all, active).filter(c => !cached[c] && c !== active);
    if (queue.length === 0) return;
    this._scheduleNext(queue, token);
  }

  _scheduleNext(queue, token) {
    if (token !== this._currentToken) return;   // a newer kick superseded us
    if (this._aborted || queue.length === 0) return;
    const chrom = queue.shift();
    const fire = () => {
      if (token !== this._currentToken || this._aborted) return;
      if (!this.registry || typeof this.registry.resolve !== 'function') return;
      this._inflight = true;
      Promise.resolve(this.registry.resolve('scrubber_main', { chrom }))
        .then((payload) => {
          // 2026-05-26: write a chromSummary right here so the shell
          // chip ticks up as the prewarmer makes progress. Without this,
          // the registry cache fills silently and the user sees no
          // feedback until they actually mount a page on the chrom (at
          // which point the page's own setChromSummary fires). For the
          // "I turned on prewarm; is it doing anything?" UX, the chip
          // is the canonical surface. Skip when the payload was null
          // (auto-index miss / 404 — the chrom genuinely has no precomp).
          if (!payload || typeof payload !== 'object') return;
          if (this.state && typeof this.state.setChromSummary === 'function') {
            this.state.setChromSummary(chrom, buildChromSummary(payload, { chrom }));
          }
        })
        .catch((e) => {
          // Don't spam the console for the expected 404s — the chrom may
          // simply have no precomp on disk yet.
          if (typeof console.debug === 'function') {
            console.debug(`[chrom prewarm] ${chrom} skipped:`, (e && e.message) || e);
          }
        })
        .finally(() => {
          this._inflight = false;
          // Yield to the browser before the next chrom so the active
          // page never feels janky from background fetches.
          _idle(() => this._scheduleNext(queue, token), 500);
        });
    };
    _idle(fire, 1500);
  }
}

// Order chroms so that the closest neighbors of the active chrom come
// first, then the further ones outwards. With active=LG07, ordering is
// LG06, LG08, LG05, LG09, LG04, LG10, ..., LG01, LG28, LG02, LG27, etc.
// Lex order falls through for any chroms that don't match the LG regex.
function _neighborsFirstOrder(chroms, active) {
  if (!active) return chroms.slice();
  const idx = chroms.indexOf(active);
  if (idx < 0) return chroms.slice();
  const out = [];
  for (let d = 1; d <= chroms.length; d++) {
    const left  = idx - d;
    const right = idx + d;
    if (right < chroms.length) out.push(chroms[right]);
    if (left  >= 0)            out.push(chroms[left]);
  }
  return out;
}

function _readChromListFromScopebar() {
  if (typeof document === 'undefined') return [];
  const sel = document.querySelector(
    '#scopebar .scope-picker[data-slot="activeChrom"] select');
  if (!sel) return [];
  return Array.from(sel.options)
    .map(o => o.value)
    .filter(v => v && v.length > 0);
}

// rIC shim — falls back to setTimeout in browsers without
// requestIdleCallback (Safari). The `timeout` ms is the latest we'll
// wait before firing even when the browser isn't idle, so chroms still
// pre-warm in the background even under sustained main-thread work.
function _idle(fn, timeout) {
  if (typeof requestIdleCallback === 'function') {
    requestIdleCallback(fn, { timeout });
  } else if (typeof setTimeout === 'function') {
    setTimeout(fn, Math.min(timeout, 250));
  } else {
    fn();
  }
}
