# SPEC — population-atlas `QC` page (per-sample QC inventory)

**Status**: round-1 scaffold shipped (2026-05-11). Round-2 wires the
coverage histogram + missingness-vs-coverage scatter from MODULE_QC and
exposes a "recompute QC" action.

**Implemented in:**

| file | role |
|---|---|
| [`pages/qc/page_qc.html`](../atlases/population/pages/qc/page_qc.html) | scaffold with QC threshold grid + planned-panels grid |
| [`pages/qc/page_qc.js`](../atlases/population/pages/qc/page_qc.js) | mount lifecycle (no-op render today) |

---

## 1. The biological question

> Per sample, **does this fish pass the QC bar to enter cohort-wide
> analyses?** Coverage, callable fraction, missingness, contamination,
> BEAGLE genotype confidence, and pruning status — green/yellow/red.

This is the **gatekeeper page**: failing QC here propagates a hint
("excluded from default analyses") to every sibling page.

## 2. Data input

**v1 today** (scaffold):
- Threshold grid is hard-coded HTML; no live data.

**v2 target**:
- **HTTP-shim**: `GET /api/population/module_qc_summary`
- **File-backed**: `data/qc/module_qc_summary.json` →
  [`module_qc_summary_v1`](../atlases/population/registries/schemas/schema_out/module_qc_summary_v1.schema.json)

## 3. QC threshold grid (cohort-wide config)

| metric | threshold | tool | doc |
|---|---|---|---|
| mean_coverage | ≥ 5× | samtools depth | manuscript §M.2 |
| callable_fraction | ≥ 0.80 | mosdepth | §M.2 |
| missingness | ≤ 0.10 | ANGSD `-doCounts` | §M.2 |
| FREEMIX | ≤ 0.03 | VerifyBamID2 | §M.2 |
| CHIPMIX | ≤ 0.03 | VerifyBamID2 | §M.2 |
| BEAGLE_GP_mean | ≥ 0.90 | BEAGLE | §M.2 |
| natora_kept | bool | NAToRA | §M.2 |

Thresholds editable in v2 via a JSON config payload; recompute action
re-derives `qc_pass` per sample using the user's overrides.

## 4. Planned panels (v2)

| panel | data | renderer |
|---|---|---|
| Coverage histogram | `mean_coverage[]` | inline SVG |
| Missingness × coverage scatter | `(missingness, mean_coverage)` per sample | inline SVG |
| Contamination scatter | `(FREEMIX, CHIPMIX)` per sample | inline SVG |
| QC pass/fail summary | `count(qc_pass)` × `{pass, warn, fail}` | summary chips |
| Per-sample QC inventory table | one row per sample | sortable table |

Row click → drill-down side panel with all threshold-vs-actual cells
for that sample (highlighted in red where the threshold was violated).

## 5. "Recompute QC" action

User edits thresholds inline → click "recompute" → posts
`actions_submit` manifest with `action_type='recompute_qc'` → polls
`actions_status` until the produced `module_qc_summary` layer
re-resolves. Threshold config persisted in localStorage so the user's
preferences survive reloads.

## 6. State + interaction

- `state.shared.activeSample` — set on row click; routes sibling pages
- `state.population.qcThresholds` — local override of the v2 default
  threshold grid; consumed by the recompute action

## 7. Failure modes

| # | condition | behaviour |
|---|---|---|
| 7.1 | No layer loaded | scaffold render |
| 7.2 | Recompute action fails | error chip in toolbar + log; thresholds revert |
| 7.3 | Per-metric column missing in payload | column blank; sortable still works |
| 7.4 | All samples fail QC | full-red panel hint "check thresholds" |

## 8. Cross-page links

- Row click → `state.shared.activeSample`
- `qc_pass = fail` propagates as a samples-page row stripe red

## 9. Promotion criteria

| criterion | v1 | v2 |
|---|---|---|
| Static scaffold renders | ✓ | ✓ |
| QC threshold grid editable | ✗ | required |
| Coverage histogram | ✗ | required |
| Missingness × coverage scatter | ✗ | required |
| Per-sample QC inventory table | ✗ | required |
| Recompute QC action | ✗ | required |
| Contamination scatter | ✗ | nice-to-have |
| Custom threshold profiles (cohort A vs B) | ✗ | future |

## 10. Open questions

- **Strict vs permissive QC**: do we ship the cohort default or
  per-analysis variants (e.g. relaxed for ROH detection)? Currently
  one global threshold set.
- **Round-2 vs round-3 split**: panels are heavy; histogram + scatter
  could ship in round 2 and the recompute action in round 3.
