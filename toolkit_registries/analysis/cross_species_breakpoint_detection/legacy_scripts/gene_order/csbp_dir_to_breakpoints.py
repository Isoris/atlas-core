#!/usr/bin/env python3
"""
csbp_dir_to_breakpoints.py -- read a DIRECTORY of cs_breakpoints JSONs (one per
species-pair, produced by STEP_CS01_extract_breakpoints.py on each tiered wfmash
PAF) and emit ONE long breakpoints table for cluster_breakpoints.py.

Each JSON's 'breakpoints' list is read (the real STEP_CS01 calls, with
event_type_refined). The comparison species is taken from species_target.
Output rows tagged with query_species so cluster_breakpoints can see WHICH
species supports each focal breakpoint -- same per-species detail as the
gene-order pairwise catalog, but from SEQUENCE alignment.

Output: ref_chrom break_mb class query_species confidence detail
"""
import argparse, json, csv, sys, re, os, glob

def norm(c):
    c=str(c); m=re.search(r'LG[_]?(\d+)', c)
    if m: return str(int(m.group(1)))
    m=re.search(r'(\d+)\s*$', c.replace("_"," ").strip())
    return str(int(m.group(1))) if m else c

def class_of(et):
    et=(et or "").lower()
    if "inv" in et: return "orientation"
    if "fission" in et or "fusion" in et: return "interchrom"
    if "transloc" in et: return "interchrom"
    return et or "breakpoint"

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--json-dir",required=True,help="dir of *.json from STEP_CS01")
    ap.add_argument("--glob",default="*.json")
    ap.add_argument("--out",required=True)
    args=ap.parse_args()
    files=sorted(glob.glob(os.path.join(args.json_dir,args.glob)))
    if not files: sys.exit(f"no JSONs matching {args.glob} in {args.json_dir}")
    rows=[]; nper={}
    for fp in files:
        try: data=json.load(open(fp))
        except Exception as e: print(f"  skip {fp}: {e}",file=sys.stderr); continue
        sp=data.get("species_target",{}).get("name","") or os.path.basename(fp).split("__vs__")[-1].replace(".json","")
        sp=sp.replace("Clarias ","C_").replace(" ","_")
        n=0
        for b in data.get("breakpoints",[]):
            chrom=norm(b.get("gar_chr","")); mb=b.get("gar_pos_mb")
            if mb is None and "gar_pos_start" in b: mb=b["gar_pos_start"]/1e6
            if chrom=="" or mb is None: continue
            et=b.get("event_type_refined", b.get("event_type",""))
            rows.append((chrom,round(float(mb),3),class_of(et),sp,"high",
                         f"{b.get('id','')} {et}"))
            n+=1
        nper[os.path.basename(fp)]=n
    with open(args.out,"w",newline="") as fh:
        w=csv.writer(fh,delimiter="\t")
        w.writerow(["ref_chrom","break_mb","class","query_species","confidence","detail"])
        w.writerows(sorted(rows))
    print(f"[csbp-dir] {len(files)} JSONs, {len(rows)} breakpoints -> {args.out}",file=sys.stderr)
    for f,n in sorted(nper.items()): print(f"    {f}: {n}",file=sys.stderr)

if __name__=="__main__": main()
