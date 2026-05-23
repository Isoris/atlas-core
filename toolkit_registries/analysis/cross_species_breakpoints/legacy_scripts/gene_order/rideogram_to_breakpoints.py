#!/usr/bin/env python3
"""
rideogram_to_breakpoints.py -- breakpoints from RIdeogram dual-synteny files.

Input format (TAB), per-ortholog anchor pairs:
    Chr_1/Species_1  Start_1  End_1  Chr_2/Species_2  Start_2  End_2  fill  [type]
Each row = one ortholog's position in genome1 (focal) and genome2 (comparison).
Chromosomes are BARE NUMBERS in each genome's own numbering (Gar 22 != Mac 22).

We report breakpoints on the FOCAL (Chr_1 / genome1) frame: walk anchors along
each focal chromosome in coordinate order; a breakpoint is where consecutive
anchors switch which genome2 chromosome they map to (interchrom) or reverse
direction in genome2 (orientation; weak -- these are gene midpoints, no strand).

Output: ref_chrom  break_mb  class  query_species  detail
matching build_evidence_matrix.py's expected columns.

Usage:
  python rideogram_to_breakpoints.py --synteny synteny_hybrid_haps.txt \
     --focal-name HybGar --query-name HybMac --out synteny_breakpoints.tsv
  (focal/query names are just labels for the output)
"""
import argparse, csv, sys
from collections import defaultdict

def load(path):
    rows=[]
    with open(path, errors="ignore") as fh:
        rdr=csv.reader(fh, delimiter="\t")
        header=next(rdr,None)
        for f in rdr:
            if len(f)<6: continue
            try:
                c1=f[0]; s1=int(float(f[1])); e1=int(float(f[2]))
                c2=f[3]; s2=int(float(f[4])); e2=int(float(f[5]))
            except ValueError:
                continue
            rows.append((c1,(s1+e1)//2,c2,(s2+e2)//2))
    return rows

def call(rows, focal, query):
    bps=[]
    by=defaultdict(list)
    for c1,m1,c2,m2 in rows:
        by[c1].append((m1,c2,m2))
    for c1, anchors in by.items():
        anchors.sort()  # by focal midpoint
        for (m1a,c2a,m2a),(m1b,c2b,m2b) in zip(anchors,anchors[1:]):
            edge_mb=round((m1a+m1b)/2/1e6,3)
            if c2a!=c2b:
                bps.append((c1,edge_mb,"interchrom",query,"high",
                            f"{focal}{c1}: maps {query}{c2a}->{query}{c2b}"))
            else:
                # same query chrom: check direction reversal in genome2.
                # NO STRAND -> single-anchor reversal is WEAK (local jitter, not
                # necessarily an inversion). Tagged low; confirm vs wfmash BPATLAS.
                if (m2b-m2a) < 0:
                    bps.append((c1,edge_mb,"orientation",query,"low",
                                f"{focal}{c1} vs {query}{c2a}: order reversal (no-strand, weak)"))
    return bps

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--synteny",required=True)
    ap.add_argument("--focal-name",default="focal")
    ap.add_argument("--query-name",default="query")
    ap.add_argument("--out",required=True)
    ap.add_argument("--collapse-orientation-runs",action="store_true",
                    help="merge consecutive orientation flips on same chrom/query into one (reduces noise)")
    args=ap.parse_args()
    rows=load(args.synteny)
    print(f"[rideo] {len(rows)} anchor pairs",file=sys.stderr)
    bps=call(rows,args.focal_name,args.query_name)

    if args.collapse_orientation_runs:
        # keep interchrom as-is; collapse adjacent orientation bps within 1 Mb
        collapsed=[]; last=None
        for b in sorted(bps):
            if b[2]=="orientation" and last and last[0]==b[0] and last[2]=="orientation" \
               and abs(b[1]-last[1])<1.0:
                continue
            collapsed.append(b); last=b
        bps=collapsed

    with open(args.out,"w",newline="") as fh:
        w=csv.writer(fh,delimiter="\t")
        w.writerow(["ref_chrom","break_mb","class","query_species","confidence","detail"])
        w.writerows(sorted(bps))
    from collections import Counter
    cc=Counter(b[2] for b in bps)
    print(f"[rideo] {len(bps)} breakpoints (interchrom={cc['interchrom']}, "
          f"orientation={cc['orientation']}) -> {args.out}",file=sys.stderr)

if __name__=="__main__": main()
