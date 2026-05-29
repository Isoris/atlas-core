#!/usr/bin/env python3
"""
STEP_BP6_joint_classify.py

Build the manuscript's "joint candidate catalogue" by joining BP_ATLAS
zones with population-genomics evidence and family/Mendelian evidence,
then assigning a final A-E class.

This is the integration step that distinguishes:

  Class A  popgen-supported AND reciprocal BP_ATLAS support AND Mendelian
           consistency. Headline figures. Best inversion candidates.

  Class B  popgen-supported AND one-sided / partial BP_ATLAS support.
           Strong but not reciprocal. Supplement or secondary figures.

  Class C  BP_ATLAS-only (no popgen overlap at any of 50/100/500 kb).
           Real structural variation, but possibly private or not
           polymorphic in the 226-fish cohort.

  Class D  popgen-only (no BP_ATLAS support in any haplotype pair).
           Old inversion, repetitive boundary, absent from long-read
           haplotypes, or non-inversion haplotype regime. THIS IS THE
           CLASS THE LG28 PROTOTYPE LANDS IN if BP_ATLAS doesn't see
           the canonical 15.115-18.005 Mb interval.

  Class E  Dominant event type is a fission/fusion or inverted
           translocation, not a simple inversion. Classified
           structurally regardless of popgen support so we don't
           overclaim "inversion" in the manuscript.

Inputs (some required, some optional; missing optional ones leave the
corresponding columns as N/A):

    --atlas-json    (required)  results_bpatlas/05_atlas_data/atlas_data.json
                                Already produced by STEP_BP5_prep_atlas_data.
                                Provides zones (both kinds, both anchors),
                                reciprocal_zone_id (pre-joined by BP3c),
                                and dominant_event_type per zone.

    --popgen-tsv    (optional)  Population inversion candidate catalogue
                                from inversion-popgen-toolkit phase_8.
                                Expected columns (case-sensitive, tab-sep):
                                    popgen_id       Unique candidate ID
                                    chrom           Chromosome (must match
                                                    BP_ATLAS zones$chrom)
                                    popgen_start    1-based inclusive
                                    popgen_end      1-based inclusive
                                    localPCA_yes    'yes'/'no'/'NA'
                                    theta_yes       'yes'/'no'/'NA'
                                    GHSL_yes        'yes'/'no'/'NA'
                                    n_k_clusters    (optional) K from local PCA
                                    n_carriers      (optional) # samples carrying
                                                    the minor regime
                                Missing optional fields are propagated as NA.
                                If --popgen-tsv is omitted, every BP zone
                                becomes Class C and no Class D rows appear.

    --mendelian-tsv (optional)  Mendelian-inheritance support per locus.
                                Expected columns:
                                    chrom
                                    interval_start  (inclusive)
                                    interval_end    (inclusive)
                                    mendelian_status   'consistent' /
                                                       'inconsistent' /
                                                       'untested'
                                    n_informative_families  (optional)
                                Joined by interval-overlap to popgen rows.

    --popstats-tsv  (optional)  Per-locus Fst / heterozygosity / θπ summary.
                                Expected columns:
                                    chrom
                                    interval_start
                                    interval_end
                                    fst_between_regimes        float
                                    theta_pi_minor_regime      float
                                    theta_pi_major_regime      float
                                    popstats_support           'yes'/'no'

    --overlap-windows           Default 50000,100000,500000. Emits one
                                yes/no column per window.

Outputs (under --out):

    joint_candidates.tsv
        Long-format outer join. One row per (popgen_id, bp_zone_uid)
        match. Each row carries:
            candidate_id            stable per-row ID (CAND_000000)
            final_class             A | A* | B | C | D | E
            class_reason            short human-readable justification
            assembly_error_risk     high | medium | low | NA
                                    Quick filter for "is this row trustworthy?"
                                    NA when no BP zone is present (Class D).
            flags                   ;-joined list of every warning condition
                                    that fired. Examples:
                                      single_pair_support  — only 1 hap pair
                                      no_backbone          — Pass B rejects
                                      backbone_untested    — no Pass B run
                                      c_tier_assembly_involved — C-tier qc
                                      reuse_hotspot        — same locus,
                                                             multiple event
                                                             types
                                      low_confidence_only
                                      complex_rearrangement (fission/fusion
                                                             or inv translocation)
            popgen_id, popgen_chrom, popgen_start, popgen_end
            localPCA_yes, theta_yes, GHSL_yes
            popgen_n_methods_yes    integer 0-3
            bp_zone_uid, bp_chrom, bp_start, bp_end, bp_centroid
            bp_zone_kind, bp_dominant_event_type
            bp_support_pair_count, bp_confidence, bp_backbone_support
            bp_best_qc_combo, bp_n_distinct_event_classes, bp_event_classes
            bp_reciprocal_zone_id, bp_reciprocal_bidirectional
            overlaps_50k, overlaps_100k, overlaps_500k   ('yes'/'no')
            mendelian_status, n_informative_families
            popstats_support, fst_between_regimes
            haplotypes_supporting   ; -joined list

    joint_candidates_summary.tsv
        Counts by final_class.

    popgen_with_no_bp_support.tsv
        Class D rows only. The LG28 prototype lives here when the BP
        zone is >500 kb away from the popgen interval.

    bp_with_no_popgen_support.tsv
        Class C rows only.

    breakpoint_reuse_hotspots.tsv
        Zones where n_distinct_event_classes > 1 — the same locus shows
        up as different event types across haplotype pairs. These are
        either real evolutionary hotspots (recombination, repeats) or
        misleading PAF transitions; reviewer should look at the underlying
        PAFs before claiming inversion.

    high_assembly_error_risk.tsv
        Rows where assembly_error_risk == "high": single-pair support
        AND backbone fails or untested. Useful for the "we acknowledge
        these uncertain calls" supplementary table.

Classification rules — encoded as constants at the top of main() so a
reviewer can audit them in one place. Edit there to retune.

Usage:
    python3 STEP_BP6_joint_classify.py \\
        --atlas-json   results_bpatlas/05_atlas_data/atlas_data.json \\
        --popgen-tsv   ../inversion-popgen-toolkit/phase_8/popgen_candidates.tsv \\
        --mendelian-tsv ../results_inheritance/mendelian_table.tsv \\
        --popstats-tsv ../results_popstats/popstats_summary.tsv \\
        --out          results_bpatlas/06_joint/

Stub mode (no popgen/mendelian/popstats yet):
    python3 STEP_BP6_joint_classify.py \\
        --atlas-json   results_bpatlas/05_atlas_data/atlas_data.json \\
        --out          results_bpatlas/06_joint/

In stub mode every BP_ATLAS zone gets a row in joint_candidates.tsv with
popgen / Mendelian / popstats columns as 'NA'. Classification falls back
to C (BP-only) or E (structural rearrangement). This lets you produce a
valid file today and re-run when the popgen / Mendelian tables land.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path


# ---------------------------------------------------------------------------
# Schemas — declared up front so we can validate at load time
# ---------------------------------------------------------------------------
POPGEN_REQUIRED = ("popgen_id", "chrom", "popgen_start", "popgen_end")
POPGEN_BOOL_FIELDS = ("localPCA_yes", "theta_yes", "GHSL_yes")
POPGEN_OPTIONAL = ("n_k_clusters", "n_carriers")

MENDELIAN_REQUIRED = ("chrom", "interval_start", "interval_end", "mendelian_status")
MENDELIAN_OPTIONAL = ("n_informative_families",)

POPSTATS_REQUIRED = ("chrom", "interval_start", "interval_end",
                     "popstats_support")
POPSTATS_OPTIONAL = ("fst_between_regimes", "theta_pi_minor_regime",
                     "theta_pi_major_regime")

# Sentinel value for missing data — kept consistent across the script and
# in the final TSV so downstream consumers can grep -v NA reliably.
NA = "NA"


# ---------------------------------------------------------------------------
# I/O helpers
# ---------------------------------------------------------------------------
def read_tsv(path: Path) -> list[dict]:
    """Read a TSV emitted by any BP step. Handles:
      - leading '#'-comment lines that don't look like headers
      - the '# header' convention (BED-style commented column row)
      - the '# no <thing>' sentinel for empty tables
      - UTF-8 BOMs

    See STEP_BP5_prep_atlas_data.py for the logic explanation.
    """
    if path is None or not path.exists():
        return []
    with open(path, encoding="utf-8-sig") as fh:
        raw_lines = fh.readlines()
    if not raw_lines:
        return []

    first_idx = next((i for i, ln in enumerate(raw_lines) if ln.strip()), None)
    if first_idx is None:
        return []
    first = raw_lines[first_idx]

    treat_first_as_header = False
    if first.lstrip().startswith("#"):
        decommented = first.lstrip().lstrip("#").lstrip()
        if "\t" in decommented:
            cols = decommented.rstrip("\n").split("\t")
            if all(c and "/" not in c and "," not in c and " " not in c
                   for c in cols):
                treat_first_as_header = True

    if treat_first_as_header:
        decommented_header = raw_lines[first_idx].lstrip().lstrip("#").lstrip()
        body = [ln for ln in raw_lines[first_idx + 1:]
                if not ln.lstrip().startswith("#")]
        lines = [decommented_header] + body
    else:
        lines = [ln for ln in raw_lines if not ln.lstrip().startswith("#")]

    if not lines:
        return []
    return list(csv.DictReader(lines, delimiter="\t"))


def validate_columns(rows: list[dict], required: tuple[str, ...],
                     label: str) -> None:
    if not rows:
        return
    have = set(rows[0].keys())
    missing = [c for c in required if c not in have]
    if missing:
        raise SystemExit(
            f"[STEP_BP6] {label}: missing required column(s) "
            f"{missing}. Have: {sorted(have)}"
        )


def coerce_int_or_none(s: str | None) -> int | None:
    if s is None or s == "" or s == NA:
        return None
    try:
        return int(s)
    except (ValueError, TypeError):
        return None


def coerce_float_or_none(s: str | None) -> float | None:
    if s is None or s == "" or s == NA:
        return None
    try:
        return float(s)
    except (ValueError, TypeError):
        return None


def normalize_yes_no(s: str | None) -> str:
    """Coerce a variety of input encodings to 'yes' / 'no' / 'NA'."""
    if s is None:
        return NA
    s = str(s).strip().lower()
    if s in ("yes", "y", "true", "t", "1"):
        return "yes"
    if s in ("no", "n", "false", "f", "0"):
        return "no"
    if s in ("", "na", "n/a", "nan", "null", "none"):
        return NA
    # Defensive: anything unknown is NA, not yes
    return NA


# ---------------------------------------------------------------------------
# Reading the inputs
# ---------------------------------------------------------------------------
def load_atlas(atlas_json: Path) -> dict:
    """Load atlas_data.json and pre-build helper indices."""
    with open(atlas_json) as fh:
        atlas = json.load(fh)

    # Index reciprocity table by both cgar_zone_uid and cmac_zone_uid for
    # fast lookup of "does this zone have a bidirectional partner?".
    recip_by_uid: dict[str, dict] = {}
    for r in atlas.get("reciprocity", []):
        for k in ("cgar_zone_uid", "cmac_zone_uid"):
            if r.get(k):
                recip_by_uid[r[k]] = r
    atlas["_recip_by_uid"] = recip_by_uid
    return atlas


def load_popgen(path: Path | None) -> list[dict]:
    """Load popgen catalogue, normalize the yes/no columns, type the
    coordinates. Missing file returns []."""
    rows = read_tsv(path) if path else []
    validate_columns(rows, POPGEN_REQUIRED, "popgen-tsv")
    out = []
    for r in rows:
        rec = {
            "popgen_id":   r["popgen_id"],
            "chrom":       r["chrom"],
            "popgen_start": coerce_int_or_none(r["popgen_start"]),
            "popgen_end":   coerce_int_or_none(r["popgen_end"]),
        }
        for col in POPGEN_BOOL_FIELDS:
            rec[col] = normalize_yes_no(r.get(col))
        for col in POPGEN_OPTIONAL:
            v = r.get(col)
            rec[col] = v if (v not in (None, "", NA)) else NA
        # Pre-compute the n_methods_yes summary
        rec["popgen_n_methods_yes"] = sum(
            1 for c in POPGEN_BOOL_FIELDS if rec[c] == "yes"
        )
        if rec["popgen_start"] is None or rec["popgen_end"] is None:
            print(f"[STEP_BP6] WARN: popgen row {rec['popgen_id']} has "
                  "non-numeric start/end, skipping", file=sys.stderr)
            continue
        out.append(rec)
    print(f"[STEP_BP6] popgen rows loaded: {len(out)}", file=sys.stderr)
    return out


def load_mendelian(path: Path | None) -> list[dict]:
    rows = read_tsv(path) if path else []
    validate_columns(rows, MENDELIAN_REQUIRED, "mendelian-tsv")
    out = []
    for r in rows:
        rec = {
            "chrom":          r["chrom"],
            "interval_start": coerce_int_or_none(r["interval_start"]),
            "interval_end":   coerce_int_or_none(r["interval_end"]),
            "mendelian_status":       r.get("mendelian_status", NA) or NA,
            "n_informative_families": r.get("n_informative_families", NA) or NA,
        }
        if rec["interval_start"] is None or rec["interval_end"] is None:
            continue
        out.append(rec)
    print(f"[STEP_BP6] Mendelian rows loaded: {len(out)}", file=sys.stderr)
    return out


def load_popstats(path: Path | None) -> list[dict]:
    rows = read_tsv(path) if path else []
    validate_columns(rows, POPSTATS_REQUIRED, "popstats-tsv")
    out = []
    for r in rows:
        rec = {
            "chrom":          r["chrom"],
            "interval_start": coerce_int_or_none(r["interval_start"]),
            "interval_end":   coerce_int_or_none(r["interval_end"]),
            "popstats_support":    normalize_yes_no(r.get("popstats_support")),
            "fst_between_regimes": r.get("fst_between_regimes", NA) or NA,
            "theta_pi_minor_regime": r.get("theta_pi_minor_regime", NA) or NA,
            "theta_pi_major_regime": r.get("theta_pi_major_regime", NA) or NA,
        }
        if rec["interval_start"] is None or rec["interval_end"] is None:
            continue
        out.append(rec)
    print(f"[STEP_BP6] popstats rows loaded: {len(out)}", file=sys.stderr)
    return out


# ---------------------------------------------------------------------------
# Overlap utilities — symmetric windowed overlap between two intervals.
# All coordinates are 1-based inclusive on input; treated as half-open
# internally for comparison cleanliness.
# ---------------------------------------------------------------------------
def intervals_overlap(a_start: int, a_end: int,
                      b_start: int, b_end: int,
                      pad: int = 0) -> bool:
    """True if [a_start-pad, a_end+pad] intersects [b_start-pad, b_end+pad].
    Symmetric: padding is applied to both sides."""
    return (a_end + pad) >= (b_start - pad) and (b_end + pad) >= (a_start - pad)


def find_overlapping(rows: list[dict],
                     chrom: str, a_start: int, a_end: int,
                     pad: int,
                     b_start_key: str = "interval_start",
                     b_end_key: str = "interval_end") -> list[dict]:
    """Linear scan — these tables are small (~hundreds of rows)."""
    out = []
    for r in rows:
        if r.get("chrom") != chrom:
            continue
        bs = r.get(b_start_key); be = r.get(b_end_key)
        if bs is None or be is None:
            continue
        if intervals_overlap(a_start, a_end, bs, be, pad=pad):
            out.append(r)
    return out


# ---------------------------------------------------------------------------
# Classification rules — exposed as a function at module top so reviewers
# can audit. Returns (final_class, class_reason).
# ---------------------------------------------------------------------------
def classify(row: dict) -> tuple[str, str]:
    """Apply the A-E classification rules to one joint-table row.

    Class E first — structural-category override beats evidence tier.
    A fission/fusion zone is not an inversion candidate even if popgen
    also flagged the same locus.
    """
    # Class E: structural rearrangement that is not a simple inversion
    dom = (row.get("bp_dominant_event_type") or "").strip().lower()
    if dom in ("fission_or_fusion", "inverted_translocation"):
        return "E", f"BP dominant_event_type={dom}; not a simple inversion"

    # All popgen flags must be 'yes' to count as popgen-supported
    pg_yes = all(row.get(c) == "yes" for c in POPGEN_BOOL_FIELDS)
    pg_score = row.get("popgen_n_methods_yes", 0)
    has_bp  = bool(row.get("bp_zone_uid")) and row["bp_zone_uid"] != NA
    has_pg  = bool(row.get("popgen_id"))   and row["popgen_id"]   != NA

    bidir   = row.get("bp_reciprocal_bidirectional") == "yes"
    mendel  = row.get("mendelian_status", NA)
    mendel_ok = mendel == "consistent"

    # Class A: popgen (all 3) + reciprocal BP + Mendelian consistent
    if has_bp and has_pg and pg_yes and bidir and mendel_ok:
        return "A", "popgen=3/3, BP reciprocal bidirectional, Mendelian consistent"

    # Class A relaxed when Mendelian is untested / NA — still strongest
    # popgen+BP combination available, just flagged for inheritance follow-up
    if has_bp and has_pg and pg_yes and bidir and mendel in (NA, "untested"):
        return "A*", "popgen=3/3, BP reciprocal bidirectional, Mendelian pending"

    # Class B: popgen-supported + non-reciprocal / partial BP support
    if has_bp and has_pg and pg_score >= 1:
        return "B", (f"popgen={pg_score}/3, BP support but not bidirectional "
                     f"(reciprocal={bidir})")

    # Class C: BP zone only, no popgen at any window
    if has_bp and not has_pg:
        return "C", "BP_ATLAS zone present; no popgen overlap at any window"

    # Class D: popgen flagged but no BP support
    if has_pg and not has_bp:
        return "D", f"popgen={pg_score}/3; no BP zone overlap at any window"

    # Fallback (shouldn't happen in a clean join)
    return "?", "unclassifiable — empty row"


# ---------------------------------------------------------------------------
# Assembly-error risk + warning flags
# ---------------------------------------------------------------------------
# The single most important reviewer concern with PAF-based breakpoint calls
# is "could this single breakpoint just be an assembly error?". BP_ATLAS has
# three structural filters against this — multi-pair support, Pass B
# backbone check, and reciprocity from the other anchor — but the final
# table needs to surface them explicitly so a reviewer doesn't have to
# reconstruct the reasoning.
#
# assembly_error_risk is a 3-tier summary; flags is a fine-grained list of
# every individual warning that fired.

def compute_assembly_error_risk(row: dict) -> str:
    """
    high   : single-pair support AND backbone fails or untested
    medium : single-pair support OR backbone fails
    low    : >=2 supporting pairs AND backbone yes/partial
    NA     : no BP zone present (popgen-only Class D row)
    """
    if not row.get("bp_zone_uid") or row["bp_zone_uid"] == NA:
        return NA

    try:
        n_pairs = int(row.get("bp_support_pair_count", 0) or 0)
    except (ValueError, TypeError):
        n_pairs = 0
    backbone = (row.get("bp_backbone_support") or "").strip().lower()

    single_pair = (n_pairs <= 1)
    no_backbone = (backbone == "no")
    backbone_ok = (backbone in ("yes", "partial"))

    if single_pair and (no_backbone or backbone == "n/a" or backbone == ""):
        return "high"
    if single_pair or no_backbone:
        return "medium"
    if not single_pair and backbone_ok:
        return "low"
    # Fallback: e.g. 2-pair support with backbone n/a (no Pass B run)
    return "medium"


def compute_flags(row: dict) -> str:
    """Semicolon-joined list of every condition that should make a
    reviewer slow down on this row. Empty string for clean rows.
    """
    f: list[str] = []

    if row.get("bp_zone_uid") and row["bp_zone_uid"] != NA:
        try:
            n_pairs = int(row.get("bp_support_pair_count", 0) or 0)
        except (ValueError, TypeError):
            n_pairs = 0
        if n_pairs <= 1:
            f.append("single_pair_support")

        backbone = (row.get("bp_backbone_support") or "").strip().lower()
        if backbone == "no":
            f.append("no_backbone")
        elif backbone in ("", "n/a"):
            f.append("backbone_untested")

        # C-tier query/target (assembly quality concern)
        qc = (row.get("bp_best_qc_combo") or "").upper()
        if "C" in qc:
            f.append("c_tier_assembly_involved")

        # Breakpoint-reuse hotspot (new BP3 column)
        try:
            n_distinct = int(row.get("bp_n_distinct_event_classes", 1) or 1)
        except (ValueError, TypeError):
            n_distinct = 1
        if n_distinct > 1:
            f.append("reuse_hotspot")

        if (row.get("bp_confidence") or "").lower() == "low":
            f.append("low_confidence_only")

        dom = (row.get("bp_dominant_event_type") or "").lower()
        if dom in ("fission_or_fusion", "inverted_translocation"):
            f.append("complex_rearrangement")

    return "; ".join(f)


# ---------------------------------------------------------------------------
# Main join logic
# ---------------------------------------------------------------------------
def build_joint_table(
    atlas: dict,
    popgen_rows: list[dict],
    mendelian_rows: list[dict],
    popstats_rows: list[dict],
    overlap_windows: list[int],
) -> list[dict]:
    """Full-outer join BP_ATLAS zones × popgen catalogue at the largest
    window, with per-window overlap flags. Then for each row, attach
    Mendelian + popstats info by chromosomal overlap.

    Each output row is keyed by (popgen_id, bp_zone_uid). A BP zone with
    no popgen match emits one row with empty popgen fields. A popgen
    interval with no BP match emits one row with empty BP fields. A
    many-to-many overlap emits one row per pair.
    """
    max_window = max(overlap_windows)
    zones = atlas.get("zones", [])
    recip = atlas.get("_recip_by_uid", {})

    # Index BP zones by chrom for popgen-driven lookup
    bp_by_chrom: dict[str, list[dict]] = defaultdict(list)
    for z in zones:
        bp_by_chrom[z["chrom"]].append(z)

    # Track which BP zones get joined to at least one popgen row, so we can
    # emit unmatched BP zones afterward.
    matched_bp_uids: set[str] = set()
    matched_popgen_ids: set[str] = set()

    out_rows: list[dict] = []

    # ---- Pass 1: every popgen row × overlapping BP zones --------------
    for pg in popgen_rows:
        # All BP zones on the same chrom within max_window
        overlapping_bp = find_overlapping(
            bp_by_chrom.get(pg["chrom"], []),
            chrom=pg["chrom"],
            a_start=pg["popgen_start"], a_end=pg["popgen_end"],
            pad=max_window,
            b_start_key="zone_start", b_end_key="zone_end",
        )
        if overlapping_bp:
            for bp in overlapping_bp:
                matched_bp_uids.add(bp["zone_uid"])
                matched_popgen_ids.add(pg["popgen_id"])
                row = _make_row(pg, bp, recip, overlap_windows,
                                mendelian_rows, popstats_rows)
                out_rows.append(row)
        else:
            # Popgen-only (Class D candidate)
            matched_popgen_ids.add(pg["popgen_id"])
            row = _make_row(pg, None, recip, overlap_windows,
                            mendelian_rows, popstats_rows)
            out_rows.append(row)

    # ---- Pass 2: BP zones with no popgen match (Class C candidates) ----
    for z in zones:
        if z["zone_uid"] in matched_bp_uids:
            continue
        row = _make_row(None, z, recip, overlap_windows,
                        mendelian_rows, popstats_rows)
        out_rows.append(row)

    # Stable candidate IDs in order of emission
    for i, r in enumerate(out_rows):
        r["candidate_id"] = f"CAND_{i:06d}"

    return out_rows


def _make_row(pg: dict | None, bp: dict | None,
              recip: dict[str, dict],
              overlap_windows: list[int],
              mendelian_rows: list[dict],
              popstats_rows: list[dict]) -> dict:
    """Build one output row from (popgen?, bp_zone?). At least one of the
    two must be non-None.
    """
    row: dict = {"candidate_id": ""}  # filled by caller

    # ---- popgen side ---------------------------------------------------
    if pg is not None:
        row.update({
            "popgen_id":     pg["popgen_id"],
            "popgen_chrom":  pg["chrom"],
            "popgen_start":  pg["popgen_start"],
            "popgen_end":    pg["popgen_end"],
            "localPCA_yes":  pg["localPCA_yes"],
            "theta_yes":     pg["theta_yes"],
            "GHSL_yes":      pg["GHSL_yes"],
            "popgen_n_methods_yes": pg["popgen_n_methods_yes"],
        })
        for col in POPGEN_OPTIONAL:
            row[f"popgen_{col}"] = pg.get(col, NA)
    else:
        row.update({
            "popgen_id": NA, "popgen_chrom": NA,
            "popgen_start": NA, "popgen_end": NA,
            "localPCA_yes": NA, "theta_yes": NA, "GHSL_yes": NA,
            "popgen_n_methods_yes": 0,
            **{f"popgen_{c}": NA for c in POPGEN_OPTIONAL},
        })

    # ---- BP side -------------------------------------------------------
    if bp is not None:
        bp_uid = bp.get("zone_uid", NA)
        row.update({
            "bp_zone_uid":      bp_uid,
            "bp_anchor":        bp.get("anchor_species", NA),
            "bp_chrom":         bp["chrom"],
            "bp_start":         bp.get("zone_start", NA),
            "bp_end":           bp.get("zone_end", NA),
            "bp_centroid":      bp.get("zone_centroid", NA),
            "bp_zone_kind":     bp.get("zone_kind", "inversion"),
            "bp_dominant_event_type": bp.get("dominant_event_type", NA),
            "bp_support_pair_count": bp.get("support_pair_count", 0),
            "bp_confidence":    bp.get("confidence", NA),
            "bp_backbone_support": bp.get("backbone_support", NA),
            # Fields needed by compute_flags() / compute_assembly_error_risk()
            "bp_best_qc_combo": bp.get("best_qc_combo", NA),
            "bp_n_distinct_event_classes": bp.get("n_distinct_event_classes", 1),
            "bp_event_classes": bp.get("event_classes", NA),
            "haplotypes_supporting": bp.get("support_pairs", NA),
        })
        # Reciprocal partner via the BP3c-pre-joined column
        recip_partner_id = bp.get("reciprocal_zone_id", "none")
        row["bp_reciprocal_zone_id"] = (
            recip_partner_id if recip_partner_id and recip_partner_id != "none"
            else NA
        )
        # Bidirectional flag from the reciprocity table
        r = recip.get(bp_uid)
        row["bp_reciprocal_bidirectional"] = (
            r.get("bidirectional", "no") if r else "no"
        )
    else:
        row.update({
            "bp_zone_uid": NA, "bp_anchor": NA, "bp_chrom": NA,
            "bp_start": NA, "bp_end": NA, "bp_centroid": NA,
            "bp_zone_kind": NA, "bp_dominant_event_type": NA,
            "bp_support_pair_count": 0, "bp_confidence": NA,
            "bp_backbone_support": NA,
            "bp_best_qc_combo": NA,
            "bp_n_distinct_event_classes": NA,
            "bp_event_classes": NA,
            "haplotypes_supporting": NA,
            "bp_reciprocal_zone_id": NA, "bp_reciprocal_bidirectional": NA,
        })

    # ---- Per-window overlap flags --------------------------------------
    # Use the popgen interval and the BP zone interval if both exist; else NA.
    if pg is not None and bp is not None:
        for w in overlap_windows:
            ov = intervals_overlap(
                pg["popgen_start"], pg["popgen_end"],
                bp["zone_start"], bp["zone_end"], pad=w,
            )
            row[f"overlaps_{_humanize_bp(w)}"] = "yes" if ov else "no"
    else:
        for w in overlap_windows:
            row[f"overlaps_{_humanize_bp(w)}"] = NA

    # ---- Mendelian + popstats joins ------------------------------------
    # Use whichever interval is present (prefer popgen, fall back to BP)
    if pg is not None:
        chrom = pg["chrom"]; q_start = pg["popgen_start"]; q_end = pg["popgen_end"]
    elif bp is not None:
        chrom = bp["chrom"]; q_start = bp["zone_start"]; q_end = bp["zone_end"]
    else:
        chrom = q_start = q_end = None

    if chrom is not None:
        # Mendelian — strict overlap (no padding); we trust the family
        # tables' own interval definitions.
        m_hits = find_overlapping(mendelian_rows, chrom, q_start, q_end, pad=0)
        if m_hits:
            # If multiple, prefer 'consistent' > 'untested' > 'inconsistent'
            order = {"consistent": 0, "untested": 1, "inconsistent": 2,
                     NA: 3}
            best = sorted(m_hits,
                          key=lambda r: order.get(r["mendelian_status"], 4))[0]
            row["mendelian_status"]       = best["mendelian_status"]
            row["n_informative_families"] = best.get("n_informative_families", NA)
        else:
            row["mendelian_status"]       = NA
            row["n_informative_families"] = NA

        # Popstats
        s_hits = find_overlapping(popstats_rows, chrom, q_start, q_end, pad=0)
        if s_hits:
            best = s_hits[0]
            row["popstats_support"]    = best["popstats_support"]
            row["fst_between_regimes"] = best.get("fst_between_regimes", NA)
        else:
            row["popstats_support"]    = NA
            row["fst_between_regimes"] = NA
    else:
        row["mendelian_status"]       = NA
        row["n_informative_families"] = NA
        row["popstats_support"]       = NA
        row["fst_between_regimes"]    = NA

    # ---- Assembly-error risk + warning flags ---------------------------
    # Computed BEFORE classify() so classify() could in principle consult
    # them. Surfaces the reviewer concern "could this be an assembly
    # error?" explicitly rather than burying it in support_pair_count and
    # backbone_support columns the reviewer has to combine mentally.
    row["assembly_error_risk"] = compute_assembly_error_risk(row)
    row["flags"]               = compute_flags(row)

    # ---- Classification ------------------------------------------------
    cls, why = classify(row)
    row["final_class"]  = cls
    row["class_reason"] = why

    return row


def _humanize_bp(n: int) -> str:
    """1000 -> '1k', 50000 -> '50k', 500000 -> '500k', 1000000 -> '1M'."""
    if n % 1_000_000 == 0: return f"{n // 1_000_000}M"
    if n % 1_000 == 0:     return f"{n // 1_000}k"
    return str(n)


# ---------------------------------------------------------------------------
# Output writers
# ---------------------------------------------------------------------------
# Column order for the main TSV — chosen to read top-to-bottom as a
# narrative: identity -> popgen -> BP -> evidence overlaps -> Mendelian
# -> popstats -> final class.
COLUMN_ORDER = [
    "candidate_id",
    "final_class", "class_reason",
    "assembly_error_risk", "flags",
    # popgen side
    "popgen_id", "popgen_chrom", "popgen_start", "popgen_end",
    "localPCA_yes", "theta_yes", "GHSL_yes", "popgen_n_methods_yes",
    "popgen_n_k_clusters", "popgen_n_carriers",
    # BP side
    "bp_zone_uid", "bp_anchor", "bp_chrom", "bp_start", "bp_end",
    "bp_centroid", "bp_zone_kind", "bp_dominant_event_type",
    "bp_support_pair_count", "bp_confidence", "bp_backbone_support",
    "bp_best_qc_combo", "bp_n_distinct_event_classes", "bp_event_classes",
    "haplotypes_supporting",
    "bp_reciprocal_zone_id", "bp_reciprocal_bidirectional",
    # overlap flags (per window) — added dynamically based on --overlap-windows
    # Mendelian + popstats
    "mendelian_status", "n_informative_families",
    "popstats_support", "fst_between_regimes",
]


def write_tsv(rows: list[dict], path: Path, windows: list[int]) -> None:
    if not rows:
        with open(path, "w") as fh:
            fh.write("# no rows\n")
        return
    # Insert per-window overlap cols at a stable position (right after
    # bp_reciprocal_bidirectional, before Mendelian)
    overlap_cols = [f"overlaps_{_humanize_bp(w)}" for w in windows]
    idx = COLUMN_ORDER.index("bp_reciprocal_bidirectional") + 1
    cols = COLUMN_ORDER[:idx] + overlap_cols + COLUMN_ORDER[idx:]

    # Ensure every row has every column (fill NA for missing)
    for r in rows:
        for c in cols:
            r.setdefault(c, NA)

    with open(path, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=cols, delimiter="\t",
                                extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--atlas-json", required=True, type=Path,
                    help="atlas_data.json from STEP_BP5_prep_atlas_data.py")
    ap.add_argument("--popgen-tsv", type=Path, default=None,
                    help="OPTIONAL inversion-popgen-toolkit phase_8 catalogue")
    ap.add_argument("--mendelian-tsv", type=Path, default=None,
                    help="OPTIONAL Mendelian-inheritance per-locus table")
    ap.add_argument("--popstats-tsv", type=Path, default=None,
                    help="OPTIONAL Fst/theta popstats per-locus table")
    ap.add_argument("--out", required=True, type=Path,
                    help="Output directory")
    ap.add_argument("--overlap-windows", default="50000,100000,500000",
                    help="Comma-separated bp windows for the overlap "
                         "yes/no columns. Default: 50000,100000,500000")
    args = ap.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    windows = [int(w) for w in args.overlap_windows.split(",") if w.strip()]

    atlas       = load_atlas(args.atlas_json)
    popgen_rows = load_popgen(args.popgen_tsv)
    mendel_rows = load_mendelian(args.mendelian_tsv)
    stats_rows  = load_popstats(args.popstats_tsv)

    rows = build_joint_table(atlas, popgen_rows, mendel_rows, stats_rows,
                             overlap_windows=windows)
    print(f"[STEP_BP6] joint candidates: {len(rows)} rows", file=sys.stderr)

    # Sort: class A first, then by combined evidence score
    cls_order = {"A": 0, "A*": 1, "B": 2, "C": 3, "D": 4, "E": 5, "?": 9}
    def score(r):
        pg_n = r.get("popgen_n_methods_yes", 0)
        try: pg_n = int(pg_n)
        except: pg_n = 0
        bp_n = r.get("bp_support_pair_count", 0)
        try: bp_n = int(bp_n)
        except: bp_n = 0
        return (cls_order.get(r["final_class"], 9),
                -(pg_n + bp_n),
                r.get("popgen_chrom") or r.get("bp_chrom", ""))
    rows.sort(key=score)

    # Main joint table
    main_path = args.out / "joint_candidates.tsv"
    write_tsv(rows, main_path, windows)
    print(f"[STEP_BP6] -> {main_path}", file=sys.stderr)

    # Summary by class
    summary_path = args.out / "joint_candidates_summary.tsv"
    cls_counts: dict[str, int] = defaultdict(int)
    for r in rows:
        cls_counts[r["final_class"]] += 1
    with open(summary_path, "w", newline="") as fh:
        w = csv.writer(fh, delimiter="\t")
        w.writerow(["final_class", "n_rows"])
        for cls in sorted(cls_counts.keys(),
                          key=lambda c: cls_order.get(c, 9)):
            w.writerow([cls, cls_counts[cls]])
    print(f"[STEP_BP6] -> {summary_path}  ({dict(cls_counts)})",
          file=sys.stderr)

    # Class-specific side files
    class_c = [r for r in rows if r["final_class"] == "C"]
    class_d = [r for r in rows if r["final_class"] == "D"]
    write_tsv(class_c, args.out / "bp_with_no_popgen_support.tsv", windows)
    write_tsv(class_d, args.out / "popgen_with_no_bp_support.tsv", windows)
    print(f"[STEP_BP6] -> {args.out / 'bp_with_no_popgen_support.tsv'} "
          f"({len(class_c)} rows)", file=sys.stderr)
    print(f"[STEP_BP6] -> {args.out / 'popgen_with_no_bp_support.tsv'} "
          f"({len(class_d)} rows)", file=sys.stderr)

    # Reviewer-targeted side files for the assembly-quality concerns
    reuse_hotspots = [r for r in rows
                      if "reuse_hotspot" in (r.get("flags") or "")]
    high_risk      = [r for r in rows
                      if r.get("assembly_error_risk") == "high"]
    write_tsv(reuse_hotspots, args.out / "breakpoint_reuse_hotspots.tsv",
              windows)
    write_tsv(high_risk,      args.out / "high_assembly_error_risk.tsv",
              windows)
    print(f"[STEP_BP6] -> {args.out / 'breakpoint_reuse_hotspots.tsv'} "
          f"({len(reuse_hotspots)} rows; zones where same locus shows "
          f"different event types in different pairs)",
          file=sys.stderr)
    print(f"[STEP_BP6] -> {args.out / 'high_assembly_error_risk.tsv'} "
          f"({len(high_risk)} rows; single-pair + no/untested backbone)",
          file=sys.stderr)


if __name__ == "__main__":
    main()
