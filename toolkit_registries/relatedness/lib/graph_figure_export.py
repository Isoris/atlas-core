#!/usr/bin/env python3
"""
graph_figure_export.py — publication-quality SVG export for the registry
architecture graphs (layer / atlas-dependency / chain / panel-coverage).

Reads a *_graph.json from 01_registry/graphs/ — schema:
    {"nodes":[{"id","kind","label",...}], "edges":[{"from","to","kind",...}]}
— and emits a clean, DETERMINISTIC SVG figure: fixed font, white background,
no UI chrome, layered left-to-right layout.

The "publication export" contract (why this exists rather than a screenshot):

    same data -> one drawing function -> deterministic layout -> white bg
    -> standard font -> vector SVG

No browser, no canvas, no device-pixel-ratio, no screenshot path — so the
same registry state always yields a byte-identical figure (the output embeds
no timestamp). SVG is the master format; convert to PDF losslessly with
cairosvg / rsvg-convert / inkscape when a vector PDF is required (the tool
prints the exact command and will run it automatically if a converter is
on PATH).

§refusals: read-only; never mutates a registry; only writes the output file.

Usage:
  python3 -m toolkit_registries.relatedness.lib.graph_figure_export --list
  python3 -m ...graph_figure_export --graph atlas_dependency --out fig.svg
  python3 -m ...graph_figure_export --graph chain --out chain.svg --pdf
  python3 -m ...graph_figure_export --all --outdir 05_figures
"""
from __future__ import annotations
import argparse
import json
import pathlib
import shutil
import subprocess
import sys

REPO   = pathlib.Path(__file__).resolve().parents[3]
RELA   = REPO / "toolkit_registries" / "relatedness"
GRAPHS = RELA / "01_registry" / "graphs"

# ---- drawing constants (the fixed publication geometry) --------------------
NODE_H    = 28      # node box height, px
FONT      = 13      # label font-size, px
TITLE_FS  = 22
SUB_FS    = 13
CHAR_W    = 6.9     # mean glyph advance at FONT px (Helvetica/Arial)
PAD       = 44      # outer margin
COL_GAP   = 92      # horizontal gap between layout columns
ROW_GAP   = 14      # vertical gap between nodes in a column
LABEL_PAD = 22      # horizontal padding inside a node box
MAX_LABEL = 46      # truncate labels longer than this (chars)

# kind -> fill. node["color"] wins when present; then source_kind; then this.
PALETTE = {
    "atlas":    "#1a2540",
    "layer":    "#2b6cb0",
    "analysis": "#2f855a",
    "chain":    "#9c4221",
    "panel":    "#6b46c1",
    "module":   "#b7791f",
    "file":     "#718096",
}
FALLBACK = ["#4a5568", "#805ad5", "#dd6b20", "#319795", "#c53030", "#3182ce"]


def load_graph(name_or_path: str) -> tuple[str, dict]:
    """Resolve a graph by short name (atlas_dependency, chain, layer,
    panel_coverage) or by explicit path. Returns (stem, data)."""
    p = pathlib.Path(name_or_path)
    if p.exists():
        return p.stem, json.loads(p.read_text())
    stem = name_or_path
    if not stem.endswith("_graph"):
        stem = stem + "_graph"
    f = GRAPHS / f"{stem}.json"
    if not f.exists():
        raise SystemExit(f"no such graph {name_or_path!r}; try --list")
    return f.stem, json.loads(f.read_text())


def list_graphs() -> list[pathlib.Path]:
    return sorted(GRAPHS.glob("*_graph.json"))


def esc(s: str) -> str:
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def trunc(s: str) -> str:
    s = str(s)
    return s if len(s) <= MAX_LABEL else s[: MAX_LABEL - 1] + "…"


def node_fill(n: dict, kind_color: dict[str, str]) -> str:
    if n.get("color"):
        return n["color"]
    for key in (n.get("kind"), n.get("source_kind")):
        if key and key in PALETTE:
            return PALETTE[key]
    return kind_color.get(n.get("kind", "?"), "#4a5568")


def assign_layers(node_ids: list[str], edges: list[dict]) -> dict[str, int]:
    """Longest-path layering (left-to-right). Cycle-safe: relaxation is
    capped at len(node_ids) passes, which bounds layer indices."""
    idset = set(node_ids)
    layer = {i: 0 for i in node_ids}
    for _ in range(len(node_ids)):
        changed = False
        for e in edges:
            f, t = e.get("from"), e.get("to")
            if f in idset and t in idset and layer[t] < layer[f] + 1:
                layer[t] = layer[f] + 1
                changed = True
        if not changed:
            break
    return layer


def build_svg(stem: str, data: dict, width_override: int | None) -> str:
    nodes = list(data.get("nodes", []))
    edges = data.get("edges", [])
    if not nodes:
        raise SystemExit(f"{stem}: graph has no nodes")

    # Synthesize a "referenced" ghost node for any edge endpoint that is not
    # a declared node. These graphs routinely reference layers/panels by id
    # without materializing them (e.g. chain_graph is all chains; its required
    # layers are referenced only) — without this, those edges would silently
    # vanish and the figure would collapse to one column.
    by_id = {n["id"]: n for n in nodes}
    for e in edges:
        for end in (e.get("from"), e.get("to")):
            if end and end not in by_id:
                ghost = {"id": end, "kind": "referenced", "label": end, "_ghost": True}
                by_id[end] = ghost
                nodes.append(ghost)

    has_ghost = any(n.get("_ghost") for n in nodes)

    # deterministic kind palette for kinds without an explicit color
    kinds = sorted({n.get("kind", "?") for n in nodes})
    kind_color = {}
    fi = 0
    for k in kinds:
        if k in PALETTE:
            kind_color[k] = PALETTE[k]
        elif k == "referenced":
            kind_color[k] = "#ffffff"
        else:
            kind_color[k] = FALLBACK[fi % len(FALLBACK)]
            fi += 1

    node_ids = [n["id"] for n in nodes]
    layer = assign_layers(node_ids, edges)

    # group into columns; sort within a column deterministically (label, id)
    cols: dict[int, list[dict]] = {}
    for n in nodes:
        cols.setdefault(layer[n["id"]], []).append(n)
    for c in cols:
        cols[c].sort(key=lambda n: (str(n.get("label", n["id"])).lower(), n["id"]))
    col_keys = sorted(cols)

    # geometry: per-column width from widest label; columns laid left->right
    def box_w(n: dict) -> float:
        return len(trunc(n.get("label", n["id"]))) * CHAR_W + LABEL_PAD * 2

    col_w = {c: max(box_w(n) for n in cols[c]) for c in col_keys}
    col_x: dict[int, float] = {}
    x = PAD
    for c in col_keys:
        col_x[c] = x
        x += col_w[c] + COL_GAP
    content_w = x - COL_GAP + PAD

    col_h = {c: len(cols[c]) * (NODE_H + ROW_GAP) - ROW_GAP for c in col_keys}
    content_h = max(col_h.values())
    title_h = 64

    # place nodes; columns vertically centered against the tallest column
    pos: dict[str, tuple[float, float, float]] = {}  # id -> (x, y, w)
    for c in col_keys:
        y = PAD + title_h + (content_h - col_h[c]) / 2
        for n in cols[c]:
            pos[n["id"]] = (col_x[c], y, col_w[c])
            y += NODE_H + ROW_GAP

    total_w = content_w
    total_h = PAD + title_h + content_h + PAD + 46  # +legend strip

    out: list[str] = []
    disp_w = width_override or int(total_w)
    disp_h = int(total_h * (disp_w / total_w))
    out.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{disp_w}" height="{disp_h}" '
        f'viewBox="0 0 {int(total_w)} {int(total_h)}" '
        f'font-family="Helvetica, Arial, sans-serif">'
    )
    out.append(f'<rect x="0" y="0" width="{int(total_w)}" height="{int(total_h)}" fill="#ffffff"/>')
    # arrowhead marker
    out.append(
        '<defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="7" '
        'refY="3" orient="auto"><path d="M0,0 L7,3 L0,6 Z" fill="#9aa3af"/>'
        '</marker></defs>'
    )

    # title + subtitle
    pretty = stem.replace("_", " ")
    out.append(f'<text x="{PAD}" y="{PAD + 22}" font-size="{TITLE_FS}" '
               f'font-weight="700" fill="#1a202c">{esc(pretty)}</text>')
    out.append(f'<text x="{PAD}" y="{PAD + 44}" font-size="{SUB_FS}" '
               f'fill="#4a5568">{len(nodes)} nodes · {len(edges)} edges</text>')

    # edges first (under nodes)
    for e in edges:
        f, t = e.get("from"), e.get("to")
        if f not in pos or t not in pos:
            continue
        x1, y1, w1 = pos[f]
        x2, y2, w2 = pos[t]
        sx, sy = x1 + w1, y1 + NODE_H / 2
        tx, ty = x2, y2 + NODE_H / 2
        dx = max(28, (tx - sx) * 0.5)
        out.append(
            f'<path d="M{sx:.1f},{sy:.1f} C{sx + dx:.1f},{sy:.1f} '
            f'{tx - dx:.1f},{ty:.1f} {tx:.1f},{ty:.1f}" fill="none" '
            f'stroke="#c2c8d0" stroke-width="1.2" marker-end="url(#arrow)"/>'
        )

    # nodes
    for n in nodes:
        x0, y0, w = pos[n["id"]]
        if n.get("_ghost"):
            fill, stroke, dash, text_fill = "#ffffff", "#a0aec0", ' stroke-dasharray="4 3"', "#4a5568"
        else:
            fill = node_fill(n, kind_color)
            blocked = str(n.get("status", "")).lower() in ("blocked", "inactive", "unready")
            stroke = "#e53e3e" if blocked else "#2d3748"
            dash = ' stroke-dasharray="4 3"' if blocked else ""
            text_fill = "#ffffff"
        out.append(
            f'<rect x="{x0:.1f}" y="{y0:.1f}" width="{w:.1f}" height="{NODE_H}" '
            f'rx="6" fill="{fill}" stroke="{stroke}" stroke-width="1"{dash}/>'
        )
        out.append(
            f'<text x="{x0 + w / 2:.1f}" y="{y0 + NODE_H / 2 + 4.5:.1f}" '
            f'font-size="{FONT}" fill="{text_fill}" text-anchor="middle">'
            f'{esc(trunc(n.get("label", n["id"])))}</text>'
        )

    # legend strip (kind -> colour)
    lx, ly = PAD, total_h - 24
    out.append(f'<text x="{lx}" y="{ly - 4}" font-size="11" fill="#718096">kind:</text>')
    lx += 46
    for k in kinds:
        swatch_stroke = ' stroke="#a0aec0" stroke-dasharray="2 2"' if k == "referenced" else ' stroke="#2d3748"'
        out.append(f'<rect x="{lx}" y="{ly - 12}" width="12" height="12" rx="2" '
                   f'fill="{kind_color[k]}"{swatch_stroke} stroke-width="0.8"/>')
        out.append(f'<text x="{lx + 17}" y="{ly - 2}" font-size="11" '
                   f'fill="#4a5568">{esc(k)}</text>')
        lx += 30 + len(k) * 7

    out.append("</svg>")
    return "\n".join(out)


def to_pdf(svg_path: pathlib.Path) -> bool:
    """Convert SVG->PDF if a converter is available. Returns True on success."""
    pdf = svg_path.with_suffix(".pdf")
    try:
        import cairosvg  # type: ignore
        cairosvg.svg2pdf(url=str(svg_path), write_to=str(pdf))
        print(f"  pdf  -> {pdf}")
        return True
    except Exception:
        pass
    for tool, cmd in (
        ("rsvg-convert", ["rsvg-convert", "-f", "pdf", "-o", str(pdf), str(svg_path)]),
        ("inkscape", ["inkscape", str(svg_path), "--export-filename", str(pdf)]),
    ):
        if shutil.which(tool):
            subprocess.run(cmd, check=True)
            print(f"  pdf  -> {pdf}  (via {tool})")
            return True
    print("  pdf  -> SKIPPED: no converter found. To make a vector PDF, run "
          "one of:\n"
          f"         cairosvg {svg_path} -o {pdf}\n"
          f"         rsvg-convert -f pdf -o {pdf} {svg_path}\n"
          f"         inkscape {svg_path} --export-filename {pdf}")
    return False


def export_one(name: str, out: pathlib.Path, width: int | None, pdf: bool) -> None:
    stem, data = load_graph(name)
    svg = build_svg(stem, data, width)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(svg)
    print(f"  svg  -> {out}  ({data.get('n_nodes', len(data.get('nodes', [])))} nodes)")
    if pdf:
        to_pdf(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Export registry graphs as publication SVG.")
    ap.add_argument("--graph", help="short name (atlas_dependency|chain|layer|panel_coverage) or path")
    ap.add_argument("--out", help="output .svg path")
    ap.add_argument("--all", action="store_true", help="export every *_graph.json")
    ap.add_argument("--outdir", default=str(RELA / "05_figures"), help="dir for --all")
    ap.add_argument("--width", type=int, default=None, help="display width px (vector scales losslessly)")
    ap.add_argument("--pdf", action="store_true", help="also emit PDF if a converter is available")
    ap.add_argument("--list", action="store_true", help="list available graphs and exit")
    a = ap.parse_args(argv)

    if a.list:
        for f in list_graphs():
            d = json.loads(f.read_text())
            print(f"  {f.stem:28s} {d.get('n_nodes', '?'):>4} nodes  {d.get('n_edges', '?'):>4} edges")
        return 0

    if a.all:
        outdir = pathlib.Path(a.outdir)
        print(f"exporting all graphs -> {outdir}")
        for f in list_graphs():
            export_one(f.stem, outdir / f"{f.stem}.svg", a.width, a.pdf)
        return 0

    if not a.graph:
        ap.error("give --graph NAME (with --out) or --all, or --list")
    out = pathlib.Path(a.out) if a.out else pathlib.Path(f"{a.graph}.svg")
    export_one(a.graph, out, a.width, a.pdf)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
