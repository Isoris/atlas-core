#!/usr/bin/env python3
"""
wide_orthologs_to_breakpoints.py -- multi-species breakpoints from macrosyntR's
WIDE ortholog table (my_orthologs_with_18_sp: 983 orthologs x 18 species).

Each row = one ortholog with spN.Chr / spN.Start / spN.End / spN.Index for every
species. We pick a FOCAL species (e.g. fClaHyb_Gar), order orthologs along each
focal chromosome by focal Start, and between consecutive orthologs ask, FOR EACH
other species, whether the comparison chromosome changed (interchrom) -- a vote.
A breakpoint with many species voting = strong multi-species consensus, in ONE pass.

Output (matches build_evidence_matrix.py):
  ref_chrom  break_mb  class  query_species  confidence  detail
  - one row per (focal edge, supporting species) with class=interchrom
  - PLUS a consensus detail showing how many species support that edge

Discover the species<->spN map from the *.ID columns automatically.
"""
import argparse, csv, sys, re
from collections import defaultdict

def load_table(path):
    with open(path, errors="ignore") as fh:
        rdr=csv.DictReader(fh, delimiter="\t")
        rows=list(rdr); cols=rdr.fieldnames or []
    return rows, cols

def species_map(rows, cols):
    """spN -> species label, from the spN.ID values like '100034at7898_C_gariepinus'."""
    m={}
    idcols=[c for c in cols if re.fullmatch(r"sp\d+\.ID", c)]
    for c in idcols:
        spn=c.split(".")[0]
        for r in rows:
            v=r.get(c,"")
            mm=re.match(r'\d+at\d+_(.+)', v)
            if mm: m[spn]=mm.group(1); break
    return m

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--table",required=True,help="wide ortholog TSV (my_orthologs_with_18_sp)")
    ap.add_argument("--focal-species",default="fClaHyb_Gar")
    ap.add_argument("--out")
    ap.add_argument("--list-species",action="store_true",help="just print the spN->species map and exit")
    args=ap.parse_args()

    rows, cols = load_table(args.table)
    smap = species_map(rows, cols)
    inv = {v:k for k,v in smap.items()}
    if args.list_species:
        for spn in sorted(smap, key=lambda x:int(x[2:])):
            print(f"  {spn} = {smap[spn]}")
        return
    if not args.out:
        sys.exit("--out required unless --list-species")
    if args.focal_species not in inv:
        sys.exit(f"focal {args.focal_species} not found. Species: {sorted(smap.values())}")
    focal=inv[args.focal_species]
    others=[s for s in smap if s!=focal]
    print(f"[wide] focal={args.focal_species} ({focal}); {len(others)} comparison species; {len(rows)} orthologs",file=sys.stderr)

    def getf(r,spn,field):
        v=r.get(f"{spn}.{field}","")
        return v
    # order orthologs along focal chromosomes
    by=defaultdict(list)
    for r in rows:
        fchr=getf(r,focal,"Chr"); fstart=getf(r,focal,"Start")
        if not fchr or not fstart: continue
        try: fstart=int(float(fstart))
        except ValueError: continue
        by[fchr].append((fstart,r))

    bps=[]; consensus=defaultdict(lambda: defaultdict(set))  # (fchr,edge)-> 'count' species
    for fchr,lst in by.items():
        lst.sort(key=lambda x:x[0])
        for (s_a,ra),(s_b,rb) in zip(lst,lst[1:]):
            edge_mb=round((s_a+s_b)/2/1e6,3)
            for spn in others:
                ca=getf(ra,spn,"Chr"); cb=getf(rb,spn,"Chr")
                if ca and cb and ca!=cb:
                    sp=smap[spn]
                    bps.append((fchr,edge_mb,"interchrom",sp,"high",
                                f"focal {args.focal_species}{fchr}: {sp} {ca}->{cb}"))
                    consensus[(fchr,edge_mb)]["sp"].add(sp)

    # write per-(edge,species) rows + a consensus column
    with open(args.out,"w",newline="") as fh:
        w=csv.writer(fh,delimiter="\t")
        w.writerow(["ref_chrom","break_mb","class","query_species","confidence","detail","n_species_consensus"])
        for fchr,edge_mb,cls,sp,conf,detail in sorted(bps):
            n=len(consensus[(fchr,edge_mb)]["sp"])
            w.writerow([fchr,edge_mb,cls,sp,conf,detail,n])
    nedges=len(consensus)
    multi=sum(1 for k in consensus if len(consensus[k]["sp"])>=3)
    print(f"[wide] {len(bps)} (edge,species) breakpoints over {nedges} distinct edges",file=sys.stderr)
    print(f"[wide] {multi} edges with >=3 species consensus -> {args.out}",file=sys.stderr)

if __name__=="__main__": main()
