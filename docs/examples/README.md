# docs/examples — worked examples

Self-contained snippets that exercise atlas-core APIs end-to-end.
Open them in a browser served by `atlas_server.py`, or set the base
URL inside each demo to point at a remote server (CORS allows `null`
origin, so `file://` also works).

| File | What it shows |
|---|---|
| `layer_api_demo.html` | `core/layer_api.js` round-trips: `GET /api/layers`, `GET /api/layers/{id}`, `POST /api/actions`, `GET /api/actions/{id}`. Drop-in template for page modules that consume action-pipeline envelopes. |

## Using `layer_api_demo.html` as a template

The same five steps appear in any page that wants to consume the new
action pipeline:

```js
import {
  configureLayerApi, listLayers, getLayer, resolveLatestLayer,
  submitAction, newActionId,
} from '../../core/atlas_api.js';   // or '../core/layer_api.js' directly

// 1. (file:// only) point at the server
configureLayerApi({ baseUrl: 'http://127.0.0.1:8000' });

// 2. list envelopes
const { layers } = await listLayers({ layer_type: 'fst_windows', dataset_id });

// 3. fetch one
const env = await getLayer(layers.at(-1).layer_id);

// 4. or resolve the most-recent directly
const latest = await resolveLatestLayer('fst_windows', { dataset_id });

// 5. submit a new compute, get its produced_layers back
const res = await submitAction({
  action_id: newActionId(),
  type:      'run_popstats',
  dataset_id,
  runner:    'run_popstats',
  target:    { chrom, groups },
  params:    { stat: 'fst' },
  expected_outputs: [{ layer_type: 'fst_windows', schema_version: 'fst_windows_v1' }],
}, { atlas: 'inversion' });
```

The demo HTML is intentionally framework-free — pages can copy the
shape into their own renderer (React / lit / plain DOM) without
inheriting any dependency.
