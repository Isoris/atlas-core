// atlases/mock/pages/hello.js
//
// Minimal page that proves the shell + registry loop closes.
// Mounts, calls registry.resolve('hello_data'), renders the message.

import { resolve } from '../../../core/atlas_api.js';

export async function mount(root, atlasState, registry) {
  const data = await resolve('hello_data');
  const el = root.querySelector('#hello-msg');
  if (el) el.textContent = data.message;
  atlasState.mock.greetingShown = true;
}

export async function unmount(root) {
  // Nothing to clean up.
}
