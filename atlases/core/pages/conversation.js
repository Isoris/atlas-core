// atlases/core/pages/conversation.js
// =============================================================================
// Conversation page — static design-doc surface. No data loads, no event
// wiring beyond the in-fragment <a href="#/core/..."> links which the
// AtlasRouter handles via its hashchange listener.
//
// mount() exists only to satisfy the router contract. unmount() is a no-op.
// =============================================================================

export async function mount(_root, _atlasState, _registry) {
  // Nothing to do — the fragment is fully self-contained.
}

export async function unmount(_root) {
  // Nothing to tear down.
}
