#!/usr/bin/env python3
"""
STEP_BP4_overlap_population.py

Cross-reference breakpoint zones (from STEP_BP3) with population-genetic
candidate intervals exported from `inversion-popgen-toolkit`. Produces:

  1. zones_with_pop.tsv      — zones table joined with the nearest /
                               overlapping population candidate (one row
                               per zone, NA where no candidate is nearby)
  2. candidates_with_bp.tsv  — population candidates joined with their
                               supporting breakpoint zones (one row per
                               candidate, with classification)

Classification rules (taken straight from the spec):

    Population signal only
        → inversion-like structural haplotype candidate

    Population signal + two same-chrom orientation breakpoints near
    the LEFT and RIGHT boundaries of the candidate
        → inversion candidate

    Population signal + outer (parent) and inner (nested) breakpoint pairs
        → nested/compound inversion candidate

    Population signal + breakpoint partner at distant locus/chromosome
        → inverted translocation-like candidate

    Breakpoint evidence with no population signal
        → fixed/rare/recent rearrangement (reported separately, not as
          a candidate)

Input format for population candidates (TSV, one row per candidate):
    candidate_id   chrom   start   end   [optional cols ignored]
e.g. exported from inversion-popgen-toolkit phase_8 catalogue.

Usage:
    python3 STEP_BP4_overlap_population.py \\
        --zones results_bpatlas/03_breakpoints/breakpoint_zones.tsv \\
        --pop   /scratch/.../inversion-popgen-toolkit/results/phase_8/catalogue.tsv \\
        --out   results_bpatlas/04_overlap/ \\
        [--boundary-tol 100000] [--inner-search-pad 200000]
"""
from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path


def load_zones(path: Path) -> list[dict]:
    with open(path) as fh:
        lines = [ln for ln in fh if not ln.startswith("#")]
    reader = csv.DictReader(lines, delimiter="\t")
    out = []
    for r in reader:
        for f in ("zone_start", "zone_end", "zone_centroid",
                  "zone_width_bp", "support_pair_count", "n_raw_events"):
            if f in r:
                try:
                    r[f] = int(r[f])
                except (ValueError, TypeError):
                    r[f] = 0
        out.append(r)
    return out


def load_candidates(path: Path) -> list[dict]:
    """
    Population candidates. Tolerant about column names — accepts:
        candidate_id | inversion_id | id
        chrom | chromosome | seqid
        start | left | left_bp
        end | right | right_bp
    """
    aliases = {
        "candidate_id": ["candidate_id", "inversion_id", "id", "name"],
        "chrom":        ["chrom", "chromosome", "seqid", "chr"],
        "start":        ["start", "left", "left_bp", "begin", "from"],
        "end":          ["end", "right", "right_bp", "stop", "to"],
    }
    with open(path) as fh:
        lines = [ln for ln in fh if not ln.startswith("#")]
    reader = csv.DictReader(lines, delimiter="\t")
    fieldnames = reader.fieldnames or []
    pick = {}
    for std, alts in aliases.items():
        for a in alts:
            if a in fieldnames:
                pick[std] = a
                break
        if std not in pick and std != "candidate_id":
            sys.exit(f"[STEP_BP4] population catalogue missing required column "
                     f"(any of {alts})")
    out = []
    for i, r in enumerate(reader):
        cid = r.get(pick.get("candidate_id", ""), f"POP_{i:05d}")
        try:
            start = int(r[pick["start"]])
            end   = int(r[pick["end"]])
        except (KeyError, ValueError):
            continue
        out.append({
            "candidate_id": cid,
            "chrom":        r[pick["chrom"]],
            "start":        start,
            "end":          end,
            # keep all original fields for downstream
            **{k: v for k, v in r.items() if k not in pick.values()}
        })
    return out


def index_zones_by_chrom(zones: list[dict]) -> dict[str, list[dict]]:
    idx = defaultdict(list)
    for z in zones:
        idx[z["chrom"]].append(z)
    for chrom in idx:
        idx[chrom].sort(key=lambda z: z["zone_centroid"])
    return idx


def find_zones_near(
    chrom: str,
    pos: int,
    pad: int,
    idx: dict[str, list[dict]],
) -> list[dict]:
    """Return zones on `chrom` whose [start, end] window is within `pad` of pos."""
    out = []
    for z in idx.get(chrom, []):
        # Use zone EDGES not just centroid for proximity test
        if z["zone_end"] + pad < pos:
            continue
        if z["zone_start"] - pad > pos:
            break
        if (z["zone_start"] - pad) <= pos <= (z["zone_end"] + pad):
            out.append(z)
    return out


def find_zones_in_interval(
    chrom: str,
    start: int,
    end: int,
    idx: dict[str, list[dict]],
) -> list[dict]:
    """Return zones whose centroid falls inside [start, end]."""
    out = []
    for z in idx.get(chrom, []):
        if z["zone_centroid"] < start:
            continue
        if z["zone_centroid"] > end:
            break
        out.append(z)
    return out


def classify_candidate(
    cand: dict,
    left_zones: list[dict],
    right_zones: list[dict],
    inner_zones: list[dict],
) -> dict:
    """
    Apply the classification rules. Returns dict with classification,
    sub-evidence flags, and the chosen supporting zone IDs.
    """
    # Check for distant partner loci. The translocation rule depends on
    # WITHIN-SPECIES partners specifically — cross-species partners on a
    # different chrom are usually just orthology and don't imply a
    # within-species translocation. STEP_BP3 emitted partner_loci_within_sp
    # for this purpose.
    distant_partners = set()
    for z in left_zones + right_zones + inner_zones:
        plocs = z.get("partner_loci_within_sp", "none")
        if plocs and plocs != "none":
            for p in plocs.split("; "):
                if not p.startswith(cand["chrom"] + ":"):
                    distant_partners.add(p)

    # Check for orientation-switch evidence at boundaries
    has_left_inv  = any("INVERSION" in z.get("event_classes", "") or
                        "INVERTED" in z.get("event_classes", "")
                        for z in left_zones)
    has_right_inv = any("INVERSION" in z.get("event_classes", "") or
                        "INVERTED" in z.get("event_classes", "")
                        for z in right_zones)

    has_inner_zones = len(inner_zones) > 0

    # Best confidence among supporting zones
    confs = [z.get("confidence", "low") for z in left_zones + right_zones + inner_zones]
    rank = {"high": 0, "medium": 1, "low": 2}
    best_conf = "low"
    if confs:
        best_conf = sorted(confs, key=lambda c: rank.get(c, 99))[0]

    # Apply rules in priority order. Renamed for precision since STEP_BP3 now
    # only clusters INVERSION_breakpoint and INVERTED_TRANSLOC into zones —
    # any within-species off-anchor partner therefore comes from an
    # INVERTED_TRANSLOC event, not a generic interchrom break.
    if distant_partners:
        cls = "inverted_translocation_candidate"
    elif has_left_inv and has_right_inv and has_inner_zones:
        cls = "nested_compound_inversion_candidate"
    elif has_left_inv and has_right_inv:
        cls = "inversion_candidate"
    elif left_zones or right_zones or inner_zones:
        cls = "inversion_like_with_partial_bp_support"
    else:
        cls = "inversion_like_no_bp_support"

    return {
        "classification": cls,
        "best_supporting_confidence": best_conf,
        "has_left_orientation_switch": has_left_inv,
        "has_right_orientation_switch": has_right_inv,
        "has_inner_zone": has_inner_zones,
        "distant_partner_count": len(distant_partners),
        "distant_partner_loci": "; ".join(sorted(distant_partners)) if distant_partners else "",
    }


# ----------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--zones", required=True, type=Path,
                    help="breakpoint_zones.tsv from STEP_BP3")
    ap.add_argument("--pop",   required=True, type=Path,
                    help="population candidate intervals TSV")
    ap.add_argument("--out",   required=True, type=Path)
    ap.add_argument("--boundary-tol", type=int, default=100_000,
                    help="how close a zone must be to a candidate boundary "
                         "to count as supporting evidence (default 100 kb)")
    ap.add_argument("--hic-lookup", type=Path, default=None,
                    help="OPTIONAL path to a Hi-C evidence lookup TSV "
                         "(chrom, start, end, evidence_note). If present, "
                         "candidates overlapping any row get a hic_evidence "
                         "column populated. Use this to cite pre-existing "
                         "Hi-C butterflies from the parent assembly QC "
                         "reports — NOT to run new Hi-C analysis.")
    args = ap.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)

    zones = load_zones(args.zones)
    cands = load_candidates(args.pop)
    print(f"[STEP_BP4] {len(zones)} zones, {len(cands)} population candidates",
          file=sys.stderr)

    if not zones:
        sys.exit("[STEP_BP4] No zones in input — nothing to overlap")
    if not cands:
        sys.exit("[STEP_BP4] No population candidates in input — nothing to classify")

    # Optional: load pre-existing Hi-C evidence intervals
    hic_intervals: list[dict] = []
    if args.hic_lookup is not None and args.hic_lookup.exists():
        with open(args.hic_lookup) as fh:
            lines = [ln for ln in fh if not ln.startswith("#")]
        reader = csv.DictReader(lines, delimiter="\t")
        for r in reader:
            try:
                hic_intervals.append({
                    "chrom": r["chrom"],
                    "start": int(r["start"]),
                    "end":   int(r["end"]),
                    "note":  r.get("evidence_note", ""),
                })
            except (KeyError, ValueError):
                continue
        print(f"[STEP_BP4] Loaded {len(hic_intervals)} Hi-C evidence intervals "
              f"from {args.hic_lookup}", file=sys.stderr)
    elif args.hic_lookup is not None:
        print(f"[STEP_BP4] --hic-lookup file not found: {args.hic_lookup} "
              "(continuing without Hi-C evidence column)", file=sys.stderr)

    idx = index_zones_by_chrom(zones)

    # ------------------------------------------------------------------------
    # Per-candidate join: classify each candidate from its supporting zones
    # ------------------------------------------------------------------------
    cand_rows = []
    used_zone_ids: set[str] = set()
    for c in cands:
        left_zones  = find_zones_near(c["chrom"], c["start"], args.boundary_tol, idx)
        right_zones = find_zones_near(c["chrom"], c["end"],   args.boundary_tol, idx)
        inner_zones = find_zones_in_interval(
            c["chrom"],
            c["start"] + args.boundary_tol,  # exclude boundary zones from "inner"
            c["end"]   - args.boundary_tol,
            idx,
        )
        cls = classify_candidate(c, left_zones, right_zones, inner_zones)

        for z in left_zones + right_zones + inner_zones:
            used_zone_ids.add(z["zone_id"])

        # Optional Hi-C evidence join — find any HiC interval overlapping the
        # candidate window. Empty string if no overlap or no lookup loaded.
        hic_notes = []
        for hi in hic_intervals:
            if hi["chrom"] != c["chrom"]:
                continue
            # Any overlap counts
            if hi["end"] >= c["start"] and hi["start"] <= c["end"]:
                hic_notes.append(hi["note"])

        row = {
            "candidate_id":     c["candidate_id"],
            "chrom":            c["chrom"],
            "start":            c["start"],
            "end":              c["end"],
            "width_bp":         c["end"] - c["start"],
            "n_left_zones":     len(left_zones),
            "n_right_zones":    len(right_zones),
            "n_inner_zones":    len(inner_zones),
            "left_zone_ids":    "; ".join(z["zone_id"] for z in left_zones),
            "right_zone_ids":   "; ".join(z["zone_id"] for z in right_zones),
            "inner_zone_ids":   "; ".join(z["zone_id"] for z in inner_zones),
            **cls,
        }
        # Only emit hic_evidence column if user provided a lookup file
        if args.hic_lookup is not None:
            row["hic_evidence"] = "; ".join(hic_notes) if hic_notes else ""
        cand_rows.append(row)

    cand_path = args.out / "candidates_with_bp.tsv"
    with open(cand_path, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(cand_rows[0].keys()),
                                delimiter="\t")
        writer.writeheader()
        writer.writerows(cand_rows)
    print(f"[STEP_BP4] {len(cand_rows)} candidates classified -> {cand_path}",
          file=sys.stderr)

    # Classification summary
    cls_counts: dict[str, int] = defaultdict(int)
    for r in cand_rows:
        cls_counts[r["classification"]] += 1
    print("[STEP_BP4] Candidates by classification:", file=sys.stderr)
    for k, v in sorted(cls_counts.items(), key=lambda x: -x[1]):
        print(f"  {k:50s} {v:6d}", file=sys.stderr)

    # ------------------------------------------------------------------------
    # Per-zone join: one row per zone, with the population candidate it
    # overlaps (if any). Zones not used by any candidate are flagged as
    # "fixed_or_recent_rearrangement".
    # ------------------------------------------------------------------------
    cand_idx_by_chrom: dict[str, list[dict]] = defaultdict(list)
    for c in cands:
        cand_idx_by_chrom[c["chrom"]].append(c)
    for chrom in cand_idx_by_chrom:
        cand_idx_by_chrom[chrom].sort(key=lambda c: c["start"])

    zone_rows = []
    for z in zones:
        # Find candidates that this zone overlaps
        overlaps = []
        for c in cand_idx_by_chrom.get(z["chrom"], []):
            # Zone counts as overlapping a candidate if its centroid falls
            # within (start - tol, end + tol) of the candidate
            if (c["start"] - args.boundary_tol) <= z["zone_centroid"] <= (c["end"] + args.boundary_tol):
                overlaps.append(c)
        if overlaps:
            ovl_class = "supports_population_candidate"
        else:
            ovl_class = "fixed_or_recent_rearrangement"

        zone_rows.append({
            **z,
            "overlaps_pop_candidate": "yes" if overlaps else "no",
            "pop_candidate_ids":      "; ".join(c["candidate_id"] for c in overlaps),
            "n_pop_candidates":       len(overlaps),
            "interpretation":         ovl_class,
        })

    zone_path = args.out / "zones_with_pop.tsv"
    with open(zone_path, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(zone_rows[0].keys()),
                                delimiter="\t")
        writer.writeheader()
        writer.writerows(zone_rows)
    print(f"[STEP_BP4] {len(zone_rows)} zones (with pop join) -> {zone_path}",
          file=sys.stderr)

    n_supp = sum(1 for r in zone_rows if r["overlaps_pop_candidate"] == "yes")
    print(f"[STEP_BP4] {n_supp}/{len(zone_rows)} zones overlap a population candidate",
          file=sys.stderr)


if __name__ == "__main__":
    main()
