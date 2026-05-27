# SPEC — diversity-atlas `roadmap` page (planned but not yet shipped)

**Status**: scaffold. Meta-page; pure documentation surface.

**Scaffolded in:**

| file | role |
|---|---|
| [`pages/meta/roadmap.html`](../atlases/diversity/pages/meta/roadmap.html) | static markdown-style fragment listing planned features |
| [`pages/meta/roadmap.js`](../atlases/diversity/pages/meta/roadmap.js) | mount lifecycle; no dynamic data |

---

## 1. Goal

A single page surfacing **what we plan to ship that isn't shipped yet**.
Reads like an internal product roadmap. Target audience: collaborators
seeing the atlas for the first time, or returning contributors checking
what's still open.

Distinct from [`about`](SPEC_about_page.md) which describes what
**is** shipped — this page describes what is **not**.

## 2. Content sections

Three categories:

### 2.1 Imminent (next-round)

Things planned for the next migration round but not yet wired:

- Envelope-aware data loading for all 11 pages (today most read static TSVs)
- The 4 cross-cutting adapter pairs:
  - `diversity_per_chromosome_v1`
  - `diversity_hotspots_v1`
  - `cohort_ancestry_q_v1`
  - `diversity_qc_v1`
- Shared stratification pill (K=8 / family / per-sample / F_ROH-quartile)
  wired across `roh`, `burden`, `chromosomes`, `texture`

### 2.2 Mid-term (planned but no schedule)

- Cold-spot view (low-θπ outlier windows) — sister to [`hotspots`](SPEC_hotspots_page.md) §7.2
- Per-K stability / consensus across NGSadmix replicates — see [`ancestry` §7.3](SPEC_ancestry_page.md)
- Bootstrap CIs on per-gene πN/πS, π0/π4 — see [`burden` §6.1](SPEC_burden_page.md)
- Permutation-based edge significance on the divergence network — see [`divergence` §7.4](SPEC_divergence_page.md)
- Sex stratification across all per-sample pages

### 2.3 Long-term (decisions pending)

- Cross-species comparison (introgression, divergence vs. *C. macrocephalus*)
- Polarised SFS via outgroup (separates ancestral / derived alleles)
- LD-adjusted multiple-testing correction
- Cross-atlas evolution-atlas integration (this atlas's outputs feeding the future evolution atlas)
- Drug-target / disease-gene annotation overlay on the `burden` page

## 3. Data input

None — fully static.

## 4. State + interaction

None — pure documentation page.

## 5. Cross-page links

Each roadmap item links to:
- The SPEC for the feature
- The page where it will live

## 6. UI surface

```
┌────────────────────────────────────────────────────────────┐
│ Header: "Roadmap — Diversity Atlas"                        │
│ Sub: "What's planned but not yet shipped."                 │
├────────────────────────────────────────────────────────────┤
│ § 1. Imminent (next-round)                                 │
│   Bulleted list with SPEC links                            │
├────────────────────────────────────────────────────────────┤
│ § 2. Mid-term (planned, no schedule)                       │
│   Bulleted list with SPEC links                            │
├────────────────────────────────────────────────────────────┤
│ § 3. Long-term (decisions pending)                         │
│   Bulleted list                                            │
└────────────────────────────────────────────────────────────┘
```

## 7. Promotion criteria

| criterion | v1 | v2 |
|-----------|----|----|
| Three-section roadmap renders | ✓ | ✓ |
| Each item links to its SPEC | ✓ | ✓ |
| Items get checked-off / moved-to-shipped as they ship | manual | nice-to-have automation |

The roadmap should be **the inverse of `specs_done/`** — it's the
public view of `specs_todo/`. v2 could auto-generate this page from
the `specs_todo/` directory listing.

## 8. Maintenance

When a SPEC moves from `specs_todo/` to `specs_done/`, the
corresponding roadmap item should be removed (or moved to a "recently
shipped" footer for one-round visibility before being deleted).

Update cadence: end of every migration round.
