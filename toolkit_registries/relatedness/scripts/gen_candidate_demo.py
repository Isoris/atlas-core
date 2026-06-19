#!/usr/bin/env python3
"""
gen_candidate_demo.py — deterministic synthetic demo for the per-candidate
folder model. Generates 3 candidates (LRR01, LRR02, LRR03) under
04_results/candidates/<id>/ with all evidence files conforming to the
schemas in toolkit_registries/schemas/structured_block_schemas/. Pure
stdlib, seeded — running twice produces byte-identical output.

§refusals: this is SYNTHETIC demonstration data on the n=226 hatchery
cohort frame, NOT real biological measurements. Each generated file
carries `synthetic: true` (JSON) or a `# SYNTHETIC` header (TSV). Do not
quote any number from these files as a finding.
"""
from __future__ import annotations
import csv, json, math, pathlib, random

REPO = pathlib.Path(__file__).resolve().parents[3]
ROOT = REPO / "toolkit_registries" / "relatedness" / "04_results" / "candidates"
COHORT = "cgar_hatchery_226"
N_SAMPLES = 226
N_FAMILIES = 18

# Per-candidate generator config.  Three deliberately different profiles:
#   LRR01 — clean inversion-like 3-cluster signal (the LG28 showcase)
#   LRR02 — smaller block, slightly less clean
#   LRR03 — weaker / less coherent signal (still a candidate)
CANDIDATES = [
    {
        "block_id": "LRR01",
        "chrom":    "C_gar_LG28",
        "start":    1_200_000,
        "end":      8_400_000,
        "window_bp": 100_000,
        "freq_H1":  0.50,
        "long_range_vote_pct": 86.0,
        "local_continuity_score": 0.91,
        "fst_inside_mean":  0.72,
        "fst_outside_mean": 0.05,
        "pi_inside_mean":   0.0058,
        "fis_inside_mean":  -0.082,    # heterozygote excess
        "n_informative_per_family": 6,
        "inconsistency_rate":   0.02,
        "internal_switch_rate": 0.015,
        "seed": 28,
    },
    {
        "block_id": "LRR02",
        "chrom":    "C_gar_LG14",
        "start":    22_400_000,
        "end":      26_900_000,
        "window_bp": 100_000,
        "freq_H1":  0.41,
        "long_range_vote_pct": 71.0,
        "local_continuity_score": 0.78,
        "fst_inside_mean":  0.48,
        "fst_outside_mean": 0.05,
        "pi_inside_mean":   0.0046,
        "fis_inside_mean":  -0.041,
        "n_informative_per_family": 5,
        "inconsistency_rate":   0.06,
        "internal_switch_rate": 0.04,
        "seed": 14,
    },
    {
        "block_id": "LRR03",
        "chrom":    "C_gar_LG07",
        "start":    11_100_000,
        "end":      13_700_000,
        "window_bp": 100_000,
        "freq_H1":  0.32,
        "long_range_vote_pct": 58.0,
        "local_continuity_score": 0.62,
        "fst_inside_mean":  0.31,
        "fst_outside_mean": 0.05,
        "pi_inside_mean":   0.0041,
        "fis_inside_mean":  -0.018,
        "n_informative_per_family": 4,
        "inconsistency_rate":   0.11,
        "internal_switch_rate": 0.08,
        "seed": 7,
    },
]


def hwe_chi2_p(n_AA: int, n_Aa: int, n_aa: int) -> tuple[float, float, float, float, float, float]:
    n = n_AA + n_Aa + n_aa
    if n == 0:
        return 0.0, 1.0, 0.0, 0.0, 0.0, 0.0
    p = (2 * n_AA + n_Aa) / (2 * n)
    q = 1 - p
    e_AA, e_Aa, e_aa = n * p * p, 2 * n * p * q, n * q * q
    chi2 = 0.0
    for o, e in ((n_AA, e_AA), (n_Aa, e_Aa), (n_aa, e_aa)):
        if e > 0:
            chi2 += (o - e) ** 2 / e
    # 1-df chi-square upper-tail = erfc(sqrt(x/2))
    pval = math.erfc(math.sqrt(chi2 / 2.0)) if chi2 > 0 else 1.0
    return chi2, pval, e_AA, e_Aa, e_aa, p


def fis(n_Aa: int, n_total: int, p: float) -> float:
    if n_total == 0 or p in (0.0, 1.0):
        return 0.0
    h_obs = n_Aa / n_total
    h_exp = 2 * p * (1 - p)
    return 1 - h_obs / h_exp if h_exp > 0 else 0.0


def round2(x):  # JSON-friendly rounding
    return round(float(x), 6)


def write_candidate(cfg: dict) -> None:
    rng = random.Random(cfg["seed"])
    bid = cfg["block_id"]
    dst = ROOT / bid
    dst.mkdir(parents=True, exist_ok=True)
    figs = dst / "figures"
    figs.mkdir(exist_ok=True)

    size_bp = cfg["end"] - cfg["start"] + 1
    n_windows = max(1, size_bp // cfg["window_bp"])

    # ---- karyotype_groups.tsv (n=226, seeded) ---------------------------
    fH1 = cfg["freq_H1"]
    # Heterozygote excess: bias H1H2 up by ~3% absolute (consistent with the
    # FIS inside_mean we report).
    p, q = fH1, 1 - fH1
    pe = p * p
    he = 2 * p * q
    qe = q * q
    fis_target = cfg["fis_inside_mean"]
    he_actual = he * (1 - fis_target)         # heterozygotes inflated
    excess = he_actual - he
    pe_actual = pe - excess / 2
    qe_actual = qe - excess / 2
    karyo_lines = ["sample_id\tkaryotype_class\tconfidence\tfamily_id"]
    counts = {"H1H1": 0, "H1H2": 0, "H2H2": 0}
    for i in range(1, N_SAMPLES + 1):
        u = rng.random()
        if u < pe_actual:
            k = "H1H1"
        elif u < pe_actual + he_actual:
            k = "H1H2"
        else:
            k = "H2H2"
        counts[k] += 1
        conf = round2(0.85 + rng.random() * 0.14)
        fam = f"BL{((i - 1) % N_FAMILIES) + 1:02d}"
        karyo_lines.append(f"S{i:03d}\t{k}\t{conf}\t{fam}")
    (dst / "karyotype_groups.tsv").write_text(
        "# SYNTHETIC demo — n=226 hatchery (cgar_hatchery_226) — gen_candidate_demo.py\n"
        + "\n".join(karyo_lines) + "\n"
    )

    n_total = sum(counts.values())
    chi2, pval, e11, e12, e22, freq_H1 = hwe_chi2_p(counts["H1H1"], counts["H1H2"], counts["H2H2"])
    fis_obs = fis(counts["H1H2"], n_total, freq_H1)

    # ---- localpca_windows.tsv -------------------------------------------
    # PC1 medians per cluster: clean separation inside; noisier in LRR02/03
    sep = cfg["fst_inside_mean"]
    sep_noise = 0.05
    lpca_lines = ["window_id\tchrom\tstart\tend\tpc1_median_H1H1\tpc1_median_H1H2\tpc1_median_H2H2"
                  "\tpc2_median_H1H1\tpc2_median_H1H2\tpc2_median_H2H2\twindow_cluster_continuity"]
    pos = cfg["start"]
    for w in range(n_windows):
        wstart, wend = pos, min(pos + cfg["window_bp"] - 1, cfg["end"])
        wid = f"{bid}_W{w + 1:03d}"
        pc1_h1 = -sep + rng.uniform(-sep_noise, sep_noise)
        pc1_h2 =  sep + rng.uniform(-sep_noise, sep_noise)
        pc1_het = rng.uniform(-0.03, 0.03)
        pc2_h1 = rng.uniform(-0.05, 0.05)
        pc2_h2 = rng.uniform(-0.05, 0.05)
        pc2_het = rng.uniform(-0.05, 0.05)
        cont = round2(cfg["local_continuity_score"] + rng.uniform(-0.05, 0.05))
        cont = max(0.0, min(1.0, cont))
        lpca_lines.append(
            f"{wid}\t{cfg['chrom']}\t{wstart}\t{wend}\t"
            f"{round2(pc1_h1)}\t{round2(pc1_het)}\t{round2(pc1_h2)}\t"
            f"{round2(pc2_h1)}\t{round2(pc2_het)}\t{round2(pc2_h2)}\t{cont}"
        )
        pos += cfg["window_bp"]
    (dst / "localpca_windows.tsv").write_text(
        "# SYNTHETIC demo — local-PCA per-window summaries — gen_candidate_demo.py\n"
        + "\n".join(lpca_lines) + "\n"
    )

    # ---- popstats.tsv ---------------------------------------------------
    ps_lines = ["window_id\tchrom\tstart\tend\tpi\tdxy_H1_H2\tarrangement_FST_like"
                "\tHWE_FIS\theterozygosity_obs\theterozygosity_exp"]
    pos = cfg["start"]
    he_exp = he
    for w in range(n_windows):
        wstart, wend = pos, min(pos + cfg["window_bp"] - 1, cfg["end"])
        wid = f"{bid}_W{w + 1:03d}"
        pi = round2(cfg["pi_inside_mean"] + rng.uniform(-0.0008, 0.0008))
        dxy = round2(pi * 2.1 + rng.uniform(-0.0006, 0.0006))
        fst = round2(cfg["fst_inside_mean"] + rng.uniform(-0.08, 0.08))
        fst = max(0.0, min(1.0, fst))
        fis_w = round2(cfg["fis_inside_mean"] + rng.uniform(-0.04, 0.04))
        het_obs = round2(he_exp * (1 - fis_w))
        het_exp = round2(he_exp + rng.uniform(-0.005, 0.005))
        ps_lines.append(
            f"{wid}\t{cfg['chrom']}\t{wstart}\t{wend}\t{pi}\t{dxy}\t{fst}\t{fis_w}\t{het_obs}\t{het_exp}"
        )
        pos += cfg["window_bp"]
    (dst / "popstats.tsv").write_text(
        "# SYNTHETIC demo — per-window popstats — gen_candidate_demo.py\n"
        + "\n".join(ps_lines) + "\n"
    )

    # ---- family_segregation.tsv ----------------------------------------
    fs_lines = ["family_id\tn_informative_offspring\tn_consistent\tn_inconsistent\tn_internal_switches"]
    tot_off = tot_cons = tot_inc = tot_sw = 0
    for f in range(1, N_FAMILIES + 1):
        fam = f"BL{f:02d}"
        n_off = cfg["n_informative_per_family"] + rng.randint(-1, 1)
        n_off = max(2, n_off)
        n_inc = sum(1 for _ in range(n_off) if rng.random() < cfg["inconsistency_rate"])
        n_cons = n_off - n_inc
        n_sw = sum(1 for _ in range(n_off) if rng.random() < cfg["internal_switch_rate"])
        fs_lines.append(f"{fam}\t{n_off}\t{n_cons}\t{n_inc}\t{n_sw}")
        tot_off += n_off; tot_cons += n_cons; tot_inc += n_inc; tot_sw += n_sw
    (dst / "family_segregation.tsv").write_text(
        "# SYNTHETIC demo — per-family segregation counts — gen_candidate_demo.py\n"
        + "\n".join(fs_lines) + "\n"
    )

    # ---- candidate.json -------------------------------------------------
    (dst / "candidate.json").write_text(json.dumps({
        "block_id": bid, "chrom": cfg["chrom"], "start": cfg["start"], "end": cfg["end"],
        "size_bp": size_bp, "cohort_id": COHORT,
        "source": "synthetic demo (gen_candidate_demo.py)", "synthetic": True
    }, indent=2) + "\n")

    # ---- long_range_regime.json ----------------------------------------
    (dst / "long_range_regime.json").write_text(json.dumps({
        "block_id": bid, "n_windows": n_windows, "window_bp": cfg["window_bp"],
        "long_range_vote_pct": cfg["long_range_vote_pct"],
        "local_continuity_score": cfg["local_continuity_score"],
        "major_dosage_classes": ["H1H1", "H1H2", "H2H2"],
        "detection_method": "synthetic demo",
        "broodline_structure_note": "Any K-structure observed in the cgar_hatchery_226 cohort is broodline / family structure, NOT species admixture."
    }, indent=2) + "\n")

    # ---- frequency_block.json ------------------------------------------
    if abs(freq_H1 - 0.5) < 0.1:
        pclass = "balanced_three_class"
    elif min(freq_H1, 1 - freq_H1) < 0.1:
        pclass = "near_monomorphic"
    else:
        pclass = "skewed_minor_allele"
    (dst / "frequency_block.json").write_text(json.dumps({
        "block_id": bid, "n_total": n_total,
        "n_H1H1": counts["H1H1"], "n_H1H2": counts["H1H2"], "n_H2H2": counts["H2H2"],
        "freq_H1": round2(freq_H1),
        "expected_H1H1": round2(e11), "expected_H1H2": round2(e12), "expected_H2H2": round2(e22),
        "HWE_chi2": round2(chi2), "HWE_p": round2(pval),
        "HWE_FIS": round2(fis_obs),
        "polymorphism_class": pclass
    }, indent=2) + "\n")

    print(f"  {bid}: {cfg['chrom']}:{cfg['start']}-{cfg['end']}  "
          f"n=({counts['H1H1']}/{counts['H1H2']}/{counts['H2H2']})  "
          f"freq_H1={freq_H1:.3f}  HWE_p={pval:.3f}  FIS={fis_obs:+.3f}")


def main() -> int:
    ROOT.mkdir(parents=True, exist_ok=True)
    print(f"generating demo candidates into {ROOT}")
    for cfg in CANDIDATES:
        write_candidate(cfg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
