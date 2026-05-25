// core/persist_debounced.js
// =====================================================================
// Debounced localStorage writer for the atlas-core shell. Lifted from
// the inversion-atlas helper of the same name (2026-05-21 perf audit
// Tier-S #2); the atlas-core copy lives here so AtlasState and the
// router can use it without taking a cross-repo dependency.
//
// Per-key debounce: rapid writes to the same key coalesce into one
// localStorage.setItem call. Values are stringified at call time so
// the caller can mutate the source object afterward.
//
// Flush triggers: the scheduled timer, an explicit flushPersistNow()
// call, page hide / beforeunload / visibilitychange→hidden.
// =====================================================================

const _TIMERS         = new Map();   // key → timeoutId
const _PENDING_VALUES = new Map();   // key → string (latest pending value)

/** Debounce-write a value to localStorage under `key`. Non-string
 *  values are JSON.stringified at call time. Rapid same-key calls
 *  within `ms` coalesce: only the LAST value gets written. Default
 *  300ms — covers the rapid-click window with a margin without making
 *  close-tab persistence feel laggy (pagehide flushes everything
 *  pending). */
export function persistDebounced(key, value, ms = 300) {
  const s = (typeof value === 'string') ? value : JSON.stringify(value);
  _PENDING_VALUES.set(key, s);
  const prev = _TIMERS.get(key);
  if (prev !== undefined && typeof clearTimeout === 'function') {
    clearTimeout(prev);
  }
  if (typeof setTimeout !== 'function') {
    _flushKey(key);  // non-browser env (tests) — write through
    return;
  }
  _TIMERS.set(key, setTimeout(() => _flushKey(key), ms));
}

/** Flush ALL pending writes synchronously. Called on page hide so a
 *  tab close doesn't lose any pending state. Also exposed so explicit
 *  save / export flows can guarantee persistence before they fire. */
export function flushPersistNow() {
  for (const key of [..._TIMERS.keys()]) {
    const t = _TIMERS.get(key);
    if (t !== undefined && typeof clearTimeout === 'function') clearTimeout(t);
    _flushKey(key);
  }
}

function _flushKey(key) {
  const v = _PENDING_VALUES.get(key);
  _TIMERS.delete(key);
  _PENDING_VALUES.delete(key);
  if (v === undefined) return;
  try {
    if (typeof localStorage !== 'undefined') localStorage.setItem(key, v);
  } catch (_) { /* quota / disabled / SecurityError → drop silently */ }
}

if (typeof window !== 'undefined') {
  try {
    window.addEventListener('pagehide',     flushPersistNow);
    window.addEventListener('beforeunload', flushPersistNow);
  } catch (_) {}
}
if (typeof document !== 'undefined') {
  try {
    document.addEventListener('visibilitychange', () => {
      if (document.visibilityState === 'hidden') flushPersistNow();
    });
  } catch (_) {}
}
