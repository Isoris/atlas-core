# SPEC — relatedness-atlas `network` page

**Status**: shipped. Envelope-aware migration landed as commit 25 of the
toolkit_registries action-pipeline branch (per
[atlas-core/toolkit_registries/STATUS.md](../../atlas-core/toolkit_registries/STATUS.md)
§1 commit 25). 15-assertion smoke test green; wired into the umbrella as
"relatedness-atlas network page (envelope-aware)".

**Implemented in:**
- [`atlases/relatedness/pages/hub/network.html`](../atlases/relatedness/pages/hub/network.html) — extracted from legacy `Relatedness_atlas.html` §6 (lines 802–871)
- [`atlases/relatedness/pages/hub/network.js`](../atlases/relatedness/pages/hub/network.js)
- [`atlases/relatedness/pages/hub/test_network_data_source.js`](../atlases/relatedness/pages/hub/test_network_data_source.js)

---

## 1. Goal

Render the active family hub as an SVG node-link diagram, showing every
edge incident to the focal individual. Edge classes are colour-coded:

- `strong_po` — black solid (high-confidence parent-offspring)
- `possible_po` — blue solid (moderate-confidence PO)
- `ambiguous` — amber dashed (likely-related but PO direction unclear)
- `mendelian_conflict` — red dashed (incompatible with PO, flagged for review)

Clicking a node invokes `shared/pop_tree.js::selectIndividual` which
emits `'individual_changed'` on the page bus; the Inspector + sibling
pages stay in sync automatically.

The page also hosts **inline previews** of the Karyotypes table (top 5
rows) and Inversion candidates (4-row paginated table) — these reuse the
shared/karyotype_table.js renderer plus the local
`renderInversionTablesInline()` helper from `inversions.js`.

## 2. Envelope-aware data source

`mount()` probes for the latest `ngsrelate_pairs_v1` envelope:

```js
const env = await resolveLatestLayer('ngsrelate_pairs', {
  dataset_id: 'main_226_hatchery',
});
```

Result is rendered as a status badge above the SVG:

- **envelope present** — green badge: `pairs from ngsrelate run <layer_id> · N pairs · created_at`
- **envelope absent** (empty `layers` list) — grey badge: `DEMO fallback — no ngsrelate_pairs_v1 envelope yet`
- **fetch error** — silently falls back to DEMO (no console noise, no thrown error)

This is the **advertise** pattern, not the **consume** pattern: the SVG
itself still reads `DEMO.network_edges` for now. Switching from advertise
→ consume is a follow-up once a relatedness threshold convention is
settled for {strong_po, possible_po, ambiguous, conflict}. The SPEC for
that decision is in `specs_todo/SPEC_relatedness_threshold_calibration.md`
(to be authored).

## 3. State + events

Mount-time hooks:
- `state.shared.activeFamily` — read; identifies the family hub to draw
- `state.shared.focalIndividual` — read; centres the layout

Event listeners:
- `'individual_changed'` — re-emit on node click; consumed by Inspector + other pages
- `'family_changed'` — re-render the whole SVG

Cleanup (in `unmount()`): detach all listeners; the page module has no
module-level state that survives unmount.

## 4. Surface

The HTML fragment expects:

```
#networkSvg            — the <svg> root for the force-directed-ish layout
#networkDataSource     — slot for the envelope status badge
#networkKaryotypesInline — slot for the inline karyotypes preview (top 5)
#networkInversionsInline — slot for the inline inversions preview (4-row)
```

`mount()` populates `#networkDataSource` first (sync after the
resolveLatestLayer await), then renders the SVG (sync), then the inline
previews. Order matters: if the SVG fails for any reason, the badge is
already painted so the user sees the data-source state regardless.

## 5. Tested paths

The 15-assertion smoke (see
[`test_network_data_source.js`](../atlases/relatedness/pages/hub/test_network_data_source.js))
covers the envelope-probe + badge-render path via mocked fetch:

- envelope present → badge advertises layer_id + n_pairs + created_at
- envelope absent (empty `layers`) → DEMO badge
- fetch error (HTTP 500) → silently falls back to DEMO
- singular/plural pair count
- title attribute carries `action_id` + `source_layer_ids` (lineage)
- null slot is a no-op (HTML scaffold may lack the badge div in early states)

SVG rendering itself is NOT tested (would need a full DOM simulation);
that's covered by manual verification at `#/relatedness/network`.

## 6. Open work

- **Switch from advertise → consume** once threshold convention lands. The current SVG reads DEMO; should read `envelope.payload.pairs` filtered to the active family hub.
- **Multi-cohort badge** — `resolveLatestLayer` returns the most-recent envelope of its type. When multiple cohorts coexist (e.g. 226 + a future macrocephalus run), the page needs a dropdown.
- **Click-to-trace** — clicking the badge could open a side panel showing the full envelope JSON (this is exactly what the [Inventory page](../../atlas-core/atlases/core/pages/inventory.html) does for any envelope; could be promoted here as a "trace this data source" button).
