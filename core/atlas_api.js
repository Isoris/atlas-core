// core/atlas_api.js
// =====================================================================
// The public API surface that page modules import from.
//
// A page module looks like:
//
//   import { resolve, set, subscribe, registerHandler } from '../core/atlas_api.js';
//
//   export async function mount(root, atlasState, registry) {
//     const candidate = atlasState.shared.activeCandidate;
//     const fst = await resolve('fst_hom1_hom2', { candidate_id: candidate.id });
//     // ... render ...
//   }
//
// This module is a thin facade over the singleton registry + state.
// It exists so pages can import a stable surface without knowing where
// the registry is constructed.
//
// =====================================================================

let _registry = null;
let _state = null;

export function bootstrap({ registry, atlasState }) {
  _registry = registry;
  _state = atlasState;
}

export function resolve(key, args = {})    { return _registry.resolve(key, args); }
export function set(key, value, args = {}) { return _registry.set(key, value, args); }
export function invalidate(key, args = {}) { return _registry.invalidate(key, args); }
export function trace(key, args = {})      { return _registry.trace(key, args); }

export function subscribe(event, callback) { return _state.subscribe(event, callback); }
export function emit(event, payload)       { return _state.emit(event, payload); }

export function getState() { return _state; }
