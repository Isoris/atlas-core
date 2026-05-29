#!/usr/bin/env python3
"""
STEP_BP3_cluster_zones.py

Cluster raw breakpoints (from STEP_BP2) into breakpoint ZONES.

The motivation, straight from the spec Quentin endorsed:

    Whole-genome alignments will give slightly different breakpoint
    coordinates depending on tool, repeat masking, haplotype quality,
    alignment parameters, assembly gaps, segmental duplications.

    Cluster breakpoints in windows:
        ±10 kb  for clean assemblies
        ±50 kb  for normal confidence
        ±100–500 kb for repeat-rich / fragmented regions

This step does single-linkage clustering on the QUERY coordinate of each
event, separately per (anchor_species, anchor_chrom). The tolerance used
for any pair of events is the MAX of:
    - their tier-derived defaults (A/A => 50 kb, A/B => 100 kb, A/C => 500 kb)
    - both events being on the same anchor chromosome (already enforced)

We anchor on the CGAR side when possible, because the inversion paper's
candidate intervals are reported in Cgar coordinates. So:
    - within-Cgar pairs  (Cgar_h*)        : anchor = query (Cgar)
    - within-Cmac pairs                   : anchor = query (Cmac)
    - cross-species, query=Cgar           : anchor = query (Cgar)
    - cross-species, query=Cmac           : anchor = TARGET (Cgar)
                                            (so events get reported in
                                             Cgar coords for the atlas)

Output:
    breakpoint_zones.tsv    one row per zone, with the supporting pairs and
                            classes folded into list-columns ('; '-joined)

Usage:
    python3 STEP_BP3_cluster_zones.py \\
        --raw-bp results_bpatlas/03_breakpoints/breakpoints_raw.tsv \\
        --anchor-species Cgar \\
        --out    results_bpatlas/03_breakpoints/
"""
from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path


# Base tier tolerance (zone half-width in bp), for within-species pairs
TIER_TOL_BASE = {
    ("A", "A"): 50_000,
    ("A", "B"): 100_000,
    ("B", "A"): 100_000,
    ("B", "B"): 150_000,
    ("A", "C"): 500_000,
    ("C", "A"): 500_000,
    ("B", "C"): 500_000,
    ("C", "B"): 500_000,
    ("C", "C"): 500_000,  # but C/C never happens — STEP_BP1 forbids C as query
}

# Multiplier for cross-species pairs — speciation-era indels and rearrangements
# move breakpoint coordinates more than within-species haplotype divergence.
# Empirically, ~3x slack is reasonable for Cgar↔Cmac (~10 My divergence).
CROSS_SPECIES_MULT = 3.0


def tier_tolerance(qc1: str, qc2: str, pair_kind: str = "") -> int:
    base = TIER_TOL_BASE.get((qc1, qc2), 500_000)
    if pair_kind.startswith("cross_"):
        return int(base * CROSS_SPECIES_MULT)
    return base


# ----------------------------------------------------------------------------
# Pass B backbone loader. Reads every Pass B PAF in the given directory and
# builds a map { (pair_id, query_chrom): [(qstart, qend), ...] } of large
# (~500 kb) approximate-mapping chains. STEP_BP3 uses this to flag zones
# whose Pass-A signal does NOT sit on a coarse-scale synteny chain — those
# are likely repeat artifacts.
# ----------------------------------------------------------------------------
def load_passB_intervals(passB_dir: Path) -> dict[tuple[str, str], list[tuple[int, int]]]:
    """
    Returns {(pair_id, query_chrom): sorted list of (qstart, qend)} from all
    Pass B PAFs in passB_dir. Keys are by pair so that backbone support is
    tested against the SAME pair that produced the Pass A event — a
    candidate confirmed by Cgar_h1__vs__Cgar_h2 should be checked against
    THAT pair's Pass B, not someone else's.
    """
    out: dict[tuple[str, str], list[tuple[int, int]]] = defaultdict(list)
    if not passB_dir.exists():
        return out
    for paf in sorted(passB_dir.glob("*.paf")):
        pair_id = paf.stem
        with open(paf) as fh:
            for line in fh:
                if not line.strip():
                    continue
                f = line.rstrip("\n").split("\t")
                if len(f) < 12:
                    continue
                try:
                    qname = f[0]
                    qstart = int(f[2])
                    qend = int(f[3])
                except (ValueError, IndexError):
                    continue
                out[(pair_id, qname)].append((qstart, qend))
    # Sort intervals per key for binary-search-style overlap checks
    for k in out:
        out[k].sort()
    return out


def position_on_backbone(
    pair_id: str,
    chrom: str,
    pos: int,
    passB: dict[tuple[str, str], list[tuple[int, int]]],
    pad: int = 250_000,
) -> bool:
    """Is `pos` (with ±pad slack) inside any Pass-B chain for this pair on this chrom?"""
    intervals = passB.get((pair_id, chrom), [])
    for s, e in intervals:
        if s - pad <= pos <= e + pad:
            return True
        if s - pad > pos:
            return False  # sorted — no later interval will help
    return False


# ----------------------------------------------------------------------------
# Event-class triage.
#
# FOCUS    : INVERSION_breakpoint + INVERTED_TRANSLOC
#            -> clustered into the primary `breakpoint_zones.tsv`
# TRANSLOC : INTERCHROM_breakpoint
#            -> clustered into `translocation_zones.tsv`, with each event's
#               CS-style refined label ('fission_or_fusion' vs
#               'translocation') aggregated by majority vote across the
#               supporting pairs in the zone.
# CONTEXT  : NONCOLLINEAR
#            -> not clustered; kept in `context_breakpoints.tsv` for the
#               record.
#
# Earlier versions of BP3 grouped INTERCHROM and NONCOLLINEAR together as
# "context". Splitting them out exposes fission/fusion/translocation
# signals that the manuscript needs, especially the ones supported by
# multiple haplotype pairs (the strongest evidence class).
# ----------------------------------------------------------------------------
FOCUS_CLASSES    = {"INVERSION_breakpoint", "INVERTED_TRANSLOC"}
TRANSLOC_CLASSES = {"INTERCHROM_breakpoint"}
CONTEXT_CLASSES  = {"NONCOLLINEAR"}


# ----------------------------------------------------------------------------
# Re-anchor every event so its position is in <anchor_species> coordinates
# ----------------------------------------------------------------------------
def reanchor(events: list[dict], anchor_species: str) -> list[dict]:
    """
    For each raw event, decide which side ('query' or 'target') is in the
    anchor species and assign anchor_chrom / anchor_pos accordingly.

    For within-species pairs, both sides are in the same species — we
    anchor on the QUERY side (the haplotype frame the breakpoint was
    detected on). The TARGET partner becomes the 'partner' field.

    For cross-species pairs where the query is the anchor species, query
    = anchor. Where the target is the anchor species, we re-anchor on
    the target side: anchor_pos becomes target_left_pos (the
    coordinate where the orientation switch lands on the anchor
    chromosome), and partner becomes the query haplotype.

    Events with neither side in the anchor species (e.g. Cmac->Cmac
    when anchoring on Cgar) are flagged with anchor_in_species=False
    and kept for context but NOT clustered with the rest.
    """
    out = []
    for e in events:
        qsp = e["query_species"]
        tsp = e["target_species"]

        if qsp == anchor_species:
            anchor_side = "query"
            anchor_chrom = e["query_chrom"]
            anchor_pos   = int(e["query_pos"])
            partner_chrom_l = e["target_left_chrom"]
            partner_pos_l   = int(e["target_left_pos"])
            partner_chrom_r = e["target_right_chrom"]
            partner_pos_r   = int(e["target_right_pos"])
        elif tsp == anchor_species:
            # We project the breakpoint onto the target side. The target
            # partner is split across left/right (b1.tend, b2.tstart).
            # Use their midpoint where both touch the same target chrom,
            # otherwise use target_left_pos as the anchor.
            anchor_side = "target"
            if e["target_left_chrom"] == e["target_right_chrom"]:
                anchor_chrom = e["target_left_chrom"]
                anchor_pos   = (int(e["target_left_pos"]) + int(e["target_right_pos"])) // 2
            else:
                # Interchrom: take the left target side as anchor coordinate;
                # the partner is the right target chrom.
                anchor_chrom = e["target_left_chrom"]
                anchor_pos   = int(e["target_left_pos"])
            partner_chrom_l = e["query_chrom"]
            partner_pos_l   = int(e["query_left_end"])
            partner_chrom_r = e["query_chrom"]
            partner_pos_r   = int(e["query_right_start"])
        else:
            anchor_side = "neither"
            anchor_chrom = ""
            anchor_pos = -1
            partner_chrom_l = ""
            partner_pos_l = -1
            partner_chrom_r = ""
            partner_pos_r = -1

        e_out = dict(e)
        e_out["anchor_side"] = anchor_side
        e_out["anchor_chrom"] = anchor_chrom
        e_out["anchor_pos"] = anchor_pos
        e_out["partner_chrom_l"] = partner_chrom_l
        e_out["partner_pos_l"]   = partner_pos_l
        e_out["partner_chrom_r"] = partner_chrom_r
        e_out["partner_pos_r"]   = partner_pos_r
        e_out["anchor_in_species"] = (anchor_side != "neither")
        out.append(e_out)
    return out


# ----------------------------------------------------------------------------
# Single-linkage clustering on a sorted list of (pos, tol) tuples
# ----------------------------------------------------------------------------
def cluster_positions(events_on_chrom: list[dict]) -> list[list[dict]]:
    """
    Single-linkage cluster on anchor_pos using per-event tolerance.
    Two events join the same cluster if their positions are within
    max(tol_a, tol_b) of each other.
    """
    if not events_on_chrom:
        return []
    # Sort by anchor_pos
    s = sorted(events_on_chrom, key=lambda e: e["anchor_pos"])
    clusters: list[list[dict]] = [[s[0]]]
    for ev in s[1:]:
        prev = clusters[-1][-1]
        tol = max(
            tier_tolerance(prev["query_qc"], prev["target_qc"], prev.get("pair_kind", "")),
            tier_tolerance(ev["query_qc"], ev["target_qc"], ev.get("pair_kind", "")),
        )
        if ev["anchor_pos"] - prev["anchor_pos"] <= tol:
            clusters[-1].append(ev)
        else:
            clusters.append([ev])
    return clusters


# ----------------------------------------------------------------------------
# Build zone records
# ----------------------------------------------------------------------------
def build_zone(
    zid: str,
    members: list[dict],
    passB: dict[tuple[str, str], list[tuple[int, int]]] | None = None,
    zone_kind: str = "inversion",
) -> dict:
    """Build a zone record from a single-linkage cluster of events.

    zone_kind:
      "inversion"     -> the long-standing FOCUS zones (INVERSION + INVERTED_TRANSLOC)
      "translocation" -> INTERCHROM zones; an additional
                         `dominant_event_type` field is added via majority
                         vote of each member's `event_type_refined` from
                         BP2 ('fission_or_fusion' or 'translocation'). Ties
                         break toward 'fission_or_fusion' because it's the
                         more conservative biological claim (one ancestral
                         chromosome rearranged) versus 'translocation'
                         (two ancestral chromosomes exchanged material).
    """
    positions = [m["anchor_pos"] for m in members]
    chrom = members[0]["anchor_chrom"]
    centroid = sum(positions) // len(positions)
    half_width = max(1, (max(positions) - min(positions)) // 2 + 5_000)

    pairs = sorted({m["pair_id"] for m in members})
    classes = sorted({m["event_class"] for m in members})
    qc_combo = sorted({(m["query_qc"], m["target_qc"]) for m in members})
    qc_str = "; ".join(f"{a}{b}" for a, b in qc_combo)

    # Best-tier qc combo: A/A > A/B > A/C
    tier_rank = {("A","A"):0, ("A","B"):1, ("B","A"):1, ("B","B"):2,
                 ("A","C"):3, ("C","A"):3, ("B","C"):4, ("C","B"):4, ("C","C"):5}
    best_tier = sorted(qc_combo, key=lambda x: tier_rank.get(x, 99))[0]
    best_tier_str = f"{best_tier[0]}{best_tier[1]}"

    # Partner loci collected as a compact summary
    partners_all = []
    partners_within = []
    for m in members:
        is_within = m.get("pair_kind", "").startswith("within_")
        if m["partner_chrom_l"] and m["partner_chrom_l"] != chrom:
            ploc = f"{m['partner_chrom_l']}:{m['partner_pos_l']}"
            partners_all.append(ploc)
            if is_within:
                partners_within.append(ploc)
        if m["partner_chrom_r"] and m["partner_chrom_r"] != chrom \
           and m["partner_chrom_r"] != m["partner_chrom_l"]:
            ploc = f"{m['partner_chrom_r']}:{m['partner_pos_r']}"
            partners_all.append(ploc)
            if is_within:
                partners_within.append(ploc)
    partners_all = sorted(set(partners_all))
    partners_within = sorted(set(partners_within))

    # Backbone support — fraction of supporting pairs whose Pass B chain
    # covers the zone centroid. If no Pass B was provided (passB is None),
    # report "n/a" so STEP_BP4 won't downgrade.
    if passB is not None:
        n_on_backbone = sum(
            1 for m in members
            if position_on_backbone(m["pair_id"], chrom, centroid, passB)
        )
        backbone_frac = n_on_backbone / len(members) if members else 0.0
        if backbone_frac >= 0.5:
            backbone_support = "yes"
        elif backbone_frac > 0.0:
            backbone_support = "partial"
        else:
            backbone_support = "no"
    else:
        n_on_backbone = -1
        backbone_frac = -1.0
        backbone_support = "n/a"

    # Confidence:
    #   high   : best=AA AND ≥2 pairs AND backbone yes
    #   medium : best=AA OR  ≥2 pairs (and backbone not "no")
    #   low    : everything else, or backbone="no" regardless
    if backbone_support == "no":
        conf = "low"
    elif best_tier_str == "AA" and len(pairs) >= 2 and backbone_support in ("yes", "n/a"):
        conf = "high"
    elif best_tier_str == "AA" or len(pairs) >= 2:
        conf = "medium"
    else:
        conf = "low"

    return {
        "zone_id":           zid,
        "zone_kind":         zone_kind,
        "chrom":             chrom,
        "zone_start":        max(0, centroid - half_width),
        "zone_end":          centroid + half_width,
        "zone_centroid":     centroid,
        "zone_width_bp":     2 * half_width,
        "n_raw_events":      len(members),
        "support_pairs":     "; ".join(pairs),
        "support_pair_count": len(pairs),
        "best_qc_combo":     best_tier_str,
        "all_qc_combos":     qc_str,
        "event_classes":     "; ".join(classes),
        # Number of distinct event classes at this zone. A zone with
        # n_distinct_event_classes > 1 is a putative BREAKPOINT-REUSE
        # HOTSPOT: the same locus shows up as different event types
        # (e.g. INVERSION_breakpoint in one pair, INTERCHROM_breakpoint
        # in another). Grep this column for >1 to find candidates.
        "n_distinct_event_classes": len(classes),
        # CS-style refined classification: meaningful only for translocation
        # zones. For inversion zones we still report it (will be "inversion"
        # or "inverted_translocation") so the schema is unified across
        # zone_kind values.
        "dominant_event_type": _dominant_refined(members),
        "refined_breakdown":   _refined_breakdown(members),
        "target_dominance_summary": _aggregate_dominance(members),
        "partner_loci":            "; ".join(partners_all)    if partners_all    else "none",
        "partner_loci_within_sp":  "; ".join(partners_within) if partners_within else "none",
        "backbone_support":  backbone_support,
        "backbone_frac":     round(backbone_frac, 3) if backbone_frac >= 0 else "n/a",
        "confidence":        conf,
    }


def _dominant_refined(members: list[dict]) -> str:
    """Majority vote of `event_type_refined` across members.

    Ties between 'fission_or_fusion' and 'translocation' break toward
    'fission_or_fusion' (more conservative single-ancestral-chrom claim).
    Members without the column (e.g. raw events from a pre-patch BP2)
    fall back to their `event_class`.
    """
    from collections import Counter
    labels = [m.get("event_type_refined") or m.get("event_class", "")
              for m in members]
    if not labels:
        return ""
    c = Counter(labels)
    top_n = c.most_common()
    top_count = top_n[0][1]
    tied = [lbl for lbl, n in top_n if n == top_count]
    if "fission_or_fusion" in tied:
        return "fission_or_fusion"
    return tied[0]


def _refined_breakdown(members: list[dict]) -> str:
    """Per-label count, '; '-joined, sorted by count desc, e.g.
    'fission_or_fusion:3; translocation:1'. Empty string if no labels.
    """
    from collections import Counter
    labels = [m.get("event_type_refined", "") for m in members
              if m.get("event_type_refined")]
    if not labels:
        return ""
    c = Counter(labels)
    return "; ".join(f"{lbl}:{n}" for lbl, n in c.most_common())


def _aggregate_dominance(members: list[dict]) -> str:
    """Compact summary of the per-event `target_dominance` strings,
    deduplicated and sorted. Empty if no member has the column populated.
    """
    parts = sorted({m.get("target_dominance", "") for m in members
                    if m.get("target_dominance")})
    return "; ".join(parts)


# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--raw-bp",          required=True, type=Path,
                    help="breakpoints_raw.tsv from STEP_BP2")
    ap.add_argument("--anchor-species",  required=True,
                    help="Species whose coordinates the atlas uses (typically Cgar)")
    ap.add_argument("--out",             required=True, type=Path)
    ap.add_argument("--zone-id-prefix",  default="BP_zone_")
    ap.add_argument("--passB-paf-dir",   type=Path, default=None,
                    help="OPTIONAL directory of Pass B (-s 500k) wfmash PAFs "
                         "from STEP_BP1. If provided, each zone gets a "
                         "backbone_support flag (yes/partial/no/n_a). Zones "
                         "with backbone='no' are forced to low confidence.")
    args = ap.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)

    # Read raw events
    with open(args.raw_bp) as fh:
        # Skip leading comment lines
        first = fh.readline()
        while first.startswith("#"):
            first = fh.readline()
        if not first.strip():
            sys.exit("[STEP_BP3] empty raw breakpoint file — nothing to cluster")
        # Re-read with DictReader (rewind)
    with open(args.raw_bp) as fh:
        # Handle possible comment header
        lines = [ln for ln in fh if not ln.startswith("#")]
    if not lines:
        sys.exit("[STEP_BP3] empty raw breakpoint file — nothing to cluster")

    reader = csv.DictReader(lines, delimiter="\t")
    raw = list(reader)
    print(f"[STEP_BP3] Loaded {len(raw)} raw events", file=sys.stderr)

    # Coerce numeric fields
    int_fields = ["query_pos", "query_left_end", "query_right_start",
                  "target_left_pos", "target_right_pos", "gap_bp",
                  "left_block_bp", "right_block_bp", "left_mapq", "right_mapq"]
    for r in raw:
        for f in int_fields:
            if f in r:
                try:
                    r[f] = int(r[f])
                except (ValueError, TypeError):
                    r[f] = 0

    # Re-anchor everything to the anchor species
    reanchored = reanchor(raw, args.anchor_species)

    in_species = [e for e in reanchored if e["anchor_in_species"]]
    out_species = [e for e in reanchored if not e["anchor_in_species"]]
    print(f"[STEP_BP3] {len(in_species)} events anchored on {args.anchor_species}, "
          f"{len(out_species)} events on other-species frames (kept as context)",
          file=sys.stderr)

    # Split anchored events into three buckets:
    #   focus   -> primary inversion zones (kept identical to legacy behaviour)
    #   transloc -> INTERCHROM events, clustered into translocation_zones
    #   context -> NONCOLLINEAR only; kept for the record
    focus    = [e for e in in_species if e["event_class"] in FOCUS_CLASSES]
    transloc = [e for e in in_species if e["event_class"] in TRANSLOC_CLASSES]
    context  = [e for e in in_species if e["event_class"] in CONTEXT_CLASSES]
    print(f"[STEP_BP3] {len(focus)} focus events (INVERSION + INVERTED_TRANSLOC), "
          f"{len(transloc)} translocation events (INTERCHROM), "
          f"{len(context)} context events (NONCOLLINEAR)",
          file=sys.stderr)

    # Load Pass B backbone if provided (used by both zone types)
    passB = None
    if args.passB_paf_dir is not None:
        passB = load_passB_intervals(args.passB_paf_dir)
        n_keys = len(passB)
        n_intervals = sum(len(v) for v in passB.values())
        print(f"[STEP_BP3] Loaded Pass B backbone: {n_intervals} intervals "
              f"across {n_keys} (pair, chrom) keys", file=sys.stderr)

    # ---- inversion zones (legacy) --------------------------------------
    by_chrom: dict[str, list[dict]] = defaultdict(list)
    for e in focus:
        by_chrom[e["anchor_chrom"]].append(e)

    zones = []
    zid_counter = 0
    for chrom in sorted(by_chrom.keys()):
        clusters = cluster_positions(by_chrom[chrom])
        for cl in clusters:
            zid = f"{args.zone_id_prefix}{zid_counter:06d}"
            zones.append(build_zone(zid, cl, passB=passB, zone_kind="inversion"))
            zid_counter += 1

    # Sort by support_pair_count desc, then chrom, then centroid — so the
    # most-supported zones (strongest evidence) are at the top of the table.
    zones.sort(key=lambda z: (-z["support_pair_count"], z["chrom"], z["zone_centroid"]))

    # Write inversion zones — column order preserved from legacy schema where
    # possible; new columns (zone_kind, dominant_event_type, refined_breakdown,
    # target_dominance_summary) appended.
    zones_path = args.out / "breakpoint_zones.tsv"
    if zones:
        with open(zones_path, "w", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(zones[0].keys()),
                                    delimiter="\t")
            writer.writeheader()
            writer.writerows(zones)
    else:
        with open(zones_path, "w") as fh:
            fh.write("# no zones — anchor species absent from raw events?\n")
    print(f"[STEP_BP3] {len(zones)} inversion zones -> {zones_path}", file=sys.stderr)

    # Confidence counts (inversions)
    conf_counts: dict[str, int] = defaultdict(int)
    for z in zones:
        conf_counts[z["confidence"]] += 1
    print("[STEP_BP3] Inversion zones by confidence:", file=sys.stderr)
    for k in ("high", "medium", "low"):
        print(f"  {k:8s} {conf_counts.get(k, 0):6d}", file=sys.stderr)

    # ---- translocation zones (new) -------------------------------------
    by_chrom_t: dict[str, list[dict]] = defaultdict(list)
    for e in transloc:
        by_chrom_t[e["anchor_chrom"]].append(e)

    tzones = []
    tzid_counter = 0
    for chrom in sorted(by_chrom_t.keys()):
        clusters = cluster_positions(by_chrom_t[chrom])
        for cl in clusters:
            zid = f"TR_zone_{tzid_counter:06d}"
            tzones.append(build_zone(zid, cl, passB=passB, zone_kind="translocation"))
            tzid_counter += 1

    tzones.sort(key=lambda z: (-z["support_pair_count"], z["chrom"], z["zone_centroid"]))

    tzones_path = args.out / "translocation_zones.tsv"
    if tzones:
        with open(tzones_path, "w", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(tzones[0].keys()),
                                    delimiter="\t")
            writer.writeheader()
            writer.writerows(tzones)
    else:
        with open(tzones_path, "w") as fh:
            fh.write("# no translocation zones — no INTERCHROM events anchored on this species\n")
    print(f"[STEP_BP3] {len(tzones)} translocation zones -> {tzones_path}",
          file=sys.stderr)

    # Translocation zones by dominant_event_type, for the manuscript table
    t_kind_counts: dict[str, int] = defaultdict(int)
    for z in tzones:
        t_kind_counts[z["dominant_event_type"]] += 1
    if tzones:
        print("[STEP_BP3] Translocation zones by dominant_event_type:", file=sys.stderr)
        for k in sorted(t_kind_counts.keys()):
            print(f"  {k:24s} {t_kind_counts[k]:6d}", file=sys.stderr)

    # ---- combined zone table (inversions + translocations) -------------
    # One file with both kinds, sorted by support_pair_count desc, so the
    # manuscript and the atlas can scan ALL multi-pair zones in one view.
    combined = zones + tzones
    combined.sort(key=lambda z: (-z["support_pair_count"], z["zone_kind"],
                                 z["chrom"], z["zone_centroid"]))
    combined_path = args.out / "all_zones_combined.tsv"
    if combined:
        with open(combined_path, "w", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(combined[0].keys()),
                                    delimiter="\t")
            writer.writeheader()
            writer.writerows(combined)
        print(f"[STEP_BP3] {len(combined)} combined zones (inv + transloc) "
              f"-> {combined_path}", file=sys.stderr)

    # Also dump out-of-anchor events for context (e.g. within-Cmac when
    # anchor=Cgar). These are useful for the Methods narrative.
    if out_species:
        ctx_path = args.out / "breakpoints_other_anchor.tsv"
        with open(ctx_path, "w", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(out_species[0].keys()),
                                    delimiter="\t")
            writer.writeheader()
            writer.writerows(out_species)
        print(f"[STEP_BP3] {len(out_species)} other-anchor events -> {ctx_path}",
              file=sys.stderr)

    # Dump remaining context events (NONCOLLINEAR only, after INTERCHROM was
    # promoted to its own translocation_zones table). Kept as a side file for
    # the Methods narrative and Reviewer #3 traceability.
    if context:
        ctx2_path = args.out / "context_breakpoints.tsv"
        with open(ctx2_path, "w", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(context[0].keys()),
                                    delimiter="\t")
            writer.writeheader()
            writer.writerows(context)
        print(f"[STEP_BP3] {len(context)} context events (noncollinear) "
              f"-> {ctx2_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
