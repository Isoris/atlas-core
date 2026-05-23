#!/usr/bin/env python3
"""anchor_density.py -- report orthologs-per-chromosome for a focal species in a
wide ortholog table, so you KNOW if it's dense enough (not guess).
Usage: python anchor_density.py --table orthologs_18sp.tsv --focal-species fClaHyb_Gar
"""
import argparse, csv, re, sys
from collections import Counter
ap=argparse.ArgumentParser()
ap.add_argument("--table",required=True); ap.add_argument("--focal-species",required=True)
a=ap.parse_args()
rows=list(csv.DictReader(open(a.table,errors="ignore"),delimiter="\t"))
cols=rows[0].keys() if rows else []
# find spN for focal
focal=None
for c in [c for c in cols if re.fullmatch(r"sp\d+\.ID",c)]:
    for r in rows:
        m=re.match(r'\d+at\d+_(.+)',r.get(c,""))
        if m and m.group(1)==a.focal_species: focal=c.split(".")[0]; break
    if focal: break
if not focal: sys.exit(f"{a.focal_species} not found")
cnt=Counter(r.get(f"{focal}.Chr","") for r in rows if r.get(f"{focal}.Chr",""))
tot=sum(cnt.values()); nchr=len(cnt)
print(f"focal {a.focal_species} ({focal}): {tot} anchors over {nchr} chroms, mean {tot/nchr:.1f}/chrom")
print("per-chrom (sorted):")
for c,n in sorted(cnt.items(),key=lambda x:-x[1]):
    bar="#"*min(n,40)
    print(f"  chr {c:>4}: {n:4} {bar}")
lo=[c for c,n in cnt.items() if n<10]
if lo: print(f"\n  WARNING: {len(lo)} chroms with <10 anchors (sparse): {sorted(lo)}")
print(f"\n  rule of thumb: >=20/chrom good for large events; <10 too sparse to localize.")
