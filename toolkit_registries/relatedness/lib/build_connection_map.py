#!/usr/bin/env python3
"""
build_connection_map.py — scan adapters + packages + pages + panels, emit
the connection map.

Per ADAPTER_CONTRACT.md §6. The connection map is the join of:
  - analysis adapter meta (read from analysis/<id>/adapter_atlas.js)
  - package manifests   (read from packages/<id>/manifest.json)
  - page  + panel JSON  (read from 01_registry/pages.jsonl / panels.jsonl)
  - layer / hook / analysis registries (read from 01_registry/*.jsonl)

Output: 01_registry/connection_map.json — a node/edge graph that links

  packages ←→ analyses ←→ layers ←→ panels ←→ pages

Stdlib only. Does NOT run any analysis. Does NOT modify the canonical
JSONL files (use lib/tsv_from_jsonl.py for the TSV derived view).

Usage:
  python3 -m lib.build_connection_map
  python3 -m lib.build_connection_map --out /tmp/cm.json
  python3 -m lib.build_connection_map --print
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
from typing import Dict, List, Optional


# --------------------------------------------------------------------------- #
def _find_root(start: pathlib.Path) -> pathlib.Path:
    """Walk upward to find a folder with 01_registry/."""
    p = start.resolve()
    for cand in [p, *p.parents]:
        if (cand / "01_registry").is_dir():
            return cand
    raise SystemExit("could not find 01_registry/ above " + str(start))


def _find_toolkit_root(registry_root: pathlib.Path) -> Optional[pathlib.Path]:
    """toolkit_registries/ — parent of relatedness/. Holds analysis/, packages/."""
    for cand in [registry_root, *registry_root.parents]:
        if (cand / "analysis").is_dir() or (cand / "packages").is_dir():
            return cand
    return None


def _read_jsonl(path: pathlib.Path) -> List[Dict]:
    if not path.is_file(): return []
    rows = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _read_json(path: pathlib.Path) -> Optional[Dict]:
    if not path.is_file(): return None
    return json.loads(path.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- #
META_RE = re.compile(
    r"export\s+const\s+meta\s*=\s*\{(?P<body>.*?)\};",
    flags=re.S
)
KEY_RE = re.compile(r"^\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*:\s*(.+?),?\s*$", flags=re.M)


def _parse_adapter_meta(js_path: pathlib.Path) -> Optional[Dict]:
    """Lightweight extractor for the `export const meta = { ... };` block in
    adapter_atlas.js. Stdlib only — we do NOT spin up a JS engine; we accept
    only literal values (strings, arrays of strings, booleans). Adapters
    that need dynamic meta are out of scope here (rare)."""
    if not js_path.is_file(): return None
    text = js_path.read_text(encoding="utf-8")
    m = META_RE.search(text)
    if not m: return None
    body = m.group("body")
    out: Dict[str, object] = {}
    # Hand-roll a tiny parser: strip line comments and trailing commas.
    body = re.sub(r"//.*$", "", body, flags=re.M)
    # Iterate key:value pairs at top level
    depth = 0
    buf = []
    pairs = []
    for ch in body:
        if ch in "[{": depth += 1
        if ch in "]}": depth -= 1
        if ch == "," and depth == 0:
            pairs.append("".join(buf)); buf = []
            continue
        buf.append(ch)
    if buf and "".join(buf).strip(): pairs.append("".join(buf))
    for p in pairs:
        if ":" not in p: continue
        k, _, v = p.partition(":")
        k = k.strip()
        v = v.strip().rstrip(",").strip()
        if v.startswith('"') and v.endswith('"'):
            out[k] = v[1:-1]
        elif v.startswith("'") and v.endswith("'"):
            out[k] = v[1:-1]
        elif v.startswith("[") and v.endswith("]"):
            inner = v[1:-1]
            arr = [x.strip().strip('"').strip("'") for x in inner.split(",") if x.strip()]
            out[k] = arr
        elif v in ("true", "false"):
            out[k] = (v == "true")
        else:
            try: out[k] = int(v)
            except ValueError:
                try: out[k] = float(v)
                except ValueError: out[k] = v
    return out


# --------------------------------------------------------------------------- #
class ConnectionMapBuilder:
    def __init__(self, registry_root: pathlib.Path, toolkit_root: pathlib.Path):
        self.registry_root = registry_root
        self.toolkit_root  = toolkit_root
        reg = registry_root / "01_registry"
        self.layers    = _read_jsonl(reg / "layer_registry.jsonl")
        self.hooks     = _read_jsonl(reg / "hook_registry.jsonl")
        self.analyses  = _read_jsonl(reg / "analysis_registry.jsonl")
        self.results   = _read_jsonl(reg / "analysis_results.jsonl")
        self.panels    = _read_jsonl(reg / "panels.jsonl")
        self.pages     = _read_jsonl(reg / "pages.jsonl")
        self.atlases   = _read_jsonl(reg / "atlases.jsonl")
        self.products  = _read_jsonl(reg / "products.jsonl")
        self.questions = _read_jsonl(reg / "questions.jsonl")

    def build(self) -> Dict:
        adapters  = self._scan_adapters()
        packages  = self._scan_packages()
        warnings: List[str] = []

        # 1) adapter cross-check: every adapter's analysis_id should be in
        # analysis_registry. Stub adapters get a warning, not an error.
        registered = {a["analysis_id"] for a in self.analyses}
        for ad in adapters:
            if ad["analysis_id"] not in registered:
                warnings.append(f"adapter analysis_id {ad['analysis_id']!r} not in analysis_registry.jsonl")

        # 2) panel cross-check
        layer_ids = {l["layer_id"] for l in self.layers}
        for p in self.panels:
            if p.get("layer_id") not in layer_ids:
                warnings.append(f"panel {p['panel_id']!r} layer_id {p.get('layer_id')!r} not in layer_registry")

        # 3) page cross-check
        panel_ids = {p["panel_id"] for p in self.panels}
        hook_ids  = {h["hook_id"]  for h in self.hooks}
        for pg in self.pages:
            for pn in (pg.get("panels") or []):
                pid = pn.get("panel_id") if isinstance(pn, dict) else pn
                if pid and pid not in panel_ids:
                    warnings.append(f"page {pg['page_id']!r} references unknown panel_id {pid!r}")
            if pg.get("hook_id") and pg["hook_id"] not in hook_ids:
                warnings.append(f"page {pg['page_id']!r} hook_id {pg['hook_id']!r} not in hook_registry")

        # 4) edges: layers → analyses (input), analyses → layers (output),
        # layers → hooks (required + optional), layers → panels (consumed),
        # panels → pages (member), analyses → packages (member),
        # adapters → analyses (backs)
        edges: List[Dict] = []
        for a in self.analyses:
            aid = a["analysis_id"]
            for lid in _csv(a.get("input_layer_types")): edges.append({"from": lid, "to": aid, "kind": "input"})
            for lid in _csv(a.get("produces")):          edges.append({"from": aid, "to": lid, "kind": "output"})
        for h in self.hooks:
            hid = h["hook_id"]
            for lid in _csv(h.get("requires_layers")): edges.append({"from": lid, "to": hid, "kind": "hook_required"})
            for lid in _csv(h.get("optional_layers")): edges.append({"from": lid, "to": hid, "kind": "hook_optional"})
        for p in self.panels:
            edges.append({"from": p["layer_id"], "to": p["panel_id"], "kind": "panel_renders"})
        for pg in self.pages:
            for pn in (pg.get("panels") or []):
                pid = pn.get("panel_id") if isinstance(pn, dict) else pn
                if pid: edges.append({"from": pid, "to": pg["page_id"], "kind": "page_member"})
            if pg.get("hook_id"): edges.append({"from": pg["hook_id"], "to": pg["page_id"], "kind": "page_hook"})
        for pkg in packages:
            for a in pkg.get("analyses", []):
                edges.append({"from": a["analysis_id"], "to": pkg["package_id"], "kind": "package_analysis"})
            for p in pkg.get("panels", []):
                edges.append({"from": p["panel_id"], "to": pkg["package_id"], "kind": "package_panel"})
        for ad in adapters:
            edges.append({"from": ad["analysis_id"] + "_adapter", "to": ad["analysis_id"], "kind": "adapter_backs"})

        # atlas membership: product → atlas, question → atlas (by tag inference)
        atlas_ids = {a["atlas_id"] for a in self.atlases}
        for p in self.products:
            aid = p.get("atlas", "")
            if aid in atlas_ids:
                edges.append({"from": p["product_id"], "to": aid, "kind": "atlas_member_product"})
        for q in self.questions:
            tags = q.get("tags", []) or []
            # crude tag → atlas inference (kept light; the atlas can override)
            cand = None
            if "meiosis" in tags or "interchromosomal" in tags: cand = "meiosis_atlas"
            elif "mendelian" in tags or "path_a" in tags or "path_b" in tags: cand = "relatedness_atlas"
            elif "inversions" in tags or "pair_relation" in tags: cand = "inversion_atlas"
            if cand and cand in atlas_ids:
                edges.append({"from": q["question_id"], "to": cand, "kind": "atlas_member_question"})

        # nodes (denormalised view)
        nodes = []
        for l in self.layers:    nodes.append({"id": l["layer_id"],     "type": "layer",    "label": l.get("label", ""),    "status": l.get("status", "")})
        for a in self.analyses:  nodes.append({"id": a["analysis_id"],  "type": "analysis", "label": a.get("label", ""),    "status": a.get("status", "")})
        for h in self.hooks:     nodes.append({"id": h["hook_id"],      "type": "hook",     "label": h.get("label", ""),    "status": h.get("status", "")})
        for p in self.panels:    nodes.append({"id": p["panel_id"],     "type": "panel",    "label": p.get("label", ""),    "status": p.get("status", ""), "layer_id": p.get("layer_id")})
        for pg in self.pages:    nodes.append({"id": pg["page_id"],     "type": "page",     "label": pg.get("label", ""),   "status": pg.get("status", "")})
        for pkg in packages:     nodes.append({"id": pkg["package_id"], "type": "package",  "label": pkg.get("label", ""),  "status": pkg.get("status", "")})
        for atl in self.atlases: nodes.append({"id": atl["atlas_id"],   "type": "atlas",    "label": atl.get("label", ""),  "status": atl.get("status", ""), "color": atl.get("color", "")})
        for ad in adapters:      nodes.append({"id": ad["analysis_id"] + "_adapter", "type": "adapter",
                                              "label": ad.get("label", ""), "status": ad.get("status", ""),
                                              "input_layer_types": ad.get("input_layer_types", []),
                                              "produces": ad.get("produces", [])})

        return {
            "schema_version": "connection_map_v1",
            "registry_root":  str(self.registry_root),
            "n_nodes":        len(nodes),
            "n_edges":        len(edges),
            "warnings":       warnings,
            "nodes":          nodes,
            "edges":          edges,
            "adapters":       adapters,
            "packages":       packages,
        }

    def _scan_adapters(self) -> List[Dict]:
        out = []
        adir = self.toolkit_root / "analysis"
        if not adir.is_dir(): return out
        for sub in sorted(adir.iterdir()):
            if not sub.is_dir(): continue
            js = sub / "adapter_atlas.js"
            meta = _parse_adapter_meta(js)
            if meta:
                meta.setdefault("analysis_id", sub.name)
                meta["_path"] = str(js.relative_to(self.toolkit_root))
                out.append(meta)
        return out

    def _scan_packages(self) -> List[Dict]:
        out = []
        pdir = self.toolkit_root / "packages"
        if not pdir.is_dir(): return out
        for sub in sorted(pdir.iterdir()):
            if not sub.is_dir(): continue
            mani = sub / "manifest.json"
            obj = _read_json(mani)
            if obj:
                obj["_path"] = str(mani.relative_to(self.toolkit_root))
                out.append(obj)
        return out


def _csv(s) -> List[str]:
    if isinstance(s, list): return [x for x in s if x]
    return [x.strip() for x in (s or "").split(",") if x.strip()]


# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--registry-root", default=None)
    ap.add_argument("--out", default=None, help="path to write connection_map.json; default = <registry_root>/01_registry/connection_map.json")
    ap.add_argument("--print", action="store_true", help="also print the JSON to stdout")
    args = ap.parse_args()

    start = pathlib.Path(args.registry_root) if args.registry_root else pathlib.Path(__file__).parent
    registry_root = _find_root(start)
    toolkit_root  = _find_toolkit_root(registry_root)
    if toolkit_root is None:
        raise SystemExit("could not find analysis/ or packages/ above " + str(registry_root))

    cm = ConnectionMapBuilder(registry_root, toolkit_root).build()
    out_path = pathlib.Path(args.out) if args.out else (registry_root / "01_registry" / "connection_map.json")
    out_path.write_text(json.dumps(cm, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {out_path}  ({cm['n_nodes']} nodes, {cm['n_edges']} edges, {len(cm['warnings'])} warnings)")
    if cm["warnings"]:
        for w in cm["warnings"]: print("  warn:", w)
    if args.print:
        print(json.dumps(cm, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
