#!/usr/bin/env python3
"""
STEP_BP5_prep_atlas_data.py

Consolidate every BP_ATLAS result file into ONE canonical JSON the
downstream plot scripts read. Two-file output:

    atlas_data.json          (compact: haplotypes, chroms, zones,
                              reciprocity, per-event metadata.
                              Reading this is enough to draw any
                              zone-level plot.)
    atlas_paf_arcs.json      (large, OPTIONAL: per-(pair, chrom) list
                              of alignment blocks for ribbon plots
                              that need the real Pass A arcs rather
                              than just zone lenses. Only written when
                              --include-paf is set.)

Why a single JSON instead of letting each plot re-parse the TSVs:
    1. Every plot script — the static R figures (BP5c/BP5d) and the
       interactive inversion-atlas HTML pages — reads the same data.
       One source of truth, no schema drift.
    2. The atlas browser pages load JSON natively. Loading a dozen TSVs
       via JS Papaparse is fragile and slow.
    3. Adds derived joins once (haplotype↔species, zone↔reciprocal_partner,
       chromosome↔length) instead of re-doing them in every plot script.

Schema is documented inline below the `build_payload` function.

Usage:
    python3 STEP_BP5_prep_atlas_data.py \\
        --bp-out  results_bpatlas/03_breakpoints/ \\
        --manifest 00_input/manifests/haplotype_manifest.tsv \\
        --out      results_bpatlas/05_atlas_data/ \\
        [--include-paf  results_bpatlas/02_paf_passA/]
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from collections import defaultdict


# ---------------------------------------------------------------------------
# I/O helpers
# ---------------------------------------------------------------------------
def read_tsv(path: Path) -> list[dict]:
    """Read a TSV emitted by any BP step. Handles:
      - leading '#'-comment lines that don't look like headers
      - the '# header' convention (BED-style commented column row)
      - the '# no <thing>' sentinel BP3 emits for empty zone tables
      - UTF-8 BOMs

    Logic: read the first non-blank line. If it starts with '#' AND
    contains at least one tab AND the de-commented version contains
    the expected column-name pattern (no path separators, mostly
    word chars), treat it as a commented header — strip the '#'
    and use it. Otherwise treat all '#' lines as comments.
    """
    if not path.exists():
        return []
    with open(path, encoding="utf-8-sig") as fh:
        raw_lines = fh.readlines()
    if not raw_lines:
        return []

    # Find the first non-blank line
    first_idx = next((i for i, ln in enumerate(raw_lines) if ln.strip()), None)
    if first_idx is None:
        return []
    first = raw_lines[first_idx]

    # Is the first non-blank line a commented HEADER (vs a sentinel comment)?
    # Heuristic: starts with '#', contains tabs, and the columns after
    # stripping the '#' look like identifiers (no '/' path chars,
    # no commas, mostly word/underscore).
    treat_first_as_header = False
    if first.lstrip().startswith("#"):
        decommented = first.lstrip().lstrip("#").lstrip()
        if "\t" in decommented:
            cols = decommented.rstrip("\n").split("\t")
            # All "cells" look like column identifiers, not data
            if all(c and "/" not in c and "," not in c and " " not in c
                   for c in cols):
                treat_first_as_header = True

    if treat_first_as_header:
        # Emit the de-commented header + every subsequent non-#-comment line
        decommented_header = raw_lines[first_idx].lstrip().lstrip("#").lstrip()
        body = [ln for ln in raw_lines[first_idx + 1:]
                if not ln.lstrip().startswith("#")]
        lines = [decommented_header] + body
    else:
        # Original behavior: '#' lines are all comments
        lines = [ln for ln in raw_lines if not ln.lstrip().startswith("#")]

    if not lines:
        return []
    reader = csv.DictReader(lines, delimiter="\t")
    return list(reader)


def coerce_int(row: dict, keys: list[str]) -> None:
    """In-place int coercion of any present numeric fields."""
    for k in keys:
        if k in row and row[k] != "":
            try:
                row[k] = int(row[k])
            except (ValueError, TypeError):
                pass


def coerce_float(row: dict, keys: list[str]) -> None:
    for k in keys:
        if k in row and row[k] != "":
            try:
                row[k] = float(row[k])
            except (ValueError, TypeError):
                pass


# ---------------------------------------------------------------------------
# .fai reader → per-haplotype chromosome lengths
# ---------------------------------------------------------------------------
def read_fai(fasta_path: Path) -> list[dict]:
    """Read the samtools .fai sidecar of `fasta_path` and return a list of
    {name, length}. Missing .fai is non-fatal — returns []."""
    fai = Path(str(fasta_path) + ".fai")
    if not fai.exists():
        return []
    out = []
    with open(fai) as fh:
        for line in fh:
            f = line.rstrip("\n").split("\t")
            if len(f) < 2:
                continue
            try:
                out.append({"name": f[0], "length": int(f[1])})
            except ValueError:
                continue
    return out


# ---------------------------------------------------------------------------
# Haplotype manifest → list of haplotype objects with chrom list attached
# ---------------------------------------------------------------------------
def load_haplotypes(manifest_path: Path) -> list[dict]:
    rows = read_tsv(manifest_path)
    haps = []
    for r in rows:
        if r.get("haplotype_id") == "haplotype_id":  # belt-and-braces header skip
            continue
        if not r.get("haplotype_id"):
            continue
        fasta = Path(r.get("fasta_path", ""))
        chroms = read_fai(fasta) if fasta else []
        haps.append({
            "haplotype_id":  r["haplotype_id"],
            "species":       r.get("species", ""),
            "source":        r.get("source", ""),
            "qc_tier":       r.get("qc_tier", ""),
            "fasta_path":    r.get("fasta_path", ""),
            "notes":         r.get("notes", ""),
            "n_chroms":      len(chroms),
            "total_length":  sum(c["length"] for c in chroms),
            "chromosomes":   chroms,
        })

    # Diagnose-and-fail if the manifest produced zero rows. Silently emitting
    # an atlas_data.json with 0 haplotypes was the cause of a real failure
    # mode where every downstream ribbon plot errored with "'species' not
    # found amongst []". A loud failure here saves hours of confusion.
    if not haps:
        cols = list(rows[0].keys()) if rows else []
        msg = [
            f"[STEP_BP5] FATAL: loaded 0 haplotypes from {manifest_path}",
            f"           ({len(rows)} non-comment lines parsed)",
            f"           column names seen: {cols}",
            f"           expected columns: haplotype_id, species, source, qc_tier, fasta_path",
            "",
            "  Likely causes:",
            "    1. Wrong path passed to --manifest",
            "    2. File uses spaces or '\\t' literals instead of real tab bytes",
            "       (check with: od -c FILE | head)",
            "    3. First-column header is corrupt (BOM, leading whitespace, etc.)",
            "    4. Manifest is empty or has only a header line",
        ]
        raise SystemExit("\n".join(msg))

    return haps


# ---------------------------------------------------------------------------
# Zone tables → unified list, keyed with anchor prefix to avoid collisions
# ---------------------------------------------------------------------------
ZONE_INT_FIELDS = ["zone_start", "zone_end", "zone_centroid", "zone_width_bp",
                   "n_raw_events", "support_pair_count", "reciprocal_count",
                   "n_distinct_event_classes"]
ZONE_FLOAT_FIELDS = ["backbone_frac"]


def load_zones_for_anchor(bp_out: Path, anchor: str) -> list[dict]:
    """Load BOTH inversion zones and translocation zones for the given
    anchor species, merge them into one list with a uniform schema
    (zone_kind already in the column from the BP3 patch). Each zone gets
    an `anchor_species` field and an atlas-scoped `zone_uid` of the form
    'Cgar/BP_zone_000003' so the JSON can mix them without collisions.
    """
    out = []
    anchor_dir = bp_out / f"anchor_{anchor}"
    # Prefer the reciprocity-annotated copies (they have reciprocal_zone_id)
    recip_dir = bp_out / "reciprocity"
    annotated = recip_dir / f"anchor_{anchor}_zones_annotated.tsv"

    if annotated.exists():
        rows = read_tsv(annotated)
        for r in rows:
            coerce_int(r, ZONE_INT_FIELDS)
            coerce_float(r, ZONE_FLOAT_FIELDS)
            r["anchor_species"] = anchor
            r["zone_uid"] = f"{anchor}/{r['zone_id']}"
            out.append(r)
        return out

    # Fall back to the raw BP3 outputs if BP3c wasn't run yet
    for src_name in ("breakpoint_zones.tsv", "translocation_zones.tsv"):
        rows = read_tsv(anchor_dir / src_name)
        for r in rows:
            coerce_int(r, ZONE_INT_FIELDS)
            coerce_float(r, ZONE_FLOAT_FIELDS)
            r["anchor_species"] = anchor
            r["zone_uid"] = f"{anchor}/{r['zone_id']}"
            r.setdefault("reciprocal_zone_id", "none")
            r.setdefault("reciprocal_count",   0)
            out.append(r)
    return out


# ---------------------------------------------------------------------------
# Reciprocity table — already in the format we want, just re-typed
# ---------------------------------------------------------------------------
def load_reciprocity(bp_out: Path) -> list[dict]:
    rows = read_tsv(bp_out / "reciprocity" / "reciprocity_table.tsv")
    for r in rows:
        coerce_int(r, ["cgar_centroid", "cgar_support_pairs",
                       "cmac_centroid", "cmac_support_pairs",
                       "combined_support"])
        # Attach atlas-scoped UIDs for cross-referencing in the front-end
        r["cgar_zone_uid"] = f"Cgar/{r['cgar_zone_id']}"
        r["cmac_zone_uid"] = f"Cmac/{r['cmac_zone_id']}"
    return rows


# ---------------------------------------------------------------------------
# Raw events — used for highlighting individual breakpoints inside a zone
# ---------------------------------------------------------------------------
EVENT_INT_FIELDS = ["query_pos", "query_left_end", "query_right_start",
                    "target_left_pos", "target_right_pos", "gap_bp",
                    "left_block_bp", "right_block_bp", "left_mapq", "right_mapq"]
EVENT_FLOAT_FIELDS = ["left_identity", "right_identity"]


def load_raw_events(bp_out: Path) -> list[dict]:
    rows = read_tsv(bp_out / "breakpoints_raw.tsv")
    for r in rows:
        coerce_int(r, EVENT_INT_FIELDS)
        coerce_float(r, EVENT_FLOAT_FIELDS)
    return rows


# ---------------------------------------------------------------------------
# Optional: Pass A PAF arcs for ribbon plots
# ---------------------------------------------------------------------------
def load_paf_arcs(paf_dir: Path, min_block_bp: int = 50_000) -> dict[str, list[dict]]:
    """Return { pair_id: [ {q_chrom, q_start, q_end, t_chrom, t_start,
    t_end, strand, mapq, identity}, ... ] }.

    Blocks smaller than `min_block_bp` are dropped — they bloat the JSON
    and don't add information at the zoom levels the atlas uses.
    """
    if not paf_dir.exists():
        return {}
    out: dict[str, list[dict]] = {}
    for paf in sorted(paf_dir.glob("*.paf")):
        pair_id = paf.stem
        arcs: list[dict] = []
        with open(paf) as fh:
            for line in fh:
                if not line.strip():
                    continue
                f = line.rstrip("\n").split("\t")
                if len(f) < 12:
                    continue
                try:
                    qspan = int(f[3]) - int(f[2])
                    if qspan < min_block_bp:
                        continue
                    matches = int(f[9]); aln_len = int(f[10])
                    identity = (matches / aln_len) if aln_len else 0.0
                    arcs.append({
                        "q_chrom": f[0],
                        "q_start": int(f[2]),
                        "q_end":   int(f[3]),
                        "strand":  f[4],
                        "t_chrom": f[5],
                        "t_start": int(f[7]),
                        "t_end":   int(f[8]),
                        "mapq":    int(f[11]),
                        "identity": round(identity, 4),
                    })
                except (ValueError, IndexError):
                    continue
        if arcs:
            out[pair_id] = arcs
    return out


# ---------------------------------------------------------------------------
# Payload assembly
# ---------------------------------------------------------------------------
def build_payload(
    bp_out: Path,
    manifest_path: Path,
    paf_dir: Path | None,
) -> tuple[dict, dict | None]:
    """Assemble atlas_data.json and (optionally) atlas_paf_arcs.json.

    Schema of atlas_data.json (top-level keys):

        schema_version : "bpatlas/1.0"
        generated_from : path to bp_out (for traceability)
        haplotypes     : [ {haplotype_id, species, qc_tier, source, notes,
                            n_chroms, total_length,
                            chromosomes: [ {name, length}, ... ]}, ... ]
        anchors        : ["Cgar", "Cmac"]   (which anchor frames have data)
        zones          : [ flat list of zones across all anchors.
                           Every zone has zone_kind in {"inversion","translocation"},
                           anchor_species in {"Cgar","Cmac"}, zone_uid as the
                           cross-anchor stable id, and a reciprocal_zone_id
                           pointing to its partner on the other anchor
                           (or "none"). ]
        reciprocity    : [ {cgar_zone_uid, cmac_zone_uid, bidirectional,
                            combined_support, ...} ]
        events         : [ raw events from breakpoints_raw.tsv with
                           every field typed. Used by per-zone drill-down
                           views (which haplotype pair contributed this
                           specific transition). ]
        summary        : { zones_by_kind_and_confidence, zones_by_anchor,
                           reciprocal_pair_count_bidirectional }

    Schema of atlas_paf_arcs.json:
        schema_version : "bpatlas-paf/1.0"
        arcs           : { pair_id: [ {q_chrom, q_start, q_end, strand,
                                       t_chrom, t_start, t_end, mapq,
                                       identity}, ... ] }
    """
    haplotypes = load_haplotypes(manifest_path)

    # Which anchors exist? Look for anchor_<sp>/breakpoint_zones.tsv files
    anchors = sorted({p.name.removeprefix("anchor_") for p in bp_out.iterdir()
                      if p.is_dir() and p.name.startswith("anchor_")})

    zones: list[dict] = []
    for a in anchors:
        zones.extend(load_zones_for_anchor(bp_out, a))

    reciprocity = load_reciprocity(bp_out)
    events = load_raw_events(bp_out)

    # Summary stats
    by_kind_conf: dict[tuple[str, str, str], int] = defaultdict(int)
    by_anchor:    dict[str, int] = defaultdict(int)
    for z in zones:
        by_kind_conf[(z["anchor_species"],
                      z.get("zone_kind", "inversion"),
                      z.get("confidence", ""))] += 1
        by_anchor[z["anchor_species"]] += 1
    bidir = sum(1 for r in reciprocity if r.get("bidirectional") == "yes")

    payload = {
        "schema_version": "bpatlas/1.0",
        "generated_from": str(bp_out),
        "haplotypes":     haplotypes,
        "anchors":        anchors,
        "zones":          zones,
        "reciprocity":    reciprocity,
        "events":         events,
        "summary": {
            "zones_by_anchor":  dict(by_anchor),
            "zones_by_kind_and_confidence": [
                {"anchor": a, "zone_kind": k, "confidence": c, "n": n}
                for (a, k, c), n in sorted(by_kind_conf.items())
            ],
            "reciprocal_pair_count_bidirectional": bidir,
            "n_zones": len(zones),
            "n_events": len(events),
            "n_haplotypes": len(haplotypes),
        },
    }

    arcs_payload = None
    if paf_dir is not None:
        arcs_payload = {
            "schema_version": "bpatlas-paf/1.0",
            "min_block_bp":   50_000,
            "arcs":           load_paf_arcs(paf_dir),
        }

    return payload, arcs_payload


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bp-out",    required=True, type=Path,
                    help="results_bpatlas/03_breakpoints/  (parent of "
                         "anchor_<sp>/ and reciprocity/)")
    ap.add_argument("--manifest",  required=True, type=Path,
                    help="haplotype_manifest.tsv (used for species/QC/chrom lengths)")
    ap.add_argument("--out",       required=True, type=Path,
                    help="Output directory (atlas_data.json will be written here)")
    ap.add_argument("--include-paf", type=Path, default=None,
                    help="OPTIONAL Pass A PAF directory. If given, also "
                         "emits atlas_paf_arcs.json with the per-pair "
                         "alignment blocks for ribbon plots.")
    ap.add_argument("--indent", type=int, default=0,
                    help="JSON indent (0 = single line, smallest file; "
                         "2 = pretty-printed, larger but git-diffable). "
                         "Default 0.")
    args = ap.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)

    payload, arcs_payload = build_payload(args.bp_out, args.manifest,
                                          args.include_paf)

    out_main = args.out / "atlas_data.json"
    with open(out_main, "w") as fh:
        if args.indent:
            json.dump(payload, fh, indent=args.indent)
        else:
            json.dump(payload, fh, separators=(",", ":"))
    size_kb = out_main.stat().st_size / 1024
    print(f"[STEP_BP5] atlas_data.json -> {out_main}  ({size_kb:.1f} KB)",
          file=sys.stderr)
    print(f"           {payload['summary']['n_haplotypes']} haplotypes, "
          f"{payload['summary']['n_zones']} zones, "
          f"{payload['summary']['n_events']} events, "
          f"{payload['summary']['reciprocal_pair_count_bidirectional']} "
          f"bidirectional reciprocal pairs",
          file=sys.stderr)

    if arcs_payload is not None:
        out_arcs = args.out / "atlas_paf_arcs.json"
        with open(out_arcs, "w") as fh:
            if args.indent:
                json.dump(arcs_payload, fh, indent=args.indent)
            else:
                json.dump(arcs_payload, fh, separators=(",", ":"))
        size_kb = out_arcs.stat().st_size / 1024
        n_pairs = len(arcs_payload["arcs"])
        n_arcs = sum(len(v) for v in arcs_payload["arcs"].values())
        print(f"[STEP_BP5] atlas_paf_arcs.json -> {out_arcs}  ({size_kb:.1f} KB)",
              file=sys.stderr)
        print(f"           {n_pairs} pairs, {n_arcs} alignment blocks "
              f"(min_block_bp={arcs_payload['min_block_bp']})",
              file=sys.stderr)


if __name__ == "__main__":
    main()
