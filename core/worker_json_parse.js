// core/worker_json_parse.js
// =====================================================================
// Host-side helper for the JSON-parse Web Worker.
//
// Why: parsing a 30+ MB scrubber_main JSON on the main thread blocks
// paint, scroll, and click for the full parse duration (~300-800 ms on
// modest laptops). Offloading the parse to a Worker keeps the main
// thread interactive — the page can render a "loading" indicator,
// handle clicks, and run other animations during the parse.
//
// Tradeoff: the parsed object crosses the worker boundary via
// structured clone, which for a 30 MB object adds ~100-200 ms of copy
// time. Wall-clock is therefore *not* shorter than a main-thread parse;
// the win is purely "the main thread doesn't freeze". For payloads
// smaller than a few MB the copy overhead is meaningful relative to the
// parse, so this helper is opt-in (set `worker_parse: true` on the
// layer entry; only flip on for genuinely heavy payloads).
//
// One Worker per host page is reused across calls (workers are heavy
// to spin up — ~5 ms each — and we want concurrent parses to share).
//
// Falls back to a synchronous JSON.parse when Worker construction
// fails or `Worker` is unavailable (older browsers, JSDOM, server).
// =====================================================================

let _worker = null;
let _nextId = 1;
const _pending = new Map();

/**
 * Parse `text` as JSON, off the main thread when possible.
 *
 * @param {string} text
 * @returns {Promise<any>}
 */
export function parseJsonInWorker(text) {
  const w = _ensureWorker();
  if (!w) {
    // Fallback path — Worker isn't available; do it on the main thread.
    try { return Promise.resolve(JSON.parse(text)); }
    catch (e) { return Promise.reject(e); }
  }
  return new Promise((resolve, reject) => {
    const id = _nextId++;
    _pending.set(id, { resolve, reject });
    w.postMessage({ id, text });
  });
}

/**
 * Terminate the worker (drops any in-flight parses). Tests + the bulk
 * loader's tear-down call this to release the worker's heap. Idempotent.
 */
export function terminateJsonWorker() {
  if (_worker) {
    try { _worker.terminate(); } catch (_) {}
    _worker = null;
  }
  for (const [, { reject }] of _pending) {
    try { reject(new Error('worker terminated')); } catch (_) {}
  }
  _pending.clear();
}

function _ensureWorker() {
  if (_worker) return _worker;
  if (typeof Worker === 'undefined') return null;
  try {
    // ESM-style worker URL — the assembled workspace serves
    // core/json_worker.js at the same path. import.meta.url gives the
    // host module's URL, which resolves relative to the workspace.
    const workerUrl = new URL('./json_worker.js', import.meta.url);
    _worker = new Worker(workerUrl, { type: 'module' });
    _worker.onmessage = (e) => {
      const { id, ok, payload, error } = e.data || {};
      const pending = _pending.get(id);
      if (!pending) return;
      _pending.delete(id);
      if (ok) pending.resolve(payload);
      else    pending.reject(new Error(error || 'json_worker: unknown error'));
    };
    _worker.onerror = (e) => {
      console.warn('[json_worker] runtime error:', (e && e.message) || e);
      // Best-effort: reject every pending request so callers don't hang.
      for (const [id, { reject }] of _pending) {
        try { reject(new Error('worker crashed')); } catch (_) {}
        _pending.delete(id);
      }
      _worker = null;
    };
    return _worker;
  } catch (e) {
    console.warn('[json_worker] failed to spawn worker; falling back to main-thread parse:', (e && e.message) || e);
    _worker = null;
    return null;
  }
}
