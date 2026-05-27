// core/json_worker.js
// =====================================================================
// Tiny Web Worker that runs JSON.parse off the main thread.
//
// Protocol:
//   in:  { id: number, text: string }
//   out: { id: number, ok: true,  payload: any }
//        { id: number, ok: false, error: string }
//
// The host (core/worker_json_parse.js) keeps id → resolver mappings so
// multiple in-flight parses can share one worker. The result crosses the
// postMessage boundary as a structured-clone (browser-native; no JSON
// re-serialize), so the per-message overhead is the clone cost only.
// =====================================================================

self.onmessage = function (e) {
  const data = e.data || {};
  const id = data.id;
  const text = data.text;
  if (typeof text !== 'string') {
    self.postMessage({ id, ok: false, error: 'json_worker: expected message.text to be a string' });
    return;
  }
  try {
    const payload = JSON.parse(text);
    self.postMessage({ id, ok: true, payload });
  } catch (err) {
    self.postMessage({ id, ok: false, error: (err && err.message) || String(err) });
  }
};
