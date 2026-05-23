#!/usr/bin/env python3
"""
STEP_BP3c_reciprocity.py

Cross-reference the two anchor-species zone catalogues (Cgar and Cmac) and
flag zones whose partner_loci land inside a zone on the other anchor.

A "reciprocal zone pair" is the strongest evidence class for a real
chromosomal rearrangement: the same biological event shows up
independently when each species is used as the reference frame. The
manuscript's claim "this inversion is supported from both directions"
operationally means "BP_zone_N in anchor_Cgar has a partner locus that
sits inside BP_zone_M in anchor_Cmac, and vice versa".

This script:
  1. Loads both breakpoint_zones.tsv (and optionally translocation_zones.tsv)
     produced by STEP_BP3.
  2. For each zone, parses its partner_loci column ("chrom:pos; chrom:pos; ...")
     and asks: does any of those partners fall inside a zone on the OTHER
     anchor's table?
  3. Emits reciprocity_table.tsv with one row per matched zone pair.
  4. Emits an annotated copy of each anchor's zone tables with a new
     `reciprocal_zone_id` column (most-overlapping partner, "none" if no
     match).

Usage:
    python3 STEP_BP3c_reciprocity.py \\
        --cgar-dir results_bpatlas/03_breakpoints/anchor_Cgar/ \\
        --cmac-dir results_bpatlas/03_breakpoints/anchor_Cmac/ \\
        --out      results_bpatlas/03_breakpoints/reciprocity/ \\
        [--zone-kinds inversion,translocation]    # which zone files to load

Does NOT modify the inputs; writes everything into --out.
"""
from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path


# ---------------------------------------------------------------------------
# I/O
# ---------------------------------------------------------------------------
def load_zones(zones_tsv: Path) -> list[dict]:
    """Read a zones.tsv produced by STEP_BP3. Tolerates missing files
    (returns []) and the legacy "# no zones — ..." sentinel.
    """
    if not zones_tsv.exists():
        return []
    with open(zones_tsv) as fh:
        first = fh.readline()
        if first.startswith("#"):
            return []
        # Restart with DictReader (rewinding via re-open avoids buffering quirks)
    with open(zones_tsv) as fh:
        lines = [ln for ln in fh if not ln.startswith("#")]
    if not lines:
        return []
    reader = csv.DictReader(lines, delimiter="\t")
    rows = list(reader)
    # Coerce numeric fields we'll need
    for r in rows:
        for k in ("zone_start", "zone_end", "zone_centroid", "zone_width_bp",
                  "n_raw_events", "support_pair_count"):
            try:
                r[k] = int(r[k])
            except (KeyError, ValueError, TypeError):
                pass
    return rows


def parse_partner_loci(s: str) -> list[tuple[str, int]]:
    """Split a partner_loci field like 'chromA:12345; chromB:67890' into
    [(chromA, 12345), (chromB, 67890)]. Tolerates 'none' and empty strings.
    """
    if not s or s.strip().lower() == "none":
        return []
    out = []
    for piece in s.split(";"):
        piece = piece.strip()
        if not piece or ":" not in piece:
            continue
        chrom, _, pos = piece.rpartition(":")
        try:
            out.append((chrom.strip(), int(pos)))
        except ValueError:
            continue
    return out


# ---------------------------------------------------------------------------
# Indexing & overlap
# ---------------------------------------------------------------------------
def index_by_chrom(zones: list[dict]) -> dict[str, list[dict]]:
    """Return {chrom: [zone, ...] sorted by zone_start}."""
    idx: dict[str, list[dict]] = defaultdict(list)
    for z in zones:
        idx[z["chrom"]].append(z)
    for chrom in idx:
        idx[chrom].sort(key=lambda z: z.get("zone_start", 0))
    return idx


def zones_containing(idx: dict[str, list[dict]], chrom: str, pos: int,
                     pad: int = 0) -> list[dict]:
    """Linear scan — zone counts are small (≤~50) so no need for bisect."""
    hits = []
    for z in idx.get(chrom, []):
        if (z["zone_start"] - pad) <= pos <= (z["zone_end"] + pad):
            hits.append(z)
    return hits


# ---------------------------------------------------------------------------
# Main reciprocity logic
# ---------------------------------------------------------------------------
def find_reciprocal_partners(
    src_zones: list[dict],
    other_idx: dict[str, list[dict]],
    pad: int,
) -> dict[str, list[dict]]:
    """For each zone in src_zones, return a list of zones on the OTHER
    anchor that one of its partner_loci falls into.

    Returns {src_zone_id: [other_zone, other_zone, ...]}; an empty list
    for src zones with no reciprocal partner.
    """
    out: dict[str, list[dict]] = {}
    for z in src_zones:
        partners = parse_partner_loci(z.get("partner_loci", ""))
        matches: list[dict] = []
        seen_ids: set[str] = set()
        for chrom, pos in partners:
            for hit in zones_containing(other_idx, chrom, pos, pad=pad):
                if hit["zone_id"] not in seen_ids:
                    matches.append(hit)
                    seen_ids.add(hit["zone_id"])
        out[z["zone_id"]] = matches
    return out


# ---------------------------------------------------------------------------
# Output writers
# ---------------------------------------------------------------------------
def write_reciprocity_table(matches_cgar: dict[str, list[dict]],
                            matches_cmac: dict[str, list[dict]],
                            cgar_zones: list[dict], cmac_zones: list[dict],
                            out_path: Path) -> int:
    """Emit a long-format table of every (Cgar_zone, Cmac_zone) reciprocal
    pair. A pair is "bidirectional" if it appears on both sides
    (Cgar_zone says Cmac_zone is a partner AND vice versa) — these are
    the strongest evidence class.
    """
    cgar_by_id = {z["zone_id"]: z for z in cgar_zones}
    cmac_by_id = {z["zone_id"]: z for z in cmac_zones}

    # First collect forward matches (Cgar -> Cmac)
    rows = []
    for gid, partners in matches_cgar.items():
        gz = cgar_by_id.get(gid)
        if gz is None:
            continue
        if not partners:
            continue
        for mz in partners:
            bidir = mz["zone_id"] in {p["zone_id"] for p in matches_cmac.get(mz["zone_id"], [])}
            # bidir = does the Cmac zone's partner_loci point back to a Cgar
            # zone that includes gid? Test via the Cmac->Cgar matches map.
            cmac_back = matches_cmac.get(mz["zone_id"], [])
            bidir = gid in {p["zone_id"] for p in cmac_back}
            rows.append({
                "cgar_zone_id":         gid,
                "cgar_chrom":           gz["chrom"],
                "cgar_centroid":        gz["zone_centroid"],
                "cgar_support_pairs":   gz["support_pair_count"],
                "cgar_confidence":      gz.get("confidence", ""),
                "cgar_zone_kind":       gz.get("zone_kind", "inversion"),
                "cgar_dominant_event":  gz.get("dominant_event_type", ""),
                "cmac_zone_id":         mz["zone_id"],
                "cmac_chrom":           mz["chrom"],
                "cmac_centroid":        mz["zone_centroid"],
                "cmac_support_pairs":   mz["support_pair_count"],
                "cmac_confidence":      mz.get("confidence", ""),
                "cmac_zone_kind":       mz.get("zone_kind", "inversion"),
                "cmac_dominant_event":  mz.get("dominant_event_type", ""),
                "bidirectional":        "yes" if bidir else "no",
                "combined_support":     gz["support_pair_count"] + mz["support_pair_count"],
            })

    # Sort: bidirectional first, then by combined_support desc
    rows.sort(key=lambda r: (
        0 if r["bidirectional"] == "yes" else 1,
        -r["combined_support"],
        r["cgar_chrom"], r["cgar_centroid"],
    ))

    if rows:
        with open(out_path, "w", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()),
                                    delimiter="\t")
            writer.writeheader()
            writer.writerows(rows)
    else:
        with open(out_path, "w") as fh:
            fh.write("# no reciprocal zone pairs found\n")
    return len(rows)


def write_annotated_zones(src_zones: list[dict],
                          matches: dict[str, list[dict]],
                          out_path: Path) -> None:
    """Copy src_zones to out_path with two new columns:
       reciprocal_zone_id  (best match's zone_id, or 'none')
       reciprocal_count    (how many zones on the other anchor matched)
    """
    if not src_zones:
        return
    annotated = []
    for z in src_zones:
        mlist = matches.get(z["zone_id"], [])
        if mlist:
            # Best = highest support_pair_count
            best = sorted(mlist, key=lambda m: -m["support_pair_count"])[0]
            recip_id = best["zone_id"]
        else:
            recip_id = "none"
        z_out = dict(z)
        z_out["reciprocal_zone_id"] = recip_id
        z_out["reciprocal_count"]   = len(mlist)
        annotated.append(z_out)

    fieldnames = list(annotated[0].keys())
    with open(out_path, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, delimiter="\t")
        writer.writeheader()
        writer.writerows(annotated)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cgar-dir", required=True, type=Path,
                    help="Directory containing the Cgar-anchor zone TSVs "
                         "(usually results_bpatlas/03_breakpoints/anchor_Cgar/)")
    ap.add_argument("--cmac-dir", required=True, type=Path,
                    help="Same for Cmac anchor")
    ap.add_argument("--out", required=True, type=Path,
                    help="Output directory for reciprocity tables")
    ap.add_argument("--zone-kinds", default="inversion,translocation",
                    help="Comma-separated list of which zone files to load. "
                         "Options: 'inversion' (breakpoint_zones.tsv) and "
                         "'translocation' (translocation_zones.tsv). "
                         "Default: both.")
    ap.add_argument("--pad-bp", type=int, default=100_000,
                    help="Symmetric pad applied when testing whether a "
                         "partner locus falls inside a zone on the other "
                         "anchor. Default 100 kb to absorb cross-species "
                         "coordinate slack.")
    args = ap.parse_args()

    kinds = {k.strip() for k in args.zone_kinds.split(",") if k.strip()}
    args.out.mkdir(parents=True, exist_ok=True)

    # Load zones from both anchors. We pool inversion + translocation zones
    # into one combined list per anchor so cross-anchor matching can find
    # e.g. a Cgar INTERCHROM zone whose partner is a Cmac INVERSION zone.
    cgar_zones: list[dict] = []
    cmac_zones: list[dict] = []
    if "inversion" in kinds:
        cgar_zones += load_zones(args.cgar_dir / "breakpoint_zones.tsv")
        cmac_zones += load_zones(args.cmac_dir / "breakpoint_zones.tsv")
    if "translocation" in kinds:
        cgar_zones += load_zones(args.cgar_dir / "translocation_zones.tsv")
        cmac_zones += load_zones(args.cmac_dir / "translocation_zones.tsv")

    print(f"[STEP_BP3c] Loaded {len(cgar_zones)} Cgar-anchor zones, "
          f"{len(cmac_zones)} Cmac-anchor zones", file=sys.stderr)

    if not cgar_zones or not cmac_zones:
        print("[STEP_BP3c] One side has zero zones — nothing to reciprocate",
              file=sys.stderr)
        # Still touch an empty reciprocity table for downstream consistency
        with open(args.out / "reciprocity_table.tsv", "w") as fh:
            fh.write("# at least one anchor produced 0 zones — no reciprocity computed\n")
        return

    # Build chrom-indexed lookups on each side
    cgar_idx = index_by_chrom(cgar_zones)
    cmac_idx = index_by_chrom(cmac_zones)

    # Each Cgar zone's partner_loci point to Cmac coordinates (and vice versa)
    matches_cgar = find_reciprocal_partners(cgar_zones, cmac_idx, pad=args.pad_bp)
    matches_cmac = find_reciprocal_partners(cmac_zones, cgar_idx, pad=args.pad_bp)

    n_cgar_with_match = sum(1 for v in matches_cgar.values() if v)
    n_cmac_with_match = sum(1 for v in matches_cmac.values() if v)
    print(f"[STEP_BP3c] {n_cgar_with_match}/{len(cgar_zones)} Cgar zones have "
          f"a Cmac reciprocal partner", file=sys.stderr)
    print(f"[STEP_BP3c] {n_cmac_with_match}/{len(cmac_zones)} Cmac zones have "
          f"a Cgar reciprocal partner", file=sys.stderr)

    # Reciprocity table — one row per (cgar_zone, cmac_zone) match,
    # bidirectional pairs sorted first.
    recip_path = args.out / "reciprocity_table.tsv"
    n_pairs = write_reciprocity_table(matches_cgar, matches_cmac,
                                      cgar_zones, cmac_zones, recip_path)
    print(f"[STEP_BP3c] {n_pairs} reciprocal pair rows -> {recip_path}",
          file=sys.stderr)

    # Annotated per-anchor copies with reciprocal_zone_id column appended
    write_annotated_zones(cgar_zones, matches_cgar,
                          args.out / "anchor_Cgar_zones_annotated.tsv")
    write_annotated_zones(cmac_zones, matches_cmac,
                          args.out / "anchor_Cmac_zones_annotated.tsv")
    print(f"[STEP_BP3c] Annotated zone tables (with reciprocal_zone_id) "
          f"-> {args.out}/", file=sys.stderr)


if __name__ == "__main__":
    main()
