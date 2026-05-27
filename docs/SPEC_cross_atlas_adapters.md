# SPEC: cross_atlas adapters

**Status:** shipped 2026-05-23 (Phase 1d).
**Owner:** atlas-core (this SPEC + the dotted-namespace lookup in `core/registry_core.js`).
**Companion docs:** [SPEC_registry_v1.md](SPEC_registry_v1.md), [SPEC_cohorts_v1.md](SPEC_cohorts_v1.md).

---

## Purpose

When the catfish workspace grew from 1 to 11 atlases, cross-atlas data sharing needed a
canonical shape. This SPEC pins down:

1. How an atlas declares **which layers it reads from other atlases** (imports).
2. How an atlas declares **which layers it publishes for others to consume** (exports).
3. How `registry.resolve(...)` actually finds a cross-atlas layer at runtime.
4. How `atlas-core/cohorts.registry.json` aggregates the full producer/consumer map.
5. How the lint script (`build/_lint_atlases.py`) enforces the contract.

The pattern is already used by all 11 non-core atlases. Future atlases follow the same
shape verbatim.

---

## 1. The `cross_atlas` block in `manifest.json`

Every atlas manifest carries a top-level `cross_atlas` field with two arrays:

```json
"cross_atlas": {
  "_doc": "One-sentence summary of this atlas's role (producer / consumer / both).",
  "imports": [
    {
      "layer":   "<producer_atlas_id>.<layer_id>",
      "from":    "<producer_atlas_id>",
      "purpose": "Why this atlas needs that layer."
    }
  ],
  "exports": [
    {
      "layer":   "<this_atlas_id>.<layer_id>",
      "used_by": ["<consumer_atlas_id>", "..."],
      "purpose": "What downstream consumers do with this layer."
    }
  ]
}
```

Conventions:

- `layer` is **always** dotted: `<atlas_id>.<layer_id>`. This is the same key that
  `registry.resolve(layer)` accepts.
- `purpose` must be one sentence. Used in `cohorts.registry.json` summaries + the
  system_health page tooltips. Don't write paragraphs.
- The `from` field is redundant with the dotted prefix, but pinned so a human can
  read imports without parsing strings.
- `used_by` is an array even when there's one consumer. Empty array (`[]`) is
  meaningful — declares the layer as "published but currently unread", which the
  system_health page surfaces as `(unused)`.

---

## 2. Required: declare the actual layer in your `layers.registry.json`

The `cross_atlas` block is **documentation + a contract**. The runtime layer must
also be declared in the producing atlas's `registries/data/layers.registry.json`,
exactly like any non-cross-atlas layer:

```json
{
  "layer_id":        "candidates_v1",
  "kind":            "tabular",
  "leaf_kind":       "tsv",
  "tier":            "warm",
  "source":          "file",
  "root":            "candidates",
  "path_under_root": "_index.json",
  "_status":         "session_state",
  "description":     "..."
}
```

The dotted prefix in `cross_atlas` (`inversion.candidates_v1`) is stripped at lookup
time — the registry indexes the bare `candidates_v1`. **The same layer name must
appear once in the producer's layers registry, never again in any consumer.**

---

## 3. Runtime: how `registry.resolve` dispatches

`core/registry_core.js::_lookup(key)` accepts three forms:

| Caller writes | What lookup uses | When to use which |
|---|---|---|
| `resolve('scrubber_main')` | `scrubber_main` (bare) | Reading a layer owned by your own atlas |
| `resolve('inversion:scrubber_main')` | `scrubber_main` (strip `:`) | Legacy form; both work, dot preferred |
| `resolve('inversion.candidates_v1')` | `candidates_v1` (strip first `.`) | **Canonical cross-atlas read** |

The lookup is namespace-stripping: prefixed forms exist only to make calling code
self-documenting. Internally everything goes to a single flat layer index.

**Implication:** layer names must be globally unique across all atlases. If two
atlases want a `candidates` layer, one of them needs a more specific name
(`inversion_candidates`, `pod_candidates`, etc.). The registry's conflict-resolution
path (`_registerKey`) catches collisions at boot — see [SPEC_registry_v1.md §11](SPEC_registry_v1.md).

---

## 4. The master index: `atlas-core/cohorts.registry.json`

Every cross_atlas export in every atlas's manifest gets a mirror entry in
`cohorts.registry.json` under `producers`:

```json
{
  "producers": {
    "inversion.candidates_v1": {
      "atlas_id": "inversion",
      "used_by":  ["evolution", "popstats", "cross-species",
                   "relatedness", "meiosis", "diversity", "population"]
    }
  }
}
```

This file is **not loaded by the shell at boot** (each atlas registers its own
layers via its manifest). It is:
- Human-readable answer to "who reads what from whom?"
- Read by the system_health page to render the cross-atlas graph.
- The lint script's source of truth for the producer→consumer map.

When you add a layer to one atlas's cross_atlas.exports, **update cohorts.registry.json
in the same commit**. The lint script will flag drift on the next run.

---

## 5. Lint: `build/_lint_atlases.py`

Run from atlas-core:

```bash
python build/_lint_atlases.py
```

The lint pass checks:

1. Every `manifest.json` parses as valid JSON (UTF-8).
2. Every page's `fragment` + `module` path exists on disk.
3. Every registry referenced from manifest exists + parses.
4. Every cross_atlas `imports[].layer` resolves to a real layer in the named producer atlas.
5. Every cross_atlas `exports[].layer` resolves to a layer this atlas actually declares.
6. Every `cohorts.registry.json` producer entry matches a real declared layer.

Exit code: non-zero if any ERROR-level finding. Warnings don't fail the run.

**Target:** zero warnings before any merge that touches a manifest, registry, or
cross_atlas block.

---

## 6. Worked example: adding a new producer→consumer edge

Scenario: meiosis-atlas wants to consume `population.ngsadmix_q` for ancestry-stratified
CO calling.

**Step 1.** Verify `population.ngsadmix_q` is declared in
[population-atlas/atlases/population/registries/data/layers.registry.json](../../population-atlas/atlases/population/registries/data/layers.registry.json):

```json
"ngsadmix_q": {
  "tier": "warm", "source": "file", "path": "data/ngsadmix/q_matrix.json",
  ...
}
```

**Step 2.** Add the import to meiosis manifest's cross_atlas.imports:

```json
{
  "layer":   "population.ngsadmix_q",
  "from":    "population",
  "purpose": "K-cluster Q-matrix for ancestry-stratified CO/NCO calls."
}
```

**Step 3.** Add `meiosis` to population's cross_atlas.exports.used_by for `ngsadmix_q`:

```json
{
  "layer":   "population.ngsadmix_q",
  "used_by": ["inversion", "popstats", "relatedness", "meiosis"],
  ...
}
```

**Step 4.** Update `atlas-core/cohorts.registry.json`:

```json
"population.ngsadmix_q": {
  "atlas_id": "population",
  "used_by":  ["inversion", "popstats", "relatedness", "meiosis"]
}
```

**Step 5.** Run `python build/_lint_atlases.py`. Expect zero findings.

**Step 6.** In meiosis page code:

```js
const Q = await registry.resolve('population.ngsadmix_q');
```

That's it. The dotted lookup strips `population.` and finds the bare `ngsadmix_q`
entry in the global layer index, which was registered when population-atlas booted.

---

## 7. Anti-patterns

- **Don't redeclare a layer in the consumer.** Each layer has exactly one home.
  Cross-atlas reads do not copy the declaration.
- **Don't invent layer names that aren't backed.** If you list
  `relatedness.pairwise_relationship_classification` in your imports but the
  relatedness registry declares only `res_pairwise`, the lint fails and the resolve
  returns `null`. Pick the existing name OR add a stub in the producer first.
- **Don't bypass the dotted prefix.** Page code that hardcodes `resolve('candidates_v1')`
  works ONLY if no other atlas declares a layer with the same bare name. Future
  collisions will silently route to the wrong producer. Always use the dotted form
  for cross-atlas reads.
- **Don't load cohorts.registry.json at boot.** It is documentation + a lint target.
  The shell builds its registry from per-atlas manifests; cohorts.registry is
  redundant runtime work.

---

## 8. Open questions / future work

- **Versioned layers.** Today the `_v1` suffix is convention, not enforced. When
  layer schemas change, we'll need a versioning policy (semantic? monotonic? alias
  layers?). See [SPEC_registry_v1.md §6](SPEC_registry_v1.md).
- **Cross-atlas operation calls.** `cross_atlas.imports` lists layers, but
  operations can also be called cross-atlas (e.g. `registry.runOperation('popstats:popstats_groupwise', args)`).
  This SPEC focuses on data; ops follow the same dotted-namespace convention but
  aren't explicitly listed in cross_atlas blocks today.
- **Cycle detection.** A → B → A would be a hard error; the lint doesn't currently
  detect cycles in the producer graph. Add a tarjan pass to `_lint_atlases.py` if
  cycles start happening.

---

## Appendix A. Production examples

Producer with many consumers ([inversion.candidates_v1](../../inversion-atlas/atlases/inversion/manifest.json)):

```json
{
  "layer":   "inversion.candidates_v1",
  "used_by": ["evolution", "popstats", "cross-species",
              "relatedness", "meiosis", "diversity", "population"],
  "purpose": "The canonical inversion candidate list. Every per-candidate operation in every atlas is keyed by candidate_id."
}
```

Consumer with many imports ([meiosis-atlas](../../meiosis-atlas/atlases/meiosis/manifest.json)):

```json
"imports": [
  { "layer": "inversion.candidates_v1",       "from": "inversion" },
  { "layer": "inversion.regime_catalogue_v1", "from": "inversion" },
  { "layer": "relatedness.res_pairwise",      "from": "relatedness" },
  { "layer": "relatedness.per_chrom_qc",      "from": "relatedness" },
  { "layer": "genome.chromosome_map",         "from": "genome" },
  { "layer": "genome.centromere_telomere",    "from": "genome" }
]
```

Method-engine producer ([popstats.groupwise_stats_v1](../../popstats-atlas/atlases/popstats/manifest.json)):

```json
{
  "layer":   "popstats.groupwise_stats_v1",
  "used_by": ["inversion", "evolution"],
  "purpose": "Group-wise pi/FST/dXY per candidate. Inversion reads it for candidate-focus card; evolution reads it as a feature for the archaeology synthesis card."
}
```
