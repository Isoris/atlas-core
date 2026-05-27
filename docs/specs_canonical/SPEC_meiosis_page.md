# SPEC — relatedness-atlas `meiosis` page

**Status**: scaffold; **overlaps with [meiosis-atlas](../../meiosis-atlas/SPECS.md)**.
Reconciliation decision pending — see [SPECS.md §"Architecture note"](../SPECS.md).

**Scaffolded in:** [`atlases/relatedness/pages/hub/meiosis.html`](../atlases/relatedness/pages/hub/meiosis.html) + `meiosis.js`.

---

## 1. Goal

Per the manifest tooltip: "Meiotic crossover observables. Single CO (r1,
r2), double CO (r12), coefficient of coincidence C, interference
I = 1 − C." Plus a documented d / x identifiability limitation: from
offspring genotype data alone, the precondition probability d and
exchange probability x are not separable. Per-inversion-carrier CO
frequency is a stub until a per-individual CO call layer arrives.

## 2. The overlap

This page predates the meiosis-atlas. Its content maps directly to:

- [meiosis-atlas `crossovers` page](../../meiosis-atlas/specs_todo/SPEC_crossovers_page.md) — CO observables (r1, r2, r12)
- [meiosis-atlas `interchromosomal` page](../../meiosis-atlas/specs_todo/SPEC_interchromosomal_page.md) — coefficient of coincidence C
- Eligibility / resolution discussion below also maps to `crossovers` karyo-strat view

The relatedness-atlas's lead question is `mendelian_qc_on_LG28_candidate`;
meiosis observables belong under meiosis-atlas's lead question
`inversion_effect_on_meiosis_per_chromosome`.

## 3. Recommendation: DELETE from relatedness-atlas

Three options were considered (per [SPECS.md §"Architecture note"](../SPECS.md)):

1. **DELETE** — remove the page, point users to `#/meiosis/crossovers`. ← **recommended**
2. **Keep as proxy** — embed meiosis-atlas's `crossovers` via iframe or a shared module
3. **Keep both** — accept the duplication; manually keep them in sync

Option 1 is cleanest. The "evidence hub" UX value (everything reachable
from one atlas) is mostly lost the moment the user has to switch atlases
anyway (the meiosis-atlas already exists). The cost of maintaining the
duplicate is permanent.

Per option 1:
1. Remove the page entry from `atlases/relatedness/manifest.json`.
2. Delete `atlases/relatedness/pages/hub/meiosis.{html,js}` and any sibling `meiosis/` directory.
3. Drop the entry from `atlases/relatedness/registries/data/pages.registry.json`.
4. Move this SPEC to `specs_done/` with a `Removed in:` block instead of `Implemented in:`.

## 4. Counter-arguments (in case the deletion is contested)

- **Existing in-progress work** — if there are uncommitted changes here that haven't migrated to meiosis-atlas, those need to migrate first.
- **Demo / standalone use** — if the relatedness-atlas is sometimes deployed standalone (no meiosis-atlas), the page provides on-atlas access to the same content. Cheap to keep behind a feature flag.

Both are addressable; neither outweighs the maintenance cost in normal flow.

## 5. Decision required

Mark this SPEC `Decided: <DATE>` once the decision is made, then either
delete (option 1) or move to `specs_done/` with the rationale for keeping
(options 2/3).
