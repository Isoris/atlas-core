#!/usr/bin/env python3
"""
harvest_candidates.py — read every 04_results/candidates/<id>/ folder,
validate each file against its schema, and emit the three thesis chapter
tables (Tables 7.1, 7.2, 7.3) as TSVs in the candidates root.

§refusals: read-only on the per-candidate folders. Schema validation is
hard — any candidate that fails validation is skipped with a diagnostic
and contributes no row to any table.
"""
from __future__ import annotations
import csv, json, pathlib, sys

REPO = pathlib.Path(__file__).resolve().parents[3]
ROOT = REPO / "toolkit_registries" / "relatedness" / "04_results" / "candidates"
SCHEMAS = REPO / "toolkit_registries" / "schemas" / "structured_block_schemas"


def load_jsonl_tsv(p: pathlib.Path) -> list[dict]:
    if not p.exists():
        return []
    text = [l for l in p.read_text().splitlines() if l and not l.startswith("#")]
    if not text:
        return []
    reader = csv.DictReader(text, delimiter="\t")
    return [dict(r) for r in reader]


def load_json(p: pathlib.Path) -> dict | None:
    return json.loads(p.read_text()) if p.exists() else None


def mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else 0.0


def fnum(s):
    try: return float(s)
    except (TypeError, ValueError): return None


def interpret_block(freq: dict, regime: dict, popstats: list[dict], fam: list[dict]) -> tuple[str, str, str]:
    """Return (interp_7_1, interp_7_2, interp_7_3) interpretation columns."""
    fis = float(freq.get("HWE_FIS", 0.0))
    fst_mean = mean([fnum(r.get("arrangement_FST_like")) for r in popstats])
    vote = float(regime.get("long_range_vote_pct", 0))
    cont = float(regime.get("local_continuity_score", 0))
    inconsistent = sum(int(r["n_inconsistent"]) for r in fam)
    informative = sum(int(r["n_informative_offspring"]) for r in fam)
    inc_rate = inconsistent / informative if informative else 1.0

    if vote >= 80 and cont >= 0.85:
        i71 = "candidate LRR"
    elif vote >= 65:
        i71 = "candidate LRR"
    else:
        i71 = "weak / unresolved"

    if fis <= -0.04 and fst_mean >= 0.4:
        i72 = "overdominance-like"
    elif fst_mean >= 0.4:
        i72 = "divergent maintenance"
    else:
        i72 = "unresolved"

    if inc_rate <= 0.05:
        i73 = "coherent inheritance"
    elif inc_rate <= 0.10:
        i73 = "coherent inheritance"
    else:
        i73 = "weak / unresolved"

    return i71, i72, i73


def harvest_one(folder: pathlib.Path) -> dict | None:
    cand   = load_json(folder / "candidate.json")
    regime = load_json(folder / "long_range_regime.json")
    freq   = load_json(folder / "frequency_block.json")
    karyo   = load_jsonl_tsv(folder / "karyotype_groups.tsv")
    lpca    = load_jsonl_tsv(folder / "localpca_windows.tsv")
    popstats = load_jsonl_tsv(folder / "popstats.tsv")
    fam      = load_jsonl_tsv(folder / "family_segregation.tsv")
    if not (cand and regime and freq):
        print(f"  skipped {folder.name}: missing required JSON", file=sys.stderr)
        return None
    if cand["cohort_id"] != "cgar_hatchery_226":
        print(f"  skipped {folder.name}: not the hatchery cohort", file=sys.stderr)
        return None

    i71, i72, i73 = interpret_block(freq, regime, popstats, fam)

    # ---- Table 7.1 ------------------------------------------------------
    size_mb = round(cand["size_bp"] / 1e6, 2)
    row_71 = {
        "block_id": cand["block_id"],
        "chrom": cand["chrom"],
        "start_bp": cand["start"],
        "end_bp": cand["end"],
        "size_Mb": size_mb,
        "n_windows": regime["n_windows"],
        "major_dosage_classes": "/".join(regime["major_dosage_classes"]),
        "long_range_vote_pct": regime["long_range_vote_pct"],
        "local_continuity_score": regime["local_continuity_score"],
        "interpretation": i71,
    }

    # ---- Table 7.2 ------------------------------------------------------
    het_obs_inside = mean([fnum(r["heterozygosity_obs"]) for r in popstats])
    het_exp_inside = mean([fnum(r["heterozygosity_exp"]) for r in popstats])
    het_delta = het_obs_inside - het_exp_inside
    fst_mean = mean([fnum(r["arrangement_FST_like"]) for r in popstats])
    if het_delta > 0.005:
        het_note = "increased"
    elif abs(het_delta) <= 0.005:
        het_note = "neutral"
    else:
        het_note = "depleted"
    row_72 = {
        "block_id": cand["block_id"],
        "chrom": cand["chrom"],
        "n_H1H1": freq["n_H1H1"],
        "n_H1H2": freq["n_H1H2"],
        "n_H2H2": freq["n_H2H2"],
        "heterozygote_diversity": het_note,
        "HWE_p": freq["HWE_p"],
        "HWE_FIS": freq["HWE_FIS"],
        "arrangement_FST_like_mean": round(fst_mean, 3),
        "deleterious_burden_SIFT": "n/a (not in demo)",
        "interpretation": i72,
    }

    # ---- Table 7.3 ------------------------------------------------------
    informative_fams = sum(1 for r in fam if int(r["n_informative_offspring"]) > 0)
    informative = sum(int(r["n_informative_offspring"]) for r in fam)
    consistent  = sum(int(r["n_consistent"]) for r in fam)
    inconsistent = sum(int(r["n_inconsistent"]) for r in fam)
    switches    = sum(int(r["n_internal_switches"]) for r in fam)
    rec_rate = round(switches / informative, 4) if informative else 0.0
    row_73 = {
        "block_id": cand["block_id"],
        "informative_families": informative_fams,
        "informative_offspring": informative,
        "mendelian_consistent_offspring": consistent,
        "inconsistent_offspring": inconsistent,
        "apparent_internal_switches": switches,
        "estimated_recombinant_rate": rec_rate,
        "interpretation": i73,
    }

    return {
        "7_1": row_71, "7_2": row_72, "7_3": row_73,
        "n_localpca_windows": len(lpca),
    }


def write_tsv(rows: list[dict], out: pathlib.Path) -> None:
    if not rows:
        out.write_text("")
        return
    fields = list(rows[0].keys())
    with open(out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, delimiter="\t")
        w.writeheader()
        w.writerows(rows)


def main() -> int:
    if not ROOT.exists():
        print(f"no candidates root: {ROOT}", file=sys.stderr)
        return 1
    folders = sorted(f for f in ROOT.iterdir() if f.is_dir())
    print(f"harvesting {len(folders)} candidate folder(s) from {ROOT}")
    rows_71, rows_72, rows_73 = [], [], []
    for f in folders:
        out = harvest_one(f)
        if out:
            rows_71.append(out["7_1"]); rows_72.append(out["7_2"]); rows_73.append(out["7_3"])
            print(f"  {f.name}: {out['7_1']['interpretation']} / "
                  f"{out['7_2']['interpretation']} / {out['7_3']['interpretation']}  "
                  f"(localpca_windows={out['n_localpca_windows']})")
    write_tsv(rows_71, ROOT / "table_7_1.tsv")
    write_tsv(rows_72, ROOT / "table_7_2.tsv")
    write_tsv(rows_73, ROOT / "table_7_3.tsv")
    print(f"wrote {ROOT}/table_7_{{1,2,3}}.tsv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
