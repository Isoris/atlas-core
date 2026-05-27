# COPY_ORIGIN_PAINTING_SPEC — paralogue ancestry painting for breakpoint detection

**Status**: PARTIAL — Steps D + E shipped 2026-05-21 (audit). Steps A–C
remain data-bound and unimplemented. SPEC body below is preserved
verbatim from the 2026-05-08 chat origin.

**Implemented in (Steps D + E):**
- [`atlases/inversion/shared/copy_origin_painting.js`](../atlases/inversion/shared/copy_origin_painting.js) — 421 lines, pure-JS primitives
- [`tests/test_shared_copy_origin_painting.js`](../tests/test_shared_copy_origin_painting.js) — 250-line unit test suite
- Consumer: [`atlases/inversion/shared/inversion_classification.js`](../atlases/inversion/shared/inversion_classification.js) — `origin_mechanism` + `copy_origin_verdict` fields fed by the two exports below

**Public surface (shipped):**
- `classifyBreakpointMechanism(windows, opts)` — per-window paint sequence → `NAHR-compatible` / `TE-mediated` / `NHEJ/MMEJ-compatible` / `complex paralogue mosaic` / `replication-based` / `no mosaic evidence` (vocabulary matches SPEC §"Step D")
- `partitionPaintingByArrangement(samples, painting)` — HOM_A / HET / HOM_B copy-origin summary
- `interpretCopyOriginPattern(perGroup)` — cross-group verdict (`arrangement-specific SD mosaic` / `no copy-origin difference` / `complex rearrangement` / `low-PSV-density uncallable`)
- `COPY_ORIGIN_MECHANISMS` — frozen vocab table (six labels, all SPEC-compliant — "compatible" not "confirmed")

**Per-step status matrix:**

| step | scope                                                              | status |
|------|--------------------------------------------------------------------|--------|
| A    | Define paralogue copies (per-locus SD discovery)                   | ⏳ data-bound (PSV-calling pipeline upstream) |
| B    | Find paralogue-informative SNVs (PSVs)                             | ⏳ data-bound (depends on Step A) |
| C    | Paint reads/windows against the K paralogue copies                 | ⏳ data-bound (per-window Q vector input) |
| D    | Mechanism classification from per-window copy calls                | ✅ shipped — `classifyBreakpointMechanism` |
| E    | Arrangement-group partition + interpretation                       | ✅ shipped — `partitionPaintingByArrangement` + `interpretCopyOriginPattern` |
| F    | `05_breakpoint_switches.tsv` emission (TSV writer)                  | ⏳ deferred — pure-JS code computes the rows; the file writer is producer-side and lives in a future catfish-inversion-analysis stage |

**Audit summary (2026-05-21):**

The two pure-compute steps (D + E) are fully shipped with a 250-line test
suite covering the six mechanism labels, the three arrangement groups,
and the four interpretation verdicts. The exact "NAHR-compatible" /
"NHEJ/MMEJ-compatible" / "no mosaic evidence" wording mandated by the
SPEC §"Wording rules" is preserved verbatim in `COPY_ORIGIN_MECHANISMS`.
TE-mediated and replication-based refinements (caller-supplied flags)
are also implemented, slightly extending the SPEC's six-label vocabulary.

Steps A–C are upstream data-prep that depend on the catfish PSV-calling
pipeline (not yet producing PSVs at the per-locus resolution this
module needs). When that pipeline ships, the shared module here will
consume its output without further change to the public surface.

**Source**: user-provided text, 2026-05-08 chat.
**Position in pipeline**: complementary to Stage 4 — it runs as a
post-hoc per-candidate analysis on regions where the long-range
regimes pipeline (or any other SV caller) has flagged a candidate
breakpoint interval. It does NOT replace Stage 4; it characterises
the *mechanism* of breakpoints that Stage 4 already discovered.

## What this module is

A within-locus paralogue-aware classifier that assigns short sequence
windows (1–10 kb) to their most likely **source duplicated copy**.
Instead of population ancestry (A/B/C populations), the output is
**copy ancestry**: paralogue_1 / paralogue_2 / paralogue_3 / unknown
/ mixed.

It uses the same conceptual machinery as Quentin's existing
`instant_q` engine (C++ fixed-F EM in MODULE_2B's unified ancestry
module), but transposed:

| Quentin's `instant_q` (existing)          | Copy-Origin Painting (proposed)        |
|-------------------------------------------|----------------------------------------|
| K populations as ancestry sources         | K paralogous copies as origin sources  |
| ancestry-informative markers (AIMs)       | paralogue-informative SNVs (PSVs)      |
| per-sample Q vector (sum to 1)            | per-window Q vector over copies        |
| genome-wide chunks                        | per-breakpoint-locus windows           |
| population genetics                       | structural-variant mechanism inference |

This analogy is the spec's organising metaphor. If the audit chat
finds the analogy doesn't hold (e.g. PSV calling is too noisy for
EM-style soft assignment), the architecture should be revisited
before implementation.

## Output: one row per breakpoint candidate

The headline file. Everything else in the module exists to produce
this:

```
05_breakpoint_switches.tsv

candidate_id  chr     start_bp  end_bp     left_origin  right_origin
              switch_pos_bp     mechanism                      confidence

INV001        LG05    10000000  10100000   copy1        copy2
              10053200          NAHR-compatible                 high
INV002        LG08    22000000  22100000   copy1        unknown
              22045500          NHEJ/MMEJ-compatible            medium
INV003        LG12     4000000   4100000   copy1        copy3
              4022000           complex paralogue mosaic        medium
INV004        LG28   15115000  15116000   copy1        copy1
              NA                no mosaic evidence              n/a
```

**Wording rules** (mandatory):
- "NAHR-compatible", not "NAHR-confirmed."
- "NHEJ/MMEJ-compatible", not "NHEJ-confirmed."
- "no mosaic evidence" does **not** mean "no breakpoint." It means
  either no rearrangement OR a rearrangement between identical
  paralogous copies (invisible to this method). The audit chat
  should verify this distinction is preserved in every downstream
  consumer.

## Step A — define paralogue copies

For each segmental-duplication (SD) family, list all duplicated
copies in the assembly.

**File**: `01_copy_dictionary.tsv`

```
copy_id              chr     start_bp   end_bp     length_bp  family_id
SDfam001_copy1       LG05    10200000   10800000   600000     SDfam001
SDfam001_copy2       LG05    35100000   35700000   600000     SDfam001
SDfam001_copy3       LG12     4000000    4600000   600000     SDfam001
```

**Required upstream inputs**:
- SD calls from `SDquest`, `BISER`, or RepeatMasker-derived
  self-alignment. Quentin's `catfish-synteny-toolkit` (wfmash-based)
  may produce these; needs to be verified.
- The C. gariepinus Gar haplotype assembly (28 LGs).

**Edge cases to handle**:
- A family with only 1 "copy" → not actually duplicated → skip.
- A family with > 6 copies → high-copy repeat family, copy-origin
  painting becomes unreliable. Flag and either skip or run with a
  warning.
- Copies on the same chromosome at distance < 100 kb → may be
  recent tandem duplication; PSV density will be very low; flag.

## Step B — find paralogue-informative markers (PSVs)

Pairwise-align all copies in the family. Find positions that
distinguish at least two copies.

**File**: `02_copy_markers.tsv`

```
family_id   marker_id  copy1_base  copy2_base  copy3_base
            copy1_pos  copy2_pos   copy3_pos

SDfam001    m001       A           G           T
            10500123   35400123    4100123
SDfam001    m002       C           C           A
            10500450   35400450    4100450
```

**Required QC filters** (audit chat to confirm thresholds):
- **k-mer uniqueness**: the 31-mer centred on each marker must be
  unique within ±100 bp on each copy. Otherwise it's a hot-spot
  for mismapping and the marker is unreliable.
- **Coverage filter**: when reads from the cohort are mapped to
  the reference, the depth at this marker position must fall in
  the expected range (typically 0.7× to 1.3× of genome-wide
  median). Markers with anomalous depth indicate mismapping or
  CNV; reject.
- **Allele complexity**: marker must be a SNV, not an indel.
  Indels in SD regions are dominated by alignment artefacts.
- **Minimum copy diversity**: at least 2 of the K copies must
  carry distinguishable bases. Otherwise the marker is
  uninformative.

**Critical caveat**: PSV calling is the hardest step in this whole
pipeline. False PSVs from misalignment will dominate noise. The
spec recommends:
- Validate a sample of PSVs against long-read assemblies if
  available.
- Cross-check PSV calls against the EDTA TE annotation: markers
  inside TE-dense regions get extra scrutiny.

## Step C — paint reads or windows

For each candidate breakpoint region (input from Stage 4 or any
SV caller), split into windows.

Window sizes to provide:
- 1 kb (high resolution, low marker count per window)
- 5 kb (default, balanced)
- 10 kb (coarse, more markers, better stats)

For each window, count marker support per copy. A read or assembled
window "supports" copy_k at marker_m if its base at marker_m matches
`copy_k_base` from the dictionary.

**File**: `03_window_copy_painting.tsv`

```
window_id  chr   window_start  window_end   copy1_support  copy2_support
                                            copy3_support  unknown_support
                                            call           call_confidence

w0001      LG05  10000000      10001000     18             1
                                             0              2
                                             copy1          high
w0002      LG05  10001000      10002000     16             2
                                             0              3
                                             copy1          high
w0003      LG05  10002000      10003000      4             13
                                             0              4
                                             copy2          medium
w0004      LG05  10003000      10004000      1             17
                                             0              3
                                             copy2          high
```

**Calling rules**:
- `call = copy_k` if `copy_k_support / total_informative ≥ 0.8` AND
  `total_informative ≥ 5`.
- `call = unknown` if `total_informative < 5`.
- `call = mixed` if no single copy reaches 0.8 dominance but ≥ 2
  copies have ≥ 0.2 share each.
- `call_confidence`:
  - `high`: dominance ≥ 0.9, informative ≥ 10
  - `medium`: dominance ≥ 0.8, informative ≥ 5
  - `low`: marginal, or `mixed`

**These thresholds are starting points — audit chat must verify
against real PSV density in the C. gariepinus SDs.**

## Step D — classify breakpoint mechanism

Sequence the per-window calls in genomic order across the candidate
breakpoint. Classify the transition pattern.

**File**: `06_mechanism_classification.tsv`

| pattern                                        | label                       |
|------------------------------------------------|-----------------------------|
| `copy1 copy1 copy1 \| copy2 copy2 copy2`       | NAHR-compatible             |
| `copy1 copy1 \| unknown scar \| copy2 copy2`   | NHEJ/MMEJ-compatible        |
| `copy1 \| copy2 \| copy1 \| copy3`             | complex paralogue mosaic    |
| `copy1 copy1 copy1 copy1`                      | no mosaic evidence          |

**Operational definitions**:
- **NAHR-compatible**: exactly one clean transition between two
  copies; transition window is ≤ 1 window wide (or the resolution
  limit); no "unknown" windows flanking the junction.
- **NHEJ/MMEJ-compatible**: exactly one transition, but with ≥ 1
  "unknown" window at the junction (the "scar"), OR the transition
  is at a position with microhomology evidence (1–10 bp shared
  sequence between the two copies). Microhomology detection
  requires sequence-level analysis, not just call patterns.
- **complex paralogue mosaic**: ≥ 2 transitions in the candidate
  interval, OR ≥ 3 distinct copies called in the interval. Often
  indicates assembly/mapping artefact in high-copy SD families;
  flag with a warning.
- **no mosaic evidence**: zero transitions. As noted above, this
  is ambiguous — could mean no rearrangement OR rearrangement
  between identical copies.

## Step E — integrate with HOM/HET arrangement groups

This is where the module connects to the long-range regimes pipeline.

For each Stage-4 candidate that overlaps an SD family, partition
samples by arrangement karyotype (HOM_A / HET / HOM_B, called by
the existing dosage + karyotype machinery). Run the painting
separately for each group's pooled BAMs (or per-sample, then
aggregate).

**File**: `04_sample_copy_painting.tsv`

```
sample_id   candidate_id   chr   start_bp   end_bp
            arrangement_group  copy1_share  copy2_share  copy3_share
            unknown_share      call_summary

CGA_001     INV001          LG05  10000000   10100000
            HOM_A              0.95         0.03         0.00
            0.02               left_copy1_right_copy1
CGA_002     INV001          LG05  10000000   10100000
            HOM_B              0.02         0.97         0.00
            0.01               left_copy2_right_copy2
CGA_003     INV001          LG05  10000000   10100000
            HET                0.48         0.49         0.00
            0.03               mixed_copy1_copy2
```

**Expected pattern for a true arrangement-specific SD junction**:

| group | expected dominant copy_share | typical pattern                |
|-------|------------------------------|--------------------------------|
| HOM_A | ≥ 0.85 on copy_1             | uniform left-to-right copy1    |
| HOM_B | ≥ 0.85 on copy_2             | uniform left-to-right copy2    |
| HET   | mixed (≥ 0.2 each on c1+c2)  | both copies present per window |

**Interpretation table** (the meaningful summary):

| HOM_A origin | HOM_B origin | HET signal           | interpretation                  |
|--------------|--------------|----------------------|---------------------------------|
| copy1        | copy2        | mixed copy1/copy2    | arrangement-specific SD mosaic  |
| copy1        | copy1        | copy1 only           | no copy-origin difference       |
| copy1        | copy3        | mixed/ambiguous      | complex rearrangement           |
| ambiguous    | ambiguous    | ambiguous            | low PSV density — uncallable    |

**Critical caveat (circular dependency)**: this integration assumes
the HOM_A/HET/HOM_B karyotype calls are correct. Breakpoint regions
are notoriously the hardest to genotype (low coverage, multi-mapping
reads, structural complexity). If the karyotype calls are wrong, the
copy-origin contrast across groups will be noisy even when the
biology is clean. The audit chat should think about how to detect
this circularity — possibly by also reporting *raw* per-sample
painting without group aggregation, so the user can see if groups
are internally consistent.

## Final module outputs

```
01_copy_dictionary.tsv             # Step A: paralogue copies per family
02_copy_markers.tsv                # Step B: PSVs across copies
03_window_copy_painting.tsv        # Step C: per-window copy calls
04_sample_copy_painting.tsv        # Step E: per-sample per-candidate calls
05_breakpoint_switches.tsv         # headline output — one row per candidate
06_mechanism_classification.tsv    # Step D: mechanism labels
07_plot_copy_painting.html         # standalone visualisation (see below)
```

## Visualisation: Copy-Origin / Paralogue Painting page

A new atlas page with five stacked panels:

1. **Top: genome track**. Candidate inversion/regime interval,
   plus flanking ±500 kb context.
2. **Copy-origin painting track**. Coloured blocks per window:
   ```
   copy1 copy1 copy1 │ copy2 copy2 copy2
                     ▲
                  switch position
   ```
   Each copy gets a distinct hue (consistent with the dosage
   palette where possible — blue/red/etc.).
3. **HOM/HET comparison track**. Three rows (HOM_A / HET / HOM_B),
   each painted with that group's dominant copy origin per window:
   ```
   HOM_A  ████████████████████  copy1
   HET    ████░░░░░████░░░░░██  copy1/copy2 mixed
   HOM_B  ████████████████████  copy2
   ```
4. **Mechanism label**. The Step-D label for this candidate
   (NAHR-compatible / NHEJ/MMEJ-compatible / complex mosaic / no
   evidence) with the confidence tier.
5. **Centromere / TE / SD overlay**. Annotation tracks showing
   centromere proximity, TE density (EDTA), and SD family extents
   (BISER/SDquest). Helps the user evaluate context — high TE
   density or centromere proximity is a confounder.

## Where this lives in the atlas

A new page sibling to the regimes page:

- `pages/discovery/copy_origin_page/copy_origin_page.js`     (page wrapper)
- `pages/discovery/copy_origin_page/copy_origin_panel.js`    (painting track)
- `pages/discovery/copy_origin_page/copy_origin_groups.js`   (HOM/HET comparison)
- `pages/discovery/copy_origin_page/copy_origin_overlay.js`  (centromere/TE/SD)

The same DOM contract pattern as the regimes page:

```html
<div id="copyOriginPageHeader"></div>
<div class="copy-origin-grid">
  <div id="copyOriginPaintingPanel">
    <div id="copyOriginPaintingContainer"></div>
  </div>
  <div id="copyOriginGroupsPanel">
    <div id="copyOriginGroupsContainer"></div>
  </div>
  <div id="copyOriginOverlayPanel">
    <div id="copyOriginOverlayContainer"></div>
  </div>
</div>
```

The painting data comes from cluster-side `05_breakpoint_switches.tsv`
+ `03_window_copy_painting.tsv` + `04_sample_copy_painting.tsv` loaded
as JSON via the existing dosage_bridge / popstats_server endpoint
pattern. A new endpoint:

```
GET /api/copy_origin/painting?candidate_id=INV001&window_size=5000
GET /api/copy_origin/groups?candidate_id=INV001
GET /api/copy_origin/families?chrom=LG05
```

The cluster-side processing (Steps A–D) runs offline; the atlas only
serves the pre-computed results.

## Naming and manuscript wording

**Module name** (for code): `copy_origin_painting`
**Method name** (for manuscript): copy-origin painting
**Cool name** (for atlas UI): Paralogue Ancestry Painting

**Canonical reference sentence**:

> We implemented a copy-origin painting approach, hereafter referred
> to as paralogue ancestry painting, to assign breakpoint-proximal
> windows to their most likely duplicated-copy background.

**Methods paragraph (manuscript-style)**:

> To characterize rearrangement breakpoints embedded within duplicated
> sequence, we developed a copy-origin painting strategy. Segmental-
> duplication families were first decomposed into paralogous copies,
> which were aligned to identify copy-informative markers. For each
> candidate breakpoint, reads or assembled sequence windows were
> scored according to their support for each paralogue background.
> Abrupt transitions between copy-origin states were interpreted as
> mosaic junctions, while ambiguous scars or unassigned sequence at
> transitions were used to distinguish NAHR-compatible from
> NHEJ/MMEJ-compatible patterns. Copy-origin profiles were then
> compared across homozygous and heterozygous arrangement classes to
> test whether candidate haplotype regimes carried arrangement-
> specific duplicated-copy backgrounds.

**Result-sentence template**:

> Copy-origin painting revealed that several long-range inheritance
> regimes contained abrupt transitions between paralogous sequence
> backgrounds near candidate breakpoints, consistent with mosaic
> junctions generated by duplication-mediated rearrangement. In these
> regions, homozygous arrangement classes carried distinct copy-
> origin profiles, whereas heterokaryotypes showed mixed support,
> validating the presence of arrangement-specific structural
> haplotypes.

---

## Audit questions for the next chat

1. **PSV calling reliability**. Step B is the hardest step. What
   tools should produce the PSV table? Has Quentin already validated
   PSV calls in any SD family of the Gar haplotype? If not, this
   step is a known unknown — the module's accuracy floor depends
   entirely on PSV quality.

2. **Are the calling thresholds defensible?** 0.8 dominance for a
   confident copy call, ≥ 5 informative markers per window. Where
   do these come from? The audit chat should look at typical PSV
   density in the C. gariepinus SDs and recommend cohort-appropriate
   thresholds.

3. **Window-size choice**. 1 kb / 5 kb / 10 kb are offered as
   alternatives. Should the module compute all three and let the
   user pick, or pick adaptively based on PSV density per locus?

4. **NAHR vs NHEJ/MMEJ distinguishability**. The spec marks the
   distinction as "compatible" not "found" — this is correct but
   the audit chat should think about the false-positive rates of
   each label. Short ambiguous scars in repetitive regions can come
   from either mechanism.

5. **Microhomology detection** is mentioned for NHEJ/MMEJ but the
   actual sequence-level method isn't specified. Does the spec
   require an aligner-based approach (looking for 1–10 bp matches
   spanning the junction)?

6. **Circular dependency on karyotype calls** (Step E). How robust
   is the HOM_A/HET/HOM_B contrast when the karyotypes themselves
   are uncertain near the breakpoint? Possible mitigation: report
   per-sample painting without group pooling so the user can spot-
   check.

7. **The "no mosaic evidence" ambiguity**. This label hides two
   distinct biological scenarios (no rearrangement vs invisible
   rearrangement between identical copies). Should the spec require
   a secondary check — e.g. dosage / coverage anomaly at the
   candidate interval — before declaring "no rearrangement"?

8. **Existing tools**. Are there published equivalents to this
   method that the spec should cite or compare to?
   - `PSV-caller` (a hypothetical example) — does anything like it
     exist?
   - `nahrwhals` / `BREAKSeq` — these classify break mechanisms
     differently; how does copy-origin painting compare?
   - The audit chat should do a literature pass.

9. **Integration with the existing `instant_q` Engine B**. The spec
   uses the `instant_q` analogy. Should the actual implementation
   *reuse* the `instant_q` C++ binary with a different reference
   matrix (paralogue PSVs instead of population AIMs), or be a
   separate C++/Rust module? Reusing has the appeal of one binary
   to maintain; separate gives cleaner semantics.

10. **Resolution limits and missing-data behaviour**. What happens
    when a window has only 1–2 informative markers? When ALL windows
    in a candidate interval are below the 5-marker floor? The spec
    says "unknown" but the audit chat should verify this graceful
    degradation is actually graceful.

## What this spec does NOT cover

- **Implementation**: zero code. The spec is structural / file-format
  / decision-rule only.
- **Statistical significance**: produces categorical labels (NAHR-
  compatible / NHEJ-compatible / etc), not p-values. If manuscript-
  grade significance is required, an empirical-null permutation
  layer must be added.
- **Read-level realignment**. The spec assumes the BAMs are already
  aligned to the reference. Re-aligning reads to each copy
  individually (graph genome / pangenome approach) is a different
  module and would change the painting accuracy substantially.
- **Per-haplotype phasing**. The spec implicitly assumes diploid
  callable haplotypes are available. If the data is read-pile only
  (no phased haplotypes), the HET interpretation is murkier — the
  "mixed copy1/copy2" signal could be inter-haplotype OR within-
  haplotype mosaic.
- **Quality control on the BAMs themselves**. The module assumes the
  BAMs are usable; pre-screening for chimeric reads, soft-clips at
  candidate breakpoints, and read-pair anomalies is required upstream
  but not specified here.
- **Cross-cohort transfer**. Like the regime annotation spec, the
  copy-origin painting thresholds are tuned for the 226-sample
  C. gariepinus hatchery cohort. They may not transfer to wild
  C. macrocephalus or to F1 hybrids.

## Status checklist for implementation (DO NOT BEGIN YET)

When the audit chat has approved this spec, implementation order:

- [ ] Confirm SD calls exist for the Gar haplotype assembly.
- [ ] Run Step A on a test family (LG05 or wherever the cleanest
      SD family lives).
- [ ] Run Step B on that family. Manually inspect 50 PSVs against
      the assembly to estimate false-PSV rate.
- [ ] If false-PSV rate > 10%, stop and revisit PSV calling.
- [ ] Run Step C on one candidate breakpoint (suggest: LG28
      15.115–18.005 Mb if SDs are present there; else pick another
      validated candidate).
- [ ] Run Step D on that candidate. Sanity-check the mechanism
      label.
- [ ] Run Step E with the existing karyotype calls. Compare to
      the dosage-overlay output for the same candidate.
- [ ] Build the visualisation page only after Steps A–E produce
      reasonable output on ≥ 3 candidates.
- [ ] Build the integration with the regimes page (clicking a
      regime → opens the copy-origin painting page for its
      candidate interval).
