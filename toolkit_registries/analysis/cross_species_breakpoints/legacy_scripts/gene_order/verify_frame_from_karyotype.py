#!/usr/bin/env python3
"""verify_frame_from_karyotype.py -- frame check using the RIdeogram karyotype
file instead of a genome .fa (which you can't download). The karyotype file IS
the chromosome-length ground truth.

Checks that every focal chromosome+coordinate in the synteny file fits within
the chromosome lengths declared in the karyotype file. Overrun => synteny was
built on a different assembly than the karyotype (frame mismatch).

Usage:
  python verify_frame_from_karyotype.py --synteny synteny_hybrid_haps.txt \
     --karyotype karyotype_hybrid_haps.txt --focal-species HybGar
"""
import argparse, csv, sys
from collections import defaultdict

def load_karyotype(path, focal_species=None):
    lens={}
    with open(path,errors="ignore") as fh:
        rdr=csv.DictReader(fh,delimiter="\t")
        for r in rdr:
            sp=r.get("species","")
            if focal_species and sp!=focal_species: continue
            try: lens[r["Chr"]]=int(float(r["End"]))
            except (KeyError,ValueError): continue
    return lens

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--synteny",required=True)
    ap.add_argument("--karyotype",required=True)
    ap.add_argument("--focal-species",default=None,
                    help="species label in karyotype for the FOCAL (Chr_1) genome, e.g. HybGar")
    args=ap.parse_args()
    lens=load_karyotype(args.karyotype,args.focal_species)
    if not lens:
        sys.exit(f"no chrom lengths loaded (species filter={args.focal_species}). "
                 f"Check the 'species' column values in {args.karyotype}.")
    print(f"[frame] {len(lens)} focal chromosomes in karyotype",file=sys.stderr)
    overrun=defaultdict(int); missing=defaultdict(int); maxend=defaultdict(int); n=0
    with open(args.synteny,errors="ignore") as fh:
        rdr=csv.reader(fh,delimiter="\t"); next(rdr,None)
        for f in rdr:
            if len(f)<3: continue
            try:
                c1=f[0]; e1=int(float(f[2]))
            except ValueError: continue
            n+=1
            if c1 not in lens: missing[c1]+=1
            elif e1>lens[c1]:
                overrun[c1]+=1; maxend[c1]=max(maxend[c1],e1)
    print(f"[frame] checked {n} focal anchors")
    if missing:
        print(f"[X] {len(missing)} focal chrom(s) NOT in karyotype: {dict(list(missing.items())[:8])}")
    else:
        print("[OK] all focal chroms present in karyotype")
    if overrun:
        print(f"[X] {len(overrun)} chrom(s) have anchors PAST karyotype length:")
        for c in list(overrun)[:8]:
            print(f"      chr{c}: {overrun[c]} anchors, max end {maxend[c]} > len {lens[c]}")
    else:
        print("[OK] no anchor exceeds its chromosome length")
    print("\n==== VERDICT ====")
    if not missing and not overrun:
        print("SAME FRAME -- synteny coords fit the karyotype. Good to use as-is.")
    else:
        print("MISMATCH -- synteny was built on a different assembly than this karyotype.")

if __name__=="__main__": main()
