# SPEC — diversity-atlas `samples` page (per-sample diversity table)

**Status**: shipped — first page in the diversity atlas to consume the
action-pipeline envelope contract (commit 28 of the toolkit_registries
action-pipeline branch). Envelope-aware data-source badge is wired;
table content is still DEMO-data-backed pending the consume-stage
migration. 14-assertion smoke test green; wired into the umbrella as
"diversity-atlas per_sample/page1 (envelope-provenance badge)".

**Implemented in:**

| file | role |
|---|---|
| [`pages/per_sample/samples.html`](../atlases/diversity/pages/per_sample/samples.html) | static fragment with per-sample table + provenance badge slot + drill-down side panel |
| [`pages/per_sample/samples.js`](../atlases/diversity/pages/per_sample/samples.js) | mount lifecycle, envelope-probe via `listLayers + getLayer` fan-out, table render |
| [`pages/per_sample/test_samples_provenance.js`](../atlases/diversity/pages/per_sample/test_samples_provenance.js) | 14-assertion smoke (envelope present / absent / multiple / fetch-failure-resilience / fail-soft) |
| [`shared/mode_b_badge.js`](../atlases/diversity/shared/mode_b_badge.js) | shared envelope-provenance badge renderer |

This SPEC is **retrospective** — the migration shipped before the SPEC.

---

## 1. The biological question

> Per sample, what's its **genome-wide diversity profile**? Is this
> fish in the cohort's high-diversity tail, the low-diversity tail, or
> typical? How does its F_ROH compare to the cohort median? Where
> should the reviewer drill in to understand any individual sample?

This page is the **per-sample roll-up of the diversity-atlas's three
primary metrics** — heterozygosity (H), runs-of-homozygosity fraction
(F_ROH), and θπ summary stats. One row per sample (cohort = 226 fish);
sortable; click → drill-down per-chromosome breakdown.

It's the diversity atlas's most-visited "first stop" page — review of
a new sample starts here, then routes to chromosomes / hotspots / roh
pages for the specific drill-down.

## 2. Data input

**v1 today** (envelope-advertise + DEMO consume):

Envelope-aware via the action pipeline:
- `listLayers({ layer_type: 'staging_diversity_slot_v0' })` → filter envelopes by `payload.slot === 'embedded_tables'`
- Most-recent matching envelope drives the **provenance badge**: rows × cols shape, humanised byte count, `created_at`, `action_id`
- The actual table cells still come from `DEMO.per_sample_diversity` — the consume-stage migration is open work

**v2 target** (envelope-consume): the table cells should bind to the
envelope's `payload.rows` directly, replacing DEMO. The envelope shape
already supports the rows; it's a renderer swap.

## 3. The table view

One row per sample. Columns:

| col | source | meaning |
|---|---|---|
| `sample_id` | input | canonical id |
| `family_id` | producer | family-hub assignment (cross-atlas: relatedness) |
| `sex` | producer | M / F / U (unknown) |
| `K=8_cluster` | producer | hard-call NGSadmix cluster at canonical K (see [SPEC_ancestry_page.md](SPEC_ancestry_page.md)) |
| `H` | producer | genome-wide heterozygosity |
| `F_ROH` | producer | total runs-of-homozygosity fraction |
| `F_ROH_short`, `F_ROH_medium`, `F_ROH_long` | producer | length-class decomposition (see [SPEC_roh_page.md](SPEC_roh_page.md)) |
| `theta_pi_mean` | producer | per-chromosome θπ summary, mean across chromosomes |
| `theta_pi_sd` | producer | per-chromosome SD |
| `n_chroms_with_data` | producer | how many chroms have non-null θπ for this sample |

Row click → drill-down side panel:
- Per-chromosome breakdown of H + F_ROH + θπ
- Cross-page links: scope `chromosomes` / `hotspots` / `roh` / `burden` to this sample

## 4. The provenance badge

Above the table, the envelope-provenance badge surfaces:

```
[●] embedded_tables  N rows × K cols  · X.X MB · 2026-05-14 12:34 UTC · act_xyz
```

Three states (per the standard pattern):

1. **Envelope present** (matching `slot == 'embedded_tables'`): green badge with shape + bytes + timestamp + action_id
2. **No matching envelope**: grey badge — "DEMO fallback — no embedded_tables envelope yet"
3. **Fetch failure** (server down): silently falls back to DEMO; no console noise

The 14-assertion smoke validates all 3 states, plus the
**multiple-envelope most-recent-wins** path, plus **partial-fetch-failure
resilience** (when listLayers succeeds but per-envelope getLayer fails
on some).

## 5. The list+get fan-out pattern

This page introduced the **fan-out idiom** for envelope filtering by
inner payload field:

```
1. listLayers({ layer_type: 'staging_diversity_slot_v0' })
   → returns N envelope index rows
2. For each row:
     env = getLayer(row.layer_id)         // fetch full envelope
     if (env.payload.slot === 'embedded_tables') keep
3. Sort kept envelopes by created_at descending → most-recent wins
```

The pattern is used elsewhere when `layer_type` alone is too coarse
(the staging-slot envelope can carry one of 5 slots: `embedded_tables`,
`texture_metrics`, `functional_burden`, `roh_gene_overlap`,
`divergence_network`). Filtering by `payload.slot` requires the
per-envelope fetch, but partial fetch failures are tolerated.

## 6. State + interaction

- `state.shared.activeSample` — set on row click; routes sibling pages
- `state.shared.activeQK` — read; used to populate the K=8_cluster column

## 7. Failure modes

| # | condition | behaviour |
|---|---|---|
| 7.1 | `listLayers` returns empty | DEMO fallback; badge "no envelopes yet" |
| 7.2 | Some `getLayer` calls fail (HTTP 503) | partial fan-out result; badge advertises the successful subset; failures logged |
| 7.3 | All `getLayer` calls fail | DEMO fallback; badge "fetch failed" |
| 7.4 | Multiple envelopes match | most-recent (by `created_at`) wins; older ones noted in tooltip |
| 7.5 | Sample missing in DEMO but present in envelope | render with envelope-only data; sibling pages may emit stale-DEMO warnings |
| 7.6 | Envelope shape evolves (new column shipped) | additive — renderer ignores unknown columns until they get a UI column entry |
| 7.7 | Per-sample θπ missing | column blank for that row; sortable still works |

## 8. What's currently NOT modelled

### 8.1 Switch from advertise → consume

The table cells still come from DEMO. Production should bind to
`envelope.payload.rows` directly. This is the **only real outstanding
work** for v2 promotion.

### 8.2 Per-stat normalisation toggle

H and F_ROH have different units; a "normalize to z-score per metric"
toggle would help cross-metric comparison. v2 nice-to-have.

### 8.3 Per-family / per-sex row shading

Rows colour-tinted by family or sex would surface batch effects
visually. v2 nice-to-have.

### 8.4 Cross-sample similarity search

Click a sample → "show me the 10 most similar samples by H/F_ROH/θπ
multivariate distance". Useful for finding sample-replicate-pair
candidates. v2.

### 8.5 Cohort-percentile chips

Each numeric cell could carry a small chip showing the sample's
percentile rank in the cohort. v2 visual nice-to-have.

## 9. Cross-page links

- Row click → `state.shared.activeSample` → sibling pages scope:
  - [`chromosomes`](SPEC_chromosomes_page.md) — per-chrom view of this sample
  - [`hotspots`](SPEC_hotspots_page.md) — which hotspots this sample drives
  - [`roh`](SPEC_roh_page.md) — this sample's ROH composition
  - [`burden`](SPEC_burden_page.md) — this sample's contribution to per-gene burden
  - [`pruning_qc`](SPEC_pruning_qc_page.md) — was this sample NAToRA-pruned?
  - [`texture`](SPEC_texture_page.md) — this sample's DDI / χ_min position in the scatter

## 10. UI surface

```
┌────────────────────────────────────────────────────────────┐
│ provenance badge — embedded_tables · N × K · bytes · time  │
├────────────────────────────────────────────────────────────┤
│ per-sample table (sortable; columns above in §3)           │
│   row click → drill-down side panel + state.shared.activeSample │
├────────────────────────────────────────────────────────────┤
│ Drill-down side panel (slides out on row click)             │
│   per-chromosome breakdown: H + F_ROH + θπ                  │
│   "Open in: chromosomes | hotspots | roh | burden" links    │
├────────────────────────────────────────────────────────────┤
│ [Export TSV]                                                │
└────────────────────────────────────────────────────────────┘
```

## 11. Promotion criteria

| criterion | v1 (today) | v2 |
|-----------|------------|----|
| Envelope-advertise via provenance badge | ✓ | ✓ |
| 14-assertion smoke covering all badge states | ✓ | ✓ |
| Table renders (DEMO data) | ✓ | ✓ (envelope-bound) |
| Row click → state.shared.activeSample | ✓ | ✓ |
| Drill-down side panel | ✓ | ✓ |
| Envelope-consume (cells from envelope, not DEMO) | ✗ | required |
| Per-stat normalization toggle | ✗ | nice-to-have |
| Per-family / per-sex shading | ✗ | nice-to-have |
| Cross-sample similarity search | ✗ | future |

## 12. Open biological design questions

### 12.1 What's a "diverse" vs "inbred" sample threshold

The page is descriptive — no flags fire today. v2 could highlight
samples with F_ROH > Q3+1.5×IQR (Tukey-style outliers) or H below the
cohort 5th percentile. The thresholds need biological grounding;
currently the page shows raw numbers and lets the reviewer judge.

### 12.2 Family vs sample as the primary unit

This page sorts by sample. For some analyses (e.g. cohort
demographic-history modeling) the family is the right grain. v2 could
add a "group by family" mode that pre-aggregates the table.

### 12.3 What to show for an admixed sample

Hard-call K=8_cluster = -1 for admixed samples. v2 could show the
top-2 Q values inline (e.g. "K3 (61%) + K5 (37%)") so the user sees
the actual ancestry composition.
