# SPEC — Mode-B pattern: cross-checking carved data against the registry

**Audience**: anyone adding a Mode-B probe to a new atlas page, debugging a
drifting badge, or adding a new probe.

**Status**: shipped 2026-05-20. 18 pages wired across 6 atlases. Helper +
event bus + CSS + tally all live in `atlas-core/core/` and `atlas-core/css/`.

**TL;DR.** Each page renders from one primary data source (a manuscript carve,
a precomp JSON cached in `AtlasState`, demo data). The same data is *also*
reachable through `registry.resolve()` — an independent path through the layer
registry. A "Mode-B probe" calls the registry path at mount time, compares
the result to the page's primary source via a small comparator callback, and
renders a single-line badge above the page content showing whether the two
agree (`●` live), disagree (`⚠` drift), or whether the registry path is
empty (`○` data pending / unavailable). 

---

## 1. Why this exists

Atlases ship two different ways of looking at the same numbers:

| Mode | Source | Pros | Cons |
|---|---|---|---|
| **A** | manuscript carve / precomp JSON cached in `AtlasState` / demo data baked in `shared/demo_data.js` | fast, offline-capable, the page renders from it today | drifts silently when upstream pipeline regenerates the source |
| **B** | `registry.resolve('layer_key', args)` → master_config root → static mount → typed payload | always current, validates the registry config end-to-end, surfaces pipeline-driven changes | can be empty (stub on disk), slower (no cache warmup) |

Before this pattern, only Mode A was visible. A reviewer looking at the page
had no signal whether the registry path agreed with what they were seeing, or
whether a pipeline rerun had silently changed the numbers under them. The
common failure mode was "the carve is two months stale and nobody noticed
until the manuscript reviewer flagged it".

Mode-B is a *cross-check probe*, not a data source. The page renders from
Mode A regardless — the badge is additive provenance.

---

## 2. Three-state vocabulary

The badge text always starts with one of three glyphs:

| Glyph | State | When | CSS class |
|---|---|---|---|
| **`●`** | **live** | registry resolved + comparator says shape agrees | `.data-source-badge.live` |
| **`⚠`** | **drift** | resolved but comparator says shape disagrees with the carve | `.data-source-badge.demo` |
| **`○`** | **stub** or **missing** | payload empty (`stub-payload`) or fetch failed (`registry-not-injected`, `empty-result`, `resolve-threw`) | `.data-source-badge.demo` |

The tally chip in the top chrome collapses `stub` + `missing` into one count
since both mean "no useful data today" — a tooltip on the chip breaks them
apart for debugging.

---

## 3. File map

| File | Role |
|---|---|
| [`core/mode_b_badge.js`](../../core/mode_b_badge.js) | Canonical helper. Exports `probeModeB`, `renderModeBBadge`, `medianOf`, `meanOf`, `distinctCount`, `relDiff`. ~190 LOC. |
| [`css/badges.css`](../../css/badges.css) | Style for `.data-source-badge` (per-page slot) + `.mode-b-card` (expanded card). Uses tokens `--ink-dim` / `--panel-2` / `--rule` from `tokens.css`. |
| [`index.html`](../../index.html) | Loads `badges.css`. |

Per-atlas pages declare ONLY the badge slot (`<div id="..." class="data-source-badge">`)
and call `probeModeB` + `renderModeBBadge` from their `mount()`. No per-atlas
helper. No per-atlas CSS.

---

## 4. Helper API

### `probeModeB(registry, layerKey, args, opts) → Promise<probeResult>`

Resolves a layer through the registry. Never throws. Always returns:

```js
// Success
{ ok: true, rows, payload, n, sample_keys }
// Failure
{ ok: false, reason, error?, payload? }
```

`reason` ∈ `'registry-not-injected'` | `'empty-result'` | `'stub-payload'` | `'resolve-threw'`.

`opts.extractRows(payload) => Array | null` lets callers project a sub-array
out of an object payload. Default: pass through arrays, reject anything else
(matching the shape `format: tsv` layers produce via `parseDelimited`).

Three common extractor patterns:

```js
// JSON payload with an obvious primary array
extractRows: (p) => (p && Array.isArray(p.per_sample)) ? p.per_sample : null

// Map → entries (e.g. candidate_lineage.versions = { v_id: meta })
extractRows: (p) => {
  if (!p || !p.versions) return null;
  return Object.entries(p.versions).map(([id, meta]) => ({ version_id: id, ...meta }));
}

// Multi-key fallback (loaders haven't standardised yet)
extractRows: (p) => {
  if (!p) return null;
  if (Array.isArray(p.rows))    return p.rows;
  if (Array.isArray(p.samples)) return p.samples;
  return null;
}
```

### `renderModeBBadge(slotId, probeResult, opts) → void`

Renders the probe result into `document.getElementById(slotId)`. No-op when
the slot is missing (browser-less test mode, deferred-mount race).

`opts`:

| Key | Type | Purpose |
|---|---|---|
| `label` | string | Short layer name shown in the badge text. *Required.* |
| `layerKey` | string | Logged in the tooltip. Recommended. |
| `context` | string | Scope tag (chrom / candidate id / version id) appended after the label. Surfaces multi-scope debugging. |
| `compare` | `(probeResult) => { pass, summary }` | Comparator. `pass=false` → ⚠ drift. Omit → generic `(N rows resolved)` summary. |
| `provenance` | `ctx.PROVENANCE` block from a data_loader | Appends `— vs carve: <version> · sha <hash>` to the tooltip. Diversity-only today; other atlases stamp on demand. |

### Statistic helpers

```js
medianOf(rows, ...keys)    // first non-null numeric across keys[]
meanOf(rows, ...keys)
distinctCount(rows, key)   // Set-based unique count
relDiff(observed, baseline) // abs((o - b) / b); null on bad inputs
```

Helpers exist because the same 4 operations appear in ~12 of the 18 wired
comparators. Adding a 5th helper that's only used once is the wrong tradeoff.

---

## 5. Page-side authoring guide

### 5.1 HTML slot

Page HTML declares one container per badge:

```html
<div id="myPageModeBBadge" class="data-source-badge"></div>
```

That's it. `badges.css` provides the baseline style. Per-page overrides go
inline only when meaningfully different from the default (`margin`,
`display: none`):

```html
<!-- inversion pages have chrome-padded margins -->
<div id="lpdModeBBadge" class="data-source-badge" style="margin: 4px 8px;"></div>

<!-- candidate-keyed pages start hidden, revealed when a candidate is selected -->
<div id="cfModeBBadge" class="data-source-badge" style="margin: 4px 8px; display: none;"></div>
```

### 5.2 JS wiring

In the page module:

```js
import { probeModeB, renderModeBBadge } from '../../../../core/mode_b_badge.js';

export async function mount(root, atlasState, registry) {
  // ... existing mount work ...

  // Mode-B probe — non-blocking, fail-soft.
  _renderMyBadge(atlasState, registry).catch((e) => {
    console.warn('myPage.mount: badge probe threw —', e);
  });
}

async function _renderMyBadge(atlasState, registry) {
  const slot = document.getElementById('myPageModeBBadge');
  if (!slot) return;

  // Optional: hide when no scope selected
  const scope = atlasState?.shared?.activeChrom;   // or activeCandidate, etc.
  if (!scope) { slot.style.display = 'none'; return; }
  slot.style.display = 'block';

  const probe = await probeModeB(registry, 'my_layer_key', { chrom: scope });
  renderModeBBadge('myPageModeBBadge', probe, {
    label:    'short name',           // shown in badge text
    layerKey: 'my_layer_key',         // shown in tooltip
    context:  scope,                  // scope chip in badge text
    compare:  (probeResult) => ({
      pass: probeResult.n > 0 && /* whatever shape agreement check */,
      summary: `${probeResult.n} X · derived stat Y`,
    }),
    provenance: ctx.PROVENANCE,       // optional — only if data_loader exposes it
  });
}
```

The probe runs after the synchronous render — the page stays interactive
regardless of registry/network latency. The badge updates when the probe
resolves.

### 5.3 Conventional probe shapes

Three patterns cover all 18 callsites:

**Single-layer probe** (most pages — samples, hotspots, network, …):
```js
const probe = await probeModeB(registry, 'foo', args);
renderModeBBadge(slotId, probe, { label, layerKey, compare });
```

**Parallel primary + optional** (texture, crossovers_per_candidate, karyotypes):
```js
const [primaryProbe, optProbe] = await Promise.all([
  probeModeB(registry, 'primary', args, { extractRows: ... }),
  probeModeB(registry, 'optional', args, { extractRows: ... }),
]);
const optTag = optProbe.ok ? `opt N=${optProbe.n}` : 'opt: data pending';
renderModeBBadge(slotId, primaryProbe, {
  label, layerKey: 'primary', context, compare: (r) => ({
    pass: ..., summary: `${r.n} primary rows · ${optTag}`,
  }),
});
```

**Chained probe** (boundary_refinement — lineage drives the second probe's args):
```js
const lineageProbe = await probeModeB(registry, 'candidate_lineage', { candidate_id });
if (!lineageProbe.ok) { renderModeBBadge(...); return; }
const active = lineageProbe.payload.active_version_id;
const boundsProbe = await probeModeB(registry, 'candidate_boundaries',
  { candidate_id, version_id: active });
renderModeBBadge(slotId, boundsProbe, { ... });
```

**N-axis parallel** (pca_comparator — 3 independent axes, custom verdict):
```js
const results = await Promise.all(axes.map(a =>
  registry.resolve(a.layer, { chrom }).then(p => ({ axis: a.id, n: p?.windows?.length || 0 }))
                                       .catch(() => ({ axis: a.id, n: 0 }))));
const loaded = results.filter(r => r.n > 0);
const pass = loaded.length === axes.length && new Set(loaded.map(r => r.n)).size === 1;
// hand-construct the probeResult shape and call renderModeBBadge
```

---

## 6. The 18 wired pages

Reference for the cookbook (each pattern shows up at least twice):

| Atlas | Page | Probe target | Pattern |
|---|---|---|---|
| diversity | `samples` | `samples_genomewide_het` | single + provenance |
| diversity | `chromosomes` | `samples_theta_pi_pestpg` @ CGA009/500kb | single, scope-templated |
| diversity | `hotspots` | `samples_theta_pi_pestpg` @ CGA009/10kb | single, fine-scale variant |
| diversity | `ancestry` | `ancestry_het_kruskal_all` | single, K-sweep aggregate |
| diversity | `pruning_qc` | `ancestry_het_pruned81_samples` | single, cross-checks D.S11 overlap |
| diversity | `texture` | `texture_metrics_payload` | extractRows: per_sample[] |
| diversity | `burden` | `functional_burden_payload` | extractRows: per_sample[] + cohort flags |
| diversity | `divergence` | `divergence_network_payload` | extractRows: edges[] |
| inversion | `local_pca_dosage` | in-hand `data` | hand-constructed probeResult (already-resolved) |
| inversion | `candidate_focus` | `candidate_lineage` | extractRows: versions map → entries |
| inversion | `boundary_refinement` | `candidate_lineage` + `candidate_boundaries` | chained (lineage → active_version → bounds) |
| inversion | `pca_comparator` | 3× `scrubber_*` | N-axis parallel, hand-rolled |
| meiosis | `crossovers_per_candidate` | `crossover_track` + `prdm9_motif` | parallel primary + optional |
| meiosis | `nco_per_candidate` | `nco_gc_track` | single, kind-split (nco/gc) |
| relatedness | `network` | `res_pairwise` | single, class-distribution chips |
| relatedness | `karyotypes` | `inversion_karyotypes` + `ancestry_q` | parallel primary + optional |
| genome | `page_assembly_stats` | `assembly_stats` | single, payload globals |
| population | `page1 (qc)` | `per_sample_stats` | single, column-group detection |

---

## 7. CSS tokens consumed

| Token | Used for | Defined in |
|---|---|---|
| `--ink-dim` | badge + chip text colour | `tokens.css` (all 3 themes) |
| `--panel-2` | badge + chip background | `tokens.css` (all 3 themes) |
| `--rule` | badge left border + chip outline | `tokens.css` (all 3 themes) |

The two glyph-tone colours (`#3cc08a` for `●` live, `#f5a524` for `⚠` drift)
are hardcoded in `badges.css` rather than tokenised — they match the
inversion-atlas `pca_comparator` concordance badge's existing palette and
should stay in sync with it.

---

## 8. Adding a new wired page (checklist)

1. **HTML**: insert `<div id="<page>ModeBBadge" class="data-source-badge"></div>`
   above the first content card.
2. **JS imports**: `import { probeModeB, renderModeBBadge } from '../../../../core/mode_b_badge.js';`
3. **Helper function**: `async function _render<Page>Badge(atlasState, registry) { ... }`
   following one of the four patterns in §5.3.
4. **mount() call**: append `_render<Page>Badge(atlasState, registry).catch(...)`
   AFTER the existing synchronous render. Non-blocking.
5. **Verify**: balance check (`python3 -c "..."`), then if the atlas has a
   smoke test, run it.

Onboarding cost is **1 import line + 1 helper function + 1 mount call** —
deliberately the same shape across all 18 callsites so the pattern stays
greppable.

---

## 9. Failure modes seen in the wild

| Symptom | Likely cause | Fix |
|---|---|---|
| `○ registry-not-injected` on every page | Shell not passing `registry` as 3rd `mount()` arg | Should not happen — `atlas_router.js:114` does this. If observed, atlas-core regression. |
| `○ empty-result` on a `format: tsv` layer | Static mount unreachable, or `parseDelimited` skipped the header | Check `master_config.yaml` root + first-line `#` prefix (see [`extractors/pestpg.py` history](../../../diversity-atlas/atlases/diversity/registries/extractors/pestpg.py) — same bug class on the Python side, fixed in turn 2026-05-20). |
| `○ stub-payload` on an optional payload | File exists but empty `{}` — round-1 stub state | Expected today; auto-flips to `●` when upstream pipeline writes a real payload. |
| `⚠` even though carve looks right | Comparator's pass condition is too strict | Loosen the threshold (`< 0.01` → `< 0.05`), or surface a soft `summary` without flipping `pass: false`. The badge is provenance, not validation gate. |

---

## 10. Future work

Not blocking any current round. Listed so a future session knows the obvious
gaps:

1. **Manifest-declared probes**. Each page currently embeds its probe target
   in `mount()`. Promoting to `manifest.json` per-page (e.g.
   `"mode_b_probe": { "layerKey": "samples_genomewide_het" }`) would let
   the chrome surface coverage stats without needing each page to mount
   first. ~30 min to refactor 18 callsites.
2. **CI report**. A headless run could emit "this branch adds 2 ●, breaks 1
   from ● → ⚠" to the PR description. Useful at the 50+ page coverage mark.
3. **Promote the green/orange glyph colours** to tokens. Currently
   hardcoded in `badges.css`; should match the inversion `pca_comparator`
   concord badge's palette if either ever changes.
---

## 11. Provenance

| | |
|---|---|
| Pattern shipped | 2026-05-20 |
| First atlas | diversity-atlas (`samples` page) |
| Promoted to atlas-core/core | 2026-05-20 (third-use threshold met by inversion-atlas) |
| Authors | Quentin Andres (architecture) + Claude (implementation) |
| Reference smoke test | [`atlases/diversity/pages/per_sample/test_samples_modeb.js`](../../../diversity-atlas/atlases/diversity/pages/per_sample/test_samples_modeb.js) — 10 cases including a real-disk variant |
