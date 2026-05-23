#!/usr/bin/env python3
"""
cluster_breakpoints.py -- merge breakpoints across methods by TOLERANCE clustering,
not fixed bins. Honest about resolution: reports the actual spread of method
positions within each cluster, so you SEE how far apart the methods are.

A cluster = breakpoints on the same chrom within --tol-kb of each other (single-
linkage). Default 500 kb (tight). Each cluster reports which methods contributed,
the min/max/spread of their positions, and -- crucially -- a cross_method flag
that is TRUE only when an INDEPENDENT method family agrees.

Method families (independence-aware):
  gene_order : synteny18, synteny5, genejson   (all BUSCO gene-order; correlated)
  sequence   : wfmash                          (sequence alignment; independent)
  karyotype  : mashmap                         (if present)
cross_method = TRUE iff >=2 DIFFERENT families present in the cluster.

Sources passed as NAME:PATH:FAMILY  (FAMILY optional; inferred from NAME if omitted).

Output:
  cluster_id ref_chrom centroid_mb span_kb n_methods methods families
  n_families cross_method  pos_by_method  event_classes
"""
import argparse, csv, sys, re
from collections import defaultdict

FAMILY={"synteny18":"gene_order","synteny5":"gene_order","genejson":"gene_order",
        "wfmash":"sequence","mashmap":"karyotype"}

def norm_chrom(c):
    if c is None: return None
    c=str(c)
    m=re.search(r'LG[_]?(\d+)', c)
    if m: return str(int(m.group(1)))
    m=re.search(r'(\d+)\s*$', c.replace("_"," ").strip())
    return str(int(m.group(1))) if m else c

def read_source(path, name):
    rows=[]
    with open(path,errors="ignore") as fh:
        rdr=csv.DictReader(fh,delimiter="\t"); cols=rdr.fieldnames or []
        def pick(*c):
            for x in c:
                if x in cols: return x
            return None
        cc=pick("ref_chrom","chrom","Chr","query_chrom","seqnames","qchrom")
        cm=pick("break_mb","centroid_mb","pos_mb","Mb")
        cpos=pick("Pos","pos","position","query_pos","qpos")
        ccls=pick("class","event","bp_class","event_class","event_type_refined")
        ckind=pick("pair_kind","comparison")
        for r in rdr:
            chrom=norm_chrom(r.get(cc)) if cc else None
            if cm and r.get(cm):
                try: mb=float(r[cm])
                except: continue
            elif cpos and r.get(cpos):
                try: mb=float(r[cpos])/1e6
                except: continue
            else: continue
            cls=(r.get(ccls,"") if ccls else "").strip()
            if cls.upper()=="NONCOLLINEAR": continue
            kind=(r.get(ckind,"") if ckind else "")
            if chrom is None: continue
            rows.append((chrom,mb,cls,kind))
    return rows

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--source",action="append",required=True,help="NAME:PATH[:FAMILY]")
    ap.add_argument("--tol-kb",type=float,default=500.0)
    ap.add_argument("--split-wfmash",action="store_true",
                    help="split wfmash into within-Cgar vs cross-species columns")
    ap.add_argument("--out",required=True)
    args=ap.parse_args()
    tol=args.tol_kb/1000.0

    fam_of={}; allbp=[]
    for s in args.source:
        parts=s.split(":")
        name,path=parts[0],parts[1]
        fam=parts[2] if len(parts)>2 else FAMILY.get(name,name)
        rows=read_source(path,name)
        for chrom,mb,cls,kind in rows:
            mname,mfam=name,fam
            # split wfmash into within-Cgar vs cross-species as separate columns
            if args.split_wfmash and name=="wfmash":
                if kind and "within" in kind.lower():
                    mname,mfam="wfmash_withinCgar","sequence"   # SAME method family as cross
                else:
                    mname,mfam="wfmash_cross","sequence"
            allbp.append({"chrom":chrom,"mb":mb,"method":mname,"family":mfam,"class":cls,"kind":kind})
        print(f"  {name:12} {len(rows)} breakpoints",file=sys.stderr)

    # single-linkage cluster within tol, per chrom
    byc=defaultdict(list)
    for b in allbp: byc[b["chrom"]].append(b)
    clusters=[]
    for chrom,bl in byc.items():
        bl.sort(key=lambda x:x["mb"])
        cur=[bl[0]]
        for b in bl[1:]:
            if b["mb"]-cur[-1]["mb"]<=tol:
                cur.append(b)
            else:
                clusters.append((chrom,cur)); cur=[b]
        clusters.append((chrom,cur))

    out=[]
    for chrom,members in clusters:
        mbs=[m["mb"] for m in members]
        methods=sorted(set(m["method"] for m in members))
        fams=sorted(set(m["family"] for m in members))
        pos_by={}
        for m in members:
            pos_by.setdefault(m["method"],[]).append(round(m["mb"],3))
        out.append({
            "ref_chrom":chrom,
            "centroid_mb":round(sum(mbs)/len(mbs),3),
            "span_kb":round((max(mbs)-min(mbs))*1000,1),
            "n_methods":len(methods),
            "methods":",".join(methods),
            "families":",".join(fams),
            "n_families":len(fams),
            "cross_method":"yes" if len(fams)>=2 else "no",
            "pos_by_method":"; ".join(f"{k}={'/'.join(map(str,v))}" for k,v in sorted(pos_by.items())),
            "event_classes":",".join(sorted(set(m["class"] for m in members if m["class"]))),
        })
    # rank: cross_method first, then more families, then more methods
    out.sort(key=lambda r:(r["cross_method"]!="yes", -r["n_families"], -r["n_methods"],
                           r["ref_chrom"], r["centroid_mb"]))
    for i,r in enumerate(out,1): r["cluster_id"]=f"CL{i:04d}"
    cols=["cluster_id","ref_chrom","centroid_mb","span_kb","n_methods","methods",
          "families","n_families","cross_method","pos_by_method","event_classes"]
    with open(args.out,"w",newline="") as fh:
        w=csv.DictWriter(fh,fieldnames=cols,delimiter="\t"); w.writeheader(); w.writerows(out)
    xm=sum(1 for r in out if r["cross_method"]=="yes")
    print(f"[cluster] tol={args.tol_kb}kb: {len(out)} clusters, {xm} CROSS-METHOD "
          f"(independent families agree) -> {args.out}",file=sys.stderr)

if __name__=="__main__": main()
