# DATA_LIFECYCLE — when to precomp, when to interface raw

This is the one-rule policy for which results get pre-baked into a
JSON precomp on the HPC, which results get read raw from a folder
through the registry, and which results get written by the atlas
itself per candidate.

Read this when you're about to build a new data domain and don't
know where it goes.

---

## The rule, in one sentence

> **Use the HPC for big one-shot analyses; precomp those results into
> JSON. Read raw tool output through the registry when the analysis
> can be re-subset interactively. Write per-candidate atlas-shaped
> JSONs from the browser through the registry's write path.**

That sentence covers every data domain. The three categories below
are how it applies in practice.

---

## Category 1 — Heavy one-shot HPC analyses → precomp to JSON

**When:** the analysis is big, slow, parameter-locked at run time,
and produces a single canonical output. Re-running it requires HPC
time and a deliberate rerun decision; you don't re-subset it
interactively.

**Where the result lives:** `data/precomp/{chrom}/<thing>.json` (or
`.tsv`), one file per chromosome or one per analysis run.

**Examples:**

| Analysis | Why precomp | File |
|---|---|---|
| Local PCA windows + sim_mat + Z | sim_mat is 226×226 × N_windows; baked once | `data/precomp/{chrom}.json` |
| Repeat density per scrubber window | RepeatModeler/EDTA is hours of work, output is per-window numbers | `data/precomp/{chrom}/repeat_density.scrubber_windows.json` |
| Cohort diversity (θπ, π, F_ROH per window) | ANGSD/PoPLDdecay over 226 samples × full genome | `data/precomp/cohort_diversity_v1.json` |
| Cross-species breakpoints | wfmash + downstream parsing | `data/precomp/cs_breakpoints_v1.json` |
| Per-window SV density (future) | Bin DELLY+Manta calls along chromosome | `data/precomp/{chrom}/sv_density.scrubber_windows.tsv` |

**How the atlas reads it:** registry layer with `source: file`,
`tier: hot` or `warm`, `preload_on: chrom_change` for per-chrom
files, `preload_on: page_mount` for cohort-wide files. **All** the
existing `band_*`, `scrubber_main`, `repeat_density`,
`cohort_diversity` layers are this category.

**Rule of thumb:** if running it once takes >10 minutes of HPC
time, and the output shape is fixed (no parameter you'd want to
flip interactively), it's a precomp.

---

## Category 2 — Tool-native folders → registry interfaces raw

**When:** the analysis tool emits structured per-pair / per-window
files; the user wants to re-subset (different sample subset,
different threshold, different population) without re-running the
heavy upstream step. Re-baking a single JSON locks in choices the
next analysis didn't know it would want.

**Where the result lives:** `data/cohort/<domain>/<tool>/<run_id>/...`
in the tool's native layout — the atlas does NOT re-export.

**Examples:**

| Tool | Why interface raw | Folder |
|---|---|---|
| ngsRelate | 23 columns; different analyses need different subsets (Mendelian needs IBS0, family detection needs theta, etc.). Re-baking to a 3-column JSON loses 20 columns forever. | `data/cohort/relatedness/ngsrelate/<run_id>/relatedness.tsv` |
| NGSadmix global Q | Same .qopt file is consumed at K=2, K=4, K=8; population-subset analyses re-bin the same file | `data/cohort/ancestry/global/K{K}/ngsadmix.qopt` |
| KING / hap-IBD (future) | Same logic as ngsRelate — column subset is analysis-specific | `data/cohort/relatedness/<tool>/<run_id>/...` |
| pyrho recombination (future) | rho per window; downstream queries pick scales | `data/cohort/recombination/pyrho/<run_id>/...` |

**How the atlas reads it:** registry layer with `source: file`,
`format: tsv` (or whatever the native format is), `fields: null`
default, with the option to pass `fields: [...]` per call to drop
unneeded columns at parse time. The `fields:` filter is wired (chat
~33).

**Rule of thumb:** if a future analysis might want a column you
didn't think of today, **don't pre-bake.** Read raw, take only the
columns you need at call time.

---

## Category 3 — Per-candidate atlas-shaped JSONs → producer or browser writes through registry

**When:** the analysis is candidate-specific (depends on candidate
boundaries, callset, version) and the output is small enough to
ship as one JSON per candidate. The output is the deliverable, not
a re-bakeable summary.

**Where the result lives:** `data/candidates/<cid>/<version_id>/<thing>.json`.

**Examples:**

| Output | Producer | File |
|---|---|---|
| SV genotype counts in candidate window | `STEP_SV_GT_AGG` Python on HPC | `sv_genotype_counts.json` |
| SV evidence combinations (UpSet) | `STEP_SV_EVID_COMB` Python on HPC | `sv_evidence_combinations.json` |
| Per-sample SV support matrix | `STEP_SV_SUPPORT` Python on HPC | `sv_support_by_sample.json` |
| Refined boundary call | dosage-bridge consensus on HPC | `boundaries_refined.json` |
| Mendelian inheritance result | `analysis/mendelian_inheritance.js` in browser | `mendelian_inheritance.json` |
| Marker primer panel | (future) browser or HPC | `marker_primers.json` |
| Breeding readiness card | browser | `breeding_readiness_card.json` |

**Two write modes** depending on producer location:

- **HPC-side producer** (the SV pipeline): runs as a SLURM/Python
  script against the raw VCF on LANTA. Writes its JSON output to
  `data/candidates/<cid>/<version_id>/`. Atlas reads through the
  registry layer on `candidate_change`. **HPC writes; browser reads.**
- **Browser-side producer** (the Mendelian module, the breeding
  card): runs in the browser through `analysis/*.js`. Writes its
  JSON output through `Registry.write(...)` (SPEC v2 item 4). Same
  destination path. **Browser writes; browser reads.**

**Rule of thumb:** if the analysis takes a candidate's
`(boundaries, callset, version)` as input, the output is per-candidate
and goes in this category. Whether it's HPC-side or browser-side
depends on whether the heavy raw data lives on LANTA (VCF, BAM) or
in a registry layer the browser already has (relatedness TSV,
chrom-level precomp).

---

## How to decide which category

A new analysis lands on your desk. You ask three questions:

```
1. Is the heavy upstream step parameter-locked and slow?
   ├── YES → pre-bake one canonical output → Category 1 (precomp)
   └── NO  → continue ↓
2. Will future analyses want columns you don't know about today?
   ├── YES → read raw tool output, columns on demand → Category 2 (raw folder)
   └── NO  → continue ↓
3. Does the output depend on a candidate's (boundaries, callset, version)?
   ├── YES → write per-candidate JSON, version-suffixed → Category 3 (per-candidate)
   └── NO  → think again — almost everything fits 1, 2, or 3.
```

If a domain seems to fit two categories at once, it usually splits:
the heavy chrom-wide aggregate is Category 1 (precomp), the per-
candidate detail is Category 3 (per-candidate). That's exactly the
SV split: chrom-level density → Category 1; per-candidate genotype
counts → Category 3. Both backed by the same raw VCF on LANTA, but
two different producers, two different output shapes, two different
registry layers.

---

## What this rules out

The categories are exhaustive, but several patterns are explicitly
NOT recommended:

- **Don't precomp tool-native output that's re-subsettable.** That's
  the lesson from `data/precomp/catfish_226_relatedness.json` — 3
  of 23 columns were kept; the missing IBS0 blocks Mendelian QC.
  **Read raw through Category 2 instead.**
- **Don't run small analyses on HPC.** If it's fast enough to do in
  the browser (Mendelian filtering, het rate calculation, sample
  group operations), do it in the browser. HPC is for things that
  need cluster compute. Quentin's rule: *"use HPC only for big
  analysis, otherwise headache."*
- **Don't pre-bake per-candidate output that depends on parameters
  the user can change.** That's Category 3 with version_id, not a
  candidate-naive precomp. Two candidates with overlapping windows
  but different active versions get different folders.
- **Don't write per-candidate output anywhere except
  `data/candidates/<cid>/<version_id>/`.** No `04_intermediate/`,
  no `05_catalogues/`, no parallel hierarchy. The canonical
  per-candidate folder is the destination for every per-candidate
  result, regardless of whether the producer is HPC-side or
  browser-side.

---

## How the registry stays the central librarian

In every category, the registry is the **single read interface** for
pages and analysis modules:

```
Page / analysis module
       │
       ▼
   registry.resolve('<layer>', { ... })
       │
       ├─→ Category 1: file in data/precomp/   (1 fetch, RAM cached)
       ├─→ Category 2: file in data/cohort/<domain>/  (1 fetch, IndexedDB cached, optional fields:)
       └─→ Category 3: file in data/candidates/<cid>/<version_id>/  (1 fetch, IndexedDB cached)
```

And the **single write interface** for browser-side producers:

```
analysis module
       │
       ▼
   registry.write('<layer>', { candidate_id, version_id }, payload)
       │
       └─→ POST /file/data/candidates/<cid>/<version_id>/<thing>.json
            (server-side path allowlist enforces canonical layout)
```

HPC-side producers don't go through `registry.write` — they write
directly to disk on LANTA in their SLURM/Python step. The browser
reads what they wrote through the same registry layers. The two
write modes converge on the same destination paths and the same
read paths.

That's the librarian model in one diagram. **Pages don't know which
category their data came from.** They call `registry.resolve(...)`,
get rows or objects back, render. The registry handles the routing.

---

## Worked example: a candidate's full data

User clicks `1715000000000_a4b` on the LG28 scrubber.
`setActiveCandidate(cand)` fires `candidate_change`. The prewarm
scheduler walks every `preload_on: candidate_change` layer:

```
data flowing in (all in parallel, all cached after first hit):

Category 1 (already in RAM from chrom_change):
  scrubber_main          state.data.windows
  candidate_tracks       state.data.candidate_tracks (has active_version_id)

Category 2 (loaded once on page_mount, still in IndexedDB):
  cohort_sample_manifest
  cohort_sample_groups
  cohort_relatedness     (or relatedness_ngsrelate when wired)

Category 3 (fetched now, parameterised by {candidate_id, version_id}):
  candidate_lineage          → lineage.json
  candidate_boundaries        → v2_theta_refined/boundaries_refined.json
  candidate_sv_counts         → v2_theta_refined/sv_genotype_counts.json
  candidate_sv_combinations   → v2_theta_refined/sv_evidence_combinations.json
  candidate_sv_support        → v2_theta_refined/sv_support_by_sample.json
  candidate_gene_cargo        → v2_theta_refined/gene_cargo.json
  candidate_marker_primers    → v2_theta_refined/marker_primers.json
  candidate_karyotype         → v2_theta_refined/karyotype.json
  arrangement_calls           → v2_theta_refined/arrangement_calls.json
  candidate_breeding_card     → v2_theta_refined/breeding_card.json
  candidate_final_class       → v2_theta_refined/final_classification.json
  candidate_mendelian         → v2_theta_refined/mendelian_inheritance.json   (when wired)
```

11 fetches in parallel, each is a small JSON (~10–20 KB), all cached
in IndexedDB. The scrubber strip never opens any of these — it
reads the active boundaries from `candidate_tracks.json` which is
already in RAM. Click cost: <500 ms first time, <10 ms thereafter.

Switch to `v1_localPCA_initial` to compare: 11 more fetches against
the v1 subfolder, then both cached. Toggle v1 ↔ v2 instantly.

---

## What gets built next

This doc doesn't add code; it locks down the policy so future chats
don't redebate it. The actual implementation pieces are still:

- **Piece α** — chrom-level SV density (Category 1 producer)
- **Piece β** — candidate versioning (Category 3 layer + path
  templating)
- **Piece γ** — producer wiring for versioned output (Category 3
  HPC-side)
- **Piece δ** — `Registry.write` (Category 3 browser-side)
- **Piece ε** — `analysis/mendelian_inheritance.js` (Category 3
  browser-side producer, depends on β + δ)

Each one slots cleanly into a single category. None of them
straddles. That's how we know the categories are right.
