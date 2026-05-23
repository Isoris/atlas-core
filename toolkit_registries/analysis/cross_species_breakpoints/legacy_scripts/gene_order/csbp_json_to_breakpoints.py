#!/usr/bin/env python3
"""
csbp_json_to_breakpoints.py -- breakpoints from cs_breakpoints_v1.json (v2 schema).

The JSON has TWO useful lists:
  - 'breakpoints'    : ALREADY-CALLED breakpoints (id, event_type, gar_chr,
                       gar_pos_mb, prev_block, next_block) -- the cleanest source.
  - 'synteny_blocks' : raw blocks (gar_chr/gar_start/gar_end/mac_chr/strand) --
                       fallback if 'breakpoints' is empty.

Default: read the pre-called 'breakpoints' list (preferred). Use --from-blocks
to recompute from synteny_blocks instead.

Output (matches build_evidence_matrix.py):
  ref_chrom  break_mb  class  query_species  confidence  detail
"""
import argparse, json, csv, sys, re
from collections import defaultdict

def norm(c):
    m=re.search(r'(\d+)\s*$', str(c)); return m.group(1) if m else str(c)

def from_called(data, query):
    bps=[]
    for b in data.get("breakpoints", []):
        chrom=norm(b.get("gar_chr",""))
        mb=b.get("gar_pos_mb")
        if mb is None and "gar_pos_start" in b:
            mb=b["gar_pos_start"]/1e6
        if chrom=="" or mb is None: continue
        et=b.get("event_type","")
        cls = "interchrom" if "fission" in et or "fusion" in et else \
              ("orientation" if "inversion" in et else et or "breakpoint")
        # detail from prev/next block mac chroms if present
        pv=b.get("prev_block",{}); nx=b.get("next_block",{})
        det=f"{b.get('id','')} {et}"
        if isinstance(pv,dict) and isinstance(nx,dict) and pv.get("mac_chr") and nx.get("mac_chr"):
            det+=f" ({pv['mac_chr']}->{nx['mac_chr']})"
        bps.append((chrom,round(float(mb),3),cls,query,"high",det))
    return bps

def from_blocks(data, query):
    blocks=data.get("synteny_blocks",[])
    by=defaultdict(list)
    for b in blocks: by[b["gar_chr"]].append(b)
    bps=[]
    for gchr,bl in by.items():
        bl.sort(key=lambda x:x["gar_start"]); c=norm(gchr)
        for a,d in zip(bl,bl[1:]):
            edge_mb=round((a["gar_end"]+d["gar_start"])/2/1e6,3)
            if a["mac_chr"]!=d["mac_chr"]:
                bps.append((c,edge_mb,"interchrom",query,"high",
                            f"{gchr}: {a['mac_chr']}->{d['mac_chr']}"))
            elif a["strand"]!=d["strand"]:
                bps.append((c,edge_mb,"orientation",query,"high",
                            f"{gchr} vs {a['mac_chr']}: strand {a['strand']}->{d['strand']}"))
    return bps

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--json",required=True)
    ap.add_argument("--query-name",default="C_mac")
    ap.add_argument("--from-blocks",action="store_true",
                    help="recompute from synteny_blocks instead of reading called breakpoints")
    ap.add_argument("--out",required=True)
    args=ap.parse_args()
    data=json.load(open(args.json))
    nb=len(data.get("breakpoints",[])); nblk=len(data.get("synteny_blocks",[]))
    print(f"[csbp-json] {nb} called breakpoints, {nblk} synteny blocks",file=sys.stderr)
    bps = from_blocks(data,args.query_name) if args.from_blocks else from_called(data,args.query_name)
    if not bps and not args.from_blocks:
        print("[csbp-json] no called breakpoints; falling back to blocks",file=sys.stderr)
        bps=from_blocks(data,args.query_name)
    with open(args.out,"w",newline="") as fh:
        w=csv.writer(fh,delimiter="\t")
        w.writerow(["ref_chrom","break_mb","class","query_species","confidence","detail"])
        w.writerows(sorted(bps))
    from collections import Counter
    cc=Counter(b[2] for b in bps)
    print(f"[csbp-json] {len(bps)} breakpoints {dict(cc)} -> {args.out}",file=sys.stderr)

if __name__=="__main__": main()
