# SPEC — Live Engine-Backed Popstats: User-Defined Groups → Live Fst / dXY / θπ / HoverE

**Status**: draft. New spec. Supersedes the "live group-vs-group via active-samples" line item from the consolidated queue with a more concrete and more ambitious version.

**Source**: Quentin chat. Pushback on my earlier statement that "Fst whole genome not possible in browser." The pushback is correct — Fst is computed by an engine F binary that exists, runs in seconds, and is reachable via a server. Browser doesn't do the math; browser sends a sample partition to the server, gets results back, animates them in. The earlier statement conflated "live in atlas" with "live in browser-only."

**Scope**: User-defined sample groups (from PCA selection, tracked-samples panel, karyotype call, family ID, ROH carrier status, or any combination) drive **server-mediated live recomputation** of Fst / dXY / θπ / HoverE across the chromosome (and ultimately across the genome). Results stream back into page 6 popstats panel, page 7 ancestry, page 12 θπ tracks, with subtle animation when a recompute completes.

---

## 1. The reframe

I owe a correction. Earlier I said:

> "Fst between groups: NOT live. Fst is a between-pop quadratic estimator; computing live across 5000 windows × 226 samples is ~5e6 ops per recompute. Tractable but slow (~500ms uncached). Better to precompute via Q07."

That's wrong-shaped. The choice isn't "browser-side live" vs "precompute on cluster." It's three options:

- **Browser-side live**: only feasible for cheap aggregations (mean, median, fraction over loaded data). Quadratic estimators no.
- **Precompute on cluster**: deterministic, slow turnaround, doesn't support arbitrary user group definitions.
- **Server-mediated live**: the engine binaries already exist (`region_popstats`, `instant_q`, `hobs_windower`). Wrap them in a daemon. Atlas posts a sample partition; server runs engine; server streams results back. Latency: tens of ms (per-region) to a few seconds (genome-wide), well within "live with animation" range.

Server-mediated live is what Quentin has been describing. It's the right architecture for the engines we have. The engines are fast, the missing piece is the daemon that exposes them to HTTP.

Crucially: **this isn't a new idea**, it's the same dosage_streaming server pattern Quentin has been using for the dosage heatmap, just extended to wrap more engines. The architecture exists; only the surface area changes.

---

## 2. The user experience (north star)

The thing the user does:

1. User opens the atlas, picks a chromosome, lands on page 1
2. User clicks/drags on the PCA scatter to lasso some samples — say, the samples that cluster as HOM_INV on candidate LG28-15Mb
3. The tracked-samples panel populates with those sample IDs (already exists in atlas)
4. **A "popstats recompute" button appears** in the popstats toolbar (or page 7, or page 12 — wherever popstats lives), reading: "compute Fst / dXY / θπ / HoverE for the 47 selected samples vs the 179 background"
5. User clicks it (or it auto-fires after a 1-second debounce)
6. A subtle animation: popstats track lines fade slightly, a thin progress bar at the top fills, then the new tracks slide in via a tween — old line transitions to new line over 300ms
7. The user can switch between "static (precomputed Q07 from blessed candidates)" and "live (current selection)" modes via a chip

Multiple group definitions:
- One-vs-rest (selected vs not-selected) — default
- Pairs of groups — "selected_blue vs selected_orange" — when the user has saved multiple named subsets
- Karyotype trichotomy — Hom1/Het/Hom2 from atlas-side K-means(3) labels at the focal candidate

Whole-genome view:
- Same UX, but the recompute fires across all 28 chromosomes
- Slower (~3-5 seconds with engine F)
- Progress animation: chromosomes light up sequentially as they finish on the server (server streams chrom-by-chrom)
- Result is a Manhattan-plot-style strip on a new genome-wide overview page

That's the thing. Now the engineering.

---

## 3. The architecture, concretely

### Layer 1: server (the engine wrapper daemon)

A single Python or Go daemon, call it `popstats_server`, sitting on the same machine as the dosage_streaming server (or merged into it). Wraps the existing C binaries:

- `region_popstats` (Engine F) — Hudson Fst, dXY, θπ per group
- `hobs_windower` — HoverE per group
- `angsd_fixed_HWE` (Mérot's patched ANGSD) — per-group HWE/Hexp at SNP level

The daemon doesn't reinvent any computation. It exposes one HTTP endpoint per supported computation, takes JSON request, runs the binary, streams the result back.

### Endpoints

```
POST /api/popstats/groupwise
  body: {
    chrom: "C_gar_LG28" | "all",
    region: { start_bp, end_bp } | null,    // null = whole chrom or whole genome
    groups: {
      "selected": ["CGA_001", "CGA_047", ...],
      "background": ["CGA_002", ...]            // server can fill in as complement
    },
    metrics: ["fst", "dxy", "theta_pi", "tajimas_d"],
    win_bp: 50000,
    step_bp: 10000
  }
  response (streaming JSON-lines):
    { chrom: "...", window_bp: N, fst: ..., dxy: ..., theta_pi: {selected: ..., background: ...} }
    { chrom: "...", ... }
    ...

POST /api/popstats/hobs_groupwise
  body: similar, plus optional --reuse_hwe_cache flag
  response: per-window per-group HoverE

POST /api/ancestry/groupwise_q
  body: groups + region + K
  response: per-window mean Q-vector per group (lighter than instant_q full run)

GET /api/cache/status?key=<hash>
  response: 200 if cached, 404 if not, 202 if in progress
```

All endpoints support **streaming**. The daemon yields partial results as they're computed (one JSON-lines record per window, or per chrom in genome-wide mode), so the atlas can animate progressively.

### Caching

Two layers:

- **Daemon-side**: keyed by `sha256(chrom + region + groups + metrics + win/step + engine_version)`. Engine output stored as JSON on disk. On cache hit, daemon streams from disk in <50ms. Cache wipe on engine binary update (engine_version in the key).
- **Atlas-side**: keyed by the same hash, stored in IndexedDB. Atlas first checks local cache, if miss, hits server, on response stores result. Survives reload, scoped per cohort.

This means: the user's *third* time selecting "HOM_INV at LG28-15Mb" returns instantly from atlas IndexedDB. The *first* time costs whatever the engine costs (a few seconds for genome-wide, ~100ms for region-focal).

### Performance budget (honest estimates)

I want to set realistic expectations before this turns into "live everything everywhere."

| Computation | Region scope | Latency estimate (engine F) | UX class |
|---|---|---|---|
| θπ per group | one candidate | <50ms | instant |
| Fst per group | one candidate | <100ms | instant |
| Fst per group | one chromosome | 200-500ms | feels-live with subtle spinner |
| Fst per group | whole genome (28 chroms) | 2-5s | progress bar, chrom-by-chrom streaming |
| HoverE per group | one chromosome | depends on whether HWE cache exists; first time slow (re-run patched ANGSD), cached fast | first-time 5-15s, cached <500ms |
| Pairwise Fst, all karyotype combos | whole genome | 5-15s | "compute" button, progress, no auto-fire |

The HoverE first-run-cost is the awkward one because it requires re-running patched ANGSD on a new sample partition (Q07b's job). For *predefined* karyotype groups (Hom1/Het/Hom2 derived from atlas-side K=3 K-means at a candidate), Q07b can be precomputed and cached. For *arbitrary user group selections*, the first request triggers a slow re-run. Mitigation in section 6.

### What stays precomputed

Even with this server, some things stay precomputed because the inputs change rarely:

- **Q01/Q02/Q03 chromosome QC tracks** — function only of BAM + ANGSD output, not of group definition. Precompute per chrom, atlas reads via Q08 emitter (previous spec).
- **Q06 ancestry per-window summary** — function of BEAGLE × NGSadmix Fopt. Precompute per chrom, atlas reads via Q08.
- **Genome-wide ancestry palette** (the "color samples by family" view) — function of cohort-level kinship. Precompute, drag-drop ngsRelate JSON.
- **Chromosome-wide θπ per sample** (`w.theta` injection) — function of BAM. Precompute, in precomp JSON.

What becomes live:
- **Anything that depends on a user-defined group partition.** Fst, dXY, θπ stratified by group, HoverE per group, Δ12 stratified by group.

The split is: per-sample precompute, per-group live.

---

## 4. Atlas-side surfaces (where the live recomputes appear)

### Page 6 popstats — "static" vs "live" modes

Top of the popstats toolbar, a mode chip group:

```
[ static (Q07 precomp) ]  [ live (current selection) ]  [ split (overlay) ]
```

- **Static**: reads precomputed Q07 / Q07c per-candidate JSONs (existing path, the Q09 emitter from previous spec)
- **Live**: reads from the server using the current `state.activeSampleSet` as the "selected" group, complement as "background"
- **Split**: shows both as overlaid lines (static = solid, live = dashed) so the user can compare "what the manuscript shows" against "what my current selection shows"

Tracks that become live: `theta_invgt`, `fst_hom1_hom2`, `hobs_hexp`, `delta12_multi` (if delta12 stratification is wanted).

### Page 1 — selection → recompute trigger

The PCA scatter on page 1 already supports lasso selection (turn 95+). When the user selects samples:

1. `state.activeSampleSet` updates (AS1 already does this)
2. A new toast appears in the popstats panel header: *"47 samples selected — refresh popstats live? [yes / dismiss]"*
3. If yes (or auto-fire after debounce in user settings), atlas posts the partition to the server
4. Animation runs

This is the "tracked samples → automatic recompute" pattern Quentin asked about. Implemented as a toast / button rather than full-auto, with optional debounced auto-fire as a user-pref toggle.

### Page 12 — same pattern for θπ tracks

Once page 12 ships (after STEP_R40/R41), it gets the same live mode:

- Static: precomputed θπ-PCA from STEP_R40
- Live: per-window mean θπ within `activeSampleSet` vs background, recomputed live (or computed in-browser since per-sample θπ is already in `w.theta`)

Note: page-12's *local PCA on θπ profiles* itself stays precomputed (eigendecomposition is too heavy to recompute live per group selection). What's live is the per-group θπ track, not the PCA.

### New page: genome-wide popstats overview

The cross-chromosome view that doesn't currently exist (open queue item #17). Manhattan-plot strip showing all 28 chroms side-by-side, current group-vs-background popstats overlaid. Select track (Fst / dXY / θπ / HoverE), see whole genome at once.

In live mode: when the user changes selection, all 28 chromosomes recompute in parallel on the server, results stream chrom-by-chrom to the atlas, each chromosome's strip animates in as it finishes.

This is the "is there a hotspot of Hom1-vs-background Fst on some other chromosome too?" view that motivates whole-genome live mode in the first place.

### Page 7 ancestry — group-stratified Δ12

Less critical but the same pattern: Δ12 per group (mean Δ12 within HOM_INV samples vs HOM_REF samples) as a new heatmap-row option. Live, recomputed per group selection. Uses the per-sample ancestry matrix Q06 already provides; the math is just aggregation, can run in browser without the server.

---

## 5. The "what makes a group" inventory

Group definitions the atlas can compose:

| Group source | Where it comes from | Atlas-side label |
|---|---|---|
| Lasso on PCA scatter | Page 1 PCA scatter mouse-drag | `selection_lasso` |
| Tracked-samples panel | Page 1 right sidebar manual list | `tracked_samples` |
| K-means(3) at focal candidate | Page 1 K=3 K-means automatic | `kmeans_<k>_band_<b>` |
| Karyotype call (after C01i) | precomp registry | `karyotype_HOM_INV`, `karyotype_HET`, etc. |
| Family ID | family palette JSON | `family_<id>` |
| ROH carrier status | F_ROH JSON | `roh_carrier`, `roh_noncarrier` |
| Active-samples mask | AS1-AS5 mask | `active_samples` |
| Saved named subset | user-saved (planned) | `saved_<name>` |

Any two of these can be combined into a "selected vs background" pair, or two named subsets can be paired against each other.

The UI is a simple group picker: **Compute Fst between [HOM_INV at LG28-15Mb] vs [background]** with both pickers populated by the same dropdown of saved/derived groups.

This is genuinely powerful because it makes the comparisons the user wants to make trivially expressible:
- "What's Fst between samples that cluster HOM_INV at LG28 vs samples that cluster HOM_INV at LG14? Are they the same fish?"
- "What's θπ in family-1 vs family-2 across the genome? Does family-1 have an inversion the others don't?"
- "What's Δ12 stratified by ROH carrier status? Are inbred samples ancestry-confounded?"

These are real biological questions you can ask in seconds of UI interaction, not days of pipeline rerun.

---

## 6. Honest engineering caveats

I want to be fair about the costs because I was unfair earlier in the other direction.

### Caveat 1: HoverE first-run cost is real

`hobs_hexp` requires Q07b's per-group ANGSD HWE re-run on the new sample partition. ANGSD takes 5-15s on a big BAM list per chromosome. For arbitrary user-group selections this gets expensive.

**Mitigation**: precompute HoverE for the predefined karyotype groups at every blessed candidate (the existing Q07b/Q07c pipeline). Live mode for HoverE is **opt-in with a "this will take ~30 seconds for 28 chroms" warning**, not auto-fire. Or: only allow live HoverE for region-focal queries (single chromosome, region around focal candidate) where the cost is <5s.

### Caveat 2: Streaming vs progress vs spinner

For genome-wide whole-cohort recomputes, the right UX is **streaming chrom-by-chrom**. Each chrom appears in the genome-wide overview as the server finishes it. Total time: 2-5s. User sees progress, not a frozen spinner.

For per-chromosome focal recomputes (<500ms), no spinner, just animate-on-arrival. Latency hides itself.

For HoverE first-run (>5s), **explicit confirm + progress bar with text** ("recomputing per-group HWE for chromosome X…").

Three different UX classes. Don't pretend they're all "live."

### Caveat 3: Server scaling

If the daemon has 4 cores and three users are interacting simultaneously, queue depth matters. For now, single-user assumption is fine (Quentin is the only user). Later, queue with backpressure if multiple users.

### Caveat 4: Engine version drift

If you update `region_popstats` or `hobs_windower` (bugfix, parameter change), the cache must invalidate. Daemon-side cache key includes engine binary's content hash. Atlas-side cache invalidates on schema version change.

### Caveat 5: Reproducibility vs interactivity

The manuscript figures must be reproducible from a deterministic precompute pipeline. If a manuscript reviewer runs Q07/Q07b/Q07c on the canonical karyotype groups and gets different numbers from what's in the atlas, that's a problem.

**Solution**: live recompute is for *exploration*. Manuscript figures are generated from the deterministic batch path (Q07/Q07b/Q07c → Q09 emitter → atlas reads precomputed JSON in static mode). The "live mode" is exclusively for "what if I select these other samples?" interactive work.

The atlas's "static / live / split" mode chip makes this distinction visible. Manuscript-mode = static. Exploration = live.

### Caveat 6: Genome-wide is the actual hard one

Per-chrom is easy. Genome-wide cross-chromosome view (the new overview page) is harder because:

- 28 parallel server jobs (or one big multi-chrom binary call)
- 28 progress indicators or one combined progress bar
- 28 results streaming back, atlas has to merge and render
- Memory: 28 × ~5000 windows × 4 metrics × 8 bytes = ~5MB per partition. Fine.

Not a blocker but it's where the UX gets fiddliest. Build per-chrom first, genome-wide as a follow-on.

---

## 7. Implementation, staged

### Stage A — daemon basics (server-side)

- `popstats_server` daemon wrapping `region_popstats` for Fst/dXY/θπ. Single endpoint, JSON-in JSON-out, no streaming yet, in-memory cache.
- Validates group definitions, fills "background" as complement if not specified, enforces min-group-n.
- ~300 lines Python (FastAPI + subprocess) or Go (less dependency churn). Run as systemd service or under tmux on the cluster.

Estimated: 2-3 turns to ship a working endpoint. Test locally with curl before any atlas integration.

### Stage B — atlas-side static/live mode toggle on page 6

- Mode chip in popstats toolbar: static / live / split
- Live mode: on selection change (with debounce), POST to `/api/popstats/groupwise` for current chrom, region = visible viewport
- Animate transition (300ms tween) when results arrive
- IndexedDB cache atlas-side
- Disable live mode chip if server unreachable; show static-only

Estimated: 3-4 turns. Includes the multiline renderer (queue item #9) needed to display per-group lines.

### Stage C — streaming + genome-wide

- Server endpoint streams results chrom-by-chrom for genome-wide queries
- New atlas page (or extension of page 6) for genome-wide Manhattan strip
- Progress UI: chromosomes light up as they arrive
- Cancel button (user changes mind mid-recompute)

Estimated: 3-4 turns.

### Stage D — HoverE + ancestry-Q live extensions

- Add `/api/popstats/hobs_groupwise` endpoint wrapping Q07b/Q07c
- HoverE-specific UX: opt-in, slower, explicit progress
- Add `/api/ancestry/groupwise_q` for stratified Δ12 (cheaper since Q matrix is already computed)
- Atlas-side: page 7 group-stratified Δ12 view

Estimated: 2-3 turns.

### Stage E — composable group picker UI

- Group definition dropdown menu (lasso / tracked / karyotype / family / ROH / saved)
- Two-group picker for explicit pairs (group1 vs group2)
- "Save this selection as named subset" feature (localStorage)
- Compute trigger: explicit button + optional debounced auto-fire

Estimated: 2-3 turns.

**Total**: ~12-17 turns across daemon + atlas + UX. Substantial. But ships *the* interactive analysis tool the project has been pointing at since the dosage_streaming server was built.

---

## 8. What this enables, biologically

To anchor against why we're doing this — the user-stories this unlocks:

1. **"Are these two distant LG candidates the same translocation?"** Lasso HOM_INV samples on LG28-15Mb. Lasso HOM_INV samples on LG14-22Mb. Compute pairwise Fst between the two groups. If high → different rearrangements; if zero → same fish carry both → likely co-segregating system or single complex rearrangement.

2. **"Is family LD masquerading as inversion structure?"** Lasso the K=3 HET samples at a borderline candidate. Color them by family palette. If 80% of "HET" are family-3, the candidate is family-LD not inversion. Compute Fst within family-3 only; if it disappears, family-LD is confirmed.

3. **"Does this inversion have a sweep signature?"** Compute θπ within HOM_REF group across the genome (live, ~3s). Look at whether the candidate's chromosome shows depressed θπ at and near the candidate. If yes → recent positive selection.

4. **"How does ancestry partition stratify by inversion karyotype?"** Compute mean Δ12 within HOM_INV vs HOM_REF. If different → inversion is associated with ancestry → admixture-driven, not balancing selection.

5. **"What's the manuscript figure if I redefine the candidate?"** Tweak the K-means K, watch popstats redraw. See if the "Hom1-vs-Hom2 Fst spike at the shelf" signal is robust to the K choice.

These are genuinely novel analysis moves the existing batch pipeline can't do at speed. A user who can do them in seconds rather than days of cluster-resubmission will discover things faster.

---

## 9. Updated salvage queue

Adding to the queue from the previous turn:

**Atlas-side queue (consolidated, all 9 audit phases + this spec)**:

1. `window_metrics` data layer reader
2. MDS view
3. sim_mat contrast modes (raw / row-Z / row-quantile / dist-normalized + SVD-residual + axis toggle)
4. Per-chr relatedness layer reader (D11a/b)
5. AS2-AS5 active-samples extension
6. **Spec A — pan/zoom navigator + L1/L2 in precomp**
7. **Q08 emitter — chromosome QC tracks**
8. **Q09 emitter — per-candidate popstats (precomputed/static path)**
9. **`drawPopstatsMultiline` renderer** (also needed by the live spec)
10. **Per-candidate track switching** atlas state
11. **STEP_R40/R41 θπ local PCA**
12. D03 artifact-dip badge
13. D09n masked_local_simmat primitive
14. D09n effect_class live mask badge
15. **Live group-vs-group via AS-mask** — superseded by this spec, expanded
16. **`invgt_assignments` → AS4 auto-rule**
17. **Genome-wide / cross-chromosome overview page** (now first-class consumer of live spec)
18. **Spec B — manual boundary annotation cross-page** (deferred)
19. **Per-candidate concordance figure** (atlas docs §22.7)
20. **NEW — Live engine-backed popstats spec (this document)**:
    - Stage A: popstats_server daemon (Engine F + Engine H wrapper)
    - Stage B: page 6 static/live/split mode
    - Stage C: streaming + genome-wide overview
    - Stage D: HoverE + ancestry-Q live extensions
    - Stage E: composable group picker UI

The dosage_streaming server pattern Quentin already built is the precedent. This spec is its natural extension to the popstats engines. The architecture is proven.

---

## 10. What this turn shipped

- This spec document. No code, no other specs updated.

The most important sentence in this spec: **the architecture for live engine-backed popstats already exists** (dosage_streaming pattern), the engines already exist (Q07/Q07b/Q07c), the atlas surfaces already exist (page 6 popstats with placeholders, page 7 ancestry, planned genome-wide overview). What's missing is the daemon that wraps the engines into HTTP endpoints and the atlas-side UX for triggering and animating recomputes.

This is real work — ~12-17 turns across daemon + atlas + UX — but it's the work that justifies the engines existing in the first place.

If you want to commit to it, the right first move is **Stage A** (the daemon, server-side, Python or Go ~300 lines). Test it works with curl. Then Stage B brings the atlas online. Stages C-E are polish.

If you want to keep the simpler precomputed-only path (Q08 + Q09 emitters from the previous spec) and skip the live spec for now, that's also defensible — it ships faster and covers the manuscript figures. The live spec is for the *exploration* mode, not the publication mode.

I'd argue: do both. The Q08/Q09 emitters ship the manuscript-ready static path in 1-3 turns. The live spec extends from there over many more turns. They're not mutually exclusive — the static path is the manuscript fallback, the live path is the interactive exploration tool. Atlas's static/live mode chip lets the user pick which mode they're in.
