#!/usr/bin/env python3
"""
render_candidate_figures.py — emit five publication SVGs per candidate
from the files under 04_results/candidates/<id>/. Deterministic
(no embedded timestamp), no browser, pure stdlib. Same publication
contract as graph_figure_export.py:

    same data -> one drawing function -> fixed size -> white bg
    -> standard font -> vector SVG

Per candidate (into <id>/figures/):
  fig1_localpca_track.svg     PC1 per cluster across the block
  fig2_karyotype_groups.svg   observed vs HWE-expected class counts
  fig3_popstats_track.svg     pi / arrangement_FST_like / HWE_FIS per window
  fig4_heterozygosity.svg     per-window obs vs exp heterozygosity
  fig5_frequency_summary.svg  block-level frequency / HWE / FIS info-card

§refusals: read-only on the candidate folders; writes only to figures/.
"""
from __future__ import annotations
import csv, json, math, pathlib, sys

REPO = pathlib.Path(__file__).resolve().parents[3]
ROOT = REPO / "toolkit_registries" / "relatedness" / "04_results" / "candidates"

# ---- publication geometry --------------------------------------------------
W, H = 920, 360
PAD_L, PAD_R, PAD_T, PAD_B = 70, 24, 46, 56
PLOT_W = W - PAD_L - PAD_R
PLOT_H = H - PAD_T - PAD_B
FONT = "Helvetica, Arial, sans-serif"
COL = {
    "H1H1": "#1f6feb",
    "H1H2": "#9b59b6",
    "H2H2": "#d35400",
    "pi":               "#2f855a",
    "arrangement_FST":  "#9c4221",
    "HWE_FIS":          "#1a2540",
    "obs":              "#1f6feb",
    "exp":              "#a0aec0",
    "grid":             "#e2e8f0",
    "axis":             "#4a5568",
    "title":            "#1a202c",
    "subtitle":         "#4a5568",
}


def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def fnum(s):
    try: return float(s)
    except (TypeError, ValueError): return None


def load_tsv(p):
    if not p.exists(): return []
    text = [l for l in p.read_text().splitlines() if l and not l.startswith("#")]
    if not text: return []
    return [dict(r) for r in csv.DictReader(text, delimiter="\t")]


def load_json(p):
    return json.loads(p.read_text()) if p.exists() else None


def svg_open(title: str, subtitle: str, h: int = H) -> list[str]:
    out = []
    out.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{h}" '
        f'viewBox="0 0 {W} {h}" font-family="{FONT}">'
    )
    out.append(f'<rect x="0" y="0" width="{W}" height="{h}" fill="#ffffff"/>')
    out.append(f'<text x="{PAD_L}" y="22" font-size="16" font-weight="700" fill="{COL["title"]}">{esc(title)}</text>')
    out.append(f'<text x="{PAD_L}" y="38" font-size="11" fill="{COL["subtitle"]}">{esc(subtitle)}</text>')
    return out


def svg_close(out): out.append("</svg>"); return "\n".join(out)


def axis_box(ax, ay, aw, ah):
    return (
        f'<rect x="{ax}" y="{ay}" width="{aw}" height="{ah}" '
        f'fill="none" stroke="{COL["axis"]}" stroke-width="0.8"/>'
    )


def scale(v, vmin, vmax, pmin, pmax):
    if vmax == vmin: return (pmin + pmax) / 2
    return pmin + (v - vmin) / (vmax - vmin) * (pmax - pmin)


def hgrid_with_labels(ymin, ymax, ay, ah, ax_left, ax_right, n=4, fmt="{:.2f}"):
    out = []
    for i in range(n + 1):
        v = ymin + (ymax - ymin) * i / n
        y = ay + ah - (i / n) * ah
        out.append(f'<line x1="{ax_left}" y1="{y:.1f}" x2="{ax_right}" y2="{y:.1f}" '
                   f'stroke="{COL["grid"]}" stroke-width="0.6"/>')
        out.append(f'<text x="{ax_left - 6}" y="{y + 3:.1f}" font-size="10" '
                   f'fill="{COL["axis"]}" text-anchor="end">{fmt.format(v)}</text>')
    return out


# ---------- Figure 1: local-PCA track ---------------------------------------
def fig1_localpca(folder, cand, regime):
    lpca = load_tsv(folder / "localpca_windows.tsv")
    if not lpca: return None
    xs = [int(r["start"]) for r in lpca]
    xmin, xmax = min(xs), max(int(r["end"]) for r in lpca)
    ymin, ymax = -1.0, 1.0
    out = svg_open(
        f"Fig 1 · {cand['block_id']} · Local-PCA per-window PC1 by karyotype cluster",
        f"{cand['chrom']}:{cand['start']:,}–{cand['end']:,}  ·  {regime['n_windows']} windows · "
        f"long-range vote {regime['long_range_vote_pct']:.0f}% · "
        f"local continuity {regime['local_continuity_score']:.2f}"
    )
    out.append(axis_box(PAD_L, PAD_T, PLOT_W, PLOT_H))
    out.extend(hgrid_with_labels(ymin, ymax, PAD_T, PLOT_H, PAD_L, PAD_L + PLOT_W))

    # X-axis ticks
    for i in range(6):
        bp = xmin + (xmax - xmin) * i / 5
        x = scale(bp, xmin, xmax, PAD_L, PAD_L + PLOT_W)
        out.append(f'<line x1="{x:.1f}" y1="{PAD_T + PLOT_H}" x2="{x:.1f}" y2="{PAD_T + PLOT_H + 4}" stroke="{COL["axis"]}"/>')
        out.append(f'<text x="{x:.1f}" y="{PAD_T + PLOT_H + 16}" font-size="10" '
                   f'fill="{COL["axis"]}" text-anchor="middle">{int(bp/1e6)} Mb</text>')

    # one polyline per cluster
    for label, key in (("H1H1", "pc1_median_H1H1"), ("H1H2", "pc1_median_H1H2"), ("H2H2", "pc1_median_H2H2")):
        pts = []
        for r in lpca:
            xc = scale((int(r["start"]) + int(r["end"])) / 2, xmin, xmax, PAD_L, PAD_L + PLOT_W)
            yc = scale(fnum(r[key]) or 0.0, ymin, ymax, PAD_T + PLOT_H, PAD_T)
            pts.append(f"{xc:.1f},{yc:.1f}")
            out.append(f'<circle cx="{xc:.1f}" cy="{yc:.1f}" r="2.2" fill="{COL[label]}"/>')
        out.append(f'<polyline points="{" ".join(pts)}" fill="none" '
                   f'stroke="{COL[label]}" stroke-width="1.3" stroke-opacity="0.55"/>')

    # Legend
    lx, ly = PAD_L, H - 18
    for i, label in enumerate(["H1H1", "H1H2", "H2H2"]):
        out.append(f'<rect x="{lx + i*120}" y="{ly - 9}" width="12" height="12" rx="2" fill="{COL[label]}"/>')
        out.append(f'<text x="{lx + i*120 + 17}" y="{ly + 1}" font-size="11" fill="{COL["axis"]}">{label}</text>')
    out.append(f'<text x="{PAD_L - 50}" y="{PAD_T + PLOT_H/2}" font-size="11" fill="{COL["axis"]}" '
               f'text-anchor="middle" transform="rotate(-90 {PAD_L - 50},{PAD_T + PLOT_H/2})">PC1 median</text>')
    return svg_close(out)


# ---------- Figure 2: karyotype group bars ----------------------------------
def fig2_karyotype(folder, cand, freq):
    out = svg_open(
        f"Fig 2 · {cand['block_id']} · Karyotype-group counts (observed vs HWE-expected)",
        f"n = {freq['n_total']}  ·  freq H1 = {freq['freq_H1']:.3f}  ·  "
        f"HWE χ² = {freq['HWE_chi2']:.3f}, p = {freq['HWE_p']:.3f}  ·  HWE_FIS = {freq['HWE_FIS']:+.3f}"
    )
    cats = ["H1H1", "H1H2", "H2H2"]
    obs = [freq[f"n_{c}"] for c in cats]
    exp = [freq[f"expected_{c}"] for c in cats]
    ymax = max(obs + exp) * 1.15
    out.append(axis_box(PAD_L, PAD_T, PLOT_W, PLOT_H))
    out.extend(hgrid_with_labels(0, ymax, PAD_T, PLOT_H, PAD_L, PAD_L + PLOT_W, n=4, fmt="{:.0f}"))

    bar_w = PLOT_W / (len(cats) * 3)
    for i, c in enumerate(cats):
        cx = PAD_L + (i + 0.5) * PLOT_W / len(cats)
        h_obs = (obs[i] / ymax) * PLOT_H
        h_exp = (exp[i] / ymax) * PLOT_H
        # observed (filled)
        out.append(f'<rect x="{cx - bar_w*1.05:.1f}" y="{PAD_T + PLOT_H - h_obs:.1f}" '
                   f'width="{bar_w:.1f}" height="{h_obs:.1f}" fill="{COL[c]}"/>')
        # expected (outlined)
        out.append(f'<rect x="{cx + 0.05*bar_w:.1f}" y="{PAD_T + PLOT_H - h_exp:.1f}" '
                   f'width="{bar_w:.1f}" height="{h_exp:.1f}" fill="none" stroke="{COL[c]}" stroke-width="1.5" stroke-dasharray="3 3"/>')
        out.append(f'<text x="{cx:.1f}" y="{PAD_T + PLOT_H + 16}" font-size="11" '
                   f'fill="{COL["axis"]}" text-anchor="middle">{c}</text>')
        out.append(f'<text x="{cx - bar_w*0.55:.1f}" y="{PAD_T + PLOT_H - h_obs - 4:.1f}" font-size="10" '
                   f'fill="{COL["axis"]}" text-anchor="middle">{obs[i]}</text>')
        out.append(f'<text x="{cx + bar_w*0.55:.1f}" y="{PAD_T + PLOT_H - h_exp - 4:.1f}" font-size="10" '
                   f'fill="{COL["axis"]}" text-anchor="middle">{exp[i]:.0f}</text>')

    # legend
    lx, ly = PAD_L, H - 18
    out.append(f'<rect x="{lx}" y="{ly - 9}" width="12" height="12" fill="{COL["axis"]}"/>')
    out.append(f'<text x="{lx + 17}" y="{ly + 1}" font-size="11" fill="{COL["axis"]}">observed</text>')
    out.append(f'<rect x="{lx + 100}" y="{ly - 9}" width="12" height="12" fill="none" '
               f'stroke="{COL["axis"]}" stroke-width="1.5" stroke-dasharray="3 3"/>')
    out.append(f'<text x="{lx + 117}" y="{ly + 1}" font-size="11" fill="{COL["axis"]}">HWE expected</text>')
    return svg_close(out)


# ---------- Figure 3: per-window popstats (stacked tracks) ------------------
def fig3_popstats(folder, cand, regime):
    pop = load_tsv(folder / "popstats.tsv")
    if not pop: return None
    h_total = 480
    out = svg_open(
        f"Fig 3 · {cand['block_id']} · Per-window popstats (π · arrangement_FST_like · HWE_FIS)",
        f"{cand['chrom']}:{cand['start']:,}–{cand['end']:,}  ·  {regime['n_windows']} windows",
        h=h_total
    )
    xs = [int(r["start"]) for r in pop]
    xmin, xmax = min(xs), max(int(r["end"]) for r in pop)
    tracks = [
        ("pi",                    "π (nucleotide diversity)", COL["pi"]),
        ("arrangement_FST_like",  "arrangement_FST_like (H1 vs H2)", COL["arrangement_FST"]),
        ("HWE_FIS",               "HWE_FIS (window)", COL["HWE_FIS"]),
    ]
    track_h = (h_total - PAD_T - PAD_B - 30) / len(tracks)
    for ti, (col, lbl, color) in enumerate(tracks):
        ay = PAD_T + ti * (track_h + 10)
        vals = [fnum(r[col]) or 0.0 for r in pop]
        vmin, vmax = min(vals), max(vals)
        if vmax == vmin: vmax = vmin + 1e-6
        out.append(axis_box(PAD_L, ay, PLOT_W, track_h))
        out.extend(hgrid_with_labels(vmin, vmax, ay, track_h, PAD_L, PAD_L + PLOT_W, n=3, fmt="{:.3f}"))
        pts = []
        for r in pop:
            xc = scale((int(r["start"]) + int(r["end"])) / 2, xmin, xmax, PAD_L, PAD_L + PLOT_W)
            yc = scale(fnum(r[col]) or 0.0, vmin, vmax, ay + track_h, ay)
            pts.append(f"{xc:.1f},{yc:.1f}")
        out.append(f'<polyline points="{" ".join(pts)}" fill="none" '
                   f'stroke="{color}" stroke-width="1.4"/>')
        out.append(f'<text x="{PAD_L + 8}" y="{ay + 14}" font-size="11" '
                   f'fill="{color}" font-weight="600">{esc(lbl)}</text>')

    # X-axis ticks
    ay = PAD_T + (len(tracks) - 1) * (track_h + 10) + track_h
    for i in range(6):
        bp = xmin + (xmax - xmin) * i / 5
        x = scale(bp, xmin, xmax, PAD_L, PAD_L + PLOT_W)
        out.append(f'<text x="{x:.1f}" y="{ay + 16}" font-size="10" '
                   f'fill="{COL["axis"]}" text-anchor="middle">{int(bp/1e6)} Mb</text>')
    return svg_close(out)


# ---------- Figure 4: heterozygosity (observed vs expected per window) ------
def fig4_het(folder, cand):
    pop = load_tsv(folder / "popstats.tsv")
    if not pop: return None
    obs = [fnum(r["heterozygosity_obs"]) or 0.0 for r in pop]
    exp = [fnum(r["heterozygosity_exp"]) or 0.0 for r in pop]
    mean_obs = sum(obs) / len(obs); mean_exp = sum(exp) / len(exp)
    out = svg_open(
        f"Fig 4 · {cand['block_id']} · Per-window heterozygosity (observed vs expected)",
        f"mean observed = {mean_obs:.3f}  ·  mean expected = {mean_exp:.3f}  ·  "
        f"Δ = {mean_obs - mean_exp:+.3f}"
    )
    xs = [int(r["start"]) for r in pop]
    xmin, xmax = min(xs), max(int(r["end"]) for r in pop)
    ymin = 0
    ymax = max(obs + exp) * 1.15
    out.append(axis_box(PAD_L, PAD_T, PLOT_W, PLOT_H))
    out.extend(hgrid_with_labels(ymin, ymax, PAD_T, PLOT_H, PAD_L, PAD_L + PLOT_W, n=4, fmt="{:.3f}"))

    for series, color, key in (("exp", COL["exp"], exp), ("obs", COL["obs"], obs)):
        pts = []
        for r, v in zip(pop, key):
            xc = scale((int(r["start"]) + int(r["end"])) / 2, xmin, xmax, PAD_L, PAD_L + PLOT_W)
            yc = scale(v, ymin, ymax, PAD_T + PLOT_H, PAD_T)
            pts.append(f"{xc:.1f},{yc:.1f}")
        out.append(f'<polyline points="{" ".join(pts)}" fill="none" '
                   f'stroke="{color}" stroke-width="1.5"/>')

    for i in range(6):
        bp = xmin + (xmax - xmin) * i / 5
        x = scale(bp, xmin, xmax, PAD_L, PAD_L + PLOT_W)
        out.append(f'<text x="{x:.1f}" y="{PAD_T + PLOT_H + 16}" font-size="10" '
                   f'fill="{COL["axis"]}" text-anchor="middle">{int(bp/1e6)} Mb</text>')

    lx, ly = PAD_L, H - 18
    out.append(f'<rect x="{lx}" y="{ly - 9}" width="12" height="12" fill="{COL["obs"]}"/>')
    out.append(f'<text x="{lx + 17}" y="{ly + 1}" font-size="11" fill="{COL["axis"]}">observed</text>')
    out.append(f'<rect x="{lx + 110}" y="{ly - 9}" width="12" height="12" fill="{COL["exp"]}"/>')
    out.append(f'<text x="{lx + 127}" y="{ly + 1}" font-size="11" fill="{COL["axis"]}">expected (HWE)</text>')
    return svg_close(out)


# ---------- Figure 5: frequency / HWE / FIS info-card -----------------------
def fig5_summary(folder, cand, freq, regime):
    h_total = 280
    out = svg_open(
        f"Fig 5 · {cand['block_id']} · Block frequency / HWE / FIS summary",
        f"cohort {cand['cohort_id']}  ·  n = {freq['n_total']}  ·  "
        f"polymorphism class: {freq['polymorphism_class'].replace('_', ' ')}",
        h=h_total
    )
    y = 70
    rows = [
        ("freq(H1)",   f"{freq['freq_H1']:.4f}",                   ""),
        ("freq(H2)",   f"{1 - freq['freq_H1']:.4f}",               ""),
        ("n H1H1",     f"{freq['n_H1H1']}",                        f"(exp HWE {freq['expected_H1H1']:.1f})"),
        ("n H1H2",     f"{freq['n_H1H2']}",                        f"(exp HWE {freq['expected_H1H2']:.1f})"),
        ("n H2H2",     f"{freq['n_H2H2']}",                        f"(exp HWE {freq['expected_H2H2']:.1f})"),
        ("HWE χ²",     f"{freq['HWE_chi2']:.3f}",                  "1 df"),
        ("HWE p",      f"{freq['HWE_p']:.3f}",                     "erfc(√(χ²/2))"),
        ("HWE_FIS",    f"{freq['HWE_FIS']:+.4f}",                  "1 − H_obs/H_exp"),
        ("long-range vote", f"{regime['long_range_vote_pct']:.0f}%", ""),
        ("local continuity",f"{regime['local_continuity_score']:.2f}", ""),
    ]
    out.append(f'<rect x="{PAD_L - 8}" y="56" width="{W - PAD_L - PAD_R + 16}" height="{h_total - 90}" '
               f'rx="6" fill="#fafbfc" stroke="#e2e8f0"/>')
    for i, (k, v, extra) in enumerate(rows):
        yy = y + 8 + i * 18
        out.append(f'<text x="{PAD_L}" y="{yy}" font-size="12" fill="{COL["axis"]}">{esc(k)}</text>')
        out.append(f'<text x="{PAD_L + 160}" y="{yy}" font-size="12" font-weight="600" '
                   f'fill="{COL["title"]}">{esc(v)}</text>')
        if extra:
            out.append(f'<text x="{PAD_L + 270}" y="{yy}" font-size="11" '
                       f'fill="{COL["subtitle"]}">{esc(extra)}</text>')
    return svg_close(out)


# ---------- driver ----------------------------------------------------------
def render_one(folder):
    cand = load_json(folder / "candidate.json")
    regime = load_json(folder / "long_range_regime.json")
    freq = load_json(folder / "frequency_block.json")
    if not (cand and regime and freq):
        print(f"  skipped {folder.name}: missing JSON", file=sys.stderr); return
    figs = folder / "figures"; figs.mkdir(exist_ok=True)
    for name, svg in (
        ("fig1_localpca_track.svg",     fig1_localpca(folder, cand, regime)),
        ("fig2_karyotype_groups.svg",   fig2_karyotype(folder, cand, freq)),
        ("fig3_popstats_track.svg",     fig3_popstats(folder, cand, regime)),
        ("fig4_heterozygosity.svg",     fig4_het(folder, cand)),
        ("fig5_frequency_summary.svg",  fig5_summary(folder, cand, freq, regime)),
    ):
        if svg is None:
            print(f"  {folder.name}/{name}: skipped (input missing)"); continue
        (figs / name).write_text(svg)
        print(f"  {folder.name}/figures/{name}")


def main():
    if not ROOT.exists():
        print(f"no candidates root: {ROOT}", file=sys.stderr); return 1
    for f in sorted(d for d in ROOT.iterdir() if d.is_dir()):
        render_one(f)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
