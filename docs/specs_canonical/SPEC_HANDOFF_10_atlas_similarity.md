# HANDOFF 10 — Interactive scrubbable similarity matrix panel

**Goal**: add a scrollable per-chromosome dosage similarity matrix panel
to atlas Page 1. As the user scrubs the genome cursor, the catfish ×
catfish similarity matrix updates in real time. Scale (100 kb / 250 kb
/ 500 kb / 1 Mb) is user-selectable. Sample subset is user-selectable
(lasso in PCA panel, click on matrix axes, or TSV upload).

This is the **interactive UI** version of HANDOFF 9's per-candidate
analysis. Same math primitives, different deliverable: live
exploration vs. static paper figure.

**Status**: not started. Builds on HANDOFF 1 (per-window dosage data),
HANDOFF 2 (atlas UI shared rendering state), HANDOFF 9 (similarity-
matrix and block-detection algorithms).

**Audience**: a fresh chat where Claude implements the atlas-side
similarity-matrix panel. The chat should focus on UI integration and
client-side performance; the underlying math is in HANDOFF 9.

---

## What you're building

Visual layout addition to atlas Page 1:

```
┌────────────────────────────────────────────────────────────────┐
│ Genome track [chrom selector]    [position scrubber]            │
├────────────────────────────────────────────────────────────────┤
│ PCA panel               │ Heatmap panel (HANDOFF 2)             │
├─────────────────────────┴───────────────────────────────────────┤
│ Similarity matrix panel (THIS HANDOFF)                          │
│  ┌──────────────────────────────────────────┐                   │
│  │ ┌────────────────────────────────┐       │ Scale: [500kb▾]  │
│  │ │                                │       │ Window: 16.4-16.9 │
│  │ │   N×N similarity matrix        │       │ K_blocks: 4       │
│  │ │   colored by similarity        │       │ Silhouette: 0.71  │
│  │ │   axes colored by block ID     │       │                   │
│  │ │                                │       │ [Auto-detect blocks│
│  │ │                                │       │  ☑ Show overlay] │
│  │ └────────────────────────────────┘       │                   │
│  │                                           │ Selected: 226/226 │
│  │ Position track:                           │ [Lasso] [Reset]   │
│  │ ◄═══════════════[●]═════════════►        │                   │
│  └──────────────────────────────────────────┘                   │
├─────────────────────────────────────────────────────────────────┤
│ Tree panel (HANDOFF 5) │ Fingerprint track (HANDOFF 6)          │
└─────────────────────────────────────────────────────────────────┘
```

Real-time updates as the user:
- Scrubs the genome cursor (matrix re-renders for new window)
- Changes scale (matrix re-renders at new window size)
- Changes sample subset (matrix re-renders with subset's similarities)
- Switches chromosome (loads new dosage data, then renders)

---

## What this handoff is NOT

- **NOT a replacement for HANDOFF 9.** HANDOFF 9 is the per-candidate
  paper-figure pipeline. This is the interactive exploration tool. Both
  call the same math.
- **NOT a discovery tool by itself.** It's a visualization of structure
  the user is investigating. Discovery comes from upstream local PCA /
  D17 / HANDOFF 1 producer.
- **NOT a phylogenetic / evolutionary analysis tool.** It shows
  haplotype-sharing patterns; interpretation as ancestry / IBD requires
  HANDOFF 5 (tree) for confirmation.

---

## Naming convention

Same as HANDOFF 9: avoid "IBD" and "outer/inner inversion" until
validated. Use:
- "Local haplotype similarity matrix" or "Dosage similarity matrix"
- "Block structure" / "sample groups by similarity"
- "Major candidate" / "Internal candidate" before validation

The atlas UI labels match: panel title = "Local haplotype similarity",
status line says "K_blocks: 4" not "Detected nested inversion."

---

## Core architectural decision: client-side computation

For real-time scrolling, similarity matrices must compute on demand
without server round-trips.

### Why not pre-compute everything

- 4 scales × ~12,000 window positions per chromosome × 226² × 4 bytes
  ≈ ~10 GB per chromosome
- Storage prohibitive
- Adding a scale requires regenerating

### Why not server-side on demand

- Each scrub event requires a round-trip
- Network latency makes scrubbing laggy
- Requires server-side state and caching

### The client-side approach

Per chromosome (or per region, depending on browser memory):
1. Server ships **per-marker dosage matrix** as compact binary (one byte
   per dosage value, scaled 0-255 mapping to 0-2 dosage range)
2. Client computes per-window similarity matrix in JS on demand as the
   cursor moves
3. Each matrix computation: ~226² × n_markers_in_window × ~50 ns
   ≈ 2 ms for 250 kb window with default SNP density
4. Sub-second response; faster than human perception of scrubbing

### Memory budget

- Dosage matrix per chromosome: 226 samples × ~50,000 markers × 1 byte
  ≈ 11 MB
- Per-marker positions: 50,000 × 4 bytes = 200 kB
- Cached recent similarity matrices: ~10 × 226² × 4 bytes = 2 MB
- Total: ~15 MB per chromosome resident in browser

For LG28 specifically (~50,000 markers in candidate region): well under
typical browser tab memory limits.

### Marker density consideration

Different chromosomes have different SNP densities. The fingerprinter
(HANDOFF 6) and dosage clustering (HANDOFF 8) used 50 kb windows
because at typical density that gives ~250 SNPs per window, which is
plenty for similarity computation. Same logic here:

| Scale | Typical SNP count per window | Reliability |
|---|---|---|
| 100 kb | ~500 SNPs | high |
| 250 kb | ~1,250 SNPs | high |
| 500 kb | ~2,500 SNPs | very high |
| 1 Mb | ~5,000 SNPs | very high |

The 100 kb minimum scale is chosen because below this the matrix gets
noisy (fewer SNPs → noisier per-pair correlation). Above 1 Mb is
unnecessary detail for haplotype-block visualization at population
level.

---

## Pipeline architecture

```
                  ┌─────────────────────────────────┐
                  │ Server: per-chromosome dosage   │
                  │ matrix as binary blob (.bin)    │
                  │                                  │
                  │ Format: header + sample_ids +   │
                  │ marker_positions + dosages      │
                  └────────────┬────────────────────┘
                               │ fetch per chrom
                               ▼
                  ┌─────────────────────────────────┐
                  │ Browser: typed-array storage    │
                  │ Uint8Array: dosage matrix       │
                  │ Float32Array: marker positions  │
                  │ String[]: sample IDs            │
                  └────────────┬────────────────────┘
                               │
                               ▼
                  ┌─────────────────────────────────┐
                  │ User scrubs cursor              │
                  │  - Position changes             │
                  │  - Scale changes                │
                  │  - Sample selection changes     │
                  └────────────┬────────────────────┘
                               │
                               ▼
                  ┌─────────────────────────────────┐
                  │ Compute similarity matrix       │
                  │  for current window in JS:      │
                  │  1. Filter markers in window    │
                  │  2. Filter samples to selection │
                  │  3. Compute Pearson correlation │
                  │     between sample vectors      │
                  │  4. Cache the result            │
                  └────────────┬────────────────────┘
                               │
                               ▼
                  ┌─────────────────────────────────┐
                  │ Detect blocks (optional)         │
                  │  - Hierarchical clustering on   │
                  │    similarity matrix            │
                  │  - Adaptive K cut               │
                  │  - Color sample axes by block   │
                  └────────────┬────────────────────┘
                               │
                               ▼
                  ┌─────────────────────────────────┐
                  │ Render matrix to canvas          │
                  │  - Cell color: similarity value  │
                  │  - Axis annotation: block IDs    │
                  │  - Status line: K, silhouette    │
                  └─────────────────────────────────┘
```

Cache step is critical: for unchanged window/scale/selection
combinations, return cached matrix. LRU cache of last 20 matrices
gives near-instant scrubbing within a region.

---

## Stage 1: server-side dosage data export

Per chromosome, write a binary blob the client can fetch:

```
Layout (.bin file):
  [header]
    magic: 4 bytes (e.g., "DOSv1")
    n_samples: 4 bytes (uint32)
    n_markers: 4 bytes (uint32)
    chrom_name: variable, null-terminated
  [sample_ids]
    n_samples × variable, null-terminated strings
  [marker_positions]
    n_markers × 4 bytes (uint32, bp position)
  [dosage matrix]
    n_samples × n_markers × 1 byte
    encoded as round(dosage * 127) where dosage ∈ [0, 2]
    so byte 0 = dosage 0, byte 127 = dosage 1, byte 254 = dosage 2
    byte 255 = missing
```

Generated by an R/Python preprocessor from the filtered Beagle:

```bash
Rscript export_dosage_binary.R \
  --beagle bi_baseline.beagle.gz \
  --beagle_sidecar bi_baseline.beagle.pairs.tsv \
  --chrom C_gar_LG28 \
  --out atlas_data/dosage/LG28.bin
```

For 226 samples × 50,000 markers: ~11.5 MB binary file per chromosome.
Served as static file from CDN/server; browser fetches once per
chromosome session.

Plus a sidecar JSON for chromosome metadata:

```json
"atlas_data/dosage/LG28.json":
{
  "chrom": "C_gar_LG28",
  "n_samples": 226,
  "n_markers": 50234,
  "min_position": 12345,
  "max_position": 28456789,
  "marker_density_per_mb": 1745,
  "binary_url": "atlas_data/dosage/LG28.bin",
  "binary_sha256": "abc123...",
  "produced_at": "2026-05-10T18:00:00Z"
}
```

This sidecar tells the client what to expect before fetching the
binary.

### Multi-chromosome export

Per-chromosome files keep memory usage bounded; the user typically
investigates one chromosome at a time. A multi-chromosome index points
to all chromosome files:

```json
"atlas_data/dosage/index.json":
{
  "chromosomes": [
    {"chrom": "C_gar_LG01", "binary_url": "LG01.bin", "metadata_url": "LG01.json"},
    {"chrom": "C_gar_LG02", "binary_url": "LG02.bin", "metadata_url": "LG02.json"},
    ...
  ]
}
```

---

## Stage 2: client-side data loading

When a user enters atlas Page 1 with similarity-matrix panel enabled:

```javascript
class DosageMatrixCache {
  constructor() {
    this.chromosomes = new Map();   // chrom -> {dosage, samples, positions}
    this.matrixCache = new LRUCache(20);  // window-key -> similarity matrix
  }

  async loadChromosome(chrom) {
    if (this.chromosomes.has(chrom)) return this.chromosomes.get(chrom);

    // Fetch binary
    const response = await fetch(`atlas_data/dosage/${chrom}.bin`);
    const buffer = await response.arrayBuffer();
    const view = new DataView(buffer);

    // Parse header
    let offset = 4;   // skip magic
    const nSamples = view.getUint32(offset, true); offset += 4;
    const nMarkers = view.getUint32(offset, true); offset += 4;

    // Skip chrom_name (null-terminated)
    while (view.getUint8(offset) !== 0) offset++;
    offset++;

    // Sample IDs (null-terminated)
    const samples = [];
    for (let i = 0; i < nSamples; i++) {
      const start = offset;
      while (view.getUint8(offset) !== 0) offset++;
      samples.push(new TextDecoder().decode(buffer.slice(start, offset)));
      offset++;
    }

    // Marker positions
    const positions = new Uint32Array(buffer, offset, nMarkers);
    offset += nMarkers * 4;

    // Dosage matrix
    const dosage = new Uint8Array(buffer, offset, nSamples * nMarkers);

    const data = { samples, positions, dosage, nSamples, nMarkers };
    this.chromosomes.set(chrom, data);
    return data;
  }
}
```

Loading 11 MB takes ~1 second on typical connections. After load, all
operations are local.

---

## Stage 3: similarity matrix computation per window

```javascript
function computeSimilarityMatrix(chromData, windowStart, windowEnd, sampleSubset) {
  const { samples, positions, dosage, nMarkers } = chromData;
  const nSamples = sampleSubset.length;

  // Find markers in window via binary search
  const startIdx = binarySearchFirstGE(positions, windowStart);
  const endIdx = binarySearchFirstGE(positions, windowEnd);
  const nMarkersInWindow = endIdx - startIdx;

  if (nMarkersInWindow < 20) {
    return { matrix: null, K: 0, reason: "insufficient_markers" };
  }

  // Compute mean & SD per sample for Pearson denominator
  const sampleMeans = new Float32Array(nSamples);
  const sampleSDs = new Float32Array(nSamples);

  for (let s = 0; s < nSamples; s++) {
    const sampleIdx = sampleSubset[s];
    let sum = 0, sumSq = 0;
    for (let m = startIdx; m < endIdx; m++) {
      const v = dosage[sampleIdx * chromData.nMarkers + m];
      if (v === 255) continue;   // skip missing
      const d = v / 127;          // decode dosage
      sum += d;
      sumSq += d * d;
    }
    sampleMeans[s] = sum / nMarkersInWindow;
    sampleSDs[s] = Math.sqrt(sumSq / nMarkersInWindow - sampleMeans[s] ** 2);
  }

  // Pearson correlation matrix
  const matrix = new Float32Array(nSamples * nSamples);
  for (let i = 0; i < nSamples; i++) {
    matrix[i * nSamples + i] = 1.0;   // diagonal
    for (let j = i + 1; j < nSamples; j++) {
      let cov = 0;
      const iIdx = sampleSubset[i];
      const jIdx = sampleSubset[j];
      for (let m = startIdx; m < endIdx; m++) {
        const vi = dosage[iIdx * chromData.nMarkers + m];
        const vj = dosage[jIdx * chromData.nMarkers + m];
        if (vi === 255 || vj === 255) continue;
        const di = vi / 127, dj = vj / 127;
        cov += (di - sampleMeans[i]) * (dj - sampleMeans[j]);
      }
      cov /= nMarkersInWindow;
      const corr = cov / (sampleSDs[i] * sampleSDs[j]);
      matrix[i * nSamples + j] = corr;
      matrix[j * nSamples + i] = corr;
    }
  }

  return { matrix, nSamples, nMarkersInWindow, samples: sampleSubset.map(i => samples[i]) };
}
```

For 226 samples × 1250 markers (250 kb window): ~64 million ops →
~50 ms in JS. Fast enough for real-time.

For larger samples (e.g., 500+) or larger windows, consider
WebAssembly implementation. For 226 samples, plain JS is sufficient.

### Cache key

```javascript
function cacheKey(chrom, windowStart, windowEnd, sampleSubset) {
  // Sample subset hash: short hash of sorted indices
  const subsetHash = simpleHash(Array.from(sampleSubset).sort().join(","));
  return `${chrom}:${windowStart}-${windowEnd}:${subsetHash}`;
}
```

LRU cache of 20 entries gives near-instant scrubbing within a region.

---

## Stage 3.5: polarity modes (NEW)

The interactive panel supports the same four polarity-correction modes
as HANDOFF 8 Stage 1.5. The math is identical; this section documents
how the modes plug into the live UI and how the panel switches between
them.

**Why polarity matters for the live panel**: in `raw_scan` mode the
panel works fine for *detecting* block structure but the matrix cells
will look noisier because markers with opposite polarity contribute
opposing signs that get absorbed by the absolute-correlation operator.
In corrected modes the matrix becomes visually cleaner and block
boundaries sharper. Switching modes during exploration lets the user
see both the discovery view (raw) and the publication view (corrected)
without re-running offline analysis.

### The four modes (UI presentation)

| Mode | Similarity formula | UI behavior |
|---|---|---|
| `raw_scan` | `\|cor(D_i, D_j)\|` (absolute Pearson) | Default on chromosome load. Works without any prior group definition. |
| `polarity_corrected_outer` | `cor(D_i_corrected, D_j_corrected)` where markers are flipped to align with outer contrast | Available after the user has identified an outer candidate (via PCA panel band assignment, or via a candidate from upstream pipeline) |
| `polarity_corrected_inner` | Same formula, markers flipped to align with inner contrast within one outer stratum | Available after outer + inner reference groups defined; `ASK QUENTIN: implementation details — see HANDOFF 8 Stage 1.5 Mode 3 open questions` |
| `hierarchical_u_v` | Two parallel matrices: outer-layer markers and inner-layer markers each contribute their own correlation matrix | Available after both axes defined; `ASK QUENTIN: implementation details — see HANDOFF 8 Stage 1.5 Mode 4 open questions` |

### UI control

Add a polarity-mode dropdown next to the scale selector:

```html
<select id="polarity_mode_selector">
  <option value="raw_scan" selected>Raw (no correction)</option>
  <option value="polarity_corrected_outer">Outer-corrected</option>
  <option value="polarity_corrected_inner" disabled>Inner-corrected (define groups first)</option>
  <option value="hierarchical_u_v" disabled>Hierarchical u/v (define groups first)</option>
</select>
```

Modes 2-4 start disabled and are enabled progressively as the user
defines reference groups (via PCA lasso, click-to-assign, or upload).

### Precomputed flip vectors

Polarity correction is a per-marker decision (flip or don't flip).
Once the user defines reference groups, compute the flip vector once
and cache it; the live similarity computation just reads the
appropriate dosage value (or 2 - dosage if flipped) at each marker.

```javascript
// When user defines outer reference groups via PCA lasso:
function computeFlipVectorOuter(refPosSamples, refNegSamples) {
  const { dosage, nMarkers, nSamples } = state.chromData;
  const flipOuter = new Uint8Array(nMarkers);   // 0 = keep, 1 = flip

  for (let m = 0; m < nMarkers; m++) {
    let posSum = 0, posCount = 0, negSum = 0, negCount = 0;
    for (const sIdx of refPosSamples) {
      const v = dosage[sIdx * nMarkers + m];
      if (v !== 255) { posSum += v / 127; posCount++; }
    }
    for (const sIdx of refNegSamples) {
      const v = dosage[sIdx * nMarkers + m];
      if (v !== 255) { negSum += v / 127; negCount++; }
    }
    const contrast = (posSum / posCount) - (negSum / negCount);
    flipOuter[m] = contrast < 0 ? 1 : 0;
  }
  return flipOuter;
}
```

### Switched dosage lookup

In the similarity computation (Stage 3), wrap the dosage read with
the flip vector:

```javascript
function getDosage(dosage, sampleIdx, markerIdx, nMarkers, flipVector) {
  const raw = dosage[sampleIdx * nMarkers + markerIdx];
  if (raw === 255) return null;   // missing
  const decoded = raw / 127;
  if (flipVector && flipVector[markerIdx]) {
    return 2 - decoded;
  }
  return decoded;
}
```

Performance impact is negligible (one extra branch per marker read).

### Mode switching invalidates cache

Changing polarity mode invalidates the similarity matrix cache:

```javascript
function onPolarityModeChange(newMode) {
  state.polarityMode = newMode;
  state.flipVector = computeFlipVectorForMode(newMode);
  matrixCache.clear();   // all cached matrices used the old polarity
  rerenderCurrentWindow();
}
```

The cache invalidation is acceptable: switching polarity mode is a
deliberate user action, not a frequent scrubber event. Recomputing
the current window's matrix after a mode switch takes ~50 ms.

### How reference groups get into the panel

Three paths, mirroring sample selection mechanisms:

1. **PCA panel band assignment**: when the user has band assignments
   from the local PCA in the candidate region (HOM1/HET/HOM2),
   selecting "Use PCA bands as outer reference" sets the flip vector
   from those band assignments
2. **Lasso two groups**: lasso once for "positive" reference
   (e.g., HOM2-like cluster), again for "negative" reference
   (HOM1-like cluster); the panel computes flip vector from these
3. **TSV upload**: two-column file with `sample_id` and
   `reference_group ∈ {pos, neg}` defines the contrast directly

For Mode 3 (inner) and Mode 4 (hierarchical), the user provides two
sets of reference groups: outer (HOM1 vs HOM2) and inner (HOM2.A vs
HOM2.B within the relevant outer stratum). The panel UI gates these
behind a wizard:

```
[1] Define outer reference  [Lasso] [PCA bands] [Upload]
[2] Define inner reference  [Lasso] [Upload]
       (only enabled after step 1)
[3] Choose mode  [Outer] [Inner] [Hierarchical u/v]
```

### Visual annotation when polarity is corrected

When a corrected mode is active, annotate the panel header:

```
Local haplotype similarity   |   Mode: Outer-corrected   |   Reference: 60 vs 60 samples
Window: 16.4-16.9 Mb (500 kb) |  Markers: 1247 (412 flipped) | K_blocks: 3 | Sil: 0.82
```

This keeps the user oriented about which mode is in effect, since
the matrix appearance changes between modes.

### Recommended workflow

1. Load chromosome → starts in `raw_scan` mode
2. Scrub to find structured regions (matrix shows blocks via abs-
   correlation)
3. Use PCA panel to identify outer band assignments in the strongest-
   structure region
4. Switch to `polarity_corrected_outer` mode → cleaner matrix, sharper
   blocks
5. If the matrix shows asymmetric subdivision (one block looks
   internally heterogeneous), define inner reference within that
   block
6. Switch to `hierarchical_u_v` mode → see two layers separately

This workflow can also be reversed: a user with a known nested
candidate from offline analysis can jump straight to Mode 4 by
uploading reference TSVs.

---

## Stage 4: block detection (optional overlay)

When the user toggles "Show blocks," run hierarchical clustering on
the current matrix:

```javascript
function detectBlocks(simMatrix, nSamples, options = {}) {
  const { sigThreshold = 0.4, minBlockSize = 10, maxK = 6 } = options;

  // Convert similarity to distance matrix (in-place, since we just need it once)
  const distMatrix = new Float32Array(nSamples * nSamples);
  for (let i = 0; i < nSamples * nSamples; i++) {
    distMatrix[i] = 1 - simMatrix[i];
  }

  // Use a JS hierarchical clustering library (e.g., ml-hclust)
  // or implement Ward.D2 directly
  const linkage = hclustWard(distMatrix, nSamples);

  // Try K = 1..maxK, pick best by silhouette + min block size
  let bestK = 1, bestSil = 0, bestAssignment = new Uint8Array(nSamples);
  for (let K = 2; K <= maxK; K++) {
    const cl = cutLinkage(linkage, K);
    const sizes = countSizes(cl);
    if (Math.min(...sizes) < minBlockSize) continue;
    const sil = computeSilhouette(cl, distMatrix, nSamples);
    if (sil > bestSil && sil > sigThreshold) {
      bestK = K;
      bestSil = sil;
      bestAssignment = cl;
    }
  }

  return { K: bestK, silhouette: bestSil, assignment: bestAssignment };
}
```

For 226 samples, hierarchical clustering is ~10 ms in JS. Block
detection adds minimal overhead.

### Visual output

Per-axis colored bars showing block ID for each sample. Border lines
on the matrix at block boundaries. Status line:

```
Window: 16.4-16.9 Mb (500 kb)   Markers: 1247   K_blocks: 4   Silhouette: 0.71
```

---

## Stage 5: rendering to canvas

```javascript
function renderMatrix(canvas, simMatrix, blocks, sampleOrder) {
  const ctx = canvas.getContext('2d');
  const nSamples = blocks.assignment.length;
  const cellSize = canvas.width / nSamples;

  // 1. Draw similarity cells (color by similarity value)
  for (let i = 0; i < nSamples; i++) {
    for (let j = 0; j < nSamples; j++) {
      const sim = simMatrix[sampleOrder[i] * nSamples + sampleOrder[j]];
      ctx.fillStyle = similarityColor(sim);   // diverging colormap
      ctx.fillRect(j * cellSize, i * cellSize, cellSize, cellSize);
    }
  }

  // 2. Draw block boundaries
  if (blocks && blocks.K > 1) {
    ctx.strokeStyle = 'black';
    ctx.lineWidth = 1;
    let prevBlock = -1;
    for (let i = 0; i < nSamples; i++) {
      const block = blocks.assignment[sampleOrder[i]];
      if (block !== prevBlock && i > 0) {
        ctx.strokeRect(0, i * cellSize, canvas.width, 0);  // horizontal
        ctx.strokeRect(i * cellSize, 0, 0, canvas.height); // vertical
      }
      prevBlock = block;
    }
  }

  // 3. Draw axis color bars (block IDs)
  // (separate small canvases on top and left)
}
```

Sample order: hierarchical clustering's leaf order ensures within-block
samples are adjacent. Computed when block detection runs; stored in
state.

For 226 samples, canvas is ~600×600 px (cell size ~2.6 px). Fast enough
to redraw on each scrub event without flickering.

### Color scheme

Similarity value range typically [-0.5, 1.0]:
- Diverging colormap: blue (low/negative) → white (zero) → red (high)
- Diagonal forced to red (sim = 1.0 by construction)

Using ColorBrewer "RdBu" or matplotlib "coolwarm" for paper-grade
appearance.

---

## Stage 6: UI controls and integration

### Top of panel: scale and chromosome selector

```html
<div id="similarity_controls">
  <select id="chrom_selector">
    <option value="C_gar_LG01">LG01</option>
    <option value="C_gar_LG02">LG02</option>
    ...
  </select>
  <select id="scale_selector">
    <option value="100000">100 kb</option>
    <option value="250000" selected>250 kb</option>
    <option value="500000">500 kb</option>
    <option value="1000000">1 Mb</option>
  </select>
  <button id="show_blocks_toggle">Show blocks</button>
  <button id="lasso_button">Lasso select</button>
  <button id="reset_selection">All samples</button>
</div>
```

### Position scrubber (genome track within the panel)

A horizontal mini-track showing the chromosome with a draggable cursor.
Cursor position = window center. Width of highlighted region = window
size. As user drags:

```javascript
function onScrubberDrag(newPos) {
  const windowStart = newPos - state.scale / 2;
  const windowEnd = newPos + state.scale / 2;
  const cacheKey = makeCacheKey(state.chrom, windowStart, windowEnd, state.selectedSamples);

  let result;
  if (matrixCache.has(cacheKey)) {
    result = matrixCache.get(cacheKey);
  } else {
    result = computeSimilarityMatrix(chromData, windowStart, windowEnd, state.selectedSamples);
    if (state.showBlocks) {
      result.blocks = detectBlocks(result.matrix, result.nSamples);
    }
    matrixCache.set(cacheKey, result);
  }

  renderMatrix(canvas, result.matrix, result.blocks, getSampleOrder(result));
  updateStatus(result);
}
```

Throttled to ~30 fps via requestAnimationFrame so dragging stays
smooth even on slow machines.

### Keyboard shortcuts

- Arrow left/right: step cursor by half-window
- Page up/down: step by full window
- Home/End: jump to chromosome start/end
- + / -: cycle through scales
- Enter: snap cursor to nearest candidate boundary

### Lasso integration

When user clicks "Lasso select":
1. Switches PCA panel into lasso mode
2. User draws a region around samples in PC space
3. Lasso resolves to a `Set<sampleIndex>`
4. Set is written to `state.selectedSamples`
5. All panels (matrix, heatmap, etc.) re-render with the subset

The same mechanism applies in reverse: clicking a row label in the
similarity matrix toggles that sample's inclusion in `selectedSamples`.

### TSV upload

```html
<button id="upload_subset">Load samples from TSV</button>
<input type="file" id="subset_file" accept=".tsv" hidden>
```

Parse on file change:

```javascript
async function loadSampleSubsetFromFile(file) {
  const text = await file.text();
  const lines = text.split('\n').map(l => l.trim()).filter(Boolean);
  const wantedSamples = new Set(lines);
  const indices = [];
  state.chromData.samples.forEach((s, i) => {
    if (wantedSamples.has(s)) indices.push(i);
  });
  state.selectedSamples = indices;
  rerenderAll();
}
```

---

## Stage 7: cross-panel coordination (shared rendering state)

The shared rendering state from HANDOFF 2 Section 10 already covers:
- `view_name` / `weighting` / `anchor_mode` / `centering` /
  `polarity_reference` (from PCA/heatmap controls)
- `sample_order` / `sample_color_mode` / `selected_samples`
- `hover_sample` / `hover_marker`

This handoff adds:

| New state field | Set by | Read by |
|---|---|---|
| `similarity_chrom` | Chrom selector in panel | Similarity matrix panel |
| `similarity_window_pos` | Scrubber drag | Similarity matrix panel; genome cursor sync |
| `similarity_scale` | Scale selector | Similarity matrix panel |
| `similarity_show_blocks` | Show blocks toggle | Similarity matrix panel |

Coordination rules:
- When the genome cursor moves in another panel (PCA scrubber), the
  similarity-matrix scrubber follows
- When user drags similarity-matrix scrubber, other panels follow
- `selected_samples` change in any panel propagates everywhere
- Hover linkage: hover a sample row in similarity matrix → highlight
  the same sample in PCA + heatmap

This is achieved via the existing event bus in HANDOFF 2; no new
mechanism needed.

---

## Stage 7.5: scale-suggestion track shared with HANDOFF 8 (NEW)

The scrollable panel sits visually between (or alongside) HANDOFF 8's
dosage curves panel and shares a synchronized scrubbing experience.
The scale-suggestion track between them tells the user when to switch
scale (100 kb / 250 kb / 500 kb / 1 Mb) at the current cursor
position.

### What this panel adds

A horizontal mini-track sitting just above the matrix, replacing or
augmenting the simple position scrubber from Stage 6. The track shows:

```
Scale-suggestion track:
   100 kb │░░░░░▒▒▒▓▓▒▒▒▒░░░░░░░░░░░ │
   250 kb │░░░░▓▓▓▓▓▓▓▓▓▒▒░░░░░░░░░░ │ ★ recommended at cursor
   500 kb │░░░▓▓▓▓▓▓▓▓▓▓▓▒░░░░░░░░░░ │
     1 Mb │░░░▓▓▓▓▓▓▓▓▓▓▓▓▓░░░░░░░░░ │
   K=1 ░  K=3 ▓  K=4+ ▓  silhouette: low░ high▓
   cursor → ▼
```

Color = block count × silhouette at each (scale, position). The user
can:
- See at a glance where structured regions are at each scale
- Click directly on a scale row at a given position to jump there
- See which scale is recommended at the current cursor (★)

### Data source

The track reads from the per-chromosome scale-suggestion data
generated alongside the dosage binary blob:

```
atlas_data/dosage/LG28.bin                  (Stage 1 binary)
atlas_data/dosage/LG28.json                 (chromosome metadata)
atlas_data/scale_suggestion/LG28.json       (scale × position summary)
```

The scale-suggestion data is small (~100 kB per chromosome at four
scales), generated once during the preprocessing step that produces
the binary dosage blob. Per-chromosome generation:

```r
# Run alongside Stage 1 export
for (scale in c(100000, 250000, 500000, 1000000)) {
  step <- scale / 4
  positions <- seq(chrom_start, chrom_end, by = step)
  for (pos in positions) {
    sim_mat <- compute_similarity(chrom_data, pos, pos + scale)
    blocks <- detect_blocks(sim_mat)
    summary[[scale]][[as.character(pos)]] <- list(
      K = blocks$K, sil = blocks$silhouette
    )
  }
}
write_json(summary, "atlas_data/scale_suggestion/LG28.json")
```

Per chromosome, this is ~10,000 windows × 4 scales × 226² similarity
computations → ~30 minutes server-side. Acceptable as a one-time
preprocessing cost.

### Interaction with the live matrix

When the user clicks on the scale-suggestion track at position `p` and
scale `s`:

```javascript
function onSuggestionTrackClick(scale, position) {
  state.scale = scale;
  state.cursorPos = position;
  state.scaleDropdown.value = scale;   // sync the dropdown
  rerenderMatrix();
}
```

The user can also drag along the track to scrub at a different scale
than the current one — useful for "I want to see this region at
multiple scales quickly."

### When the recommended scale differs from current scale

Visual indicator: a small ★ next to the scale dropdown when the panel's
algorithm thinks a different scale would show structure better. The
user can click the ★ to accept the recommendation or ignore it.

```
Scale: [500 kb ▾] ★ Try 250 kb
```

The recommendation is computed from the scale-suggestion data:

```javascript
function recommendedScaleAt(cursorPos) {
  let bestScore = 0;
  let bestScale = state.scale;
  for (const scale of [100000, 250000, 500000, 1000000]) {
    const summary = scaleSuggestionData[scale];
    const nearestPos = nearestSampledPosition(summary, cursorPos);
    const score = (summary[nearestPos].K - 1) * summary[nearestPos].silhouette;
    if (score > bestScore) {
      bestScore = score;
      bestScale = scale;
    }
  }
  return bestScale;
}
```

Updated on each cursor move. Only show the ★ if `bestScale !==
state.scale` and `bestScore > 0.5` (some meaningful structure exists
at the recommended scale).

### Cross-panel cursor synchronization

The cursor position propagates to/from HANDOFF 8's dosage-curves
panel. The user drags the cursor on either panel; both update.

State machine:
- User drags cursor on HANDOFF 10 matrix scrubber → updates
  `state.cursorPos`
- HANDOFF 8 listens for `state.cursorPos` change → vertical line on
  curves panel moves to new position
- Conversely: user drags cursor on HANDOFF 8 curves → matrix in
  HANDOFF 10 re-renders for that position

This is done via the existing shared rendering state event bus from
HANDOFF 2; both panels are subscribers of `cursorPos` and `scale`.

### Display modes

The scale-suggestion track has two display modes:

1. **Compact (default)**: 4 thin rows (one per scale), color-coded by
   block-count × silhouette
2. **Expanded**: separate K_blocks track and silhouette track per
   scale, more detail; toggled via a small button

Compact mode is suitable for typical use; expanded mode helps when
debugging unusual signals or writing a paper figure.

### Recommended workflow integrating both panels

1. Open atlas, load chromosome → both panels show flat curves /
   uniform matrix outside candidates
2. Scroll to candidate region → curves diverge into 3 clusters,
   matrix gains 3 blocks; scale-suggestion track shows strong signal
   at 500 kb
3. Continue scrolling within candidate → if scale-suggestion track
   shows higher block count at 250 kb than at 500 kb at some
   position, user has a hint that **inner structure exists here at
   finer scale**
4. Click ★ to switch to 250 kb → matrix re-renders at finer scale,
   showing inner subdivision
5. Switch polarity mode to `polarity_corrected_outer` for cleaner
   visualization at the figure-grade resolution

This workflow mirrors the offline pipeline (HANDOFF 8 + 9 + 7) but
makes it interactive and visual.

---

## Stage 8: performance optimizations

### Web Workers for computation

For very large sample sets (>500), move similarity computation to a
Web Worker so the main thread stays responsive:

```javascript
const worker = new Worker('similarity-worker.js');
worker.postMessage({
  command: 'compute',
  dosage: chromData.dosage,
  positions: chromData.positions,
  windowStart, windowEnd,
  sampleSubset
});
worker.onmessage = (e) => {
  const result = e.data;
  matrixCache.set(cacheKey, result);
  renderMatrix(canvas, result.matrix, result.blocks);
};
```

For 226 samples, single-threaded JS is fast enough; Web Worker is a
future optimization.

### WebGL rendering

For matrix rendering of larger sample sets, WebGL with a single
fragment shader rendering the matrix from a uniform buffer is much
faster than canvas 2D context. For 226 samples, canvas 2D is sufficient.

### Prefetching

When the user pauses on a position, prefetch matrices for the next/
previous windows:

```javascript
function onScrubberPause(currentPos) {
  setTimeout(() => {
    prefetchMatrix(state.chrom, currentPos + state.scale, state.scale);
    prefetchMatrix(state.chrom, currentPos - state.scale, state.scale);
  }, 200);
}
```

---

## Stage 9: visual diagnostic features

### Detected-block annotations

When K_blocks ≥ 2 is detected, annotate above the matrix:

```
Block 1: 60 samples (HOM1-like)
Block 2: 106 samples (HET-like)
Block 3: 60 samples (HOM2-like)
```

(Names are inferred from PCA cluster correspondence if available, else
just numbered.)

### Similarity-vs-position track

Below the matrix, a per-window mini-track showing K_blocks vs position
across the chromosome (computed by sampling matrices at fixed
intervals). Lets the user see at a glance where block structure exists
along the genome.

### Subsample mode

A "show only N most variable samples" option for working with large
cohorts. Reduces matrix dimensions while preserving the strongest
signal samples.

---

## Stage 9.5: pairwise contrast overlay (NEW)

When blocks are detected (Stage 4), the user can click two block IDs
to see their pairwise dosage contrast curve overlaid on the dosage
curves panel (HANDOFF 8). This makes driver-segment identification
interactive: the user explores cluster pairs in real time and sees
exactly where in the genome each pair is separated.

### What the user sees

After block detection produces K block labels visible on the matrix
axes, the panel adds clickable affordances:

```
┌─ Similarity matrix panel ─────────────────────────────┐
│ ┌─────────────────────────────────┐                   │
│ │  [Matrix with block bars]       │ K_blocks: 4       │
│ │  ┌─[B1]─┐                       │ Sil: 0.71         │
│ │  │      │                       │                   │
│ │  └──────┘                       │ Block click mode: │
│ │   ┌──[B2]──┐                    │ ☑ Pairwise contrast│
│ │   │        │                    │                   │
│ │   └────────┘                    │ Selected blocks:  │
│ │              ┌──[B3]──┐         │   B1 vs B3 ▾      │
│ │              │        │         │                   │
│ │              └────────┘         │ [Show contrast]   │
│ │                       ┌─[B4]─┐  │                   │
│ │                       │      │  │                   │
│ │                       └──────┘  │                   │
│ └─────────────────────────────────┘                   │
└────────────────────────────────────────────────────────┘
            ▼
┌─ Pairwise contrast curve panel (overlay on HANDOFF 8) ─┐
│ effect size                                            │
│  3 │                ╭──╮                               │
│    │              ╱     ╲                              │
│  2 │            ╱         ╲       ← driver segment     │
│    │          ╱             ╲                          │
│  1 │ ───────                  ───────                  │
│    │                                                   │
│  0 │                                                   │
│    └──────────────────────────────────────────────►    │
│      15.0    15.5    16.0    16.5    17.0    17.5      │
│                       ▼                                │
│                shape: inner_middle_only                │
│                driver: 16.4-16.7 Mb                    │
└────────────────────────────────────────────────────────┘
```

### Implementation

The pairwise contrast curve is computed client-side for the **current
window's local view** (faster) plus optionally the **full extended
interval** (slower but more informative).

```javascript
function computePairwiseContrast(chromData, blockA_samples, blockB_samples,
                                   intervalStart, intervalEnd, smoothBp = 100000) {
  const { dosage, positions, nMarkers } = chromData;
  const startIdx = binarySearchFirstGE(positions, intervalStart);
  const endIdx = binarySearchFirstGE(positions, intervalEnd);

  const delta = new Float32Array(endIdx - startIdx);
  const effect = new Float32Array(endIdx - startIdx);

  for (let m = startIdx; m < endIdx; m++) {
    let sumA = 0, countA = 0, sumSqA = 0;
    let sumB = 0, countB = 0, sumSqB = 0;

    for (const sIdx of blockA_samples) {
      const v = dosage[sIdx * nMarkers + m];
      if (v === 255) continue;
      const d = v / 127;
      sumA += d; sumSqA += d * d; countA++;
    }
    for (const sIdx of blockB_samples) {
      const v = dosage[sIdx * nMarkers + m];
      if (v === 255) continue;
      const d = v / 127;
      sumB += d; sumSqB += d * d; countB++;
    }
    if (countA < 2 || countB < 2) continue;

    const meanA = sumA / countA, meanB = sumB / countB;
    const varA = sumSqA / countA - meanA * meanA;
    const varB = sumSqB / countB - meanB * meanB;
    const pooledSD = Math.sqrt(((countA-1)*varA + (countB-1)*varB) / (countA + countB - 2));

    delta[m - startIdx] = meanA - meanB;
    effect[m - startIdx] = delta[m - startIdx] / Math.max(pooledSD, 0.05);
  }

  // Smooth in genomic space
  const smoothed = smoothLoess(effect, positions.subarray(startIdx, endIdx), smoothBp);

  return { delta, effect, smoothed,
           positions: positions.slice(startIdx, endIdx) };
}
```

Per-window: fast (~ same cost as one similarity matrix). Full
extended interval: ~5-10× slower but still sub-second for typical
candidates.

### UI flow

1. User toggles "Pairwise contrast" mode in the matrix panel
2. User clicks first block bar → block highlighted in color A
3. User clicks second block bar → block highlighted in color B
4. Panel computes contrast curve for blocks (A, B) over the
   currently-visible interval (or full chromosome if "full" toggled)
5. Curve renders below the dosage curves panel (HANDOFF 8 area)
6. Driver segments highlighted as colored bands under the curve
7. Status line shows shape classification: `inner_middle_only`,
   `outer_whole_interval`, `edge_or_adjacent`, `complex`, or
   `weak_or_noise`

The user can rapidly iterate: click two different blocks → see
contrast → click two new blocks → see new contrast. This is the
**interactive driver-segment exploration tool** that complements the
batch Stage 5.5 analysis.

### Cross-validation with offline Stage 5.5

When the user has already run HANDOFF 8 Stage 5.5 offline, the panel
can load the precomputed `driver_segments_per_pair.tsv` and show the
batch-computed driver segments as default annotations. The
interactive contrast then matches what the offline analysis found, or
diverges (interesting case worth investigating).

### Pairwise contrast matrix mini-view

Clicking "Show all pairs" generates the K × K contrast matrix grid
(see HANDOFF 8 Stage 5.5 visualization), rendered live in the atlas:

```
        B1     B2     B3     B4
B1     ───   wide   wide   wide+narrow
B2            ───   wide   wide+narrow
B3                  ───    narrow            ← inner driver: B3 vs B4
B4                          ───
```

Each cell is a tiny sparkline of the contrast curve; clicking a cell
expands it into the full curve view.

This grid is the same paper figure as HANDOFF 8 Stage 5.5d, available
live in the atlas instead of as a static PDF.

### Coordination with shared rendering state

The selected block pair (A, B) is held in shared state:

```javascript
state.contrastBlockA = blockIdA;
state.contrastBlockB = blockIdB;
state.contrastInterval = "current_window" | "full_chromosome";
```

When set, the dosage curves panel (HANDOFF 8) shows the contrast curve
overlay; the matrix panel highlights the two selected blocks. Other
panels (PCA, tree, fingerprint) get the same block-pair coloring for
the involved samples.

### Honest expected performance

- **Per-window contrast**: ~50 ms in JS for 226 samples × 1250 markers.
  Same cost as a similarity matrix update.
- **Full chromosome contrast**: ~500 ms - 2 s depending on chromosome
  size. Acceptable for occasional clicks but not for rapid iteration.
- **K × K matrix view**: K(K-1)/2 contrast computations. For K=8 → 28
  contrasts → 28 × 50 ms = 1.4 s window; or 28 × 1 s = ~30 s full
  chromosome. Tolerable when explicitly requested but not real-time.

### When to use this vs the offline Stage 5.5

| Use case | Tool |
|---|---|
| Exploration: which cluster pair is interesting? | This stage (live UI) |
| Specific question: where does B3 differ from B4? | This stage |
| Paper-figure quality, all pairs, with LOO validation | HANDOFF 8 Stage 5.5 (offline) |
| Reproducible analysis with logged thresholds | HANDOFF 8 Stage 5.5 |
| Architecture summary JSON for downstream | HANDOFF 8 Stage 5.5 |

The live UI is for hypothesis generation; the offline analysis is for
hypothesis confirmation and publication.

---

## Outputs

This handoff is primarily UI; outputs are the user's interactive
experience. Optional export:

- "Save current matrix as PNG" → PNG of canvas
- "Save current matrix as TSV" → upper-triangle similarity values as
  TSV (for offline analysis)
- "Save block assignments as TSV" → sample → block mapping

These are useful when the user finds an interesting pattern and wants
to capture it for a paper figure or further analysis. Each is a
single-button-click export.

---

## Driver

There's no command-line driver — this is a UI feature. The
preprocessing step (Stage 1, exporting binary dosage data) has a
driver:

```bash
# Per-chromosome export
bash export_chrom_dosage.sh \
  --beagle bi_baseline.beagle.gz \
  --beagle_sidecar bi_baseline.beagle.pairs.tsv \
  --chroms_list chromosomes.txt \
  --out_dir atlas_data/dosage/
```

Iterates over chromosomes, produces .bin and .json per chromosome plus
the index.json.

---

## Implementation phases

### Phase 1: data preprocessing (1 day)
- Server-side R script to export per-chromosome binary blobs
- Sidecar JSON metadata
- Index file across chromosomes

### Phase 2: client-side data loading (1 day)
- Fetch + parse binary blob into typed arrays
- Cache loaded chromosomes
- Show loading indicator during fetch

### Phase 3: similarity matrix computation (2 days)
- Vanilla JS implementation of Pearson correlation
- Cache layer
- Sample-subset filtering
- Performance benchmarking on 226 samples × various window sizes

### Phase 4: block detection (1 day)
- JS hierarchical clustering (use ml-hclust or implement Ward.D2)
- Adaptive K selection with silhouette + min block size
- Block assignment output

### Phase 5: rendering (1-2 days)
- Canvas 2D rendering of matrix
- Diverging colormap
- Block boundary lines
- Axis color bars
- Sample order from hierarchical clustering

### Phase 6: UI controls (2-3 days)
- Scale selector
- Chromosome selector
- Position scrubber (mini genome track)
- Show blocks toggle
- Lasso integration with PCA panel
- Sample subset upload
- Keyboard shortcuts

### Phase 7: cross-panel coordination (1 day)
- Wire to shared rendering state
- Hover linkage
- Selection propagation
- Cursor sync with other panels' scrubbers

### Phase 8: polish (1-2 days)
- Loading states
- Error messages (insufficient markers, chromosome not loaded)
- Status line updates
- Keyboard shortcut help
- Export buttons

Total ~10-12 days for full feature. **Phases 1-5 alone (5-7 days)
deliver the core scrubbable matrix without lasso integration or
cross-panel coordination** — sufficient for initial use.

---

## Honest expected performance

### Will work
- **Real-time scrubbing** at 100 kb / 250 kb / 500 kb / 1 Mb scales for
  226 samples. Per-window computation < 100 ms; rendering < 50 ms.
- **Sample subset filtering** by lasso, click, or upload — recomputes
  matrix instantly (subset is just a different sample list passed to
  the same function).
- **Block detection overlay** showing K_blocks and silhouette in real
  time. Adds ~10-20 ms per scrub event.
- **Cache hits** for revisited windows — instant response, no
  recomputation.

### Probably work
- **Chromosomes with ~100,000 markers** (high SNP density): fetch
  takes ~2 seconds; computation per window stays fast because the
  marker count per window is bounded by window size.
- **Cohorts up to ~500 samples**: still feasible but per-window
  computation grows quadratically (n_samples²). Above 500, move to
  Web Worker or WebAssembly.

### Honestly uncertain
- **Cohorts > 1000 samples**: rendering is fast enough but
  computation becomes the bottleneck. WebAssembly + Web Worker
  required. Out of scope for first version.
- **Chromosomes > 100 Mb with very high SNP density**: binary file
  exceeds 50 MB. Either compress (LZ4 / Zstd) or split into regions.
- **Mobile / low-memory browsers**: 11 MB chromosome data may strain
  some devices. Provide a "low memory" mode that fetches per-region
  on demand instead of full chromosome.

### Recommended use

Treat the similarity matrix panel as the **primary nesting-detection
visualization tool** for users who already know what to look for. The
panel makes nested architecture visually obvious in seconds: scrub
into a candidate, see 3 large blocks; scrub further, watch one block
subdivide into smaller sub-blocks; scrub past, watch the subdivision
return to the 3-block pattern.

This is the user-facing complement to HANDOFF 9's automated
classification. The atlas users can identify candidates by eye that
the algorithms might miss; the algorithms can flag candidates the
users might overlook.

---

## File map

```
mgl_adapter/                          (existing, HANDOFFs 0-4)
trees/                                (HANDOFF 5)
fingerprints/                         (HANDOFF 6)
nested/                               (HANDOFF 7)
dosage_clustering/                    (HANDOFF 8)
dosage_similarity/                    (HANDOFF 9)
atlas_similarity/                     (this handoff)
├── server/
│   └── export_chrom_dosage.R         (Stage 1)
├── client/
│   ├── data_loader.js                (Stage 2)
│   ├── similarity_compute.js         (Stage 3)
│   ├── block_detect.js               (Stage 4)
│   ├── matrix_render.js              (Stage 5)
│   ├── controls.js                   (Stage 6)
│   ├── coordination.js               (Stage 7)
│   ├── similarity-worker.js          (Stage 8 web worker)
│   └── similarity_panel.html         (panel template)
└── tests/
    ├── benchmark.html                (perf testing)
    └── synthetic_test.html           (correctness on synthetic data)

specs/
└── HANDOFF_10_atlas_similarity.md    (this document)
```

---

## What you can ignore

- **Whole-genome panoramic view** showing all chromosomes at once: out
  of scope. Users navigate one chromosome at a time.
- **Hierarchical similarity at multiple scales simultaneously**:
  showing 100 kb and 1 Mb in same view is confusing; let the user
  switch between scales.
- **Comparison of two chromosomes side by side**: nice-to-have future
  feature; first version is single chromosome.
- **Real-time IBD inference**: out of scope. We compute dosage
  similarity, not IBD. True IBD requires tools like hap-IBD or
  IBDseq, which would be separate offline analyses.

## Pointers to existing code

- HANDOFF 1's filtered Beagle (`bi_baseline.beagle.gz`) is the source
  for Stage 1's binary export.
- HANDOFF 2 Section 10 documents the shared rendering state pattern;
  this handoff plugs into it.
- HANDOFF 9 documents the per-window similarity-matrix algorithm and
  block-detection logic; reuse the math, not the I/O paths.

## External tools required

- Server-side: R packages from earlier handoffs (`data.table`, etc.)
- Client-side JS libraries:
  - `ml-hclust` or equivalent for hierarchical clustering
  - Optionally `wasm-blob` for WebAssembly correlation if scaling
    beyond 500 samples
  - LRU cache implementation (small dependency or hand-roll)

---

## Validation checks for LG28

1. **Matrix loads in <1 second** for LG28 (~50,000 markers).
2. **Window scrubbing at 250 kb scale** updates matrix in <100 ms per
   scrub event on a typical laptop.
3. **Outside the candidate (e.g., LG28:5-10 Mb)**: K_blocks should
   typically return 1 (no structure) at high silhouette; matrix is
   uniform low values.
4. **Inside the candidate at outer-only stretches (e.g., LG28:15.5-16.0
   or 17.0-17.5 Mb)**: K_blocks = 3, silhouette > 0.5; three clear
   blocks of ~60/106/60.
5. **Scale changes are smooth**: switching from 250 kb to 1 Mb
   re-renders within ~200 ms.
6. **Lasso selecting only HOM2 samples (n=60)**: matrix re-renders
   showing 60×60 patterns; if a nested inversion exists in HOM2 (none
   expected for LG28), it would be visible here as further
   subdivision.
7. **Sample TSV upload**: arbitrary subset list applies correctly;
   matrix dimensions update.

If LG28 shows clean 3-block structure across the candidate with the
expected ~60/106/60 sample counts, the panel is correctly calibrated
for application to other candidates.
