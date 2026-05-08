// core/cache_store.js
// =====================================================================
// Cache primitives. Three tiers:
//   - hot:  in-memory Map
//   - warm: IndexedDB
//   - cold: throws (cold is not cached at this layer)
//
// Standalone module — no dependencies on registry_core or atlas state.
// =====================================================================

const DB_NAME = 'atlas_registry_cache';
const DB_VERSION = 1;
const STORE_NAME = 'kv';

export class CacheStore {

  constructor({ maxBytes = 500 * 1024 * 1024 } = {}) {
    this.maxBytes = maxBytes;
    this._mem = new Map();
    this._memOrder = [];
    this._dbPromise = null;
  }

  get(tier, key) {
    if (tier === 'hot')  return this._memGet(key);
    if (tier === 'warm') return this._idbGet(key);
    throw new Error(`CacheStore.get: invalid tier '${tier}'`);
  }

  set(tier, key, value) {
    if (tier === 'hot')  return this._memSet(key, value);
    if (tier === 'warm') return this._idbSet(key, value);
    throw new Error(`CacheStore.set: invalid tier '${tier}'`);
  }

  delete(tier, key) {
    if (tier === 'hot')  return this._memDelete(key);
    if (tier === 'warm') return this._idbDelete(key);
    throw new Error(`CacheStore.delete: invalid tier '${tier}'`);
  }

  list(tier, prefix = '') {
    if (tier === 'hot')  return [...this._mem.keys()].filter(k => k.startsWith(prefix));
    if (tier === 'warm') return this._idbList(prefix);
    throw new Error(`CacheStore.list: invalid tier '${tier}'`);
  }

  // ------------------------------------------------------------------
  // PRIVATE: memory tier
  // ------------------------------------------------------------------

  _memGet(key) {
    if (!this._mem.has(key)) return null;
    this._touchLRU(key);
    return this._mem.get(key);
  }

  _memSet(key, value) {
    if (this._mem.has(key)) {
      this._mem.set(key, value);
      this._touchLRU(key);
    } else {
      this._mem.set(key, value);
      this._memOrder.push(key);
    }
    while (this._mem.size > 1000) {
      const evict = this._memOrder.shift();
      this._mem.delete(evict);
    }
  }

  _memDelete(key) {
    if (!this._mem.has(key)) return;
    this._mem.delete(key);
    const i = this._memOrder.indexOf(key);
    if (i >= 0) this._memOrder.splice(i, 1);
  }

  _touchLRU(key) {
    const i = this._memOrder.indexOf(key);
    if (i >= 0) this._memOrder.splice(i, 1);
    this._memOrder.push(key);
  }

  // ------------------------------------------------------------------
  // PRIVATE: IndexedDB tier
  // ------------------------------------------------------------------

  _ensureDb() {
    if (this._dbPromise) return this._dbPromise;
    this._dbPromise = new Promise((resolve, reject) => {
      if (typeof indexedDB === 'undefined') {
        resolve(null);
        return;
      }
      const req = indexedDB.open(DB_NAME, DB_VERSION);
      req.onupgradeneeded = (e) => {
        const db = e.target.result;
        if (!db.objectStoreNames.contains(STORE_NAME)) {
          db.createObjectStore(STORE_NAME);
        }
      };
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    });
    return this._dbPromise;
  }

  async _idbGet(key) {
    const db = await this._ensureDb();
    if (!db) return this._memGet(`__warm__:${key}`);
    return new Promise((resolve, reject) => {
      const tx = db.transaction(STORE_NAME, 'readonly');
      const req = tx.objectStore(STORE_NAME).get(key);
      req.onsuccess = () => resolve(req.result === undefined ? null : req.result);
      req.onerror = () => reject(req.error);
    });
  }

  async _idbSet(key, value) {
    const db = await this._ensureDb();
    if (!db) { this._memSet(`__warm__:${key}`, value); return; }
    return new Promise((resolve, reject) => {
      const tx = db.transaction(STORE_NAME, 'readwrite');
      const req = tx.objectStore(STORE_NAME).put(value, key);
      req.onsuccess = () => resolve();
      req.onerror = () => reject(req.error);
    });
  }

  async _idbDelete(key) {
    const db = await this._ensureDb();
    if (!db) { this._memDelete(`__warm__:${key}`); return; }
    return new Promise((resolve, reject) => {
      const tx = db.transaction(STORE_NAME, 'readwrite');
      const req = tx.objectStore(STORE_NAME).delete(key);
      req.onsuccess = () => resolve();
      req.onerror = () => reject(req.error);
    });
  }

  async _idbList(prefix) {
    const db = await this._ensureDb();
    if (!db) {
      return [...this._mem.keys()]
        .filter(k => k.startsWith('__warm__:'))
        .map(k => k.slice('__warm__:'.length))
        .filter(k => k.startsWith(prefix));
    }
    return new Promise((resolve, reject) => {
      const tx = db.transaction(STORE_NAME, 'readonly');
      const req = tx.objectStore(STORE_NAME).getAllKeys();
      req.onsuccess = () => {
        const keys = req.result.filter(k => typeof k === 'string' && k.startsWith(prefix));
        resolve(keys);
      };
      req.onerror = () => reject(req.error);
    });
  }
}
