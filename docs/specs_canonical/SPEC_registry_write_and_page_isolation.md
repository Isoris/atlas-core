# SPEC — Page-isolation principle (companion to SPEC_registry_v2)

**Status**: shipped 2026-05-20 (audit-sweep — the SPEC is a companion
doc to `SPEC_registry_v2.md`, not a half-shipped feature SPEC; both
halves are accounted for elsewhere). Promoted from `specs_todo/` after
the per-slice audit below. Original SPEC body is preserved verbatim
below as design archive.

**Implemented in:**
- **Page-isolation discipline** (this SPEC's atlas-side scope) — enforced at the source level: cross-page imports (`from '../<other-page>/'`) are zero across the `atlases/inversion/pages/` tree. Audited 2026-05-20 by `grep -rEn "from '[\./]*pages/" atlases/inversion/pages/` → empty result. The discipline is preserved by code review + the no-grep-result smoke check; no runtime enforcement is needed because the violation is detected at refactor time.
- **Registry.write semantics + writable-layer flag + server transport + schema validation + cache invalidation** (the SPEC's other half, explicitly deferred to the canonical reference) — see [`specs_done/SPEC_registry_v2.md`](SPEC_registry_v2.md)
- Cartridge-side registry config: [`atlases/inversion/registries/data/*.registry.json`](../atlases/inversion/registries/data/) — declares `writable: true` on per-candidate / lineage-index layers per the v2 contract

**Per-slice status:**

| slice | status | location |
|---|---|---|
| Page-isolation discipline (zero cross-page imports) | ✅ shipped | Commit `4e695f7`; audit-confirmed 2026-05-20 by re-grep |
| Registry.write contract semantics | ✅ shipped via reference | `specs_done/SPEC_registry_v2.md` (canonical design) |
| `writable: true` layer flag | ✅ shipped via reference | Same |
| Server transport for writes | ✅ shipped via reference | Same |
| Schema validation on write | ✅ shipped via reference | Same |
| Cache invalidation on write | ✅ shipped via reference | Same |

**Why archived now:** this SPEC is *structurally* not a deferred-work
SPEC — it's a companion design doc. It explicitly says (line 13–15) "the
canonical reference is `specs_done/SPEC_registry_v2.md`. Read that
first." The page-isolation discipline it adds (cartridge-side rule:
pages may not import from each other) is enforced by commit `4e695f7`
and verified empty by `grep`. There is no "pending half" — the
Registry.write contract was *always* meant to live in
`SPEC_registry_v2.md`, and that doc is already in `specs_done/`.

The old `specs_todo/README.md` status "HALF SHIPPED" was a
mis-categorisation arising from reading the SPEC as parallel-to v2
rather than companion-to v2. The audit-sweep corrects this.

**Filed:** 2026-05-12.

---

## The principle (Quentin's framing)

> "Most things you need to write them to some registry IDB or yeah to a
> file, but not wire internally."

In the legacy single-HTML-file architecture, cross-page state lived in
one global `state` object + `localStorage` + `IndexedDB`. Pages shared
JavaScript closures because there was only one tab, one script context.

In the new architecture (`atlas-workspace = atlas-core + cartridge`),
pages are mounted independently by `atlas_router` and the **Registry**
is the system of record for anything multiple pages need to agree on.
Pages should:

- Read state via `registry.resolve(layer, params)` (✅ already wired)
- Write state via `registry.write(layer, key, value)` (❌ not built yet)
- **Never reach into another page's module to fetch state** — that's
  the legacy global-state pattern in disguise.

## What "wired internally" means (anti-patterns to avoid)

```
// ❌ candidate_focus/_list.js → local_pca_dosage/inheritance.js
import { isAutoCandidate } from '../local_pca_dosage/inheritance.js';

// ❌ page22.js → local_pca_dosage/_state.js
import { _setActiveState as _setPage1ActiveState } from './local_pca_dosage/_state.js';

// ❌ candidate_focus/_html_builders.js → candidate_focus.js's runtime state
const cand = state.candidates[id];   // reading another page's _pageState
```

What's allowed:

```
// ✅ Pure compute / predicates live in shared/
import { isAutoCandidate } from '../../../shared/candidate_predicates.js';

// ✅ Persistence helpers wrap localStorage / IDB / (future) registry
import { persistActiveCandidateId } from '../../../shared/active_candidate.js';

// ✅ Within-page imports (local_pca_dosage/lines_panel.js → local_pca_dosage/z_panel.js) are fine
import { drawZ } from './z_panel.js';
```

## The persistence layer

Today, the cartridge can only persist through browser primitives:

| State              | Mechanism today                     | Future (Registry.write())                     |
|--------------------|-------------------------------------|-----------------------------------------------|
| activeCandidateId  | localStorage (shared/active_candidate.js) | `registry.write('state/activeCandidateId', id)` |
| candidateList      | (in-memory only, not persisted)     | `registry.write('inversion/candidateList', list)` |
| bandTraceFishSet   | localStorage (local_pca_dosage/band_trace_state.js) | `registry.write('inversion/bandTrace/fishSet', set)` |
| bandTraceOn        | localStorage                        | `registry.write('inversion/bandTrace/on', bool)` |
| l2SweepDismissed   | localStorage (per-chrom)            | `registry.write('inversion/l2sweep/dismissed/<chrom>', set)` |
| activeSampleSet    | localStorage (shared/active_samples? actually local_pca_dosage/active_samples.js) | `registry.write('inversion/activeSamples', set)` |
| chromCache         | IndexedDB (local_pca_dosage/idb.js)            | `registry.write('inversion/chromCache/<chrom>', data)` |
| enrichments        | IndexedDB                           | `registry.write('inversion/enrichments/<name>', data)` |
| inheritanceResult  | (in-memory, recomputed per session) | possibly cache via registry.write for slow cases |
| lineageResult      | (in-memory, recomputed per session) | possibly cache via registry.write for slow cases |

**The helper modules I've extracted already isolate the persistence
calls.** Every page calls through a helper, not `localStorage.setItem`
directly. So when `Registry.write()` ships, the swap is one-line per
helper. The call sites don't change.

## Page-isolation contract

When a future round picks up a new feature, the checklist is:

1. **Does it cross page boundaries?** If yes, the state goes through
   the persistence layer (helper module wrapping localStorage / IDB /
   registry). Page A writes; page B reads. No direct imports.
2. **Is it pure compute?** Put it in `shared/`. Anything page-shaped
   that doesn't need state goes there.
3. **Is it page-local?** Keep it under `pages/<stage>/<page>/`. Other
   pages don't import from it.
4. **Is it DOM-bound but generic?** Headless-tolerant helpers go in
   `shared/` too (e.g. an SVG builder, a tooltip positioner). Page-
   specific renderers stay under the page.

## Registry.write() — see SPEC_registry_v2

The full contract — signature `registry.write(key, args, payload)`,
`writable: true` flag on layer entries, path templating, schema
validation before send, `POST /file/{path:path}` transport, cache
invalidation on success, transitive invalidation on candidate_change
— is specified in `specs_done/SPEC_registry_v2.md` items 4 + 5.
Don't duplicate it here.

The signature I sketched in an earlier revision of this file
(`registry.write(layerName, key, value)` with broadcast / subscribe)
was not aligned with SPEC_v2. The canonical surface is:

```
registry.resolve(key, args)        — read cached/fresh
registry.write(key, args, payload) — write through to canonical store
registry.invalidate(key, args)     — drop one cache entry
registry.invalidateAllForCandidate(cid) — drop all candidate-scoped entries
```

No `subscribe`, no `BroadcastChannel`. SPEC_v2 §11 explicitly rules
those out for v2.

## Acceptance criteria (cartridge half)

The page-isolation half is **already met** in the cartridge as of
commit `4e695f7`:

- [x] No page module imports from another page module. Cross-page
      state flows exclusively through `shared/` (pure compute /
      predicates) and persistence helpers (localStorage / IDB).
- [x] Audit grep `from '\.\./page[0-9]'` in
      `atlases/inversion/pages/` returns zero hits.
- [x] Audit grep `from '\./local_pca_dosage/'` in
      `atlases/inversion/pages/` (excluding `local_pca_dosage.js` itself) returns
      zero hits.

The Registry.write half (depends on atlas-core changes per SPEC_v2):

- [ ] `registry.write(key, args, payload)` exists in
      `core/registry_core.js` per SPEC_v2 §5
- [ ] `registry.invalidateAllForCandidate(cid)` exists per SPEC_v2 §6
- [ ] Server-side path allowlist on `POST /file/{path}` per SPEC_v2 §9
- [ ] Every existing `persist*` helper (`shared/active_candidate.js`,
      `local_pca_dosage/idb.js`, `local_pca_dosage/band_trace_state.js`, `local_pca_dosage/l2_sweep.js`,
      `local_pca_dosage/active_samples.js`) gets a one-line swap from localStorage
      / IDB to `registry.write`. The call signatures I built were
      designed for this swap — each helper takes the same arguments
      `registry.write` will need, so the change is mechanical per
      module.

## What this SPEC does NOT say

- It doesn't dictate that EVERY state has to go through the server.
  Cursor position, hover state, mousedrag state — those are inherently
  per-page and stay in `_pageState`. The principle applies to state
  that needs to *survive page reloads* or *be visible to other pages*.
- It doesn't require deleting the localStorage / IDB helpers. They
  stay as the fallback when the server is unreachable. Registry.write
  should use them as its local-cache tier.
- It doesn't block any in-flight extraction work. The pattern I've
  established (small helper per persistence concern + page imports
  the helper) is exactly what makes the eventual swap mechanical.
