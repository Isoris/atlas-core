#!/usr/bin/env python3
"""
pairwise_all_species.py -- focal-vs-EACH-species breakpoints from the wide
ortholog table, one comparison at a time, then summarized per focal position.

For the focal (e.g. fClaHyb_Gar), walk each focal chromosome by position; for
EACH comparison species independently, flag where consecutive orthologs switch
that species' chromosome (interchrom). Output keeps per-species detail AND a
consensus tally, so you see exactly which species support each focal breakpoint.

This maximizes breakpoint observations to bound haploblock edges: a focal edge
supported by many species = strong recurrent boundary.

Output (long format, one row per focal-edge x supporting-species):
  ref_chrom  break_mb  query_species  comp_chrom_left  comp_chrom_right  n_species_at_edge
Plus a wide summary: ref_chrom break_mb n_species species_list

Usage:
  python pairwise_all_species.py --table orthologs_18sp.tsv \
     --focal-species fClaHyb_Gar --out-long pairwise_long.tsv --out-summary pairwise_summary.tsv \
     --edge-merge-kb 200
"""
import argparse, csv, sys, re
from collections import defaultdict

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--table",required=True)
    ap.add_argument("--focal-species",default="fClaHyb_Gar")
    ap.add_argument("--out-long",required=True)
    ap.add_argument("--out-summary",required=True)
    ap.add_argument("--edge-merge-kb",type=float,default=200.0,
                    help="merge focal edges within this distance into one consensus edge")
    args=ap.parse_args()

    rows=list(csv.DictReader(open(args.table,errors="ignore"),delimiter="\t"))
    cols=rows[0].keys() if rows else []
    # species<->spN
    smap={}
    for c in [c for c in cols if re.fullmatch(r"sp\d+\.ID",c)]:
        spn=c.split(".")[0]
        for r in rows:
            m=re.match(r'\d+at\d+_(.+)',r.get(c,""))
            if m: smap[spn]=m.group(1); break
    inv={v:k for k,v in smap.items()}
    if args.focal_species not in inv: sys.exit(f"focal not found; have {sorted(smap.values())}")
    focal=inv[args.focal_species]; others=[s for s in smap if s!=focal]
    print(f"[pairwise] focal={args.focal_species}; {len(others)} comparison species; {len(rows)} orthologs",file=sys.stderr)

    def g(r,spn,f): return r.get(f"{spn}.{f}","")
    by=defaultdict(list)
    for r in rows:
        fchr=g(r,focal,"Chr"); fs=g(r,focal,"Start")
        if not fchr or not fs: continue
        try: fs=int(float(fs))
        except: continue
        by[fchr].append((fs,r))

    long_rows=[]
    raw_edges=defaultdict(lambda: defaultdict(set))  # (fchr, edge_mb) -> 'sp' -> set
    for fchr,lst in by.items():
        lst.sort(key=lambda x:x[0])
        for (sa,ra),(sb,rb) in zip(lst,lst[1:]):
            edge_mb=round((sa+sb)/2/1e6,3)
            for spn in others:
                ca=g(ra,spn,"Chr"); cb=g(rb,spn,"Chr")
                if ca and cb and ca!=cb:
                    sp=smap[spn]
                    long_rows.append({"ref_chrom":fchr,"break_mb":edge_mb,"query_species":sp,
                                      "comp_chrom_left":ca,"comp_chrom_right":cb})
                    raw_edges[(fchr,edge_mb)]["sp"].add(sp)

    # merge nearby focal edges into consensus positions
    mtol=args.edge_merge_kb/1000.0
    by_chr=defaultdict(list)
    for (fchr,emb),d in raw_edges.items():
        by_chr[fchr].append((emb,d["sp"]))
    summary=[]
    for fchr,edges in by_chr.items():
        edges.sort()
        cur_mbs=[edges[0][0]]; cur_sp=set(edges[0][1])
        def flush(mbs,sp):
            summary.append({"ref_chrom":fchr,"break_mb":round(sum(mbs)/len(mbs),3),
                            "n_species":len(sp),"span_kb":round((max(mbs)-min(mbs))*1000,1),
                            "species_list":",".join(sorted(sp))})
        for emb,sp in edges[1:]:
            if emb-cur_mbs[-1]<=mtol:
                cur_mbs.append(emb); cur_sp|=sp
            else:
                flush(cur_mbs,cur_sp); cur_mbs=[emb]; cur_sp=set(sp)
        flush(cur_mbs,cur_sp)

    with open(args.out_long,"w",newline="") as fh:
        w=csv.DictWriter(fh,fieldnames=["ref_chrom","break_mb","query_species","comp_chrom_left","comp_chrom_right"],delimiter="\t")
        w.writeheader(); w.writerows(long_rows)
    summary.sort(key=lambda r:(-r["n_species"],r["ref_chrom"],r["break_mb"]))
    with open(args.out_summary,"w",newline="") as fh:
        w=csv.DictWriter(fh,fieldnames=["ref_chrom","break_mb","n_species","span_kb","species_list"],delimiter="\t")
        w.writeheader(); w.writerows(summary)
    multi=sum(1 for s in summary if s["n_species"]>=3)
    print(f"[pairwise] {len(long_rows)} focal-edge x species obs; {len(summary)} consensus edges; "
          f"{multi} with >=3 species -> {args.out_summary}",file=sys.stderr)

if __name__=="__main__": main()
