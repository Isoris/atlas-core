# SPEC — relatedness-atlas `coincidence` page

**Status**: scaffold; **overlaps with [meiosis-atlas `interchromosomal`
page](../../meiosis-atlas/specs_todo/SPEC_interchromosomal_page.md)**.
Reconciliation decision pending — see [SPECS.md §"Architecture note"](../SPECS.md).

**Scaffolded in:** [`atlases/relatedness/pages/hub/coincidence.html`](../atlases/relatedness/pages/hub/coincidence.html) + `coincidence.js`.

---

## 1. Goal

Per the manifest tooltip: "Coincidence — 2D per-window-pair heatmap of
C = r12 / (r1*r2) for one chromosome (Sandler interference map). C ~ 1
= independence; C < 1 = positive interference (the normal pattern);
C >> 1 = negative interference (usually artefact). Click any cell to
inspect the pair."

Backs the registered meiosis_atlas product
[`coincidence_matrix.v1`](../../atlas-core/toolkit_registries/relatedness/01_registry/products.jsonl)
— specifically the **intrachromosomal slice** (same-chromosome interval
pairs). The interchromosomal slice is the
[interchromosomal page](../../meiosis-atlas/specs_todo/SPEC_interchromosomal_page.md).

## 2. The overlap

- This page = intrachromosomal Sandler interference map (within-chrom interval pairs, one chromosome at a time)
- meiosis-atlas `interchromosomal` = inter-chromosome focal-inversion × tested-chrom test

Both read the **same product** (`coincidence_matrix.v1`); they slice it
differently. The product itself is one matrix with both intra- and
inter-pair cells.

## 3. Recommendation: KEEP as the intrachromosomal view

Unlike the `meiosis` page overlap (which is total), this page has a
distinct biological framing — the Sandler interference map is a
well-established within-chromosome view, separate from the
interchromosomal-effects test.

Per the page tooltip, it's also interactive (click a cell to inspect a
pair), which would be awkward to fold into the interchromosomal page.

Recommendation: keep this page; let meiosis-atlas's interchromosomal
focus on cross-chromosome effects exclusively. Both consume the same
underlying `coincidence_matrix.v1` envelope but apply different filters
(`scope = intra_chrom` vs `scope = inter_chrom`).

## 4. Data dependencies

Today: stubbed.

Envelope-aware target:
- `coincidence_matrix.v1` from meiosis-atlas (cross-atlas read) — currently **missing — builder needed** per registry. Wire after the meiosis-atlas's builder lands.

The filter applied to the envelope payload:
```js
payload.pairs.filter(p => p.chrom1 === activeChrom && p.chrom2 === activeChrom)
```

## 5. Surface

```
#coinChromSelect    — chromosome (cross-tab — same select as elsewhere)
#coinHeatmap        — 2D heatmap; rows = window 1, cols = window 2 on same chrom
#coinColorScale     — legend (C value → colour, log scale recommended)
#coinDataSource     — envelope status badge
#coinPairInspector  — slide-out for clicked cell details (positions, r1, r2, r12, C, n)
```

## 6. Behaviour

`mount()`:
1. Probe `coincidence_matrix.v1` envelope (fail-soft).
2. Render status badge.
3. Filter envelope payload to active chrom (intra-chrom pairs only).
4. Render heatmap; greyed-out cells for window pairs with too few events.
5. Wire click → open inspector slide-out for that pair.

`unmount()`: detach listeners + inspector.

## 7. Open work

- **Cross-atlas envelope read** — depends on meiosis-atlas's `coincidence_matrix` builder shipping first.
- **Decision: window size** — the heatmap resolution is window-count-squared; for 28 chroms × ~50 windows-per-chrom, that's ~2500 cells per chrom × 28 chroms = 70k cells total. Tractable; per-chrom rendering keeps it under 2500 cells per view.
- **Negative interference highlighting** — C >> 1 cells should be flagged in `var(--bad)` (likely artefact per the tooltip).
- **Inspector content** — clicking a cell should show: the two windows' coords, n events in each, raw r1/r2/r12 counts, computed C, the Sandler null reference. Possibly also a mini per-family barchart (similar to mendelian's DRIVE_CANDIDATE drill-down).

## 8. Cross-atlas wiring

The cross-atlas read pattern (relatedness-atlas page consuming a
meiosis-atlas product) is the same `resolveLatestLayer()` call as
intra-atlas reads — the envelope index is workspace-wide, not per-atlas.

No special wiring needed beyond a normal import of
`../../shared/api_client.js`.
