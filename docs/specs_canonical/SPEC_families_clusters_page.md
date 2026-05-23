# SPEC — population-atlas `families & clusters` page (structure analysis)

**Status**: round-1 scaffold shipped with envelope-status annotations
(2026-05-14). Six panel slots wired; renderers pending the
MODULE_2B exports.

**Implemented in:**

| file | role |
|---|---|
| [`pages/structure/page_families_clusters.html`](../atlases/population/pages/structure/page_families_clusters.html) | 6 panel-slot mockups, each carrying `data-pa-slot=<name>` |
| [`pages/structure/page_families_clusters.js`](../atlases/population/pages/structure/page_families_clusters.js) | mount + envelope-status annotator via `listLayers + getLayer` fan-out |

---

## 1. The biological question

> What's the **population structure** of the 226-fish cohort? Two-round
> design — full 226 then NAToRA-pruned 81 — across NGSadmix, ngsRelate,
> PCAngsd, evalAdmix, and family-tree clustering. Cross-validates the
> "1 hatchery cohort vs many" question.

This is the **most data-dense page** in the atlas. Six panels, four
file-backed layers, two HTTP-shim slots.

## 2. Data input — six panel slots

| slot | adapter | producer |
|---|---|---|
| `ngsadmix_q_round1` | `harvest_file → ngsadmix_q_v1` OR `import_ngsadmix_q` (staging) | MODULE_2B NGSadmix all-226 |
| `ngsadmix_q_round2` | same shape, separate envelopes | MODULE_2B NGSadmix pruned-81 |
| `ngsrelate_kinship` | `import_slot → staging_population_slot_v0` (filter payload.slot) | ngsRelate Stage 2 |
| `pcangsd_pca` | `import_slot → staging_population_slot_v0` (filter payload.slot) | PCAngsd genome-wide |
| `natora` | not yet wired (no action) | NAToRA + ngsRelate matrix |
| `evaladmix` | not yet wired (no action) | evalAdmix residuals |

The slot ↔ layer mapping is encoded in `_SLOT_LAYER_MAPPING` in
`page_families_clusters.js`. Slots with `mapping: null` advertise
"no action wired" in the foot text.

## 3. Six planned panels

| # | panel | round | grain |
|---|---|---|---|
| 1 | NGSadmix Q-bar plot — round 1 | all 226 | K=2..12 stacked bars, sorted by dominant Q |
| 2 | NGSadmix Q-bar plot — round 2 | pruned 81 | same K range, cleaner signal |
| 3 | Kinship heatmap | all 226 | pairwise π̂, broodline-annotated |
| 4 | NAToRA pruning diagram | all 226 | Hungarian graph, kept/removed nodes |
| 5 | PCAngsd PCA scatter | all 226 | PC1 × PC2 colored by family + broodline |
| 6 | evalAdmix residuals | all 226 | per-K residual heatmap |

## 4. The list+get fan-out pattern

Envelope filtering by `payload.slot` (when `layer_type` alone is too
coarse — multiple slots share the `population_slot` envelope type):

```
1. listLayers({ layer_type: 'population_slot', stage: 'staging', limit: 200 })
2. Promise.all per envelope:
     env = getLayer(row.layer_id)
     if (env.payload.slot === <wanted>) keep
3. Sort kept envelopes by created_at descending → most-recent wins
```

The list-then-get fan-out was parallelized 2026-05-20 (was sequential;
slow on 200-envelope indexes).

## 5. Round1 vs round2 ngsadmix discriminator

**Known limitation**: `ngsadmix_q_round1` and `ngsadmix_q_round2`
currently probe the SAME `layer_type='ngsadmix_q'` with no payload
filter — they show the SAME envelope count. The foot text flags this
explicitly: "(combined count — round1 + round2 share layer_type)".

**v2 fix**: extend the staging envelope payload with `payload.cohort
∈ {'all226', 'pruned81'}` so the fan-out can discriminate. Requires a
producer-side change.

## 6. State + interaction

- `state.shared.activeQK` — K dropdown selection; consumed by samples
  page for the `ancestry_Q_top` column
- `state.shared.activeSample` — read; row click on NGSadmix bar
  highlights the sample

## 7. Failure modes

| # | condition | behaviour |
|---|---|---|
| 7.1 | No envelopes for any slot | every panel shows `◌ N captures (run …)` foot text |
| 7.2 | Some `getLayer` calls fail | partial fan-out; failures silently dropped |
| 7.3 | NGSadmix Q-vector wrong K | panel logs "expected K=8, got K=N" + skips render |
| 7.4 | Kinship matrix sample-id mismatch with cohort | drop unknown rows; warn |
| 7.5 | NAToRA / evalAdmix not wired | panel-foot reads "no action wired" |

## 8. Cross-page links

- K dropdown → `state.shared.activeQK` → samples page ancestry column
- PCA dot click → `state.shared.activeSample` → samples / breeding row scope
- "Open in Inversion Atlas" callout (genome-wide PC1×PC2 reuses the same dots)

## 9. UI surface

```
┌────────────────────────────────────────────────────────────────────┐
│ Panel grid (2×3):                                                  │
│                                                                    │
│  ┌─ NGSadmix Q-bars round 1 ┐  ┌─ NGSadmix Q-bars round 2 ┐       │
│  │ K=2..12 stacked          │  │ K=2..12 stacked, pruned   │       │
│  └──────────────────────────┘  └───────────────────────────┘       │
│  ┌─ Kinship heatmap        ┐  ┌─ NAToRA pruning diagram  ┐        │
│  │ pairwise π̂              │  │ Hungarian graph           │        │
│  └──────────────────────────┘  └───────────────────────────┘       │
│  ┌─ PCAngsd PCA            ┐  ┌─ evalAdmix residuals     ┐        │
│  │ PC1×PC2 colored          │  │ per-K residual heatmap    │        │
│  └──────────────────────────┘  └───────────────────────────┘       │
└────────────────────────────────────────────────────────────────────┘
```

Per-panel foot: envelope-provenance line (●/○/◌ + count + latest).

## 10. Promotion criteria

| criterion | v1 | v2 |
|---|---|---|
| Static scaffold renders | ✓ | ✓ |
| Envelope-status annotator (per panel) | ✓ | ✓ |
| Parallel fan-out for `getLayer` | ✓ | ✓ |
| NGSadmix Q-bar renderer | ✗ | required |
| Kinship heatmap renderer | ✗ | required |
| PCAngsd PCA scatter | ✗ | required |
| `payload.cohort` round1/round2 discriminator | ✗ | required (producer-side) |
| NAToRA pruning diagram | ✗ | required |
| evalAdmix residual heatmap | ✗ | required |
| Family-tree clustering view | ✗ | future (round 3) |

## 11. Open questions

- **Best-K selection**: today's mockup shows K=2..12 stacked. v2
  needs a "best-K" highlight (CV-min or biological-prior driven).
- **Family vs cluster**: NGSadmix clusters and ngsRelate families are
  different signals; should we show them side-by-side as a 2-column
  matrix per sample?
