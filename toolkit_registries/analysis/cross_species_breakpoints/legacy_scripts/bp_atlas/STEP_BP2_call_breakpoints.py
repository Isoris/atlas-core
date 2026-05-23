#!/usr/bin/env python3
"""
STEP_BP2_call_breakpoints.py

Call breakpoints from each pairwise wfmash PAF produced by STEP_BP1.
(STEP_BP1 uses wfmash --approx-mapping, NOT minimap2 — so PAF MAPQ is
1-5, which is why --min-mapq defaults to 1 here.)
Reuses the breakpoint detection logic from scripts/STEP_C_call_breakpoints.py
but adapted for non-PanSN naming and haplotype-pair metadata.

Detects four classes of events between adjacent collinear blocks on the
same query chromosome:

    INVERSION_breakpoint    same target chrom, strand flip
    INTERCHROM_breakpoint   different target chrom (translocation/fusion sig)
    INVERTED_TRANSLOC       different target chrom AND strand flip
    NONCOLLINEAR            same chrom, same strand, but target jump

Usage:
    python3 STEP_BP2_call_breakpoints.py \\
        --paf-dir results_bpatlas/02_paf/ \\
        --out    results_bpatlas/03_breakpoints/ \\
        [--min-block-bp 50000] [--max-gap-bp 2000000]

Default thresholds are looser than the inter-species pipeline (50 kb
instead of 200 kb) because intra-specific haplotype pairs have higher
identity and we want the inversion-paper resolution, not chromosomal
rearrangements.
"""
from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path


# ----------------------------------------------------------------------------
# PAF parsing — wfmash output, no PanSN naming
# ----------------------------------------------------------------------------
@dataclass
class PafRow:
    qname: str
    qlen: int
    qstart: int
    qend: int
    strand: str   # '+' or '-'
    tname: str
    tlen: int
    tstart: int
    tend: int
    matches: int
    aln_len: int
    mapq: int

    @property
    def qspan(self) -> int:
        return self.qend - self.qstart

    @property
    def identity(self) -> float:
        return self.matches / self.aln_len if self.aln_len else 0.0


def parse_paf(path: Path) -> list[PafRow]:
    rows = []
    with open(path) as fh:
        for line in fh:
            if not line.strip():
                continue
            f = line.rstrip("\n").split("\t")
            if len(f) < 12:
                continue
            try:
                rows.append(PafRow(
                    qname=f[0], qlen=int(f[1]),
                    qstart=int(f[2]), qend=int(f[3]),
                    strand=f[4],
                    tname=f[5], tlen=int(f[6]),
                    tstart=int(f[7]), tend=int(f[8]),
                    matches=int(f[9]), aln_len=int(f[10]),
                    mapq=int(f[11]),
                ))
            except ValueError:
                continue
    return rows


def _compute_target_coverage(rows: list[PafRow]) -> dict[str, dict[str, int]]:
    """Per-query-chrom map of target_chrom -> aligned bp.

    Used to reclassify INTERCHROM_breakpoint events into 'fission_or_fusion'
    vs 'translocation' à la STEP_CS01: if at most 2 target chroms cover a
    given query chrom AND one of them dominates (>=50% of aligned bp), the
    interchromosomal transitions on that query chrom likely reflect a
    lineage-specific fission/fusion rather than a clean translocation.

    Returns: { query_chrom: { target_chrom: aligned_bp } }
    """
    cov: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for r in rows:
        cov[r.qname][r.tname] += r.aln_len
    return {q: dict(t) for q, t in cov.items()}


def _classify_interchrom(qchrom: str,
                         target_coverage: dict[str, dict[str, int]]) -> tuple[str, str]:
    """Apply STEP_CS01's dominant-Mac rule on the per-pair coverage map.

    Returns (refined_label, dominance_summary). The summary string captures
    the top-2 target chroms and their fraction of aligned bp for the zone
    builder downstream to aggregate. Empty target_coverage -> fallback
    'translocation' with summary 'unknown'.
    """
    macs = target_coverage.get(qchrom, {})
    if not macs:
        return "translocation", "unknown"
    total = sum(macs.values())
    if total <= 0:
        return "translocation", "unknown"
    sorted_macs = sorted(macs.items(), key=lambda x: -x[1])
    dominant_frac = sorted_macs[0][1] / total
    n_macs = len([m for m, v in sorted_macs if v >= 0.05 * total])
    top2 = sorted_macs[:2]
    summary = "; ".join(f"{m}:{v/total:.2f}" for m, v in top2)
    if n_macs <= 2 and dominant_frac >= 0.5:
        return "fission_or_fusion", summary
    return "translocation", summary


# ----------------------------------------------------------------------------
# Breakpoint calling on a single pair
# ----------------------------------------------------------------------------
def call_breakpoints_one_pair(
    rows: list[PafRow],
    pair_meta: dict,
    min_block_bp: int = 50_000,
    max_gap_bp: int = 2_000_000,
    min_mapq: int = 1,
) -> list[dict]:
    """
    Walk each query chromosome and detect breakpoints between consecutive
    blocks. Returns a list of event dicts with the master schema.

    Each event gets an `event_type_refined` column:
      - INVERSION_breakpoint      -> 'inversion'
      - INVERTED_TRANSLOC         -> 'inverted_translocation'
      - INTERCHROM_breakpoint     -> 'fission_or_fusion' or 'translocation'
                                     (CS-style: see _classify_interchrom)
      - NONCOLLINEAR              -> 'noncollinear'
    Plus `target_dominance` (top-2 target chrom fractions on this query
    chrom) so zone clustering can aggregate the signal.
    """
    # Filter blocks: require min size + min mapq
    rows = [r for r in rows if r.qspan >= min_block_bp and r.mapq >= min_mapq]
    if not rows:
        return []

    # Per-query-chrom target-coverage map — computed AFTER filtering so the
    # fractions reflect the same blocks the breakpoint walk considers.
    target_cov = _compute_target_coverage(rows)

    # Group by query chromosome
    by_qchrom: dict[str, list[PafRow]] = defaultdict(list)
    for r in rows:
        by_qchrom[r.qname].append(r)

    events = []
    for qchrom, blist in by_qchrom.items():
        blist.sort(key=lambda b: b.qstart)
        for b1, b2 in zip(blist[:-1], blist[1:]):
            gap = b2.qstart - b1.qend
            if gap > max_gap_bp:
                continue
            if gap < -50_000:
                # Heavy overlap — likely repeat artifact, not a real breakpoint
                continue

            same_chrom = (b1.tname == b2.tname)
            strand_flip = (b1.strand != b2.strand)

            # Classify the event between b1 and b2
            if same_chrom and strand_flip:
                etype = "INVERSION_breakpoint"
            elif (not same_chrom) and strand_flip:
                etype = "INVERTED_TRANSLOC"
            elif not same_chrom:
                etype = "INTERCHROM_breakpoint"
            elif b1.strand == "+" and b2.tstart < b1.tend - min_block_bp:
                etype = "NONCOLLINEAR"
            elif b1.strand == "-" and b2.tend > b1.tstart + min_block_bp:
                etype = "NONCOLLINEAR"
            else:
                # collinear, no event
                continue

            # Anchor the breakpoint to the query coordinate halfway through the gap
            q_bp = (b1.qend + b2.qstart) // 2

            # Partner: where on the target this breakpoint connects to
            t_left  = b1.tend if b1.strand == "+" else b1.tstart
            t_right = b2.tstart if b2.strand == "+" else b2.tend

            # Refined classification (CS-style for INTERCHROM; pass-through
            # label for the other classes so a single column suffices in
            # downstream tools).
            if etype == "INVERSION_breakpoint":
                refined, dominance = "inversion", ""
            elif etype == "INVERTED_TRANSLOC":
                refined, dominance = "inverted_translocation", ""
            elif etype == "INTERCHROM_breakpoint":
                refined, dominance = _classify_interchrom(qchrom, target_cov)
            elif etype == "NONCOLLINEAR":
                refined, dominance = "noncollinear", ""
            else:
                refined, dominance = etype, ""

            events.append({
                # identity / provenance
                "pair_id":         pair_meta["pair_id"],
                "query_id":        pair_meta["query_id"],
                "target_id":       pair_meta["target_id"],
                "query_species":   pair_meta["query_species"],
                "target_species":  pair_meta["target_species"],
                "pair_kind":       pair_meta["pair_kind"],
                "query_qc":        pair_meta["query_qc"],
                "target_qc":       pair_meta["target_qc"],
                # query-side breakpoint location (the coordinate to cluster on)
                "query_chrom":     qchrom,
                "query_pos":       q_bp,
                "query_left_end":  b1.qend,
                "query_right_start": b2.qstart,
                # target-side breakpoint partners
                "target_left_chrom":  b1.tname,
                "target_left_pos":    t_left,
                "target_right_chrom": b2.tname,
                "target_right_pos":   t_right,
                # event metadata
                "event_class":     etype,
                "event_type_refined": refined,
                "target_dominance":   dominance,
                "left_strand":     b1.strand,
                "right_strand":    b2.strand,
                "gap_bp":          gap,
                "left_block_bp":   b1.qspan,
                "right_block_bp":  b2.qspan,
                "left_identity":   round(b1.identity, 4),
                "right_identity":  round(b2.identity, 4),
                "left_mapq":       b1.mapq,
                "right_mapq":      b2.mapq,
            })

    return events


# ----------------------------------------------------------------------------
# Driver — process every PAF in the input directory
# ----------------------------------------------------------------------------
def process_directory(
    paf_dir: Path,
    out_dir: Path,
    min_block_bp: int,
    max_gap_bp: int,
    min_mapq: int,
):
    out_dir.mkdir(parents=True, exist_ok=True)
    paf_files = sorted(paf_dir.glob("*.paf"))
    if not paf_files:
        sys.exit(f"[STEP_BP2] No PAF files found in {paf_dir}")

    print(f"[STEP_BP2] Processing {len(paf_files)} PAFs", file=sys.stderr)

    all_events = []
    per_pair_counts: dict[str, dict] = {}

    for paf in paf_files:
        meta_path = paf.with_suffix(".meta.tsv")
        if not meta_path.exists():
            print(f"[STEP_BP2] WARNING: no meta for {paf.name}, skipping", file=sys.stderr)
            continue

        # Read pair metadata (single data row)
        with open(meta_path) as fh:
            reader = csv.DictReader(fh, delimiter="\t")
            meta = next(iter(reader), None)
        if meta is None:
            print(f"[STEP_BP2] WARNING: empty meta for {paf.name}", file=sys.stderr)
            continue

        rows = parse_paf(paf)
        events = call_breakpoints_one_pair(
            rows, meta,
            min_block_bp=min_block_bp,
            max_gap_bp=max_gap_bp,
            min_mapq=min_mapq,
        )
        all_events.extend(events)

        # Per-pair summary
        cls_counts: dict[str, int] = defaultdict(int)
        refined_counts: dict[str, int] = defaultdict(int)
        for e in events:
            cls_counts[e["event_class"]] += 1
            refined_counts[e["event_type_refined"]] += 1
        per_pair_counts[meta["pair_id"]] = {
            "pair_kind": meta["pair_kind"],
            "query_qc": meta["query_qc"],
            "target_qc": meta["target_qc"],
            "n_paf_records": len(rows),
            "n_events_total": len(events),
            **{cls: cls_counts.get(cls, 0) for cls in
               ("INVERSION_breakpoint", "INVERTED_TRANSLOC",
                "INTERCHROM_breakpoint", "NONCOLLINEAR")},
            # CS-refined split of INTERCHROM into fission/fusion vs translocation
            "fission_or_fusion": refined_counts.get("fission_or_fusion", 0),
            "translocation":    refined_counts.get("translocation", 0),
        }
        print(f"  {meta['pair_id']:40s} {len(rows):6d} PAF rows, "
              f"{len(events):4d} events", file=sys.stderr)

    # ------------------------------------------------------------------------
    # Write master events table — one row per breakpoint, all pairs combined
    # ------------------------------------------------------------------------
    master_path = out_dir / "breakpoints_raw.tsv"
    if all_events:
        with open(master_path, "w", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(all_events[0].keys()),
                                    delimiter="\t")
            writer.writeheader()
            writer.writerows(all_events)
    else:
        # Touch empty file with header so downstream doesn't fail
        with open(master_path, "w") as fh:
            fh.write("# no breakpoints called — check input PAFs\n")
    print(f"[STEP_BP2] Wrote {len(all_events)} raw breakpoints -> {master_path}",
          file=sys.stderr)

    # ------------------------------------------------------------------------
    # Per-pair summary
    # ------------------------------------------------------------------------
    summary_path = out_dir / "per_pair_summary.tsv"
    with open(summary_path, "w") as fh:
        fh.write("pair_id\tpair_kind\tquery_qc\ttarget_qc\tn_paf_records\t"
                 "n_events_total\tINVERSION\tINVERTED_TRANSLOC\t"
                 "INTERCHROM\tNONCOLLINEAR\t"
                 "fission_or_fusion\ttranslocation\n")
        for pid, c in sorted(per_pair_counts.items()):
            fh.write(f"{pid}\t{c['pair_kind']}\t{c['query_qc']}\t"
                     f"{c['target_qc']}\t{c['n_paf_records']}\t"
                     f"{c['n_events_total']}\t"
                     f"{c['INVERSION_breakpoint']}\t"
                     f"{c['INVERTED_TRANSLOC']}\t"
                     f"{c['INTERCHROM_breakpoint']}\t"
                     f"{c['NONCOLLINEAR']}\t"
                     f"{c['fission_or_fusion']}\t"
                     f"{c['translocation']}\n")
    print(f"[STEP_BP2] Per-pair summary -> {summary_path}", file=sys.stderr)

    # ------------------------------------------------------------------------
    # Quick QC flag: which tier-A pairs produced suspiciously many events?
    # (Real biology: <50 inter-haplotype inversions per 1 Gb in vertebrates;
    #  >200 events from a tier-A pair = probable contig-order artifact)
    # ------------------------------------------------------------------------
    flag_path = out_dir / "qc_flags.tsv"
    with open(flag_path, "w") as fh:
        fh.write("pair_id\tflag\treason\n")
        for pid, c in per_pair_counts.items():
            if c["query_qc"] == "A" and c["target_qc"] == "A":
                if c["n_events_total"] > 200:
                    fh.write(f"{pid}\tHIGH_EVENT_COUNT\t"
                             f"{c['n_events_total']} events from A/A pair — "
                             f"check for assembly contig-order issues\n")
                if c["n_paf_records"] < 100:
                    fh.write(f"{pid}\tLOW_PAF_RECORDS\t"
                             f"only {c['n_paf_records']} PAF rows — alignment failed?\n")
    print(f"[STEP_BP2] QC flags -> {flag_path}", file=sys.stderr)


# ----------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--paf-dir", required=True, type=Path)
    ap.add_argument("--out",     required=True, type=Path)
    ap.add_argument("--min-block-bp", type=int, default=50_000,
                    help="Minimum aligned block length to consider (default 50 kb)")
    ap.add_argument("--max-gap-bp",   type=int, default=2_000_000,
                    help="Max query-side gap between adjacent blocks to call a breakpoint (default 2 Mb)")
    ap.add_argument("--min-mapq",     type=int, default=1,
                    help="Minimum PAF MAPQ to keep a block. Default 1 because "
                         "this pipeline is fed by wfmash, whose approx-mapping "
                         "MAPQ is typically 1-5 (NOT 40 like minimap2). Using "
                         "the old default of 5 silently discards nearly all "
                         "wfmash blocks and yields 0 breakpoints. Pass "
                         "--min-mapq 40 only for minimap2-produced PAFs.")
    args = ap.parse_args()

    process_directory(
        args.paf_dir, args.out,
        min_block_bp=args.min_block_bp,
        max_gap_bp=args.max_gap_bp,
        min_mapq=args.min_mapq,
    )


if __name__ == "__main__":
    main()
